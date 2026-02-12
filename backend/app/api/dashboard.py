from fastapi import APIRouter, Query
from app.services.dashboard_service import get_parent_dashboard


router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("/parent")
def parent_dashboard(student_id: str = Query(...)):
    return get_parent_dashboard(student_id)
