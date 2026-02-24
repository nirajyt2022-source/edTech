"""
PDF generation service for revision notes.

Produces a clean, colourful 1-2 page A4 PDF with:
- Header with topic title in forest green
- Key concepts with amber accent titles
- Worked examples with green headers
- Common mistakes with red accents
- Quick quiz with answer reveal
- Memory tips with lightbulb prefix
- Footer branding + page number
"""

import io
import os
import logging
from xml.sax.saxutils import escape as xml_escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

logger = logging.getLogger(__name__)

# ── Font registration (matches pdf.py pattern) ───────────────────────────

_FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "fonts")
_NOTO_VARIABLE = os.path.join(_FONT_DIR, "NotoSans-Variable.ttf")
_DEJAVU = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_DEJAVU_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

_USE_UNICODE_FONT = False

if os.path.exists(_NOTO_VARIABLE):
    try:
        pdfmetrics.registerFont(TTFont('RevisionFont', _NOTO_VARIABLE))
        pdfmetrics.registerFont(TTFont('RevisionFont-Bold', _NOTO_VARIABLE))
        _USE_UNICODE_FONT = True
    except Exception:
        pass

if not _USE_UNICODE_FONT and os.path.exists(_DEJAVU):
    try:
        pdfmetrics.registerFont(TTFont('RevisionFont', _DEJAVU))
        pdfmetrics.registerFont(TTFont('RevisionFont-Bold', _DEJAVU_BOLD if os.path.exists(_DEJAVU_BOLD) else _DEJAVU))
        _USE_UNICODE_FONT = True
    except Exception:
        pass

FONT_REGULAR = 'RevisionFont' if _USE_UNICODE_FONT else 'Helvetica'
FONT_BOLD = 'RevisionFont-Bold' if _USE_UNICODE_FONT else 'Helvetica-Bold'

# ── Colour palette ────────────────────────────────────────────────────────

_FOREST_GREEN = colors.HexColor("#1B4332")
_DARK_GREEN = colors.HexColor("#166534")
_AMBER = colors.HexColor("#D97706")
_RED = colors.HexColor("#DC2626")
_LIGHT_GREEN_BG = colors.HexColor("#F0FDF4")
_LIGHT_AMBER_BG = colors.HexColor("#FFFBEB")
_LIGHT_RED_BG = colors.HexColor("#FEF2F2")
_LIGHT_BLUE_BG = colors.HexColor("#EFF6FF")
_LIGHT_GREY_BG = colors.HexColor("#F9FAFB")
_MUTED_TEXT = colors.HexColor("#6B7280")
_BODY_TEXT = colors.HexColor("#1F2937")

PAGE_WIDTH, PAGE_HEIGHT = A4


# ── Styles ────────────────────────────────────────────────────────────────

def _build_styles():
    """Build all ParagraphStyles used in the revision PDF."""
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        'RevTitle',
        fontName=FONT_BOLD,
        fontSize=18,
        leading=22,
        textColor=_FOREST_GREEN,
        alignment=TA_CENTER,
        spaceAfter=2,
    ))

    styles.add(ParagraphStyle(
        'RevSubtitle',
        fontName=FONT_REGULAR,
        fontSize=10,
        leading=14,
        textColor=_MUTED_TEXT,
        alignment=TA_CENTER,
        spaceAfter=12,
    ))

    styles.add(ParagraphStyle(
        'RevSectionHeader',
        fontName=FONT_BOLD,
        fontSize=13,
        leading=17,
        textColor=_FOREST_GREEN,
        spaceBefore=14,
        spaceAfter=6,
    ))

    styles.add(ParagraphStyle(
        'RevBody',
        fontName=FONT_REGULAR,
        fontSize=9.5,
        leading=13,
        textColor=_BODY_TEXT,
        spaceAfter=4,
    ))

    styles.add(ParagraphStyle(
        'RevBodyBold',
        fontName=FONT_BOLD,
        fontSize=9.5,
        leading=13,
        textColor=_BODY_TEXT,
        spaceAfter=2,
    ))

    styles.add(ParagraphStyle(
        'RevConceptTitle',
        fontName=FONT_BOLD,
        fontSize=10,
        leading=13,
        textColor=_AMBER,
        spaceAfter=2,
    ))

    styles.add(ParagraphStyle(
        'RevExampleHeader',
        fontName=FONT_BOLD,
        fontSize=10,
        leading=13,
        textColor=_DARK_GREEN,
        spaceAfter=2,
    ))

    styles.add(ParagraphStyle(
        'RevMistakeHeader',
        fontName=FONT_BOLD,
        fontSize=10,
        leading=13,
        textColor=_RED,
        spaceAfter=2,
    ))

    styles.add(ParagraphStyle(
        'RevAnswer',
        fontName=FONT_BOLD,
        fontSize=9.5,
        leading=13,
        textColor=_DARK_GREEN,
        spaceAfter=2,
    ))

    styles.add(ParagraphStyle(
        'RevFooter',
        fontName=FONT_REGULAR,
        fontSize=8,
        leading=10,
        textColor=_MUTED_TEXT,
        alignment=TA_CENTER,
    ))

    return styles


def _esc(text: str) -> str:
    """XML-escape text for safe use inside ReportLab Paragraphs."""
    if not text:
        return ""
    return xml_escape(str(text))


# ── Main PDF generation ──────────────────────────────────────────────────

def generate_revision_pdf(notes) -> bytes:
    """Generate a revision notes PDF and return raw bytes.

    Args:
        notes: RevisionResponse Pydantic model (or duck-typed object with same attrs).

    Returns:
        PDF file as bytes.
    """
    buf = io.BytesIO()
    styles = _build_styles()

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=1.5 * cm,
        bottomMargin=2.0 * cm,
        title=f"{notes.topic} - Revision Notes",
        author="Skolar",
    )

    story = []

    # ── Header ────────────────────────────────────────────────────────
    story.append(Paragraph(_esc(f"{notes.topic} \u2014 Revision Notes"), styles['RevTitle']))
    subtitle = f"{notes.grade}  |  {notes.subject}  |  {notes.language}"
    story.append(Paragraph(_esc(subtitle), styles['RevSubtitle']))
    story.append(HRFlowable(width="100%", thickness=1.5, color=_FOREST_GREEN, spaceAfter=10))

    # ── Introduction ──────────────────────────────────────────────────
    if notes.introduction:
        story.append(Paragraph(_esc(notes.introduction), styles['RevBody']))
        story.append(Spacer(1, 6))

    # ── Key Concepts ──────────────────────────────────────────────────
    if notes.key_concepts:
        story.append(Paragraph("\u25C6  Key Concepts", styles['RevSectionHeader']))

        for i, concept in enumerate(notes.key_concepts, 1):
            concept_items = []
            concept_items.append(Paragraph(
                f"{i}. {_esc(concept.title)}",
                styles['RevConceptTitle'],
            ))
            concept_items.append(Paragraph(_esc(concept.explanation), styles['RevBody']))
            if concept.example:
                concept_items.append(Paragraph(
                    f"<i>Example:</i> {_esc(concept.example)}",
                    styles['RevBody'],
                ))
            concept_items.append(Spacer(1, 4))

            # Wrap each concept in a light amber box
            inner_table = Table(
                [[concept_items]],
                colWidths=[doc.width - 0.6 * cm],
            )
            inner_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), _LIGHT_AMBER_BG),
                ('BOX', (0, 0), (-1, -1), 0.5, _AMBER),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            story.append(KeepTogether([inner_table, Spacer(1, 4)]))

    # ── Worked Examples ───────────────────────────────────────────────
    if notes.worked_examples:
        story.append(Paragraph("\u270D  Worked Examples", styles['RevSectionHeader']))

        for i, ex in enumerate(notes.worked_examples, 1):
            ex_items = []
            ex_items.append(Paragraph(
                f"Example {i}: {_esc(ex.problem)}",
                styles['RevExampleHeader'],
            ))
            for step_idx, step in enumerate(ex.step_by_step):
                ex_items.append(Paragraph(f"  {_esc(step)}", styles['RevBody']))
            ex_items.append(Paragraph(
                f"Answer: {_esc(ex.answer)}",
                styles['RevAnswer'],
            ))
            ex_items.append(Spacer(1, 4))

            inner_table = Table(
                [[ex_items]],
                colWidths=[doc.width - 0.6 * cm],
            )
            inner_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), _LIGHT_GREEN_BG),
                ('BOX', (0, 0), (-1, -1), 0.5, _DARK_GREEN),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            story.append(KeepTogether([inner_table, Spacer(1, 4)]))

    # ── Common Mistakes ───────────────────────────────────────────────
    if notes.common_mistakes:
        story.append(Paragraph("\u26A0  Common Mistakes", styles['RevSectionHeader']))

        for i, m in enumerate(notes.common_mistakes, 1):
            m_items = []
            m_items.append(Paragraph(
                f"{i}. Mistake: {_esc(m.mistake)}",
                styles['RevMistakeHeader'],
            ))
            m_items.append(Paragraph(
                f"<b>Correction:</b> {_esc(m.correction)}",
                styles['RevBody'],
            ))
            m_items.append(Paragraph(
                f"<i>Tip:</i> {_esc(m.tip)}",
                styles['RevBody'],
            ))
            m_items.append(Spacer(1, 4))

            inner_table = Table(
                [[m_items]],
                colWidths=[doc.width - 0.6 * cm],
            )
            inner_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), _LIGHT_RED_BG),
                ('BOX', (0, 0), (-1, -1), 0.5, _RED),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            story.append(KeepTogether([inner_table, Spacer(1, 4)]))

    # ── Quick Quiz ────────────────────────────────────────────────────
    if notes.quick_quiz:
        story.append(Paragraph("\u2753  Quick Quiz", styles['RevSectionHeader']))

        for i, q in enumerate(notes.quick_quiz, 1):
            q_items = []
            q_items.append(Paragraph(
                f"Q{i}. {_esc(q.question)}",
                styles['RevBodyBold'],
            ))
            option_letters = ['A', 'B', 'C', 'D']
            for j, opt in enumerate(q.options):
                letter = option_letters[j] if j < len(option_letters) else str(j + 1)
                is_correct = (opt.strip() == q.correct_answer.strip())
                if is_correct:
                    q_items.append(Paragraph(
                        f"  <b>{letter})</b> {_esc(opt)}  <font color='#166534'>\u2713</font>",
                        styles['RevAnswer'],
                    ))
                else:
                    q_items.append(Paragraph(
                        f"  {letter}) {_esc(opt)}",
                        styles['RevBody'],
                    ))
            if q.explanation:
                q_items.append(Paragraph(
                    f"<i>{_esc(q.explanation)}</i>",
                    styles['RevBody'],
                ))
            q_items.append(Spacer(1, 4))

            inner_table = Table(
                [[q_items]],
                colWidths=[doc.width - 0.6 * cm],
            )
            inner_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), _LIGHT_BLUE_BG),
                ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#3B82F6")),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            story.append(KeepTogether([inner_table, Spacer(1, 4)]))

    # ── Memory Tips ───────────────────────────────────────────────────
    if notes.memory_tips:
        story.append(Paragraph("\u2728  Memory Tips", styles['RevSectionHeader']))

        for tip in notes.memory_tips:
            story.append(Paragraph(
                f"\u2022  {_esc(tip)}",
                styles['RevBody'],
            ))
        story.append(Spacer(1, 8))

    # ── Build with footer ─────────────────────────────────────────────
    def _add_footer(canvas, doc):
        """Draw footer on every page."""
        canvas.saveState()
        # Branding
        canvas.setFont(FONT_REGULAR, 8)
        canvas.setFillColor(_MUTED_TEXT)
        canvas.drawCentredString(
            PAGE_WIDTH / 2,
            1.2 * cm,
            "Generated by Skolar \u2014 ed-tech-drab.vercel.app",
        )
        # Page number
        canvas.drawRightString(
            PAGE_WIDTH - 1.8 * cm,
            1.2 * cm,
            f"Page {doc.page}",
        )
        canvas.restoreState()

    doc.build(story, onFirstPage=_add_footer, onLaterPages=_add_footer)

    return buf.getvalue()
