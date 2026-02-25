from datetime import datetime

import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from app.core.deps import DbClient, UserId
from app.middleware.rate_limit import limiter
from app.middleware.sanitize import sanitize_string

router = APIRouter(prefix="/api/children", tags=["children"])
logger = structlog.get_logger("skolar.children")


class CreateChildRequest(BaseModel):
    name: str = Field(..., max_length=100)
    grade: str = Field(..., max_length=20)
    board: str | None = Field(default=None, max_length=50)
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("name", "grade", "board", "notes", mode="before")
    @classmethod
    def _sanitize(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return sanitize_string(v, "name")


class UpdateChildRequest(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    grade: str | None = Field(default=None, max_length=20)
    board: str | None = Field(default=None, max_length=50)
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("name", "grade", "board", "notes", mode="before")
    @classmethod
    def _sanitize(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return sanitize_string(v, "name")


class Child(BaseModel):
    id: str
    user_id: str
    name: str
    grade: str
    board: str | None
    notes: str | None
    created_at: str
    updated_at: str


@router.post("/")
@limiter.limit("30/minute")
async def create_child(request: Request, body: CreateChildRequest, user_id: UserId, db: DbClient):
    """Create a new child profile."""

    try:
        result = (
            db.table("children")
            .insert(
                {
                    "user_id": user_id,
                    "name": body.name,
                    "grade": body.grade,
                    "board": body.board,
                    "notes": body.notes,
                }
            )
            .execute()
        )

        if result.data:
            return {"success": True, "child": result.data[0]}
        else:
            raise HTTPException(status_code=500, detail="Failed to create child profile")

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to create child profile: %s", e)
        raise HTTPException(status_code=500, detail="Something went wrong. Please try again.")


@router.get("/")
@limiter.limit("60/minute")
async def list_children(request: Request, user_id: UserId, db: DbClient):
    """List all children for the authenticated user."""
    try:
        result = db.table("children").select("*").eq("user_id", user_id).order("created_at", desc=False).execute()

        return {"children": result.data}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to list children: %s", e)
        raise HTTPException(status_code=500, detail="Something went wrong. Please try again.")


@router.get("/{child_id}")
@limiter.limit("60/minute")
async def get_child(request: Request, child_id: str, user_id: UserId, db: DbClient):
    """Get a single child profile by ID."""
    try:
        result = db.table("children").select("*").eq("id", child_id).eq("user_id", user_id).single().execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Child not found")

        return result.data

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get child: %s", e)
        raise HTTPException(status_code=500, detail="Something went wrong. Please try again.")


@router.put("/{child_id}")
@limiter.limit("30/minute")
async def update_child(request: Request, child_id: str, body: UpdateChildRequest, user_id: UserId, db: DbClient):
    """Update a child profile."""

    try:
        # Build update data with only provided fields
        update_data = {}
        if body.name is not None:
            update_data["name"] = body.name
        if body.grade is not None:
            update_data["grade"] = body.grade
        if body.board is not None:
            update_data["board"] = body.board
        if body.notes is not None:
            update_data["notes"] = body.notes

        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        update_data["updated_at"] = datetime.now().isoformat()

        result = db.table("children").update(update_data).eq("id", child_id).eq("user_id", user_id).execute()

        if result.data:
            return {"success": True, "child": result.data[0]}
        else:
            raise HTTPException(status_code=404, detail="Child not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update child: %s", e)
        raise HTTPException(status_code=500, detail="Something went wrong. Please try again.")


@router.delete("/{child_id}")
@limiter.limit("30/minute")
async def delete_child(request: Request, child_id: str, user_id: UserId, db: DbClient):
    """Delete a child profile."""
    try:
        db.table("children").delete().eq("id", child_id).eq("user_id", user_id).execute()

        return {"success": True, "deleted": child_id}

    except Exception as e:
        logger.error("Failed to delete child: %s", e)
        raise HTTPException(status_code=500, detail="Something went wrong. Please try again.")
