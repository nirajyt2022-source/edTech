#!/usr/bin/env python3
"""
SVG Render Orchestrator.

Reads output.json, dispatches PICTORIAL_MODEL questions to the correct
renderer, writes SVG artifacts and a render manifest.

Usage:
    python engine/render_svg.py --output output.json --run-id demo_sub02_l2
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPECS_PATH = ROOT / "curriculum" / "visual_model_specs.json"
ARTIFACTS_DIR = ROOT / "artifacts"

# Renderer registry — model_id → module.function
RENDERER_REGISTRY: dict[str, str] = {
    "BASE_TEN_REGROUPING": "engine.renderers.base_ten_regrouping:render_base_ten_regrouping",
    "NUMBER_LINE": "engine.renderers.number_line:render_number_line",
    "ARRAYS": "engine.renderers.arrays:render_arrays",
    "FRACTION_STRIPS": "engine.renderers.fraction_strips:render_fraction_strips",
    "FRACTION_SHAPES": "engine.renderers.fraction_strips:render_fraction_shapes",
}


def _load_renderer(model_id: str):
    """Dynamically load a renderer function by model_id."""
    if model_id not in RENDERER_REGISTRY:
        return None
    module_path, func_name = RENDERER_REGISTRY[model_id].rsplit(":", 1)
    # Convert dotted module path to file path for direct import
    parts = module_path.split(".")
    py_path = ROOT / "/".join(parts) / f"../{parts[-1]}.py"
    # Use importlib instead
    import importlib
    mod = importlib.import_module(module_path)
    return getattr(mod, func_name)


def load_json(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def render_all(output_path: Path, run_id: str) -> dict:
    """Render all pictorial questions and write artifacts.

    Returns {"manifest_path": str, "manifest": dict, "errors": list}
    """
    output_data = load_json(output_path)
    model_specs = load_json(SPECS_PATH)

    run_dir = ARTIFACTS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    manifest_entries: list[dict] = []
    errors: list[dict] = []

    for q in output_data.get("questions", []):
        q_id = q.get("q_id", "???")
        representation = q.get("representation", "")

        if representation not in ("PICTORIAL_MODEL", "PICTORIAL_OBJECT"):
            continue

        visual_spec = q.get("visual_spec")
        if not visual_spec:
            errors.append({
                "q_id": q_id,
                "code": "missing_visual_spec",
                "detail": f"{q_id}: PICTORIAL question has no visual_spec",
            })
            continue

        model_id = visual_spec.get("model_id", "")
        planned_refs = q.get("visual_model_ref", [])

        # Pre-render check: model_id must be in planned refs
        if model_id not in planned_refs:
            errors.append({
                "q_id": q_id,
                "code": "model_id_mismatch",
                "detail": f"{q_id}: visual_spec.model_id '{model_id}' not in planned refs {planned_refs}",
            })
            continue

        renderer = _load_renderer(model_id)
        if renderer is None:
            errors.append({
                "q_id": q_id,
                "code": "no_renderer",
                "detail": f"{q_id}: No renderer registered for model '{model_id}'",
            })
            continue

        # Render
        try:
            result = renderer(visual_spec, model_specs)
        except Exception as e:
            errors.append({
                "q_id": q_id,
                "code": "render_error",
                "detail": f"{q_id}: Renderer raised {type(e).__name__}: {e}",
            })
            continue

        # Write SVG
        svg_filename = f"{q_id}.svg"
        svg_path = run_dir / svg_filename
        svg_path.write_text(result["svg"])

        # Write metadata
        meta_filename = f"{q_id}.meta.json"
        meta_path = run_dir / meta_filename
        meta_path.write_text(json.dumps(result["metadata"], indent=2))

        manifest_entries.append({
            "q_id": q_id,
            "model_id": model_id,
            "svg_path": str(svg_path),
            "meta_path": str(meta_path),
            "width": result["width"],
            "height": result["height"],
        })

    manifest = {
        "run_id": run_id,
        "output_source": str(output_path),
        "entries": manifest_entries,
        "errors": errors,
    }

    manifest_path = run_dir / "render_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    return {
        "manifest_path": str(manifest_path),
        "manifest": manifest,
        "errors": errors,
    }


def main():
    # Add project root to path for imports
    sys.path.insert(0, str(ROOT))

    parser = argparse.ArgumentParser(description="Render SVGs for pictorial questions")
    parser.add_argument("--output", required=True, help="Path to output.json")
    parser.add_argument("--run-id", required=True, help="Unique run identifier")

    args = parser.parse_args()
    output_path = Path(args.output)

    if not output_path.exists():
        print(f"Error: {output_path} not found", file=sys.stderr)
        sys.exit(1)

    result = render_all(output_path, args.run_id)

    print(f"Manifest: {result['manifest_path']}")
    print(f"Rendered: {len(result['manifest']['entries'])} SVGs")
    if result["errors"]:
        print(f"Errors: {len(result['errors'])}")
        for e in result["errors"]:
            print(f"  [{e['q_id']}] {e['code']}: {e['detail']}")
        sys.exit(1)
    else:
        print("No errors.")


if __name__ == "__main__":
    main()
