#!/usr/bin/env python3
"""
Visual Self-Check for rendered SVG artifacts.

Checks rendered metadata for correctness:
1. Rendered block counts match expected counts.
2. No overlapping primitives (bounding boxes with epsilon tolerance).
3. All text labels are within canvas bounds.
4. No negative coordinates.

Usage:
    python engine/visual_check.py --manifest artifacts/<run_id>/render_manifest.json
"""

import argparse
import json
import sys
from pathlib import Path

OVERLAP_EPSILON = 2  # pixels tolerance for overlap detection


def load_json(path: str | Path) -> dict:
    with open(path) as f:
        return json.load(f)


def check_counts(q_id: str, meta: dict) -> list[dict]:
    """Check that rendered_counts == expected_counts (BASE_TEN models)."""
    errors = []
    model_id = meta.get("model_id", "")

    # NUMBER_LINE uses point-based checks instead of block counts
    if model_id == "NUMBER_LINE":
        return _check_number_line(q_id, meta)

    # ARRAYS uses total-count checks
    if model_id == "ARRAYS":
        return _check_arrays(q_id, meta)

    # Fraction models use highlight-part checks
    if model_id in ("FRACTION_STRIPS", "FRACTION_SHAPES"):
        return _check_fraction_parts(q_id, meta)

    expected = meta.get("expected_counts", {})
    rendered = meta.get("rendered_counts", {})
    for place in ("hundreds", "tens", "ones"):
        exp = expected.get(place, 0)
        got = rendered.get(place, 0)
        if exp != got:
            errors.append({
                "q_id": q_id,
                "code": "count_mismatch",
                "detail": f"{place}: expected {exp}, rendered {got}",
            })
    return errors


def _check_number_line(q_id: str, meta: dict) -> list[dict]:
    """NUMBER_LINE-specific checks: points match, tick_count correct, label overlaps."""
    errors = []

    # 1. expected_points == rendered_points
    expected_pts = meta.get("expected_points", [])
    rendered_pts = meta.get("rendered_points", [])
    if len(expected_pts) != len(rendered_pts):
        errors.append({
            "q_id": q_id,
            "code": "point_count_mismatch",
            "detail": f"expected {len(expected_pts)} points, rendered {len(rendered_pts)}",
        })
    else:
        for i, (ep, rp) in enumerate(zip(expected_pts, rendered_pts)):
            if abs(ep - rp) > 1e-5:
                errors.append({
                    "q_id": q_id,
                    "code": "point_value_mismatch",
                    "detail": f"point[{i}]: expected {ep}, rendered {rp}",
                })

    # 2. tick_count sanity (must be > 0)
    tick_count = meta.get("tick_count", 0)
    if tick_count < 2:
        errors.append({
            "q_id": q_id,
            "code": "insufficient_ticks",
            "detail": f"tick_count is {tick_count}, expected >= 2",
        })

    # 3. Tick label overlap check
    text_boxes = meta.get("text_boxes", [])
    tick_labels = [tb for tb in text_boxes if tb.get("y", 0) > 70]  # labels below baseline
    for i in range(len(tick_labels)):
        for j in range(i + 1, len(tick_labels)):
            a, b = tick_labels[i], tick_labels[j]
            if _label_boxes_overlap(a, b):
                errors.append({
                    "q_id": q_id,
                    "code": "tick_label_overlap",
                    "detail": f"labels '{a['text']}' and '{b['text']}' overlap",
                })

    return errors


def _check_arrays(q_id: str, meta: dict) -> list[dict]:
    """ARRAYS-specific checks: total counts, items in bounds, no item overlap."""
    errors = []

    # 1. rendered_total == expected_total
    expected_total = meta.get("expected_total", 0)
    rendered_total = meta.get("rendered_total", 0)
    if expected_total != rendered_total:
        errors.append({
            "q_id": q_id,
            "code": "arrays_count_mismatch",
            "detail": f"expected {expected_total} rendered {rendered_total}",
        })

    # 2. All items within canvas bounds (checked by generic check_labels_in_bounds
    #    and check_no_negative_coords — but also verify item bboxes specifically)
    item_boxes = [bb for bb in meta.get("bounding_boxes", []) if bb.get("type") == "item"]
    for i, bb in enumerate(item_boxes):
        if bb["x"] < 0 or bb["y"] < 0:
            errors.append({
                "q_id": q_id,
                "code": "arrays_item_negative",
                "detail": f"item[{i}] at ({bb['x']:.1f},{bb['y']:.1f}) has negative coordinates",
            })

    # 3. No overlap between items
    for i in range(len(item_boxes)):
        for j in range(i + 1, len(item_boxes)):
            if _label_boxes_overlap(item_boxes[i], item_boxes[j]):
                errors.append({
                    "q_id": q_id,
                    "code": "arrays_item_overlap",
                    "detail": (
                        f"item[{i}] at ({item_boxes[i]['x']:.1f},{item_boxes[i]['y']:.1f}) "
                        f"overlaps item[{j}] at ({item_boxes[j]['x']:.1f},{item_boxes[j]['y']:.1f})"
                    ),
                })

    return errors


def _check_fraction_parts(q_id: str, meta: dict) -> list[dict]:
    """FRACTION_STRIPS / FRACTION_SHAPES checks: part counts and highlight totals."""
    errors = []
    model_id = meta.get("model_id", "FRACTION_STRIPS")
    expected = meta.get("expected", {})
    rendered = meta.get("rendered", {})

    # 1. Total parts
    if model_id == "FRACTION_STRIPS":
        exp_parts = expected.get("whole_count", 0) * expected.get("denominator", 1)
    else:
        exp_parts = expected.get("shape_count", 0) * expected.get("denominator", 1)

    got_parts = rendered.get("parts_total", 0)
    if exp_parts != got_parts:
        errors.append({
            "q_id": q_id,
            "code": "fraction_parts_mismatch",
            "detail": f"expected {exp_parts} total parts, rendered {got_parts}",
        })

    # 2. Highlighted parts
    exp_hl = expected.get("highlighted_parts_total", 0)
    got_hl = rendered.get("highlighted_parts_total", 0)
    if exp_hl != got_hl:
        errors.append({
            "q_id": q_id,
            "code": "fraction_highlight_mismatch",
            "detail": f"expected {exp_hl} highlighted parts, rendered {got_hl}",
        })

    # 3. Rectangles within canvas bounds (no negative coords)
    for i, bb in enumerate(meta.get("bounding_boxes", [])):
        if bb["x"] < -1 or bb["y"] < -1:
            errors.append({
                "q_id": q_id,
                "code": "fraction_negative_coords",
                "detail": f"bbox[{i}] type={bb.get('type','')} at ({bb['x']:.1f},{bb['y']:.1f})",
            })

    # 4. Text labels don't overlap strip/shape borders
    text_boxes = meta.get("text_boxes", [])
    border_boxes = [bb for bb in meta.get("bounding_boxes", [])
                    if bb.get("type") in ("strip_border", "shape_border")]
    for tb in text_boxes:
        for bb in border_boxes:
            if _label_boxes_overlap(tb, bb):
                errors.append({
                    "q_id": q_id,
                    "code": "fraction_label_overlaps_shape",
                    "detail": f"label '{tb.get('text','')}' overlaps {bb.get('type','')}",
                })

    return errors


def _label_boxes_overlap(a: dict, b: dict) -> bool:
    """Check if two text label bounding boxes overlap."""
    ax1, ay1 = a["x"], a["y"]
    ax2, ay2 = a["x"] + a["w"], a["y"] + a["h"]
    bx1, by1 = b["x"], b["y"]
    bx2, by2 = b["x"] + b["w"], b["y"] + b["h"]

    if ax1 >= bx2 or bx1 >= ax2:
        return False
    if ay1 >= by2 or by1 >= ay2:
        return False
    return True


def _boxes_overlap(a: dict, b: dict, eps: float = OVERLAP_EPSILON) -> bool:
    """Check if two bounding boxes overlap (with epsilon shrink)."""
    ax1, ay1 = a["x"] + eps, a["y"] + eps
    ax2, ay2 = a["x"] + a["w"] - eps, a["y"] + a["h"] - eps
    bx1, by1 = b["x"] + eps, b["y"] + eps
    bx2, by2 = b["x"] + b["w"] - eps, b["y"] + b["h"] - eps

    if ax1 >= bx2 or bx1 >= ax2:
        return False
    if ay1 >= by2 or by1 >= ay2:
        return False
    return True


def check_no_overlaps(q_id: str, meta: dict) -> list[dict]:
    """Check that no two bounding boxes of the same type overlap."""
    errors = []
    bboxes = meta.get("bounding_boxes", [])

    # Group by type for targeted overlap checks (only check within same-type groups
    # to avoid false positives from intentional layering like arrows over blocks)
    by_type: dict[str, list[dict]] = {}
    for bb in bboxes:
        t = bb.get("type", "unknown")
        by_type.setdefault(t, []).append(bb)

    for btype, boxes in by_type.items():
        if btype == "arrow":
            continue  # arrows can overlap blocks intentionally
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                if _boxes_overlap(boxes[i], boxes[j]):
                    errors.append({
                        "q_id": q_id,
                        "code": "overlap_detected",
                        "detail": (
                            f"{btype}[{i}] at ({boxes[i]['x']},{boxes[i]['y']}) "
                            f"overlaps {btype}[{j}] at ({boxes[j]['x']},{boxes[j]['y']})"
                        ),
                    })
    return errors


def check_labels_in_bounds(q_id: str, meta: dict, canvas_w: int, canvas_h: int) -> list[dict]:
    """Check that all text boxes are within canvas bounds."""
    errors = []
    for i, tb in enumerate(meta.get("text_boxes", [])):
        x, y, w, h = tb["x"], tb["y"], tb["w"], tb["h"]
        if x < 0 or y < 0:
            errors.append({
                "q_id": q_id,
                "code": "label_negative_coords",
                "detail": f"text_box[{i}] '{tb.get('text','')}' at ({x},{y}) has negative coordinates",
            })
        if x + w > canvas_w + 10:  # small tolerance
            errors.append({
                "q_id": q_id,
                "code": "label_out_of_bounds",
                "detail": f"text_box[{i}] '{tb.get('text','')}' extends beyond canvas width ({x+w} > {canvas_w})",
            })
        if y + h > canvas_h + 10:
            errors.append({
                "q_id": q_id,
                "code": "label_out_of_bounds",
                "detail": f"text_box[{i}] '{tb.get('text','')}' extends beyond canvas height ({y+h} > {canvas_h})",
            })
    return errors


def check_no_negative_coords(q_id: str, meta: dict) -> list[dict]:
    """Check that no bounding box has negative coordinates."""
    errors = []
    for i, bb in enumerate(meta.get("bounding_boxes", [])):
        if bb["x"] < 0 or bb["y"] < 0:
            errors.append({
                "q_id": q_id,
                "code": "negative_coordinates",
                "detail": f"{bb['type']}[{i}] at ({bb['x']},{bb['y']}) has negative coordinates",
            })
    return errors


def run_checks(manifest: dict) -> list[dict]:
    """Run all visual checks on a render manifest. Returns error list."""
    all_errors: list[dict] = []

    for entry in manifest.get("entries", []):
        q_id = entry["q_id"]
        meta_path = entry.get("meta_path")
        canvas_w = entry.get("width", 9999)
        canvas_h = entry.get("height", 9999)

        if not meta_path or not Path(meta_path).exists():
            all_errors.append({
                "q_id": q_id,
                "code": "missing_metadata",
                "detail": f"Metadata file not found: {meta_path}",
            })
            continue

        meta = load_json(meta_path)

        all_errors.extend(check_counts(q_id, meta))
        all_errors.extend(check_no_overlaps(q_id, meta))
        all_errors.extend(check_labels_in_bounds(q_id, meta, canvas_w, canvas_h))
        all_errors.extend(check_no_negative_coords(q_id, meta))

    return all_errors


def main():
    parser = argparse.ArgumentParser(description="Visual self-checks on rendered SVG metadata")
    parser.add_argument("--manifest", required=True, help="Path to render_manifest.json")
    parser.add_argument("--json", action="store_true", help="Output errors as JSON")

    args = parser.parse_args()
    manifest_path = Path(args.manifest)

    if not manifest_path.exists():
        print(f"Error: {manifest_path} not found", file=sys.stderr)
        sys.exit(1)

    manifest = load_json(manifest_path)
    errors = run_checks(manifest)

    if args.json:
        print(json.dumps(errors, indent=2))
    else:
        print("=" * 60)
        print("  Visual Self-Check")
        print("=" * 60)
        if not errors:
            print(f"  All checks passed for {len(manifest.get('entries', []))} rendered questions.")
        else:
            for e in errors:
                print(f"  [{e['q_id']}] {e['code']}: {e['detail']}")
            print("-" * 60)
            print(f"  RESULT: {len(errors)} error(s)")

    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
