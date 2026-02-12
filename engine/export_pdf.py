#!/usr/bin/env python3
"""
PDF Worksheet Exporter.

Generates a formatted PDF worksheet from output.json and rendered SVG artifacts.
Uses reportlab for PDF generation. SVGs are rendered as native reportlab shapes
(no external SVG rasterizer needed).

Usage:
    python engine/export_pdf.py --output-json output.json \\
        --render-manifest artifacts/demo/render_manifest.json \\
        --out worksheet.pdf --include-answers
"""

import argparse
import json
import re
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdf_canvas


PAGE_W, PAGE_H = A4
MARGIN = 20 * mm
CONTENT_W = PAGE_W - 2 * MARGIN
HEADER_FONT = "Helvetica-Bold"
BODY_FONT = "Helvetica"
FONT_SIZE_TITLE = 16
FONT_SIZE_SUBTITLE = 11
FONT_SIZE_BODY = 11
FONT_SIZE_OPTION = 10
FONT_SIZE_SMALL = 9
LINE_HEIGHT = 14
SVG_SCALE = 0.65  # scale SVG drawings to fit page


def load_json(path: str | Path) -> dict:
    with open(path) as f:
        return json.load(f)


def _parse_svg_rects(svg_text: str) -> list[dict]:
    """Extract rect elements from SVG for reportlab drawing."""
    rects = []
    for m in re.finditer(
        r'<rect\s+([^>]+)/>', svg_text
    ):
        attrs = m.group(1)

        def attr(name):
            match = re.search(rf'{name}="([^"]*)"', attrs)
            return match.group(1) if match else None

        try:
            rects.append({
                "x": float(attr("x") or 0),
                "y": float(attr("y") or 0),
                "w": float(attr("width") or 0),
                "h": float(attr("height") or 0),
                "fill": attr("fill") or "#CCCCCC",
                "stroke": attr("stroke") or "#333333",
                "opacity": float(attr("opacity") or 1.0),
            })
        except (ValueError, TypeError):
            continue
    return rects


def _parse_svg_texts(svg_text: str) -> list[dict]:
    """Extract text elements from SVG."""
    texts = []
    for m in re.finditer(
        r'<text\s+([^>]*)>([^<]*)</text>', svg_text
    ):
        attrs_str = m.group(1)
        content = m.group(2)

        def attr(name):
            match = re.search(rf'{name}="([^"]*)"', attrs_str)
            return match.group(1) if match else None

        try:
            texts.append({
                "x": float(attr("x") or 0),
                "y": float(attr("y") or 0),
                "text": content,
                "size": float(attr("font-size") or 10),
                "fill": attr("fill") or "#333333",
                "anchor": attr("text-anchor") or "start",
            })
        except (ValueError, TypeError):
            continue
    return texts


def _parse_svg_lines(svg_text: str) -> list[dict]:
    """Extract line elements from SVG."""
    lines = []
    for m in re.finditer(r'<line\s+([^>]+)/>', svg_text):
        attrs_str = m.group(1)

        def attr(name):
            match = re.search(rf'{name}="([^"]*)"', attrs_str)
            return match.group(1) if match else None

        try:
            lines.append({
                "x1": float(attr("x1") or 0),
                "y1": float(attr("y1") or 0),
                "x2": float(attr("x2") or 0),
                "y2": float(attr("y2") or 0),
                "stroke": attr("stroke") or "#333333",
                "sw": float(attr("stroke-width") or 1),
            })
        except (ValueError, TypeError):
            continue
    return lines


def _hex_to_color(hex_str: str, opacity: float = 1.0):
    """Convert hex color to reportlab Color."""
    hex_str = hex_str.lstrip("#")
    if len(hex_str) == 6:
        r, g, b = int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16)
        return colors.Color(r / 255, g / 255, b / 255, opacity)
    return colors.Color(0.8, 0.8, 0.8, opacity)


def _draw_svg_on_canvas(c, svg_text: str, x_offset: float, y_offset: float, scale: float, svg_h: float):
    """Draw parsed SVG primitives onto reportlab canvas.

    Reportlab has Y going up, SVG has Y going down. We flip.
    """
    c.saveState()
    c.translate(x_offset, y_offset)
    c.scale(scale, scale)

    # Flip Y axis for SVG coordinate system
    c.translate(0, svg_h)
    c.scale(1, -1)

    rects = _parse_svg_rects(svg_text)
    for r in rects:
        fill = _hex_to_color(r["fill"], r["opacity"])
        stroke_c = _hex_to_color(r["stroke"])
        c.setFillColor(fill)
        c.setStrokeColor(stroke_c)
        c.setLineWidth(0.5)
        c.rect(r["x"], r["y"], r["w"], r["h"], fill=1, stroke=1)

    line_elems = _parse_svg_lines(svg_text)
    for ln in line_elems:
        c.setStrokeColor(_hex_to_color(ln["stroke"]))
        c.setLineWidth(ln["sw"] * 0.7)
        c.line(ln["x1"], ln["y1"], ln["x2"], ln["y2"])

    # Text needs un-flipped Y
    c.scale(1, -1)
    texts = _parse_svg_texts(svg_text)
    for t in texts:
        c.setFillColor(_hex_to_color(t["fill"]))
        c.setFont(BODY_FONT, t["size"] * 0.85)
        tx = t["x"]
        ty = t["y"]
        if t["anchor"] == "middle":
            c.drawCentredString(tx, -ty + t["size"] * 0.3, t["text"])
        else:
            c.drawString(tx, -ty + t["size"] * 0.3, t["text"])

    c.restoreState()


def _new_page_if_needed(c, y, needed: float) -> float:
    """Start a new page if not enough space. Returns updated y."""
    if y - needed < MARGIN:
        c.showPage()
        return PAGE_H - MARGIN
    return y


def export_pdf(
    output_data: dict,
    manifest: dict | None,
    out_path: Path,
    include_answers: bool = False,
):
    """Generate a PDF worksheet."""
    c = pdf_canvas.Canvas(str(out_path), pagesize=A4)

    # Build SVG lookup from manifest
    svg_lookup: dict[str, dict] = {}
    if manifest:
        for entry in manifest.get("entries", []):
            svg_path = entry.get("svg_path")
            if svg_path and Path(svg_path).exists():
                svg_lookup[entry["q_id"]] = {
                    "svg": Path(svg_path).read_text(),
                    "width": entry.get("width", 400),
                    "height": entry.get("height", 300),
                }

    y = PAGE_H - MARGIN

    # --- Title block ---
    c.setFont(HEADER_FONT, FONT_SIZE_TITLE)
    skill_name = output_data.get("skill_name", "Worksheet")
    c.drawString(MARGIN, y, f"PracticeCraft Worksheet")
    y -= 22

    c.setFont(BODY_FONT, FONT_SIZE_SUBTITLE)
    c.drawString(MARGIN, y, f"Skill: {output_data.get('skill_id', '')} — {skill_name}")
    y -= 16
    c.drawString(MARGIN, y, f"Difficulty: {output_data.get('difficulty', 'L2')}    |    Grade 3 Math")
    y -= 8

    # Divider line
    c.setStrokeColor(colors.Color(0.3, 0.3, 0.3))
    c.setLineWidth(1)
    c.line(MARGIN, y, PAGE_W - MARGIN, y)
    y -= 20

    # --- Questions ---
    questions = output_data.get("questions", [])
    for qi, q in enumerate(questions):
        q_id = q.get("q_id", f"Q{qi+1:02d}")
        representation = q.get("representation", "")
        question_text = q.get("question_text", "")
        options = q.get("options", [])

        # Estimate space needed
        svg_info = svg_lookup.get(q_id)
        svg_needed = (svg_info["height"] * SVG_SCALE + 20) if svg_info else 0
        total_needed = 30 + svg_needed + len(options) * 16 + 20
        y = _new_page_if_needed(c, y, total_needed)

        # Question number + text
        c.setFont(HEADER_FONT, FONT_SIZE_BODY)
        c.drawString(MARGIN, y, f"{q_id}.")
        c.setFont(BODY_FONT, FONT_SIZE_BODY)

        # Word-wrap question_text
        max_text_w = CONTENT_W - 30
        words = question_text.split()
        lines_out: list[str] = []
        current_line = ""
        for word in words:
            test = f"{current_line} {word}".strip()
            if c.stringWidth(test, BODY_FONT, FONT_SIZE_BODY) < max_text_w:
                current_line = test
            else:
                if current_line:
                    lines_out.append(current_line)
                current_line = word
        if current_line:
            lines_out.append(current_line)

        for line in lines_out:
            c.drawString(MARGIN + 30, y, line)
            y -= LINE_HEIGHT
        y -= 4

        # Render SVG if pictorial
        if svg_info:
            svg_text = svg_info["svg"]
            svg_w = svg_info["width"]
            svg_h = svg_info["height"]
            scaled_h = svg_h * SVG_SCALE

            y = _new_page_if_needed(c, y, scaled_h + 10)

            _draw_svg_on_canvas(c, svg_text, MARGIN + 10, y - scaled_h, SVG_SCALE, svg_h)
            y -= scaled_h + 10

        # Options
        for opt in options:
            y = _new_page_if_needed(c, y, 16)
            c.setFont(BODY_FONT, FONT_SIZE_OPTION)
            c.drawString(MARGIN + 36, y, opt)
            y -= 14

        y -= 12

    # --- Answer Key (optional, on new page) ---
    if include_answers:
        c.showPage()
        y = PAGE_H - MARGIN

        c.setFont(HEADER_FONT, FONT_SIZE_TITLE)
        c.drawString(MARGIN, y, "Answer Key")
        y -= 24

        c.setStrokeColor(colors.Color(0.3, 0.3, 0.3))
        c.line(MARGIN, y, PAGE_W - MARGIN, y)
        y -= 16

        for q in questions:
            q_id = q.get("q_id", "")
            answer = q.get("answer", "")
            answer_value = q.get("answer_value", "")
            answer_key = q.get("answer_key", "")

            needed = 20 + (len(answer_key) // 80 + 1) * LINE_HEIGHT + 16
            y = _new_page_if_needed(c, y, needed)

            c.setFont(HEADER_FONT, FONT_SIZE_BODY)
            c.drawString(MARGIN, y, f"{q_id}: {answer}) {answer_value}")
            y -= LINE_HEIGHT

            c.setFont(BODY_FONT, FONT_SIZE_SMALL)
            # Word-wrap answer_key
            words = answer_key.split()
            current_line = ""
            for word in words:
                test = f"{current_line} {word}".strip()
                if c.stringWidth(test, BODY_FONT, FONT_SIZE_SMALL) < CONTENT_W - 20:
                    current_line = test
                else:
                    c.drawString(MARGIN + 10, y, current_line)
                    y -= LINE_HEIGHT - 2
                    current_line = word
            if current_line:
                c.drawString(MARGIN + 10, y, current_line)
                y -= LINE_HEIGHT - 2

            y -= 10

    c.save()


def main():
    parser = argparse.ArgumentParser(description="Export worksheet as PDF")
    parser.add_argument("--output-json", required=True, help="Path to output.json")
    parser.add_argument("--render-manifest", default=None, help="Path to render_manifest.json")
    parser.add_argument("--out", required=True, help="Output PDF path")
    parser.add_argument("--include-answers", action="store_true", help="Include answer key page")

    args = parser.parse_args()

    output_data = load_json(args.output_json)
    manifest = load_json(args.render_manifest) if args.render_manifest else None

    out_path = Path(args.out)
    export_pdf(output_data, manifest, out_path, args.include_answers)
    print(f"PDF written to {out_path}")


if __name__ == "__main__":
    main()
