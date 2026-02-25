import structlog
from fastapi import APIRouter, Query, Request

from app.core.deps import DbClient, UserId, verify_child_ownership
from app.middleware.rate_limit import limiter
from app.services.dashboard_service import get_parent_dashboard

logger = structlog.get_logger("skolar.dashboard")

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("/parent")
@limiter.limit("60/minute")
async def parent_dashboard(request: Request, user_id: UserId, db: DbClient, student_id: str = Query(...)):
    verify_child_ownership(user_id, student_id)

    from app.services.cache import get_cached_dashboard, set_cached_dashboard

    cached = get_cached_dashboard(student_id)
    if cached:
        return cached

    try:
        data = get_parent_dashboard(student_id)
        set_cached_dashboard(student_id, data)
        return data
    except Exception as e:
        logger.error("dashboard_failed", student_id=student_id, error=str(e))
        # Return empty dashboard instead of 500 — lets frontend render gracefully
        return {
            "student_id": student_id,
            "overall_stats": {
                "total_worksheets": 0,
                "total_stars": 0,
                "current_streak": 0,
                "longest_streak": 0,
            },
            "skills": [],
            "recent_topics": [],
        }
