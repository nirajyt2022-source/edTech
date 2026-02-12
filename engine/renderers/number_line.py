"""
Deterministic SVG renderer for NUMBER_LINE visual model.

Supports three modes (auto-detected from parameters):
  1. Rounding: integer range with highlight_value and target_value
  2. Fraction: 0-to-1 range with denominator and highlight_fraction
  3. Jump subtraction: integer range with jump_values (curved arrows)

All tick positions are mathematically derived. No randomness.
"""

from __future__ import annotations

import html
import math

# Canvas constants
CANVAS_W = 600
CANVAS_H = 140
H_PAD = 40
BASELINE_Y = 80
TICK_LEN = 10
MARKER_R = 6
TARGET_R = 8

# Colors
LINE_COLOR = "#333333"
TICK_COLOR = "#333333"
LABEL_COLOR = "#333333"
MARKER_FILL = "#E04040"
TARGET_FILL = "#4A90D9"
JUMP_COLOR = "#E04040"
HIGHLIGHT_COLOR = "#FFD700"
BG_COLOR = "#FAFAFA"

# Label sizing
LABEL_FONT_SIZE = 11
LABEL_CHAR_W = 6.6  # approximate width per char at font size 11
LABEL_H = 14


def _detect_mode(params: dict) -> str:
    if "denominator" in params or "highlight_fraction" in params:
        return "fraction"
    if "jump_values" in params:
        return "jump"
    return "rounding"


def _svg_line(x1, y1, x2, y2, color=LINE_COLOR, sw=2):
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{sw}"/>'


def _svg_circle(cx, cy, r, fill, stroke="none", sw=0):
    return f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'


def _svg_text(x, y, text, size=LABEL_FONT_SIZE, color=LABEL_COLOR, anchor="middle", weight="normal"):
    escaped = html.escape(str(text))
    return (
        f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" '
        f'text-anchor="{anchor}" font-weight="{weight}" '
        f'font-family="Arial, Helvetica, sans-serif">{escaped}</text>'
    )


def _svg_rect(x, y, w, h, fill, stroke="none", sw=0, opacity=1.0):
    attrs = f'x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"'
    if opacity < 1.0:
        attrs += f' opacity="{opacity}"'
    return f'<rect {attrs}/>'


def _svg_curved_arrow(x1, y1, x2, y2, color=JUMP_COLOR, sw=2):
    """Curved arrow arcing above the baseline."""
    arc_height = min(35, abs(x2 - x1) * 0.4)
    mid_x = (x1 + x2) / 2
    ctrl_y = y1 - arc_height
    return (
        f'<path d="M {x1:.1f} {y1:.1f} Q {mid_x:.1f} {ctrl_y:.1f} {x2:.1f} {y2:.1f}" '
        f'fill="none" stroke="{color}" stroke-width="{sw}" '
        f'marker-end="url(#nl_arrowhead)"/>'
    )


def _value_to_x(value: float, start: float, end: float) -> float:
    """Convert a numeric value to an x coordinate on the number line."""
    if end == start:
        return H_PAD
    frac = (value - start) / (end - start)
    return H_PAD + frac * (CANVAS_W - 2 * H_PAD)


def _label_width(text: str) -> float:
    return len(text) * LABEL_CHAR_W


def _render_rounding(params: dict) -> dict:
    start = params.get("start", 0)
    end = params.get("end", 100)
    step = params.get("step", 10)
    highlight_value = params.get("highlight_value")
    target_value = params.get("target_value")

    if step <= 0:
        step = 10
    total_units = (end - start) / step
    if total_units <= 0:
        total_units = 1

    elements: list[str] = []
    bboxes: list[dict] = []
    text_boxes: list[dict] = []
    rendered_points: list[float] = []

    # Background
    elements.append(_svg_rect(0, 0, CANVAS_W, CANVAS_H, BG_COLOR))

    # Arrow defs
    elements.append(
        '<defs>'
        '<marker id="nl_arrowhead" markerWidth="10" markerHeight="7" '
        'refX="10" refY="3.5" orient="auto">'
        f'<polygon points="0 0, 10 3.5, 0 7" fill="{JUMP_COLOR}"/>'
        '</marker>'
        '</defs>'
    )

    # Main line
    x_start = H_PAD
    x_end = CANVAS_W - H_PAD
    elements.append(_svg_line(x_start, BASELINE_Y, x_end, BASELINE_Y, LINE_COLOR, 2))
    bboxes.append({"type": "line", "x": x_start, "y": BASELINE_Y - 1, "w": x_end - x_start, "h": 2})

    # Arrowhead at right end
    elements.append(
        f'<polygon points="{x_end},{BASELINE_Y-4} {x_end+8},{BASELINE_Y} {x_end},{BASELINE_Y+4}" '
        f'fill="{LINE_COLOR}"/>'
    )

    # Ticks and labels
    tick_count = int(total_units) + 1
    for i in range(tick_count):
        value = start + i * step
        x = _value_to_x(value, start, end)

        # Tick
        elements.append(_svg_line(x, BASELINE_Y - TICK_LEN // 2, x, BASELINE_Y + TICK_LEN // 2, TICK_COLOR, 1.5))
        bboxes.append({"type": "tick", "x": x - 0.75, "y": BASELINE_Y - TICK_LEN // 2, "w": 1.5, "h": TICK_LEN})

        # Label
        label = str(int(value)) if value == int(value) else f"{value:.1f}"
        lw = _label_width(label)
        lx = x - lw / 2
        ly = BASELINE_Y + TICK_LEN // 2 + 4
        elements.append(_svg_text(x, ly + LABEL_FONT_SIZE, label, anchor="middle"))
        text_boxes.append({"text": label, "x": lx, "y": ly, "w": lw, "h": LABEL_H})

    # Highlight value marker (red circle)
    if highlight_value is not None:
        hx = _value_to_x(highlight_value, start, end)
        elements.append(_svg_circle(hx, BASELINE_Y, MARKER_R, MARKER_FILL))
        bboxes.append({"type": "marker", "x": hx - MARKER_R, "y": BASELINE_Y - MARKER_R, "w": MARKER_R * 2, "h": MARKER_R * 2})
        rendered_points.append(highlight_value)

        # Label above
        hl_label = str(int(highlight_value)) if highlight_value == int(highlight_value) else f"{highlight_value}"
        hlw = _label_width(hl_label)
        elements.append(_svg_text(hx, BASELINE_Y - MARKER_R - 8, hl_label, size=10, color=MARKER_FILL, weight="bold"))
        text_boxes.append({"text": hl_label, "x": hx - hlw / 2, "y": BASELINE_Y - MARKER_R - 20, "w": hlw, "h": LABEL_H})

    # Target value marker (blue diamond-ish ring)
    if target_value is not None:
        tx = _value_to_x(target_value, start, end)
        elements.append(_svg_circle(tx, BASELINE_Y, TARGET_R, "none", TARGET_FILL, 2.5))
        bboxes.append({"type": "target", "x": tx - TARGET_R, "y": BASELINE_Y - TARGET_R, "w": TARGET_R * 2, "h": TARGET_R * 2})
        rendered_points.append(target_value)

        # Label above
        tl = str(int(target_value)) if target_value == int(target_value) else f"{target_value}"
        tlw = _label_width(tl)
        elements.append(_svg_text(tx, BASELINE_Y - TARGET_R - 8, tl, size=10, color=TARGET_FILL, weight="bold"))
        text_boxes.append({"text": tl, "x": tx - tlw / 2, "y": BASELINE_Y - TARGET_R - 20, "w": tlw, "h": LABEL_H})

    expected_points = []
    if highlight_value is not None:
        expected_points.append(highlight_value)
    if target_value is not None:
        expected_points.append(target_value)

    return elements, bboxes, text_boxes, expected_points, rendered_points, tick_count


def _render_fraction(params: dict) -> dict:
    start = params.get("start", 0)
    end = params.get("end", 1)
    denominator = params.get("denominator", 4)
    highlight_fraction = params.get("highlight_fraction")

    if denominator <= 0:
        denominator = 4

    elements: list[str] = []
    bboxes: list[dict] = []
    text_boxes: list[dict] = []
    rendered_points: list[float] = []

    # Background
    elements.append(_svg_rect(0, 0, CANVAS_W, CANVAS_H, BG_COLOR))

    # Main line
    x_start = H_PAD
    x_end = CANVAS_W - H_PAD
    elements.append(_svg_line(x_start, BASELINE_Y, x_end, BASELINE_Y, LINE_COLOR, 2))
    bboxes.append({"type": "line", "x": x_start, "y": BASELINE_Y - 1, "w": x_end - x_start, "h": 2})

    # Ticks: one per 1/denominator
    tick_count = denominator + 1
    for i in range(tick_count):
        value = start + i * (end - start) / denominator
        x = _value_to_x(value, start, end)

        # Tick — endpoints get longer ticks
        tlen = TICK_LEN + 4 if (i == 0 or i == denominator) else TICK_LEN
        elements.append(_svg_line(x, BASELINE_Y - tlen // 2, x, BASELINE_Y + tlen // 2, TICK_COLOR, 1.5))
        bboxes.append({"type": "tick", "x": x - 0.75, "y": BASELINE_Y - tlen // 2, "w": 1.5, "h": tlen})

        # Labels: only for 0 and 1 (endpoints) — intermediates unlabeled
        if i == 0:
            label = "0"
        elif i == denominator:
            label = "1"
        else:
            label = ""

        if label:
            lw = _label_width(label)
            lx = x - lw / 2
            ly = BASELINE_Y + tlen // 2 + 4
            elements.append(_svg_text(x, ly + LABEL_FONT_SIZE, label, anchor="middle"))
            text_boxes.append({"text": label, "x": lx, "y": ly, "w": lw, "h": LABEL_H})

    # Highlight fraction marker
    if highlight_fraction:
        num = highlight_fraction.get("num", 0)
        den = highlight_fraction.get("den", denominator)
        if den <= 0:
            den = denominator
        frac_val = num / den
        hx = _value_to_x(start + frac_val * (end - start), start, end)

        elements.append(_svg_circle(hx, BASELINE_Y, MARKER_R, MARKER_FILL))
        bboxes.append({"type": "marker", "x": hx - MARKER_R, "y": BASELINE_Y - MARKER_R, "w": MARKER_R * 2, "h": MARKER_R * 2})
        rendered_points.append(round(frac_val, 6))

        # Label above: show as fraction
        fl = f"{num}/{den}"
        flw = _label_width(fl)
        elements.append(_svg_text(hx, BASELINE_Y - MARKER_R - 8, fl, size=11, color=MARKER_FILL, weight="bold"))
        text_boxes.append({"text": fl, "x": hx - flw / 2, "y": BASELINE_Y - MARKER_R - 20, "w": flw, "h": LABEL_H})

    expected_points = []
    if highlight_fraction:
        num = highlight_fraction.get("num", 0)
        den = highlight_fraction.get("den", denominator)
        expected_points.append(round(num / den, 6))

    return elements, bboxes, text_boxes, expected_points, rendered_points, tick_count


def _render_jump(params: dict) -> dict:
    start = params.get("start", 0)
    end = params.get("end", 100)
    jump_values = params.get("jump_values", [])
    step = params.get("step")

    # Auto-detect step if not provided
    if step is None:
        if jump_values:
            step = min(jump_values) if min(jump_values) > 0 else 10
        else:
            step = max(1, (end - start) // 10)

    if step <= 0:
        step = 10

    elements: list[str] = []
    bboxes: list[dict] = []
    text_boxes: list[dict] = []
    rendered_points: list[float] = []

    # Background
    elements.append(_svg_rect(0, 0, CANVAS_W, CANVAS_H, BG_COLOR))

    # Arrow defs
    elements.append(
        '<defs>'
        '<marker id="nl_arrowhead" markerWidth="10" markerHeight="7" '
        'refX="10" refY="3.5" orient="auto">'
        f'<polygon points="0 0, 10 3.5, 0 7" fill="{JUMP_COLOR}"/>'
        '</marker>'
        '</defs>'
    )

    # Main line
    x_start_line = H_PAD
    x_end_line = CANVAS_W - H_PAD
    elements.append(_svg_line(x_start_line, BASELINE_Y, x_end_line, BASELINE_Y, LINE_COLOR, 2))
    bboxes.append({"type": "line", "x": x_start_line, "y": BASELINE_Y - 1, "w": x_end_line - x_start_line, "h": 2})

    # Ticks
    total_units = (end - start) / step
    tick_count = int(total_units) + 1
    for i in range(tick_count):
        value = start + i * step
        x = _value_to_x(value, start, end)

        elements.append(_svg_line(x, BASELINE_Y - TICK_LEN // 2, x, BASELINE_Y + TICK_LEN // 2, TICK_COLOR, 1.5))
        bboxes.append({"type": "tick", "x": x - 0.75, "y": BASELINE_Y - TICK_LEN // 2, "w": 1.5, "h": TICK_LEN})

        label = str(int(value)) if value == int(value) else f"{value:.1f}"
        lw = _label_width(label)
        lx = x - lw / 2
        ly = BASELINE_Y + TICK_LEN // 2 + 4
        elements.append(_svg_text(x, ly + LABEL_FONT_SIZE, label, anchor="middle"))
        text_boxes.append({"text": label, "x": lx, "y": ly, "w": lw, "h": LABEL_H})

    # Jump arrows
    current = end  # jumps typically start from the end going left (subtraction)
    rendered_points.append(current)
    for jv in jump_values:
        next_val = current - jv
        x1 = _value_to_x(current, start, end)
        x2 = _value_to_x(next_val, start, end)

        elements.append(_svg_curved_arrow(x1, BASELINE_Y, x2, BASELINE_Y, JUMP_COLOR, 2))
        bboxes.append({"type": "jump_arrow", "x": min(x1, x2), "y": BASELINE_Y - 40, "w": abs(x2 - x1), "h": 40})

        # Label above arc
        mid_x = (x1 + x2) / 2
        jl = f"-{jv}"
        jlw = _label_width(jl)
        elements.append(_svg_text(mid_x, BASELINE_Y - 38, jl, size=10, color=JUMP_COLOR, weight="bold"))
        text_boxes.append({"text": jl, "x": mid_x - jlw / 2, "y": BASELINE_Y - 50, "w": jlw, "h": LABEL_H})

        # Dot at landing point
        elements.append(_svg_circle(x2, BASELINE_Y, 4, JUMP_COLOR))
        bboxes.append({"type": "marker", "x": x2 - 4, "y": BASELINE_Y - 4, "w": 8, "h": 8})

        rendered_points.append(next_val)
        current = next_val

    expected_points = list(rendered_points)

    return elements, bboxes, text_boxes, expected_points, rendered_points, tick_count


def render_number_line(spec: dict, model_specs: dict) -> dict:
    """Render NUMBER_LINE to SVG with metadata.

    Args:
        spec: The visual_spec from a question (has model_id, parameters).
        model_specs: The full visual_model_specs.json dict.

    Returns:
        {"svg": str, "width": int, "height": int, "metadata": {...}}
    """
    params = spec.get("parameters", {})
    mode = _detect_mode(params)

    if mode == "fraction":
        elements, bboxes, text_boxes, expected_points, rendered_points, tick_count = _render_fraction(params)
    elif mode == "jump":
        elements, bboxes, text_boxes, expected_points, rendered_points, tick_count = _render_jump(params)
    else:
        elements, bboxes, text_boxes, expected_points, rendered_points, tick_count = _render_rounding(params)

    # Build SVG
    svg_parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS_W}" height="{CANVAS_H}" '
        f'viewBox="0 0 {CANVAS_W} {CANVAS_H}">',
    ]
    svg_parts.extend(elements)
    svg_parts.append("</svg>")
    svg_str = "\n".join(svg_parts)

    metadata = {
        "model_id": "NUMBER_LINE",
        "mode": mode,
        "expected_points": expected_points,
        "rendered_points": rendered_points,
        "tick_count": tick_count,
        "bounding_boxes": bboxes,
        "text_boxes": text_boxes,
    }

    return {
        "svg": svg_str,
        "width": CANVAS_W,
        "height": CANVAS_H,
        "metadata": metadata,
    }
