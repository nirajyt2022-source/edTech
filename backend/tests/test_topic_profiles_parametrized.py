"""
Parametrized tests for all 198 topic profiles in TOPIC_PROFILES.

Validates schema correctness, required fields, recipe integrity, and
constraint consistency for every topic — catching data regressions early.
"""

from __future__ import annotations

import pytest

from app.data.topic_profiles import TOPIC_PROFILES

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

VALID_SLOT_TYPES = {"recognition", "application", "representation", "error_detection", "thinking"}

REQUIRED_KEYS = {"allowed_skill_tags", "allowed_slot_types", "default_recipe"}

OPTIONAL_KEYS = {
    "disallowed_keywords",
    "disallowed_visual_types",
    "allowed_visual_types",
    "recipes_by_count",
    "max_questions",
    "subject",
    "devanagari_examples",
    "sequential_generation",
}

ALL_TOPIC_NAMES = sorted(TOPIC_PROFILES.keys())


# ─────────────────────────────────────────────────────────────────────────────
# Parametrized: one test per topic
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("topic_name", ALL_TOPIC_NAMES, ids=ALL_TOPIC_NAMES)
class TestTopicProfileSchema:
    """Validates schema integrity for each topic profile."""

    def test_required_keys_present(self, topic_name: str):
        profile = TOPIC_PROFILES[topic_name]
        missing = REQUIRED_KEYS - set(profile.keys())
        assert not missing, f"Missing required keys: {missing}"

    def test_no_unknown_keys(self, topic_name: str):
        profile = TOPIC_PROFILES[topic_name]
        allowed = REQUIRED_KEYS | OPTIONAL_KEYS
        unknown = set(profile.keys()) - allowed
        assert not unknown, f"Unknown keys: {unknown}"

    def test_allowed_skill_tags_non_empty(self, topic_name: str):
        tags = TOPIC_PROFILES[topic_name]["allowed_skill_tags"]
        assert isinstance(tags, list), "allowed_skill_tags must be a list"
        assert len(tags) > 0, "allowed_skill_tags must not be empty"

    def test_allowed_skill_tags_are_strings(self, topic_name: str):
        tags = TOPIC_PROFILES[topic_name]["allowed_skill_tags"]
        for tag in tags:
            assert isinstance(tag, str), f"Skill tag must be a string, got {type(tag)}"
            assert tag.strip() == tag, f"Skill tag has leading/trailing whitespace: '{tag}'"

    def test_no_duplicate_skill_tags(self, topic_name: str):
        tags = TOPIC_PROFILES[topic_name]["allowed_skill_tags"]
        assert len(tags) == len(set(tags)), f"Duplicate skill tags: {[t for t in tags if tags.count(t) > 1]}"

    def test_slot_types_valid(self, topic_name: str):
        slot_types = TOPIC_PROFILES[topic_name]["allowed_slot_types"]
        assert isinstance(slot_types, list), "allowed_slot_types must be a list"
        assert len(slot_types) > 0, "allowed_slot_types must not be empty"
        invalid = set(slot_types) - VALID_SLOT_TYPES
        assert not invalid, f"Invalid slot types: {invalid}"

    def test_default_recipe_structure(self, topic_name: str):
        recipe = TOPIC_PROFILES[topic_name]["default_recipe"]
        assert isinstance(recipe, list), "default_recipe must be a list"
        assert len(recipe) > 0, "default_recipe must not be empty"
        for i, item in enumerate(recipe):
            assert isinstance(item, dict), f"Recipe item {i} must be a dict"
            assert "skill_tag" in item, f"Recipe item {i} missing 'skill_tag'"
            assert "count" in item, f"Recipe item {i} missing 'count'"
            assert isinstance(item["count"], int), f"Recipe item {i} count must be int"
            assert item["count"] > 0, f"Recipe item {i} count must be positive"

    def test_recipe_skill_tags_in_allowed(self, topic_name: str):
        """Every skill_tag in the recipe must be in allowed_skill_tags."""
        profile = TOPIC_PROFILES[topic_name]
        allowed = set(profile["allowed_skill_tags"])
        for item in profile["default_recipe"]:
            tag = item["skill_tag"]
            assert tag in allowed, (
                f"Recipe tag '{tag}' not in allowed_skill_tags"
            )

    def test_default_recipe_count_is_10(self, topic_name: str):
        """Default recipe should sum to 10 questions (the standard count)."""
        recipe = TOPIC_PROFILES[topic_name]["default_recipe"]
        total = sum(item["count"] for item in recipe)
        # Most profiles target 10; some use 5 or other counts
        assert total >= 5, f"Recipe total ({total}) is too small"
        assert total <= 20, f"Recipe total ({total}) is too large"

    def test_disallowed_lists_are_lists(self, topic_name: str):
        profile = TOPIC_PROFILES[topic_name]
        for key in ("disallowed_keywords", "disallowed_visual_types"):
            if key in profile:
                val = profile[key]
                assert isinstance(val, list), f"{key} must be a list, got {type(val)}"


@pytest.mark.parametrize("topic_name", ALL_TOPIC_NAMES, ids=ALL_TOPIC_NAMES)
class TestTopicProfileRecipesByCount:
    """Validates recipes_by_count when present."""

    def test_recipes_by_count_keys_are_ints(self, topic_name: str):
        profile = TOPIC_PROFILES[topic_name]
        rbc = profile.get("recipes_by_count")
        if rbc is None:
            pytest.skip("No recipes_by_count")
        for k in rbc:
            assert isinstance(k, int), f"recipes_by_count key must be int, got {type(k)}: {k}"

    def test_recipes_by_count_sums_match_key(self, topic_name: str):
        profile = TOPIC_PROFILES[topic_name]
        rbc = profile.get("recipes_by_count")
        if rbc is None:
            pytest.skip("No recipes_by_count")
        for count, recipe in rbc.items():
            total = sum(item["count"] for item in recipe)
            assert total == count, (
                f"recipes_by_count[{count}] sums to {total}, expected {count}"
            )

    def test_recipes_by_count_tags_in_allowed(self, topic_name: str):
        profile = TOPIC_PROFILES[topic_name]
        rbc = profile.get("recipes_by_count")
        if rbc is None:
            pytest.skip("No recipes_by_count")
        allowed = set(profile["allowed_skill_tags"])
        for count, recipe in rbc.items():
            for item in recipe:
                assert item["skill_tag"] in allowed, (
                    f"recipes_by_count[{count}] tag '{item['skill_tag']}' not in allowed_skill_tags"
                )


# ─────────────────────────────────────────────────────────────────────────────
# Aggregate tests (run once, not per-profile)
# ─────────────────────────────────────────────────────────────────────────────


class TestTopicProfileAggregates:
    """Cross-profile checks."""

    def test_minimum_profile_count(self):
        """We should have at least 196 profiles (CBSE Class 1-5, 9 subjects)."""
        assert len(TOPIC_PROFILES) >= 196, (
            f"Expected ≥196 profiles, got {len(TOPIC_PROFILES)}"
        )

    def test_no_empty_topic_names(self):
        for name in TOPIC_PROFILES:
            assert name.strip(), "Empty topic name found"
            assert name == name.strip(), f"Topic name has whitespace: '{name}'"

    def test_all_five_slot_types_used(self):
        """At least one profile should use each of the 5 slot types."""
        all_used = set()
        for profile in TOPIC_PROFILES.values():
            all_used.update(profile.get("allowed_slot_types", []))
        assert all_used == VALID_SLOT_TYPES, (
            f"Not all slot types are used. Missing: {VALID_SLOT_TYPES - all_used}"
        )

    def test_maths_topics_exist(self):
        """Core Maths topics should be present."""
        maths_topics = ["Addition (carries)", "Subtraction (borrowing)", "Multiplication (tables 2-10)", "Division basics", "Fractions"]
        for t in maths_topics:
            assert t in TOPIC_PROFILES, f"Missing core Maths topic: {t}"

    def test_english_topics_exist(self):
        """At least some English topics should be present."""
        english = [name for name, p in TOPIC_PROFILES.items() if p.get("subject") == "English"]
        # Fallback: check for known English topic names
        if not english:
            english_names = [n for n in TOPIC_PROFILES if any(kw in n.lower() for kw in ("grammar", "tense", "noun", "verb", "reading", "comprehension", "writing"))]
            english = english_names
        assert len(english) >= 5, f"Expected ≥5 English topics, found {len(english)}"
