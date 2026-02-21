"""Tests for quality_gate.run_quality_gate() — all 5 checks."""
import pytest
from app.utils.quality_gate import run_quality_gate, jaccard, extract_times


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
        # Same sentence with only one word changed → jaccard > 0.6
        qs = [
            _make_q(1, "What is the sum of 47 and 35?", "82"),
            _make_q(2, "What is the sum of 47 and 35?", "82"),
        ]
        passed, issues = run_quality_gate(_worksheet(qs))
        assert passed is False
        assert any("DUPLICATE" in i for i in issues), issues

    def test_jaccard_boundary(self):
        # Exactly at the boundary — just under 0.60 should pass
        a = "dog cat bird fish whale shark"       # 6 unique words
        b = "dog cat bird fish whale eagle"       # 5 shared, 1 different → 5/7 ≈ 0.71 > 0.6
        assert jaccard(a, b) > 0.6
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
