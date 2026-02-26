"""CI-enforced test: recipe skill_tags must be a subset of allowed_skill_tags."""

from app.data.topic_profiles import TOPIC_PROFILES


def test_all_recipe_tags_are_allowed():
    """Every skill_tag in default_recipe must exist in allowed_skill_tags."""
    errors: list[str] = []

    for topic_name, profile in TOPIC_PROFILES.items():
        allowed = set(profile.get("allowed_skill_tags", []))
        if not allowed:
            continue

        for item in profile.get("default_recipe", []):
            tag = item.get("skill_tag", "")
            if tag and tag not in allowed:
                errors.append(f"{topic_name}: recipe tag '{tag}' not in allowed_skill_tags")

        for count_key, recipe in profile.get("recipes_by_count", {}).items():
            for item in recipe:
                tag = item.get("skill_tag", "")
                if tag and tag not in allowed:
                    errors.append(f"{topic_name}: recipes_by_count[{count_key}] tag '{tag}' not in allowed")

    assert not errors, f"Found {len(errors)} mismatch(es):\n" + "\n".join(errors)


def test_all_profiles_have_recipes():
    """Every profile should have a default_recipe (catch accidental deletion)."""
    missing = [name for name, p in TOPIC_PROFILES.items() if not p.get("default_recipe")]
    assert not missing, f"{len(missing)} profiles missing default_recipe: {missing[:5]}"


def test_recipe_counts_are_positive():
    """Every recipe item should have count >= 1."""
    errors: list[str] = []
    for topic_name, profile in TOPIC_PROFILES.items():
        for item in profile.get("default_recipe", []):
            if item.get("count", 0) < 1:
                errors.append(f"{topic_name}: recipe tag '{item.get('skill_tag')}' has count < 1")
    assert not errors, f"Found {len(errors)} invalid count(s):\n" + "\n".join(errors)
