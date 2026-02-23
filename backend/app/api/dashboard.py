import logging
from fastapi import APIRouter, Query
from app.services.dashboard_service import get_parent_dashboard

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("/parent")
def parent_dashboard(student_id: str = Query(...)):
    try:
        return get_parent_dashboard(student_id)
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
