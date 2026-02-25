from datetime import datetime

import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from app.core.deps import DbClient, UserId
from app.middleware.rate_limit import limiter
from app.middleware.sanitize import sanitize_string

router = APIRouter(prefix="/api/users", tags=["users"])
logger = structlog.get_logger("skolar.users")


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


@router.get("/profile")
@limiter.limit("60/minute")
async def get_profile(request: Request, user_id: UserId, db: DbClient):
    """Get the current user's profile. Returns {profile: null} if no profile exists."""
    try:
        result = db.table("user_profiles").select("*").eq("user_id", user_id).execute()

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
async def upsert_profile(request: Request, body: UpdateProfileRequest, user_id: UserId, db: DbClient):
    """Create or update the user's profile."""
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
        existing = db.table("user_profiles").select("user_id").eq("user_id", user_id).execute()

        if existing.data and len(existing.data) > 0:
            # Update existing
            result = (
                db.table("user_profiles")
                .update({k: v for k, v in profile_data.items() if k != "user_id"})
                .eq("user_id", user_id)
                .execute()
            )
        else:
            # Insert new
            result = db.table("user_profiles").insert(profile_data).execute()

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
async def switch_role(request: Request, body: SwitchRoleRequest, user_id: UserId, db: DbClient):
    """Switch the user's active role."""
    if body.active_role not in ("parent", "teacher"):
        raise HTTPException(status_code=400, detail="active_role must be 'parent' or 'teacher'")

    try:
        result = (
            db.table("user_profiles")
            .update(
                {
                    "active_role": body.active_role,
                    "updated_at": datetime.now().isoformat(),
                }
            )
            .eq("user_id", user_id)
            .execute()
        )

        if result.data:
            return {"profile": result.data[0]}
        else:
            raise HTTPException(status_code=404, detail="Profile not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to switch role: %s", e)
        raise HTTPException(status_code=500, detail="Something went wrong. Please try again.")
