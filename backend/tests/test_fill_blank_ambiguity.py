"""Tests for S2.3 — Ambiguous Fill-in-the-Blank Detector (CHECK 20, check #22, R18, CONTENT_11)."""

import pytest

from app.services.quality_reviewer import _FB_BLANK_RE, _FB_GENERIC_ANSWERS, _FB_SUBJECTIVE_RE
from app.services.output_validator import get_validator
from app.services.release_gate import run_release_gate
from app.services.quality_scorer import score_worksheet


# ---------------------------------------------------------------------------
# Unit: Module-level patterns
# ---------------------------------------------------------------------------


class TestFillBlankPatterns:
    @pytest.mark.parametrize("text,expected", [
        ("The capital of India is ______.", True),
        ("Fill: 2 + 3 = ___", True),
        ("What is 2+3...", True),
        ("What is [blank]?", True),
        ("What is [___]?", True),
        ("Normal question with no blank", False),
        ("A single _ is fine", False),
    ])
    def test_blank_marker_detection(self, text, expected):
        assert bool(_FB_BLANK_RE.search(text)) == expected

    @pytest.mark.parametrize("word,expected", [
        ("the", True),
        ("is", True),
        ("photosynthesis", False),
        ("Delhi", False),
    ])
    def test_generic_answer(self, word, expected):
        assert (word in _FB_GENERIC_ANSWERS) == expected

    @pytest.mark.parametrize("text,expected", [
        ("Write a word of your choice", True),
        ("Name any animal", True),
        ("Your favourite colour is", True),
        ("The capital of India is", False),
    ])
    def test_subjective_detection(self, text, expected):
        assert bool(_FB_SUBJECTIVE_RE.search(text)) == expected


# ---------------------------------------------------------------------------
# Integration: OutputValidator check #22
# ---------------------------------------------------------------------------


class TestOVCheck22:
    def test_missing_blank_marker(self):
        validator = get_validator()
        data = {
            "questions": [
                {"id": "Q1", "text": "The capital of India is Delhi", "type": "fill_blank", "correct_answer": "Delhi"},
            ]
        }
        _, errors = validator.validate_worksheet(data, grade="Class 3", subject="English", num_questions=1)
        assert any("missing blank marker" in e for e in errors)

    def test_subjective_prompt(self):
        validator = get_validator()
        data = {
            "questions": [
                {"id": "Q1", "text": "Write any word that starts with A ______.", "type": "fill_blank", "correct_answer": "apple"},
            ]
        }
        _, errors = validator.validate_worksheet(data, grade="Class 3", subject="English", num_questions=1)
        assert any("subjective" in e for e in errors)

    def test_generic_answer(self):
        validator = get_validator()
        data = {
            "questions": [
                {"id": "Q1", "text": "He ______ a boy.", "type": "fill_blank", "correct_answer": "is"},
            ]
        }
        _, errors = validator.validate_worksheet(data, grade="Class 3", subject="English", num_questions=1)
        assert any("generic" in e for e in errors)

    def test_clean_fill_blank_passes(self):
        validator = get_validator()
        data = {
            "questions": [
                {"id": "Q1", "text": "The capital of India is ______.", "type": "fill_blank", "correct_answer": "Delhi"},
            ]
        }
        _, errors = validator.validate_worksheet(data, grade="Class 3", subject="English", num_questions=1)
        fb_errors = [e for e in errors if "fill-blank" in e]
        assert len(fb_errors) == 0


# ---------------------------------------------------------------------------
# Integration: R18 release gate
# ---------------------------------------------------------------------------


class TestR18FillBlankAmbiguity:
    def _make_fill_blanks(self, n, ambiguous_indices=None):
        questions = []
        for i in range(n):
            q = {
                "id": f"Q{i + 1}",
                "text": "The answer is ______.",
                "type": "fill_blank",
                "correct_answer": f"answer{i}",
            }
            if ambiguous_indices and i in ambiguous_indices:
                q["_fill_blank_ambiguous"] = True
            questions.append(q)
        return questions

    def test_r18_passes_clean(self):
        verdict = run_release_gate(
            questions=self._make_fill_blanks(5),
            grade_level="Class 3",
            subject="English",
            topic="Nouns",
            num_questions=5,
            difficulty="medium",
            warnings=[],
        )
        r18 = next(r for r in verdict.rule_results if r.rule_name == "R18_FILL_BLANK_AMBIGUITY")
        assert r18.passed

    def test_r18_skips_too_few(self):
        verdict = run_release_gate(
            questions=self._make_fill_blanks(1, ambiguous_indices=[0]),
            grade_level="Class 3",
            subject="English",
            topic="Nouns",
            num_questions=1,
            difficulty="medium",
            warnings=[],
        )
        r18 = next(r for r in verdict.rule_results if r.rule_name == "R18_FILL_BLANK_AMBIGUITY")
        assert r18.passed  # Too few → skip

    def test_r18_degrades_high_ratio(self):
        # 3 out of 5 = 60% ambiguous → should degrade
        verdict = run_release_gate(
            questions=self._make_fill_blanks(5, ambiguous_indices=[0, 1, 2]),
            grade_level="Class 3",
            subject="English",
            topic="Nouns",
            num_questions=5,
            difficulty="medium",
            warnings=[],
        )
        r18 = next(r for r in verdict.rule_results if r.rule_name == "R18_FILL_BLANK_AMBIGUITY")
        assert not r18.passed
        assert r18.enforcement.value == "degrade"


# ---------------------------------------------------------------------------
# Integration: CONTENT_11 scorer
# ---------------------------------------------------------------------------


class TestContent11Scorer:
    def test_fill_blank_ambiguous_flag(self):
        ws = {
            "grade": "Class 3",
            "subject": "English",
            "topic": "Nouns",
            "questions": [
                {"id": "Q1", "text": "He ______ a boy.", "type": "fill_blank", "correct_answer": "is", "_fill_blank_ambiguous": True},
                {"id": "Q2", "text": "Delhi is the ______ of India.", "type": "fill_blank", "correct_answer": "capital"},
            ],
        }
        result = score_worksheet(ws)
        content_11 = [f for f in result.failures if f.check_id == "CONTENT_11"]
        assert len(content_11) >= 1
        assert content_11[0].severity == "minor"
