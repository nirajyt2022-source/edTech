"""PDF generation service for creating downloadable worksheets."""

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.enums import TA_LEFT, TA_CENTER
import io
from typing import Any
from xml.sax.saxutils import escape as xml_escape


class PDFService:
    """Service for generating PDF versions of worksheets."""

    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        """Set up custom paragraph styles."""
        self.styles.add(ParagraphStyle(
            name='WorksheetTitle',
            parent=self.styles['Heading1'],
            fontSize=18,
            spaceAfter=6,
            alignment=TA_CENTER,
        ))
        self.styles.add(ParagraphStyle(
            name='WorksheetSubtitle',
            parent=self.styles['Normal'],
            fontSize=11,
            textColor=colors.grey,
            alignment=TA_CENTER,
            spaceAfter=20,
        ))
        self.styles.add(ParagraphStyle(
            name='QuestionText',
            parent=self.styles['Normal'],
            fontSize=11,
            spaceAfter=6,
            leftIndent=20,
        ))
        self.styles.add(ParagraphStyle(
            name='OptionText',
            parent=self.styles['Normal'],
            fontSize=10,
            leftIndent=40,
            spaceAfter=3,
        ))
        self.styles.add(ParagraphStyle(
            name='Instructions',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.darkblue,
            spaceAfter=15,
            borderPadding=10,
        ))
        self.styles.add(ParagraphStyle(
            name='AnswerKeyTitle',
            parent=self.styles['Heading2'],
            fontSize=14,
            spaceBefore=20,
            spaceAfter=10,
        ))
        self.styles.add(ParagraphStyle(
            name='AnswerText',
            parent=self.styles['Normal'],
            fontSize=9,
            leftIndent=10,
        ))

    def generate_worksheet_pdf(self, worksheet: dict, pdf_type: str = "full") -> bytes:
        """Generate a PDF from a worksheet.

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
            rightMargin=1.5*cm,
            leftMargin=1.5*cm,
            topMargin=1.5*cm,
            bottomMargin=1.5*cm
        )

        story = []
        questions = worksheet.get('questions', [])

        if pdf_type == "answer_key":
            self._build_answer_key(story, worksheet, questions)
        else:
            self._build_questions(story, worksheet, questions)
            if pdf_type == "full" and questions:
                story.append(PageBreak())
                self._build_answer_key(story, worksheet, questions)

        # Build PDF
        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()

    def _build_questions(self, story: list, worksheet: dict, questions: list) -> None:
        """Build the questions section of the PDF."""
        # Title
        title = worksheet.get('title', 'Practice Worksheet')
        story.append(Paragraph(title, self.styles['WorksheetTitle']))

        # Subtitle with metadata
        subtitle_parts = []
        if worksheet.get('grade'):
            subtitle_parts.append(worksheet['grade'])
        if worksheet.get('subject'):
            subtitle_parts.append(worksheet['subject'])
        if worksheet.get('topic'):
            subtitle_parts.append(worksheet['topic'])
        if worksheet.get('difficulty'):
            subtitle_parts.append(f"Difficulty: {worksheet['difficulty']}")

        if subtitle_parts:
            subtitle = " | ".join(subtitle_parts)
            story.append(Paragraph(subtitle, self.styles['WorksheetSubtitle']))

        # Instructions box
        story.append(Paragraph(
            "<b>Instructions:</b> Answer all questions. Show your work where applicable.",
            self.styles['Instructions']
        ))

        # Name and Date fields
        name_date_data = [
            ['Name: _______________________', 'Date: _______________']
        ]
        name_date_table = Table(name_date_data, colWidths=[10*cm, 6*cm])
        name_date_table.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 15),
        ]))
        story.append(name_date_table)
        story.append(Spacer(1, 15))

        # Questions
        for i, question in enumerate(questions, 1):
            q_type = question.get('type', 'short_answer')
            q_text = question.get('text', '')

            # Question number and text
            story.append(Paragraph(
                f"<b>Q{i}.</b> {q_text}",
                self.styles['QuestionText']
            ))

            # Handle different question types
            if q_type == 'multiple_choice' and question.get('options'):
                options = question['options']
                for j, option in enumerate(options):
                    letter = chr(65 + j)  # A, B, C, D
                    story.append(Paragraph(
                        f"({letter}) {option}",
                        self.styles['OptionText']
                    ))
                story.append(Spacer(1, 8))

            elif q_type == 'true_false':
                story.append(Paragraph("( ) True    ( ) False", self.styles['OptionText']))
                story.append(Spacer(1, 8))

            elif q_type == 'fill_blank':
                story.append(Paragraph(
                    "Answer: _______________________",
                    self.styles['OptionText']
                ))
                story.append(Spacer(1, 8))

            else:  # short_answer or other
                # Add lines for writing
                for _ in range(2):
                    story.append(Paragraph(
                        "_" * 70,
                        self.styles['OptionText']
                    ))
                story.append(Spacer(1, 8))

            story.append(Spacer(1, 5))

    def _build_answer_key(self, story: list, worksheet: dict, questions: list) -> None:
        """Build the answer key section of the PDF."""
        # Title header for standalone answer key
        title = worksheet.get('title', 'Practice Worksheet')
        story.append(Paragraph(f"{title} — Answer Key", self.styles['AnswerKeyTitle']))
        story.append(Spacer(1, 10))

        # Create answer key table
        answer_data = []
        row = []
        for i, question in enumerate(questions, 1):
            answer = question.get('correct_answer', 'N/A')
            if isinstance(answer, list):
                answer = ', '.join(answer)
            row.append(f"Q{i}: {answer}")
            if len(row) == 3:  # 3 columns per row
                answer_data.append(row)
                row = []
        if row:  # Add remaining items
            while len(row) < 3:
                row.append('')
            answer_data.append(row)

        if answer_data:
            answer_table = Table(answer_data, colWidths=[5.5*cm, 5.5*cm, 5.5*cm])
            answer_table.setStyle(TableStyle([
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ]))
            story.append(answer_table)

        # Add explanations if available
        has_explanations = any(q.get('explanation') for q in questions)
        if has_explanations:
            story.append(Spacer(1, 20))
            story.append(Paragraph("<b>Explanations:</b>", self.styles['Normal']))
            story.append(Spacer(1, 10))

            for i, question in enumerate(questions, 1):
                explanation = question.get('explanation')
                if explanation:
                    story.append(Paragraph(
                        f"<b>Q{i}:</b> {explanation}",
                        self.styles['AnswerText']
                    ))
                    story.append(Spacer(1, 5))


def get_pdf_service() -> PDFService:
    return PDFService()
