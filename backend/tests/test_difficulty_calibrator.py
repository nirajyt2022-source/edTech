"""
Tests for DifficultyCalibrator.

All tests run fully offline — no Supabase or LLM calls required.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.difficulty_calibrator import (
    DifficultyCalibrator,
    _make_hint,
    _sort_key,
    get_difficulty_calibrator,
)
from app.services.topic_intelligence import GenerationContext

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _ctx(**overrides) -> GenerationContext:
    defaults = dict(
        topic_slug="Addition (carries)",
        subject="Maths",
        grade=3,
        ncert_chapter="Addition (carries)",
        ncert_subtopics=["obj1"],
        bloom_level="recall",
        format_mix={"mcq": 40, "fill_blank": 30, "word_problem": 30},
        scaffolding=False,
        challenge_mode=False,
        valid_skill_tags=["column_add_with_carry", "addition_word_problem"],
        child_context={},
    )
    defaults.update(overrides)
    return GenerationContext(**defaults)


def _q(fmt="missing_number", text="Short", **kw) -> dict:
    base = {
        "id": 1,
        "slot_type": "representation",
        "format": fmt,
        "question_text": text,
        "answer": "42",
        "skill_tag": "column_add_with_carry",
        "difficulty": "easy",
    }
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# _sort_key helper
# ---------------------------------------------------------------------------

class TestSortKey:
    def test_shorter_text_sorts_first(self):
        q_short = _q(text="Add 1 2")
        q_long = _q(text="Compute the sum of one hundred and fifty and two hundred and twenty")
        assert _sort_key(q_short) < _sort_key(q_long)

    def test_hard_format_sorts_after_easy_same_length(self):
        q_easy = _q(fmt="missing_number", text="What")
        q_hard = _q(fmt="word_problem",   text="What")
        assert _sort_key(q_easy) < _sort_key(q_hard)

    def test_hard_formats_recognized(self):
        for fmt in ("word_problem", "multi_step", "thinking", "growing_pattern"):
            _, is_hard = _sort_key(_q(fmt=fmt))
            assert is_hard == 1, f"Expected {fmt} to be hard"

    def test_easy_formats_not_hard(self):
        for fmt in ("missing_number", "place_value", "column_setup", "estimation"):
            _, is_hard = _sort_key(_q(fmt=fmt))
            assert is_hard == 0, f"Expected {fmt} to be easy"


# ---------------------------------------------------------------------------
# _make_hint helper
# ---------------------------------------------------------------------------

class TestMakeHint:
    def test_simple_topic(self):
        hint = _make_hint("Addition (carries)")
        assert hint == "Think about: Addition"

    def test_multi_word_topic(self):
        hint = _make_hint("Multiplication (tables 2-10)")
        assert hint == "Think about: Multiplication"

    def test_class_suffix_stripped(self):
        hint = _make_hint("Nouns (Class 3)")
        assert hint == "Think about: Nouns"

    def test_no_parentheses(self):
        hint = _make_hint("Fractions")
        assert hint == "Think about: Fractions"

    def test_starts_with_think_about(self):
        assert _make_hint("Any Topic (Class 5)").startswith("Think about:")


# ---------------------------------------------------------------------------
# STEP A — Sorting
# ---------------------------------------------------------------------------

class TestStepASorting:
    def test_scaffolding_true_sorts_easiest_first(self):
        """With scaffolding=True, shorter/easier questions come before longer/harder ones."""
        ctx = _ctx(scaffolding=True)
        q_hard = _q(fmt="word_problem",   text="word " * 20, id=1)
        q_easy = _q(fmt="missing_number", text="short",      id=2)
        result, _warnings = DifficultyCalibrator().calibrate([q_hard, q_easy], ctx)
        assert result[0]["id"] == 2  # easy first
        assert result[1]["id"] == 1  # hard last

    def test_scaffolding_false_order_unchanged(self):
        """With scaffolding=False, the original order must be preserved."""
        ctx = _ctx(scaffolding=False)
        q1 = _q(fmt="word_problem",   text="word " * 20, id=1)
        q2 = _q(fmt="missing_number", text="short",      id=2)
        result, _warnings = DifficultyCalibrator().calibrate([q1, q2], ctx)
        # Neither STEP A nor STEP B fires — order stays as given
        assert result[0]["id"] == 1
        assert result[1]["id"] == 2

    def test_sort_is_stable_for_equal_keys(self):
        """Questions with identical sort keys should retain relative order."""
        ctx = _ctx(scaffolding=True)
        q1 = _q(fmt="missing_number", text="Same text here", id=1)
        q2 = _q(fmt="missing_number", text="Same text here", id=2)
        q3 = _q(fmt="missing_number", text="Same text here", id=3)
        result, _warnings = DifficultyCalibrator().calibrate([q1, q2, q3], ctx)
        # sorted() is stable in CPython — relative order preserved
        ids = [q["id"] for q in result]
        assert ids == [1, 2, 3]

    def test_word_problem_sorted_after_fill_blank(self):
        """word_problem must be sorted after fill_blank even when text length is equal."""
        ctx = _ctx(scaffolding=True)
        q_wp = _q(fmt="word_problem", text="five words right here.", id=1)
        q_fb = _q(fmt="fill_blank",   text="five words right here.", id=2)
        result, _warnings = DifficultyCalibrator().calibrate([q_wp, q_fb], ctx)
        assert result[0]["id"] == 2  # fill_blank first
        assert result[1]["id"] == 1  # word_problem last


# ---------------------------------------------------------------------------
# STEP B — Hint injection
# ---------------------------------------------------------------------------

class TestStepBHints:
    def test_scaffolding_true_adds_hint_to_first_two(self):
        """With scaffolding=True, first 2 questions without hints get hints."""
        ctx = _ctx(scaffolding=True)
        # Use varied formats to prevent STEP D/F from reordering
        fmts = ["mcq", "fill_blank", "word_problem", "missing_number"]
        questions = [_q(id=i, fmt=fmts[i - 1]) for i in range(1, 5)]
        result, _warnings = DifficultyCalibrator().calibrate(questions, ctx)
        # Count how many questions got hints (should be exactly 2)
        hinted = [q for q in result if q.get("hint")]
        assert len(hinted) == 2, f"Expected 2 hints, got {len(hinted)}"

    def test_hint_content_matches_topic(self):
        """Hint text must reference the first word of the topic slug."""
        ctx = _ctx(scaffolding=True, topic_slug="Multiplication (tables 2-10)")
        questions = [_q(id=1)]
        result, _warnings = DifficultyCalibrator().calibrate(questions, ctx)
        assert result[0]["hint"] == "Think about: Multiplication"

    def test_existing_hint_not_overwritten(self):
        """A question that already has a non-empty 'hint' must be skipped."""
        ctx = _ctx(scaffolding=True)
        q_with_hint    = _q(id=1, hint="My custom hint")
        q_without_hint = _q(id=2)
        result, _warnings = DifficultyCalibrator().calibrate([q_with_hint, q_without_hint], ctx)
        # q1 keeps original hint; q2 gets a generated hint; hint count is now 2 total but
        # q1 is NOT overwritten
        assert result[0]["hint"] == "My custom hint"
        assert result[1].get("hint")  # generated

    def test_scaffolding_false_no_hints_added(self):
        """With scaffolding=False, no hints must be injected."""
        ctx = _ctx(scaffolding=False)
        questions = [_q(id=i) for i in range(1, 4)]
        result, _warnings = DifficultyCalibrator().calibrate(questions, ctx)
        for q in result:
            assert not q.get("hint"), f"Q{q['id']} should not have hint"

    def test_single_question_gets_one_hint(self):
        """With only 1 question and scaffolding=True, that one question gets a hint."""
        ctx = _ctx(scaffolding=True)
        result, _warnings = DifficultyCalibrator().calibrate([_q(id=1)], ctx)
        assert result[0].get("hint")

    def test_empty_list_no_crash(self):
        """Empty question list with scaffolding=True must not crash."""
        ctx = _ctx(scaffolding=True)
        result, _warnings = DifficultyCalibrator().calibrate([], ctx)
        assert result == []


# ---------------------------------------------------------------------------
# STEP C — Bonus challenge question
# ---------------------------------------------------------------------------

class TestStepCBonus:
    def test_challenge_mode_adds_bonus(self):
        """With challenge_mode=True, one extra bonus question is appended."""
        ctx = _ctx(challenge_mode=True)
        questions = [_q(id=1), _q(id=2)]
        result, _warnings = DifficultyCalibrator().calibrate(questions, ctx)
        assert len(result) == 3
        assert result[-1].get("_is_bonus") is True

    def test_bonus_format_is_word_problem(self):
        ctx = _ctx(challenge_mode=True)
        result, _warnings = DifficultyCalibrator().calibrate([_q()], ctx)
        bonus = result[-1]
        assert bonus["format"] == "word_problem"

    def test_bonus_answer_is_see_working(self):
        ctx = _ctx(challenge_mode=True)
        result, _warnings = DifficultyCalibrator().calibrate([_q()], ctx)
        assert result[-1]["answer"] == "See working"

    def test_bonus_skill_tag_uses_first_valid(self):
        ctx = _ctx(challenge_mode=True, valid_skill_tags=["col_add", "add_word"])
        result, _warnings = DifficultyCalibrator().calibrate([_q()], ctx)
        assert result[-1]["skill_tag"] == "col_add"

    def test_bonus_skill_tag_fallback_when_no_valid_tags(self):
        ctx = _ctx(challenge_mode=True, valid_skill_tags=[])
        result, _warnings = DifficultyCalibrator().calibrate([_q()], ctx)
        assert result[-1]["skill_tag"] == "general"

    def test_bonus_question_text_contains_topic(self):
        ctx = _ctx(challenge_mode=True, topic_slug="Fractions (halves, quarters)")
        result, _warnings = DifficultyCalibrator().calibrate([_q()], ctx)
        assert "Fractions (halves, quarters)" in result[-1]["question_text"]

    def test_challenge_mode_false_no_bonus(self):
        """With challenge_mode=False, list length must be unchanged."""
        ctx = _ctx(challenge_mode=False)
        questions = [_q(id=1), _q(id=2)]
        result, _warnings = DifficultyCalibrator().calibrate(questions, ctx)
        assert len(result) == 2
        assert not any(q.get("_is_bonus") for q in result)


# ---------------------------------------------------------------------------
# STEP D — Format distribution (active swap)
# ---------------------------------------------------------------------------

class TestStepDFormatFix:
    def test_no_swap_when_within_threshold(self):
        """Formats within 20pp of target should not be swapped."""
        ctx = _ctx(format_mix={"word_problem": 50, "missing_number": 50})
        original = [_q(fmt="word_problem", id=1), _q(fmt="missing_number", id=2)]
        result, _warnings = DifficultyCalibrator().calibrate(original, ctx)
        assert result[0]["format"] == "word_problem"
        assert result[1]["format"] == "missing_number"

    def test_empty_questions_no_crash(self):
        """Empty list must not crash the format fixer."""
        ctx = _ctx()
        result, _warnings = DifficultyCalibrator().calibrate([], ctx)
        assert result == []

    def test_swap_when_format_overrepresented(self):
        """When one format is far over target, it should be swapped toward under."""
        # Target: 40% mcq, 30% fill_blank, 30% word_problem
        # Actual: 100% mcq (10 of 10) — massive drift
        ctx = _ctx(format_mix={"mcq": 40, "fill_blank": 30, "word_problem": 30})
        questions = [_q(fmt="mcq", id=i) for i in range(10)]
        result, warnings = DifficultyCalibrator().calibrate(questions, ctx)
        formats = [q["format"] for q in result]
        # At least some should have been swapped away from mcq
        assert formats.count("mcq") < 10, "Some mcqs should have been swapped"
        assert any("drift fix" in w for w in warnings)


# ---------------------------------------------------------------------------
# Combined flags
# ---------------------------------------------------------------------------

class TestCombinedFlags:
    def test_scaffolding_and_challenge_both_active(self):
        """Both scaffolding and challenge_mode: sorted + hints + bonus."""
        ctx = _ctx(scaffolding=True, challenge_mode=True)
        q_hard = _q(fmt="word_problem",   text="word " * 15, id=1)
        q_easy = _q(fmt="missing_number", text="short",      id=2)
        result, _warnings = DifficultyCalibrator().calibrate([q_hard, q_easy], ctx)

        # Sorted: easy first
        assert result[0]["id"] == 2
        assert result[1]["id"] == 1
        # Hints on first 2 non-bonus questions
        assert result[0].get("hint")
        assert result[1].get("hint")
        # Bonus appended last
        assert result[-1].get("_is_bonus") is True
        assert len(result) == 3

    def test_neither_flag_questions_pass_through(self):
        """With both flags off, questions pass through completely unchanged."""
        ctx = _ctx(scaffolding=False, challenge_mode=False)
        questions = [
            _q(fmt="word_problem", id=1),
            _q(fmt="thinking",     id=2),
        ]
        result, _warnings = DifficultyCalibrator().calibrate(questions, ctx)
        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[1]["id"] == 2
        assert not result[0].get("hint")
        assert not result[1].get("hint")
        assert not any(q.get("_is_bonus") for q in result)


# ---------------------------------------------------------------------------
# Return type and singleton
# ---------------------------------------------------------------------------

class TestReturnType:
    def test_returns_tuple_of_list_and_warnings(self):
        ctx = _ctx()
        result = DifficultyCalibrator().calibrate([], ctx)
        assert isinstance(result, tuple)
        assert isinstance(result[0], list)
        assert isinstance(result[1], list)

    def test_singleton_same_instance(self):
        assert get_difficulty_calibrator() is get_difficulty_calibrator()

    def test_singleton_correct_type(self):
        assert isinstance(get_difficulty_calibrator(), DifficultyCalibrator)


# ---------------------------------------------------------------------------
# Pre-correction quality score
# ---------------------------------------------------------------------------

class TestCalibrationScore:
    def test_score_present_in_warnings(self):
        """calibrate() should always append a calibration_score warning."""
        ctx = _ctx()
        qs = [{"question_text": f"What is {i}+1?", "format": "mcq", "skill_tag": "column_add_with_carry"}
              for i in range(5)]
        _, warnings = DifficultyCalibrator().calibrate(qs, ctx)
        score_warnings = [w for w in warnings if "[calibration_score]" in w]
        assert len(score_warnings) == 1
        assert "corrections=" in score_warnings[0]

    def test_zero_corrections_when_clean(self):
        """No swaps needed → corrections=0."""
        ctx = _ctx(format_mix={})  # no target → no drift
        qs = [{"question_text": "What is 2+3?", "format": "mcq", "skill_tag": "column_add_with_carry"}]
        _, warnings = DifficultyCalibrator().calibrate(qs, ctx)
        score_line = [w for w in warnings if "[calibration_score]" in w][0]
        assert "corrections=0" in score_line

    def test_nonzero_corrections_on_drift(self):
        """Heavy format drift should produce corrections > 0."""
        ctx = _ctx(format_mix={"mcq": 10, "fill_blank": 10, "word_problem": 80})
        # All MCQ → heavy drift from 80% word_problem target
        qs = [{"question_text": f"Q{i}: What is {i}+1?", "format": "mcq",
               "skill_tag": "column_add_with_carry"} for i in range(10)]
        _, warnings = DifficultyCalibrator().calibrate(qs, ctx)
        score_line = [w for w in warnings if "[calibration_score]" in w][0]
        # Should have some format swaps
        assert "format_swaps=" in score_line


# ---------------------------------------------------------------------------
# STEP B2 — Encouragement micro-prompt (T4)
# ---------------------------------------------------------------------------

class TestStepB2Encouragement:
    def test_scaffolding_adds_encouragement_at_q5(self):
        """With scaffolding=True and ≥5 questions, Q5 gets encouragement."""
        ctx = _ctx(scaffolding=True, format_mix={})
        fmts = ["mcq", "fill_blank", "word_problem", "missing_number", "estimation"]
        qs = [_q(id=i, fmt=fmts[i - 1]) for i in range(1, 6)]
        result, _warnings = DifficultyCalibrator().calibrate(qs, ctx)
        encouraged = [q for q in result if q.get("_encouragement")]
        assert len(encouraged) == 1
        assert "great" in encouraged[0]["_encouragement"].lower()

    def test_scaffolding_false_no_encouragement(self):
        """With scaffolding=False, no encouragement should be added."""
        ctx = _ctx(scaffolding=False, format_mix={})
        qs = [_q(id=i) for i in range(1, 6)]
        result, _warnings = DifficultyCalibrator().calibrate(qs, ctx)
        assert not any(q.get("_encouragement") for q in result)

    def test_fewer_than_5_no_encouragement(self):
        """With fewer than 5 questions, no encouragement added."""
        ctx = _ctx(scaffolding=True, format_mix={})
        qs = [_q(id=i) for i in range(1, 4)]
        result, _warnings = DifficultyCalibrator().calibrate(qs, ctx)
        assert not any(q.get("_encouragement") for q in result)
