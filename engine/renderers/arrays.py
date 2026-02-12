"""
Deterministic SVG renderer for ARRAYS visual model.

Supports two modes (auto-detected from parameters):
  1. Array mode: rows × cols grid of dots or squares.
  2. Equal groups mode: N groups of M items each.

All item positions are mathematically derived. No randomness.
"""

from __future__ import annotations

import html

# Canvas constants
CANVAS_W = 600
CANVAS_H = 220
PAD = 40

# Colors
BG_COLOR = "#FAFAFA"
ITEM_FILL = "#4A90D9"
ITEM_STROKE = "#2A6099"
HIGHLIGHT_FILL = "#FFD700"
HIGHLIGHT_OPACITY = 0.25
GROUP_BORDER = "#E04040"
LABEL_COLOR = "#333333"
EQUATION_COLOR = "#555555"
ROW_LABEL_COLOR = "#888888"

# Defaults
DEFAULT_CELL_SIZE = 24
DEFAULT_SHAPE = "dot"


def _detect_mode(params: dict) -> str:
    if "rows" in params and "cols" in params:
        return "array"
    if "groups" in params and "items_per_group" in params:
        return "equal_groups"
    return "array"


def _clamp_cell_size(cs: int) -> int:
    return max(18, min(36, cs))


def _svg_circle(cx, cy, r, fill=ITEM_FILL, stroke=ITEM_STROKE, sw=1):
    return f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'


def _svg_rect(x, y, w, h, fill, stroke="none", sw=0, opacity=1.0, rx=0):
    attrs = f'x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"'
    if opacity < 1.0:
        attrs += f' opacity="{opacity:.2f}"'
    if rx:
        attrs += f' rx="{rx}"'
    return f"<rect {attrs}/>"


def _svg_text(x, y, text, size=11, color=LABEL_COLOR, anchor="middle", weight="normal"):
    escaped = html.escape(str(text))
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{color}" '
        f'text-anchor="{anchor}" font-weight="{weight}" '
        f'font-family="Arial, Helvetica, sans-serif">{escaped}</text>'
    )


def _render_item(x: float, y: float, cell_size: int, shape: str) -> tuple[str, dict]:
    """Render a single item (dot or square) centered at (x, y).

    Returns (svg_element, bounding_box).
    """
    if shape == "square":
        side = cell_size * 0.5
        rx = x - side / 2
        ry = y - side / 2
        elem = _svg_rect(rx, ry, side, side, ITEM_FILL, ITEM_STROKE, 1)
        bbox = {"type": "item", "x": rx, "y": ry, "w": side, "h": side}
    else:
        r = cell_size * 0.25
        elem = _svg_circle(x, y, r)
        bbox = {"type": "item", "x": x - r, "y": y - r, "w": r * 2, "h": r * 2}
    return elem, bbox


def _render_array(params: dict) -> tuple[list[str], list[dict], list[dict], dict]:
    """Render array mode. Returns (elements, bboxes, text_boxes, extra_meta)."""
    rows = params.get("rows", 3)
    cols = params.get("cols", 4)
    cell_size = _clamp_cell_size(params.get("cell_size", DEFAULT_CELL_SIZE))
    shape = params.get("shape", DEFAULT_SHAPE)
    show_labels = params.get("show_row_col_labels", False)
    show_equation = params.get("show_equation", False)
    highlight = params.get("highlight", {})
    hl_mode = highlight.get("mode", "none")
    hl_index = highlight.get("index", 0)

    elements: list[str] = []
    bboxes: list[dict] = []
    text_boxes: list[dict] = []
    rendered_total = 0

    # Background
    elements.append(_svg_rect(0, 0, CANVAS_W, CANVAS_H, BG_COLOR))

    # Compute grid origin — center the grid horizontally
    grid_w = cols * cell_size
    grid_h = rows * cell_size
    label_offset = 24 if show_labels else 0
    origin_x = max(PAD + label_offset, (CANVAS_W - grid_w) / 2)
    origin_y = PAD + label_offset

    # Column labels (top)
    if show_labels:
        for c in range(cols):
            cx = origin_x + c * cell_size + cell_size / 2
            cy = origin_y - 10
            elements.append(_svg_text(cx, cy, str(c + 1), size=10, color=ROW_LABEL_COLOR))
            text_boxes.append({"text": str(c + 1), "x": cx - 5, "y": cy - 10, "w": 10, "h": 12})

    # Row labels (left)
    if show_labels:
        for r in range(rows):
            rx = origin_x - 14
            ry = origin_y + r * cell_size + cell_size / 2 + 4
            elements.append(_svg_text(rx, ry, str(r + 1), size=10, color=ROW_LABEL_COLOR, anchor="end"))
            text_boxes.append({"text": str(r + 1), "x": rx - 10, "y": ry - 10, "w": 14, "h": 12})

    # Highlight backgrounds (drawn before items so items appear on top)
    if hl_mode == "row" and 0 <= hl_index < rows:
        hy = origin_y + hl_index * cell_size
        elements.append(_svg_rect(origin_x - 4, hy - 2, grid_w + 8, cell_size + 4,
                                   HIGHLIGHT_FILL, opacity=HIGHLIGHT_OPACITY, rx=4))
        bboxes.append({"type": "highlight", "x": origin_x - 4, "y": hy - 2,
                        "w": grid_w + 8, "h": cell_size + 4})
    elif hl_mode == "col" and 0 <= hl_index < cols:
        hx = origin_x + hl_index * cell_size
        elements.append(_svg_rect(hx - 2, origin_y - 4, cell_size + 4, grid_h + 8,
                                   HIGHLIGHT_FILL, opacity=HIGHLIGHT_OPACITY, rx=4))
        bboxes.append({"type": "highlight", "x": hx - 2, "y": origin_y - 4,
                        "w": cell_size + 4, "h": grid_h + 8})

    # Render items
    for r in range(rows):
        for c in range(cols):
            ix = origin_x + c * cell_size + cell_size / 2
            iy = origin_y + r * cell_size + cell_size / 2
            elem, bbox = _render_item(ix, iy, cell_size, shape)
            elements.append(elem)
            bboxes.append(bbox)
            rendered_total += 1

    # Equation below grid
    if show_equation:
        total = rows * cols
        eq_text = f"{rows} \u00d7 {cols} = {total}"
        eq_y = origin_y + grid_h + 24
        elements.append(_svg_text(CANVAS_W / 2, eq_y, eq_text, size=14,
                                   color=EQUATION_COLOR, weight="bold"))
        text_boxes.append({"text": eq_text, "x": CANVAS_W / 2 - 60, "y": eq_y - 12,
                           "w": 120, "h": 16})

    extra = {"rows": rows, "cols": cols, "groups": 0, "items_per_group": 0,
             "expected_total": rows * cols, "rendered_total": rendered_total}
    return elements, bboxes, text_boxes, extra


def _render_equal_groups(params: dict) -> tuple[list[str], list[dict], list[dict], dict]:
    """Render equal groups mode. Returns (elements, bboxes, text_boxes, extra_meta)."""
    groups = params.get("groups", 3)
    items_per_group = params.get("items_per_group", 4)
    layout = params.get("layout", "rows")
    cell_size = _clamp_cell_size(params.get("cell_size", DEFAULT_CELL_SIZE))
    shape = params.get("shape", DEFAULT_SHAPE)
    highlight = params.get("highlight", {})
    hl_mode = highlight.get("mode", "none")

    elements: list[str] = []
    bboxes: list[dict] = []
    text_boxes: list[dict] = []
    rendered_total = 0

    # Background
    elements.append(_svg_rect(0, 0, CANVAS_W, CANVAS_H, BG_COLOR))

    group_gap = cell_size * 0.8
    item_total_w = items_per_group * cell_size

    if layout == "rows":
        # Each group on its own row
        origin_x = PAD + 30  # leave room for group labels
        origin_y = PAD

        for g in range(groups):
            gy = origin_y + g * (cell_size + group_gap)

            # Group label
            elements.append(_svg_text(origin_x - 16, gy + cell_size / 2 + 4,
                                       f"G{g+1}", size=10, color=ROW_LABEL_COLOR, anchor="end"))
            text_boxes.append({"text": f"G{g+1}", "x": origin_x - 30, "y": gy + cell_size / 2 - 6,
                               "w": 18, "h": 12})

            # Group outline if highlight mode=groups
            if hl_mode == "groups":
                elements.append(_svg_rect(origin_x - 4, gy - 2, item_total_w + 8,
                                           cell_size + 4, "none", GROUP_BORDER, 1.5, rx=4))
                bboxes.append({"type": "group_border", "x": origin_x - 4, "y": gy - 2,
                                "w": item_total_w + 8, "h": cell_size + 4})

            # Items in this group
            for i in range(items_per_group):
                ix = origin_x + i * cell_size + cell_size / 2
                iy = gy + cell_size / 2
                elem, bbox = _render_item(ix, iy, cell_size, shape)
                elements.append(elem)
                bboxes.append(bbox)
                rendered_total += 1
    else:
        # Grid: pack groups left-to-right, wrap if needed
        origin_x = PAD
        origin_y = PAD
        x_cursor = origin_x
        y_cursor = origin_y
        max_row_w = CANVAS_W - 2 * PAD

        for g in range(groups):
            group_w = items_per_group * cell_size + group_gap

            # Wrap to next row if needed
            if x_cursor + items_per_group * cell_size > origin_x + max_row_w and g > 0:
                x_cursor = origin_x
                y_cursor += cell_size + group_gap

            # Group outline
            if hl_mode == "groups":
                elements.append(_svg_rect(x_cursor - 2, y_cursor - 2,
                                           items_per_group * cell_size + 4, cell_size + 4,
                                           "none", GROUP_BORDER, 1.5, rx=4))
                bboxes.append({"type": "group_border", "x": x_cursor - 2, "y": y_cursor - 2,
                                "w": items_per_group * cell_size + 4, "h": cell_size + 4})

            for i in range(items_per_group):
                ix = x_cursor + i * cell_size + cell_size / 2
                iy = y_cursor + cell_size / 2
                elem, bbox = _render_item(ix, iy, cell_size, shape)
                elements.append(elem)
                bboxes.append(bbox)
                rendered_total += 1

            x_cursor += items_per_group * cell_size + group_gap

    # Equation at bottom
    total = groups * items_per_group
    eq_text = f"{groups} groups \u00d7 {items_per_group} = {total}"
    # Find the lowest rendered element
    max_y = PAD
    for bb in bboxes:
        max_y = max(max_y, bb["y"] + bb["h"])
    eq_y = max_y + 22
    elements.append(_svg_text(CANVAS_W / 2, eq_y, eq_text, size=13,
                               color=EQUATION_COLOR, weight="bold"))
    text_boxes.append({"text": eq_text, "x": CANVAS_W / 2 - 80, "y": eq_y - 12,
                       "w": 160, "h": 16})

    extra = {"rows": 0, "cols": 0, "groups": groups, "items_per_group": items_per_group,
             "expected_total": total, "rendered_total": rendered_total}
    return elements, bboxes, text_boxes, extra


def render_arrays(spec: dict, model_specs: dict) -> dict:
    """Render ARRAYS to SVG with metadata.

    Args:
        spec: The visual_spec from a question (has model_id, parameters).
        model_specs: The full visual_model_specs.json dict.

    Returns:
        {"svg": str, "width": int, "height": int, "metadata": {...}}
    """
    params = spec.get("parameters", {})
    mode = _detect_mode(params)

    if mode == "equal_groups":
        elements, bboxes, text_boxes, extra = _render_equal_groups(params)
    else:
        elements, bboxes, text_boxes, extra = _render_array(params)

    # Compute actual canvas height from content
    max_y = CANVAS_H
    for bb in bboxes:
        max_y = max(max_y, bb["y"] + bb["h"])
    for tb in text_boxes:
        max_y = max(max_y, tb["y"] + tb["h"])
    canvas_h = int(max_y + PAD)
    # Clamp to minimum
    canvas_h = max(canvas_h, CANVAS_H)

    # Patch the background rect to actual height
    elements[0] = _svg_rect(0, 0, CANVAS_W, canvas_h, BG_COLOR)

    svg_parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS_W}" height="{canvas_h}" '
        f'viewBox="0 0 {CANVAS_W} {canvas_h}">',
    ]
    svg_parts.extend(elements)
    svg_parts.append("</svg>")
    svg_str = "\n".join(svg_parts)

    metadata = {
        "model_id": "ARRAYS",
        "mode": mode,
        "expected_total": extra["expected_total"],
        "rendered_total": extra["rendered_total"],
        "rows": extra["rows"],
        "cols": extra["cols"],
        "groups": extra["groups"],
        "items_per_group": extra["items_per_group"],
        "bounding_boxes": bboxes,
        "text_boxes": text_boxes,
    }

    return {
        "svg": svg_str,
        "width": CANVAS_W,
        "height": canvas_h,
        "metadata": metadata,
    }
