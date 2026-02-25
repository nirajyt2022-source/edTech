import logging

from fastapi import APIRouter, Header, Query, Request
from app.services.supabase_client import get_supabase_client
from app.core.deps import get_current_user_id, verify_child_ownership
from app.middleware.rate_limit import limiter

logger = logging.getLogger("skolar.analytics")

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/skill_accuracy")
@limiter.limit("60/minute")
def skill_accuracy(request: Request, authorization: str = Header(...)):
    user_id = get_current_user_id(authorization)
    try:
        sb = get_supabase_client()
        res = sb.table("v_skill_accuracy").select("*").execute()
        return res.data
    except Exception as e:
        logger.error("skill_accuracy failed for user=%s: %s", user_id, e)
        return []


@router.get("/error_distribution")
@limiter.limit("60/minute")
def error_distribution(request: Request, authorization: str = Header(...), skill_tag: str | None = None):
    user_id = get_current_user_id(authorization)
    try:
        sb = get_supabase_client()
        q = sb.table("v_error_distribution").select("*")
        if skill_tag:
            q = q.eq("skill_tag", skill_tag)
        return q.execute().data
    except Exception as e:
        logger.error("error_distribution failed for user=%s: %s", user_id, e)
        return []


@router.get("/student_progress")
@limiter.limit("60/minute")
def student_progress(request: Request, authorization: str = Header(...), student_id: str = Query(...)):
    user_id = get_current_user_id(authorization)
    verify_child_ownership(user_id, student_id)
    try:
        sb = get_supabase_client()
        return (
            sb.table("v_student_skill_progress")
            .select("*")
            .eq("student_id", student_id)
            .execute()
            .data
        )
    except Exception as e:
        logger.error("student_progress failed for user=%s student=%s: %s", user_id, student_id, e)
        return []
