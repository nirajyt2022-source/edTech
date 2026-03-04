"""
Tests for parent confidence block validation — CHECK 22, R21, PED_07.
"""

import pytest

from app.services.quality_reviewer import validate_parent_blocks, _GENERIC_PARENT_RE
from app.services.release_gate import (
    GateContext,
    run_release_gate,
    r21_parent_confidence,
)
from app.services.quality_scorer import score_worksheet


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _q(idx: int = 1, text: str = "What is 2+3?", answer: str = "5") -> dict:
    return {
        "id": f"q{idx}",
        "type": "short_answer",
        "text": text,
        "question_text": text,
        "correct_answer": answer,
        "answer": answer,
        "format": "short_answer",
        "skill_tag": "addition",
        "role": "application",
        "hint": "Think about it",
    }


def _worksheet(**overrides) -> dict:
    qs = [_q(i, text=f"Solve problem {i}: {i}+{i+1}?", answer=str(2 * i + 1)) for i in range(1, 6)]
    base = {
        "title": "Test Worksheet",
        "grade": "Class 3",
        "subject": "Maths",
        "topic": "Addition",
        "difficulty": "Medium",
        "language": "English",
        "questions": qs,
        "learning_objectives": ["Understand addition with carrying"],
        "chapter_ref": "NCERT Ch 3",
        "skill_focus": "Addition with carry",
        "common_mistake": "Forgetting to carry over",
        "parent_tip": "Use physical objects like blocks to demonstrate carrying",
    }
    base.update(overrides)
    return base


def _gate_ctx(worksheet_meta: dict | None = None, **kwargs) -> GateContext:
    questions = kwargs.pop("questions", [_q(i) for i in range(1, 6)])
    return GateContext(
        questions=questions,
        grade_level="Class 3",
        grade_num=3,
        subject="Maths",
        topic="Addition",
        num_questions=5,
        difficulty="medium",
        warnings=[],
        worksheet_meta=worksheet_meta or {},
        **kwargs,
    )


# ===========================================================================
# CHECK 22 — validate_parent_blocks()
# ===========================================================================


class TestValidateParentBlocks:
    def test_complete_blocks_pass(self):
        ws = _worksheet()
        ok, warnings = validate_parent_blocks(ws)
        assert ok is True
        assert warnings == []

    def test_missing_skill_focus(self):
        ws = _worksheet(skill_focus="")
        ok, warnings = validate_parent_blocks(ws)
        assert ok is False
        assert any("missing skill_focus" in w for w in warnings)

    def test_missing_common_mistake(self):
        ws = _worksheet(common_mistake="")
        ok, warnings = validate_parent_blocks(ws)
        assert ok is False
        assert any("missing common_mistake" in w for w in warnings)

    def test_missing_learning_objectives(self):
        ws = _worksheet(learning_objectives=[])
        ok, warnings = validate_parent_blocks(ws)
        assert ok is False
        assert any("missing learning_objectives" in w for w in warnings)

    def test_none_learning_objectives(self):
        ws = _worksheet(learning_objectives=None)
        ok, warnings = validate_parent_blocks(ws)
        assert ok is False
        assert any("missing learning_objectives" in w for w in warnings)

    def test_generic_parent_tip(self):
        ws = _worksheet(parent_tip="Practice regularly")
        ok, warnings = validate_parent_blocks(ws)
        assert ok is False
        assert any("generic parent_tip" in w for w in warnings)

    def test_generic_common_mistake(self):
        ws = _worksheet(common_mistake="Keep practicing")
        ok, warnings = validate_parent_blocks(ws)
        assert ok is False
        assert any("generic common_mistake" in w for w in warnings)

    def test_specific_parent_tip_passes(self):
        ws = _worksheet(parent_tip="Use a number line to show carrying from ones to tens")
        ok, warnings = validate_parent_blocks(ws)
        assert ok is True

    def test_multiple_issues(self):
        ws = _worksheet(skill_focus="", common_mistake="", learning_objectives=[])
        ok, warnings = validate_parent_blocks(ws)
        assert ok is False
        assert len(warnings) == 3


# ===========================================================================
# _GENERIC_PARENT_RE patterns
# ===========================================================================


class TestGenericParentRegex:
    @pytest.mark.parametrize(
        "text",
        [
            "Practice regularly",
            "keep practicing",
            "Revise daily",
            "Help your child",
            "Encourage your child",
            "Make sure to practice",
            "Practice makes perfect",
            "Review the concepts",
        ],
    )
    def test_generic_phrases_match(self, text):
        assert _GENERIC_PARENT_RE.match(text)

    @pytest.mark.parametrize(
        "text",
        [
            "Use a number line to demonstrate carrying",
            "Children often forget to carry over when adding two-digit numbers",
            "Practice addition with objects around the house",
            "Watch for mistakes in the tens column",
        ],
    )
    def test_specific_phrases_do_not_match(self, text):
        assert not _GENERIC_PARENT_RE.match(text)


# ===========================================================================
# R21 — PARENT_CONFIDENCE release gate rule
# ===========================================================================


class TestR21ParentConfidence:
    def test_complete_blocks_pass(self):
        ws = _worksheet()
        ctx = _gate_ctx(worksheet_meta=ws)
        result = r21_parent_confidence(ctx)
        assert result.passed is True
        assert result.stamps["parent_blocks_complete"] is True

    def test_missing_skill_focus_degrades(self):
        ws = _worksheet(skill_focus="")
        ctx = _gate_ctx(worksheet_meta=ws)
        result = r21_parent_confidence(ctx)
        assert result.passed is False
        assert result.stamps["parent_blocks_complete"] is False

    def test_no_worksheet_meta_skips(self):
        ctx = _gate_ctx(worksheet_meta={})
        result = r21_parent_confidence(ctx)
        assert result.passed is True  # skip = pass

    def test_integration_with_release_gate(self):
        # Use diverse questions to avoid R13/R14 blocks
        diverse_qs = [
            _q(1, text="What is 12 + 15?", answer="27"),
            _q(2, text="Find the sum of 23 and 14.", answer="37"),
            _q(3, text="If Ravi has 8 apples and gets 5 more, how many does he have?", answer="13"),
            _q(4, text="Solve: 45 + 32 = ___", answer="77"),
            _q(5, text="Can you calculate 19 + 22?", answer="41"),
        ]
        ws = _worksheet(skill_focus="", learning_objectives=[])
        verdict = run_release_gate(
            questions=diverse_qs,
            grade_level="Class 3",
            subject="Maths",
            topic="Addition",
            num_questions=5,
            difficulty="medium",
            warnings=[],
            worksheet_meta=ws,
        )
        assert verdict.stamps.get("parent_blocks_complete") is False
        # R21 is DEGRADE, so should not block
        r21_results = [r for r in verdict.rule_results if r.rule_name == "R21_PARENT_CONFIDENCE"]
        assert len(r21_results) == 1
        assert r21_results[0].passed is False
        assert r21_results[0].enforcement.value == "degrade"


# ===========================================================================
# PED_07 — quality scorer checks
# ===========================================================================


class TestPED07QualityScorer:
    def test_complete_blocks_no_ped07(self):
        ws = _worksheet()
        result = score_worksheet(ws)
        ped07 = [f for f in result.failures if f.check_id == "PED_07"]
        assert len(ped07) == 0

    def test_missing_skill_focus_deducts(self):
        ws = _worksheet(skill_focus="")
        result = score_worksheet(ws)
        ped07 = [f for f in result.failures if f.check_id == "PED_07"]
        assert any("skill_focus" in f.message for f in ped07)

    def test_missing_learning_objectives_minor(self):
        ws = _worksheet(learning_objectives=[])
        result = score_worksheet(ws)
        ped07 = [f for f in result.failures if f.check_id == "PED_07"]
        minors = [f for f in ped07 if f.severity == "minor" and "learning_objectives" in f.message]
        assert len(minors) >= 1

    def test_missing_common_mistake_minor(self):
        ws = _worksheet(common_mistake="")
        result = score_worksheet(ws)
        ped07 = [f for f in result.failures if f.check_id == "PED_07"]
        assert any(f.severity == "minor" and "common_mistake" in f.message for f in ped07)

    def test_all_missing_compounds(self):
        ws = _worksheet(skill_focus="", learning_objectives=[], common_mistake="")
        result = score_worksheet(ws)
        ped07 = [f for f in result.failures if f.check_id == "PED_07"]
        assert len(ped07) == 3
