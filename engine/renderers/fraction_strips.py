"""
Deterministic SVG renderer for FRACTION_STRIPS and FRACTION_SHAPES visual models.

FRACTION_STRIPS: Horizontal bar strips divided into equal parts, with some shaded.
FRACTION_SHAPES: Circles/rectangles/squares divided into equal sectors/parts, with some shaded.

All positions are mathematically derived. No randomness.
"""

from __future__ import annotations

import html
import math

# ─── Shared constants ────────────────────────────────────────────────
CANVAS_W = 600
PAD_X = 40
START_Y = 40
BG_COLOR = "#FAFAFA"
STRIP_FILL = "#FFFFFF"
SHADED_FILL = "#4A90D9"
OUTLINE_HIGHLIGHT = "#E04040"
PARTITION_COLOR = "#999999"
BORDER_COLOR = "#333333"
LABEL_COLOR = "#333333"
LABEL_FONT = 12

# ─── SVG helpers ─────────────────────────────────────────────────────

def _esc(text: str) -> str:
    return html.escape(str(text))


def _rect(x, y, w, h, fill, stroke="none", sw=0, opacity=1.0):
    a = f'x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"'
    if opacity < 1.0:
        a += f' opacity="{opacity:.2f}"'
    return f"<rect {a}/>"


def _line(x1, y1, x2, y2, color=PARTITION_COLOR, sw=1):
    return f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" stroke-width="{sw}"/>'


def _text(x, y, txt, size=LABEL_FONT, color=LABEL_COLOR, anchor="middle", weight="normal"):
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{color}" '
        f'text-anchor="{anchor}" font-weight="{weight}" '
        f'font-family="Arial, Helvetica, sans-serif">{_esc(txt)}</text>'
    )


def _circle(cx, cy, r, fill="none", stroke="none", sw=1):
    return f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'


def _arc_path(cx, cy, r, start_angle, end_angle, fill, stroke="none", sw=1):
    """SVG arc sector (pie slice) from start_angle to end_angle (radians, 0=top, CW)."""
    # Convert to SVG coordinates (0=right, CCW in math but SVG y is flipped so CW)
    sa = start_angle - math.pi / 2
    ea = end_angle - math.pi / 2

    x1 = cx + r * math.cos(sa)
    y1 = cy + r * math.sin(sa)
    x2 = cx + r * math.cos(ea)
    y2 = cy + r * math.sin(ea)

    large = 1 if (end_angle - start_angle) > math.pi else 0

    d = f"M {cx:.1f} {cy:.1f} L {x1:.1f} {y1:.1f} A {r:.1f} {r:.1f} 0 {large} 1 {x2:.1f} {y2:.1f} Z"
    return f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'


# ═════════════════════════════════════════════════════════════════════
#  FRACTION_STRIPS
# ═════════════════════════════════════════════════════════════════════

def render_fraction_strips(spec: dict, model_specs: dict) -> dict:
    """Render FRACTION_STRIPS to SVG with metadata."""
    params = spec.get("parameters", {})

    whole_count = params.get("whole_count", 1)
    denominator = params.get("denominator", 4)
    numerators = params.get("numerators", [0] * whole_count)
    label_mode = params.get("label_mode", "fraction")
    show_lines = params.get("show_partition_lines", True)
    hl_style = params.get("highlight_style", "fill")
    strip_w = params.get("strip_width", 480)
    strip_h = params.get("strip_height", 32)
    gap_y = params.get("gap_y", 18)

    # Clamp strip dimensions
    strip_w = max(200, min(strip_w, CANVAS_W - 2 * PAD_X))
    strip_h = max(20, min(strip_h, 50))

    # Validate
    if len(numerators) != whole_count:
        raise ValueError(
            f"numerators length ({len(numerators)}) != whole_count ({whole_count})"
        )
    for i, n in enumerate(numerators):
        if n < 0 or n > denominator:
            raise ValueError(
                f"numerators[{i}]={n} out of range [0, {denominator}]"
            )

    label_row_h = 20 if label_mode != "none" else 0
    canvas_h = START_Y + whole_count * (strip_h + gap_y + label_row_h) + 30

    elements: list[str] = []
    bboxes: list[dict] = []
    text_boxes: list[dict] = []
    highlighted_total = 0

    elements.append(_rect(0, 0, CANVAS_W, canvas_h, BG_COLOR))

    origin_x = (CANVAS_W - strip_w) / 2
    part_w = strip_w / denominator
    y = START_Y

    for si in range(whole_count):
        num = numerators[si]

        # Outer border
        elements.append(_rect(origin_x, y, strip_w, strip_h, STRIP_FILL, BORDER_COLOR, 1.5))
        bboxes.append({"type": "strip_border", "x": origin_x, "y": y, "w": strip_w, "h": strip_h})

        # Highlighted parts
        for p in range(num):
            px = origin_x + p * part_w
            if hl_style == "fill":
                elements.append(_rect(px, y, part_w, strip_h, SHADED_FILL, BORDER_COLOR, 0.5))
            else:
                elements.append(_rect(px, y, part_w, strip_h, "none", OUTLINE_HIGHLIGHT, 2.5))
            bboxes.append({"type": "highlighted_part", "x": px, "y": y, "w": part_w, "h": strip_h})
            highlighted_total += 1

        # Partition lines
        if show_lines:
            for p in range(1, denominator):
                lx = origin_x + p * part_w
                elements.append(_line(lx, y, lx, y + strip_h, PARTITION_COLOR, 1))

        # Label
        if label_mode != "none":
            label_y = y + strip_h + 14
            if label_mode == "mixed" and num == denominator:
                lbl = "1"
            else:
                lbl = f"{num}/{denominator}"
            lw = len(lbl) * 7.5
            lx = origin_x + strip_w / 2
            elements.append(_text(lx, label_y, lbl, size=LABEL_FONT, weight="bold"))
            text_boxes.append({"text": lbl, "x": lx - lw / 2, "y": label_y - 12, "w": lw, "h": 14})

        y += strip_h + gap_y + label_row_h

    parts_total = whole_count * denominator

    metadata = {
        "model_id": "FRACTION_STRIPS",
        "expected": {
            "whole_count": whole_count,
            "denominator": denominator,
            "numerators": list(numerators),
            "highlighted_parts_total": sum(numerators),
        },
        "rendered": {
            "parts_total": parts_total,
            "highlighted_parts_total": highlighted_total,
        },
        "bounding_boxes": bboxes,
        "text_boxes": text_boxes,
    }

    svg_parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS_W}" height="{int(canvas_h)}" '
        f'viewBox="0 0 {CANVAS_W} {int(canvas_h)}">',
    ]
    svg_parts.extend(elements)
    svg_parts.append("</svg>")

    return {
        "svg": "\n".join(svg_parts),
        "width": CANVAS_W,
        "height": int(canvas_h),
        "metadata": metadata,
    }


# ═════════════════════════════════════════════════════════════════════
#  FRACTION_SHAPES
# ═════════════════════════════════════════════════════════════════════

def render_fraction_shapes(spec: dict, model_specs: dict) -> dict:
    """Render FRACTION_SHAPES to SVG with metadata.

    Parameters schema:
    {
      "shape": "circle" | "rectangle" | "square",
      "shape_count": int,           # how many shapes to draw (1-3)
      "denominator": int,
      "numerators": [int, ...],     # one per shape
      "shape_size": int,            # px, 80-120
      "label_mode": "none" | "fraction" | "mixed"
    }
    """
    params = spec.get("parameters", {})

    shape_type = params.get("shape", "circle")
    shape_count = params.get("shape_count", 1)
    denominator = params.get("denominator", 4)
    numerators = params.get("numerators", [0] * shape_count)
    shape_size = max(60, min(140, params.get("shape_size", 100)))
    label_mode = params.get("label_mode", "fraction")

    if len(numerators) != shape_count:
        raise ValueError(
            f"numerators length ({len(numerators)}) != shape_count ({shape_count})"
        )
    for i, n in enumerate(numerators):
        if n < 0 or n > denominator:
            raise ValueError(f"numerators[{i}]={n} out of range [0, {denominator}]")

    gap_x = 30
    total_shapes_w = shape_count * shape_size + (shape_count - 1) * gap_x
    origin_x = (CANVAS_W - total_shapes_w) / 2
    label_row_h = 22 if label_mode != "none" else 0
    canvas_h = START_Y + shape_size + label_row_h + 30

    elements: list[str] = []
    bboxes: list[dict] = []
    text_boxes: list[dict] = []
    highlighted_total = 0
    parts_total = 0

    elements.append(_rect(0, 0, CANVAS_W, canvas_h, BG_COLOR))

    for si in range(shape_count):
        cx = origin_x + si * (shape_size + gap_x) + shape_size / 2
        cy = START_Y + shape_size / 2
        num = numerators[si]

        if shape_type == "circle":
            r = shape_size / 2
            # Draw full circle outline
            elements.append(_circle(cx, cy, r, "none", BORDER_COLOR, 1.5))
            bboxes.append({"type": "shape_border", "x": cx - r, "y": cy - r, "w": shape_size, "h": shape_size})

            # Draw sectors
            for p in range(denominator):
                sa = 2 * math.pi * p / denominator
                ea = 2 * math.pi * (p + 1) / denominator
                fill = SHADED_FILL if p < num else STRIP_FILL
                elements.append(_arc_path(cx, cy, r, sa, ea, fill, PARTITION_COLOR, 0.8))
                if p < num:
                    highlighted_total += 1
                parts_total += 1

            # Re-draw outline on top for crispness
            elements.append(_circle(cx, cy, r, "none", BORDER_COLOR, 1.5))

        elif shape_type in ("rectangle", "square"):
            half = shape_size / 2
            sx = cx - half
            sy = cy - half
            w = shape_size
            h = shape_size if shape_type == "square" else shape_size * 0.6
            if shape_type == "rectangle":
                sy = cy - h / 2

            # Outer border
            elements.append(_rect(sx, sy, w, h, STRIP_FILL, BORDER_COLOR, 1.5))
            bboxes.append({"type": "shape_border", "x": sx, "y": sy, "w": w, "h": h})

            # Parts — divide horizontally
            pw = w / denominator
            for p in range(denominator):
                px = sx + p * pw
                fill = SHADED_FILL if p < num else STRIP_FILL
                elements.append(_rect(px, sy, pw, h, fill, PARTITION_COLOR, 0.5))
                if p < num:
                    highlighted_total += 1
                parts_total += 1

            # Re-draw border
            elements.append(_rect(sx, sy, w, h, "none", BORDER_COLOR, 1.5))

        # Label
        if label_mode != "none":
            label_y = START_Y + shape_size + 16
            if label_mode == "mixed" and num == denominator:
                lbl = "1"
            else:
                lbl = f"{num}/{denominator}"
            lw = len(lbl) * 7.5
            elements.append(_text(cx, label_y, lbl, size=LABEL_FONT, weight="bold"))
            text_boxes.append({"text": lbl, "x": cx - lw / 2, "y": label_y - 12, "w": lw, "h": 14})

    metadata = {
        "model_id": "FRACTION_SHAPES",
        "expected": {
            "shape_count": shape_count,
            "denominator": denominator,
            "numerators": list(numerators),
            "highlighted_parts_total": sum(numerators),
        },
        "rendered": {
            "parts_total": parts_total,
            "highlighted_parts_total": highlighted_total,
        },
        "bounding_boxes": bboxes,
        "text_boxes": text_boxes,
    }

    svg_parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS_W}" height="{int(canvas_h)}" '
        f'viewBox="0 0 {CANVAS_W} {int(canvas_h)}">',
    ]
    svg_parts.extend(elements)
    svg_parts.append("</svg>")

    return {
        "svg": "\n".join(svg_parts),
        "width": CANVAS_W,
        "height": int(canvas_h),
        "metadata": metadata,
    }
