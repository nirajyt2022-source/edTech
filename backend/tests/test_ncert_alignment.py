"""Tests for NcertAlignmentService — deterministic NCERT alignment layer."""

from __future__ import annotations

from app.data.ncert_question_type_map import FORMAT_TO_NCERT_TYPE, NCERT_QUESTION_TYPES, ROLE_TO_NCERT_TYPE
from app.services.ncert_alignment import NcertAlignmentService


def _make_question(fmt: str = "short_answer", role: str = "recognition", **kwargs) -> dict:
    return {"format": fmt, "role": role, "text": "Test question", **kwargs}


class TestAlignWorksheet:
    """Integration tests for align_worksheet."""

    def test_known_topic_populates_all_fields(self):
        questions = [_make_question("column_setup", "application")]
        result = NcertAlignmentService.align_worksheet(
            questions, grade="Class 3", subject="Maths", topic="Addition (carries)",
            learning_objectives=["Recognize carry", "Apply carry in addition", "Reason about carry"],
        )
        a = result[0]["ncert_alignment"]
        assert a is not None
        assert a["chapter_number"] == 2
        assert a["exercise_id"] == "2.1"
        assert a["ncert_question_type"] == "computation"
        assert a["page_ref"] == "pp. 17-26"
        assert a["learning_objective"] == "Apply carry in addition"  # index 1 for application

    def test_unknown_topic_returns_none(self):
        questions = [_make_question()]
        result = NcertAlignmentService.align_worksheet(
            questions, grade="Class 9", subject="Maths", topic="Calculus",
        )
        assert result[0].get("ncert_alignment") is None

    def test_grade_normalization(self):
        """Grade '3' should normalize to 'Class 3'."""
        questions = [_make_question("word_problem", "application")]
        result = NcertAlignmentService.align_worksheet(
            questions, grade="3", subject="Maths", topic="Addition (carries)",
        )
        assert result[0]["ncert_alignment"] is not None
        assert result[0]["ncert_alignment"]["chapter_number"] == 2

    def test_fail_open_on_missing_alignment(self):
        """Questions for unknown topics should pass through unchanged."""
        questions = [_make_question()]
        original_text = questions[0]["text"]
        result = NcertAlignmentService.align_worksheet(
            questions, grade="Class 99", subject="Alien", topic="Teleportation",
        )
        assert result[0]["text"] == original_text
        assert "ncert_alignment" not in result[0]


class TestFormatMapping:
    """Tests for format → NCERT type resolution."""

    def test_word_problem_maps_correctly(self):
        questions = [_make_question("word_problem", "application")]
        result = NcertAlignmentService.align_worksheet(
            questions, grade="Class 3", subject="Maths", topic="Addition (carries)",
            learning_objectives=["LO1"],
        )
        assert result[0]["ncert_alignment"]["ncert_question_type"] == "word_problem"

    def test_mcq4_maps_to_mcq(self):
        questions = [_make_question("mcq_4", "recognition")]
        result = NcertAlignmentService.align_worksheet(
            questions, grade="Class 1", subject="Maths", topic="Addition up to 20",
        )
        a = result[0]["ncert_alignment"]
        assert a["ncert_question_type"] == "mcq"

    def test_error_spot_maps_to_error_detection(self):
        questions = [_make_question("error_spot", "error_detection")]
        result = NcertAlignmentService.align_worksheet(
            questions, grade="Class 1", subject="Maths", topic="Addition up to 20",
        )
        assert result[0]["ncert_alignment"]["ncert_question_type"] == "error_detection"

    def test_role_fallback_when_format_generic(self):
        """short_answer format + application role → word_problem via ROLE_TO_NCERT_TYPE."""
        questions = [_make_question("short_answer", "application")]
        result = NcertAlignmentService.align_worksheet(
            questions, grade="Class 3", subject="Maths", topic="Addition (carries)",
        )
        assert result[0]["ncert_alignment"]["ncert_question_type"] == "word_problem"


class TestExerciseMatching:
    """Tests for exercise matching logic."""

    def test_exercise_matched_by_question_type(self):
        """Class 3 Addition (3-digit) has exercises 2.1 (computation) and 2.2 (computation)."""
        questions = [_make_question("column_setup", "application")]
        result = NcertAlignmentService.align_worksheet(
            questions, grade="Class 3", subject="Maths", topic="Addition and subtraction (3-digit)",
        )
        a = result[0]["ncert_alignment"]
        # computation matches exercise 2.1 (first match wins)
        assert a["exercise_id"] == "2.1"

    def test_fallback_to_primary_exercise(self):
        """When question type doesn't match any exercise, fallback to primary_exercise."""
        questions = [_make_question("true_false", "recognition")]
        result = NcertAlignmentService.align_worksheet(
            questions, grade="Class 3", subject="Maths", topic="Addition (carries)",
        )
        a = result[0]["ncert_alignment"]
        # true_false doesn't appear in exercise 2.1's types, fallback to primary
        assert a["exercise_id"] == "2.1"


class TestLearningObjective:
    """Tests for learning objective selection by role index."""

    def test_recognition_picks_index_0(self):
        lo = ["Recognize", "Apply", "Think"]
        questions = [_make_question("short_answer", "recognition")]
        result = NcertAlignmentService.align_worksheet(
            questions, grade="Class 1", subject="Maths", topic="Addition up to 20",
            learning_objectives=lo,
        )
        assert result[0]["ncert_alignment"]["learning_objective"] == "Recognize"

    def test_thinking_picks_index_2(self):
        lo = ["Recognize", "Apply", "Think"]
        questions = [_make_question("thinking", "thinking")]
        result = NcertAlignmentService.align_worksheet(
            questions, grade="Class 1", subject="Maths", topic="Addition up to 20",
            learning_objectives=lo,
        )
        assert result[0]["ncert_alignment"]["learning_objective"] == "Think"

    def test_empty_learning_objectives(self):
        questions = [_make_question("thinking", "thinking")]
        result = NcertAlignmentService.align_worksheet(
            questions, grade="Class 1", subject="Maths", topic="Addition up to 20",
            learning_objectives=[],
        )
        assert result[0]["ncert_alignment"]["learning_objective"] is None


class TestQuestionTypeMap:
    """Tests for the static mapping data."""

    def test_all_format_types_are_valid(self):
        for fmt, ncert_type in FORMAT_TO_NCERT_TYPE.items():
            assert ncert_type in NCERT_QUESTION_TYPES, f"{fmt} maps to unknown type {ncert_type}"

    def test_all_role_types_are_valid(self):
        for role, ncert_type in ROLE_TO_NCERT_TYPE.items():
            assert ncert_type in NCERT_QUESTION_TYPES, f"{role} maps to unknown type {ncert_type}"

    def test_taxonomy_has_12_types(self):
        assert len(NCERT_QUESTION_TYPES) == 12
