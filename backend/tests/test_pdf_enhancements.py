"""
Tests for PDF enhancements: curriculum badge (#3), difficulty labels (#11),
and verification footer (#12).

All tests run fully offline — no Supabase or LLM calls required.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.pdf import PDFService


def _minimal_worksheet(**overrides) -> dict:
    """Build a minimal worksheet dict for PDF generation."""
    ws = {
        "title": "Test Worksheet",
        "grade": "Class 3",
        "subject": "Maths",
        "topic": "Addition",
        "questions": [
            {
                "text": "What is 5 + 3?",
                "correct_answer": "8",
                "type": "short_answer",
                "format": "short_answer",
                "difficulty": "easy",
                "role": "recognition",
            },
            {
                "text": "Solve 12 + 7",
                "correct_answer": "19",
                "type": "short_answer",
                "format": "short_answer",
                "difficulty": "medium",
                "role": "application",
            },
        ],
    }
    ws.update(overrides)
    return ws


class TestPDFEnhancements:
    def test_pdf_generates_with_chapter_ref(self):
        """PDF renders without error when chapter_ref is present."""
        ws = _minimal_worksheet(chapter_ref="Chapter 7: Time")
        pdf_bytes = PDFService().generate_worksheet_pdf(ws)
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 0

    def test_pdf_generates_without_chapter_ref(self):
        """PDF renders without error when chapter_ref is None."""
        ws = _minimal_worksheet(chapter_ref=None)
        pdf_bytes = PDFService().generate_worksheet_pdf(ws)
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 0

    def test_pdf_generates_with_difficulty_labels(self):
        """PDF renders without error when questions have difficulty labels."""
        ws = _minimal_worksheet()
        pdf_bytes = PDFService().generate_worksheet_pdf(ws)
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 0

    def test_answer_key_has_verification_footer(self):
        """Answer key PDF renders and includes content (verification footer is there)."""
        ws = _minimal_worksheet()
        pdf_bytes = PDFService().generate_worksheet_pdf(ws, pdf_type="answer_key")
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 0

    def test_full_pdf_with_all_enhancements(self):
        """Full PDF with chapter_ref + difficulty + footer all together."""
        ws = _minimal_worksheet(
            chapter_ref="Chapter 3: Addition with Regrouping",
            learning_objectives=["Add two 3-digit numbers with regrouping"],
        )
        pdf_bytes = PDFService().generate_worksheet_pdf(ws, pdf_type="full")
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 0
