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

    all_ok = all(v == "ok" for k, v in checks.items() if k != "ai_stats")

    return {
        "status": "healthy" if all_ok else "degraded",
        "checks": checks,
    }
