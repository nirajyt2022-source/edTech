"""Tests for the Fallback Bank — deterministic replacement of _needs_regen questions."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from app.services.fallback_bank import (
    replace_regen_questions,
    _get_bank,
    _build_fallback,
    MAX_REPLACEMENTS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_context(subject: str = "maths", grade: int = 3, valid_skill_tags: list | None = None):
    ctx = MagicMock()
    ctx.subject = subject
    ctx.grade = grade
    ctx.valid_skill_tags = valid_skill_tags or ["addition", "subtraction"]
    return ctx


def _make_question(qid: int = 1, needs_regen: bool = False, **overrides) -> dict:
    q = {
        "id": qid,
        "display_number": qid,
        "question_text": f"Original question {qid}",
        "text": f"Original question {qid}",
        "answer": "42",
        "correct_answer": "42",
        "format": "mcq",
        "type": "mcq",
        "slot_type": "application",
        "skill_tag": "addition",
        "difficulty": "easy",
        "images": [],
        "pictorial_elements": [],
    }
    if needs_regen:
        q["_needs_regen"] = True
    q.update(overrides)
    return q


# ---------------------------------------------------------------------------
# Tests: No regen flags → no mutations
# ---------------------------------------------------------------------------

class TestNoRegenFlags:
    def test_no_flagged_questions_returns_unchanged(self):
        questions = [_make_question(1), _make_question(2), _make_question(3)]
        ctx = _make_context()
        result, logs = replace_regen_questions(questions, ctx)
        assert len(result) == 3
        assert all(q["answer"] == "42" for q in result)
        assert logs == []

    def test_empty_list_returns_empty(self):
        result, logs = replace_regen_questions([], _make_context())
        assert result == []
        assert logs == []


# ---------------------------------------------------------------------------
# Tests: Replacement behavior
# ---------------------------------------------------------------------------

class TestReplacementBehavior:
    def test_one_regen_replaced(self):
        questions = [
            _make_question(1),
            _make_question(2, needs_regen=True),
            _make_question(3),
        ]
        ctx = _make_context("maths", 3)
        result, logs = replace_regen_questions(questions, ctx)

        assert result[0]["answer"] == "42"  # untouched
        assert result[2]["answer"] == "42"  # untouched
        # Replaced question
        replaced = result[1]
        assert replaced.get("_needs_regen") is False
        assert replaced.get("is_fallback") is True
        assert replaced.get("verified") is True
        assert replaced["id"] == 2  # preserved
        assert replaced["display_number"] == 2  # preserved
        assert any("[fallback_bank] Replaced" in msg for msg in logs)

    def test_two_regens_both_replaced(self):
        questions = [
            _make_question(1, needs_regen=True),
            _make_question(2, needs_regen=True),
            _make_question(3),
        ]
        ctx = _make_context("maths", 3)
        result, logs = replace_regen_questions(questions, ctx)

        assert result[0].get("is_fallback") is True
        assert result[1].get("is_fallback") is True
        assert result[2].get("is_fallback") is None or result[2].get("is_fallback") is not True
        # Both should have different text (deduplication via shuffle)
        # Note: with shuffle there's a tiny chance they're the same, but bank has 5 entries
        assert len([msg for msg in logs if "Replaced" in msg]) == 2

    def test_three_regens_skipped(self):
        questions = [
            _make_question(1, needs_regen=True),
            _make_question(2, needs_regen=True),
            _make_question(3, needs_regen=True),
        ]
        ctx = _make_context("maths", 3)
        result, logs = replace_regen_questions(questions, ctx)

        # All should be unchanged (skipped because >MAX_REPLACEMENTS)
        assert all(q.get("_needs_regen") is True for q in result)
        assert any("exceeds max" in msg for msg in logs)

    def test_id_and_display_number_preserved(self):
        questions = [_make_question(7, needs_regen=True, display_number=7)]
        ctx = _make_context("maths", 1)
        result, logs = replace_regen_questions(questions, ctx)

        assert result[0]["id"] == 7
        assert result[0]["display_number"] == 7


# ---------------------------------------------------------------------------
# Tests: Subject dispatchers
# ---------------------------------------------------------------------------

class TestSubjectDispatchers:
    def test_english_fallback(self):
        questions = [_make_question(1, needs_regen=True)]
        ctx = _make_context("english", 2)
        result, logs = replace_regen_questions(questions, ctx)
        assert result[0].get("is_fallback") is True
        assert result[0]["answer"] != "42"

    def test_hindi_fallback(self):
        questions = [_make_question(1, needs_regen=True)]
        ctx = _make_context("hindi", 1)
        result, logs = replace_regen_questions(questions, ctx)
        assert result[0].get("is_fallback") is True

    def test_science_fallback(self):
        questions = [_make_question(1, needs_regen=True)]
        ctx = _make_context("science", 4)
        result, logs = replace_regen_questions(questions, ctx)
        assert result[0].get("is_fallback") is True

    def test_evs_uses_science_bank(self):
        questions = [_make_question(1, needs_regen=True)]
        ctx = _make_context("evs", 3)
        result, logs = replace_regen_questions(questions, ctx)
        assert result[0].get("is_fallback") is True

    def test_unknown_subject_keeps_original(self):
        questions = [_make_question(1, needs_regen=True)]
        ctx = _make_context("art", 3)
        result, logs = replace_regen_questions(questions, ctx)
        assert result[0].get("_needs_regen") is True
        assert any("No bank" in msg for msg in logs)


# ---------------------------------------------------------------------------
# Tests: Skill tag fallback
# ---------------------------------------------------------------------------

class TestSkillTag:
    def test_original_skill_tag_preserved_when_valid(self):
        questions = [_make_question(1, needs_regen=True, skill_tag="subtraction")]
        ctx = _make_context("maths", 3, valid_skill_tags=["addition", "subtraction"])
        result, _ = replace_regen_questions(questions, ctx)
        assert result[0]["skill_tag"] == "subtraction"

    def test_invalid_skill_tag_replaced_with_first_valid(self):
        questions = [_make_question(1, needs_regen=True, skill_tag="invalid_tag")]
        ctx = _make_context("maths", 3, valid_skill_tags=["addition", "subtraction"])
        result, _ = replace_regen_questions(questions, ctx)
        assert result[0]["skill_tag"] == "addition"


# ---------------------------------------------------------------------------
# Tests: Fail-open / edge cases
# ---------------------------------------------------------------------------

class TestFailOpen:
    def test_none_context_keeps_original(self):
        questions = [_make_question(1, needs_regen=True)]
        result, logs = replace_regen_questions(questions, None)
        # With None context, subject="" → no bank → keeps original
        assert result[0].get("_needs_regen") is True
        assert any("No bank" in msg for msg in logs)

    def test_grade_clamped_to_range(self):
        bank = _get_bank("maths", 0)
        assert bank is not None  # clamped to 1
        bank = _get_bank("maths", 99)
        assert bank is not None  # clamped to 5


# ---------------------------------------------------------------------------
# Tests: _build_fallback internals
# ---------------------------------------------------------------------------

class TestBuildFallback:
    def test_clears_options(self):
        original = _make_question(1, options=["A", "B", "C", "D"])
        entry = {"text": "What is 2+2?", "answer": "4", "format": "fill_blank", "explanation": "2+2=4"}
        ctx = _make_context()
        result = _build_fallback(original, entry, ctx)
        assert "options" not in result

    def test_default_difficulty_medium(self):
        original = _make_question(1)
        original.pop("difficulty", None)
        entry = {"text": "What is 2+2?", "answer": "4", "format": "fill_blank"}
        result = _build_fallback(original, entry, _make_context())
        assert result["difficulty"] == "medium"

    def test_verified_and_fallback_flags(self):
        original = _make_question(1)
        entry = {"text": "X", "answer": "Y", "format": "fill_blank"}
        result = _build_fallback(original, entry, _make_context())
        assert result["is_fallback"] is True
        assert result["verified"] is True
        assert result["_needs_regen"] is False


# ---------------------------------------------------------------------------
# Tests: MAX_REPLACEMENTS constant
# ---------------------------------------------------------------------------

class TestConstants:
    def test_max_replacements_is_2(self):
        assert MAX_REPLACEMENTS == 2
