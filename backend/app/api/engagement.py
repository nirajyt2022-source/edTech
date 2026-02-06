from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from datetime import datetime, date, timedelta
from supabase import create_client
from app.core.config import get_settings

router = APIRouter(prefix="/api/engagement", tags=["engagement"])

settings = get_settings()
supabase = create_client(settings.supabase_url, settings.supabase_service_key)


class EngagementStats(BaseModel):
    child_id: str
    total_stars: int
    current_streak: int
    longest_streak: int
    total_worksheets_completed: int
    last_activity_date: str | None


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


def ensure_engagement_exists(user_id: str, child_id: str) -> dict:
    """Ensure engagement record exists for a child."""
    result = supabase.table("child_engagement") \
        .select("*") \
        .eq("child_id", child_id) \
        .execute()

    if result.data and len(result.data) > 0:
        return result.data[0]

    # Create new engagement record
    insert_result = supabase.table("child_engagement") \
        .insert({
            "user_id": user_id,
            "child_id": child_id,
            "total_stars": 0,
            "current_streak": 0,
            "longest_streak": 0,
            "last_activity_date": None,
            "total_worksheets_completed": 0,
        }) \
        .execute()

    if insert_result.data:
        return insert_result.data[0]

    raise HTTPException(status_code=500, detail="Failed to create engagement record")


@router.get("/{child_id}", response_model=EngagementStats)
async def get_engagement(
    child_id: str,
    authorization: str = Header(None)
):
    """Get engagement stats for a child."""
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

        engagement = ensure_engagement_exists(user_id, child_id)

        return EngagementStats(
            child_id=engagement["child_id"],
            total_stars=engagement["total_stars"],
            current_streak=engagement["current_streak"],
            longest_streak=engagement["longest_streak"],
            total_worksheets_completed=engagement["total_worksheets_completed"],
            last_activity_date=engagement.get("last_activity_date"),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get engagement: {str(e)}")


@router.post("/{child_id}/complete")
async def record_completion(
    child_id: str,
    authorization: str = Header(None)
):
    """Record a worksheet completion (triggered on PDF download)."""
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

        engagement = ensure_engagement_exists(user_id, child_id)

        today = date.today()
        last_activity = None
        if engagement.get("last_activity_date"):
            last_activity = date.fromisoformat(engagement["last_activity_date"])

        # Calculate streak with 1-day grace period
        current_streak = engagement["current_streak"]
        if last_activity:
            days_since_last = (today - last_activity).days
            if days_since_last == 0:
                # Same day, no streak change
                pass
            elif days_since_last <= 2:
                # Within grace period (1 day grace = 2 days max gap)
                current_streak += 1
            else:
                # Streak broken
                current_streak = 1
        else:
            # First activity
            current_streak = 1

        # Update longest streak if needed
        longest_streak = max(engagement["longest_streak"], current_streak)

        # Award 1 star per completion
        new_stars = engagement["total_stars"] + 1
        new_total = engagement["total_worksheets_completed"] + 1

        # Update engagement
        update_result = supabase.table("child_engagement") \
            .update({
                "total_stars": new_stars,
                "current_streak": current_streak,
                "longest_streak": longest_streak,
                "total_worksheets_completed": new_total,
                "last_activity_date": today.isoformat(),
                "updated_at": datetime.now().isoformat(),
            }) \
            .eq("child_id", child_id) \
            .execute()

        return {
            "success": True,
            "stars_earned": 1,
            "total_stars": new_stars,
            "current_streak": current_streak,
            "total_completed": new_total,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to record completion: {str(e)}")
