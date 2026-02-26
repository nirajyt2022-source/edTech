"""Tests for PDF working area whitespace (Item E)."""

import pytest


@pytest.fixture
def pdf_service():
    """Return a fresh PDF service instance."""
    from app.services.pdf import PDFService

    return PDFService()


def _make_worksheet(subject: str, questions: list[dict]) -> dict:
    return {
        "title": "Test Worksheet",
        "grade": "Class 3",
        "subject": subject,
        "topic": "Addition",
        "questions": questions,
    }


def _make_questions(count: int = 5, difficulty: str = "medium") -> list[dict]:
    return [
        {
            "text": f"What is {i+1} + {i+2}?",
            "format": "short_answer",
            "correct_answer": str(2 * i + 3),
            "difficulty": difficulty,
            "role": "application",
        }
        for i in range(count)
    ]


def test_maths_pdf_larger_than_english(pdf_service):
    """Maths PDF with working area should be larger than English PDF."""
    maths_qs = _make_questions(5, "medium")
    english_qs = _make_questions(5, "medium")

    maths_ws = _make_worksheet("Maths", maths_qs)
    english_ws = _make_worksheet("English", english_qs)

    maths_pdf = pdf_service.generate_worksheet_pdf(maths_ws)
    english_pdf = pdf_service.generate_worksheet_pdf(english_ws)

    # Maths PDF should be larger due to working area elements
    assert len(maths_pdf) > len(english_pdf)


def test_pdf_generates_with_working_area(pdf_service):
    """PDF generation should succeed with working area enabled."""
    qs = _make_questions(3, "hard")
    ws = _make_worksheet("Maths", qs)

    pdf_bytes = pdf_service.generate_worksheet_pdf(ws)
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 0
    assert pdf_bytes[:5] == b"%PDF-"


def test_easy_maths_skips_working_area(pdf_service):
    """Easy recognition questions should not get working area."""
    easy_qs = _make_questions(3, "easy")
    for q in easy_qs:
        q["role"] = "recognition"
        q["difficulty"] = "easy"

    ws = _make_worksheet("Maths", easy_qs)
    pdf_easy = pdf_service.generate_worksheet_pdf(ws)

    # Medium questions get working area
    medium_qs = _make_questions(3, "medium")
    ws_medium = _make_worksheet("Maths", medium_qs)
    pdf_medium = pdf_service.generate_worksheet_pdf(ws_medium)

    # Medium should be larger due to working area
    assert len(pdf_medium) > len(pdf_easy)
