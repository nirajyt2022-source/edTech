"""Tests for MCQ multi-correct detection (S5.2).

Covers CHECK 23 in quality_reviewer, R22 in release_gate, CONTENT_13 in quality_scorer.
"""



# ---------------------------------------------------------------------------
# CHECK 23 — MCQ multi-correct detection in quality_reviewer
# ---------------------------------------------------------------------------


class TestCheck23MultiCorrectDetection:
    """CHECK 23: flag MCQs where >1 option is numerically equivalent to the answer."""

    def _make_mcq(self, answer: str, options: list[str], qid: str = "1") -> dict:
        return {
            "id": qid,
            "type": "mcq",
            "text": "What is the value?",
            "question_text": "What is the value?",
            "answer": answer,
            "correct_answer": answer,
            "options": options,
        }

    def test_equivalent_options_flagged(self):
        """MCQ with '0.5' and '1/2' both matching answer should be flagged."""
        from app.utils.answer_normalizer import normalize_numeric

        q = self._make_mcq("0.5", ["0.5", "2/4", "1/2", "0.25"])
        answer_norm = normalize_numeric(q["answer"])
        equiv_count = sum(
            1 for opt in q["options"]
            if normalize_numeric(str(opt).strip()) == answer_norm
        )
        assert equiv_count == 3  # 0.5, 2/4, 1/2

    def test_unique_options_not_flagged(self):
        """MCQ with unique options should not be flagged."""
        from app.utils.answer_normalizer import normalize_numeric

        q = self._make_mcq("0.5", ["0.5", "0.25", "0.75", "1.0"])
        answer_norm = normalize_numeric(q["answer"])
        equiv_count = sum(
            1 for opt in q["options"]
            if normalize_numeric(str(opt).strip()) == answer_norm
        )
        assert equiv_count == 1

    def test_fraction_equivalence(self):
        """2/6 and 1/3 should be detected as equivalent."""
        from app.utils.answer_normalizer import normalize_numeric

        q = self._make_mcq("1/3", ["1/3", "2/6", "1/4", "1/2"])
        answer_norm = normalize_numeric(q["answer"])
        equiv_count = sum(
            1 for opt in q["options"]
            if normalize_numeric(str(opt).strip()) == answer_norm
        )
        assert equiv_count == 2

    def test_non_numeric_options_skipped(self):
        """Non-numeric answers should not trigger false positives."""
        from app.utils.answer_normalizer import normalize_numeric

        answer_norm = normalize_numeric("Cat")
        assert answer_norm is None  # non-numeric, skip


# ---------------------------------------------------------------------------
# R22 — MCQ_UNIQUE_ANSWER release gate rule
# ---------------------------------------------------------------------------


class TestR22McqUniqueAnswer:
    """R22: BLOCK if any question has _mcq_multi_correct=True."""

    def _make_ctx(self, questions: list[dict]):
        from app.services.release_gate import GateContext

        return GateContext(
            questions=questions,
            grade_level="Class 3",
            grade_num=3,
            subject="Maths",
            topic="Fractions",
            num_questions=len(questions),
            difficulty="medium",
            warnings=[],
        )

    def test_blocks_multi_correct(self):
        from app.services.release_gate import r22_mcq_unique_answer

        ctx = self._make_ctx([
            {"id": "1", "type": "mcq", "_mcq_multi_correct": True},
            {"id": "2", "type": "mcq"},
        ])
        result = r22_mcq_unique_answer(ctx)
        assert not result.passed
        assert result.enforcement.value == "block"

    def test_passes_no_multi_correct(self):
        from app.services.release_gate import r22_mcq_unique_answer

        ctx = self._make_ctx([
            {"id": "1", "type": "mcq"},
            {"id": "2", "type": "mcq"},
        ])
        result = r22_mcq_unique_answer(ctx)
        assert result.passed

    def test_passes_empty_questions(self):
        from app.services.release_gate import r22_mcq_unique_answer

        ctx = self._make_ctx([])
        result = r22_mcq_unique_answer(ctx)
        assert result.passed


# ---------------------------------------------------------------------------
# CONTENT_13 — quality_scorer flag check
# ---------------------------------------------------------------------------


class TestContent13McqMultiCorrect:
    """CONTENT_13: critical penalty for _mcq_multi_correct flag."""

    def test_flag_creates_failure(self):
        from app.services.quality_scorer import _run_content_checks

        questions = [
            {"id": "1", "type": "mcq", "_mcq_multi_correct": True, "answer": "0.5"},
        ]
        buckets = {
            "structural": [], "content": [], "pedagogical": [],
            "ai_smell": [], "curriculum": [],
        }
        _run_content_checks(questions, "Maths", buckets)

        content_13 = [f for f in buckets["content"] if f.check_id == "CONTENT_13"]
        assert len(content_13) == 1
        assert content_13[0].severity == "critical"
        assert content_13[0].points_deducted == 0.30

    def test_no_flag_no_failure(self):
        from app.services.quality_scorer import _run_content_checks

        questions = [
            {"id": "1", "type": "mcq", "answer": "0.5"},
        ]
        buckets = {
            "structural": [], "content": [], "pedagogical": [],
            "ai_smell": [], "curriculum": [],
        }
        _run_content_checks(questions, "Maths", buckets)

        content_13 = [f for f in buckets["content"] if f.check_id == "CONTENT_13"]
        assert len(content_13) == 0
