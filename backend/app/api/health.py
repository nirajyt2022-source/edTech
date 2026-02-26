import os

import structlog
from fastapi import APIRouter, HTTPException, Request

logger = structlog.get_logger("skolar.health")

router = APIRouter()


@router.get("/health")
async def health_check():
    return {"status": "ok"}


@router.get("/health/deep")
async def deep_health(request: Request):
    """Deep health check — verifies all dependencies. Requires X-Health-Token header."""
    expected_token = os.environ.get("HEALTH_CHECK_TOKEN", "")
    if expected_token:
        provided = request.headers.get("X-Health-Token", "")
        if provided != expected_token:
            raise HTTPException(status_code=403, detail="Forbidden")
    checks = {}

    # 1. Supabase
    try:
        from app.core.deps import get_supabase_client

        sb = get_supabase_client()
        sb.table("profiles").select("id").limit(1).execute()
        checks["supabase"] = "ok"
    except Exception as e:
        checks["supabase"] = f"error: {str(e)[:100]}"

    # 2. Gemini API
    try:
        from app.services.ai_client import get_ai_client

        ai = get_ai_client()
        ai.generate_text("Reply with 'ok'", temperature=0, max_tokens=5)
        checks["gemini"] = "ok"
    except Exception as e:
        checks["gemini"] = f"error: {str(e)[:100]}"

    # 3. AI client stats
    try:
        from app.services.ai_client import get_ai_client

        checks["ai_stats"] = get_ai_client().stats
    except Exception as e:
        logger.debug("ai_stats_check_failed", error=str(e))
        checks["ai_stats"] = "unavailable"

    # 4. Curriculum content count
    try:
        from app.core.deps import get_supabase_client as _get_sb

        count_result = _get_sb().table("curriculum_content").select("id", count="exact").execute()
        checks["curriculum_topics"] = count_result.count or 0
    except Exception as e:
        logger.debug("curriculum_check_failed", error=str(e))
        checks["curriculum_topics"] = "unavailable"

    # 5. Cache stats
    try:
        from app.services.cache import cache_stats

        checks["cache"] = cache_stats()
    except Exception as e:
        logger.debug("cache_check_failed", error=str(e))
        checks["cache"] = "unavailable"

    # 6. Embedding service
    try:
        from app.services.embedding import get_embedding_service

        svc = get_embedding_service()
        vec = await svc.embed_text("health check")
        checks["embedding"] = "ok" if len(vec) == 768 else f"unexpected dims: {len(vec)}"
    except Exception as e:
        logger.debug("embedding_check_failed", error=str(e))
        checks["embedding"] = f"error: {str(e)[:100]}"

    # 7. Vector search (pgvector)
    try:
        from app.services.vector_search import get_vector_search

        vs = get_vector_search()
        results = await vs.semantic_search("test query", top_k=1)
        checks["vector_search"] = "ok" if isinstance(results, list) else "unexpected"
    except Exception as e:
        logger.debug("vector_search_check_failed", error=str(e))
        checks["vector_search"] = f"error: {str(e)[:100]}"

    all_ok = all(v == "ok" for k, v in checks.items() if k not in ("ai_stats", "curriculum_topics", "cache"))

    return {
        "status": "healthy" if all_ok else "degraded",
        "checks": checks,
    }


@router.get("/health/ai-metrics")
async def ai_metrics(request: Request):
    """LLMOps metrics: calls, latency, tokens, cost, cache hit rate, errors.

    Protected by the same X-Health-Token as /health/deep.
    """
    expected_token = os.environ.get("HEALTH_CHECK_TOKEN", "")
    if expected_token:
        provided = request.headers.get("X-Health-Token", "")
        if provided != expected_token:
            raise HTTPException(status_code=403, detail="Forbidden")

    try:
        from app.services.ai_client import get_llm_metrics

        return get_llm_metrics()
    except Exception as e:
        logger.error("ai_metrics_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to get AI metrics")


@router.get("/api/v1/curriculum/check")
async def check_curriculum(grade: str = "Class 3", subject: str = "Maths", topic: str = "Fractions"):
    """Check if curriculum content exists for a topic (debug endpoint)."""
    from app.services.curriculum import get_curriculum_context

    context = await get_curriculum_context(grade, subject, topic)
    return {
        "grade": grade,
        "subject": subject,
        "topic": topic,
        "has_content": context is not None,
        "content_preview": context[:500] if context else None,
    }
