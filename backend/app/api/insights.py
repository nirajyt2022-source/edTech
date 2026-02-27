"""
Parent Insight API — child-level learning insights and weekly digest.

All insights are deterministic (no LLM). Gated by ENABLE_DIAGNOSTIC_DB.
"""

import structlog
from fastapi import APIRouter, HTTPException

from app.core.deps import DbClient, UserId

logger = structlog.get_logger("skolar.insights")

router = APIRouter(prefix="/api/children", tags=["insights"])


async def _verify_child_ownership(child_id: str, user_id: str, db) -> dict:
    """Verify that the child belongs to the authenticated user. Returns child row."""
    try:
        res = db.table("children").select("*").eq("id", child_id).eq("user_id", user_id).maybe_single().execute()
        data = getattr(res, "data", None)
    except Exception as exc:
        logger.error("Failed to verify child ownership: %s", exc)
        raise HTTPException(500, "Database error")
    if not data:
        raise HTTPException(404, "Child not found or not authorized")
    return data


@router.get("/{child_id}/insights")
async def get_child_insights(
    child_id: str,
    user_id: UserId = ...,
    db: DbClient = ...,
) -> dict:
    """Get learning insights for a specific child."""
    child = await _verify_child_ownership(child_id, user_id, db)
    child_name = child.get("name", "Your child")

    from app.services.insight_generator import generate_child_insights

    insight = generate_child_insights(child_id=child_id, child_name=child_name)

    return {
        "child_id": child_id,
        "child_name": insight.child_name,
        "strengths": [{"skill_tag": s.skill_tag, "display": s.display, "detail": s.detail} for s in insight.strengths],
        "struggles": [{"skill_tag": s.skill_tag, "display": s.display, "detail": s.detail} for s in insight.struggles],
        "improving": [{"skill_tag": s.skill_tag, "display": s.display, "detail": s.detail} for s in insight.improving],
        "weekly_summary": insight.weekly_summary,
        "actionable_tip": insight.actionable_tip,
        "next_worksheet_suggestion": insight.next_worksheet_suggestion,
    }


@router.get("/{child_id}/weekly-digest")
async def get_weekly_digest(
    child_id: str,
    user_id: UserId = ...,
    db: DbClient = ...,
) -> dict:
    """Get a 7-day learning digest for a specific child."""
    child = await _verify_child_ownership(child_id, user_id, db)
    child_name = child.get("name", "Your child")

    from app.services.insight_generator import generate_weekly_digest

    return generate_weekly_digest(child_id=child_id, child_name=child_name)
