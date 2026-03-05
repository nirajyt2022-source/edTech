"""Exact topic name → profile key lookup table.

Maps every possible variation of a topic name to its canonical TOPIC_PROFILES key.
Generated from curriculum_canon.json + TOPIC_PROFILES keys.

Used by get_topic_profile() as the FIRST lookup before any fuzzy matching.
"""

from __future__ import annotations

import json
import logging
import os
import re

logger = logging.getLogger(__name__)


def _build_lookup() -> dict[str, str]:
    """Build the lookup table from existing data."""
    from app.data.topic_profiles import TOPIC_PROFILES

    lookup: dict[str, str] = {}

    for key in TOPIC_PROFILES:
        normalized = key.strip().lower()
        lookup[normalized] = key

        # Without class suffix: "Addition up to 20 (Class 1)" → "addition up to 20"
        no_class = re.sub(r"\s*\(class\s*\d+\)\s*$", "", normalized, flags=re.IGNORECASE).strip()
        if no_class and no_class != normalized:
            lookup[no_class] = key

        # First word(s) before parenthetical: "Addition (carries)" → "addition"
        before_paren = normalized.split("(")[0].strip()
        if before_paren and len(before_paren) > 3 and before_paren not in lookup:
            lookup[before_paren] = key

        # With different class suffix format
        grade_match = re.search(r"class\s*(\d+)", key, re.IGNORECASE)
        if grade_match:
            grade = grade_match.group(1)
            base = re.sub(r"\s*\(class\s*\d+\)\s*", "", key, flags=re.IGNORECASE).strip()
            variant = f"{base} (class {grade})".lower()
            if variant not in lookup:
                lookup[variant] = key

            # Short-name + class: "addition (class 1)" → "Addition up to 20 (Class 1)"
            # Uses the first word of the base name (the subject term)
            first_word = base.lower().split()[0] if base else ""
            if first_word and len(first_word) > 2:
                short_class = f"{first_word} (class {grade})"
                if short_class not in lookup:
                    lookup[short_class] = key

    # Add curriculum_canon entries → profile keys
    canon_path = os.path.join(os.path.dirname(__file__), "curriculum_canon.json")
    try:
        with open(canon_path) as f:
            canon = json.load(f)

        for grade_data in canon["grades"]:
            grade = grade_data["grade"]
            for subject_data in grade_data["subjects"]:
                for skill_entry in subject_data.get("skills", []):
                    topic = skill_entry.get("name", skill_entry) if isinstance(skill_entry, dict) else skill_entry
                    topic_lower = topic.strip().lower()

                    if topic_lower in lookup:
                        continue  # already mapped

                    # Find best matching profile key
                    best_match = None
                    best_score = 0

                    for profile_key in TOPIC_PROFILES:
                        pk_lower = profile_key.lower()
                        pk_base = re.sub(r"\s*\(class\s*\d+\)\s*", "", pk_lower).strip()
                        topic_base = re.sub(r"\s*\(class\s*\d+\)\s*", "", topic_lower).strip()

                        # Exact base match
                        if topic_base == pk_base:
                            best_match = profile_key
                            best_score = 100
                            break

                        # Check if profile has matching class number
                        pk_grade = re.search(r"class\s*(\d+)", pk_lower)
                        pk_grade_num = int(pk_grade.group(1)) if pk_grade else None

                        # Base starts with or contains
                        if topic_base.startswith(pk_base) or pk_base.startswith(topic_base):
                            score = 70
                            if pk_grade_num == grade:
                                score += 20
                            if score > best_score:
                                best_score = score
                                best_match = profile_key

                    if best_match and best_score >= 70:
                        lookup[topic_lower] = best_match
                        with_class = f"{topic_lower} (class {grade})"
                        if with_class not in lookup:
                            lookup[with_class] = best_match
                        canon_with_class = f"{topic} (Class {grade})".lower()
                        if canon_with_class not in lookup:
                            lookup[canon_with_class] = best_match
    except Exception as e:
        logger.debug("curriculum_canon.json not loaded: %s", e)

    return lookup


# Build once at import time
TOPIC_LOOKUP: dict[str, str] = _build_lookup()


def resolve_topic(topic: str, grade: int | None = None) -> str | None:
    """Resolve any topic name variation to its canonical TOPIC_PROFILES key.

    Returns the profile key or None if no match found.
    """
    normalized = topic.strip().lower()

    # 1. Direct lookup
    if normalized in TOPIC_LOOKUP:
        return TOPIC_LOOKUP[normalized]

    # 2. Strip class suffix, re-add with provided grade
    if grade is not None:
        base_no_class = re.sub(r"\s*\(class\s*\d+\)\s*$", "", normalized, flags=re.IGNORECASE).strip()
        with_grade = f"{base_no_class} (class {grade})"
        if with_grade in TOPIC_LOOKUP:
            return TOPIC_LOOKUP[with_grade]

    # 3. Strip ALL parens, re-add class suffix (grade-specific before generic)
    no_paren = re.sub(r"\s*\(.*?\)\s*", "", normalized).strip()
    if no_paren and no_paren != normalized:
        if grade is not None:
            grade_variant = f"{no_paren} (class {grade})"
            if grade_variant in TOPIC_LOOKUP:
                return TOPIC_LOOKUP[grade_variant]
        if no_paren in TOPIC_LOOKUP:
            return TOPIC_LOOKUP[no_paren]

    # 4. Without class suffix specifically (keep non-class parens)
    no_class = re.sub(r"\s*\(class\s*\d+\)\s*$", "", normalized, flags=re.IGNORECASE).strip()
    if no_class != normalized and no_class in TOPIC_LOOKUP:
        return TOPIC_LOOKUP[no_class]

    return None
