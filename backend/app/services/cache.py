"""
Application-level caching for AI responses and data lookups.

Uses in-memory TTL caches. No Redis needed at current scale (< 1000 users).
When scale demands it, swap these for Redis with the same interface.
"""

from __future__ import annotations

import hashlib

import structlog
from cachetools import TTLCache

logger = structlog.get_logger("skolar.cache")

# -- Cache instances -----------------------------------------------------------

# Revision notes: key = "grade:subject:topic:language" -> full AI response dict
_revision_cache: TTLCache = TTLCache(maxsize=500, ttl=86400)  # 24 hours

# Flashcards: same key pattern -> full AI response dict
_flashcard_cache: TTLCache = TTLCache(maxsize=500, ttl=86400)  # 24 hours

# Dashboard: key = "child_id" -> dashboard data dict
_dashboard_cache: TTLCache = TTLCache(maxsize=200, ttl=300)  # 5 minutes


def _make_key(*parts: str) -> str:
    """Create a cache key from parts."""
    raw = ":".join(str(p).strip().lower() for p in parts)
    return hashlib.sha256(raw.encode()).hexdigest()


# -- Revision Cache ------------------------------------------------------------


def get_cached_revision(grade: str, subject: str, topic: str, language: str = "English") -> dict | None:
    """Get cached revision notes, or None if not cached."""
    key = _make_key("revision", grade, subject, topic, language)
    result = _revision_cache.get(key)
    if result:
        logger.info("cache_hit", cache="revision", topic=topic)
    return result


def set_cached_revision(grade: str, subject: str, topic: str, language: str, data: dict) -> None:
    """Cache revision notes."""
    key = _make_key("revision", grade, subject, topic, language)
    _revision_cache[key] = data
    logger.info("cache_set", cache="revision", topic=topic)


# -- Flashcard Cache -----------------------------------------------------------


def get_cached_flashcards(grade: str, subject: str, topic: str, language: str = "English") -> dict | None:
    """Get cached flashcards, or None if not cached."""
    key = _make_key("flashcards", grade, subject, topic, language)
    result = _flashcard_cache.get(key)
    if result:
        logger.info("cache_hit", cache="flashcards", topic=topic)
    return result


def set_cached_flashcards(grade: str, subject: str, topic: str, language: str, data: dict) -> None:
    """Cache flashcards."""
    key = _make_key("flashcards", grade, subject, topic, language)
    _flashcard_cache[key] = data
    logger.info("cache_set", cache="flashcards", topic=topic)


# -- Dashboard Cache -----------------------------------------------------------


def get_cached_dashboard(child_id: str) -> dict | None:
    """Get cached dashboard data, or None if not cached."""
    key = _make_key("dashboard", child_id)
    result = _dashboard_cache.get(key)
    if result:
        logger.info("cache_hit", cache="dashboard", child_id=child_id[:8])
    return result


def set_cached_dashboard(child_id: str, data: dict) -> None:
    """Cache dashboard data."""
    key = _make_key("dashboard", child_id)
    _dashboard_cache[key] = data
    logger.info("cache_set", cache="dashboard", child_id=child_id[:8])


def invalidate_dashboard(child_id: str) -> None:
    """Invalidate dashboard cache (call after grading, new worksheet, etc.)."""
    key = _make_key("dashboard", child_id)
    _dashboard_cache.pop(key, None)
    logger.info("cache_invalidate", cache="dashboard", child_id=child_id[:8])


# -- Stats ---------------------------------------------------------------------


def cache_stats() -> dict:
    """Return current cache sizes and capacities."""
    return {
        "revision": {"size": len(_revision_cache), "maxsize": _revision_cache.maxsize, "ttl": _revision_cache.ttl},
        "flashcards": {"size": len(_flashcard_cache), "maxsize": _flashcard_cache.maxsize, "ttl": _flashcard_cache.ttl},
        "dashboard": {"size": len(_dashboard_cache), "maxsize": _dashboard_cache.maxsize, "ttl": _dashboard_cache.ttl},
    }


def clear_all() -> None:
    """Clear all caches."""
    _revision_cache.clear()
    _flashcard_cache.clear()
    _dashboard_cache.clear()
    logger.info("all_caches_cleared")
