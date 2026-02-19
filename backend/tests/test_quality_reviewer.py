"""
Tests for QualityReviewerAgent.

All tests run fully offline — no Supabase or LLM calls required.
Uses a minimal GenerationContext (Maths, Grade 3) for all test cases.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.quality_reviewer import (
    QualityReviewerAgent,
    ReviewResult,
    get_quality_reviewer,
    _safe_eval,
    _extract_simple_arithmetic,
    _answers_match,
)
from app.services.topic_intelligence import GenerationContext

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DEFAULT_CTX = GenerationContext(
    topic_slug="Addition (carries)",
    subject="Maths",
    grade=3,
    ncert_chapter="Addition (carries)",
    ncert_subtopics=["obj1", "obj2"],
    bloom_level="recall",
    format_mix={"mcq": 40, "fill_blank": 30, "word_problem": 30},
    scaffolding=True,
    challenge_mode=False,
    valid_skill_tags=["column_add_with_carry", "addition_word_problem"],
    child_context={},
)


def _make_q(
    q_id=1,
    slot_type="recognition",
    question_text="What is 5 + 7?",
    answer="12",
    skill_tag="column_add_with_carry",
):
    return {
        "id": q_id,
        "slot_type": slot_type,
        "question_text": question_text,
        "answer": answer,
        "skill_tag": skill_tag,
        "difficulty": "easy",
    }


# ---------------------------------------------------------------------------
# _safe_eval
# ---------------------------------------------------------------------------

class TestSafeEval:
    def test_simple_addition(self):
        assert _safe_eval("5 + 7") == 12.0

    def test_simple_subtraction(self):
        assert _safe_eval("10 - 3") == 7.0

    def test_multiplication(self):
        assert _safe_eval("6 * 8") == 48.0

    def test_floor_division(self):
        assert _safe_eval("20 // 4") == 5.0

    def test_modulo(self):
        assert _safe_eval("17 % 5") == 2.0

    def test_nested_expression(self):
        result = _safe_eval("2 + 3")
        assert result == 5.0

    def test_division_by_zero_returns_none(self):
        assert _safe_eval("10 / 0") is None

    def test_variable_returns_none(self):
        assert _safe_eval("x + 5") is None

    def test_function_call_returns_none(self):
        assert _safe_eval("print(5)") is None

    def test_invalid_syntax_returns_none(self):
        assert _safe_eval("5 +* 3") is None

    def test_empty_string_returns_none(self):
        assert _safe_eval("") is None


# ---------------------------------------------------------------------------
# _extract_simple_arithmetic
# ---------------------------------------------------------------------------

class TestExtractSimpleArithmetic:
    def test_simple_addition_extracted(self):
        result = _extract_simple_arithmetic("What is 5 + 7?")
        assert result is not None
        expr, computed = result
        assert computed == 12.0

    def test_subtraction_extracted(self):
        result = _extract_simple_arithmetic("Calculate 15 - 8 =")
        assert result is not None
        _, computed = result
        assert computed == 7.0

    def test_multiplication_extracted(self):
        result = _extract_simple_arithmetic("Find 6 × 4")
        assert result is not None
        _, computed = result
        assert computed == 24.0

    def test_word_problem_skipped(self):
        # narrative words → skip
        result = _extract_simple_arithmetic("Riya had 5 apples and bought 7 more.")
        assert result is None

    def test_blank_marker_skipped(self):
        # blank markers → skip
        result = _extract_simple_arithmetic("5 + __ = 12")
        assert result is None

    def test_no_arithmetic_returns_none(self):
        result = _extract_simple_arithmetic("What is the capital of France?")
        assert result is None


# ---------------------------------------------------------------------------
# _answers_match
# ---------------------------------------------------------------------------

class TestAnswersMatch:
    def test_correct_integer(self):
        assert _answers_match("12", 12.0) is True

    def test_wrong_integer(self):
        assert _answers_match("11", 12.0) is False

    def test_float_tolerance(self):
        assert _answers_match("3.33", 10.0 / 3.0) is True

    def test_non_numeric_answer_passes(self):
        # Non-numeric stored answers are not our job to correct
        assert _answers_match("twelve", 12.0) is True

    def test_answer_with_comma(self):
        assert _answers_match("1,000", 1000.0) is True


# ---------------------------------------------------------------------------
# CHECK 1: Arithmetic correction
# ---------------------------------------------------------------------------

class TestCheck1ArithmeticCorrection:
    def test_wrong_answer_corrected(self):
        """'5 + 7 = 11' should be corrected to '12'."""
        reviewer = QualityReviewerAgent()
        q = _make_q(question_text="What is 5 + 7?", answer="11")
        result = reviewer.review_worksheet([q], _DEFAULT_CTX)

        assert len(result.corrections) == 1
        assert result.questions[0]["answer"] == "12"
        assert result.questions[0].get("_answer_corrected") is True

    def test_correct_answer_untouched(self):
        """A correct answer must pass through unchanged."""
        reviewer = QualityReviewerAgent()
        q = _make_q(question_text="What is 5 + 7?", answer="12")
        result = reviewer.review_worksheet([q], _DEFAULT_CTX)

        assert len(result.corrections) == 0
        assert result.questions[0]["answer"] == "12"
        assert result.questions[0].get("_answer_corrected") is None

    def test_error_detection_slot_skipped(self):
        """CHECK 1 skips error_detection, but CHECK 4 corrects the stored answer
        to the true computed value ('answer' must be the correct answer; the wrong
        value shown in the question lives in 'student_wrong_answer')."""
        reviewer = QualityReviewerAgent()
        q = _make_q(
            slot_type="error_detection",
            question_text="Spot the error: 5 + 7 = 11",
            answer="11",  # LLM agreed with the wrong value — CHECK 4 fixes this
        )
        result = reviewer.review_worksheet([q], _DEFAULT_CTX)

        # CHECK 4 corrects the stored answer to the real computed value
        assert len(result.corrections) == 1
        assert result.questions[0]["answer"] == "12"

    def test_word_problem_not_corrected(self):
        """Word problems (narrative words) are skipped by CHECK 1."""
        reviewer = QualityReviewerAgent()
        q = _make_q(
            question_text="Riya had 5 apples and bought 7 more. How many does she have?",
            answer="wrong",  # non-numeric — passes as non-correctable
        )
        result = reviewer.review_worksheet([q], _DEFAULT_CTX)
        # Extraction skipped → no correction
        assert len(result.corrections) == 0

    def test_non_maths_subject_check1_skipped(self):
        """CHECK 1 is Maths-only. English subjects must not have arithmetic correction."""
        from app.services.topic_intelligence import GenerationContext
        english_ctx = GenerationContext(
            topic_slug="Nouns (Class 3)",
            subject="English",
            grade=3,
            ncert_chapter="Nouns (Class 3)",
            ncert_subtopics=[],
            bloom_level="recall",
            format_mix={},
            scaffolding=True,
            challenge_mode=False,
            valid_skill_tags=["eng_identify_noun"],
            child_context={},
        )
        reviewer = QualityReviewerAgent()
        q = _make_q(
            question_text="What is 5 + 7?",
            answer="wrong_answer",
            skill_tag="eng_identify_noun",
        )
        result = reviewer.review_worksheet([q], english_ctx)
        # No arithmetic correction for English
        assert len(result.corrections) == 0


# ---------------------------------------------------------------------------
# CHECK 2: Skill tag validation
# ---------------------------------------------------------------------------

class TestCheck2SkillTagValidation:
    def test_invalid_skill_tag_replaced(self):
        """An invalid skill_tag must be replaced with valid_skill_tags[0]."""
        reviewer = QualityReviewerAgent()
        q = _make_q(skill_tag="totally_invalid_tag_xyz")
        result = reviewer.review_worksheet([q], _DEFAULT_CTX)

        assert len(result.errors) == 1
        assert result.questions[0]["skill_tag"] == _DEFAULT_CTX.valid_skill_tags[0]

    def test_valid_skill_tag_preserved(self):
        """A tag already in valid_skill_tags must not be touched."""
        reviewer = QualityReviewerAgent()
        q = _make_q(skill_tag="addition_word_problem")
        result = reviewer.review_worksheet([q], _DEFAULT_CTX)

        assert len(result.errors) == 0
        assert result.questions[0]["skill_tag"] == "addition_word_problem"

    def test_empty_valid_skill_tags_skips_check(self):
        """When valid_skill_tags is empty (unknown topic), CHECK 2 must be skipped."""
        from app.services.topic_intelligence import GenerationContext
        ctx_no_tags = GenerationContext(
            topic_slug="Unknown Topic",
            subject="Maths",
            grade=3,
            ncert_chapter="Unknown Topic",
            ncert_subtopics=[],
            bloom_level="recall",
            format_mix={},
            scaffolding=True,
            challenge_mode=False,
            valid_skill_tags=[],   # empty — no constraint
            child_context={},
        )
        reviewer = QualityReviewerAgent()
        q = _make_q(skill_tag="any_weird_tag")
        result = reviewer.review_worksheet([q], ctx_no_tags)
        # No errors: empty valid_skill_tags → no constraint enforced
        assert len(result.errors) == 0
        assert result.questions[0]["skill_tag"] == "any_weird_tag"


# ---------------------------------------------------------------------------
# CHECK 3: Grade-level word count
# ---------------------------------------------------------------------------

class TestCheck3WordCount:
    def _ctx_grade(self, grade: int):
        return GenerationContext(
            topic_slug="Some Topic",
            subject="Maths",
            grade=grade,
            ncert_chapter="Some Topic",
            ncert_subtopics=[],
            bloom_level="recall",
            format_mix={},
            scaffolding=True,
            challenge_mode=False,
            valid_skill_tags=["column_add_with_carry"],
            child_context={},
        )

    def test_grade1_long_question_flagged(self):
        """Grade 1 question with >15 words should be flagged as a warning."""
        reviewer = QualityReviewerAgent()
        long_q = "What " * 16 + "?"   # 17 words
        q = _make_q(question_text=long_q, skill_tag="column_add_with_carry")
        result = reviewer.review_worksheet([q], self._ctx_grade(1))

        assert len(result.warnings) == 1

    def test_grade1_short_question_passes(self):
        """Grade 1 question with ≤15 words must not produce a warning."""
        reviewer = QualityReviewerAgent()
        q = _make_q(question_text="What is 5 + 7?", skill_tag="column_add_with_carry")
        result = reviewer.review_worksheet([q], self._ctx_grade(1))
        assert len(result.warnings) == 0

    def test_grade3_limit_is_25_words(self):
        """Grade 3 question with >25 words should be flagged."""
        reviewer = QualityReviewerAgent()
        long_q = "word " * 26   # 26 words
        q = _make_q(question_text=long_q, skill_tag="column_add_with_carry")
        result = reviewer.review_worksheet([q], self._ctx_grade(3))

        assert len(result.warnings) == 1

    def test_warning_does_not_alter_question_text(self):
        """Word-count warning must be logged only — text must never be changed."""
        reviewer = QualityReviewerAgent()
        long_q = "word " * 30
        q = _make_q(question_text=long_q, skill_tag="column_add_with_carry")
        result = reviewer.review_worksheet([q], self._ctx_grade(1))

        assert result.questions[0]["question_text"] == long_q


# ---------------------------------------------------------------------------
# ReviewResult structure
# ---------------------------------------------------------------------------

class TestReviewResult:
    def test_returns_review_result(self):
        reviewer = QualityReviewerAgent()
        result = reviewer.review_worksheet([], _DEFAULT_CTX)
        assert isinstance(result, ReviewResult)

    def test_empty_input_no_crash(self):
        reviewer = QualityReviewerAgent()
        result = reviewer.review_worksheet([], _DEFAULT_CTX)
        assert result.questions == []
        assert result.corrections == []
        assert result.warnings == []
        assert result.errors == []

    def test_multiple_questions(self):
        """Multiple questions all pass through the review loop."""
        reviewer = QualityReviewerAgent()
        questions = [
            _make_q(q_id=1, question_text="What is 3 + 4?", answer="7"),
            _make_q(q_id=2, question_text="What is 5 + 6?", answer="99"),  # wrong
        ]
        result = reviewer.review_worksheet(questions, _DEFAULT_CTX)
        assert len(result.questions) == 2
        assert len(result.corrections) == 1
        assert result.questions[1]["answer"] == "11"


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

class TestSingleton:
    def test_get_quality_reviewer_same_instance(self):
        r1 = get_quality_reviewer()
        r2 = get_quality_reviewer()
        assert r1 is r2

    def test_get_quality_reviewer_is_correct_type(self):
        assert isinstance(get_quality_reviewer(), QualityReviewerAgent)
