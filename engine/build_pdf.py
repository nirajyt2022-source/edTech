#!/usr/bin/env python3
"""
End-to-end PDF build pipeline.

Steps:
1. Validate output against plan (engine/validate_output.py)
2. Render SVGs for pictorial questions (engine/render_svg.py)
3. Run visual self-checks (engine/visual_check.py)
4. Export PDF (engine/export_pdf.py)

If any step fails, the pipeline aborts with errors.

Usage:
    python engine/build_pdf.py --plan plan.json --output output.json \\
        --out worksheet.pdf --run-id demo_sub02_l2
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.validate_output import validate, load_json
from engine.render_svg import render_all
from engine.visual_check import run_checks
from engine.export_pdf import export_pdf


def main():
    parser = argparse.ArgumentParser(description="End-to-end worksheet PDF builder")
    parser.add_argument("--plan", required=True, help="Path to plan.json")
    parser.add_argument("--output", required=True, help="Path to output.json")
    parser.add_argument("--out", default="worksheet.pdf", help="Output PDF path")
    parser.add_argument("--run-id", default="run", help="Unique run identifier")
    parser.add_argument("--include-answers", action="store_true", help="Include answer key")

    args = parser.parse_args()
    plan_path = Path(args.plan)
    output_path = Path(args.output)
    out_path = Path(args.out)

    print("=" * 60)
    print("  PracticeCraft — PDF Build Pipeline")
    print("=" * 60)

    # --- Step 1: Validate output against plan ---
    print("\n[1/4] Validating output against plan...")
    try:
        plan = load_json(plan_path)
        output_data = load_json(output_path)
    except Exception as e:
        print(f"  FATAL: Cannot load input files: {e}")
        sys.exit(1)

    validation_errors = validate(plan, output_data)
    hard_errors = [e for e in validation_errors if e["severity"] == "ERROR"]
    warnings = [e for e in validation_errors if e["severity"] == "WARNING"]

    if hard_errors:
        print(f"  FAILED: {len(hard_errors)} validation error(s)")
        for e in hard_errors:
            q_part = f" [{e['q_id']}]" if e["q_id"] else ""
            print(f"    ERROR{q_part}: {e['message']}")
        sys.exit(1)

    if warnings:
        for w in warnings:
            q_part = f" [{w['q_id']}]" if w["q_id"] else ""
            print(f"    WARN{q_part}: {w['message']}")

    print(f"  PASSED ({len(output_data.get('questions', []))} questions validated)")

    # --- Step 2: Render SVGs ---
    print("\n[2/4] Rendering SVGs...")
    render_result = render_all(output_path, args.run_id)

    if render_result["errors"]:
        print(f"  FAILED: {len(render_result['errors'])} render error(s)")
        for e in render_result["errors"]:
            print(f"    [{e['q_id']}] {e['code']}: {e['detail']}")
        sys.exit(1)

    entry_count = len(render_result["manifest"]["entries"])
    print(f"  PASSED ({entry_count} SVGs rendered)")
    print(f"  Manifest: {render_result['manifest_path']}")

    # --- Step 3: Visual self-checks ---
    print("\n[3/4] Running visual self-checks...")
    manifest = render_result["manifest"]
    visual_errors = run_checks(manifest)

    if visual_errors:
        print(f"  FAILED: {len(visual_errors)} visual check error(s)")
        for e in visual_errors:
            print(f"    [{e['q_id']}] {e['code']}: {e['detail']}")
        sys.exit(1)

    print(f"  PASSED (all {entry_count} SVGs pass visual checks)")

    # --- Step 4: Export PDF ---
    print("\n[4/4] Exporting PDF...")
    try:
        export_pdf(output_data, manifest, out_path, args.include_answers)
    except Exception as e:
        print(f"  FAILED: PDF export error: {e}")
        sys.exit(1)

    print(f"  DONE: {out_path}")

    print("\n" + "=" * 60)
    print(f"  BUILD COMPLETE — {out_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
