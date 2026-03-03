"""Thin loader for static NCERT chapter map (fallback when DB is empty)."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger("skolar.ncert_chapter_map")

_MAP: dict | None = None
_FUZZY_INDEX: dict[str, list[tuple[str, str]]] | None = None

# Words to strip when building fuzzy keys
_STRIP_RE = re.compile(r"\s*\(.*?\)\s*")  # remove parenthetical qualifiers


def _load_map() -> dict:
    """Load the static map from JSON, building a fuzzy index alongside."""
    global _MAP, _FUZZY_INDEX
    if _MAP is not None:
        return _MAP

    p = Path(__file__).parent / "ncert_chapter_map.json"
    if p.exists():
        _MAP = json.loads(p.read_text(encoding="utf-8"))
    else:
        logger.warning("ncert_chapter_map.json not found at %s", p)
        _MAP = {}

    # Build fuzzy index: grade|subject -> [(topic_lower, chapter)]
    _FUZZY_INDEX = {}
    for key, chapter in _MAP.items():
        parts = key.split("|")
        if len(parts) != 3:
            continue
        grade, subject, topic = parts
        gs_key = f"{grade}|{subject}"
        if gs_key not in _FUZZY_INDEX:
            _FUZZY_INDEX[gs_key] = []
        _FUZZY_INDEX[gs_key].append((topic.lower(), chapter))

    return _MAP


def get_static_chapter(grade: str, subject: str, topic: str) -> str | None:
    """Look up NCERT chapter from static JSON map.

    Tries exact match first, then fuzzy substring matching.

    Args:
        grade: e.g. "Class 3" or "3"
        subject: e.g. "Maths"
        topic: e.g. "Addition (carries)"

    Returns:
        Chapter string like "Chapter 2: Fun with Numbers" or None.
    """
    _load_map()

    # Normalise grade: "3" → "Class 3", "Class 3" stays
    g = grade.strip()
    if g.isdigit():
        g = f"Class {g}"

    # 1. Exact match
    key = f"{g}|{subject}|{topic}"
    result = _MAP.get(key)  # type: ignore[union-attr]
    if result:
        return result

    # 2. Fuzzy match — strip parenthetical qualifiers and try
    topic_base = _STRIP_RE.sub("", topic).strip().lower()
    topic_lower = topic.lower()
    gs_key = f"{g}|{subject}"
    candidates = (_FUZZY_INDEX or {}).get(gs_key, [])

    # 2a. Check if any map topic is a substring of the request, or vice versa
    best = None
    best_score = 0
    for map_topic_lower, chapter in candidates:
        map_base = _STRIP_RE.sub("", map_topic_lower).strip()

        # Exact base match (e.g. "Nouns" matches "Nouns (common and proper)")
        if map_base == topic_base:
            return chapter

        # Substring: "Addition" in "Addition of Single-Digit Numbers"
        if map_base in topic_lower or topic_base in map_topic_lower:
            # Score by length of overlap (longer match = better)
            score = len(map_base) if map_base in topic_lower else len(topic_base)
            if score > best_score:
                best_score = score
                best = chapter

    if best:
        logger.info(
            "Chapter resolved via fuzzy match: '%s' -> '%s'",
            topic,
            best,
        )
        return best

    # 3. Last resort — match on first significant word (e.g. "Addition" matches "Addition up to 20")
    first_word = topic_base.split()[0] if topic_base else ""
    if len(first_word) >= 4:  # skip very short words
        for map_topic_lower, chapter in candidates:
            map_base = _STRIP_RE.sub("", map_topic_lower).strip()
            map_first = map_base.split()[0] if map_base else ""
            if first_word == map_first:
                logger.info(
                    "Chapter resolved via first-word match: '%s' -> '%s'",
                    topic,
                    chapter,
                )
                return chapter

    return None
