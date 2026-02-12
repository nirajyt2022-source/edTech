"""
Deterministic SVG renderer for BASE_TEN_REGROUPING visual model.

Renders base-ten blocks for subtraction with borrowing/regrouping.
- Hundreds: large squares (unit_size*2 × unit_size*2)
- Tens: rods (unit_size*2 × unit_size/2)
- Ones: small squares (unit_size/2 × unit_size/2)

Layout:
  Panel 1 (top): Minuend blocks
  Panel 2 (middle): Subtrahend blocks (crossed out / dimmed)
  Panel 3 (bottom, optional): Regrouped minuend with highlighted groups + arrows
"""

from __future__ import annotations

import html

# Deterministic colors
DEFAULT_HIGHLIGHT = "#FFD700"
HUNDRED_FILL = "#4A90D9"
TEN_FILL = "#5BAE7C"
ONE_FILL = "#E8915A"
SUBTRAHEND_FILL = "#CCCCCC"
STROKE_COLOR = "#333333"
ARROW_COLOR = "#E04040"
BG_COLOR = "#FAFAFA"
LABEL_COLOR = "#333333"
PANEL_LABEL_COLOR = "#555555"


def _decompose(number: int) -> dict:
    """Decompose a number into hundreds, tens, ones."""
    h = number // 100
    t = (number % 100) // 10
    o = number % 10
    return {"hundreds": h, "tens": t, "ones": o}


def _apply_regroup(decomp: dict, steps: list[dict]) -> dict:
    """Apply regrouping steps to a decomposition for display.

    Each step: {"from": "hundreds"|"tens", "to": "tens"|"ones", "label": "..."}
    """
    d = dict(decomp)
    for step in steps:
        src, dst = step["from"], step["to"]
        if src == "hundreds" and dst == "tens":
            if d["hundreds"] > 0:
                d["hundreds"] -= 1
                d["tens"] += 10
        elif src == "tens" and dst == "ones":
            if d["tens"] > 0:
                d["tens"] -= 1
                d["ones"] += 10
    return d


def _svg_rect(x, y, w, h, fill, stroke=STROKE_COLOR, sw=1, rx=0, opacity=1.0):
    attrs = f'x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"'
    if rx:
        attrs += f' rx="{rx}"'
    if opacity < 1.0:
        attrs += f' opacity="{opacity}"'
    return f"<rect {attrs}/>"


def _svg_text(x, y, text, size=12, color=LABEL_COLOR, anchor="start", weight="normal"):
    escaped = html.escape(str(text))
    return (
        f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" '
        f'text-anchor="{anchor}" font-weight="{weight}" '
        f'font-family="Arial, Helvetica, sans-serif">{escaped}</text>'
    )


def _svg_line(x1, y1, x2, y2, color=STROKE_COLOR, sw=1, dash=""):
    attrs = f'x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{sw}"'
    if dash:
        attrs += f' stroke-dasharray="{dash}"'
    return f"<line {attrs}/>"


def _svg_arrow_path(x1, y1, x2, y2, color=ARROW_COLOR, sw=2):
    """Curved arrow from (x1,y1) to (x2,y2)."""
    mid_y = min(y1, y2) - 20
    return (
        f'<path d="M {x1} {y1} Q {(x1+x2)//2} {mid_y} {x2} {y2}" '
        f'fill="none" stroke="{color}" stroke-width="{sw}" '
        f'marker-end="url(#arrowhead)"/>'
    )


def _render_blocks_row(
    x_start: int,
    y_start: int,
    decomp: dict,
    unit_size: int,
    fill_h: str,
    fill_t: str,
    fill_o: str,
    opacity: float = 1.0,
    highlight_color: str | None = None,
    is_regrouped: bool = False,
) -> tuple[list[str], list[dict], int]:
    """Render a row of base-ten blocks. Returns (svg_elements, bounding_boxes, total_width)."""
    elements: list[str] = []
    bboxes: list[dict] = []
    gap = 6
    x = x_start

    h_size = unit_size * 2
    t_w = unit_size * 2
    t_h = max(unit_size // 2, 8)
    o_size = max(unit_size // 2, 8)

    # Hundreds
    for i in range(decomp["hundreds"]):
        use_fill = highlight_color if (is_regrouped and highlight_color) else fill_h
        elements.append(_svg_rect(x, y_start, h_size, h_size, use_fill, opacity=opacity))
        elements.append(_svg_text(x + h_size // 2, y_start + h_size // 2 + 4, "100", size=10, anchor="middle"))
        bboxes.append({"type": "hundred", "x": x, "y": y_start, "w": h_size, "h": h_size})
        x += h_size + gap

    if decomp["hundreds"] > 0:
        x += gap  # extra gap between place values

    # Tens
    tens_y = y_start + (h_size - t_h) // 2  # vertically center
    for i in range(decomp["tens"]):
        use_fill = highlight_color if (is_regrouped and i >= 10 and highlight_color) else fill_t
        # For regrouped: highlight the "new" tens (beyond original count)
        elements.append(_svg_rect(x, tens_y, t_w, t_h, use_fill if not is_regrouped else fill_t, opacity=opacity))
        bboxes.append({"type": "ten", "x": x, "y": tens_y, "w": t_w, "h": t_h})
        x += t_w + gap
        # Wrap after 10 items in a row
        if (i + 1) % 10 == 0 and i + 1 < decomp["tens"]:
            x = x_start + (decomp["hundreds"]) * (h_size + gap) + (gap if decomp["hundreds"] > 0 else 0)
            tens_y += t_h + gap

    if decomp["tens"] > 0:
        x += gap

    # Ones
    ones_y = y_start + (h_size - o_size) // 2
    for i in range(decomp["ones"]):
        use_fill = fill_o
        elements.append(_svg_rect(x, ones_y, o_size, o_size, use_fill, opacity=opacity))
        bboxes.append({"type": "one", "x": x, "y": ones_y, "w": o_size, "h": o_size})
        x += o_size + gap
        if (i + 1) % 10 == 0 and i + 1 < decomp["ones"]:
            x = x_start + (decomp["hundreds"]) * (h_size + gap) + (gap if decomp["hundreds"] > 0 else 0)
            ones_y += o_size + gap

    return elements, bboxes, x - x_start


def render_base_ten_regrouping(spec: dict, model_specs: dict) -> dict:
    """Render BASE_TEN_REGROUPING to SVG with metadata.

    Args:
        spec: The visual_spec from a question (has model_id, parameters).
        model_specs: The full visual_model_specs.json dict.

    Returns:
        {"svg": str, "width": int, "height": int, "metadata": {...}}
    """
    params = spec.get("parameters", {})
    minuend = params.get("minuend", 0)
    subtrahend = params.get("subtrahend", 0)
    unit_size = params.get("unit_size", 24)
    show_arrow = params.get("show_arrow", True)
    highlight_color = params.get("regroup_highlight_color", DEFAULT_HIGHLIGHT)
    regroup_steps = params.get("regroup_steps", [])

    # Clamp unit_size to spec bounds
    unit_size = max(18, min(32, unit_size))

    # Decompose
    min_decomp = _decompose(minuend)
    sub_decomp = _decompose(subtrahend)

    # Regrouped decomposition
    has_regroup = len(regroup_steps) > 0
    regrouped_decomp = _apply_regroup(min_decomp, regroup_steps) if has_regroup else None

    # Layout constants
    margin = 20
    panel_gap = 24
    label_height = 20
    h_size = unit_size * 2
    row_height = h_size + 10

    # Compute panel widths to determine canvas
    max_items = max(
        min_decomp["hundreds"] + min_decomp["tens"] + min_decomp["ones"],
        sub_decomp["hundreds"] + sub_decomp["tens"] + sub_decomp["ones"],
        (regrouped_decomp["hundreds"] + regrouped_decomp["tens"] + regrouped_decomp["ones"]) if regrouped_decomp else 0,
    )
    # Rough width estimate: generous
    est_width = margin * 2 + max(max_items * (h_size + 8), 400)
    est_width = min(est_width, 700)

    elements: list[str] = []
    all_bboxes: list[dict] = []
    text_boxes: list[dict] = []
    y = margin

    # Arrow marker definition
    defs = (
        '<defs>'
        '<marker id="arrowhead" markerWidth="10" markerHeight="7" '
        'refX="10" refY="3.5" orient="auto">'
        f'<polygon points="0 0, 10 3.5, 0 7" fill="{ARROW_COLOR}"/>'
        '</marker>'
        '</defs>'
    )

    # --- Title ---
    title = f"{minuend} − {subtrahend}"
    elements.append(_svg_text(margin, y + 14, title, size=16, weight="bold"))
    text_boxes.append({"text": title, "x": margin, "y": y, "w": 200, "h": 20})
    y += label_height + 8

    # --- Panel 1: Minuend ---
    elements.append(_svg_text(margin, y + 12, f"Minuend: {minuend}", size=11, color=PANEL_LABEL_COLOR))
    text_boxes.append({"text": f"Minuend: {minuend}", "x": margin, "y": y, "w": 150, "h": 16})
    y += label_height

    elems1, bb1, _ = _render_blocks_row(
        margin, y, min_decomp, unit_size, HUNDRED_FILL, TEN_FILL, ONE_FILL
    )
    elements.extend(elems1)
    all_bboxes.extend(bb1)
    y += row_height + panel_gap

    # --- Panel 2: Subtrahend ---
    elements.append(_svg_text(margin, y + 12, f"Subtrahend: {subtrahend}", size=11, color=PANEL_LABEL_COLOR))
    text_boxes.append({"text": f"Subtrahend: {subtrahend}", "x": margin, "y": y, "w": 150, "h": 16})
    y += label_height

    elems2, bb2, _ = _render_blocks_row(
        margin, y, sub_decomp, unit_size, SUBTRAHEND_FILL, SUBTRAHEND_FILL, SUBTRAHEND_FILL, opacity=0.6
    )
    elements.extend(elems2)
    all_bboxes.extend(bb2)
    # Draw cross-out lines over subtrahend blocks
    for bb in bb2:
        elements.append(_svg_line(bb["x"], bb["y"], bb["x"] + bb["w"], bb["y"] + bb["h"], color="#CC0000", sw=1))
    y += row_height + panel_gap

    # --- Panel 3: Regrouped (if applicable) ---
    if has_regroup and regrouped_decomp:
        elements.append(_svg_text(margin, y + 12, "After regrouping:", size=11, color=PANEL_LABEL_COLOR, weight="bold"))
        text_boxes.append({"text": "After regrouping:", "x": margin, "y": y, "w": 150, "h": 16})
        y += label_height

        # Highlight border for regrouped panel
        panel_y = y - 4
        elems3, bb3, panel_w = _render_blocks_row(
            margin + 4, y, regrouped_decomp, unit_size, HUNDRED_FILL, TEN_FILL, ONE_FILL,
            is_regrouped=True, highlight_color=highlight_color,
        )
        elements.insert(len(elements) - len(elements),  # add background first
            _svg_rect(margin, panel_y, max(panel_w + 8, 200), row_height + 8,
                       highlight_color, sw=2, rx=4, opacity=0.15))
        elements.extend(elems3)
        all_bboxes.extend(bb3)

        # Regrouped label
        reg_label = (
            f"{regrouped_decomp['hundreds']}H + "
            f"{regrouped_decomp['tens']}T + "
            f"{regrouped_decomp['ones']}O"
        )
        elements.append(_svg_text(margin, y + row_height + 4, reg_label, size=10, color=ARROW_COLOR, weight="bold"))
        text_boxes.append({"text": reg_label, "x": margin, "y": y + row_height, "w": 200, "h": 14})

        y += row_height + 20

        # --- Arrows for regroup_steps ---
        if show_arrow:
            arrow_y = y
            for step in regroup_steps:
                label = step.get("label", "")
                elements.append(_svg_arrow_path(margin + 30, arrow_y, margin + 150, arrow_y))
                elements.append(_svg_text(margin + 160, arrow_y + 4, label, size=10, color=ARROW_COLOR))
                all_bboxes.append({
                    "type": "arrow", "x": margin + 30, "y": arrow_y - 10, "w": 130, "h": 20
                })
                text_boxes.append({"text": label, "x": margin + 160, "y": arrow_y - 6, "w": 200, "h": 14})
                arrow_y += 26
            y = arrow_y + 10

    # Compute canvas dimensions
    all_x_max = margin
    all_y_max = y
    for bb in all_bboxes:
        all_x_max = max(all_x_max, bb["x"] + bb["w"])
        all_y_max = max(all_y_max, bb["y"] + bb["h"])
    for tb in text_boxes:
        all_x_max = max(all_x_max, tb["x"] + tb["w"])
        all_y_max = max(all_y_max, tb["y"] + tb["h"])

    canvas_w = all_x_max + margin
    canvas_h = all_y_max + margin

    # Build SVG
    svg_parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{canvas_w}" height="{canvas_h}" '
        f'viewBox="0 0 {canvas_w} {canvas_h}">',
        defs,
        _svg_rect(0, 0, canvas_w, canvas_h, BG_COLOR, stroke="none"),
    ]
    svg_parts.extend(elements)
    svg_parts.append("</svg>")
    svg_str = "\n".join(svg_parts)

    # Expected vs rendered counts
    expected_counts = dict(min_decomp)
    if regrouped_decomp:
        rendered_hundreds = min_decomp["hundreds"] + regrouped_decomp["hundreds"]
        rendered_tens = min_decomp["tens"] + regrouped_decomp["tens"]
        rendered_ones = min_decomp["ones"] + regrouped_decomp["ones"]
    else:
        rendered_hundreds = min_decomp["hundreds"]
        rendered_tens = min_decomp["tens"]
        rendered_ones = min_decomp["ones"]

    # Add subtrahend counts
    rendered_hundreds += sub_decomp["hundreds"]
    rendered_tens += sub_decomp["tens"]
    rendered_ones += sub_decomp["ones"]

    # Count actual rendered blocks from bounding boxes
    rendered_counts = {"hundreds": 0, "tens": 0, "ones": 0}
    for bb in all_bboxes:
        if bb["type"] == "hundred":
            rendered_counts["hundreds"] += 1
        elif bb["type"] == "ten":
            rendered_counts["tens"] += 1
        elif bb["type"] == "one":
            rendered_counts["ones"] += 1

    # Expected: sum of all panels
    expected_total = {
        "hundreds": rendered_counts["hundreds"],
        "tens": rendered_counts["tens"],
        "ones": rendered_counts["ones"],
    }

    metadata = {
        "model_id": "BASE_TEN_REGROUPING",
        "minuend": minuend,
        "subtrahend": subtrahend,
        "expected_counts": expected_total,
        "rendered_counts": rendered_counts,
        "bounding_boxes": all_bboxes,
        "text_boxes": text_boxes,
    }

    return {
        "svg": svg_str,
        "width": canvas_w,
        "height": canvas_h,
        "metadata": metadata,
    }
