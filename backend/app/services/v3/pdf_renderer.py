"""PDF generation via WeasyPrint — converts worksheet HTML to print-ready PDF.

Replaces the 2644-line ReportLab pdf.py with a single function.
Same HTML template used for screen display also produces the PDF.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def generate_pdf(worksheet: dict, pdf_type: str = "full") -> bytes:
    """Generate PDF from worksheet dict.

    Args:
        worksheet: Enriched worksheet dict (visual_strategy already applied)
        pdf_type: "full" (questions + answers), "student" (questions only),
                  "answer_key" (answers only)

    Returns:
        PDF file as bytes
    """
    from weasyprint import HTML
    from weasyprint.text.fonts import FontConfiguration

    from .visual_strategy import enrich_visuals
    from .worksheet_template import render_worksheet_html

    font_config = FontConfiguration()

    # Enrich visuals if not already done
    if not worksheet.get("questions", [{}])[0].get("card_color"):
        worksheet = enrich_visuals(worksheet)

    # Modify worksheet for pdf_type
    ws_copy = dict(worksheet)
    if pdf_type == "student":
        ws_copy["_hide_answers"] = True
    elif pdf_type == "answer_key":
        ws_copy["_answers_only"] = True

    html_string = render_worksheet_html(ws_copy)

    html = HTML(string=html_string)
    pdf_bytes = html.write_pdf(font_config=font_config)

    logger.info(
        "[pdf_renderer] Generated %d bytes PDF (%s) for: %s",
        len(pdf_bytes),
        pdf_type,
        worksheet.get("title", ""),
    )
    return pdf_bytes
