"""
Topic Intelligence Agent — Agent 1 of 4 in the generation pipeline.

Builds a GenerationContext by combining:
  - curriculum_canon.json  (verify topic exists in CBSE curriculum, ncert_chapter)
  - slot_engine TOPIC_PROFILES (valid_skill_tags)
  - slot_engine LEARNING_OBJECTIVES (ncert_subtopics)
  - LearningGraphService.get_adaptive_difficulty() (bloom_level, format_mix, etc.)

All external calls are fail-open: any error falls back to safe defaults so that
worksheet generation is never blocked by an intelligence-layer failure.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Safe defaults
# ---------------------------------------------------------------------------

_DEFAULT_BLOOM = "recall"
_DEFAULT_FORMAT_MIX: dict[str, int] = {"mcq": 40, "fill_blank": 30, "word_problem": 30}
_DEFAULT_SCAFFOLDING = True
_DEFAULT_CHALLENGE = False

# ---------------------------------------------------------------------------
# GenerationContext — the output model consumed by downstream agents
# ---------------------------------------------------------------------------


class GenerationContext(BaseModel):
    topic_slug: str
    subject: str
    grade: int
    ncert_chapter: str          # chapter name from curriculum canon (= topic name)
    ncert_subtopics: list[str]  # 3 learning objectives from LEARNING_OBJECTIVES
    bloom_level: str            # recall | application | reasoning
    format_mix: dict            # {mcq: int, fill_blank: int, word_problem: int}
    scaffolding: bool
    challenge_mode: bool
    valid_skill_tags: list[str] # from TOPIC_PROFILES["allowed_skill_tags"]
    child_context: dict         # ≤200 tokens of child-specific state (empty if no child_id)


# ---------------------------------------------------------------------------
# Curriculum canon loader (module-level singleton, loaded once)
# ---------------------------------------------------------------------------

_CANON_CACHE: Optional[dict] = None


def _load_canon() -> dict:
    """Load curriculum_canon.json once and cache it."""
    global _CANON_CACHE
    if _CANON_CACHE is not None:
        return _CANON_CACHE

    # Path relative to this file: backend/app/data/curriculum_canon.json
    candidates = [
        Path(__file__).parent.parent / "data" / "curriculum_canon.json",
    ]
    for path in candidates:
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    _CANON_CACHE = json.load(f)
                logger.debug("[topic_intelligence] Loaded curriculum_canon from %s", path)
                return _CANON_CACHE
            except Exception as exc:
                logger.warning("[topic_intelligence] Failed to parse %s: %s", path, exc)

    logger.warning("[topic_intelligence] curriculum_canon.json not found; using empty canon")
    _CANON_CACHE = {"grades": []}
    return _CANON_CACHE


def _lookup_canon(topic_slug: str, subject: str, grade: int) -> dict:
    """
    Search curriculum_canon.json for this grade+subject combination.

    Returns:
        {"ncert_chapter": str, "in_canon": bool}

    The topic name in the canon IS the NCERT chapter (CBSE curriculum slugs
    map 1:1 to textbook chapters). Falls back to topic_slug if not found.
    """
    canon = _load_canon()
    topic_lower = topic_slug.lower()
    subject_lower = subject.lower()

    # Normalise "EVS" → "EVS", "Science" → "Science" etc. for matching
    subject_aliases = {
        "evs": ["evs", "science"],
        "science": ["science", "evs"],
    }
    accepted = subject_aliases.get(subject_lower, [subject_lower])

    for grade_entry in canon.get("grades", []):
        try:
            if int(grade_entry.get("grade", -1)) != int(grade):
                continue
        except (ValueError, TypeError):
            continue

        for subj_entry in grade_entry.get("subjects", []):
            entry_name = subj_entry.get("name", "").lower()
            if entry_name not in accepted:
                continue
            skills: list[str] = subj_entry.get("skills", [])
            matched = next(
                (s for s in skills if s.lower() == topic_lower),
                None,
            )
            if matched:
                return {"ncert_chapter": matched, "in_canon": True}

    # Not found — still use the topic_slug as the chapter (graceful fallback)
    return {"ncert_chapter": topic_slug, "in_canon": False}


# ---------------------------------------------------------------------------
# Helpers that pull from slot_engine (imported lazily — heavy module)
# ---------------------------------------------------------------------------


def _get_skill_tags(topic_slug: str) -> list[str]:
    """Return allowed_skill_tags for this topic from TOPIC_PROFILES."""
    try:
        from app.services.slot_engine import get_topic_profile
        profile = get_topic_profile(topic_slug)
        if profile:
            return list(profile.get("allowed_skill_tags", []))
    except Exception as exc:
        logger.warning("[topic_intelligence] Could not load topic profile for %r: %s", topic_slug, exc)
    return []


def _get_subtopics(topic_slug: str) -> list[str]:
    """Return NCERT subtopics (learning objectives) for this topic."""
    try:
        from app.services.slot_engine import get_learning_objectives
        return get_learning_objectives(topic_slug)
    except Exception as exc:
        logger.warning("[topic_intelligence] Could not load learning objectives for %r: %s", topic_slug, exc)
    return []


# ---------------------------------------------------------------------------
# TopicIntelligenceAgent
# ---------------------------------------------------------------------------


class TopicIntelligenceAgent:
    """
    Agent 1 of 4 in the generation pipeline.

    Converts a (child_id, topic_slug, subject, grade) tuple into a rich
    GenerationContext that all downstream agents consume.

    Usage:
        agent = TopicIntelligenceAgent()
        ctx = await agent.build_context(child_id="uuid", topic_slug="Addition (carries)",
                                        subject="Maths", grade=3)
    """

    async def build_context(
        self,
        child_id: Optional[str],
        topic_slug: str,
        subject: str,
        grade: int,
    ) -> GenerationContext:
        """
        Build a GenerationContext for the given topic + child.

        Never raises — all failures fall back to safe defaults.
        """
        # 1. NCERT chapter from curriculum canon
        canon_info = _lookup_canon(topic_slug, subject, grade)
        ncert_chapter: str = canon_info["ncert_chapter"]

        # 2. NCERT subtopics (learning objectives)
        ncert_subtopics: list[str] = _get_subtopics(topic_slug)

        # 3. Valid skill tags from topic profile
        valid_skill_tags: list[str] = _get_skill_tags(topic_slug)

        # 4. Adaptive difficulty from Learning Graph (fail-open)
        bloom_level: str = _DEFAULT_BLOOM
        format_mix: dict = dict(_DEFAULT_FORMAT_MIX)
        scaffolding: bool = _DEFAULT_SCAFFOLDING
        challenge_mode: bool = _DEFAULT_CHALLENGE
        child_context: dict = {}

        if child_id:
            try:
                from app.services.learning_graph import get_learning_graph_service
                svc = get_learning_graph_service()
                # get_adaptive_difficulty is synchronous — run in thread to stay non-blocking
                config: dict = await asyncio.to_thread(
                    svc.get_adaptive_difficulty, child_id, topic_slug
                )
                bloom_level = config.get("bloom_level", _DEFAULT_BLOOM)
                format_mix = config.get("format_mix", dict(_DEFAULT_FORMAT_MIX))
                scaffolding = bool(config.get("scaffolding", _DEFAULT_SCAFFOLDING))
                challenge_mode = bool(config.get("challenge_mode", _DEFAULT_CHALLENGE))
                child_context = {
                    "bloom_level": bloom_level,
                    "scaffolding": scaffolding,
                    "challenge_mode": challenge_mode,
                    "format_mix": format_mix,
                }
            except Exception as exc:
                logger.warning(
                    "[topic_intelligence] get_adaptive_difficulty failed for child=%s topic=%r; "
                    "using defaults. Error: %s",
                    child_id, topic_slug, exc,
                )

        return GenerationContext(
            topic_slug=topic_slug,
            subject=subject,
            grade=grade,
            ncert_chapter=ncert_chapter,
            ncert_subtopics=ncert_subtopics,
            bloom_level=bloom_level,
            format_mix=format_mix,
            scaffolding=scaffolding,
            challenge_mode=challenge_mode,
            valid_skill_tags=valid_skill_tags,
            child_context=child_context,
        )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_AGENT: Optional[TopicIntelligenceAgent] = None


def get_topic_intelligence_agent() -> TopicIntelligenceAgent:
    """Return the module-level singleton."""
    global _AGENT
    if _AGENT is None:
        _AGENT = TopicIntelligenceAgent()
    return _AGENT
