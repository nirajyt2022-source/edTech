"""Tests for D-04: Error Pattern Detection — pure helpers only (no DB)."""

import pytest

from app.services.error_pattern_detector import (
    ErrorPattern,
    SkillDiagnostic,
    classify_patterns,
    compute_trend,
    SYSTEMATIC_MIN_OCCURRENCES,
    SYSTEMATIC_MIN_ERROR_RATE,
)


# ---------------------------------------------------------------------------
# classify_patterns tests
# ---------------------------------------------------------------------------


class TestClassifyPatterns:
    def test_empty_attempts(self):
        assert classify_patterns([]) == []

    def test_all_correct_no_patterns(self):
        attempts = [
            {"is_correct": True, "misconception_id": None, "skill_tag": "add"},
            {"is_correct": True, "misconception_id": None, "skill_tag": "add"},
        ]
        assert classify_patterns(attempts) == []

    def test_single_error_not_systematic(self):
        attempts = [
            {"is_correct": False, "misconception_id": "ADD_NO_CARRY", "skill_tag": "add"},
            {"is_correct": True, "misconception_id": None, "skill_tag": "add"},
        ]
        patterns = classify_patterns(attempts)
        assert len(patterns) == 1
        assert patterns[0].misconception_id == "ADD_NO_CARRY"
        assert patterns[0].is_systematic is False

    def test_systematic_error_detected(self):
        """3+ occurrences of same misconception with ≥50% error rate → systematic."""
        attempts = [
            {"is_correct": False, "misconception_id": "ADD_NO_CARRY", "skill_tag": "column_add"},
            {"is_correct": False, "misconception_id": "ADD_NO_CARRY", "skill_tag": "column_add"},
            {"is_correct": False, "misconception_id": "ADD_NO_CARRY", "skill_tag": "column_add"},
            {"is_correct": True, "misconception_id": None, "skill_tag": "column_add"},
        ]
        patterns = classify_patterns(attempts)
        assert len(patterns) == 1
        p = patterns[0]
        assert p.misconception_id == "ADD_NO_CARRY"
        assert p.occurrences == 3
        assert p.is_systematic is True
        assert "column_add" in p.affected_skill_tags

    def test_multiple_misconceptions_sorted_by_occurrences(self):
        attempts = [
            {"is_correct": False, "misconception_id": "ADD_NO_CARRY", "skill_tag": "add"},
            {"is_correct": False, "misconception_id": "SUB_NO_BORROW", "skill_tag": "sub"},
            {"is_correct": False, "misconception_id": "SUB_NO_BORROW", "skill_tag": "sub"},
        ]
        patterns = classify_patterns(attempts)
        assert len(patterns) == 2
        assert patterns[0].misconception_id == "SUB_NO_BORROW"
        assert patterns[0].occurrences == 2
        assert patterns[1].misconception_id == "ADD_NO_CARRY"
        assert patterns[1].occurrences == 1

    def test_unknown_fallback_for_missing_misconception(self):
        attempts = [
            {"is_correct": False, "misconception_id": None, "skill_tag": "add"},
        ]
        patterns = classify_patterns(attempts)
        assert len(patterns) == 1
        assert patterns[0].misconception_id == "UNKNOWN"

    def test_affected_skill_tags_collected(self):
        attempts = [
            {"is_correct": False, "misconception_id": "ADD_NO_CARRY", "skill_tag": "column_add"},
            {"is_correct": False, "misconception_id": "ADD_NO_CARRY", "skill_tag": "addition_word_problem"},
            {"is_correct": False, "misconception_id": "ADD_NO_CARRY", "skill_tag": "column_add"},
        ]
        patterns = classify_patterns(attempts)
        assert len(patterns) == 1
        assert set(patterns[0].affected_skill_tags) == {"column_add", "addition_word_problem"}


# ---------------------------------------------------------------------------
# compute_trend tests
# ---------------------------------------------------------------------------


class TestComputeTrend:
    def test_insufficient_data_stable(self):
        attempts = [{"is_correct": True}] * 5
        assert compute_trend(attempts, window=5) == "stable"

    def test_improving_trend(self):
        # Previous 5: 20% correct; Recent 5: 80% correct → improving
        attempts = (
            [{"is_correct": False}] * 4 + [{"is_correct": True}] * 1  # prev: 20%
            + [{"is_correct": True}] * 4 + [{"is_correct": False}] * 1  # recent: 80%
        )
        assert compute_trend(attempts, window=5) == "improving"

    def test_declining_trend(self):
        # Previous 5: 80% correct; Recent 5: 20% correct → declining
        attempts = (
            [{"is_correct": True}] * 4 + [{"is_correct": False}] * 1  # prev: 80%
            + [{"is_correct": False}] * 4 + [{"is_correct": True}] * 1  # recent: 20%
        )
        assert compute_trend(attempts, window=5) == "declining"

    def test_stable_trend(self):
        # Both windows ~60% → stable
        attempts = (
            [{"is_correct": True}] * 3 + [{"is_correct": False}] * 2
            + [{"is_correct": True}] * 3 + [{"is_correct": False}] * 2
        )
        assert compute_trend(attempts, window=5) == "stable"


# ---------------------------------------------------------------------------
# Data class tests
# ---------------------------------------------------------------------------


class TestDataClasses:
    def test_error_pattern_defaults(self):
        p = ErrorPattern(
            misconception_id="ADD_NO_CARRY",
            misconception_display="Forgets carry",
            domain="addition",
            occurrences=3,
            total_attempts=10,
            error_rate=0.5,
            is_systematic=True,
        )
        assert p.affected_skill_tags == []

    def test_skill_diagnostic_defaults(self):
        d = SkillDiagnostic(
            skill_tag="add",
            total_attempts=0,
            correct_count=0,
            accuracy=0.0,
            trend="stable",
        )
        assert d.top_misconceptions == []
