"""Tests for recipe scaling and skill-tag hint helpers."""
from app.services.worksheet_generator import _scale_recipe, _get_skill_tag_hint


# Sample recipe (sums to 10)
SAMPLE_RECIPE = [
    {"skill_tag": "clock_reading", "count": 3},
    {"skill_tag": "time_word_problem", "count": 3},
    {"skill_tag": "time_fill_blank", "count": 2},
    {"skill_tag": "time_error_spot", "count": 1},
    {"skill_tag": "time_thinking", "count": 1},
]


class TestScaleRecipe:
    def test_identity_10_to_10(self):
        """10 -> 10 should return same counts."""
        result = _scale_recipe(SAMPLE_RECIPE, 10)
        assert sum(e["count"] for e in result) == 10
        # Should match original counts
        for orig, scaled in zip(SAMPLE_RECIPE, result):
            assert orig["skill_tag"] == scaled["skill_tag"]
            assert orig["count"] == scaled["count"]

    def test_downscale_10_to_5(self):
        """10 -> 5 should sum to 5 with each tag having at least 1."""
        result = _scale_recipe(SAMPLE_RECIPE, 5)
        assert sum(e["count"] for e in result) == 5
        assert all(e["count"] >= 1 for e in result)
        assert len(result) == 5

    def test_upscale_10_to_20(self):
        """10 -> 20 should sum to 20 with proportions roughly preserved."""
        result = _scale_recipe(SAMPLE_RECIPE, 20)
        assert sum(e["count"] for e in result) == 20
        assert all(e["count"] >= 1 for e in result)
        # clock_reading (30%) should have more than time_error_spot (10%)
        clock = next(e for e in result if e["skill_tag"] == "clock_reading")
        error = next(e for e in result if e["skill_tag"] == "time_error_spot")
        assert clock["count"] > error["count"]

    def test_edge_case_10_to_3(self):
        """10 -> 3 with 5 tags should truncate to 3 tags."""
        result = _scale_recipe(SAMPLE_RECIPE, 3)
        assert sum(e["count"] for e in result) == 3
        assert len(result) == 3

    def test_preserves_all_tags_when_possible(self):
        """10 -> 7 should keep all 5 tags."""
        result = _scale_recipe(SAMPLE_RECIPE, 7)
        assert sum(e["count"] for e in result) == 7
        assert len(result) == 5
        assert all(e["count"] >= 1 for e in result)


class TestSkillTagHints:
    def test_exact_match(self):
        assert "clock" in _get_skill_tag_hint("clock_reading").lower()

    def test_suffix_match(self):
        hint = _get_skill_tag_hint("subtraction_word_problem")
        assert "word problem" in hint.lower()

    def test_suffix_error_spot(self):
        hint = _get_skill_tag_hint("addition_error_spot")
        assert "mistake" in hint.lower() or "error" in hint.lower()

    def test_fallback_humanize(self):
        hint = _get_skill_tag_hint("some_unknown_tag")
        assert hint == "Some unknown tag"
