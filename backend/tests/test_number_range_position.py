"""Tests for number range by position audit (Item A)."""

from app.services.difficulty_calibrator import (
    _audit_number_range_by_position,
    _extract_max_number,
)


def test_extract_max_number_basic():
    assert _extract_max_number("What is 23 + 45?") == 45


def test_extract_max_number_no_numbers():
    assert _extract_max_number("What colour is the sky?") == 0


def test_extract_max_number_ignores_long_numbers():
    # Numbers > 6 digits are ignored (likely IDs, not math)
    assert _extract_max_number("ID 1234567 has 5 items") == 5


def test_small_numbers_in_warmup_no_warning():
    questions = [
        {"question_text": "What is 3 + 5?"},
        {"question_text": "What is 7 + 2?"},
        {"question_text": "What is 4 + 6?"},
    ]
    warnings = _audit_number_range_by_position(questions)
    assert len(warnings) == 0


def test_large_numbers_in_warmup_warns():
    questions = [
        {"question_text": "What is 345 + 678?"},  # Q1 warm-up, large number
        {"question_text": "What is 5 + 3?"},
        {"question_text": "What is 2 + 1?"},
    ]
    warnings = _audit_number_range_by_position(questions)
    assert len(warnings) == 1
    assert "Q1" in warnings[0]
    assert "warm-up" in warnings[0]


def test_small_numbers_in_stretch_warns():
    questions = [{"question_text": f"Q{i} text"} for i in range(7)]
    questions.extend([
        {"question_text": "What is 3 + 2?"},  # Q8 stretch, tiny number
        {"question_text": "What is 4 + 1?"},  # Q9 stretch, tiny number
    ])
    warnings = _audit_number_range_by_position(questions)
    assert len(warnings) == 2
    assert "Q8" in warnings[0]
    assert "stretch" in warnings[0]


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
