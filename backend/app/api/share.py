"""Share endpoints — public worksheet viewer + share URL generation."""

from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.deps import DbClient, UserId
from app.middleware.rate_limit import limiter

router = APIRouter(prefix="/api/worksheets", tags=["share"])

logger = structlog.get_logger("skolar.share")

SHARE_BASE_URL = get_settings().frontend_url


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


@router.post("/{worksheet_id}/share", response_model=ShareResponse)
@limiter.limit("30/minute")
async def create_share_link(
    request: Request,
    worksheet_id: str,
    user_id: UserId,
    db: DbClient,
):
    """Generate a public share URL for a worksheet. Owner only."""
    try:
        result = db.table("worksheets").select("id, user_id").eq("id", worksheet_id).execute()
    except Exception as e:
        logger.error("DB query failed for worksheet %s: %s", worksheet_id, e)
        raise HTTPException(status_code=500, detail="Failed to look up worksheet")

    if not result.data:
        raise HTTPException(status_code=404, detail="Worksheet not found")

    ws = result.data[0]
    if ws["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="You can only share your own worksheets")

    # Mark worksheet as shared
    db.table("worksheets").update(
        {
            "shared_at": datetime.now(timezone.utc).isoformat(),
        }
    ).eq("id", worksheet_id).execute()

    share_url = f"{SHARE_BASE_URL}/shared/{worksheet_id}"
    return ShareResponse(share_url=share_url)


@router.get("/shared/{worksheet_id}", response_model=SharedWorksheetResponse)
@limiter.limit("60/minute")
async def get_shared_worksheet(request: Request, worksheet_id: str, db: DbClient):
    """Public endpoint — fetch a shared worksheet without auth."""
    try:
        result = (
            db.table("worksheets")
            .select("id, title, grade, subject, topic, difficulty, language, questions")
            .eq("id", worksheet_id)
            .not_.is_("shared_at", "null")
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
