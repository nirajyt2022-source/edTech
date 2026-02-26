#!/usr/bin/env python3
"""
Validate topic profile consistency — recipe tags must be a subset of allowed_skill_tags.

Run as:
    python scripts/validate_topic_profiles.py

Exit code 0 = all valid, exit code 1 = mismatches found.
Suitable for CI enforcement.
"""

from __future__ import annotations

import sys
import os

# Ensure backend is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.data.topic_profiles import TOPIC_PROFILES


def validate_profiles() -> list[str]:
    """Return list of error strings for any recipe/allowed_skill_tags mismatches."""
    errors: list[str] = []

    for topic_name, profile in TOPIC_PROFILES.items():
        allowed = set(profile.get("allowed_skill_tags", []))
        if not allowed:
            continue  # No constraint to enforce

        # Check default_recipe
        for item in profile.get("default_recipe", []):
            tag = item.get("skill_tag", "")
            if tag and tag not in allowed:
                errors.append(
                    f"  {topic_name}: default_recipe tag '{tag}' not in allowed_skill_tags"
                )

        # Check recipes_by_count
        for count_key, recipe in profile.get("recipes_by_count", {}).items():
            for item in recipe:
                tag = item.get("skill_tag", "")
                if tag and tag not in allowed:
                    errors.append(
                        f"  {topic_name}: recipes_by_count[{count_key}] tag '{tag}' not in allowed_skill_tags"
                    )

    return errors


def main() -> None:
    errors = validate_profiles()

    total = len(TOPIC_PROFILES)
    profiles_with_recipes = sum(1 for p in TOPIC_PROFILES.values() if p.get("default_recipe"))

    print(f"Checked {total} topic profiles ({profiles_with_recipes} with recipes)")

    if errors:
        print(f"\nFOUND {len(errors)} MISMATCH(ES):")
        for e in errors:
            print(e)
        sys.exit(1)
    else:
        print("All recipe skill_tags are valid subsets of allowed_skill_tags.")
        sys.exit(0)


if __name__ == "__main__":
    main()
