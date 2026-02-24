"""Saved worksheets API — list, get, delete user's saved worksheets."""

import structlog
from fastapi import APIRouter, HTTPException, Header
from supabase import create_client

from app.core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()
supabase = create_client(settings.supabase_url, settings.supabase_service_key)

router = APIRouter(prefix="/api/worksheets", tags=["saved-worksheets"])


def _get_user_id(authorization: str | None) -> str:
    """Extract user ID from Supabase JWT token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = authorization.replace("Bearer ", "")
    try:
        user = supabase.auth.get_user(token)
        return user.user.id
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


@router.get("/saved/list")
async def list_saved_worksheets(
    authorization: str = Header(None),
    limit: int = 20,
    offset: int = 0,
    child_id: str | None = None,
    class_id: str | None = None,
):
    """List user's saved worksheets."""
    user_id = _get_user_id(authorization)

    try:
        query = (
            supabase.table("worksheets")
            .select("*, children(id, name), teacher_classes(id, name)")
            .eq("user_id", user_id)
        )

        if child_id:
            query = query.eq("child_id", child_id)
        if class_id:
            query = query.eq("class_id", class_id)

        result = (
            query.order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )

        worksheets = []
        for row in result.data:
            child_data = row.get("children")
            class_data = row.get("teacher_classes")
            worksheets.append({
                "id": row["id"],
                "title": row.get("title", ""),
                "board": row.get("board"),
                "grade": row.get("grade", ""),
                "subject": row.get("subject", ""),
                "topic": row.get("topic", ""),
                "difficulty": row.get("difficulty", "mixed"),
                "language": row.get("language", "English"),
                "question_count": len(row.get("questions", [])),
                "created_at": row.get("created_at"),
                "child_id": row.get("child_id"),
                "child_name": child_data.get("name") if child_data else None,
                "class_id": row.get("class_id"),
                "class_name": class_data.get("name") if class_data else None,
                "regeneration_count": row.get("regeneration_count", 0),
            })

        return {"worksheets": worksheets, "count": len(worksheets)}

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("list_saved_worksheets_failed", error=str(exc), user_id=user_id)
        raise HTTPException(status_code=500, detail="Failed to list worksheets")


@router.get("/saved/{worksheet_id}")
async def get_saved_worksheet(
    worksheet_id: str,
    authorization: str = Header(None),
):
    """Get a saved worksheet by ID."""
    user_id = _get_user_id(authorization)

    try:
        result = (
            supabase.table("worksheets")
            .select("*")
            .eq("id", worksheet_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=404, detail="Worksheet not found")

        return result.data

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_saved_worksheet_failed", error=str(exc), worksheet_id=worksheet_id)
        raise HTTPException(status_code=500, detail="Failed to get worksheet")


@router.delete("/saved/{worksheet_id}")
async def delete_saved_worksheet(
    worksheet_id: str,
    authorization: str = Header(None),
):
    """Delete a saved worksheet."""
    user_id = _get_user_id(authorization)

    try:
        supabase.table("worksheets").delete().eq("id", worksheet_id).eq("user_id", user_id).execute()
        return {"success": True, "deleted": worksheet_id}

    except Exception as exc:
        logger.error("delete_saved_worksheet_failed", error=str(exc), worksheet_id=worksheet_id)
        raise HTTPException(status_code=500, detail="Failed to delete worksheet")
