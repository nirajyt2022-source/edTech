from datetime import datetime

import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.deps import DbClient, UserId
from app.middleware.rate_limit import limiter

router = APIRouter(prefix="/api/topic-preferences", tags=["topic-preferences"])
logger = structlog.get_logger("skolar.topic_preferences")


class TopicSelection(BaseModel):
    chapter: str = Field(max_length=200)
    topics: list[str] = Field(max_length=50)  # List of selected topic names


class SavePreferencesRequest(BaseModel):
    child_id: str = Field(max_length=100)
    subject: str = Field(max_length=50)
    selected_topics: list[TopicSelection] = Field(max_length=100)


class TopicPreferences(BaseModel):
    id: str
    child_id: str
    subject: str
    selected_topics: list[TopicSelection]


@router.get("/{child_id}/{subject}")
@limiter.limit("60/minute")
async def get_topic_preferences(request: Request, child_id: str, subject: str, user_id: UserId, db: DbClient):
    """Get saved topic preferences for a child and subject."""
    try:
        # Verify child belongs to user
        child_result = db.table("children").select("id").eq("id", child_id).eq("user_id", user_id).single().execute()

        if not child_result.data:
            raise HTTPException(status_code=404, detail="Child not found")

        # Get preferences
        result = (
            db.table("topic_preferences").select("*").eq("child_id", child_id).eq("subject", subject).single().execute()
        )

        if not result.data:
            # Return empty preferences (means all selected by default)
            return {
                "child_id": child_id,
                "subject": subject,
                "selected_topics": None,  # None means all selected
                "has_preferences": False,
            }

        return {
            "id": result.data["id"],
            "child_id": result.data["child_id"],
            "subject": result.data["subject"],
            "selected_topics": result.data["selected_topics"],
            "has_preferences": True,
        }

    except HTTPException:
        raise
    except Exception as e:
        # If no preferences found, return empty (all selected)
        if "No rows" in str(e) or "0 rows" in str(e):
            return {"child_id": child_id, "subject": subject, "selected_topics": None, "has_preferences": False}
        logger.error("Failed to get preferences: %s", e)
        raise HTTPException(status_code=500, detail="Something went wrong. Please try again.")


@router.post("/")
@limiter.limit("30/minute")
async def save_topic_preferences(request: Request, body: SavePreferencesRequest, user_id: UserId, db: DbClient):
    """Save topic preferences for a child and subject."""
    try:
        # Verify child belongs to user
        child_result = (
            db.table("children").select("id").eq("id", body.child_id).eq("user_id", user_id).single().execute()
        )

        if not child_result.data:
            raise HTTPException(status_code=404, detail="Child not found")

        # Convert to JSON-serializable format
        selected_topics_data = [{"chapter": t.chapter, "topics": t.topics} for t in body.selected_topics]

        # Upsert preferences
        result = (
            db.table("topic_preferences")
            .upsert(
                {
                    "user_id": user_id,
                    "child_id": body.child_id,
                    "subject": body.subject,
                    "selected_topics": selected_topics_data,
                    "updated_at": datetime.now().isoformat(),
                },
                on_conflict="child_id,subject",
            )
            .execute()
        )

        if result.data:
            return {"success": True, "preferences": result.data[0]}
        else:
            raise HTTPException(status_code=500, detail="Failed to save preferences")

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to save preferences: %s", e)
        raise HTTPException(status_code=500, detail="Something went wrong. Please try again.")


@router.delete("/{child_id}/{subject}")
@limiter.limit("30/minute")
async def clear_topic_preferences(request: Request, child_id: str, subject: str, user_id: UserId, db: DbClient):
    """Clear topic preferences (reset to all selected)."""
    try:
        db.table("topic_preferences").delete().eq("child_id", child_id).eq("subject", subject).eq(
            "user_id", user_id
        ).execute()

        return {"success": True, "message": "Preferences cleared"}

    except Exception as e:
        logger.error("Failed to clear preferences: %s", e)
        raise HTTPException(status_code=500, detail="Something went wrong. Please try again.")
