from fastapi import APIRouter, HTTPException, Header, Request
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
import logging
from supabase import create_client
from app.core.config import get_settings
from app.middleware.rate_limit import limiter
from app.middleware.sanitize import sanitize_string

router = APIRouter(prefix="/api/users", tags=["users"])
logger = logging.getLogger("skolar.users")

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
    school_name: str | None = Field(default=None, max_length=200)
    region: str | None = Field(default=None, max_length=100)

    @field_validator("school_name", "region", mode="before")
    @classmethod
    def _sanitize(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return sanitize_string(v, "name")


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
        logger.error("Auth verification failed: %s", e)
        raise HTTPException(status_code=401, detail="Authentication failed")


@router.get("/profile")
@limiter.limit("60/minute")
async def get_profile(request: Request, authorization: str = Header(...)):
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
        logger.error("Failed to get profile: %s", e)
        raise HTTPException(status_code=500, detail="Something went wrong. Please try again.")


@router.put("/profile")
@limiter.limit("30/minute")
async def upsert_profile(
    request: Request,
    body: UpdateProfileRequest,
    authorization: str = Header(...)
):
    """Create or update the user's profile."""
    user_id = get_user_id_from_token(authorization)

    if body.role not in ("parent", "teacher"):
        raise HTTPException(status_code=400, detail="Role must be 'parent' or 'teacher'")

    try:
        profile_data = {
            "user_id": user_id,
            "role": body.role,
            "active_role": body.active_role or body.role,
            "subjects": body.subjects or [],
            "grades": body.grades or [],
            "school_name": body.school_name,
            "region": body.region or "India",
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
        logger.error("Failed to save profile: %s", e)
        raise HTTPException(status_code=500, detail="Something went wrong. Please try again.")


@router.post("/switch-role")
@limiter.limit("30/minute")
async def switch_role(
    request: Request,
    body: SwitchRoleRequest,
    authorization: str = Header(...)
):
    """Switch the user's active role."""
    user_id = get_user_id_from_token(authorization)

    if body.active_role not in ("parent", "teacher"):
        raise HTTPException(status_code=400, detail="active_role must be 'parent' or 'teacher'")

    try:
        result = supabase.table("user_profiles") \
            .update({
                "active_role": body.active_role,
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
        logger.error("Failed to switch role: %s", e)
        raise HTTPException(status_code=500, detail="Something went wrong. Please try again.")
