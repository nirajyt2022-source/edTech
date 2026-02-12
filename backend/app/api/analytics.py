from fastapi import APIRouter, Query
from app.services.supabase_client import get_supabase_client


router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/skill_accuracy")
def skill_accuracy():
    sb = get_supabase_client()
    res = sb.table("v_skill_accuracy").select("*").execute()
    return res.data


@router.get("/error_distribution")
def error_distribution(skill_tag: str | None = None):
    sb = get_supabase_client()
    q = sb.table("v_error_distribution").select("*")
    if skill_tag:
        q = q.eq("skill_tag", skill_tag)
    return q.execute().data


@router.get("/student_progress")
def student_progress(student_id: str = Query(...)):
    sb = get_supabase_client()
    return (
        sb.table("v_student_skill_progress")
        .select("*")
        .eq("student_id", student_id)
        .execute()
        .data
    )
