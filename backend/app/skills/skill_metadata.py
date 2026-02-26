"""Skill-to-topic mapping — auto-generated from TOPIC_PROFILES."""

import logging

logger = logging.getLogger(__name__)


def _load_skill_topic_map() -> dict[str, str]:
    """Auto-generate from TOPIC_PROFILES (maps skill_tag → first topic name)."""
    try:
        from app.data.topic_profiles import TOPIC_PROFILES
    except Exception:
        return {}

    mapping: dict[str, str] = {}
    for topic_name, profile in TOPIC_PROFILES.items():
        for tag in profile.get("allowed_skill_tags", []):
            if tag not in mapping:
                mapping[tag] = topic_name
    return mapping


SKILL_TOPIC_MAP: dict[str, str] = _load_skill_topic_map()


def topic_for_skill(skill_tag: str) -> str:
    return SKILL_TOPIC_MAP.get(skill_tag, "Unknown")
