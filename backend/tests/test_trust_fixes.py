"""Tests for trust-fix changes: hard-block arithmetic, retry triggers, exact count."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from app.services.quality_reviewer import QualityReviewerAgent


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_context(subject: str = "Maths", grade: int = 3, valid_tags: list | None = None):
    """Create a minimal GenerationContext-like object."""
    ctx = MagicMock()
    ctx.subject = subject
    ctx.grade = grade
    ctx.valid_skill_tags = valid_tags or []
    return ctx


def _make_q(
    q_id: str = "q1",
    slot_type: str = "application",
    question_text: str = "What is 5 + 3?",
    answer: str = "8",
) -> dict:
    return {
        "id": q_id,
        "slot_type": slot_type,
        "question_text": question_text,
        "answer": answer,
    }


# ── Fix 1: Hard-block arithmetic ────────────────────────────────────────────


class TestHardBlockArithmetic:
    """CHECK 1 should mark questions _math_unverified on exception, not skip."""

    def test_correct_answer_no_flag(self):
        reviewer = QualityReviewerAgent()
        ctx = _make_context()
        q = _make_q(question_text="What is 5 + 3?", answer="8")
        result = reviewer.review_worksheet([q], ctx)
        assert not result.questions[0].get("_math_unverified")
        assert not result.questions[0].get("_answer_corrected")

    def test_wrong_answer_corrected(self):
        reviewer = QualityReviewerAgent()
        ctx = _make_context()
        q = _make_q(question_text="What is 5 + 3?", answer="9")
        result = reviewer.review_worksheet([q], ctx)
        assert result.questions[0]["answer"] == "8"
        assert result.questions[0]["_answer_corrected"] is True
        assert len(result.corrections) == 1

    def test_error_detection_skipped(self):
        """error_detection questions should not be math-checked."""
        reviewer = QualityReviewerAgent()
        ctx = _make_context()
        q = _make_q(slot_type="error_detection", question_text="5 + 3 = 9. Is this correct?", answer="No")
        result = reviewer.review_worksheet([q], ctx)
        assert not result.questions[0].get("_math_unverified")
        assert not result.questions[0].get("_answer_corrected")

    def test_non_maths_skipped(self):
        """Non-maths subjects should not trigger CHECK 1."""
        reviewer = QualityReviewerAgent()
        ctx = _make_context(subject="English")
        q = _make_q(question_text="What is 5 + 3?", answer="9")
        result = reviewer.review_worksheet([q], ctx)
        # English questions are not math-checked
        assert not result.questions[0].get("_answer_corrected")


# ── Fix 2: Unknown type gets [type_error] tag ───────────────────────────────


class TestUnknownTypeTag:
    """validate_response should tag unknown types with [type_error] prefix."""

    def test_unknown_type_tagged(self):
        from app.services.worksheet_generator import validate_response

        raw_data = {
            "questions": [
                {
                    "id": "q1",
                    "type": "matching_pairs",
                    "text": "Match the columns",
                    "correct_answer": "A-1, B-2",
                    "difficulty": "easy",
                    "role": "recognition",
                }
            ]
        }
        data, warnings = validate_response(json.dumps(raw_data), "Maths", "Addition", 1)
        assert data["questions"][0]["type"] == "short_answer"
        assert any("[type_error]" in w for w in warnings)

    def test_valid_type_no_tag(self):
        from app.services.worksheet_generator import validate_response

        raw_data = {
            "questions": [
                {
                    "id": "q1",
                    "type": "mcq",
                    "text": "What is 2 + 3?",
                    "options": ["3", "4", "5", "6"],
                    "correct_answer": "5",
                    "difficulty": "easy",
                    "role": "recognition",
                }
            ]
        }
        data, warnings = validate_response(json.dumps(raw_data), "Maths", "Addition", 1)
        assert not any("[type_error]" in w for w in warnings)


# ── Fix 5: Exact question count ─────────────────────────────────────────────


class TestExactQuestionCount:
    """OutputValidator should reject when count < requested (not 80%)."""

    def test_exact_count_passes(self):
        from app.services.output_validator import get_validator

        validator = get_validator()
        data = {"questions": [{"id": f"q{i}", "text": f"Q{i}?", "correct_answer": str(i), "type": "short_answer"} for i in range(10)]}
        is_valid, errors = validator.validate_worksheet(data, num_questions=10)
        count_errors = [e for e in errors if "count_mismatch" in e]
        assert len(count_errors) == 0

    def test_one_fewer_fails(self):
        """9 questions when 10 requested should now fail (was passing at 80%)."""
        from app.services.output_validator import get_validator

        validator = get_validator()
        data = {"questions": [{"id": f"q{i}", "text": f"Q{i}?", "correct_answer": str(i), "type": "short_answer"} for i in range(9)]}
        is_valid, errors = validator.validate_worksheet(data, num_questions=10)
        count_errors = [e for e in errors if "count_mismatch" in e]
        assert len(count_errors) == 1

    def test_eight_of_ten_now_fails(self):
        """8/10 was the old 80% threshold — should now fail."""
        from app.services.output_validator import get_validator

        validator = get_validator()
        data = {"questions": [{"id": f"q{i}", "text": f"Q{i}?", "correct_answer": str(i), "type": "short_answer"} for i in range(8)]}
        is_valid, errors = validator.validate_worksheet(data, num_questions=10)
        count_errors = [e for e in errors if "count_mismatch" in e]
        assert len(count_errors) == 1


# ── Fix 10: Warnings surfaced in API response ───────────────────────────────


class TestWarningsSurfaced:
    """WorksheetGenerationResponse should include warnings when present."""

    def test_response_model_has_warnings_field(self):
        from app.models.worksheet import WorksheetGenerationResponse

        # Verify the field exists and accepts dict
        fields = WorksheetGenerationResponse.model_fields
        assert "warnings" in fields
        assert "verdict" in fields
