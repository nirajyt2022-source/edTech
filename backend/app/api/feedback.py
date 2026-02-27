"""App-wide feedback API — collect general feedback from parents and teachers."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.deps import DbClient, UserId
from app.middleware.rate_limit import limiter

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/feedback", tags=["feedback"])


class AppFeedbackRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    categories: list[str] = Field(default_factory=list)
    comment: str | None = Field(default=None, max_length=1000)
    page: str | None = Field(default=None, max_length=50)
    role: str | None = Field(default=None, max_length=20)


@router.post("", status_code=201)
@limiter.limit("5/minute")
async def submit_app_feedback(
    request: Request,
    body: AppFeedbackRequest,
    user_id: UserId,
    db: DbClient,
):
    """Submit general app feedback (rating + categories + comment)."""
    try:
        db.table("app_feedback").insert(
            {
                "user_id": user_id,
                "rating": body.rating,
                "categories": body.categories,
                "comment": body.comment,
                "page": body.page,
                "role": body.role,
            }
        ).execute()
    except Exception:
        logger.error("Failed to insert app feedback", user_id=user_id, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save feedback.")

    logger.info("app_feedback_submitted", user_id=user_id, rating=body.rating, categories=body.categories)
    return {"status": "ok"}
