from datetime import datetime

import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from app.core.deps import DbClient, UserId
from app.middleware.rate_limit import limiter
from app.middleware.sanitize import sanitize_string

router = APIRouter(prefix="/api/classes", tags=["classes"])
logger = structlog.get_logger("skolar.classes")


class CreateClassRequest(BaseModel):
    name: str = Field(..., max_length=100)
    grade: str = Field(..., max_length=20)
    subject: str = Field(..., max_length=50)
    board: str = Field(default="CBSE", max_length=50)
    syllabus_source: str = "cbse"
    custom_syllabus: dict | None = None

    @field_validator("name", "grade", "subject", "board", mode="before")
    @classmethod
    def _sanitize(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return sanitize_string(v, "name")


class UpdateClassRequest(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    grade: str | None = Field(default=None, max_length=20)
    subject: str | None = Field(default=None, max_length=50)
    board: str | None = Field(default=None, max_length=50)
    syllabus_source: str | None = None
    custom_syllabus: dict | None = None

    @field_validator("name", "grade", "subject", "board", mode="before")
    @classmethod
    def _sanitize(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return sanitize_string(v, "name")


@router.post("/")
@limiter.limit("30/minute")
async def create_class(request: Request, body: CreateClassRequest, user_id: UserId, db: DbClient):
    """Create a new teacher class."""
    if body.syllabus_source not in ("cbse", "custom"):
        raise HTTPException(status_code=400, detail="syllabus_source must be 'cbse' or 'custom'")

    try:
        result = (
            db.table("teacher_classes")
            .insert(
                {
                    "user_id": user_id,
                    "name": body.name,
                    "grade": body.grade,
                    "subject": body.subject,
                    "board": body.board,
                    "syllabus_source": body.syllabus_source,
                    "custom_syllabus": body.custom_syllabus,
                }
            )
            .execute()
        )

        if result.data:
            return {"success": True, "class": result.data[0]}
        else:
            raise HTTPException(status_code=500, detail="Failed to create class")

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to create class: %s", e)
        raise HTTPException(status_code=500, detail="Something went wrong. Please try again.")


@router.get("/")
@limiter.limit("60/minute")
async def list_classes(request: Request, user_id: UserId, db: DbClient):
    """List all classes for the authenticated teacher."""
    try:
        result = (
            db.table("teacher_classes").select("*").eq("user_id", user_id).order("created_at", desc=False).execute()
        )

        return {"classes": result.data}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to list classes: %s", e)
        raise HTTPException(status_code=500, detail="Something went wrong. Please try again.")


@router.get("/{class_id}")
@limiter.limit("60/minute")
async def get_class(request: Request, class_id: str, user_id: UserId, db: DbClient):
    """Get a single class by ID."""
    try:
        result = db.table("teacher_classes").select("*").eq("id", class_id).eq("user_id", user_id).single().execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Class not found")

        return result.data

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get class: %s", e)
        raise HTTPException(status_code=500, detail="Something went wrong. Please try again.")


@router.put("/{class_id}")
@limiter.limit("30/minute")
async def update_class(request: Request, class_id: str, body: UpdateClassRequest, user_id: UserId, db: DbClient):
    """Update a class."""

    try:
        update_data = {}
        if body.name is not None:
            update_data["name"] = body.name
        if body.grade is not None:
            update_data["grade"] = body.grade
        if body.subject is not None:
            update_data["subject"] = body.subject
        if body.board is not None:
            update_data["board"] = body.board
        if body.syllabus_source is not None:
            if body.syllabus_source not in ("cbse", "custom"):
                raise HTTPException(status_code=400, detail="syllabus_source must be 'cbse' or 'custom'")
            update_data["syllabus_source"] = body.syllabus_source
        if body.custom_syllabus is not None:
            update_data["custom_syllabus"] = body.custom_syllabus

        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        update_data["updated_at"] = datetime.now().isoformat()

        result = db.table("teacher_classes").update(update_data).eq("id", class_id).eq("user_id", user_id).execute()

        if result.data:
            return {"success": True, "class": result.data[0]}
        else:
            raise HTTPException(status_code=404, detail="Class not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update class: %s", e)
        raise HTTPException(status_code=500, detail="Something went wrong. Please try again.")


@router.get("/{class_id}/dashboard")
@limiter.limit("60/minute")
async def get_class_dashboard(
    request: Request,
    class_id: str,
    user_id: UserId,
    db: DbClient,
):
    """Return class mastery heatmap, weak topics, and per-student summaries.

    Response:
        class_name, total_students, children[], heatmap, weak_topics[], child_summaries{}
    """

    # 1. Verify teacher owns this class
    try:
        cls_result = (
            db.table("teacher_classes")
            .select("id, name, grade, subject")
            .eq("id", class_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        cls = getattr(cls_result, "data", None)
    except Exception as e:
        logger.error("[get_class_dashboard] DB error verifying class %s: %s", class_id, e)
        raise HTTPException(status_code=500, detail="Something went wrong. Please try again.")

    if not cls:
        raise HTTPException(status_code=403, detail="Access denied or class not found")

    # 2. Find distinct children linked to this class via worksheets
    try:
        ws_result = db.table("worksheets").select("child_id").eq("class_id", class_id).execute()
        ws_rows = getattr(ws_result, "data", None) or []
    except Exception as e:
        logger.error("[get_class_dashboard] DB error fetching worksheets for class %s: %s", class_id, e)
        raise HTTPException(status_code=500, detail="Database error fetching worksheets")

    child_ids = list({row["child_id"] for row in ws_rows if row.get("child_id")})

    if not child_ids:
        return {
            "class_name": cls["name"],
            "total_students": 0,
            "children": [],
            "heatmap": {},
            "weak_topics": [],
            "child_summaries": {},
        }

    # 3. Get child names
    try:
        children_result = db.table("children").select("id, name").in_("id", child_ids).execute()
        children_rows = getattr(children_result, "data", None) or []
    except Exception as e:
        logger.error("[get_class_dashboard] DB error fetching children for class %s: %s", class_id, e)
        raise HTTPException(status_code=500, detail="Database error fetching children")

    child_name_map = {c["id"]: c["name"] for c in children_rows}

    # 4. Get topic_mastery for all children (service key bypasses RLS)
    try:
        mastery_result = (
            db.table("topic_mastery").select("child_id, topic_slug, mastery_level").in_("child_id", child_ids).execute()
        )
        mastery_rows = getattr(mastery_result, "data", None) or []
    except Exception as e:
        logger.error("[get_class_dashboard] DB error fetching mastery for class %s: %s", class_id, e)
        raise HTTPException(status_code=500, detail="Database error fetching mastery data")

    # 5. Build heatmap: {topic_slug: {child_id: mastery_level}}
    heatmap: dict = {}
    for row in mastery_rows:
        cid = row["child_id"]
        slug = row["topic_slug"]
        level = row["mastery_level"]
        if slug not in heatmap:
            heatmap[slug] = {}
        heatmap[slug][cid] = level

    # 6. Build child_summaries
    child_summaries: dict = {}
    for cid in child_ids:
        child_mastery = [r for r in mastery_rows if r["child_id"] == cid]
        mastered_count = sum(1 for r in child_mastery if r["mastery_level"] == "mastered")
        needs_attention_count = sum(1 for r in child_mastery if r["mastery_level"] in ("learning", "unknown"))
        child_summaries[cid] = {
            "name": child_name_map.get(cid, "Unknown"),
            "mastered_count": mastered_count,
            "needs_attention_count": needs_attention_count,
        }

    # 7. Weak topics: >50% of children at learning/unknown
    n_children = len(child_ids)
    weak_topics = [
        slug
        for slug, child_levels in heatmap.items()
        if sum(1 for lv in child_levels.values() if lv in ("learning", "unknown")) > n_children * 0.5
    ]

    return {
        "class_name": cls["name"],
        "total_students": len(child_ids),
        "children": [{"id": cid, "name": child_name_map.get(cid, "Unknown")} for cid in child_ids],
        "heatmap": heatmap,
        "weak_topics": weak_topics,
        "child_summaries": child_summaries,
    }


@router.delete("/{class_id}")
@limiter.limit("30/minute")
async def delete_class(request: Request, class_id: str, user_id: UserId, db: DbClient):
    """Delete a class."""
    try:
        db.table("teacher_classes").delete().eq("id", class_id).eq("user_id", user_id).execute()

        return {"success": True, "deleted": class_id}

    except Exception as e:
        logger.error("Failed to delete class: %s", e)
        raise HTTPException(status_code=500, detail="Something went wrong. Please try again.")
