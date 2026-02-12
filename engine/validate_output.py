#!/usr/bin/env python3
"""
Worksheet Output Validator.

Validates a generated WorksheetOutput JSON against its WorksheetPlan
and basic correctness rules.

Usage:
    python engine/validate_output.py --plan plan.json --output output.json
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPECS_PATH = ROOT / "curriculum" / "visual_model_specs.json"

VALID_REPRESENTATIONS = {"NUMERIC", "WORD_PROBLEM", "PICTORIAL_MODEL", "PICTORIAL_OBJECT"}
VALID_ANSWERS = {"A", "B", "C", "D"}
OBJECT_ALLOWED_SHAPES = {"rounded_rect", "simple_circle", "triangle", "star"}
OBJECT_ALLOWED_COLORS = {"red", "blue", "green", "yellow", "orange", "purple", "brown", "black"}


def load_json(path: str | Path) -> dict:
    with open(path) as f:
        return json.load(f)


def load_specs_model_ids() -> set[str]:
    specs = load_json(SPECS_PATH)
    return {m["model_id"] for m in specs["models"]}


def validate(plan: dict, output: dict) -> list[dict]:
    """Validate output against plan. Returns list of structured errors."""
    errors: list[dict] = []
    specs_ids = load_specs_model_ids()

    def err(check: str, q_id: str | None, message: str, severity: str = "ERROR"):
        errors.append({
            "check": check,
            "q_id": q_id,
            "message": message,
            "severity": severity,
        })

    plan_questions = plan.get("questions", [])
    output_questions = output.get("questions", [])

    # --- Check 1: Question count ---
    expected_count = len(plan_questions)
    actual_count = len(output_questions)
    if actual_count != expected_count:
        err("question_count", None, f"Expected {expected_count} questions, got {actual_count}")

    # Build plan lookup
    plan_by_qid = {q["q_id"]: q for q in plan_questions}
    output_by_qid = {q.get("q_id"): q for q in output_questions}

    # --- Check 2: q_id existence and representation match ---
    for pq in plan_questions:
        q_id = pq["q_id"]
        oq = output_by_qid.get(q_id)
        if oq is None:
            err("q_id_missing", q_id, f"Planned question {q_id} not found in output")
            continue

        # Representation match
        expected_repr = pq["representation"]
        actual_repr = oq.get("representation")
        if actual_repr != expected_repr:
            err(
                "representation_mismatch",
                q_id,
                f"Expected representation '{expected_repr}', got '{actual_repr}'",
            )

        # --- Check 3: visual_model_ref correctness ---
        planned_refs = set(pq.get("visual_model_ref", []))
        actual_refs = set(oq.get("visual_model_ref", []))

        if expected_repr in ("NUMERIC", "WORD_PROBLEM"):
            if actual_refs:
                err(
                    "visual_ref_non_pictorial",
                    q_id,
                    f"Non-pictorial question should have empty visual_model_ref, got {sorted(actual_refs)}",
                )
        elif expected_repr == "PICTORIAL_MODEL":
            if not actual_refs:
                err("visual_ref_empty", q_id, "PICTORIAL_MODEL question has empty visual_model_ref")
            for ref in actual_refs:
                if ref not in specs_ids:
                    err("visual_ref_unknown", q_id, f"visual_model_ref '{ref}' not in specs")
                if ref not in planned_refs:
                    err(
                        "visual_ref_unplanned",
                        q_id,
                        f"visual_model_ref '{ref}' not in planned refs {sorted(planned_refs)}",
                        severity="WARNING",
                    )
        elif expected_repr == "PICTORIAL_OBJECT":
            if "OBJECT_ASSET_PACK_BASIC" not in actual_refs:
                err(
                    "visual_ref_object_missing",
                    q_id,
                    "PICTORIAL_OBJECT must reference OBJECT_ASSET_PACK_BASIC",
                )

        # --- Check 3b: visual_spec validation ---
        visual_spec = oq.get("visual_spec")
        if expected_repr in ("PICTORIAL_MODEL", "PICTORIAL_OBJECT") and visual_spec:
            spec_model = visual_spec.get("model_id")
            if spec_model and spec_model not in planned_refs:
                err(
                    "visual_spec_model_mismatch",
                    q_id,
                    f"visual_spec.model_id '{spec_model}' not in planned refs",
                )

        # --- Check 4: Basic numeric sanity ---
        answer_value = oq.get("answer_value", "")
        if answer_value and _is_numeric(answer_value):
            num = float(answer_value)
            if num < 0:
                err(
                    "negative_result",
                    q_id,
                    f"Negative answer value ({num}) — not allowed unless explicitly permitted",
                    severity="WARNING",
                )
            # Check for decimals when not allowed
            constraints = plan.get("request", {}).get("constraints", {})
            avoid_decimals = constraints.get("avoid_decimals", True)
            if avoid_decimals and num != int(num):
                err("decimal_result", q_id, f"Decimal answer ({num}) but avoid_decimals is true")

        # --- Check: answer field ---
        answer = oq.get("answer")
        if answer not in VALID_ANSWERS:
            err("invalid_answer", q_id, f"answer must be A/B/C/D, got '{answer}'")

        # --- Check: options ---
        options = oq.get("options", [])
        if len(options) != 4:
            err("options_count", q_id, f"Expected 4 options, got {len(options)}")

        # --- Check: question_text ---
        qtext = oq.get("question_text", "")
        if not qtext or len(qtext.strip()) < 5:
            err("empty_question", q_id, "question_text is empty or too short")

        # --- Check 5: OBJECT-specific validation ---
        if expected_repr == "PICTORIAL_OBJECT" and visual_spec:
            params = visual_spec.get("parameters", {})
            objects = params.get("objects", [])
            if not objects:
                err(
                    "object_no_objects",
                    q_id,
                    "PICTORIAL_OBJECT visual_spec must contain objects array",
                    severity="WARNING",
                )
            for idx, obj in enumerate(objects):
                shape = obj.get("shape")
                color = obj.get("color")
                if not shape:
                    err(
                        "object_shape_missing",
                        q_id,
                        f"Object[{idx}] missing explicit shape",
                    )
                elif shape not in OBJECT_ALLOWED_SHAPES:
                    err(
                        "object_shape_invalid",
                        q_id,
                        f"Object[{idx}] shape '{shape}' not in allowed: {sorted(OBJECT_ALLOWED_SHAPES)}",
                    )
                if shape == "circle":
                    err(
                        "object_circle_forbidden",
                        q_id,
                        f"Object[{idx}] uses 'circle' — must use 'simple_circle' instead",
                    )
                if not color:
                    err(
                        "object_color_missing",
                        q_id,
                        f"Object[{idx}] missing explicit color",
                    )
                elif color not in OBJECT_ALLOWED_COLORS:
                    err(
                        "object_color_invalid",
                        q_id,
                        f"Object[{idx}] color '{color}' not in allowed: {sorted(OBJECT_ALLOWED_COLORS)}",
                    )

    # Check for extra questions in output not in plan
    for oq in output_questions:
        q_id = oq.get("q_id")
        if q_id and q_id not in plan_by_qid:
            err("extra_question", q_id, f"Question {q_id} in output but not in plan")

    return errors


def _is_numeric(value: str) -> bool:
    try:
        float(value)
        return True
    except (ValueError, TypeError):
        return False


def print_results(errors: list[dict]) -> None:
    error_count = sum(1 for e in errors if e["severity"] == "ERROR")
    warn_count = sum(1 for e in errors if e["severity"] == "WARNING")

    print("=" * 60)
    print("  Worksheet Output Validation")
    print("=" * 60)

    if not errors:
        print("  RESULT: All checks passed")
    else:
        for e in errors:
            prefix = "ERROR" if e["severity"] == "ERROR" else "WARN "
            q_part = f" [{e['q_id']}]" if e["q_id"] else ""
            print(f"  [{prefix}]{q_part} {e['check']}: {e['message']}")
        print("-" * 60)
        print(f"  RESULT: {error_count} error(s), {warn_count} warning(s)")


def main():
    parser = argparse.ArgumentParser(
        description="Validate a generated WorksheetOutput against its WorksheetPlan"
    )
    parser.add_argument("--plan", required=True, help="Path to WorksheetPlan JSON")
    parser.add_argument("--output", required=True, help="Path to WorksheetOutput JSON")
    parser.add_argument(
        "--json", action="store_true", help="Output errors as JSON instead of text"
    )

    args = parser.parse_args()

    try:
        plan = load_json(args.plan)
    except Exception as e:
        print(f"Error loading plan: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        output = load_json(args.output)
    except Exception as e:
        print(f"Error loading output: {e}", file=sys.stderr)
        sys.exit(1)

    errors = validate(plan, output)

    if args.json:
        print(json.dumps(errors, indent=2))
    else:
        print_results(errors)

    error_count = sum(1 for e in errors if e["severity"] == "ERROR")
    sys.exit(1 if error_count > 0 else 0)


if __name__ == "__main__":
    main()
