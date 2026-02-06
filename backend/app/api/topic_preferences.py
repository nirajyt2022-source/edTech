from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from datetime import datetime
from supabase import create_client
from app.core.config import get_settings

router = APIRouter(prefix="/api/topic-preferences", tags=["topic-preferences"])

settings = get_settings()
supabase = create_client(settings.supabase_url, settings.supabase_service_key)


class TopicSelection(BaseModel):
    chapter: str
    topics: list[str]  # List of selected topic names


class SavePreferencesRequest(BaseModel):
    child_id: str
    subject: str
    selected_topics: list[TopicSelection]


class TopicPreferences(BaseModel):
    id: str
    child_id: str
    subject: str
    selected_topics: list[TopicSelection]


def get_user_id_from_token(authorization: str) -> str:
    """Extract user_id from Supabase JWT token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    token = authorization.replace("Bearer ", "")
    try:
        user_response = supabase.auth.get_user(token)
        if not user_response or not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user_response.user.id
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")


@router.get("/{child_id}/{subject}")
async def get_topic_preferences(
    child_id: str,
    subject: str,
    authorization: str = Header(None)
):
    """Get saved topic preferences for a child and subject."""
    user_id = get_user_id_from_token(authorization)

    try:
        # Verify child belongs to user
        child_result = supabase.table("children") \
            .select("id") \
            .eq("id", child_id) \
            .eq("user_id", user_id) \
            .single() \
            .execute()

        if not child_result.data:
            raise HTTPException(status_code=404, detail="Child not found")

        # Get preferences
        result = supabase.table("topic_preferences") \
            .select("*") \
            .eq("child_id", child_id) \
            .eq("subject", subject) \
            .single() \
            .execute()

        if not result.data:
            # Return empty preferences (means all selected by default)
            return {
                "child_id": child_id,
                "subject": subject,
                "selected_topics": None,  # None means all selected
                "has_preferences": False
            }

        return {
            "id": result.data["id"],
            "child_id": result.data["child_id"],
            "subject": result.data["subject"],
            "selected_topics": result.data["selected_topics"],
            "has_preferences": True
        }

    except HTTPException:
        raise
    except Exception as e:
        # If no preferences found, return empty (all selected)
        if "No rows" in str(e) or "0 rows" in str(e):
            return {
                "child_id": child_id,
                "subject": subject,
                "selected_topics": None,
                "has_preferences": False
            }
        raise HTTPException(status_code=500, detail=f"Failed to get preferences: {str(e)}")


@router.post("/")
async def save_topic_preferences(
    request: SavePreferencesRequest,
    authorization: str = Header(None)
):
    """Save topic preferences for a child and subject."""
    user_id = get_user_id_from_token(authorization)

    try:
        # Verify child belongs to user
        child_result = supabase.table("children") \
            .select("id") \
            .eq("id", request.child_id) \
            .eq("user_id", user_id) \
            .single() \
            .execute()

        if not child_result.data:
            raise HTTPException(status_code=404, detail="Child not found")

        # Convert to JSON-serializable format
        selected_topics_data = [
            {"chapter": t.chapter, "topics": t.topics}
            for t in request.selected_topics
        ]

        # Upsert preferences
        result = supabase.table("topic_preferences").upsert({
            "user_id": user_id,
            "child_id": request.child_id,
            "subject": request.subject,
            "selected_topics": selected_topics_data,
            "updated_at": datetime.now().isoformat()
        }, on_conflict="child_id,subject").execute()

        if result.data:
            return {"success": True, "preferences": result.data[0]}
        else:
            raise HTTPException(status_code=500, detail="Failed to save preferences")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save preferences: {str(e)}")


@router.delete("/{child_id}/{subject}")
async def clear_topic_preferences(
    child_id: str,
    subject: str,
    authorization: str = Header(None)
):
    """Clear topic preferences (reset to all selected)."""
    user_id = get_user_id_from_token(authorization)

    try:
        supabase.table("topic_preferences") \
            .delete() \
            .eq("child_id", child_id) \
            .eq("subject", subject) \
            .eq("user_id", user_id) \
            .execute()

        return {"success": True, "message": "Preferences cleared"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear preferences: {str(e)}")
