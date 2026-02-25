import structlog
from fastapi import APIRouter, HTTPException, Query, Request

from app.core.deps import DbClient, UserId, verify_child_ownership
from app.middleware.rate_limit import limiter

logger = structlog.get_logger("skolar.analytics")

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/skill_accuracy")
@limiter.limit("60/minute")
async def skill_accuracy(request: Request, user_id: UserId, db: DbClient):
    try:
        # Get user's children to scope data to this user only
        children_res = db.table("children").select("id").eq("user_id", user_id).execute()
        child_ids = [c["id"] for c in (children_res.data or [])]
        if not child_ids:
            return []
        res = db.table("v_skill_accuracy").select("*").in_("student_id", child_ids).execute()
        return res.data
    except Exception as e:
        logger.error("skill_accuracy_failed", user_id=user_id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to fetch skill accuracy")


@router.get("/error_distribution")
@limiter.limit("60/minute")
async def error_distribution(
    request: Request,
    user_id: UserId,
    db: DbClient,
    skill_tag: str | None = Query(default=None, max_length=100),
):
    try:
        # Get user's children to scope data to this user only
        children_res = db.table("children").select("id").eq("user_id", user_id).execute()
        child_ids = [c["id"] for c in (children_res.data or [])]
        if not child_ids:
            return []
        q = db.table("v_error_distribution").select("*").in_("student_id", child_ids)
        if skill_tag:
            q = q.eq("skill_tag", skill_tag)
        return q.execute().data
    except Exception as e:
        logger.error("error_distribution_failed", user_id=user_id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to fetch error distribution")


@router.get("/student_progress")
@limiter.limit("60/minute")
async def student_progress(request: Request, user_id: UserId, db: DbClient, student_id: str = Query(...)):
    verify_child_ownership(user_id, student_id)
    try:
        return db.table("v_student_skill_progress").select("*").eq("student_id", student_id).execute().data
    except Exception as e:
        logger.error("student_progress_failed", user_id=user_id, student_id=student_id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to fetch student progress")
