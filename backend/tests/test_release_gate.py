"""
Tests for the Release Gate Engine — 10 rules + integration tests.
"""

from app.services.release_gate import (
    Enforcement,
    GateContext,
    VALID_QUESTION_TYPES,
    r01_arithmetic_verified,
    r02_known_types_only,
    r03_format_mix_tolerance,
    r04_curriculum_grounded,
    r05_question_count_exact,
    r06_adaptive_explicit,
    r07_word_problem_verified,
    r08_minimum_quality_bar,
    r09_skill_tags_valid,
    r10_warnings_transparent,
    run_release_gate,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _q(idx: int = 1, qtype: str = "mcq", text: str = "What is 2+3?", answer: str = "5", **kwargs) -> dict:
    """Quick question builder."""
    d = {
        "id": f"q{idx}",
        "type": qtype,
        "text": text,
        "question_text": text,
        "correct_answer": answer,
        "answer": answer,
        "format": qtype,
        "skill_tag": kwargs.pop("skill_tag", "addition"),
    }
    d.update(kwargs)
    return d


class _FakeContext:
    """Minimal GenerationContext stand-in."""

    def __init__(self, **kwargs):
        self.format_mix = kwargs.get("format_mix", {"mcq": 40, "fill_blank": 30, "word_problem": 30})
        self.valid_skill_tags = kwargs.get("valid_skill_tags", ["addition", "subtraction", "multiplication"])
        self.adaptive_fallback = kwargs.get("adaptive_fallback", False)
        self.scaffolding = kwargs.get("scaffolding", False)
        self.challenge_mode = kwargs.get("challenge_mode", False)


def _ctx(
    questions: list[dict] | None = None,
    subject: str = "Maths",
    num_questions: int = 10,
    generation_context=None,
    curriculum_available: bool = True,
    warnings: list[str] | None = None,
) -> GateContext:
    """Quick GateContext builder."""
    if questions is None:
        questions = [_q(i) for i in range(1, num_questions + 1)]
    return GateContext(
        questions=questions,
        grade_level="Class 3",
        grade_num=3,
        subject=subject,
        topic="Addition",
        num_questions=num_questions,
        difficulty="medium",
        warnings=warnings or [],
        generation_context=generation_context,
        curriculum_available=curriculum_available,
    )


# ===========================================================================
# R01 — ARITHMETIC_VERIFIED
# ===========================================================================


class TestR01ArithmeticVerified:
    def test_clean_maths_passes(self):
        ctx = _ctx(subject="Maths")
        result = r01_arithmetic_verified(ctx)
        assert result.passed

    def test_unverified_blocks(self):
        qs = [_q(1), _q(2, _math_unverified=True), _q(3)]
        ctx = _ctx(questions=qs, subject="Maths")
        result = r01_arithmetic_verified(ctx)
        assert not result.passed
        assert result.enforcement == Enforcement.BLOCK

    def test_non_maths_skips(self):
        qs = [_q(1, _math_unverified=True)]
        ctx = _ctx(questions=qs, subject="English")
        result = r01_arithmetic_verified(ctx)
        assert result.passed


# ===========================================================================
# R02 — KNOWN_TYPES_ONLY
# ===========================================================================


class TestR02KnownTypes:
    def test_all_valid_types_pass(self):
        qs = [_q(i, qtype=t) for i, t in enumerate(VALID_QUESTION_TYPES, 1)]
        ctx = _ctx(questions=qs, num_questions=len(qs))
        result = r02_known_types_only(ctx)
        assert result.passed

    def test_unknown_type_blocks(self):
        qs = [_q(1, qtype="mystery_type")]
        ctx = _ctx(questions=qs, num_questions=1)
        result = r02_known_types_only(ctx)
        assert not result.passed
        assert "mystery_type" in result.detail

    def test_empty_type_blocks(self):
        qs = [_q(1, qtype="")]
        ctx = _ctx(questions=qs, num_questions=1)
        result = r02_known_types_only(ctx)
        assert not result.passed


# ===========================================================================
# R03 — FORMAT_MIX_TOLERANCE
# ===========================================================================


class TestR03FormatMix:
    def test_no_context_passes(self):
        ctx = _ctx(generation_context=None)
        result = r03_format_mix_tolerance(ctx)
        assert result.passed

    def test_heavy_drift_degrades(self):
        # All MCQ, target is 40% MCQ — 100% vs 40% = 60pp drift
        qs = [_q(i, qtype="mcq") for i in range(1, 11)]
        gc = _FakeContext(format_mix={"mcq": 40, "fill_blank": 30, "word_problem": 30})
        ctx = _ctx(questions=qs, generation_context=gc)
        result = r03_format_mix_tolerance(ctx)
        assert not result.passed
        assert result.enforcement == Enforcement.DEGRADE

    def test_within_tolerance_passes(self):
        # 5 MCQ + 3 fill_blank + 2 word_problem = 50/30/20 vs target 40/30/30
        qs = (
            [_q(i, qtype="mcq") for i in range(1, 6)]
            + [_q(i, qtype="fill_blank") for i in range(6, 9)]
            + [_q(i, qtype="word_problem") for i in range(9, 11)]
        )
        gc = _FakeContext(format_mix={"mcq": 40, "fill_blank": 30, "word_problem": 30})
        ctx = _ctx(questions=qs, generation_context=gc)
        result = r03_format_mix_tolerance(ctx)
        assert result.passed


# ===========================================================================
# R04 — CURRICULUM_GROUNDED
# ===========================================================================


class TestR04CurriculumGrounded:
    def test_with_curriculum_passes(self):
        ctx = _ctx(curriculum_available=True)
        result = r04_curriculum_grounded(ctx)
        assert result.passed

    def test_without_curriculum_degrades(self):
        ctx = _ctx(curriculum_available=False)
        result = r04_curriculum_grounded(ctx)
        assert not result.passed
        assert result.enforcement == Enforcement.DEGRADE


# ===========================================================================
# R05 — QUESTION_COUNT_EXACT
# ===========================================================================


class TestR05QuestionCount:
    def test_exact_passes(self):
        ctx = _ctx(num_questions=10)  # 10 questions by default
        result = r05_question_count_exact(ctx)
        assert result.passed

    def test_one_short_passes_for_10_plus(self):
        qs = [_q(i) for i in range(1, 10)]  # 9 for requested 10
        ctx = _ctx(questions=qs, num_questions=10)
        result = r05_question_count_exact(ctx)
        assert result.passed

    def test_two_short_blocks_for_10_plus(self):
        qs = [_q(i) for i in range(1, 9)]  # 8 for requested 10
        ctx = _ctx(questions=qs, num_questions=10)
        result = r05_question_count_exact(ctx)
        assert not result.passed
        assert result.enforcement == Enforcement.BLOCK

    def test_small_exact_required(self):
        qs = [_q(i) for i in range(1, 5)]  # 4 for requested 5
        ctx = _ctx(questions=qs, num_questions=5)
        result = r05_question_count_exact(ctx)
        assert not result.passed  # Small counts require exact


# ===========================================================================
# R06 — ADAPTIVE_EXPLICIT
# ===========================================================================


class TestR06AdaptiveExplicit:
    def test_fallback_stamps_true(self):
        gc = _FakeContext(adaptive_fallback=True)
        ctx = _ctx(generation_context=gc)
        result = r06_adaptive_explicit(ctx)
        assert result.passed  # Always passes
        assert result.stamps["adaptive_fallback"] is True
        assert result.stamps["adaptive_source"] == "defaults"

    def test_non_fallback_stamps_false(self):
        gc = _FakeContext(adaptive_fallback=False)
        ctx = _ctx(generation_context=gc)
        result = r06_adaptive_explicit(ctx)
        assert result.stamps["adaptive_fallback"] is False
        assert result.stamps["adaptive_source"] == "learning_graph"

    def test_no_context_stamps_true(self):
        ctx = _ctx(generation_context=None)
        result = r06_adaptive_explicit(ctx)
        assert result.stamps["adaptive_fallback"] is True


# ===========================================================================
# R07 — WORD_PROBLEM_VERIFIED
# ===========================================================================


class TestR07WordProblemVerified:
    def test_non_maths_passes(self):
        ctx = _ctx(subject="English")
        result = r07_word_problem_verified(ctx)
        assert result.passed

    def test_complex_wps_degrade(self):
        # 3 word problems, all with 4+ numbers, none answer-corrected
        qs = [
            _q(1, qtype="word_problem", text="Ram has 12 apples, 15 oranges, 20 bananas and 8 grapes"),
            _q(2, qtype="word_problem", text="Sita bought 10 books for 25 rupees each and 30 pens for 5 rupees"),
            _q(3, qtype="word_problem", text="A shop sold 100 items at 50 each plus 200 items at 30 each"),
        ]
        for q in qs:
            q["format"] = "word_problem"
        ctx = _ctx(questions=qs, subject="Maths", num_questions=3)
        result = r07_word_problem_verified(ctx)
        assert not result.passed
        assert result.enforcement == Enforcement.DEGRADE

    def test_simple_wps_pass(self):
        qs = [
            _q(1, qtype="word_problem", text="Ram has 5 apples. He gave 2. How many left?"),
            _q(2, qtype="word_problem", text="Sita has 10 books."),
        ]
        for q in qs:
            q["format"] = "word_problem"
        ctx = _ctx(questions=qs, subject="Maths", num_questions=2)
        result = r07_word_problem_verified(ctx)
        assert result.passed


# ===========================================================================
# R08 — MINIMUM_QUALITY_BAR
# ===========================================================================


class TestR08MinimumQualityBar:
    def test_clean_passes(self):
        ctx = _ctx()
        result = r08_minimum_quality_bar(ctx)
        assert result.passed

    def test_three_plus_serious_blocks(self):
        qs = [
            _q(1, _math_unverified=True),
            _q(2, _needs_regen=True),
            _q(3, text="", question_text=""),  # empty text
        ]
        ctx = _ctx(questions=qs, num_questions=3)
        result = r08_minimum_quality_bar(ctx)
        assert not result.passed
        assert result.enforcement == Enforcement.BLOCK

    def test_bonus_excluded(self):
        qs = [
            _q(1, _math_unverified=True),
            _q(2, _math_unverified=True),
            _q(3, _math_unverified=True, _is_bonus=True),  # bonus — excluded
        ]
        ctx = _ctx(questions=qs, num_questions=3)
        result = r08_minimum_quality_bar(ctx)
        assert result.passed  # Only 2 serious (bonus excluded)


# ===========================================================================
# R09 — SKILL_TAGS_VALID
# ===========================================================================


class TestR09SkillTagsValid:
    def test_diverse_passes(self):
        qs = [
            _q(1, skill_tag="addition"),
            _q(2, skill_tag="subtraction"),
            _q(3, skill_tag="multiplication"),
            _q(4, skill_tag="addition"),
            _q(5, skill_tag="subtraction"),
        ]
        gc = _FakeContext(valid_skill_tags=["addition", "subtraction", "multiplication"])
        ctx = _ctx(questions=qs, generation_context=gc, num_questions=5)
        result = r09_skill_tags_valid(ctx)
        assert result.passed

    def test_invalid_tag_degrades(self):
        qs = [_q(1, skill_tag="quantum_physics")]
        gc = _FakeContext(valid_skill_tags=["addition", "subtraction", "multiplication"])
        ctx = _ctx(questions=qs, generation_context=gc, num_questions=1)
        result = r09_skill_tags_valid(ctx)
        assert not result.passed
        assert "quantum_physics" in result.detail

    def test_mono_tag_degrades(self):
        # All 10 questions same tag when 3+ available → >60%
        qs = [_q(i, skill_tag="addition") for i in range(1, 11)]
        gc = _FakeContext(valid_skill_tags=["addition", "subtraction", "multiplication"])
        ctx = _ctx(questions=qs, generation_context=gc)
        result = r09_skill_tags_valid(ctx)
        assert not result.passed
        assert "dominates" in result.detail


# ===========================================================================
# R10 — WARNINGS_TRANSPARENT
# ===========================================================================


class TestR10WarningsTransparent:
    def test_no_warnings_high(self):
        ctx = _ctx(warnings=[])
        result = r10_warnings_transparent(ctx)
        assert result.stamps["quality_tier"] == "high"
        assert result.stamps["severity_score"] == 0

    def test_critical_warnings_low(self):
        ctx = _ctx(warnings=["math answer incorrect for Q3", "empty question text Q7"])
        result = r10_warnings_transparent(ctx)
        assert result.stamps["quality_tier"] == "low"

    def test_moderate_warnings_medium(self):
        ctx = _ctx(warnings=["Topic drift detected in Q4", "Near-duplicate pair Q2/Q5"])
        result = r10_warnings_transparent(ctx)
        assert result.stamps["quality_tier"] == "medium"


# ===========================================================================
# Integration Tests
# ===========================================================================


class TestIntegration:
    def test_clean_worksheet_released(self):
        qs = [_q(i) for i in range(1, 11)]
        verdict = run_release_gate(
            questions=qs,
            grade_level="Class 3",
            subject="Maths",
            topic="Addition",
            num_questions=10,
            difficulty="medium",
            warnings=[],
            curriculum_available=True,
        )
        assert verdict.verdict == "released"
        assert verdict.passed
        assert len(verdict.block_reasons) == 0

    def test_unknown_type_blocked(self):
        qs = [_q(1, qtype="alien_format")]
        verdict = run_release_gate(
            questions=qs,
            grade_level="Class 3",
            subject="English",
            topic="Nouns",
            num_questions=1,
            difficulty="easy",
            warnings=[],
        )
        assert verdict.verdict == "blocked"
        assert not verdict.passed
        assert any("R02" in r for r in verdict.failed_rules)

    def test_no_curriculum_best_effort(self):
        qs = [_q(i) for i in range(1, 11)]
        verdict = run_release_gate(
            questions=qs,
            grade_level="Class 3",
            subject="Maths",
            topic="Addition",
            num_questions=10,
            difficulty="medium",
            warnings=[],
            curriculum_available=False,
        )
        assert verdict.verdict == "best_effort"
        assert verdict.passed  # Not blocked, just degraded
        assert any("R04" in r for r in verdict.failed_rules)

    def test_stamps_merged(self):
        qs = [_q(i) for i in range(1, 11)]
        verdict = run_release_gate(
            questions=qs,
            grade_level="Class 3",
            subject="Maths",
            topic="Addition",
            num_questions=10,
            difficulty="medium",
            warnings=[],
        )
        # R06 stamps adaptive info, R10 stamps quality_tier
        assert "adaptive_fallback" in verdict.stamps
        assert "quality_tier" in verdict.stamps
