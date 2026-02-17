"""Share endpoints — public worksheet viewer + share URL generation."""

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
import logging

from supabase import create_client
from app.core.config import get_settings

router = APIRouter(prefix="/api/worksheets", tags=["share"])

settings = get_settings()
supabase = create_client(settings.supabase_url, settings.supabase_service_key)

logger = logging.getLogger("practicecraft.share")

# Production frontend URL for share links
SHARE_BASE_URL = "https://ed-tech-drab.vercel.app"


class ShareResponse(BaseModel):
    share_url: str


class SharedWorksheetResponse(BaseModel):
    id: str
    title: str
    grade: str
    subject: str
    topic: str
    difficulty: str
    language: str
    questions: list[dict]
    learning_objectives: list[str] | None = None


def _get_user_id_from_token(authorization: str) -> str:
    """Extract user_id from Supabase JWT token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    token = authorization.replace("Bearer ", "")
    try:
        user_response = supabase.auth.get_user(token)
        if not user_response or not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user_response.user.id
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Auth token verification failed: %s", e)
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")


@router.post("/{worksheet_id}/share", response_model=ShareResponse)
async def create_share_link(
    worksheet_id: str,
    authorization: str = Header(None),
):
    """Generate a public share URL for a worksheet. Owner only."""
    user_id = _get_user_id_from_token(authorization)

    try:
        result = (
            supabase.table("worksheets")
            .select("id, user_id")
            .eq("id", worksheet_id)
            .execute()
        )
    except Exception as e:
        logger.error("DB query failed for worksheet %s: %s", worksheet_id, e)
        raise HTTPException(status_code=500, detail="Failed to look up worksheet")

    if not result.data:
        raise HTTPException(status_code=404, detail="Worksheet not found")

    ws = result.data[0]
    if ws["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="You can only share your own worksheets")

    share_url = f"{SHARE_BASE_URL}/shared/{worksheet_id}"
    return ShareResponse(share_url=share_url)


@router.get("/shared/{worksheet_id}", response_model=SharedWorksheetResponse)
async def get_shared_worksheet(worksheet_id: str):
    """Public endpoint — fetch a shared worksheet without auth."""
    try:
        result = (
            supabase.table("worksheets")
            .select("id, title, grade, subject, topic, difficulty, language, questions")
            .eq("id", worksheet_id)
            .execute()
        )
    except Exception as e:
        logger.error("DB query failed for shared worksheet %s: %s", worksheet_id, e)
        raise HTTPException(status_code=500, detail="Failed to fetch worksheet")

    if not result.data:
        raise HTTPException(status_code=404, detail="Worksheet not found")

    ws = result.data[0]

    # Extract learning_objectives from questions metadata if present
    learning_objectives = None
    if ws.get("questions") and len(ws["questions"]) > 0:
        first_q = ws["questions"][0]
        if isinstance(first_q, dict) and "learning_objectives" in first_q:
            learning_objectives = first_q["learning_objectives"]

    return SharedWorksheetResponse(
        id=ws["id"],
        title=ws["title"] or f"{ws['topic']} Worksheet",
        grade=ws["grade"] or "",
        subject=ws["subject"] or "",
        topic=ws["topic"] or "",
        difficulty=ws["difficulty"] or "Medium",
        language=ws["language"] or "English",
        questions=ws["questions"] or [],
        learning_objectives=learning_objectives,
    )
