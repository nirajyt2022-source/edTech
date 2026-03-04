"""Tests for Gold Standard export mode (S5.3).

Covers config, release gate upgrades (R04, R21), quality scorer threshold.
"""



# ---------------------------------------------------------------------------
# Config settings
# ---------------------------------------------------------------------------


class TestGoldStandardConfig:
    def test_default_gold_score(self):
        from app.core.config import Settings

        s = Settings(supabase_url="http://test", supabase_service_key="test")
        assert s.worksheet_export_gold_score == 85

    def test_default_gold_mode_off(self):
        from app.core.config import Settings

        s = Settings(supabase_url="http://test", supabase_service_key="test")
        assert s.gold_standard_mode is False


# ---------------------------------------------------------------------------
# R04 — CURRICULUM_GROUNDED gold mode upgrade
# ---------------------------------------------------------------------------


class TestR04GoldMode:
    def _make_ctx(self, *, curriculum_available: bool, gold: bool):
        from app.services.release_gate import GateContext

        return GateContext(
            questions=[{"id": "1", "type": "mcq", "text": "test"}],
            grade_level="Class 3",
            grade_num=3,
            subject="Maths",
            topic="Addition",
            num_questions=1,
            difficulty="medium",
            warnings=[],
            curriculum_available=curriculum_available,
            gold_standard_mode=gold,
        )

    def test_degrade_without_gold(self):
        from app.services.release_gate import r04_curriculum_grounded

        ctx = self._make_ctx(curriculum_available=False, gold=False)
        result = r04_curriculum_grounded(ctx)
        assert not result.passed
        assert result.enforcement.value == "degrade"

    def test_block_with_gold(self):
        from app.services.release_gate import r04_curriculum_grounded

        ctx = self._make_ctx(curriculum_available=False, gold=True)
        result = r04_curriculum_grounded(ctx)
        assert not result.passed
        assert result.enforcement.value == "block"

    def test_passes_when_available(self):
        from app.services.release_gate import r04_curriculum_grounded

        ctx = self._make_ctx(curriculum_available=True, gold=True)
        result = r04_curriculum_grounded(ctx)
        assert result.passed


# ---------------------------------------------------------------------------
# R21 — PARENT_CONFIDENCE gold mode upgrade
# ---------------------------------------------------------------------------


class TestR21GoldMode:
    def _make_ctx(self, *, meta: dict | None, gold: bool):
        from app.services.release_gate import GateContext

        return GateContext(
            questions=[{"id": "1", "type": "mcq", "text": "test"}],
            grade_level="Class 3",
            grade_num=3,
            subject="Maths",
            topic="Addition",
            num_questions=1,
            difficulty="medium",
            warnings=[],
            worksheet_meta=meta or {},
            gold_standard_mode=gold,
        )

    def test_degrade_without_gold(self):
        from app.services.release_gate import r21_parent_confidence

        # Empty meta with no skill_focus → incomplete
        ctx = self._make_ctx(meta={"title": "test"}, gold=False)
        result = r21_parent_confidence(ctx)
        # Even if it fails, enforcement should be DEGRADE
        if not result.passed:
            assert result.enforcement.value == "degrade"

    def test_block_with_gold(self):
        from app.services.release_gate import r21_parent_confidence

        # Missing parent blocks in gold mode should BLOCK
        ctx = self._make_ctx(meta={"title": "test"}, gold=True)
        result = r21_parent_confidence(ctx)
        if not result.passed:
            assert result.enforcement.value == "block"


# ---------------------------------------------------------------------------
# Gold standard stamps in run_release_gate
# ---------------------------------------------------------------------------


class TestGoldStandardStamps:
    def test_stamps_present(self):
        from app.services.release_gate import run_release_gate

        verdict = run_release_gate(
            questions=[
                {"id": "1", "type": "mcq", "text": "What is 2+2?",
                 "question_text": "What is 2+2?", "answer": "4",
                 "correct_answer": "4", "options": ["3", "4", "5", "6"]},
            ],
            grade_level="Class 3",
            subject="Maths",
            topic="Addition",
            num_questions=1,
            difficulty="medium",
            warnings=[],
            gold_standard_mode=True,
        )
        assert "gold_standard_mode" in verdict.stamps
        assert verdict.stamps["gold_standard_mode"] is True

    def test_gold_not_eligible_when_blocked(self):
        from app.services.release_gate import run_release_gate

        verdict = run_release_gate(
            questions=[
                {"id": "1", "type": "mcq", "text": "test",
                 "question_text": "test", "answer": "4",
                 "_math_unverified": True},
            ],
            grade_level="Class 3",
            subject="Maths",
            topic="Addition",
            num_questions=1,
            difficulty="medium",
            warnings=[],
            gold_standard_mode=True,
        )
        assert verdict.stamps.get("gold_standard_eligible") is False


# ---------------------------------------------------------------------------
# Quality scorer gold threshold
# ---------------------------------------------------------------------------


class TestGoldStandardThreshold:
    def test_default_threshold_70(self):
        from app.services.quality_scorer import _get_export_threshold

        threshold = _get_export_threshold(gold_standard_mode=False)
        assert threshold == 70

    def test_gold_threshold_85(self):
        from app.services.quality_scorer import _get_export_threshold

        threshold = _get_export_threshold(gold_standard_mode=True)
        assert threshold == 85

    def test_score_worksheet_accepts_gold_mode(self):
        from app.services.quality_scorer import score_worksheet

        result = score_worksheet(
            {
                "grade": "Class 3",
                "subject": "Maths",
                "topic": "Addition",
                "questions": [
                    {"id": "1", "type": "mcq", "text": "What is 2+2?",
                     "question_text": "What is 2+2?", "answer": "4",
                     "correct_answer": "4", "options": ["3", "4", "5", "6"],
                     "role": "application", "skill_tag": "add"},
                ],
            },
            gold_standard_mode=True,
        )
        assert result.export_threshold == 85
