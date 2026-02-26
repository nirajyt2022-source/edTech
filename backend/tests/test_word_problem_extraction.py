"""Tests for word problem answer extraction (Item C)."""

from app.services.quality_reviewer import _extract_word_problem_arithmetic


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
