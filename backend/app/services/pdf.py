"""PDF generation service for creating premium downloadable worksheets.

Gold-G8: Redesigned to match Pearson/Oxford primary workbook quality.
- Tiered difficulty sections (Foundation / Application / Stretch)
- Name / Date / Score header fields
- Generous margins, clean typography, adequate answer space
- Professional footer with page number + branding
"""

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether,
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
import io
from xml.sax.saxutils import escape as xml_escape


# ──────────────────────────────────────────────
# Colours — warm, professional palette
# ──────────────────────────────────────────────
_PRIMARY = colors.Color(0.15, 0.32, 0.22)       # deep forest green
_ACCENT = colors.Color(0.80, 0.60, 0.15)        # warm amber
_LIGHT_BG = colors.Color(0.96, 0.96, 0.94)      # warm off-white
_TIER_BG = colors.Color(0.94, 0.94, 0.92)       # tier header bg
_MUTED = colors.Color(0.55, 0.55, 0.55)         # muted grey
_RULE = colors.Color(0.82, 0.82, 0.78)          # ruled line colour
_HINT_BG = colors.Color(0.95, 0.95, 0.93)       # hint box bg


# ──────────────────────────────────────────────
# Unicode → latin-1 safe replacements
# ──────────────────────────────────────────────
_UNICODE_REPLACEMENTS = {
    "\u2014": "-",   # em dash
    "\u2013": "-",   # en dash
    "\u2018": "'",   # left single quote
    "\u2019": "'",   # right single quote
    "\u201c": '"',   # left double quote
    "\u201d": '"',   # right double quote
    "\u2026": "...", # ellipsis
    "\u00d7": "x",   # multiplication sign
    "\u00f7": "/",   # division sign
    "\u2264": "<=",  # less than or equal
    "\u2265": ">=",  # greater than or equal
    "\u2260": "!=",  # not equal
    "\u25a1": "___", # white square (blank marker) — wider for writing
    "\u25a2": "___", # white square with rounded corners
    "\u2610": "___", # ballot box
    "\u2192": "->",  # right arrow
    "\u2605": "*",   # star
    "\u2b50": "*",   # star emoji
}


def _sanitize_text(text: str) -> str:
    """Replace Unicode characters that Helvetica/latin-1 cannot encode."""
    if not text:
        return ""
    for char, replacement in _UNICODE_REPLACEMENTS.items():
        text = text.replace(char, replacement)
    return text.encode("latin-1", errors="replace").decode("latin-1")


# ──────────────────────────────────────────────
# Tier grouping logic
# ──────────────────────────────────────────────
_FOUNDATION_ROLES = {"recognition", "representation"}
_APPLICATION_ROLES = {"application"}
_STRETCH_ROLES = {"error_detection", "thinking"}

_TIER_CONFIG = [
    ("foundation", _FOUNDATION_ROLES, "Foundation", "I can recall and recognise"),
    ("application", _APPLICATION_ROLES, "Application", "I can use what I know"),
    ("stretch", _STRETCH_ROLES, "Stretch", "I can think and reason"),
]

# Star labels for each tier
_TIER_STARS = {
    "foundation": "*",
    "application": "**",
    "stretch": "***",
}


def _group_questions_by_tier(questions: list) -> list[tuple[str, str, str, list]]:
    """Group questions into Foundation / Application / Stretch tiers.

    Returns list of (tier_key, tier_label, tier_desc, questions) tuples.
    Only includes tiers that have questions.
    """
    tiers = []
    for tier_key, roles, label, desc in _TIER_CONFIG:
        tier_qs = [q for q in questions if q.get("role", "") in roles]
        if tier_qs:
            tiers.append((tier_key, label, desc, tier_qs))

    # If no role data, return all questions as a single unnamed tier
    if not tiers:
        return [("all", "", "", questions)]

    return tiers


class PDFService:
    """Service for generating premium PDF worksheets."""

    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()
        self._page_count = 0

    def _setup_custom_styles(self):
        """Set up premium paragraph styles using built-in Helvetica family."""

        # ── Title ──
        self.styles.add(ParagraphStyle(
            name='WorksheetTitle',
            fontName='Helvetica-Bold',
            fontSize=20,
            leading=24,
            spaceAfter=4,
            alignment=TA_CENTER,
            textColor=_PRIMARY,
        ))

        # ── Subtitle (grade | subject | topic) ──
        self.styles.add(ParagraphStyle(
            name='WorksheetSubtitle',
            fontName='Helvetica',
            fontSize=10,
            textColor=_MUTED,
            alignment=TA_CENTER,
            spaceAfter=16,
        ))

        # ── Tier section header ──
        self.styles.add(ParagraphStyle(
            name='TierHeader',
            fontName='Helvetica-Bold',
            fontSize=11,
            leading=14,
            textColor=_PRIMARY,
            spaceBefore=18,
            spaceAfter=4,
        ))
        self.styles.add(ParagraphStyle(
            name='TierDesc',
            fontName='Helvetica-Oblique',
            fontSize=8.5,
            textColor=_MUTED,
            spaceAfter=10,
            leftIndent=2,
        ))

        # ── Question text ──
        self.styles.add(ParagraphStyle(
            name='QuestionText',
            fontName='Helvetica',
            fontSize=11,
            leading=15,
            spaceAfter=6,
            leftIndent=28,
        ))

        # ── Question number ──
        self.styles.add(ParagraphStyle(
            name='QuestionNumber',
            fontName='Helvetica-Bold',
            fontSize=11,
            leading=15,
            textColor=_PRIMARY,
        ))

        # ── Options (MCQ) ──
        self.styles.add(ParagraphStyle(
            name='OptionText',
            fontName='Helvetica',
            fontSize=10,
            leading=13,
            leftIndent=42,
            spaceAfter=2,
        ))

        # ── Instructions box ──
        self.styles.add(ParagraphStyle(
            name='Instructions',
            fontName='Helvetica',
            fontSize=9,
            leading=13,
            textColor=colors.Color(0.3, 0.3, 0.3),
            spaceAfter=12,
        ))

        # ── Header fields (Name/Date/Score) ──
        self.styles.add(ParagraphStyle(
            name='HeaderField',
            fontName='Helvetica',
            fontSize=10,
            leading=13,
        ))

        # ── Hint text ──
        self.styles.add(ParagraphStyle(
            name='HintText',
            fontName='Helvetica-Oblique',
            fontSize=8.5,
            leading=11,
            textColor=_MUTED,
            leftIndent=28,
            spaceAfter=4,
        ))

        # ── Learning objective ──
        self.styles.add(ParagraphStyle(
            name='ObjectiveTitle',
            fontName='Helvetica-Bold',
            fontSize=9.5,
            leading=12,
            textColor=_PRIMARY,
            spaceAfter=4,
        ))
        self.styles.add(ParagraphStyle(
            name='ObjectiveItem',
            fontName='Helvetica',
            fontSize=9,
            leading=12,
            leftIndent=12,
            textColor=colors.Color(0.25, 0.25, 0.25),
        ))

        # ── Answer key ──
        self.styles.add(ParagraphStyle(
            name='AnswerKeyTitle',
            fontName='Helvetica-Bold',
            fontSize=14,
            leading=18,
            textColor=_PRIMARY,
            spaceBefore=16,
            spaceAfter=10,
            alignment=TA_CENTER,
        ))
        self.styles.add(ParagraphStyle(
            name='AnswerText',
            fontName='Helvetica',
            fontSize=9,
            leading=12,
            leftIndent=8,
        ))
        self.styles.add(ParagraphStyle(
            name='ExplanationText',
            fontName='Helvetica-Oblique',
            fontSize=8.5,
            leading=11,
            leftIndent=8,
            textColor=_MUTED,
        ))

    # ──────────────────────────────────────────
    # Main entry point
    # ──────────────────────────────────────────
    def generate_worksheet_pdf(self, worksheet: dict, pdf_type: str = "full") -> bytes:
        """Generate a premium PDF from a worksheet.

        Args:
            worksheet: Worksheet data with title, questions, etc.
            pdf_type: "full" (questions + answer key), "student" (questions only),
                      "answer_key" (answer key only)

        Returns:
            PDF file as bytes
        """
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=2.0 * cm,
            leftMargin=2.0 * cm,
            topMargin=2.0 * cm,
            bottomMargin=2.0 * cm,
        )

        # Store worksheet metadata for header/footer callbacks
        self._current_worksheet = worksheet
        self._page_count = 0

        story = []
        questions = worksheet.get('questions', [])

        if pdf_type == "answer_key":
            self._build_answer_key(story, worksheet, questions)
        else:
            self._build_questions(story, worksheet, questions)
            if pdf_type == "full" and questions:
                story.append(PageBreak())
                self._build_answer_key(story, worksheet, questions)

        doc.build(
            story,
            onFirstPage=self._draw_page_furniture,
            onLaterPages=self._draw_page_furniture,
        )
        buffer.seek(0)
        return buffer.getvalue()

    # ──────────────────────────────────────────
    # Page furniture (header rule + footer)
    # ──────────────────────────────────────────
    def _draw_page_furniture(self, canvas, doc):
        """Draw footer with page number and branding on every page."""
        canvas.saveState()
        page_width, page_height = A4
        self._page_count += 1

        # ── Top rule line ──
        canvas.setStrokeColor(_PRIMARY)
        canvas.setLineWidth(1.5)
        canvas.line(2.0 * cm, page_height - 1.6 * cm,
                    page_width - 2.0 * cm, page_height - 1.6 * cm)

        # ── Footer ──
        y_footer = 1.0 * cm

        # Left: branding
        canvas.setFont('Helvetica', 7)
        canvas.setFillColor(_MUTED)
        canvas.drawString(2.0 * cm, y_footer, "PracticeCraft  |  practicecraft.in")

        # Right: page number
        canvas.drawRightString(
            page_width - 2.0 * cm, y_footer,
            f"Page {self._page_count}"
        )

        # Footer rule line
        canvas.setStrokeColor(_RULE)
        canvas.setLineWidth(0.5)
        canvas.line(2.0 * cm, y_footer + 10, page_width - 2.0 * cm, y_footer + 10)

        canvas.restoreState()

    # ──────────────────────────────────────────
    # Questions section
    # ──────────────────────────────────────────
    def _build_questions(self, story: list, worksheet: dict, questions: list) -> None:
        """Build the questions section with tiered layout."""

        # ── Title ──
        title = _sanitize_text(worksheet.get('title', 'Practice Worksheet'))
        story.append(Paragraph(title, self.styles['WorksheetTitle']))

        # ── Subtitle (grade | subject | topic) ──
        subtitle_parts = []
        if worksheet.get('grade'):
            subtitle_parts.append(worksheet['grade'])
        if worksheet.get('subject'):
            subtitle_parts.append(worksheet['subject'])
        if worksheet.get('topic'):
            subtitle_parts.append(worksheet['topic'])
        if subtitle_parts:
            subtitle = _sanitize_text("  |  ".join(subtitle_parts))
            story.append(Paragraph(subtitle, self.styles['WorksheetSubtitle']))

        story.append(Spacer(1, 4))

        # ── Learning Objectives (Gold-G5) ──
        objectives = worksheet.get('learning_objectives', [])
        if objectives:
            self._build_learning_objectives(story, objectives)
            story.append(Spacer(1, 6))

        # ── Name / Date / Score header fields ──
        self._build_header_fields(story, worksheet, questions)

        story.append(Spacer(1, 6))

        # ── Instructions ──
        story.append(Paragraph(
            "<b>Instructions:</b> Read each question carefully. "
            "Show your working in the space provided. Answer all questions.",
            self.styles['Instructions']
        ))

        # ── Thin separator ──
        story.append(HRFlowable(
            width="100%", thickness=0.5, color=_RULE,
            spaceBefore=2, spaceAfter=12,
        ))

        # ── Group questions by tier and render ──
        tiers = _group_questions_by_tier(questions)
        q_number = 1  # continuous question numbering across tiers

        for tier_key, tier_label, tier_desc, tier_qs in tiers:
            if tier_label:
                stars = _TIER_STARS.get(tier_key, "")
                story.append(Paragraph(
                    f"{stars}  {tier_label}",
                    self.styles['TierHeader']
                ))
                story.append(Paragraph(tier_desc, self.styles['TierDesc']))

            for question in tier_qs:
                elements = self._build_single_question(question, q_number, tier_key)
                # KeepTogether prevents a question from breaking across pages
                story.append(KeepTogether(elements))
                story.append(Spacer(1, 10))
                q_number += 1

    def _build_header_fields(self, story: list, worksheet: dict, questions: list) -> None:
        """Build Name / Date / Score fields as a table row."""
        num_q = len(questions)
        page_width = A4[0] - 4.0 * cm  # usable width with 2cm margins

        row_data = [
            [
                Paragraph("Name: ____________________________", self.styles['HeaderField']),
                Paragraph("Date: ______________", self.styles['HeaderField']),
                Paragraph(f"Score: _____ / {num_q}", self.styles['HeaderField']),
            ]
        ]

        col_w1 = page_width * 0.50
        col_w2 = page_width * 0.28
        col_w3 = page_width * 0.22

        header_table = Table(row_data, colWidths=[col_w1, col_w2, col_w3])
        header_table.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LINEBELOW', (0, 0), (-1, -1), 0.5, _RULE),
        ]))
        story.append(header_table)

    def _build_learning_objectives(self, story: list, objectives: list[str]) -> None:
        """Render a learning objective box at the top of the worksheet."""
        page_width = A4[0] - 4.0 * cm

        # Build content: title + bullet items
        obj_elements = []
        obj_elements.append(Paragraph(
            "Today's Learning Goal",
            self.styles['ObjectiveTitle']
        ))
        for obj in objectives:
            obj_elements.append(Paragraph(
                f"<bullet>&bull;</bullet> {_sanitize_text(obj)}",
                self.styles['ObjectiveItem']
            ))

        # Wrap in a single-cell table for the bordered box
        obj_table = Table(
            [[obj_elements]],
            colWidths=[page_width - 1.0 * cm],
        )
        obj_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), _LIGHT_BG),
            ('BOX', (0, 0), (-1, -1), 0.5, _PRIMARY),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 12),
            ('RIGHTPADDING', (0, 0), (-1, -1), 12),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        story.append(obj_table)

    def _build_single_question(self, question: dict, number: int, tier_key: str = "all") -> list:
        """Build elements for a single question. Returns list of flowables."""
        elements = []
        q_type = question.get('type', 'short_answer')
        q_text = _sanitize_text(question.get('text', ''))

        # Star badge based on tier
        star_badge = ""
        if tier_key == "foundation":
            star_badge = " *"
        elif tier_key == "application":
            star_badge = " **"
        elif tier_key == "stretch":
            star_badge = " ***"

        # Question text with number + star badge
        elements.append(Paragraph(
            f"<b><font color='#{_PRIMARY.hexval()[2:]}'>{number}.</font></b>"
            f"<font size='7' color='#{_ACCENT.hexval()[2:]}'>{star_badge}</font>  {q_text}",
            self.styles['QuestionText']
        ))

        # Answer area based on type
        if q_type == 'multiple_choice' and question.get('options'):
            for j, option in enumerate(question['options']):
                letter = chr(65 + j)
                elements.append(Paragraph(
                    f"<font color='#{_PRIMARY.hexval()[2:]}'>{letter})</font>  "
                    f"{_sanitize_text(str(option))}",
                    self.styles['OptionText']
                ))
            elements.append(Spacer(1, 6))

        elif q_type == 'true_false':
            elements.append(Paragraph(
                "<font color='#{0}'>A)</font>  True      "
                "<font color='#{0}'>B)</font>  False".format(_PRIMARY.hexval()[2:]),
                self.styles['OptionText']
            ))
            elements.append(Spacer(1, 6))

        elif q_type == 'fill_blank':
            # Single answer line with box-style underline
            elements.append(Spacer(1, 4))
            elements.append(Paragraph(
                "Ans: ________________________________________",
                self.styles['OptionText']
            ))
            elements.append(Spacer(1, 6))

        else:
            # Short answer — 3 ruled lines for adequate writing space
            elements.append(Spacer(1, 6))
            for _ in range(3):
                elements.append(HRFlowable(
                    width="85%", thickness=0.3, color=_RULE,
                    spaceBefore=10, spaceAfter=0,
                    hAlign='LEFT',
                ))
            elements.append(Spacer(1, 4))

        # Hint for thinking/error_detection questions (printed subtly)
        explanation = question.get('explanation')
        role = question.get('role', '')
        if explanation and role in ('thinking', 'error_detection'):
            hint_text = _sanitize_text(explanation)
            elements.append(Paragraph(
                f"<i>Hint: {hint_text}</i>",
                self.styles['HintText']
            ))

        return elements

    # ──────────────────────────────────────────
    # Answer key section
    # ──────────────────────────────────────────
    def _build_answer_key(self, story: list, worksheet: dict, questions: list) -> None:
        """Build a clean answer key section."""
        title = _sanitize_text(worksheet.get('title', 'Practice Worksheet'))
        story.append(Paragraph(f"{title} - Answer Key", self.styles['AnswerKeyTitle']))

        story.append(HRFlowable(
            width="100%", thickness=0.5, color=_PRIMARY,
            spaceBefore=2, spaceAfter=14,
        ))

        # Answer grid — 3 columns
        answer_data = []
        row = []
        for i, question in enumerate(questions, 1):
            answer = question.get('correct_answer', 'N/A')
            if isinstance(answer, list):
                answer = ', '.join(str(a) for a in answer)
            row.append(Paragraph(
                f"<b>Q{i}:</b> {_sanitize_text(str(answer))}",
                self.styles['AnswerText']
            ))
            if len(row) == 3:
                answer_data.append(row)
                row = []
        if row:
            while len(row) < 3:
                row.append('')
            answer_data.append(row)

        if answer_data:
            page_width = A4[0] - 4.0 * cm
            col_w = page_width / 3
            answer_table = Table(answer_data, colWidths=[col_w] * 3)
            answer_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('GRID', (0, 0), (-1, -1), 0.4, _RULE),
                # Alternate row shading
                *[
                    ('BACKGROUND', (0, r), (-1, r), _LIGHT_BG)
                    for r in range(0, len(answer_data), 2)
                ],
            ]))
            story.append(answer_table)

        # Explanations
        has_explanations = any(q.get('explanation') for q in questions)
        if has_explanations:
            story.append(Spacer(1, 18))
            story.append(Paragraph(
                "<b>Explanations</b>",
                self.styles['AnswerKeyTitle']
            ))
            story.append(HRFlowable(
                width="100%", thickness=0.3, color=_RULE,
                spaceBefore=2, spaceAfter=10,
            ))

            for i, question in enumerate(questions, 1):
                explanation = question.get('explanation')
                if explanation:
                    story.append(Paragraph(
                        f"<b>Q{i}:</b> {_sanitize_text(explanation)}",
                        self.styles['ExplanationText']
                    ))
                    story.append(Spacer(1, 4))


def get_pdf_service() -> PDFService:
    return PDFService()
