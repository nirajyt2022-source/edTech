"""Tests for mandatory visual enforcement system.

Covers:
- effective_min_count scaling
- _generate_default_visual_data for each visual type
- enforce_mandatory_visuals injection logic
- Edge cases: standard mode, non-Maths, all visuals present, no eligible questions
"""

from __future__ import annotations

from app.services.worksheet_generator import (
    _generate_default_visual_data,
    effective_min_count,
    enforce_mandatory_visuals,
)


# ── effective_min_count ──────────────────────────────────────────────────


class TestEffectiveMinCount:
    def test_zero_base_returns_zero(self):
        assert effective_min_count(0, 10) == 0
        assert effective_min_count(0, 20) == 0

    def test_base_2_for_10q(self):
        assert effective_min_count(2, 10) == 2

    def test_base_2_for_5q(self):
        assert effective_min_count(2, 5) == 1

    def test_base_2_for_20q(self):
        assert effective_min_count(2, 20) == 4

    def test_base_1_for_5q_minimum_1(self):
        assert effective_min_count(1, 5) == 1

    def test_base_1_for_3q_minimum_1(self):
        assert effective_min_count(1, 3) == 1

    def test_base_2_for_15q(self):
        assert effective_min_count(2, 15) == 3


# ── _generate_default_visual_data ────────────────────────────────────────


class TestGenerateDefaultVisualData:
    def test_clock_with_time_in_text(self):
        q = {"text": "What time does the clock show at 3:30?"}
        result = _generate_default_visual_data("clock", q, "Time")
        assert result == {"hour": 3, "minute": 30}

    def test_clock_fallback(self):
        q = {"text": "Draw the hands on the clock."}
        result = _generate_default_visual_data("clock", q, "Time")
        assert "hour" in result and "minute" in result
        assert 1 <= result["hour"] <= 12

    def test_pie_fraction_with_fraction_in_text(self):
        q = {"text": "Shade 2/4 of the circle."}
        result = _generate_default_visual_data("pie_fraction", q, "Fractions")
        assert result == {"numerator": 2, "denominator": 4}

    def test_pie_fraction_fallback(self):
        q = {"text": "Show half of the shape."}
        result = _generate_default_visual_data("pie_fraction", q, "Fractions")
        assert result == {"numerator": 1, "denominator": 2}

    def test_pie_fraction_invalid_fraction_uses_fallback(self):
        q = {"text": "What is 5/3 as a mixed number?"}
        # 5/3 has numerator > denominator, should fallback
        result = _generate_default_visual_data("pie_fraction", q, "Fractions")
        assert result == {"numerator": 1, "denominator": 2}

    def test_money_coins_with_amount(self):
        q = {"text": "Riya has ₹17. Show the coins."}
        result = _generate_default_visual_data("money_coins", q, "Money")
        assert "coins" in result
        assert isinstance(result["coins"], list)
        assert len(result["coins"]) > 0

    def test_money_coins_fallback(self):
        q = {"text": "Count the coins."}
        result = _generate_default_visual_data("money_coins", q, "Money")
        assert result == {"coins": [5, 2, 2, 1]}

    def test_shapes_with_shape_in_text(self):
        q = {"text": "How many sides does a triangle have?"}
        result = _generate_default_visual_data("shapes", q, "Shapes")
        assert result == {"shape": "triangle"}

    def test_shapes_fallback(self):
        q = {"text": "Name this figure."}
        result = _generate_default_visual_data("shapes", q, "Shapes")
        assert result == {"shape": "square"}

    def test_grid_symmetry(self):
        q = {"text": "Complete the symmetry."}
        result = _generate_default_visual_data("grid_symmetry", q, "Symmetry")
        assert "grid_size" in result
        assert "filled_cells" in result
        assert "fold_axis" in result

    def test_pattern_tiles(self):
        q = {"text": "What comes next: A, B, A, B, ?"}
        result = _generate_default_visual_data("pattern_tiles", q, "Patterns")
        assert "tiles" in result
        assert "blank_position" in result

    def test_number_line_with_numbers(self):
        q = {"text": "Mark 15 and 25 on the number line."}
        result = _generate_default_visual_data("number_line", q, "Numbers")
        assert result["start"] == 15
        assert result["end"] == 25
        assert result["step"] >= 1

    def test_number_line_fallback(self):
        q = {"text": "Show the number on the line."}
        result = _generate_default_visual_data("number_line", q, "Numbers")
        assert result == {"start": 0, "end": 10, "step": 1}

    def test_abacus_with_number(self):
        q = {"text": "Show 253 on the abacus."}
        result = _generate_default_visual_data("abacus", q, "Place Value")
        assert result == {"hundreds": 2, "tens": 5, "ones": 3}

    def test_abacus_fallback(self):
        q = {"text": "Read the abacus."}
        result = _generate_default_visual_data("abacus", q, "Place Value")
        assert result == {"hundreds": 0, "tens": 5, "ones": 3}

    def test_object_group_with_numbers(self):
        q = {"text": "Riya has 4 apples and 3 oranges."}
        result = _generate_default_visual_data("object_group", q, "Addition")
        assert result == {"groups": [4, 3], "operation": "add"}

    def test_object_group_fallback(self):
        q = {"text": "Count the objects."}
        result = _generate_default_visual_data("object_group", q, "Addition")
        assert result == {"groups": [3, 2], "operation": "add"}

    def test_base_ten_with_numbers(self):
        q = {"text": "Add 45 and 23 using base ten blocks."}
        result = _generate_default_visual_data("base_ten_regrouping", q, "Addition")
        assert result == {"numbers": [45, 23], "operation": "add"}

    def test_base_ten_no_numbers_returns_none(self):
        q = {"text": "Use blocks to solve."}
        result = _generate_default_visual_data("base_ten_regrouping", q, "Addition")
        assert result is None

    def test_unknown_type_returns_none(self):
        q = {"text": "Some question."}
        result = _generate_default_visual_data("unknown_type", q, "Topic")
        assert result is None


# ── enforce_mandatory_visuals ────────────────────────────────────────────


def _make_questions(n: int, with_visual: int = 0, visual_type: str = "clock") -> list[dict]:
    """Helper: create n questions, first `with_visual` get a visual."""
    questions = []
    for i in range(n):
        q = {
            "id": f"q{i + 1}",
            "text": f"What time is 3:00 plus {i + 1} hours?",
            "type": "short_answer",
            "correct_answer": f"{3 + i + 1}:00",
            "role": "recognition" if i % 3 == 0 else "application",
        }
        if i < with_visual:
            q["visual_type"] = visual_type
            q["visual_data"] = {"hour": 3, "minute": 0}
        questions.append(q)
    return questions


class TestEnforceMandatoryVisuals:
    def test_standard_mode_returns_none(self):
        questions = _make_questions(10)
        result, compliance = enforce_mandatory_visuals(
            questions, "Time (reading clock, calendar)", "Maths", "standard", 10
        )
        assert compliance is None

    def test_non_maths_returns_none(self):
        questions = _make_questions(10)
        result, compliance = enforce_mandatory_visuals(
            questions, "Parts of Speech", "English", "mixed", 10
        )
        assert compliance is None

    def test_topic_without_mandatory_returns_none(self):
        questions = _make_questions(10)
        result, compliance = enforce_mandatory_visuals(
            questions, "Addition (carries)", "Maths", "mixed", 10
        )
        assert compliance is None

    def test_injects_missing_required_type(self):
        questions = _make_questions(10, with_visual=0)
        result, compliance = enforce_mandatory_visuals(
            questions, "Time (reading clock, calendar)", "Maths", "mixed", 10
        )
        assert compliance is not None
        assert "clock" in compliance["found_types"]
        assert len(compliance["repairs"]) > 0

    def test_already_compliant_no_repairs(self):
        questions = _make_questions(10, with_visual=3, visual_type="clock")
        result, compliance = enforce_mandatory_visuals(
            questions, "Time (reading clock, calendar)", "Maths", "mixed", 10
        )
        assert compliance is not None
        assert compliance["compliant"] is True
        assert len(compliance["repairs"]) == 0

    def test_shortfall_filled(self):
        # min_count=2 for Time, only 1 clock present
        questions = _make_questions(10, with_visual=1, visual_type="clock")
        result, compliance = enforce_mandatory_visuals(
            questions, "Time (reading clock, calendar)", "Maths", "visual", 10
        )
        assert compliance is not None
        assert compliance["actual_count"] >= 2

    def test_scales_with_question_count(self):
        # 20 questions, base min_count=2 → effective 4
        questions = _make_questions(20, with_visual=0)
        result, compliance = enforce_mandatory_visuals(
            questions, "Time (reading clock, calendar)", "Maths", "mixed", 20
        )
        assert compliance is not None
        assert compliance["min_count"] == 4

    def test_no_eligible_questions_graceful(self):
        # All questions already have visuals — none eligible for injection
        questions = _make_questions(10, with_visual=10, visual_type="object_group")
        # Topic requires clock, but all questions already have object_group
        result, compliance = enforce_mandatory_visuals(
            questions, "Time (reading clock, calendar)", "Maths", "mixed", 10
        )
        assert compliance is not None
        # Should not crash, may not be compliant
        assert "repairs" in compliance

    def test_fractions_topic_injects_pie_fraction(self):
        questions = []
        for i in range(10):
            questions.append({
                "id": f"q{i + 1}",
                "text": f"What is 1/{i + 2} of the shape?",
                "type": "short_answer",
                "correct_answer": f"1/{i + 2}",
                "role": "recognition" if i % 3 == 0 else "application",
            })
        result, compliance = enforce_mandatory_visuals(
            questions, "Fractions (halves, quarters)", "Maths", "mixed", 10
        )
        assert compliance is not None
        assert "pie_fraction" in compliance["found_types"]
        assert compliance["compliant"] is True

    def test_visual_mode_works_same_as_mixed(self):
        questions = _make_questions(10, with_visual=0)
        result, compliance = enforce_mandatory_visuals(
            questions, "Time (reading clock, calendar)", "Maths", "visual", 10
        )
        assert compliance is not None
        assert len(compliance["repairs"]) > 0
