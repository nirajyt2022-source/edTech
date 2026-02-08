from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from datetime import datetime
from supabase import create_client
from app.core.config import get_settings

router = APIRouter(prefix="/api/users", tags=["users"])

settings = get_settings()
supabase = create_client(settings.supabase_url, settings.supabase_service_key)


class UserProfile(BaseModel):
    user_id: str
    role: str | None = None
    active_role: str | None = None
    subjects: list[str] | None = None
    grades: list[str] | None = None
    school_name: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class UpdateProfileRequest(BaseModel):
    role: str
    active_role: str | None = None
    subjects: list[str] | None = None
    grades: list[str] | None = None
    school_name: str | None = None


class SwitchRoleRequest(BaseModel):
    active_role: str


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


@router.get("/profile")
async def get_profile(authorization: str = Header(None)):
    """Get the current user's profile. Returns {profile: null} if no profile exists."""
    user_id = get_user_id_from_token(authorization)

    try:
        result = supabase.table("user_profiles") \
            .select("*") \
            .eq("user_id", user_id) \
            .execute()

        if result.data and len(result.data) > 0:
            return {"profile": result.data[0]}
        return {"profile": None}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get profile: {str(e)}")


@router.put("/profile")
async def upsert_profile(
    request: UpdateProfileRequest,
    authorization: str = Header(None)
):
    """Create or update the user's profile."""
    user_id = get_user_id_from_token(authorization)

    if request.role not in ("parent", "teacher"):
        raise HTTPException(status_code=400, detail="Role must be 'parent' or 'teacher'")

    try:
        profile_data = {
            "user_id": user_id,
            "role": request.role,
            "active_role": request.active_role or request.role,
            "subjects": request.subjects or [],
            "grades": request.grades or [],
            "school_name": request.school_name,
            "updated_at": datetime.now().isoformat(),
        }

        # Try to get existing profile
        existing = supabase.table("user_profiles") \
            .select("user_id") \
            .eq("user_id", user_id) \
            .execute()

        if existing.data and len(existing.data) > 0:
            # Update existing
            result = supabase.table("user_profiles") \
                .update({k: v for k, v in profile_data.items() if k != "user_id"}) \
                .eq("user_id", user_id) \
                .execute()
        else:
            # Insert new
            result = supabase.table("user_profiles") \
                .insert(profile_data) \
                .execute()

        if result.data:
            return {"profile": result.data[0]}
        else:
            raise HTTPException(status_code=500, detail="Failed to save profile")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save profile: {str(e)}")


@router.post("/switch-role")
async def switch_role(
    request: SwitchRoleRequest,
    authorization: str = Header(None)
):
    """Switch the user's active role."""
    user_id = get_user_id_from_token(authorization)

    if request.active_role not in ("parent", "teacher"):
        raise HTTPException(status_code=400, detail="active_role must be 'parent' or 'teacher'")

    try:
        result = supabase.table("user_profiles") \
            .update({
                "active_role": request.active_role,
                "updated_at": datetime.now().isoformat(),
            }) \
            .eq("user_id", user_id) \
            .execute()

        if result.data:
            return {"profile": result.data[0]}
        else:
            raise HTTPException(status_code=404, detail="Profile not found")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to switch role: {str(e)}")
