"""
Tests for render integrity checks — CHECK 21 (quality_reviewer),
check #23 (output_validator), R20 (release_gate), CONTENT_12 (quality_scorer).
"""

import pytest


# ---------------------------------------------------------------------------
# Regex pattern tests (module-level patterns from quality_reviewer)
# ---------------------------------------------------------------------------


class TestRenderIntegrityPatterns:
    """Test _VISUAL_REF_RE and _TABLE_REF_RE patterns."""

    @pytest.fixture(autouse=True)
    def _load_patterns(self):
        from app.services.quality_reviewer import _TABLE_REF_RE, _VISUAL_REF_RE

        self.visual_re = _VISUAL_REF_RE
        self.table_re = _TABLE_REF_RE

    def test_visual_ref_matches(self):
        assert self.visual_re.search("Look at the picture and answer")
        assert self.visual_re.search("See the diagram below")
        assert self.visual_re.search("Observe the number line")
        assert self.visual_re.search("Refer to the table")
        assert self.visual_re.search("Study the chart carefully")

    def test_visual_ref_no_false_positive(self):
        assert not self.visual_re.search("Add 23 and 45")
        assert not self.visual_re.search("What is the sum of 5 and 3?")
        assert not self.visual_re.search("Help Aarav solve this problem")

    def test_table_ref_matches(self):
        assert self.table_re.search("the following table shows prices")
        assert self.table_re.search("given chart of student marks")
        assert self.table_re.search("below diagram shows the fractions")

    def test_table_ref_no_false_positive(self):
        assert not self.table_re.search("Fill in the blanks")
        assert not self.table_re.search("What comes after 5?")


# ---------------------------------------------------------------------------
# OutputValidator check #23
# ---------------------------------------------------------------------------


class TestOutputValidatorRenderIntegrity:
    """Test check #23 in OutputValidator."""

    def _validate(self, questions, **kwargs):
        from app.services.output_validator import get_validator

        v = get_validator()
        return v.validate_worksheet(
            {"questions": questions},
            grade=kwargs.get("grade", "Class 3"),
            subject=kwargs.get("subject", "Maths"),
            topic=kwargs.get("topic", "Addition (carries)"),
            num_questions=kwargs.get("num_questions", len(questions)),
        )

    def test_phantom_ref_flagged(self):
        """Question referencing a visual with no visual attached should be flagged."""
        questions = [
            {
                "id": "Q1",
                "text": "Look at the picture and count the apples",
                "type": "short_answer",
                "correct_answer": "5",
            }
        ]
        _valid, errors = self._validate(questions, num_questions=1)
        render_errors = [e for e in errors if "render integrity" in e.lower() or "phantom" in e.lower()]
        assert len(render_errors) >= 1

    def test_visual_present_no_flag(self):
        """Question with visual_type set should NOT be flagged."""
        questions = [
            {
                "id": "Q1",
                "text": "Look at the picture and count the apples",
                "type": "short_answer",
                "correct_answer": "5",
                "visual_type": "object_group",
                "visual_data": {"groups": [{"count": 5, "object": "apple"}]},
            }
        ]
        _valid, errors = self._validate(questions, num_questions=1)
        render_errors = [e for e in errors if "render integrity" in e.lower() or "phantom" in e.lower()]
        assert len(render_errors) == 0

    def test_no_ref_no_flag(self):
        """Normal question with no visual reference should not be flagged."""
        questions = [
            {
                "id": "Q1",
                "text": "What is 23 + 45?",
                "type": "short_answer",
                "correct_answer": "68",
            }
        ]
        _valid, errors = self._validate(questions, num_questions=1)
        render_errors = [e for e in errors if "phantom" in e.lower()]
        assert len(render_errors) == 0


# ---------------------------------------------------------------------------
# Release Gate R20
# ---------------------------------------------------------------------------


class TestReleaseGateR20:
    """Test R20_RENDER_INTEGRITY rule."""

    def _run_gate(self, questions, grade_level="Class 3", subject="Maths"):
        from app.services.release_gate import run_release_gate

        return run_release_gate(
            questions=questions,
            grade_level=grade_level,
            subject=subject,
            topic="Addition (carries)",
            num_questions=len(questions),
            difficulty="medium",
            warnings=[],
        )

    def test_r20_passes_no_phantoms(self):
        questions = [
            {"id": "Q1", "text": "What is 5 + 3?", "type": "short_answer", "correct_answer": "8"},
        ]
        verdict = self._run_gate(questions)
        r20_results = [r for r in verdict.rule_results if r.rule_name == "R20_RENDER_INTEGRITY"]
        assert len(r20_results) == 1
        assert r20_results[0].passed is True

    def test_r20_degrade_on_phantom(self):
        questions = [
            {
                "id": "Q1",
                "text": "What is 5 + 3?",
                "type": "short_answer",
                "correct_answer": "8",
                "_phantom_visual_ref": True,
            },
        ]
        verdict = self._run_gate(questions, grade_level="Class 3")
        r20_results = [r for r in verdict.rule_results if r.rule_name == "R20_RENDER_INTEGRITY"]
        assert len(r20_results) == 1
        assert r20_results[0].passed is False

    def test_r20_block_class1(self):
        """Class 1-2 with phantom refs should BLOCK."""
        questions = [
            {
                "id": "Q1",
                "text": "Look at the picture",
                "type": "short_answer",
                "correct_answer": "5",
                "_phantom_visual_ref": True,
            },
        ]
        verdict = self._run_gate(questions, grade_level="Class 1")
        r20_results = [r for r in verdict.rule_results if r.rule_name == "R20_RENDER_INTEGRITY"]
        assert len(r20_results) == 1
        assert r20_results[0].passed is False
        # Should be BLOCK enforcement for Class 1
        from app.services.release_gate import Enforcement

        assert r20_results[0].enforcement == Enforcement.BLOCK


# ---------------------------------------------------------------------------
# Quality Scorer CONTENT_12
# ---------------------------------------------------------------------------


class TestQualityScorerContent12:
    """Test CONTENT_12 phantom visual flag check."""

    def test_content_12_flag_deduction(self):
        from app.services.quality_scorer import score_worksheet

        worksheet = {
            "grade": "Class 3",
            "subject": "Maths",
            "topic": "Addition (carries)",
            "learning_objectives": ["Add numbers"],
            "chapter_ref": "Chapter 3",
            "skill_focus": "addition",
            "questions": [
                {
                    "id": "Q1",
                    "text": "What is 5 + 3?",
                    "type": "short_answer",
                    "correct_answer": "8",
                    "role": "application",
                    "_phantom_visual_ref": True,
                },
            ],
        }
        result = score_worksheet(worksheet, expected_count=1)
        content_12 = [f for f in result.failures if f.check_id == "CONTENT_12"]
        assert len(content_12) >= 1
        assert content_12[0].severity == "major"
        assert content_12[0].points_deducted == 0.15

    def test_no_flag_no_deduction(self):
        from app.services.quality_scorer import score_worksheet

        worksheet = {
            "grade": "Class 3",
            "subject": "Maths",
            "topic": "Addition (carries)",
            "learning_objectives": ["Add numbers"],
            "chapter_ref": "Chapter 3",
            "skill_focus": "addition",
            "questions": [
                {
                    "id": "Q1",
                    "text": "What is 5 + 3?",
                    "type": "short_answer",
                    "correct_answer": "8",
                    "role": "application",
                },
            ],
        }
        result = score_worksheet(worksheet, expected_count=1)
        content_12 = [f for f in result.failures if f.check_id == "CONTENT_12"]
        assert len(content_12) == 0


# ---------------------------------------------------------------------------
# R19 CURRICULUM_DEPTH stamp
# ---------------------------------------------------------------------------


class TestReleaseGateR19:
    """Test R19_CURRICULUM_DEPTH stamp."""

    def test_r19_stamps_depth(self):
        from app.services.release_gate import run_release_gate

        verdict = run_release_gate(
            questions=[{"id": "Q1", "text": "What is 5+3?", "type": "short_answer", "correct_answer": "8"}],
            grade_level="Class 1",
            subject="Maths",
            topic="Addition up to 20",
            num_questions=1,
            difficulty="easy",
            warnings=[],
        )
        assert "curriculum_depth" in verdict.stamps
        # This topic exists in ncert_alignment.json, so should be "full" or "partial"
        assert verdict.stamps["curriculum_depth"] in ("full", "partial")

    def test_r19_unknown_topic_none(self):
        from app.services.release_gate import run_release_gate

        verdict = run_release_gate(
            questions=[{"id": "Q1", "text": "Test", "type": "short_answer", "correct_answer": "x"}],
            grade_level="Class 99",
            subject="Maths",
            topic="Nonexistent Topic XYZ",
            num_questions=1,
            difficulty="easy",
            warnings=[],
        )
        assert verdict.stamps.get("curriculum_depth") == "none"
