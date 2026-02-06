from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from datetime import datetime
from supabase import create_client
from app.core.config import get_settings

router = APIRouter(prefix="/api/children", tags=["children"])

settings = get_settings()
supabase = create_client(settings.supabase_url, settings.supabase_service_key)


class CreateChildRequest(BaseModel):
    name: str
    grade: str
    board: str | None = None
    notes: str | None = None


class UpdateChildRequest(BaseModel):
    name: str | None = None
    grade: str | None = None
    board: str | None = None
    notes: str | None = None


class Child(BaseModel):
    id: str
    user_id: str
    name: str
    grade: str
    board: str | None
    notes: str | None
    created_at: str
    updated_at: str


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


@router.post("/")
async def create_child(
    request: CreateChildRequest,
    authorization: str = Header(None)
):
    """Create a new child profile."""
    user_id = get_user_id_from_token(authorization)

    try:
        result = supabase.table("children").insert({
            "user_id": user_id,
            "name": request.name,
            "grade": request.grade,
            "board": request.board,
            "notes": request.notes,
        }).execute()

        if result.data:
            return {"success": True, "child": result.data[0]}
        else:
            raise HTTPException(status_code=500, detail="Failed to create child profile")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create child profile: {str(e)}")


@router.get("/")
async def list_children(
    authorization: str = Header(None)
):
    """List all children for the authenticated user."""
    user_id = get_user_id_from_token(authorization)

    try:
        result = supabase.table("children") \
            .select("*") \
            .eq("user_id", user_id) \
            .order("created_at", desc=False) \
            .execute()

        return {"children": result.data}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list children: {str(e)}")


@router.get("/{child_id}")
async def get_child(
    child_id: str,
    authorization: str = Header(None)
):
    """Get a single child profile by ID."""
    user_id = get_user_id_from_token(authorization)

    try:
        result = supabase.table("children") \
            .select("*") \
            .eq("id", child_id) \
            .eq("user_id", user_id) \
            .single() \
            .execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Child not found")

        return result.data

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get child: {str(e)}")


@router.put("/{child_id}")
async def update_child(
    child_id: str,
    request: UpdateChildRequest,
    authorization: str = Header(None)
):
    """Update a child profile."""
    user_id = get_user_id_from_token(authorization)

    try:
        # Build update data with only provided fields
        update_data = {}
        if request.name is not None:
            update_data["name"] = request.name
        if request.grade is not None:
            update_data["grade"] = request.grade
        if request.board is not None:
            update_data["board"] = request.board
        if request.notes is not None:
            update_data["notes"] = request.notes

        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        update_data["updated_at"] = datetime.now().isoformat()

        result = supabase.table("children") \
            .update(update_data) \
            .eq("id", child_id) \
            .eq("user_id", user_id) \
            .execute()

        if result.data:
            return {"success": True, "child": result.data[0]}
        else:
            raise HTTPException(status_code=404, detail="Child not found")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update child: {str(e)}")


@router.delete("/{child_id}")
async def delete_child(
    child_id: str,
    authorization: str = Header(None)
):
    """Delete a child profile."""
    user_id = get_user_id_from_token(authorization)

    try:
        result = supabase.table("children") \
            .delete() \
            .eq("id", child_id) \
            .eq("user_id", user_id) \
            .execute()

        return {"success": True, "deleted": child_id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete child: {str(e)}")
