#!/usr/bin/env python3
"""
Deterministic Worksheet Planner.

Converts a WorksheetRequest into a WorksheetPlan using the curriculum graph.
All outputs are deterministic — same input always produces same plan.

Usage:
    python engine/planner.py --skill_id SUB-02 --difficulty L2 --count 10 --mode MODEL_HEAVY
    python engine/planner.py --skill_id MUL-01 --difficulty L1 --count 5 --mode OBJECT_ALLOWED --theme animals
"""

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GRAPH_PATH = ROOT / "curriculum" / "grade_3" / "math.graph.json"
SPECS_PATH = ROOT / "curriculum" / "visual_model_specs.json"

# All valid representation types
REPR_TYPES = ["NUMERIC", "WORD_PROBLEM", "PICTORIAL_MODEL", "PICTORIAL_OBJECT"]

# Mode → target distribution as (repr_type, fraction) pairs.
# Order matters: earlier entries get floor'd slots, last gets remainder.
MODE_DISTRIBUTIONS = {
    "AUTO": [
        ("__DEFAULT__", 0.60),
        ("NUMERIC", 0.20),
        ("WORD_PROBLEM", 0.20),
    ],
    "MODEL_HEAVY": [
        ("PICTORIAL_MODEL", 0.70),
        ("NUMERIC", 0.15),
        ("WORD_PROBLEM", 0.15),
    ],
    "WORD_HEAVY": [
        ("WORD_PROBLEM", 0.60),
        ("__DEFAULT__", 0.25),
        ("NUMERIC", 0.15),
    ],
    "NUMERIC_ONLY": [
        ("NUMERIC", 1.0),
    ],
    "OBJECT_ALLOWED": [
        ("PICTORIAL_OBJECT", 0.40),
        ("PICTORIAL_MODEL", 0.30),
        ("NUMERIC", 0.15),
        ("WORD_PROBLEM", 0.15),
    ],
    "MIXED": [],  # handled specially: even split over allowed types
}

# Base rules applied to every question
BASE_RULES = [
    "strict_json_only",
    "no_free_text_outside_fields",
    "numbers_within_node_difficulty_bounds",
]


def load_graph() -> dict:
    with open(GRAPH_PATH) as f:
        return json.load(f)


def load_specs() -> dict:
    with open(SPECS_PATH) as f:
        return json.load(f)


def resolve_node(graph: dict, skill_id: str) -> dict | None:
    for node in graph["nodes"]:
        if node["skill_id"] == skill_id:
            return node
    return None


def _allowed_repr_set(node: dict) -> list[str]:
    """Build the full set of allowed representation types for a node.

    NUMERIC and WORD_PROBLEM are always allowed.
    PICTORIAL_MODEL is allowed if "PICTORIAL_MODEL" is in allowed_representation_mix.
    PICTORIAL_OBJECT is allowed if "PICTORIAL_OBJECT" is in allowed_representation_mix.
    """
    allowed = ["NUMERIC", "WORD_PROBLEM"]
    mix = node.get("allowed_representation_mix", [])
    if "PICTORIAL_MODEL" in mix:
        allowed.append("PICTORIAL_MODEL")
    if "PICTORIAL_OBJECT" in mix:
        allowed.append("PICTORIAL_OBJECT")
    return allowed


def _compute_distribution(
    mode: str,
    node: dict,
    question_count: int,
) -> tuple[list[str], list[str]]:
    """Compute a deterministic representation list for each question slot.

    Returns (representation_list, warnings).
    """
    warnings: list[str] = []
    allowed = _allowed_repr_set(node)
    default_repr = node.get("default_representation", "PICTORIAL_MODEL")

    # Resolve __DEFAULT__ placeholder
    def resolve_type(t: str) -> str:
        return default_repr if t == "__DEFAULT__" else t

    if mode == "MIXED":
        # Even split over all allowed types
        n = len(allowed)
        base = question_count // n
        remainder = question_count % n
        slots: list[str] = []
        for i, rtype in enumerate(allowed):
            count = base + (1 if i < remainder else 0)
            slots.extend([rtype] * count)
        return slots, warnings

    dist = MODE_DISTRIBUTIONS.get(mode, MODE_DISTRIBUTIONS["AUTO"])

    # Resolve types and clamp to allowed
    resolved_dist: list[tuple[str, float]] = []
    for rtype_raw, frac in dist:
        rtype = resolve_type(rtype_raw)
        if rtype not in allowed:
            warnings.append(
                f"Representation '{rtype}' not allowed for skill "
                f"'{node['skill_id']}'; downgraded to '{default_repr}'"
            )
            rtype = default_repr
        resolved_dist.append((rtype, frac))

    # Normalize fractions (in case duplicates merged)
    total_frac = sum(f for _, f in resolved_dist)
    if total_frac == 0:
        resolved_dist = [(default_repr, 1.0)]
        total_frac = 1.0

    # Allocate slots deterministically: floor each, assign remainders in order
    raw_counts: list[tuple[str, float]] = []
    for rtype, frac in resolved_dist:
        raw_counts.append((rtype, (frac / total_frac) * question_count))

    allocated: dict[str, int] = {}
    remainders: list[tuple[str, float]] = []
    for rtype, raw in raw_counts:
        floored = math.floor(raw)
        allocated[rtype] = allocated.get(rtype, 0) + floored
        remainders.append((rtype, raw - floored))

    # Sort remainders descending (stable — original order breaks ties)
    remainders.sort(key=lambda x: -x[1])
    leftover = question_count - sum(allocated.values())
    for i in range(leftover):
        rtype = remainders[i % len(remainders)][0]
        allocated[rtype] = allocated.get(rtype, 0) + 1

    # Build ordered slot list (deterministic: by REPR_TYPES order)
    slots = []
    for rtype in REPR_TYPES:
        if rtype in allocated:
            slots.extend([rtype] * allocated[rtype])

    # Safety: if total doesn't match (shouldn't happen), pad with default
    while len(slots) < question_count:
        slots.append(default_repr)
        warnings.append(f"Padded extra slot with default '{default_repr}'")
    slots = slots[:question_count]

    return slots, warnings


def _pick_visual_refs(
    representation: str,
    node: dict,
    specs_model_ids: set[str],
) -> list[str]:
    """Select visual_model_ref for a question based on its representation."""
    if representation == "PICTORIAL_OBJECT":
        return ["OBJECT_ASSET_PACK_BASIC"]

    if representation == "PICTORIAL_MODEL":
        # Use the node's visual_model_ref, filtering out OBJECT_ASSET_PACK_BASIC
        refs = [
            r
            for r in node.get("visual_model_ref", [])
            if r != "OBJECT_ASSET_PACK_BASIC" and r in specs_model_ids
        ]
        return refs if refs else node.get("visual_model_ref", [])[:1]

    # NUMERIC / WORD_PROBLEM → no visual model
    return []


def _rules_for_question(representation: str, difficulty: str) -> list[str]:
    """Build the rule set for a single question."""
    rules = list(BASE_RULES)

    if representation == "PICTORIAL_MODEL":
        rules.append("visual_must_match_model_spec_parameters")
        rules.append("no_random_decorative_art")
    elif representation == "PICTORIAL_OBJECT":
        rules.append("if_object_then_use_asset_pack_only")
        rules.append("object_shape_must_be_explicit")
        rules.append("object_color_must_be_explicit")
        rules.append("no_circle_unless_shape_is_simple_circle")
    elif representation == "WORD_PROBLEM":
        rules.append("word_problem_must_have_clear_question")
        rules.append("word_problem_context_matches_theme")

    if difficulty == "L3":
        rules.append("allow_multi_step_reasoning")

    return rules


def _apply_mix_override(
    mix_override: list[str],
    node: dict,
    question_count: int,
) -> tuple[list[str], list[str]]:
    """Apply an explicit per-question representation override."""
    warnings: list[str] = []
    allowed = _allowed_repr_set(node)
    default_repr = node.get("default_representation", "PICTORIAL_MODEL")

    slots: list[str] = []
    for i, rtype in enumerate(mix_override[:question_count]):
        if rtype not in allowed:
            warnings.append(
                f"Q{i+1:02d}: mix_override '{rtype}' not allowed for "
                f"'{node['skill_id']}'; downgraded to '{default_repr}'"
            )
            slots.append(default_repr)
        else:
            slots.append(rtype)

    # Pad if override is shorter than question_count
    while len(slots) < question_count:
        slots.append(default_repr)
        warnings.append(f"mix_override shorter than question_count; padded with '{default_repr}'")

    return slots, warnings


def build_plan(request: dict) -> dict:
    """Build a deterministic WorksheetPlan from a WorksheetRequest."""
    graph = load_graph()
    specs = load_specs()
    specs_model_ids = {m["model_id"] for m in specs["models"]}

    skill_id = request["skill_id"]
    difficulty = request["difficulty"]
    question_count = request["question_count"]
    rep_pref = request["representation_preference"]
    mode = rep_pref["mode"]

    # Resolve node
    node = resolve_node(graph, skill_id)
    if node is None:
        valid_ids = sorted(n["skill_id"] for n in graph["nodes"])
        raise ValueError(
            f"skill_id '{skill_id}' not found in curriculum graph. "
            f"Valid IDs: {valid_ids}"
        )

    # Compute representation slots
    mix_override = rep_pref.get("mix_override")
    if mix_override:
        slots, warnings = _apply_mix_override(mix_override, node, question_count)
    else:
        slots, warnings = _compute_distribution(mode, node, question_count)

    # Build question plan entries
    questions = []
    for i, representation in enumerate(slots):
        q_id = f"Q{i + 1:02d}"
        visual_refs = _pick_visual_refs(representation, node, specs_model_ids)
        rules = _rules_for_question(representation, difficulty)
        questions.append(
            {
                "q_id": q_id,
                "representation": representation,
                "visual_model_ref": visual_refs,
                "difficulty": difficulty,
                "rules": rules,
            }
        )

    # Build node summary (subset of fields for the plan)
    node_summary = {
        "skill_id": node["skill_id"],
        "skill_name": node["skill_name"],
        "category": node["category"],
        "default_representation": node["default_representation"],
        "allowed_representation_mix": node["allowed_representation_mix"],
        "visual_model_ref": node["visual_model_ref"],
    }

    plan = {
        "request": request,
        "node": node_summary,
        "questions": questions,
        "warnings": warnings,
    }

    return plan


def build_request_from_args(args: argparse.Namespace) -> dict:
    """Build a WorksheetRequest dict from CLI arguments."""
    request: dict = {
        "grade": 3,
        "subject": "Math",
        "skill_id": args.skill_id,
        "difficulty": args.difficulty,
        "question_count": args.count,
        "representation_preference": {
            "mode": args.mode,
        },
    }
    if args.theme:
        request["theme"] = args.theme
    if args.locale:
        request["locale"] = args.locale
    if args.max_number:
        request["constraints"] = {"max_number": args.max_number}
    return request


def main():
    parser = argparse.ArgumentParser(
        description="Deterministic Worksheet Planner — generates a WorksheetPlan JSON"
    )
    parser.add_argument("--skill_id", required=True, help="Skill ID from curriculum graph")
    parser.add_argument(
        "--difficulty", default="L2", choices=["L1", "L2", "L3"], help="Difficulty level"
    )
    parser.add_argument("--count", type=int, default=10, help="Number of questions (5-30)")
    parser.add_argument(
        "--mode",
        default="AUTO",
        choices=["AUTO", "NUMERIC_ONLY", "MODEL_HEAVY", "OBJECT_ALLOWED", "WORD_HEAVY", "MIXED"],
        help="Representation mode",
    )
    parser.add_argument("--theme", default=None, help="Optional theme for word problems")
    parser.add_argument("--locale", default=None, choices=["CBSE", "UAE", "GENERIC"])
    parser.add_argument("--max_number", type=int, default=None, help="Max number constraint")
    parser.add_argument(
        "-o", "--output", default=None, help="Output file path (default: stdout)"
    )

    args = parser.parse_args()

    if args.count < 5 or args.count > 30:
        print("Error: --count must be between 5 and 30", file=sys.stderr)
        sys.exit(1)

    request = build_request_from_args(args)

    try:
        plan = build_plan(request)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    output_json = json.dumps(plan, indent=2)

    if args.output:
        Path(args.output).write_text(output_json + "\n")
        print(f"Plan written to {args.output}", file=sys.stderr)
    else:
        print(output_json)

    # Print summary to stderr
    repr_counts: dict[str, int] = {}
    for q in plan["questions"]:
        r = q["representation"]
        repr_counts[r] = repr_counts.get(r, 0) + 1
    print(f"\n--- Plan Summary ---", file=sys.stderr)
    print(f"Skill: {plan['node']['skill_id']} ({plan['node']['skill_name']})", file=sys.stderr)
    print(f"Questions: {len(plan['questions'])}", file=sys.stderr)
    print(f"Distribution: {repr_counts}", file=sys.stderr)
    if plan["warnings"]:
        print(f"Warnings: {len(plan['warnings'])}", file=sys.stderr)
        for w in plan["warnings"]:
            print(f"  - {w}", file=sys.stderr)
    print(f"---", file=sys.stderr)


if __name__ == "__main__":
    main()
