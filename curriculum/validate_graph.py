#!/usr/bin/env python3
"""Validate curriculum graph and visual model specs."""

import json
import sys
from pathlib import Path

CURRICULUM_DIR = Path(__file__).parent
SPECS_PATH = CURRICULUM_DIR / "visual_model_specs.json"
GRAPH_PATH = CURRICULUM_DIR / "grade_3" / "math.graph.json"

OBJECT_ALLOWED_SKILLS = {"MUL-01", "DIV-01", "DIV-03", "SUB-01"}


def load_json(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def check_1_skill_refs(nodes_by_id: dict) -> list[str]:
    """All skill_ids in next_skills and siblings must exist as nodes."""
    errors = []
    for sid, node in nodes_by_id.items():
        for ref in node.get("next_skills", []):
            if ref not in nodes_by_id:
                errors.append(f"[CHECK 1] {sid} → next_skills ref '{ref}' not found")
        for ref in node.get("siblings", []):
            if ref not in nodes_by_id:
                errors.append(f"[CHECK 1] {sid} → siblings ref '{ref}' not found")
        for ref in node.get("prerequisites", []):
            if ref not in nodes_by_id:
                errors.append(f"[CHECK 1] {sid} → prerequisites ref '{ref}' not found")
    return errors


def check_2_visual_refs(nodes_by_id: dict, model_ids: set) -> list[str]:
    """All visual_model_ref entries must exist in visual_model_specs.json."""
    errors = []
    for sid, node in nodes_by_id.items():
        for ref in node.get("visual_model_ref", []):
            if ref not in model_ids:
                errors.append(f"[CHECK 2] {sid} → visual_model_ref '{ref}' not in specs")
    return errors


def check_3_required_fields(nodes_by_id: dict) -> list[str]:
    """Every node must have default_representation and allowed_representation_mix."""
    errors = []
    for sid, node in nodes_by_id.items():
        if "default_representation" not in node:
            errors.append(f"[CHECK 3] {sid} missing 'default_representation'")
        if "allowed_representation_mix" not in node:
            errors.append(f"[CHECK 3] {sid} missing 'allowed_representation_mix'")
    return errors


def check_4_object_default(nodes_by_id: dict) -> list[str]:
    """If default_representation == PICTORIAL_OBJECT, must ref OBJECT_ASSET_PACK_BASIC."""
    errors = []
    for sid, node in nodes_by_id.items():
        if node.get("default_representation") == "PICTORIAL_OBJECT":
            if "OBJECT_ASSET_PACK_BASIC" not in node.get("visual_model_ref", []):
                errors.append(
                    f"[CHECK 4] {sid} defaults to PICTORIAL_OBJECT but missing OBJECT_ASSET_PACK_BASIC ref"
                )
    return errors


def check_5_object_restriction(nodes_by_id: dict) -> list[str]:
    """PICTORIAL_OBJECT in allowed_representation_mix only for designated skills."""
    errors = []
    for sid, node in nodes_by_id.items():
        mix = node.get("allowed_representation_mix", [])
        has_object = "PICTORIAL_OBJECT" in mix
        if has_object and sid not in OBJECT_ALLOWED_SKILLS:
            errors.append(
                f"[CHECK 5] {sid} has PICTORIAL_OBJECT but is not in allowed set {OBJECT_ALLOWED_SKILLS}"
            )
        if not has_object and sid in OBJECT_ALLOWED_SKILLS:
            errors.append(
                f"[CHECK 5] {sid} should have PICTORIAL_OBJECT but doesn't"
            )
    # Also check that skills with PICTORIAL_OBJECT have OBJECT_ASSET_PACK_BASIC in visual_model_ref
    for sid in OBJECT_ALLOWED_SKILLS:
        if sid in nodes_by_id:
            refs = nodes_by_id[sid].get("visual_model_ref", [])
            if "OBJECT_ASSET_PACK_BASIC" not in refs:
                errors.append(
                    f"[CHECK 5] {sid} allows PICTORIAL_OBJECT but missing OBJECT_ASSET_PACK_BASIC in visual_model_ref"
                )
    return errors


def check_6_integrity(graph: dict, nodes_by_id: dict) -> list[str]:
    """No circular next_skills, version is 1.1.0, no dangling refs."""
    errors = []

    # Version check
    if graph.get("version") != "1.1.0":
        errors.append(f"[CHECK 6] Graph version is '{graph.get('version')}', expected '1.1.0'")

    # Cycle detection via DFS
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {sid: WHITE for sid in nodes_by_id}

    def dfs(sid, path):
        cycle_errors = []
        color[sid] = GRAY
        for nxt in nodes_by_id[sid].get("next_skills", []):
            if nxt not in nodes_by_id:
                continue  # already caught by check_1
            if color[nxt] == GRAY:
                cycle_errors.append(
                    f"[CHECK 6] Cycle detected: {' → '.join(path + [nxt])}"
                )
            elif color[nxt] == WHITE:
                cycle_errors.extend(dfs(nxt, path + [nxt]))
        color[sid] = BLACK
        return cycle_errors

    for sid in nodes_by_id:
        if color[sid] == WHITE:
            errors.extend(dfs(sid, [sid]))

    return errors


def main():
    print("=" * 60)
    print("  Curriculum Graph Validation")
    print("=" * 60)

    # Load files
    try:
        specs = load_json(SPECS_PATH)
        print(f"  Loaded visual_model_specs.json — {len(specs['models'])} models")
    except Exception as e:
        print(f"  FATAL: Cannot load {SPECS_PATH}: {e}")
        sys.exit(1)

    try:
        graph = load_json(GRAPH_PATH)
        print(f"  Loaded math.graph.json — {len(graph['nodes'])} nodes")
    except Exception as e:
        print(f"  FATAL: Cannot load {GRAPH_PATH}: {e}")
        sys.exit(1)

    model_ids = {m["model_id"] for m in specs["models"]}
    nodes_by_id = {n["skill_id"]: n for n in graph["nodes"]}

    print(f"  Model IDs: {sorted(model_ids)}")
    print(f"  Skill IDs: {sorted(nodes_by_id.keys())}")
    print("-" * 60)

    all_errors = []
    checks = [
        ("1. Skill reference integrity", lambda: check_1_skill_refs(nodes_by_id)),
        ("2. Visual model refs exist in specs", lambda: check_2_visual_refs(nodes_by_id, model_ids)),
        ("3. Required fields present", lambda: check_3_required_fields(nodes_by_id)),
        ("4. OBJECT default requires asset pack", lambda: check_4_object_default(nodes_by_id)),
        ("5. PICTORIAL_OBJECT restriction", lambda: check_5_object_restriction(nodes_by_id)),
        ("6. Integrity (cycles, version)", lambda: check_6_integrity(graph, nodes_by_id)),
    ]

    for name, fn in checks:
        errors = fn()
        status = "PASS" if not errors else "FAIL"
        print(f"  [{status}] {name}")
        for e in errors:
            print(f"         {e}")
        all_errors.extend(errors)

    print("-" * 60)
    if all_errors:
        print(f"  RESULT: {len(all_errors)} error(s) found")
        sys.exit(1)
    else:
        print("  RESULT: All 6 checks passed")
        sys.exit(0)


if __name__ == "__main__":
    main()
