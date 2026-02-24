from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    return {"status": "ok"}


@router.get("/health/deep")
async def deep_health():
    """Deep health check — verifies all dependencies."""
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
    except Exception:
        checks["ai_stats"] = "unavailable"

    # 4. Curriculum content count
    try:
        from app.core.deps import get_supabase_client as _get_sb
        count_result = _get_sb().table("curriculum_content").select("id", count="exact").execute()
        checks["curriculum_topics"] = count_result.count or 0
    except Exception:
        checks["curriculum_topics"] = "unavailable"

    # 5. Cache stats
    try:
        from app.services.cache import cache_stats
        checks["cache"] = cache_stats()
    except Exception:
        checks["cache"] = "unavailable"

    all_ok = all(v == "ok" for k, v in checks.items() if k not in ("ai_stats", "curriculum_topics", "cache"))

    return {
        "status": "healthy" if all_ok else "degraded",
        "checks": checks,
    }


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
