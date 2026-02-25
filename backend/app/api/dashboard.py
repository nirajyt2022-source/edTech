import logging

from fastapi import APIRouter, Header, Query, Request

from app.core.deps import get_current_user_id, verify_child_ownership
from app.middleware.rate_limit import limiter
from app.services.dashboard_service import get_parent_dashboard

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("/parent")
@limiter.limit("60/minute")
def parent_dashboard(request: Request, authorization: str = Header(...), student_id: str = Query(...)):
    user_id = get_current_user_id(authorization)
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
        logger.error("Dashboard error for student %s: %s", student_id, e)
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
