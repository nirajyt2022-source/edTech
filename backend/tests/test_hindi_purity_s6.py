"""Tests for Sprint S6 — Hindi Script Purity (Full Pipeline).

Covers:
  S6.1 — English allowlist (false positive reduction)
  S6.2 — Expanded transliteration blocklist
  S6.3 — MCQ options check (CHECK 10c)
  S6.4 — Question text sets _hindi_impure flag
"""

from app.services.quality_reviewer import (
    _has_hindi_code_mixing,
    _has_hindi_transliteration,
    _HINDI_ENGLISH_ALLOWLIST,
    _HINDI_TRANSLITERATION_BLOCKLIST,
    QualityReviewerAgent,
)
from app.services.topic_intelligence import GenerationContext


def _make_context(subject="Hindi", grade=3, topic="संज्ञा"):
    """Create a minimal GenerationContext for testing."""
    return GenerationContext(
        topic_slug=topic,
        subject=subject,
        grade=grade,
        ncert_chapter=topic,
        ncert_subtopics=["objective_1"],
        bloom_level="recall",
        format_mix={"mcq": 3, "fill_blank": 2},
        scaffolding=False,
        challenge_mode=False,
        valid_skill_tags=[],
        child_context={},
    )


# ---------------------------------------------------------------------------
# S6.1 — English Allowlist
# ---------------------------------------------------------------------------


class TestEnglishAllowlist:
    def test_tv_not_flagged(self):
        """TV is in allowlist — should not trigger code-mixing."""
        assert not _has_hindi_code_mixing("घर में TV है।")

    def test_ncert_not_flagged(self):
        assert not _has_hindi_code_mixing("NCERT की किताब पढ़ो।")

    def test_km_not_flagged(self):
        assert not _has_hindi_code_mixing("दूरी 5 km है।")

    def test_cbse_not_flagged(self):
        assert not _has_hindi_code_mixing("CBSE पाठ्यक्रम।")

    def test_multiple_allowlisted_ok(self):
        assert not _has_hindi_code_mixing("TV और AC दोनों चालू हैं।")

    def test_actual_english_still_flagged(self):
        """Real English words bypass allowlist and trigger detection."""
        assert _has_hindi_code_mixing("कितने pencils हैं?")

    def test_mixed_allowed_and_disallowed(self):
        """Allowlisted word + real English word → still flagged."""
        assert _has_hindi_code_mixing("TV पर pencils दिखाओ।")

    def test_allowlist_has_expected_entries(self):
        for word in ("TV", "AC", "DNA", "NCERT", "CBSE", "km", "cm", "kg", "ml"):
            assert word in _HINDI_ENGLISH_ALLOWLIST, f"{word} missing from allowlist"


# ---------------------------------------------------------------------------
# S6.2 — Expanded Transliteration Blocklist
# ---------------------------------------------------------------------------


class TestExpandedBlocklist:
    def test_color_detected(self):
        assert _has_hindi_transliteration("यह रेड रंग है।")

    def test_animal_detected(self):
        assert _has_hindi_transliteration("वह डॉग है।")

    def test_school_item_detected(self):
        assert _has_hindi_transliteration("मेरा शार्पनर कहाँ है?")

    def test_food_detected(self):
        assert _has_hindi_transliteration("एक गिलास पानी दो।")

    def test_llm_verb_detected(self):
        assert _has_hindi_transliteration("इसे कैलकुलेट करो।")

    def test_body_part_detected(self):
        assert _has_hindi_transliteration("अपना हैंड उठाओ।")

    def test_blocklist_size(self):
        """Blocklist should have grown to ~80+ words."""
        assert len(_HINDI_TRANSLITERATION_BLOCKLIST) >= 70

    def test_clean_hindi_not_flagged(self):
        assert not _has_hindi_transliteration("यह एक शुद्ध हिंदी वाक्य है।")


# ---------------------------------------------------------------------------
# S6.3 — MCQ Options Check (CHECK 10c)
# ---------------------------------------------------------------------------


class TestMCQOptionsCheck:
    def test_impure_option_sets_flag(self):
        """MCQ option with Latin code-mixing → _hindi_impure."""
        ctx = _make_context()
        questions = [
            {
                "id": "Q1",
                "question_text": "सही उत्तर चुनो।",
                "slot_type": "recognition",
                "format": "mcq",
                "answer": "कलम",
                "options": ["कलम", "दो pencils", "किताब", "कॉपी"],
            }
        ]
        reviewer = QualityReviewerAgent()
        reviewer.review_worksheet(questions, ctx)
        assert questions[0].get("_hindi_impure") is True

    def test_impure_translit_option_auto_fixed(self):
        """MCQ option with transliteration → auto-replaced (Hindi subject)."""
        ctx = _make_context(subject="Hindi")
        questions = [
            {
                "id": "Q1",
                "question_text": "सही रंग चुनो।",
                "slot_type": "recognition",
                "format": "mcq",
                "answer": "लाल",
                "options": ["लाल", "रेड", "नीला", "हरा"],
            }
        ]
        reviewer = QualityReviewerAgent()
        result = reviewer.review_worksheet(questions, ctx)
        # "रेड" should be auto-replaced with "लाल", not flagged
        assert "रेड" not in questions[0]["options"]
        assert questions[0].get("_hindi_impure") is not True

    def test_clean_options_no_flag(self):
        """All-Hindi MCQ options → no _hindi_impure."""
        ctx = _make_context()
        questions = [
            {
                "id": "Q1",
                "question_text": "सही उत्तर चुनो।",
                "slot_type": "recognition",
                "format": "mcq",
                "answer": "कलम",
                "options": ["कलम", "किताब", "कॉपी", "पेन"],
            }
        ]
        reviewer = QualityReviewerAgent()
        reviewer.review_worksheet(questions, ctx)
        assert questions[0].get("_hindi_impure") is not True

    def test_no_options_field_no_crash(self):
        """Question without options field → no crash."""
        ctx = _make_context()
        questions = [
            {
                "id": "Q1",
                "question_text": "यह एक प्रश्न है।",
                "slot_type": "recognition",
                "format": "short_answer",
                "answer": "उत्तर",
            }
        ]
        reviewer = QualityReviewerAgent()
        reviewer.review_worksheet(questions, ctx)
        assert questions[0].get("_hindi_impure") is not True


# ---------------------------------------------------------------------------
# S6.4 — Question Text Sets _hindi_impure
# ---------------------------------------------------------------------------


class TestQuestionTextImpureFlag:
    def test_code_mixing_in_question_sets_flag(self):
        """Latin code-mixing in question_text → _hindi_impure AND _needs_regen."""
        ctx = _make_context()
        questions = [
            {
                "id": "Q1",
                "question_text": "कितने pencils हैं?",
                "slot_type": "application",
                "format": "word_problem",
                "answer": "5",
            }
        ]
        reviewer = QualityReviewerAgent()
        reviewer.review_worksheet(questions, ctx)
        assert questions[0].get("_hindi_impure") is True
        assert questions[0].get("_needs_regen") is True

    def test_transliteration_in_question_auto_fixed(self):
        """Transliteration in question_text (Hindi subject) → auto-replaced."""
        ctx = _make_context(subject="Hindi")
        questions = [
            {
                "id": "Q1",
                "question_text": "इसमें कितने पेंसिल हैं?",
                "slot_type": "application",
                "format": "word_problem",
                "answer": "3",
            }
        ]
        reviewer = QualityReviewerAgent()
        reviewer.review_worksheet(questions, ctx)
        # "पेंसिल" should be auto-replaced with "कलम"
        assert "पेंसिल" not in questions[0]["question_text"]
        assert "कलम" in questions[0]["question_text"]
        # Should NOT be flagged for regen since it was auto-fixed
        assert questions[0].get("_hindi_impure") is not True

    def test_unknown_transliteration_still_flags(self):
        """Transliteration NOT in auto-fix dict → still flagged for regen."""
        ctx = _make_context(subject="Hindi")
        questions = [
            {
                "id": "Q1",
                "question_text": "इसमें कितने कंप्यूटर हैं?",
                "slot_type": "application",
                "format": "word_problem",
                "answer": "3",
            }
        ]
        reviewer = QualityReviewerAgent()
        reviewer.review_worksheet(questions, ctx)
        # "कंप्यूटर" is in blocklist but NOT in auto-fix dict → still flagged
        assert questions[0].get("_hindi_impure") is True
        assert questions[0].get("_needs_regen") is True

    def test_clean_question_no_flag(self):
        """Pure Hindi question → no _hindi_impure."""
        ctx = _make_context()
        questions = [
            {
                "id": "Q1",
                "question_text": "यह एक शुद्ध हिंदी प्रश्न है।",
                "slot_type": "recognition",
                "format": "short_answer",
                "answer": "उत्तर",
            }
        ]
        reviewer = QualityReviewerAgent()
        reviewer.review_worksheet(questions, ctx)
        assert questions[0].get("_hindi_impure") is not True

    def test_allowlisted_in_question_no_flag(self):
        """Allowlisted abbreviation in question → no _hindi_impure."""
        ctx = _make_context()
        questions = [
            {
                "id": "Q1",
                "question_text": "NCERT की किताब में क्या लिखा है?",
                "slot_type": "recognition",
                "format": "short_answer",
                "answer": "उत्तर",
            }
        ]
        reviewer = QualityReviewerAgent()
        reviewer.review_worksheet(questions, ctx)
        assert questions[0].get("_hindi_impure") is not True
