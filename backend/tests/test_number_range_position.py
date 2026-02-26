"""Tests for number range by position fix (Item A)."""

from app.services.difficulty_calibrator import (
    _extract_max_number,
    _fix_number_range_by_position,
)


def test_extract_max_number_basic():
    assert _extract_max_number("What is 23 + 45?") == 45


def test_extract_max_number_no_numbers():
    assert _extract_max_number("What colour is the sky?") == 0


def test_extract_max_number_ignores_long_numbers():
    # Numbers > 6 digits are ignored (likely IDs, not math)
    assert _extract_max_number("ID 1234567 has 5 items") == 5


def test_small_numbers_in_warmup_no_swap():
    questions = [
        {"question_text": "What is 3 + 5?"},
        {"question_text": "What is 7 + 2?"},
        {"question_text": "What is 4 + 6?"},
    ]
    # Less than 5 questions — skip
    warnings = _fix_number_range_by_position(questions)
    assert len(warnings) == 0


def test_large_number_in_warmup_gets_swapped():
    questions = [
        {"question_text": "What is 345 + 678?", "id": "q1"},  # Q1 warm-up, large
        {"question_text": "What is 5 + 3?", "id": "q2"},
        {"question_text": "What is 2 + 1?", "id": "q3"},
        {"question_text": "What is 10 + 20?", "id": "q4"},
        {"question_text": "What is 15 + 25?", "id": "q5"},
    ]
    warnings = _fix_number_range_by_position(questions)
    # Q1 should have been swapped with a later Q that has smaller numbers
    assert _extract_max_number(questions[0]["question_text"]) <= 100
    assert len(warnings) >= 1
    assert "Swapped" in warnings[0]


def test_no_swap_when_all_small():
    questions = [
        {"question_text": f"What is {i} + {i+1}?"} for i in range(1, 11)
    ]
    warnings = _fix_number_range_by_position(questions)
    assert len(warnings) == 0


def test_prompt_contains_number_progression_rule():
    from app.services.worksheet_generator import build_user_prompt

    prompt = build_user_prompt("CBSE", "Class 3", "Maths", "Addition", "medium", 10, "English")
    assert "NUMBER PROGRESSION" in prompt


def test_prompt_skips_number_progression_for_english():
    from app.services.worksheet_generator import build_user_prompt

    prompt = build_user_prompt("CBSE", "Class 3", "English", "Nouns", "medium", 10, "English")
    assert "NUMBER PROGRESSION" not in prompt


def test_prompt_skips_number_progression_for_small_sets():
    from app.services.worksheet_generator import build_user_prompt

    prompt = build_user_prompt("CBSE", "Class 3", "Maths", "Addition", "medium", 3, "English")
    assert "NUMBER PROGRESSION" not in prompt
