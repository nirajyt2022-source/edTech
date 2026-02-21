"""Tests for quality_gate.run_quality_gate() — all 12 checks."""
import pytest
from app.utils.quality_gate import (
    run_quality_gate, jaccard, extract_times, _content_words, _is_mcq_letter,
    _OCLOCK_RE,
)


# ── Helper builders ───────────────────────────────────────────────────────────

def _make_q(n: int, text: str, answer: str = "42", hint: str = "") -> dict:
    return {
        "display_number": n,
        "question": text,
        "correct_answer": answer,
        "hint": hint,
    }


def _worksheet(questions, grade="Class 3", requested=None, answer_key=None):
    ws = {
        "grade": grade,
        "questions": questions,
    }
    if requested is not None:
        ws["requested_count"] = requested
    if answer_key is not None:
        ws["answer_key"] = answer_key
    return ws


# ── Check 1: Count ────────────────────────────────────────────────────────────

class TestCount:
    def test_correct_count_passes(self):
        # Use unrelated questions so the duplicate check does not fire
        qs = [
            _make_q(1, "What colour is the sky on a sunny day?", "blue"),
            _make_q(2, "How many legs does a spider have?", "eight"),
            _make_q(3, "Name the capital of India.", "Delhi"),
            _make_q(4, "Which fruit is red and round?", "apple"),
            _make_q(5, "How many days are there in one week?", "seven"),
        ]
        passed, issues = run_quality_gate(_worksheet(qs, requested=5))
        assert passed is True, f"Expected pass but got: {issues}"
        assert issues == []

    def test_short_count_fails(self):
        qs = [_make_q(i, f"What is {i} + 1?", str(i + 1)) for i in range(1, 4)]
        passed, issues = run_quality_gate(_worksheet(qs, requested=5))
        assert passed is False
        assert any("COUNT" in i for i in issues)
        assert any("3" in i and "5" in i for i in issues)


# ── Check 2: Answer key alignment ────────────────────────────────────────────

class TestAnswerKeyAlignment:
    def test_matching_key_passes(self):
        qs = [_make_q(1, "What is 5 + 3?", "8")]
        key = {"Q1": "8"}
        passed, issues = run_quality_gate(_worksheet(qs, answer_key=key))
        assert passed is True
        assert issues == []

    def test_mismatched_key_fails(self):
        qs = [_make_q(1, "What is 5 + 3?", "8")]
        key = {"Q1": "9"}                   # deliberately wrong key
        passed, issues = run_quality_gate(_worksheet(qs, answer_key=key))
        assert passed is False
        assert any("KEY_MISMATCH" in i for i in issues), issues
        assert any("Q1" in i for i in issues)
        assert any("'9'" in i for i in issues)
        assert any("'8'" in i for i in issues)

    def test_no_key_entry_is_skipped(self):
        """If answer_key has no entry for a question it should not be checked."""
        qs = [_make_q(1, "What is 5 + 3?", "8")]
        passed, issues = run_quality_gate(_worksheet(qs, answer_key={}))
        assert passed is True
        assert issues == []


# ── Check 3: Duplicate questions ─────────────────────────────────────────────

class TestDuplicates:
    def test_distinct_questions_pass(self):
        qs = [
            _make_q(1, "How many apples does Ravi have after buying 3 more?", "5"),
            _make_q(2, "What is the area of a rectangle with length 4 and width 6?", "24"),
        ]
        passed, issues = run_quality_gate(_worksheet(qs))
        assert passed is True
        assert issues == []

    def test_near_identical_questions_fail(self):
        # Same sentence — jaccard = 1.0 > 0.50
        qs = [
            _make_q(1, "What is the sum of 47 and 35?", "82"),
            _make_q(2, "What is the sum of 47 and 35?", "82"),
        ]
        passed, issues = run_quality_gate(_worksheet(qs))
        assert passed is False
        assert any("DUPLICATE" in i for i in issues), issues

    def test_jaccard_threshold_is_050(self):
        # 5/7 ≈ 0.71 — well above the 0.50 threshold, should still fail
        a = "dog cat bird fish whale shark"       # 6 unique words
        b = "dog cat bird fish whale eagle"       # 5 shared, 1 different → 5/7 ≈ 0.71
        assert jaccard(a, b) > 0.50
        qs = [_make_q(1, a, "x"), _make_q(2, b, "y")]
        passed, issues = run_quality_gate(_worksheet(qs))
        assert passed is False
        assert any("DUPLICATE" in i for i in issues)

    def test_duplicate_times_detected(self):
        qs = [
            _make_q(1, "The school opens at 8:00 AM and closes at 4:00 PM.", "8h"),
            _make_q(2, "The school opens at 8:00 AM and closes at 4:00 PM.", "8h"),
        ]
        passed, issues = run_quality_gate(_worksheet(qs))
        assert passed is False
        # Either DUPLICATE (jaccard) or DUPLICATE_TIMES should fire
        assert any("DUPLICATE" in i for i in issues), issues

    def test_concept_duplicate_same_keyword(self):
        # Different phrasing but same content word "कुर्सी" (a chair in Hindi) — jaccard < 0.50
        qs = [
            _make_q(1, "कुर्सी का रंग क्या है?", "भूरा"),
            _make_q(2, "यह कुर्सी किस चीज़ से बनी है?", "लकड़ी"),
        ]
        passed, issues = run_quality_gate(_worksheet(qs))
        assert passed is False
        assert any("CONCEPT_DUPLICATE" in i for i in issues), issues

    def test_concept_duplicate_english_content_word(self):
        # Both questions reference "rectangle" — same concept, different aspects
        qs = [
            _make_q(1, "What is the perimeter of a rectangle with sides 3 and 5?", "16"),
            _make_q(2, "Find the area of a rectangle whose length is 6 and width is 4.", "24"),
        ]
        passed, issues = run_quality_gate(_worksheet(qs))
        assert passed is False
        assert any("CONCEPT_DUPLICATE" in i for i in issues), issues
        assert any("rectangle" in i for i in issues)

    def test_short_common_words_do_not_trigger_concept_duplicate(self):
        # Words like "many", "does", "have" are 4 chars — below the > 4 threshold
        qs = [
            _make_q(1, "How many legs does a dog have?", "4"),
            _make_q(2, "How many days are there in one week?", "7"),
        ]
        passed, issues = run_quality_gate(_worksheet(qs))
        # No CONCEPT_DUPLICATE — "many" is 4 chars, not > 4
        assert not any("CONCEPT_DUPLICATE" in i for i in issues), issues


# ── Check 4: Grade appropriateness ───────────────────────────────────────────

class TestGradeAppropriateness:
    def test_class_1_clean_passes(self):
        qs = [_make_q(1, "Circle the bigger number: 3 or 7.", "7")]
        passed, issues = run_quality_gate(_worksheet(qs, grade="Class 1"))
        assert passed is True
        assert issues == []

    def test_class_2_explain_why_fails(self):
        qs = [_make_q(1, "Explain why 5 + 3 is the same as 3 + 5.", "commutative")]
        passed, issues = run_quality_gate(_worksheet(qs, grade="Class 2"))
        assert passed is False
        assert any("GRADE_VIOLATION" in i for i in issues), issues
        assert any("explain why" in i for i in issues)

    def test_class_1_forbidden_phrases_all_caught(self):
        forbidden = [
            "explain why it happens",
            "explain how this works",
            "what mistake did she make",
            "what error was found",
            "how many hours remain in the day",
            "how many seconds in a minute",
            "justify your answer",
            "give reason for your choice",
            "prove that this is correct",
            "compare and contrast the two",
        ]
        for phrase in forbidden:
            qs = [_make_q(1, f"Class 1 question: {phrase}.", "x")]
            passed, issues = run_quality_gate(_worksheet(qs, grade="Class 1"))
            assert passed is False, f"Expected failure for phrase: '{phrase}'"
            assert any("GRADE_VIOLATION" in i for i in issues)

    def test_class_3_allows_higher_order(self):
        qs = [_make_q(1, "Explain why 12 is a multiple of 3.", "because 3 x 4 = 12")]
        passed, issues = run_quality_gate(_worksheet(qs, grade="Class 3"))
        assert passed is True
        assert issues == []


# ── Check 5: Hint leak ────────────────────────────────────────────────────────

class TestHintLeak:
    def test_clean_hint_passes(self):
        q = _make_q(1, "What is 6 x 7?", "42", hint="Think about the 6 times table.")
        passed, issues = run_quality_gate(_worksheet([q]))
        assert passed is True
        assert issues == []

    def test_hint_containing_answer_fails(self):
        # Answer must be > 2 chars to trigger the hint-leak guard (spec: len(answer) > 2)
        q = _make_q(
            1,
            "What is 6 x 7?",
            answer="420",                             # 3 chars → triggers the check
            hint="The answer is 420, think carefully.",
        )
        passed, issues = run_quality_gate(_worksheet([q]))
        assert passed is False, f"Expected HINT_LEAK failure but gate passed with issues={issues}"
        assert any("HINT_LEAK" in i for i in issues), issues
        assert any("'420'" in i for i in issues)

    def test_short_answer_not_flagged(self):
        # Answers of 1-2 chars (e.g. "A", "B") should not trigger hint leak
        q = _make_q(1, "Which option is correct?", answer="A", hint="A is the first option.")
        passed, issues = run_quality_gate(_worksheet([q]))
        assert passed is True  # answer len <= 2, not checked
        assert issues == []

    def test_empty_hint_not_flagged(self):
        q = _make_q(1, "What is 6 x 7?", "42", hint="")
        passed, issues = run_quality_gate(_worksheet([q]))
        assert passed is True
        assert issues == []


# ── Check 6: Fallback stubs ───────────────────────────────────────────────────

class TestFallbackStub:
    def test_stub_question_fails(self):
        q = {
            "display_number": 1,
            "question": "[Generation failed for recognition question]",
            "correct_answer": "",
            "is_fallback": True,
        }
        passed, issues = run_quality_gate(_worksheet([q]))
        assert passed is False
        assert any("FALLBACK" in i for i in issues), issues
        assert any("Q1" in i for i in issues)
        assert any("stub" in i for i in issues)

    def test_normal_question_not_flagged(self):
        q = _make_q(1, "What is 3 + 4?", "7")
        passed, issues = run_quality_gate(_worksheet([q]))
        assert not any("FALLBACK" in i for i in issues)

    def test_fallback_false_not_flagged(self):
        """Explicit is_fallback=False must not trigger the check."""
        q = {
            "display_number": 2,
            "question": "What is 5 + 3?",
            "correct_answer": "8",
            "is_fallback": False,
        }
        passed, issues = run_quality_gate(_worksheet([q]))
        assert not any("FALLBACK" in i for i in issues)

    def test_multiple_stubs_all_reported(self):
        stubs = [
            {"display_number": i, "question": f"[stub {i}]", "correct_answer": "", "is_fallback": True}
            for i in range(1, 4)
        ]
        passed, issues = run_quality_gate(_worksheet(stubs))
        assert passed is False
        fallback_issues = [i for i in issues if "FALLBACK" in i]
        assert len(fallback_issues) == 3, f"Expected 3 FALLBACK issues, got: {issues}"


# ── Check 7: MCQ integrity ────────────────────────────────────────────────────

class TestMCQIntegrity:
    def test_valid_mcq_passes(self):
        q = {
            "display_number": 1,
            "question": "Which animal is a mammal?",
            "correct_answer": "B",
            "format": "mcq_3",
            "options": ["Fish", "Whale", "Eagle"],
        }
        passed, issues = run_quality_gate(_worksheet([q]))
        assert not any("MCQ_BROKEN" in i for i in issues), issues

    def test_null_options_fails(self):
        q = {
            "display_number": 1,
            "question": "Which planet is closest to the Sun?",
            "correct_answer": "A",
            "format": "mcq_3",
            "options": None,
        }
        passed, issues = run_quality_gate(_worksheet([q]))
        assert passed is False
        assert any("MCQ_BROKEN" in i for i in issues), issues
        assert any("null" in i or "empty" in i for i in issues)

    def test_empty_options_list_fails(self):
        q = {
            "display_number": 2,
            "question": "Which planet is largest?",
            "correct_answer": "A",
            "format": "mcq_4",
            "options": [],
        }
        passed, issues = run_quality_gate(_worksheet([q]))
        assert passed is False
        assert any("MCQ_BROKEN" in i for i in issues), issues

    def test_duplicate_options_fail(self):
        q = {
            "display_number": 3,
            "question": "What colour is the sky?",
            "correct_answer": "A",
            "format": "mcq_3",
            "options": ["Blue", "Blue", "Green"],   # Blue duplicated
        }
        passed, issues = run_quality_gate(_worksheet([q]))
        assert passed is False
        assert any("MCQ_BROKEN" in i for i in issues), issues
        assert any("duplicate" in i for i in issues)
        assert any("'Blue'" in i for i in issues)

    def test_letter_answer_out_of_range_fails(self):
        # correct_answer=C but only 2 options (A, B)
        q = {
            "display_number": 4,
            "question": "Pick the correct answer.",
            "correct_answer": "C",
            "format": "mcq_3",
            "options": ["Red", "Blue"],
        }
        passed, issues = run_quality_gate(_worksheet([q]))
        assert passed is False
        assert any("MCQ_BROKEN" in i for i in issues), issues
        assert any("'C'" in i for i in issues)
        assert any("2" in i for i in issues)

    def test_non_letter_answer_not_checked(self):
        # correct_answer is the full text, not a letter — no MCQ_BROKEN
        q = {
            "display_number": 5,
            "question": "What is 3 + 4?",
            "correct_answer": "Seven",
            "format": "mcq_3",
            "options": ["Five", "Six", "Seven"],
        }
        passed, issues = run_quality_gate(_worksheet([q]))
        assert not any("MCQ_BROKEN" in i for i in issues), issues

    def test_non_mcq_format_skipped(self):
        # fill_blank format — options check should not apply
        q = {
            "display_number": 6,
            "question": "3 + ___ = 10",
            "correct_answer": "7",
            "format": "fill_blank",
            "options": None,
        }
        passed, issues = run_quality_gate(_worksheet([q]))
        assert not any("MCQ_BROKEN" in i for i in issues), issues


# ── Check 8: Empty question text ─────────────────────────────────────────────

class TestEmptyQuestion:
    def test_empty_string_fails(self):
        q = {"display_number": 1, "question": "", "correct_answer": "7"}
        passed, issues = run_quality_gate(_worksheet([q]))
        assert passed is False
        assert any("EMPTY_QUESTION" in i for i in issues), issues
        assert any("Q1" in i for i in issues)

    def test_whitespace_only_fails(self):
        q = {"display_number": 2, "question": "   ", "correct_answer": "7"}
        passed, issues = run_quality_gate(_worksheet([q]))
        assert passed is False
        assert any("EMPTY_QUESTION" in i for i in issues), issues

    def test_none_text_fails(self):
        # All text fields absent — _q_text returns ""
        q = {"display_number": 3, "correct_answer": "7"}
        passed, issues = run_quality_gate(_worksheet([q]))
        assert passed is False
        assert any("EMPTY_QUESTION" in i for i in issues), issues

    def test_normal_question_passes(self):
        q = _make_q(1, "What is 3 + 4?", "7")
        passed, issues = run_quality_gate(_worksheet([q]))
        assert not any("EMPTY_QUESTION" in i for i in issues)

    def test_empty_catches_regardless_of_is_fallback(self):
        """EMPTY_QUESTION fires even when is_fallback is False."""
        q = {"display_number": 4, "question": "", "correct_answer": "", "is_fallback": False}
        passed, issues = run_quality_gate(_worksheet([q]))
        assert any("EMPTY_QUESTION" in i for i in issues), issues


# ── Check 9: Explanation leak ─────────────────────────────────────────────────

class TestExplanationLeak:
    def test_explanation_contains_answer_fails(self):
        q = {
            "display_number": 1,
            "question": "What is 6 x 7?",
            "correct_answer": "420",
            "explanation": "Think through carefully. The answer is 420.",
        }
        passed, issues = run_quality_gate(_worksheet([q]))
        assert passed is False
        assert any("EXPLANATION_LEAK" in i for i in issues), issues
        assert any("'420'" in i for i in issues)

    def test_clean_explanation_passes(self):
        q = {
            "display_number": 2,
            "question": "What is 6 x 7?",
            "correct_answer": "420",
            "explanation": "Multiply 6 by 7 step by step.",
        }
        passed, issues = run_quality_gate(_worksheet([q]))
        assert not any("EXPLANATION_LEAK" in i for i in issues), issues

    def test_short_answer_not_flagged(self):
        # Answer <= 2 chars ("A") — same guard as hint leak
        q = {
            "display_number": 3,
            "question": "Which option?",
            "correct_answer": "A",
            "explanation": "Option A is correct because it is the right one.",
        }
        passed, issues = run_quality_gate(_worksheet([q]))
        assert not any("EXPLANATION_LEAK" in i for i in issues)

    def test_no_explanation_not_flagged(self):
        q = _make_q(1, "What is 3 + 4?", "700")
        passed, issues = run_quality_gate(_worksheet([q]))
        assert not any("EXPLANATION_LEAK" in i for i in issues)


# ── Composite: worksheet that passes ALL checks ───────────────────────────────

class TestFullPassingWorksheet:
    def test_clean_worksheet_passes(self):
        qs = [
            _make_q(1, "Circle the number that comes after 5.", "6"),
            _make_q(2, "How many legs does a dog have?", "4", hint="Think of a dog running."),
            _make_q(3, "What is 3 + 4?", "7"),
            _make_q(4, "Which shape has 4 equal sides?", "square"),
            _make_q(5, "Count the apples: apple apple apple. How many?", "3"),
        ]
        ws = _worksheet(qs, grade="Class 2", requested=5)
        ws["answer_key"] = {f"Q{q['display_number']}": q["correct_answer"] for q in qs}
        passed, issues = run_quality_gate(ws)
        assert passed is True, f"Expected all checks to pass but got: {issues}"
        assert issues == []


# ── Unit tests for helpers ────────────────────────────────────────────────────

class TestHelpers:
    def test_jaccard_identical(self):
        assert jaccard("hello world", "hello world") == 1.0

    def test_jaccard_disjoint(self):
        assert jaccard("cat dog", "fish bird") == 0.0

    def test_jaccard_empty(self):
        assert jaccard("", "hello") == 0.0
        assert jaccard("hello", "") == 0.0

    def test_extract_times_finds_hhmm(self):
        t = extract_times("The train leaves at 8:30 AM and arrives at 10:45 AM.")
        assert "8:30 AM" in t
        assert "10:45 AM" in t

    def test_extract_times_empty(self):
        assert extract_times("No times here.") == frozenset()

    def test_content_words_filters_short(self):
        # Words with <= 4 chars should be excluded
        words = _content_words("What does many have legs")
        assert "what" not in words
        assert "does" not in words
        assert "many" not in words
        assert "have" not in words
        assert "legs" not in words

    def test_content_words_keeps_long(self):
        words = _content_words("rectangle triangle spider")
        assert "rectangle" in words
        assert "triangle" in words
        assert "spider" in words

    def test_content_words_no_digits(self):
        # Numbers like "47" should not appear
        words = _content_words("47 plus 35 equals 82")
        assert not any(w.isdigit() for w in words)

    def test_q_text_fallback_fields(self):
        from app.utils.quality_gate import _q_text
        assert _q_text({"question": "A"}) == "A"
        assert _q_text({"question_text": "B"}) == "B"
        assert _q_text({"text": "C"}) == "C"
        assert _q_text({}) == ""

    def test_q_number_fallback_to_id(self):
        from app.utils.quality_gate import _q_number
        assert _q_number({"display_number": 3}) == 3
        assert _q_number({"id": "q5"}) == 5
        assert _q_number({}, fallback=7) == 7

    def test_is_mcq_letter_true(self):
        assert _is_mcq_letter("A") is True
        assert _is_mcq_letter("b") is True   # case-insensitive
        assert _is_mcq_letter("C") is True
        assert _is_mcq_letter("d") is True

    def test_is_mcq_letter_false(self):
        assert _is_mcq_letter("E") is False          # not in A-D
        assert _is_mcq_letter("AB") is False         # two chars
        assert _is_mcq_letter("True") is False       # full word
        assert _is_mcq_letter("") is False           # empty


# ── Check 10: Consecutive same answers ───────────────────────────────────────

class TestConsecutiveAnswers:
    def test_distinct_answers_pass(self):
        qs = [
            _make_q(1, "Priya has some apples in her bag.", "python"),
            _make_q(2, "Ravi drinks fresh juice every morning.", "turtle"),
            _make_q(3, "The school library has many shelves.", "rabbit"),
            _make_q(4, "Birds chirp loudly at sunrise.", "giraffe"),
            _make_q(5, "Kiran drew a landscape picture.", "dolphin"),
        ]
        passed, issues = run_quality_gate(_worksheet(qs))
        assert not any("CONSECUTIVE_ANSWERS" in i for i in issues), issues

    def test_two_consecutive_passes(self):
        # Run of 2 is fine — threshold is 3
        qs = [
            _make_q(1, "Priya has some apples in her bag.", "white"),
            _make_q(2, "Ravi drinks fresh juice every morning.", "white"),
            _make_q(3, "The school library has many shelves.", "green"),
        ]
        passed, issues = run_quality_gate(_worksheet(qs))
        assert not any("CONSECUTIVE_ANSWERS" in i for i in issues), issues

    def test_three_consecutive_fails(self):
        # Classic tenses problem: LLM locks onto one answer for entire slot group
        qs = [
            _make_q(1, "Ravi speaks Hindi every day.", "Simple present tense"),
            _make_q(2, "The students walk to school.", "Simple present tense"),
            _make_q(3, "She reads a book before sleeping.", "Simple present tense"),
        ]
        passed, issues = run_quality_gate(_worksheet(qs))
        assert passed is False
        assert any("CONSECUTIVE_ANSWERS" in i for i in issues), issues
        assert any("Simple present tense" in i for i in issues)
        assert any("3 in a row" in i for i in issues)
        assert any("Q1" in i and "Q3" in i for i in issues)

    def test_five_consecutive_single_flag(self):
        # Five in a row should produce exactly one CONSECUTIVE_ANSWERS flag
        qs = [
            _make_q(1, "Ravi speaks Hindi every day.", "Simple present tense"),
            _make_q(2, "The students walk to school.", "Simple present tense"),
            _make_q(3, "She reads a book before sleeping.", "Simple present tense"),
            _make_q(4, "Birds chirp loudly at sunrise.", "Simple present tense"),
            _make_q(5, "Priya cooks delicious meals daily.", "Simple present tense"),
        ]
        passed, issues = run_quality_gate(_worksheet(qs))
        consecutive = [i for i in issues if "CONSECUTIVE_ANSWERS" in i]
        assert len(consecutive) == 1, f"Expected 1 CONSECUTIVE_ANSWERS, got: {issues}"
        assert "5 in a row" in consecutive[0]
        assert "Q1" in consecutive[0] and "Q5" in consecutive[0]

    def test_mcq_letters_excluded(self):
        # A,A,A,B,B,B — all single MCQ letters, exempt from the check
        qs = [
            _make_q(1, "A mammal that swims.", "A"),
            _make_q(2, "A bird with colourful feathers.", "A"),
            _make_q(3, "An insect with a hard shell.", "A"),
            _make_q(4, "The largest ocean creature.", "B"),
            _make_q(5, "The speediest bird alive.", "B"),
            _make_q(6, "An underwater breathing creature.", "B"),
        ]
        passed, issues = run_quality_gate(_worksheet(qs))
        assert not any("CONSECUTIVE_ANSWERS" in i for i in issues), issues

    def test_resets_after_break(self):
        # X, X, break, X, X — two separate runs of 2, never reaches 3
        qs = [
            _make_q(1, "Priya has some apples in her bag.", "white"),
            _make_q(2, "Ravi drinks fresh juice every morning.", "white"),
            _make_q(3, "The school library has many shelves.", "green"),
            _make_q(4, "Birds chirp loudly at sunrise.", "white"),
            _make_q(5, "Kiran drew a landscape picture.", "white"),
        ]
        passed, issues = run_quality_gate(_worksheet(qs))
        assert not any("CONSECUTIVE_ANSWERS" in i for i in issues), issues


# ── Check 11: Answer flood ────────────────────────────────────────────────────

class TestAnswerFlood:
    def test_two_same_answers_passes(self):
        # Exactly 2 occurrences of the same answer — below threshold
        qs = [
            _make_q(1, "Priya has some apples in her bag.", "Paneer"),
            _make_q(2, "Ravi drinks fresh juice every morning.", "Wheat"),
            _make_q(3, "The school library has many shelves.", "Paneer"),
            _make_q(4, "Birds chirp loudly at sunrise.", "Mango"),
        ]
        passed, issues = run_quality_gate(_worksheet(qs))
        assert not any("ANSWER_FLOOD" in i for i in issues), issues

    def test_three_same_answers_fails(self):
        # Non-consecutive: same answer at Q1, Q3, Q5
        qs = [
            _make_q(1, "Ravi speaks Hindi every day.", "Simple present tense"),
            _make_q(2, "The school library has many shelves.", "past tense"),
            _make_q(3, "Birds chirp loudly at sunrise.", "Simple present tense"),
            _make_q(4, "Kiran drew a landscape picture.", "future tense"),
            _make_q(5, "Priya cooks delicious meals daily.", "Simple present tense"),
        ]
        passed, issues = run_quality_gate(_worksheet(qs))
        assert passed is False
        assert any("ANSWER_FLOOD" in i for i in issues), issues
        assert any("Simple present tense" in i for i in issues)
        assert any("3x" in i for i in issues)

    def test_four_occurrences_evs_paneer(self):
        # Real-world EVS example: 4 questions all answering "Paneer"
        qs = [
            _make_q(1, "A dairy product used in Indian cooking.", "Paneer"),
            _make_q(2, "Name a cereal grain from Punjab fields.", "Wheat"),
            _make_q(3, "Ravi bought this for the curry dish.", "Paneer"),
            _make_q(4, "Name a popular tropical yellow fruit.", "Mango"),
            _make_q(5, "Which soft ingredient adds protein to meals?", "Paneer"),
            _make_q(6, "Name a popular street food with bread.", "Vada"),
            _make_q(7, "Priya made dinner using this soft block.", "Paneer"),
        ]
        passed, issues = run_quality_gate(_worksheet(qs))
        assert passed is False
        flood = [i for i in issues if "ANSWER_FLOOD" in i]
        assert len(flood) == 1, f"Expected 1 ANSWER_FLOOD, got: {issues}"
        assert "Paneer" in flood[0]
        assert "4x" in flood[0]
        assert "Q1" in flood[0]
        assert "Q3" in flood[0]
        assert "Q5" in flood[0]
        assert "Q7" in flood[0]

    def test_mcq_letters_excluded_from_flood(self):
        # "A" appears 5 times but is a bare MCQ letter — exempt
        qs = [
            _make_q(1, "Name a planet that spins fastest.", "A"),
            _make_q(2, "Which fruit grows underground?", "A"),
            _make_q(3, "What insect builds complex tunnels?", "A"),
            _make_q(4, "Identify a bird with bright colours.", "A"),
            _make_q(5, "Name a country in South America.", "A"),
        ]
        passed, issues = run_quality_gate(_worksheet(qs))
        assert not any("ANSWER_FLOOD" in i for i in issues), issues

    def test_flood_case_insensitive(self):
        # "paneer" and "Paneer" are the same answer — should count as 3 total
        qs = [
            _make_q(1, "A dairy product used in Indian cooking.", "Paneer"),
            _make_q(2, "Ravi bought this for the curry dish.", "paneer"),
            _make_q(3, "Priya made dinner using this soft block.", "PANEER"),
            _make_q(4, "Name a popular tropical yellow fruit.", "Mango"),
        ]
        passed, issues = run_quality_gate(_worksheet(qs))
        assert any("ANSWER_FLOOD" in i for i in issues), issues
        assert any("3x" in i for i in issues)


# ── Check 12: O'clock wording contradiction ───────────────────────────────────

class TestOClockMismatch:
    def test_exact_hour_with_oclock_passes(self):
        # minute_hand_pos=12 → answer "3:00" → o'clock IS correct wording
        q = _make_q(1, "The clock shows 3 o'clock. What time is it?", "3:00")
        passed, issues = run_quality_gate(_worksheet([q]))
        assert not any("OCLOCK_MISMATCH" in i for i in issues), issues

    def test_non_hour_with_oclock_fails(self):
        # LLM writes "10 o'clock" but Python-computed answer is "10:35"
        q = _make_q(1, "The clock shows 10 o'clock. What time does it show?", "10:35")
        passed, issues = run_quality_gate(_worksheet([q]))
        assert passed is False
        assert any("OCLOCK_MISMATCH" in i for i in issues), issues
        assert any("10:35" in i for i in issues)
        assert any("Q1" in i for i in issues)

    def test_half_past_with_oclock_fails(self):
        # Answer "3:30" is half-past — writing "3 o'clock" is wrong
        q = _make_q(1, "Priya's lesson starts at 3 o'clock thirty minutes.", "3:30")
        passed, issues = run_quality_gate(_worksheet([q]))
        assert passed is False
        assert any("OCLOCK_MISMATCH" in i for i in issues), issues
        assert any("3:30" in i for i in issues)

    def test_smart_quote_variant_caught(self):
        # o\u2019clock (smart/right single quote) — still caught by _OCLOCK_RE
        q = _make_q(1, "The clock shows 10 o\u2019clock. What time is it?", "10:35")
        passed, issues = run_quality_gate(_worksheet([q]))
        assert any("OCLOCK_MISMATCH" in i for i in issues), issues

    def test_no_oclock_non_hour_passes(self):
        # Answer "10:35" but question never says o'clock — no flag
        q = _make_q(
            1,
            "The hour hand is at 10 and the minute hand is at 7. What time is it?",
            "10:35",
        )
        passed, issues = run_quality_gate(_worksheet([q]))
        assert not any("OCLOCK_MISMATCH" in i for i in issues), issues


# ── Helpers: _OCLOCK_RE pattern ───────────────────────────────────────────────

class TestOClockRegex:
    def test_standard_apostrophe(self):
        assert _OCLOCK_RE.search("3 o'clock")

    def test_smart_quote(self):
        assert _OCLOCK_RE.search("3 o\u2019clock")

    def test_space_variant(self):
        assert _OCLOCK_RE.search("3 o clock")

    def test_case_insensitive(self):
        assert _OCLOCK_RE.search("O'CLOCK")

    def test_no_match_on_unrelated(self):
        assert not _OCLOCK_RE.search("half past three")
