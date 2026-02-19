"""
Tests for the grade profile system — TDD RED first.

Covers:
  1. grade_profiles.json loads correctly with all 5 grades + required fields
  2. build_grade_guardrail_prompt() output is correct for key grades
  3. validate_grade_appropriateness() rejects forbidden question types
  4. validate_grade_appropriateness() rejects long answers for Class 1
  5. validate_grade_appropriateness() rejects "explain" in question text for Class 1-2
  6. validate_grade_appropriateness() accepts error_detection for Class 3+

All tests are fully offline — no LLM or Supabase calls.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from app.services.slot_engine import GRADE_PROFILES, build_grade_guardrail_prompt
from app.services.quality_reviewer import validate_grade_appropriateness


# ── 1. grade_profiles.json structure ────────────────────────────────────────


class TestGradeProfilesJson:
    REQUIRED_KEYS = {
        "age_range",
        "cognitive_ceiling",
        "allowed_question_types",
        "forbidden_question_types",
        "answer_constraints",
        "tier_rules",
        "context_must_be",
        "context_forbidden",
    }

    def test_all_five_grades_present(self):
        assert set(GRADE_PROFILES.keys()) == {"1", "2", "3", "4", "5"}

    def test_each_grade_has_required_keys(self):
        for grade, profile in GRADE_PROFILES.items():
            missing = self.REQUIRED_KEYS - set(profile.keys())
            assert not missing, f"Grade {grade} missing keys: {missing}"

    def test_grade1_forbids_error_detection(self):
        assert "error_detection" in GRADE_PROFILES["1"]["forbidden_question_types"]

    def test_grade1_forbids_duration_calculation(self):
        assert "duration_calculation" in GRADE_PROFILES["1"]["forbidden_question_types"]

    def test_grade1_max_words_is_5(self):
        assert GRADE_PROFILES["1"]["answer_constraints"]["max_words"] == 5

    def test_grade3_allows_error_detection(self):
        allowed = GRADE_PROFILES["3"]["allowed_question_types"]
        assert "error_detection" in allowed

    def test_grade2_forbids_error_detection(self):
        assert "error_detection" in GRADE_PROFILES["2"]["forbidden_question_types"]

    def test_grade5_max_words_is_100(self):
        assert GRADE_PROFILES["5"]["answer_constraints"]["max_words"] == 100

    def test_tier_rules_has_foundation_application_stretch(self):
        for grade, profile in GRADE_PROFILES.items():
            tier = profile["tier_rules"]
            assert "foundation" in tier, f"Grade {grade} missing tier 'foundation'"
            assert "application" in tier, f"Grade {grade} missing tier 'application'"
            assert "stretch" in tier, f"Grade {grade} missing tier 'stretch'"


# ── 2. build_grade_guardrail_prompt() ────────────────────────────────────────


class TestBuildGradeGuardrailPrompt:
    def test_grade1_prompt_contains_age_range(self):
        prompt = build_grade_guardrail_prompt(1)
        assert "6-7" in prompt

    def test_grade1_prompt_contains_forbidden_error_detection(self):
        prompt = build_grade_guardrail_prompt(1)
        assert "error_detection" in prompt

    def test_grade1_prompt_contains_max_words(self):
        prompt = build_grade_guardrail_prompt(1)
        assert "5" in prompt  # max 5 words

    def test_grade1_prompt_contains_class_header(self):
        prompt = build_grade_guardrail_prompt(1)
        assert "CLASS 1" in prompt

    def test_grade3_prompt_allows_error_detection(self):
        # error_detection should appear in the ALLOWED section, not forbidden
        prompt = build_grade_guardrail_prompt(3)
        assert "CLASS 3" in prompt
        assert "error_detection" in prompt

    def test_grade5_prompt_contains_class_header(self):
        prompt = build_grade_guardrail_prompt(5)
        assert "CLASS 5" in prompt

    def test_unknown_grade_returns_empty(self):
        prompt = build_grade_guardrail_prompt(99)
        assert prompt == ""

    def test_grade1_prompt_contains_context_constraint(self):
        prompt = build_grade_guardrail_prompt(1)
        # Should include context guidance (food/animals/toys etc.)
        assert "context" in prompt.lower() or "familiar" in prompt.lower()

    def test_prompt_is_nonempty_for_all_valid_grades(self):
        for g in [1, 2, 3, 4, 5]:
            assert build_grade_guardrail_prompt(g) != "", f"Grade {g} returned empty prompt"


# ── 3. validate_grade_appropriateness() ─────────────────────────────────────


def _make_q(role="recognition", answer="12", question="What is 5 + 3?"):
    return {"role": role, "correct_answer": answer, "question": question}


class TestValidateGradeAppropriateness:

    # -- forbidden question type --

    def test_grade1_rejects_error_detection_role(self):
        questions = [_make_q(role="error_detection")]
        valid, rejected = validate_grade_appropriateness(questions, grade_num=1)
        assert len(rejected) == 1
        assert len(valid) == 0

    def test_grade2_rejects_error_detection_role(self):
        questions = [_make_q(role="error_detection")]
        valid, rejected = validate_grade_appropriateness(questions, grade_num=2)
        assert len(rejected) == 1

    def test_grade3_accepts_error_detection_role(self):
        questions = [_make_q(role="error_detection")]
        valid, rejected = validate_grade_appropriateness(questions, grade_num=3)
        assert len(valid) == 1
        assert len(rejected) == 0

    def test_grade1_accepts_recognition_role(self):
        questions = [_make_q(role="recognition")]
        valid, rejected = validate_grade_appropriateness(questions, grade_num=1)
        assert len(valid) == 1
        assert len(rejected) == 0

    # -- answer length --

    def test_grade1_rejects_answer_exceeding_5_words(self):
        questions = [_make_q(answer="The student added the numbers incorrectly here")]
        valid, rejected = validate_grade_appropriateness(questions, grade_num=1)
        assert len(rejected) == 1
        assert any("answer too long" in r for reason in rejected for r in reason.get("_rejection_reasons", []))

    def test_grade1_accepts_short_answer(self):
        questions = [_make_q(answer="12")]
        valid, rejected = validate_grade_appropriateness(questions, grade_num=1)
        assert len(valid) == 1

    def test_grade5_accepts_long_answer(self):
        # Grade 5 allows up to 100 words
        long_answer = " ".join(["word"] * 80)
        questions = [_make_q(answer=long_answer)]
        valid, rejected = validate_grade_appropriateness(questions, grade_num=5)
        assert len(valid) == 1

    # -- explanation requests in question text --

    def test_grade1_rejects_explain_in_question(self):
        questions = [_make_q(question="Explain why 5 + 3 = 8 is correct.")]
        valid, rejected = validate_grade_appropriateness(questions, grade_num=1)
        assert len(rejected) == 1

    def test_grade2_rejects_explain_in_question(self):
        questions = [_make_q(question="Explain why the answer is wrong.")]
        valid, rejected = validate_grade_appropriateness(questions, grade_num=2)
        assert len(rejected) == 1

    def test_grade3_allows_explain_in_question(self):
        questions = [_make_q(question="Explain why the student made a mistake.")]
        valid, rejected = validate_grade_appropriateness(questions, grade_num=3)
        assert len(valid) == 1

    def test_grade1_rejects_justify_in_question(self):
        questions = [_make_q(question="Justify your answer with a reason.")]
        valid, rejected = validate_grade_appropriateness(questions, grade_num=1)
        assert len(rejected) == 1

    # -- rejection reasons are recorded --

    def test_rejected_question_carries_rejection_reasons(self):
        questions = [_make_q(role="error_detection")]
        _, rejected = validate_grade_appropriateness(questions, grade_num=1)
        assert "_rejection_reasons" in rejected[0]
        assert len(rejected[0]["_rejection_reasons"]) >= 1

    # -- multiple questions mixed --

    def test_mixed_batch_splits_correctly(self):
        questions = [
            _make_q(role="recognition", answer="5"),          # valid for grade 1
            _make_q(role="error_detection", answer="wrong"),  # invalid for grade 1
        ]
        valid, rejected = validate_grade_appropriateness(questions, grade_num=1)
        assert len(valid) == 1
        assert len(rejected) == 1

    # -- empty input --

    def test_empty_question_list_returns_empty(self):
        valid, rejected = validate_grade_appropriateness([], grade_num=1)
        assert valid == []
        assert rejected == []

    # -- unknown grade is permissive --

    def test_unknown_grade_accepts_everything(self):
        questions = [_make_q(role="error_detection")]
        valid, rejected = validate_grade_appropriateness(questions, grade_num=99)
        assert len(valid) == 1
