"""Tests for D-06: Insight Generator — template and helper tests."""

import pytest

from app.services.insight_generator import (
    ChildInsight,
    InsightItem,
    _humanize_skill,
    _TIP_MAP,
    generate_child_insights,
    generate_weekly_digest,
)


class TestHumanizeSkill:
    def test_basic_conversion(self):
        assert _humanize_skill("column_add_with_carry") == "Column Add With Carry"

    def test_word_problem_prefix(self):
        result = _humanize_skill("wp_subtraction")
        assert "Word Problem" in result or "Wp" in result

    def test_single_word(self):
        assert _humanize_skill("thinking") == "Thinking"


class TestTipMap:
    def test_all_domains_have_tips(self):
        expected_domains = [
            "addition", "subtraction", "multiplication", "division",
            "number_sense", "place_value", "word_problems", "time", "money", "general",
        ]
        for domain in expected_domains:
            assert domain in _TIP_MAP, f"Missing tip for domain: {domain}"

    def test_tips_are_nonempty_strings(self):
        for domain, tip in _TIP_MAP.items():
            assert isinstance(tip, str)
            assert len(tip) > 10, f"Tip for {domain} too short"


class TestChildInsight:
    def test_default_construction(self):
        insight = ChildInsight(child_name="Test")
        assert insight.child_name == "Test"
        assert insight.strengths == []
        assert insight.struggles == []
        assert insight.improving == []
        assert insight.weekly_summary == ""
        assert insight.actionable_tip == ""
        assert insight.next_worksheet_suggestion == {}


class TestInsightItem:
    def test_construction(self):
        item = InsightItem(
            skill_tag="column_add",
            display="Column Add",
            detail="80% accuracy",
        )
        assert item.skill_tag == "column_add"
        assert item.display == "Column Add"
        assert item.detail == "80% accuracy"


class TestGenerateInsightsDefaults:
    def test_no_diagnostic_db_returns_default(self, monkeypatch):
        monkeypatch.delenv("ENABLE_DIAGNOSTIC_DB", raising=False)
        insight = generate_child_insights("child-123", "Aarav")
        assert insight.child_name == "Aarav"
        assert "No recent data" in insight.weekly_summary or "Aarav" in insight.weekly_summary
        assert insight.actionable_tip == _TIP_MAP["general"]

    def test_returns_child_insight_type(self, monkeypatch):
        monkeypatch.delenv("ENABLE_DIAGNOSTIC_DB", raising=False)
        result = generate_child_insights("child-123", "Priya")
        assert isinstance(result, ChildInsight)


class TestWeeklyDigestDefaults:
    def test_no_diagnostic_db_returns_default(self, monkeypatch):
        monkeypatch.delenv("ENABLE_DIAGNOSTIC_DB", raising=False)
        digest = generate_weekly_digest("child-123", "Aarav")
        assert digest["child_name"] == "Aarav"
        assert digest["total_sessions"] == 0
        assert digest["total_questions"] == 0
        assert "No activity" in digest["summary"]

    def test_returns_dict(self, monkeypatch):
        monkeypatch.delenv("ENABLE_DIAGNOSTIC_DB", raising=False)
        result = generate_weekly_digest("child-123", "Test")
        assert isinstance(result, dict)
        assert "period" in result
        assert result["period"] == "last 7 days"


class TestApplyDiagnosticWeights:
    """Test the recipe weight adjuster from topic_profiles."""

    def test_basic_weight_adjustment(self):
        from app.data.topic_profiles import apply_diagnostic_weights

        recipe = [
            {"skill_tag": "column_add_with_carry", "count": 3},
            {"skill_tag": "addition_word_problem", "count": 3},
            {"skill_tag": "missing_number", "count": 2},
            {"skill_tag": "addition_error_spot", "count": 1},
            {"skill_tag": "thinking", "count": 1},
        ]
        weights = {"column_add_with_carry": 2.0}
        result = apply_diagnostic_weights(recipe, weights, 10)

        # Total should be preserved
        total = sum(item["count"] for item in result)
        assert total == 10

        # Weighted skill should have more questions
        carry_item = next(r for r in result if r["skill_tag"] == "column_add_with_carry")
        assert carry_item["count"] >= 3  # Should be boosted

    def test_no_weights_returns_original(self):
        from app.data.topic_profiles import apply_diagnostic_weights

        recipe = [{"skill_tag": "add", "count": 5}]
        result = apply_diagnostic_weights(recipe, {}, 5)
        assert result == recipe

    def test_empty_recipe(self):
        from app.data.topic_profiles import apply_diagnostic_weights

        result = apply_diagnostic_weights([], {"add": 2.0}, 10)
        assert result == []

    def test_all_counts_at_least_one(self):
        from app.data.topic_profiles import apply_diagnostic_weights

        recipe = [
            {"skill_tag": "a", "count": 5},
            {"skill_tag": "b", "count": 1},
            {"skill_tag": "c", "count": 1},
        ]
        weights = {"a": 0.1}  # Reduce 'a' heavily
        result = apply_diagnostic_weights(recipe, weights, 7)
        for item in result:
            assert item["count"] >= 1
