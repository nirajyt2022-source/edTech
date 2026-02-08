from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from datetime import datetime
from supabase import create_client
from app.core.config import get_settings

router = APIRouter(prefix="/api/classes", tags=["classes"])

settings = get_settings()
supabase = create_client(settings.supabase_url, settings.supabase_service_key)


class CreateClassRequest(BaseModel):
    name: str
    grade: str
    subject: str
    board: str = "CBSE"
    syllabus_source: str = "cbse"
    custom_syllabus: dict | None = None


class UpdateClassRequest(BaseModel):
    name: str | None = None
    grade: str | None = None
    subject: str | None = None
    board: str | None = None
    syllabus_source: str | None = None
    custom_syllabus: dict | None = None


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
async def create_class(
    request: CreateClassRequest,
    authorization: str = Header(None)
):
    """Create a new teacher class."""
    user_id = get_user_id_from_token(authorization)

    if request.syllabus_source not in ("cbse", "custom"):
        raise HTTPException(status_code=400, detail="syllabus_source must be 'cbse' or 'custom'")

    try:
        result = supabase.table("teacher_classes").insert({
            "user_id": user_id,
            "name": request.name,
            "grade": request.grade,
            "subject": request.subject,
            "board": request.board,
            "syllabus_source": request.syllabus_source,
            "custom_syllabus": request.custom_syllabus,
        }).execute()

        if result.data:
            return {"success": True, "class": result.data[0]}
        else:
            raise HTTPException(status_code=500, detail="Failed to create class")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create class: {str(e)}")


@router.get("/")
async def list_classes(
    authorization: str = Header(None)
):
    """List all classes for the authenticated teacher."""
    user_id = get_user_id_from_token(authorization)

    try:
        result = supabase.table("teacher_classes") \
            .select("*") \
            .eq("user_id", user_id) \
            .order("created_at", desc=False) \
            .execute()

        return {"classes": result.data}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list classes: {str(e)}")


@router.get("/{class_id}")
async def get_class(
    class_id: str,
    authorization: str = Header(None)
):
    """Get a single class by ID."""
    user_id = get_user_id_from_token(authorization)

    try:
        result = supabase.table("teacher_classes") \
            .select("*") \
            .eq("id", class_id) \
            .eq("user_id", user_id) \
            .single() \
            .execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Class not found")

        return result.data

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get class: {str(e)}")


@router.put("/{class_id}")
async def update_class(
    class_id: str,
    request: UpdateClassRequest,
    authorization: str = Header(None)
):
    """Update a class."""
    user_id = get_user_id_from_token(authorization)

    try:
        update_data = {}
        if request.name is not None:
            update_data["name"] = request.name
        if request.grade is not None:
            update_data["grade"] = request.grade
        if request.subject is not None:
            update_data["subject"] = request.subject
        if request.board is not None:
            update_data["board"] = request.board
        if request.syllabus_source is not None:
            if request.syllabus_source not in ("cbse", "custom"):
                raise HTTPException(status_code=400, detail="syllabus_source must be 'cbse' or 'custom'")
            update_data["syllabus_source"] = request.syllabus_source
        if request.custom_syllabus is not None:
            update_data["custom_syllabus"] = request.custom_syllabus

        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        update_data["updated_at"] = datetime.now().isoformat()

        result = supabase.table("teacher_classes") \
            .update(update_data) \
            .eq("id", class_id) \
            .eq("user_id", user_id) \
            .execute()

        if result.data:
            return {"success": True, "class": result.data[0]}
        else:
            raise HTTPException(status_code=404, detail="Class not found")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update class: {str(e)}")


@router.delete("/{class_id}")
async def delete_class(
    class_id: str,
    authorization: str = Header(None)
):
    """Delete a class."""
    user_id = get_user_id_from_token(authorization)

    try:
        result = supabase.table("teacher_classes") \
            .delete() \
            .eq("id", class_id) \
            .eq("user_id", user_id) \
            .execute()

        return {"success": True, "deleted": class_id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete class: {str(e)}")
