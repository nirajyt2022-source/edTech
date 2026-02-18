"""
Tests for the pure mastery-transition logic in learning_graph.py.
No Supabase connection required — all tests run fully offline.
"""
import sys
import os

# Ensure the backend/ directory is on the path when running from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from app.services.learning_graph import (
    _compute_mastery_transition,
    _find_weakest_format,
    _build_format_mix,
    _apply_decay,
    MASTERY_ORDER,
)
from datetime import datetime, timezone, timedelta


# ---------------------------------------------------------------------------
# _compute_mastery_transition — the 5 required cases
# ---------------------------------------------------------------------------

class TestRequiredCases:
    """The 5 cases explicitly required by the spec."""

    def test_unknown_one_correct_becomes_learning(self):
        """unknown + 1 correct (score >= 70) → learning"""
        level, streak = _compute_mastery_transition("unknown", 0, 80)
        assert level == "learning"
        assert streak == 1

    def test_learning_three_correct_becomes_improving(self):
        """learning + 3 correct in a row → improving"""
        level, streak = "learning", 0
        for i in range(3):
            level, streak = _compute_mastery_transition(level, streak, 80)
        assert level == "improving", f"Expected improving after 3 correct, got {level}"
        assert streak == 3

    def test_improving_five_correct_becomes_mastered(self):
        """improving + 5 correct in a row → mastered"""
        level, streak = "improving", 0
        for i in range(5):
            level, streak = _compute_mastery_transition(level, streak, 80)
        assert level == "mastered", f"Expected mastered after 5 correct, got {level}"
        assert streak == 5

    def test_mastered_wrong_answer_regresses_to_improving(self):
        """mastered + score < 50 → improving"""
        level, streak = _compute_mastery_transition("mastered", 5, 40)
        assert level == "improving"
        assert streak == 0

    def test_score_below_50_always_regresses_one_level(self):
        """score < 50 always regresses one level, regardless of current level."""
        # learning → unknown
        level, streak = _compute_mastery_transition("learning", 2, 40)
        assert level == "unknown"
        assert streak == 0

        # improving → learning
        level, streak = _compute_mastery_transition("improving", 4, 40)
        assert level == "learning"
        assert streak == 0

        # mastered → improving
        level, streak = _compute_mastery_transition("mastered", 5, 40)
        assert level == "improving"
        assert streak == 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_unknown_cannot_regress_below_unknown(self):
        """unknown + score < 50 → stays unknown (floor)."""
        level, streak = _compute_mastery_transition("unknown", 0, 30)
        assert level == "unknown"
        assert streak == 0

    def test_score_between_50_and_70_resets_streak_no_regression(self):
        """50 <= score < 70 resets streak but does NOT regress the level."""
        level, streak = _compute_mastery_transition("improving", 4, 65)
        assert level == "improving"
        assert streak == 0

    def test_learning_needs_exactly_three_not_two(self):
        """2 correct sessions at learning level should NOT trigger improving."""
        level, streak = "learning", 0
        for _ in range(2):
            level, streak = _compute_mastery_transition(level, streak, 80)
        assert level == "learning"
        assert streak == 2

    def test_improving_needs_exactly_five_not_four(self):
        """4 correct sessions at improving level should NOT trigger mastered."""
        level, streak = "improving", 0
        for _ in range(4):
            level, streak = _compute_mastery_transition(level, streak, 80)
        assert level == "improving"
        assert streak == 4

    def test_streak_resets_then_must_rebuild(self):
        """A wrong answer resets the streak — subsequent correct answers must rebuild."""
        # Build up to learning with streak=2
        level, streak = "learning", 0
        level, streak = _compute_mastery_transition(level, streak, 80)  # streak=1
        level, streak = _compute_mastery_transition(level, streak, 80)  # streak=2
        # One wrong answer (but not a fail — 60%)
        level, streak = _compute_mastery_transition(level, streak, 60)
        assert streak == 0
        assert level == "learning"
        # Now need 3 more correct to advance
        for _ in range(2):
            level, streak = _compute_mastery_transition(level, streak, 80)
        assert level == "learning"  # still not there
        level, streak = _compute_mastery_transition(level, streak, 80)
        assert level == "improving"  # now 3 in a row

    def test_exactly_70_counts_as_pass(self):
        """Boundary: score_pct == 70 should increment streak."""
        level, streak = _compute_mastery_transition("unknown", 0, 70)
        assert level == "learning"
        assert streak == 1

    def test_exactly_50_resets_streak_no_regression(self):
        """Boundary: score_pct == 50 resets streak but does NOT regress."""
        level, streak = _compute_mastery_transition("improving", 3, 50)
        assert level == "improving"
        assert streak == 0

    def test_exactly_49_causes_regression(self):
        """Boundary: score_pct == 49 should regress."""
        level, streak = _compute_mastery_transition("improving", 3, 49)
        assert level == "learning"
        assert streak == 0


# ---------------------------------------------------------------------------
# Spaced-repetition decay
# ---------------------------------------------------------------------------

class TestDecay:
    def test_mastered_decays_after_14_days(self):
        last = datetime.now(timezone.utc) - timedelta(days=15)
        level = _apply_decay("mastered", last)
        assert level == "improving"

    def test_mastered_does_not_decay_before_14_days(self):
        last = datetime.now(timezone.utc) - timedelta(days=13)
        level = _apply_decay("mastered", last)
        assert level == "mastered"

    def test_improving_decays_after_21_days(self):
        last = datetime.now(timezone.utc) - timedelta(days=22)
        level = _apply_decay("improving", last)
        assert level == "learning"

    def test_learning_does_not_decay(self):
        """learning has no decay threshold."""
        last = datetime.now(timezone.utc) - timedelta(days=100)
        level = _apply_decay("learning", last)
        assert level == "learning"

    def test_decay_applied_before_new_session(self):
        """A correct answer after decay should compute from the decayed level."""
        last = datetime.now(timezone.utc) - timedelta(days=15)
        # mastered → decays to improving first, then streak starts from 0
        level, streak = _compute_mastery_transition("mastered", 5, 80, last_practiced_at=last)
        # After decay to improving + 1 correct → streak=1, still improving (need 5)
        assert level == "improving"
        assert streak == 1

    def test_no_decay_if_never_practiced(self):
        """None last_practiced_at means no decay."""
        level = _apply_decay("mastered", None)
        assert level == "mastered"


# ---------------------------------------------------------------------------
# _find_weakest_format
# ---------------------------------------------------------------------------

class TestFindWeakestFormat:
    def test_finds_lowest_ratio(self):
        results = {
            "mcq":          {"correct": 4, "total": 5},   # 80%
            "fill_blank":   {"correct": 1, "total": 4},   # 25%  ← weakest
            "word_problem": {"correct": 3, "total": 4},   # 75%
        }
        assert _find_weakest_format(results) == "fill_blank"

    def test_skips_zero_total(self):
        results = {
            "mcq":        {"correct": 0, "total": 0},
            "fill_blank": {"correct": 1, "total": 2},
        }
        assert _find_weakest_format(results) == "fill_blank"

    def test_returns_none_for_empty(self):
        assert _find_weakest_format({}) is None

    def test_all_zero_totals_returns_none(self):
        results = {"mcq": {"correct": 0, "total": 0}}
        assert _find_weakest_format(results) is None


# ---------------------------------------------------------------------------
# _build_format_mix
# ---------------------------------------------------------------------------

class TestBuildFormatMix:
    def test_unknown_returns_default(self):
        mix = _build_format_mix("unknown")
        assert mix == {"mcq": 50, "fill_blank": 30, "word_problem": 20}

    def test_improving_returns_correct_mix(self):
        mix = _build_format_mix("improving")
        assert mix == {"mcq": 30, "fill_blank": 30, "word_problem": 40}

    def test_mastered_returns_correct_mix(self):
        mix = _build_format_mix("mastered")
        assert mix == {"mcq": 20, "fill_blank": 30, "word_problem": 50}

    def test_learning_boosts_weak_format(self):
        mix = _build_format_mix("learning", format_weakness="fill_blank")
        # fill_blank should be higher than baseline 33
        assert mix["fill_blank"] > 33

    def test_learning_no_weakness_sums_to_roughly_100(self):
        mix = _build_format_mix("learning")
        assert sum(mix.values()) == 100 or abs(sum(mix.values()) - 100) <= 2  # rounding tolerance
