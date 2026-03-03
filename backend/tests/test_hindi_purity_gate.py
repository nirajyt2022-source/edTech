"""Tests for S2.2 — Hindi Script Purity (CHECK 10b, R17, CONTENT_10)."""

from app.services.quality_reviewer import (
    _has_hindi_code_mixing,
    _has_hindi_transliteration,
)
from app.services.release_gate import run_release_gate
from app.services.quality_scorer import score_worksheet


# ---------------------------------------------------------------------------
# Unit: _has_hindi_code_mixing on answer/hint fields
# ---------------------------------------------------------------------------


class TestHindiCodeMixingDetection:
    def test_clean_hindi_text(self):
        assert not _has_hindi_code_mixing("यह एक शुद्ध हिंदी वाक्य है।")

    def test_latin_in_devanagari(self):
        assert _has_hindi_code_mixing("कितने pencils हैं?")

    def test_pure_english(self):
        """Pure English text should not trigger (no Devanagari)."""
        assert not _has_hindi_code_mixing("How many pencils are there?")

    def test_single_latin_char_ignored(self):
        """Single Latin char should not trigger (regex requires 2+)."""
        assert not _has_hindi_code_mixing("A और B में अंतर बताओ")


class TestHindiTransliterationDetection:
    def test_clean_hindi(self):
        assert not _has_hindi_transliteration("यह एक शुद्ध हिंदी वाक्य है।")

    def test_transliterated_word(self):
        assert _has_hindi_transliteration("इसमें कितने पेंसिल हैं?")

    def test_pure_english_skipped(self):
        assert not _has_hindi_transliteration("This is English")


# ---------------------------------------------------------------------------
# Integration: R17 release gate rule
# ---------------------------------------------------------------------------


class TestR17HindiScriptPurity:
    def _make_questions(self, n=5, impure_indices=None):
        questions = []
        for i in range(n):
            q = {
                "id": f"Q{i + 1}",
                "text": f"प्रश्न {i + 1}",
                "type": "short_answer",
                "correct_answer": "उत्तर",
            }
            if impure_indices and i in impure_indices:
                q["_hindi_impure"] = True
            questions.append(q)
        return questions

    def test_r17_passes_clean(self):
        verdict = run_release_gate(
            questions=self._make_questions(5),
            grade_level="Class 3",
            subject="Hindi",
            topic="संज्ञा",
            num_questions=5,
            difficulty="medium",
            warnings=[],
        )
        failed_names = [r.rule_name for r in verdict.rule_results if not r.passed]
        assert "R17_HINDI_SCRIPT_PURITY" not in failed_names

    def test_r17_blocks_hindi_subject(self):
        verdict = run_release_gate(
            questions=self._make_questions(5, impure_indices=[0, 1]),
            grade_level="Class 3",
            subject="Hindi",
            topic="संज्ञा",
            num_questions=5,
            difficulty="medium",
            warnings=[],
        )
        r17 = next(r for r in verdict.rule_results if r.rule_name == "R17_HINDI_SCRIPT_PURITY")
        assert not r17.passed
        assert r17.enforcement.value == "block"

    def test_r17_degrades_non_hindi_subject(self):
        verdict = run_release_gate(
            questions=self._make_questions(5, impure_indices=[0]),
            grade_level="Class 3",
            subject="Maths",
            topic="addition",
            num_questions=5,
            difficulty="medium",
            warnings=[],
        )
        r17 = next(r for r in verdict.rule_results if r.rule_name == "R17_HINDI_SCRIPT_PURITY")
        assert not r17.passed
        assert r17.enforcement.value == "degrade"


# ---------------------------------------------------------------------------
# Integration: CONTENT_10 scorer
# ---------------------------------------------------------------------------


class TestContent10Scorer:
    def test_hindi_impure_flag_deducts(self):
        ws = {
            "grade": "Class 3",
            "subject": "Hindi",
            "topic": "संज्ञा",
            "questions": [
                {"id": "Q1", "text": "प्रश्न 1", "type": "short_answer", "correct_answer": "उत्तर", "_hindi_impure": True},
                {"id": "Q2", "text": "प्रश्न 2", "type": "short_answer", "correct_answer": "उत्तर"},
            ],
        }
        result = score_worksheet(ws)
        content_10 = [f for f in result.failures if f.check_id == "CONTENT_10"]
        assert len(content_10) >= 1
        assert content_10[0].severity == "major"

    def test_no_flag_no_deduction(self):
        ws = {
            "grade": "Class 3",
            "subject": "Hindi",
            "topic": "संज्ञा",
            "questions": [
                {"id": "Q1", "text": "प्रश्न 1", "type": "short_answer", "correct_answer": "उत्तर"},
            ],
        }
        result = score_worksheet(ws)
        content_10 = [f for f in result.failures if f.check_id == "CONTENT_10"]
        assert len(content_10) == 0
