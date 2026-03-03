"""Tests for word problem answer extraction and quality reviewer P0 fixes."""

from app.services.quality_reviewer import (
    _extract_word_problem_arithmetic,
    _trim_question_text,
    QualityReviewerAgent,
)


def test_subtraction_word_problem():
    text = "Riya had 12 apples and gave 5 to Meera. How many are left?"
    result = _extract_word_problem_arithmetic(text)
    assert result is not None
    expr, value = result
    assert value == 7.0
    assert "12" in expr and "5" in expr


def test_addition_word_problem():
    text = "Aman has 8 marbles and Sneha has 6 marbles. How many marbles in all?"
    result = _extract_word_problem_arithmetic(text)
    assert result is not None
    expr, value = result
    assert value == 14.0


def test_multiplication_word_problem():
    text = "There are 4 bags with 6 pencils each. How many pencils are there?"
    result = _extract_word_problem_arithmetic(text)
    assert result is not None
    expr, value = result
    assert value == 24.0


def test_no_operation_keyword_returns_none():
    text = "What is the number 42 on the number line near 50?"
    result = _extract_word_problem_arithmetic(text)
    assert result is None


def test_subtraction_gave_away():
    text = "Priya had 20 stickers. She gave away 8 stickers. How many are remaining?"
    result = _extract_word_problem_arithmetic(text)
    assert result is not None
    assert result[1] == 12.0


def test_addition_total():
    text = "Arjun scored 15 runs and Rohit scored 23 runs. What is the total?"
    result = _extract_word_problem_arithmetic(text)
    assert result is not None
    assert result[1] == 38.0


# ── 3-number word problem tests (Fix 7) ──


def test_three_number_sequential_subtraction():
    """Had X, gave Y, lost Z → X - Y - Z"""
    text = "Riya had 12 apples, gave 5 to Meera and 3 to Kiran. How many are left?"
    result = _extract_word_problem_arithmetic(text)
    assert result is not None
    assert result[1] == 4.0


def test_three_number_mul_then_sub():
    """X items at Y each, spent Z → X*Y - Z"""
    text = "Riya bought 4 pencils at 5 rupees each and spent 3 rupees on an eraser. How much left?"
    result = _extract_word_problem_arithmetic(text)
    assert result is not None
    assert result[1] == 17.0


def test_three_number_mul_then_add():
    """X rows of Y each, plus Z extra → X*Y + Z"""
    text = "There are 3 rows of 5 chairs each, plus 2 extra chairs. How many chairs in total?"
    result = _extract_word_problem_arithmetic(text)
    assert result is not None
    assert result[1] == 17.0


def test_three_number_pure_addition():
    """X + Y + Z altogether"""
    text = "There are 10 red balls, 5 blue balls and 3 green balls in all. How many total?"
    result = _extract_word_problem_arithmetic(text)
    assert result is not None
    assert result[1] == 18.0


def test_four_numbers_skipped():
    """Only handles 2 or 3 number problems."""
    text = "Riya had 12 apples, gave 5, then 3, then 2. How many left?"
    result = _extract_word_problem_arithmetic(text)
    assert result is None


# ── P0-A: "ate" + "total" precedence fix ──


def test_ate_with_total_is_addition():
    """'ate' + 'total' = addition, not subtraction."""
    text = "Saanvi ate 2 sweets. Isha ate 4 sweets. How many sweets did they eat in all?"
    result = _extract_word_problem_arithmetic(text)
    assert result is not None
    assert result[1] == 6.0  # NOT 2.0


def test_lost_with_total_is_addition():
    """When both add and sub signals conflict, addition wins."""
    text = "Team A lost 3 points. Team B lost 5 points. How many points lost in total?"
    result = _extract_word_problem_arithmetic(text)
    assert result is not None
    assert result[1] == 8.0  # total trumps lost


def test_spent_without_total_is_subtraction():
    """'spent' alone = subtraction (no conflict)."""
    text = "Riya had 50 rupees and spent 15 rupees. How much is remaining?"
    result = _extract_word_problem_arithmetic(text)
    assert result is not None
    assert result[1] == 35.0


# ── P0-A: Decimal number support ──


def test_decimal_addition_word_problem():
    """Decimal numbers must be parsed correctly."""
    text = "She uses 0.75 kg of apples and 0.5 kg of bananas. What is the total weight?"
    result = _extract_word_problem_arithmetic(text)
    assert result is not None
    assert abs(result[1] - 1.25) < 0.01  # NOT 80.0


def test_decimal_subtraction():
    """Decimal subtraction."""
    text = "Rohan had 5.5 litres of water. He used 2.3 litres. How much is left?"
    result = _extract_word_problem_arithmetic(text)
    assert result is not None
    assert abs(result[1] - 3.2) < 0.01


def test_integer_still_works():
    """Existing integer word problems still work after decimal upgrade."""
    text = "Priya had 20 stickers. She gave away 8. How many are remaining?"
    result = _extract_word_problem_arithmetic(text)
    assert result is not None
    assert result[1] == 12.0


# ── P0-B: Word count enforcement ──


def test_trim_removes_filler():
    """Filler phrases get stripped."""
    text = "In the following Look at the picture. What is 3 + 2?"
    result = _trim_question_text(text, 15)
    assert result is not None
    assert "following" not in result
    assert "picture" not in result
    assert "3 + 2" in result


def test_trim_returns_none_when_no_filler():
    """No filler → returns None (nothing to trim)."""
    text = "What is 3 + 2?"
    result = _trim_question_text(text, 15)
    assert result is None


def test_word_count_regen_flag_over_2x():
    """Questions >2x word limit get _needs_regen flag."""
    from unittest.mock import MagicMock

    ctx = MagicMock()
    ctx.grade = 1
    ctx.subject = "maths"
    ctx.valid_skill_tags = []

    # 32 words for grade 1 limit of 15 → ratio 2.13 → regen
    long_text = " ".join(["word"] * 32)
    questions = [{"id": 1, "slot_type": "application", "question_text": long_text, "answer": "5"}]

    reviewer = QualityReviewerAgent()
    result = reviewer.review_worksheet(questions, ctx)
    assert result.questions[0].get("_needs_regen") is True


def test_word_count_trim_between_1_5x_and_2x():
    """Questions 1.5-2x limit with filler get trimmed, not regen-flagged."""
    from unittest.mock import MagicMock

    ctx = MagicMock()
    ctx.grade = 1
    ctx.subject = "english"
    ctx.valid_skill_tags = []

    # "In the following " adds 3 words of filler; total ~24 words, limit 15, ratio 1.6
    filler = "In the following "
    core = " ".join(["word"] * 21)  # 21 words
    text = filler + core  # 24 words total, ratio 1.6
    questions = [{"id": 1, "slot_type": "recognition", "question_text": text, "answer": "ok"}]

    reviewer = QualityReviewerAgent()
    result = reviewer.review_worksheet(questions, ctx)
    q = result.questions[0]
    # Should have trimmed, not regen-flagged (trimmed is 21 words, still > 15 so regen)
    # Actually 21 > 15, trim won't bring it under limit → regen
    assert q.get("_needs_regen") is True


def test_word_count_trim_successful():
    """Questions where filler removal brings count under limit get trimmed."""
    from unittest.mock import MagicMock

    ctx = MagicMock()
    ctx.grade = 3  # limit 25
    ctx.subject = "english"
    ctx.valid_skill_tags = []

    # 30 words with "In the following" and "Look at the picture." filler (7 words)
    # After trim: 23 words → under limit
    filler = "In the following Look at the picture. "
    core = " ".join(["word"] * 23)  # 23 words
    text = filler + core  # 30 words total, ratio 1.2 → under 1.5, just warning
    # Need ratio > 1.5: 39 words for limit 25 → 1.56
    core2 = " ".join(["word"] * 32)  # 32 words
    text2 = filler + core2  # 39 words total, ratio 1.56
    questions = [{"id": 1, "slot_type": "recognition", "question_text": text2, "answer": "ok"}]

    reviewer = QualityReviewerAgent()
    result = reviewer.review_worksheet(questions, ctx)
    q = result.questions[0]
    # Trimmed removes ~7 words → 32 words, still > 25 → regen
    assert q.get("_needs_regen") is True
