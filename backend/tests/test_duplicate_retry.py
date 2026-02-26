"""Tests for near-duplicate template extraction and retry logic."""

from app.services.worksheet_generator import _extract_repeated_templates


class TestExtractRepeatedTemplates:
    def test_detects_repeated_pattern(self):
        """Three questions with same structure (different names/numbers) → 1 template."""
        questions = [
            {"text": "Aarav has 5 apples and gets 3 more. How many?"},
            {"text": "Priya has 8 apples and gets 2 more. How many?"},
            {"text": "Rohan has 4 apples and gets 6 more. How many?"},
            {"text": "What is 2 + 2?"},
        ]
        repeated = _extract_repeated_templates(questions, threshold=3)
        assert len(repeated) == 1

    def test_no_repeats_below_threshold(self):
        """Two similar questions should not trigger at threshold=3."""
        questions = [
            {"text": "Aarav has 5 apples and gets 3 more. How many?"},
            {"text": "Priya has 8 apples and gets 2 more. How many?"},
            {"text": "What is the time shown on the clock?"},
            {"text": "Solve: 45 + 38 = ______"},
        ]
        repeated = _extract_repeated_templates(questions, threshold=3)
        assert len(repeated) == 0

    def test_empty_questions(self):
        repeated = _extract_repeated_templates([], threshold=3)
        assert repeated == []

    def test_missing_text_field(self):
        questions = [
            {"text": ""},
            {"id": "q1"},
            {"text": "What is 5 + 3?"},
        ]
        # Should not crash
        repeated = _extract_repeated_templates(questions, threshold=2)
        assert isinstance(repeated, list)

    def test_multiple_repeated_groups(self):
        """Two different patterns each repeated 3 times."""
        questions = [
            {"text": "Aarav has 5 apples and gets 3 more. How many?"},
            {"text": "Priya has 8 apples and gets 2 more. How many?"},
            {"text": "Rohan has 4 apples and gets 6 more. How many?"},
            {"text": "What time does this clock show? 3:00"},
            {"text": "What time does this clock show? 5:30"},
            {"text": "What time does this clock show? 8:15"},
        ]
        repeated = _extract_repeated_templates(questions, threshold=3)
        assert len(repeated) == 2

    def test_threshold_boundary(self):
        """Exactly at threshold should be included."""
        questions = [
            {"text": "Aarav has 5 mangoes."},
            {"text": "Priya has 8 mangoes."},
            {"text": "Rohan has 4 mangoes."},
        ]
        repeated = _extract_repeated_templates(questions, threshold=3)
        assert len(repeated) == 1
        repeated_below = _extract_repeated_templates(questions, threshold=4)
        assert len(repeated_below) == 0
