"""
Curriculum retriever for RAG (Retrieval-Augmented Generation).

Fetches NCERT-aligned curriculum content for a given topic and injects it
into AI prompts so generated content is perfectly aligned to what the
textbook actually teaches.

Usage:
    from app.services.curriculum import get_curriculum_context

    context = await get_curriculum_context("Class 4", "Maths", "Fractions")
    if context:
        enriched_prompt = f"{context}\n\n{original_prompt}"
"""

from __future__ import annotations

from typing import Any

import structlog

from app.core.deps import get_supabase_client

logger = structlog.get_logger("skolar.curriculum")

# In-memory cache -- curriculum doesn't change during app lifetime
_cache: dict[str, str | None] = {}
_raw_cache: dict[str, dict | None] = {}  # raw DB rows for get_chapter_name()


def _cache_key(grade: str, subject: str, topic: str) -> str:
    return f"{grade}|{subject}|{topic}".lower().strip()


async def get_curriculum_context(
    grade: str,
    subject: str,
    topic: str,
) -> str | None:
    """
    Fetch curriculum context for a topic.

    Returns a formatted string to inject into AI prompts, or None if no
    curriculum data exists for this topic.
    """
    key = _cache_key(grade, subject, topic)

    # Check cache first
    if key in _cache:
        logger.debug("curriculum_cache_hit", topic=topic)
        return _cache[key]

    try:
        sb = get_supabase_client()
        result = (
            sb.table("curriculum_content")
            .select("*")
            .eq("grade", grade)
            .eq("subject", subject)
            .eq("topic", topic)
            .maybe_single()
            .execute()
        )

        if not result.data:
            # Try fuzzy match -- topic name might differ slightly
            result = (
                sb.table("curriculum_content")
                .select("*")
                .eq("grade", grade)
                .eq("subject", subject)
                .ilike("topic", f"%{topic}%")
                .limit(1)
                .execute()
            )

            if not result.data or len(result.data) == 0:
                # Try semantic vector search as final fallback
                try:
                    from app.services.vector_search import get_vector_search

                    vs = get_vector_search()
                    vector_results = await vs.hybrid_search(topic, grade=grade, subject=subject, top_k=1)
                    if vector_results:
                        data = vector_results[0]
                        _raw_cache[key] = data
                        context = _format_context(data)
                        _cache[key] = context
                        logger.info(
                            "curriculum_loaded_via_vector",
                            topic=topic,
                            grade=grade,
                            matched_topic=data.get("topic"),
                        )
                        return context
                except Exception as ve:
                    logger.debug("vector_search_fallback_failed", error=str(ve))

                logger.info("curriculum_not_found", grade=grade, subject=subject, topic=topic)
                _cache[key] = None
                _raw_cache[key] = None
                return None

            data = result.data[0] if isinstance(result.data, list) else result.data
        else:
            data = result.data

        _raw_cache[key] = data
        context = _format_context(data)
        _cache[key] = context
        logger.info("curriculum_loaded", topic=topic, grade=grade)
        return context

    except Exception as e:
        logger.error("curriculum_fetch_error", error=str(e), topic=topic)
        _cache[key] = None
        _raw_cache[key] = None
        return None


def _format_context(data: dict[str, Any]) -> str:
    """Format curriculum data into a compact, token-efficient prompt string."""
    parts = ["[CURRICULUM]"]

    # Line 1: chapter identity
    if data.get("chapter_name"):
        parts.append(f"Chapter: {data['chapter_name']}")

    # Summary (compact)
    if data.get("ncert_summary"):
        parts.append(f"Teaches: {data['ncert_summary']}")

    # Key concepts (semicolon-delimited)
    if data.get("key_concepts"):
        concepts = data["key_concepts"]
        if isinstance(concepts, list) and concepts:
            parts.append(f"Concepts: {'; '.join(concepts)}")

    # Learning outcomes (semicolon-delimited)
    if data.get("learning_outcomes"):
        outcomes = data["learning_outcomes"]
        if isinstance(outcomes, list) and outcomes:
            parts.append(f"Outcomes: {'; '.join(outcomes)}")

    # Common mistakes (semicolon-delimited)
    if data.get("common_mistakes"):
        mistakes = data["common_mistakes"]
        if isinstance(mistakes, list) and mistakes:
            parts.append(f"Mistakes: {'; '.join(mistakes)}")

    # Difficulty notes (pipe-delimited on one line)
    if data.get("difficulty_notes"):
        notes = data["difficulty_notes"]
        if isinstance(notes, dict):
            dn_parts = []
            if notes.get("foundation"):
                dn_parts.append(f"Foundation: {notes['foundation']}")
            if notes.get("stretch"):
                dn_parts.append(f"Stretch: {notes['stretch']}")
            if dn_parts:
                parts.append(" | ".join(dn_parts))

    # Vocabulary, contexts, question types (pipe-delimited single line)
    extras = []
    if data.get("grade_vocabulary"):
        vocab = data["grade_vocabulary"]
        if isinstance(vocab, list) and vocab:
            extras.append(f"Vocab: {', '.join(vocab)}")
    if data.get("real_world_contexts"):
        contexts = data["real_world_contexts"]
        if isinstance(contexts, list) and contexts:
            extras.append(f"Contexts: {', '.join(contexts)}")
    if data.get("question_types"):
        qtypes = data["question_types"]
        if isinstance(qtypes, list) and qtypes:
            extras.append(f"Q-types: {', '.join(qtypes)}")
    if extras:
        parts.append(" | ".join(extras))

    parts.append("[/CURRICULUM]")

    return "\n".join(parts)


async def get_chapter_name(grade: str, subject: str, topic: str) -> str | None:
    """Return just the chapter_name from curriculum_content, or None."""
    key = _cache_key(grade, subject, topic)
    if key not in _raw_cache:
        await get_curriculum_context(grade, subject, topic)  # populates both caches
    raw = _raw_cache.get(key)
    if raw and isinstance(raw, dict) and raw.get("chapter_name"):
        return raw["chapter_name"]
    return None


async def get_semantic_curriculum_context(
    query: str,
    grade: str | None = None,
    subject: str | None = None,
    top_k: int = 3,
) -> str | None:
    """
    Multi-result semantic retrieval for open-ended questions.

    Unlike get_curriculum_context() which looks up a single (grade, subject, topic),
    this function searches across the entire curriculum using vector similarity,
    returning the top-K most relevant curriculum entries as a combined context block.

    Used by Ask Skolar for free-form student questions.
    """
    try:
        from app.services.vector_search import get_vector_search

        vs = get_vector_search()
        results = await vs.hybrid_search(query, grade=grade, subject=subject, top_k=top_k)

        if not results:
            logger.info("semantic_curriculum_no_results", query_preview=query[:60])
            return None

        # Format each result and combine
        parts = []
        for i, data in enumerate(results, 1):
            formatted = _format_context(data)
            if len(results) > 1:
                # Label each result when returning multiple
                formatted = formatted.replace("[CURRICULUM]", f"[CURRICULUM #{i}]")
                formatted = formatted.replace("[/CURRICULUM]", f"[/CURRICULUM #{i}]")
            parts.append(formatted)

        combined = "\n\n".join(parts)
        logger.info(
            "semantic_curriculum_loaded",
            query_preview=query[:60],
            result_count=len(results),
        )
        return combined
    except Exception as e:
        logger.error("semantic_curriculum_error", error=str(e), query_preview=query[:60])
        return None


def clear_cache() -> None:
    """Clear the curriculum cache (for testing or after population)."""
    _cache.clear()
    _raw_cache.clear()
    logger.info("curriculum_cache_cleared")
