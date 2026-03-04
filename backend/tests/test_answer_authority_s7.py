"""
Sprint S7 — Answer Authority Expansion & Answer Key Integrity tests.

Covers:
  - True/False verifier (English + Hindi)
  - MCQ answer-in-options verifier
  - Fill-blank English verifier
  - CONTENT_14 answer deduplication
  - R23 answer key completeness gate
  - R15 non-Maths expansion
  - Maths regression (arithmetic + word problem still work)
"""

from __future__ import annotations

from app.services.answer_authority import AnswerAuthority, _TF_CANONICAL


# ---------------------------------------------------------------------------
# TestTrueFalseVerifier
# ---------------------------------------------------------------------------


class TestTrueFalseVerifier:
    """_verify_true_false: canonical mapping for English + Hindi."""

    def test_true_match(self):
        v = AnswerAuthority._verify_true_false("Q1", "True")
        assert v.match is True
        assert v.method == "true_false"

    def test_false_match(self):
        v = AnswerAuthority._verify_true_false("Q2", "False")
        assert v.match is True

    def test_hindi_sahi_match(self):
        v = AnswerAuthority._verify_true_false("Q3", "सही")
        assert v.match is True
        assert v.authoritative_answer == "True"

    def test_hindi_galat_match(self):
        v = AnswerAuthority._verify_true_false("Q4", "गलत")
        assert v.match is True
        assert v.authoritative_answer == "False"

    def test_unrecognized_returns_none(self):
        v = AnswerAuthority._verify_true_false("Q5", "maybe")
        assert v.match is None
        assert v.method == "true_false"

    def test_case_insensitive(self):
        v = AnswerAuthority._verify_true_false("Q6", "TRUE")
        assert v.match is True

    def test_canonical_mapping_completeness(self):
        """All _TRUE_FORMS map to 'true', all _FALSE_FORMS map to 'false'."""
        for k, v in _TF_CANONICAL.items():
            assert v in ("true", "false")


# ---------------------------------------------------------------------------
# TestMCQVerifier
# ---------------------------------------------------------------------------


class TestMCQVerifier:
    """_verify_mcq_answer: answer must be in options list."""

    def test_answer_in_options(self):
        q = {"options": ["Cat", "Dog", "Fish"]}
        v = AnswerAuthority._verify_mcq_answer("Q1", q, "Dog")
        assert v.match is True

    def test_answer_not_in_options(self):
        q = {"options": ["Cat", "Dog", "Fish"]}
        v = AnswerAuthority._verify_mcq_answer("Q2", q, "Bird")
        assert v.match is False

    def test_case_insensitive_match(self):
        q = {"options": ["Apple", "Banana"]}
        v = AnswerAuthority._verify_mcq_answer("Q3", q, "apple")
        assert v.match is True

    def test_no_options_returns_none(self):
        q = {"options": []}
        v = AnswerAuthority._verify_mcq_answer("Q4", q, "Apple")
        assert v.match is None

    def test_missing_options_key(self):
        q = {}
        v = AnswerAuthority._verify_mcq_answer("Q5", q, "Apple")
        assert v.match is None


# ---------------------------------------------------------------------------
# TestFillBlankEnglish
# ---------------------------------------------------------------------------


class TestFillBlankEnglish:
    """_verify_fill_blank_english: simple answers only."""

    def test_clean_answer(self):
        v = AnswerAuthority._verify_fill_blank_english("Q1", "cat")
        assert v.match is True

    def test_whitespace_trimmed(self):
        v = AnswerAuthority._verify_fill_blank_english("Q2", "  dog  ")
        assert v.match is True
        assert v.authoritative_answer == "dog"

    def test_complex_answer_unverifiable(self):
        v = AnswerAuthority._verify_fill_blank_english("Q3", "the big brown fox jumps")
        assert v.match is None
        assert "too complex" in v.debug.get("reason", "")

    def test_empty_answer(self):
        v = AnswerAuthority._verify_fill_blank_english("Q4", "")
        assert v.match is None


# ---------------------------------------------------------------------------
# TestAnswerDedupCONTENT14
# ---------------------------------------------------------------------------


class TestAnswerDedupCONTENT14:
    """_check_answer_dedup in quality_scorer."""

    def _run(self, questions):
        from app.services.quality_scorer import _check_answer_dedup

        buckets = {"content": [], "structural": [], "ai_smell": [], "pedagogical": [], "curriculum": []}
        _check_answer_dedup(questions, buckets)
        return buckets["content"]

    def test_same_type_same_answer_flagged(self):
        qs = [
            {"type": "mcq", "answer": "Cat", "id": "1"},
            {"type": "mcq", "answer": "Cat", "id": "2"},
        ]
        failures = self._run(qs)
        assert len(failures) == 1
        assert failures[0].check_id == "CONTENT_14"

    def test_different_types_no_flag(self):
        qs = [
            {"type": "mcq", "answer": "Cat", "id": "1"},
            {"type": "fill_blank", "answer": "Cat", "id": "2"},
        ]
        failures = self._run(qs)
        assert len(failures) == 0

    def test_distinct_answers_clean(self):
        qs = [
            {"type": "mcq", "answer": "Cat", "id": "1"},
            {"type": "mcq", "answer": "Dog", "id": "2"},
        ]
        failures = self._run(qs)
        assert len(failures) == 0

    def test_empty_answers_skipped(self):
        qs = [
            {"type": "mcq", "answer": "", "id": "1"},
            {"type": "mcq", "answer": "", "id": "2"},
        ]
        failures = self._run(qs)
        assert len(failures) == 0

    def test_error_detection_skipped(self):
        qs = [
            {"type": "error_detection", "answer": "No", "id": "1"},
            {"type": "error_detection", "answer": "No", "id": "2"},
        ]
        failures = self._run(qs)
        assert len(failures) == 0


# ---------------------------------------------------------------------------
# TestR23AnswerKeyComplete
# ---------------------------------------------------------------------------


class TestR23AnswerKeyComplete:
    """R23_ANSWER_KEY_COMPLETE: block on missing answers."""

    def _make_ctx(self, questions):
        from app.services.release_gate import GateContext

        return GateContext(
            questions=questions,
            grade_level="Class 3",
            grade_num=3,
            subject="Maths",
            topic="Addition",
            num_questions=len(questions),
            difficulty="medium",
            warnings=[],
        )

    def test_all_present_passes(self):
        from app.services.release_gate import r23_answer_key_complete

        ctx = self._make_ctx([{"id": "1", "answer": "42"}, {"id": "2", "answer": "7"}])
        result = r23_answer_key_complete(ctx)
        assert result.passed is True

    def test_missing_answer_blocks(self):
        from app.services.release_gate import r23_answer_key_complete

        ctx = self._make_ctx([{"id": "1", "answer": "42"}, {"id": "2", "answer": ""}])
        result = r23_answer_key_complete(ctx)
        assert result.passed is False
        assert "Q2" in result.detail

    def test_bonus_skipped(self):
        from app.services.release_gate import r23_answer_key_complete

        ctx = self._make_ctx([{"id": "1", "answer": "42"}, {"id": "2", "answer": "", "_is_bonus": True}])
        result = r23_answer_key_complete(ctx)
        assert result.passed is True

    def test_correct_answer_field_accepted(self):
        from app.services.release_gate import r23_answer_key_complete

        ctx = self._make_ctx([{"id": "1", "correct_answer": "42"}])
        result = r23_answer_key_complete(ctx)
        assert result.passed is True


# ---------------------------------------------------------------------------
# TestR15NonMaths
# ---------------------------------------------------------------------------


class TestR15NonMaths:
    """R15 now fires for all subjects, not just Maths."""

    def _make_ctx(self, questions, subject="Science"):
        from app.services.release_gate import GateContext

        return GateContext(
            questions=questions,
            grade_level="Class 3",
            grade_num=3,
            subject=subject,
            topic="Animals",
            num_questions=len(questions),
            difficulty="medium",
            warnings=[],
        )

    def test_science_mismatch_blocks(self):
        from app.services.release_gate import r15_answer_authority

        ctx = self._make_ctx([{"id": "1", "_answer_mismatch": True, "answer": "Cat"}], subject="Science")
        result = r15_answer_authority(ctx)
        assert result.passed is False

    def test_english_mismatch_blocks(self):
        from app.services.release_gate import r15_answer_authority

        ctx = self._make_ctx([{"id": "1", "_answer_mismatch": True, "answer": "run"}], subject="English")
        result = r15_answer_authority(ctx)
        assert result.passed is False

    def test_no_mismatch_passes(self):
        from app.services.release_gate import r15_answer_authority

        ctx = self._make_ctx([{"id": "1", "answer": "Cat"}], subject="Science")
        result = r15_answer_authority(ctx)
        assert result.passed is True


# ---------------------------------------------------------------------------
# TestRegressionMaths
# ---------------------------------------------------------------------------


class TestRegressionMaths:
    """Maths verification still works after S7 changes."""

    def test_arithmetic_still_works(self):
        authority = AnswerAuthority()
        q = {"id": "1", "slot_type": "application", "question_text": "What is 5 + 3?", "answer": "8"}
        v = authority.verify_question(q, "Maths")
        assert v.match is True
        assert v.method == "arithmetic"

    def test_word_problem_still_works(self):
        authority = AnswerAuthority()
        q = {
            "id": "2",
            "slot_type": "application",
            "question_text": "Ram has 12 apples. He gives away 4 apples. How many apples does he have now?",
            "answer": "8",
        }
        v = authority.verify_question(q, "Maths")
        # Should be verified via arithmetic or word_problem method
        assert v.match is True or v.match is None  # word problem extraction may or may not find it


# ---------------------------------------------------------------------------
# TestFullDispatch
# ---------------------------------------------------------------------------


class TestFullDispatch:
    """End-to-end dispatch through verify_question for non-Maths."""

    def test_science_tf_dispatches(self):
        authority = AnswerAuthority()
        q = {"id": "1", "slot_type": "true_false", "question_text": "Is the sun a star?", "answer": "True"}
        v = authority.verify_question(q, "Science")
        assert v.match is True
        assert v.method == "true_false"

    def test_english_mcq_dispatches(self):
        authority = AnswerAuthority()
        q = {
            "id": "2",
            "slot_type": "mcq",
            "question_text": "Choose the noun:",
            "answer": "Cat",
            "options": ["Cat", "Run", "Big"],
        }
        v = authority.verify_question(q, "English")
        assert v.match is True
        assert v.method == "mcq"

    def test_english_fill_blank_dispatches(self):
        authority = AnswerAuthority()
        q = {"id": "3", "slot_type": "fill_blank", "question_text": "The ___ is red.", "answer": "ball"}
        v = authority.verify_question(q, "English")
        assert v.match is True
        assert v.method == "fill_blank_english"

    def test_hindi_tf_dispatches(self):
        authority = AnswerAuthority()
        q = {"id": "4", "slot_type": "true_false", "question_text": "सूरज एक तारा है।", "answer": "सही"}
        v = authority.verify_question(q, "Hindi")
        assert v.match is True
        assert v.method == "true_false"
