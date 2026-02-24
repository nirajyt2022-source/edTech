"""Saved worksheets API — save, list, get, delete, export-pdf, regenerate, analytics.

These endpoints were in the old worksheets.py and got deleted in Sprint A1.
Restored here as a standalone module with modern patterns.
"""

import structlog
from datetime import datetime
from urllib.parse import quote
from fastapi import APIRouter, HTTPException, Header, Response
from pydantic import BaseModel
from supabase import create_client

from app.core.config import get_settings
from app.services.pdf import get_pdf_service

logger = structlog.get_logger()
settings = get_settings()
supabase = create_client(settings.supabase_url, settings.supabase_service_key)
pdf_service = get_pdf_service()

router = APIRouter(prefix="/api/worksheets", tags=["saved-worksheets"])


# ── Auth helper ────────────────────────────────────────────────────────────────

def _get_user_id(authorization: str | None) -> str:
    """Extract user ID from Supabase JWT token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = authorization.replace("Bearer ", "")
    try:
        user = supabase.auth.get_user(token)
        return user.user.id
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# ── Pydantic models ───────────────────────────────────────────────────────────

class WorksheetForSave(BaseModel):
    title: str = ""
    grade: str = ""
    subject: str = ""
    topic: str = ""
    difficulty: str = "Mixed"
    language: str = "English"
    questions: list = []
    skill_focus: str = ""
    common_mistake: str = ""
    parent_tip: str = ""
    learning_objectives: list = []

class SaveWorksheetRequest(BaseModel):
    worksheet: WorksheetForSave
    board: str | None = None
    child_id: str | None = None
    class_id: str | None = None
    region: str | None = None

class PDFExportWorksheet(BaseModel):
    title: str = "Worksheet"
    grade: str = ""
    subject: str = ""
    topic: str = ""
    difficulty: str = "Mixed"
    language: str = "English"
    questions: list = []
    skill_focus: str = ""
    common_mistake: str = ""
    parent_tip: str = ""
    learning_objectives: list = []

    class Config:
        extra = "allow"

class PDFExportRequest(BaseModel):
    worksheet: PDFExportWorksheet
    pdf_type: str = "full"
    visual_theme: str | None = "color"

    class Config:
        extra = "allow"


# ── 1. Save worksheet ─────────────────────────────────────────────────────────

@router.post("/save")
async def save_worksheet(
    request: SaveWorksheetRequest,
    authorization: str = Header(None),
):
    """Save a generated worksheet to the database."""
    user_id = _get_user_id(authorization)

    try:
        questions_data = [q if isinstance(q, dict) else q.model_dump() for q in request.worksheet.questions]

        result = supabase.table("worksheets").insert({
            "user_id": user_id,
            "title": request.worksheet.title,
            "board": request.board,
            "grade": request.worksheet.grade,
            "subject": request.worksheet.subject,
            "topic": request.worksheet.topic,
            "difficulty": request.worksheet.difficulty,
            "language": request.worksheet.language,
            "questions": questions_data,
            "child_id": request.child_id,
            "class_id": request.class_id,
            "region": request.region or "India",
        }).execute()

        if result.data:
            return {"success": True, "worksheet_id": result.data[0]["id"]}
        else:
            raise HTTPException(status_code=500, detail="Failed to save worksheet")

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("save_worksheet_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to save worksheet")


# ── 2. List saved worksheets ──────────────────────────────────────────────────

@router.get("/saved/list")
async def list_saved_worksheets(
    authorization: str = Header(None),
    limit: int = 20,
    offset: int = 0,
    child_id: str | None = None,
    class_id: str | None = None,
):
    """List user's saved worksheets."""
    user_id = _get_user_id(authorization)

    try:
        query = (
            supabase.table("worksheets")
            .select("*, children(id, name), teacher_classes(id, name)")
            .eq("user_id", user_id)
        )

        if child_id:
            query = query.eq("child_id", child_id)
        if class_id:
            query = query.eq("class_id", class_id)

        result = (
            query.order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )

        worksheets = []
        for row in result.data:
            child_data = row.get("children")
            class_data = row.get("teacher_classes")
            worksheets.append({
                "id": row["id"],
                "title": row.get("title", ""),
                "board": row.get("board"),
                "grade": row.get("grade", ""),
                "subject": row.get("subject", ""),
                "topic": row.get("topic", ""),
                "difficulty": row.get("difficulty", "mixed"),
                "language": row.get("language", "English"),
                "question_count": len(row.get("questions", [])),
                "created_at": row.get("created_at"),
                "child_id": row.get("child_id"),
                "child_name": child_data.get("name") if child_data else None,
                "class_id": row.get("class_id"),
                "class_name": class_data.get("name") if class_data else None,
                "regeneration_count": row.get("regeneration_count", 0),
            })

        return {"worksheets": worksheets, "count": len(worksheets)}

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("list_saved_worksheets_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to list worksheets")


# ── 3. Get saved worksheet ────────────────────────────────────────────────────

@router.get("/saved/{worksheet_id}")
async def get_saved_worksheet(
    worksheet_id: str,
    authorization: str = Header(None),
):
    """Get a saved worksheet by ID."""
    user_id = _get_user_id(authorization)

    try:
        result = (
            supabase.table("worksheets")
            .select("*")
            .eq("id", worksheet_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=404, detail="Worksheet not found")

        return result.data

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_saved_worksheet_failed", error=str(exc), worksheet_id=worksheet_id)
        raise HTTPException(status_code=500, detail="Failed to get worksheet")


# ── 4. Delete saved worksheet ─────────────────────────────────────────────────

@router.delete("/saved/{worksheet_id}")
async def delete_saved_worksheet(
    worksheet_id: str,
    authorization: str = Header(None),
):
    """Delete a saved worksheet."""
    user_id = _get_user_id(authorization)

    try:
        supabase.table("worksheets").delete().eq("id", worksheet_id).eq("user_id", user_id).execute()
        return {"success": True, "deleted": worksheet_id}

    except Exception as exc:
        logger.error("delete_saved_worksheet_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to delete worksheet")


# ── 5. Export PDF ─────────────────────────────────────────────────────────────

@router.post("/export-pdf")
async def export_worksheet_pdf(request: PDFExportRequest):
    """Export a worksheet as a PDF file."""
    try:
        worksheet_dict = request.worksheet.model_dump()

        # Quality gate (log-only)
        try:
            from app.utils.quality_gate import run_quality_gate as _run_qg
            _gate_qs = []
            for _i, _q in enumerate(worksheet_dict.get("questions", []), 1):
                _gq = dict(_q)
                if "question" not in _gq:
                    _gq["question"] = _gq.get("text", "")
                if _gq.get("display_number") is None and _gq.get("number") is None:
                    try:
                        _gq["display_number"] = int(str(_gq.get("id", _i)).lower().replace("q", "").strip())
                    except (ValueError, TypeError):
                        _gq["display_number"] = _i
                _gate_qs.append(_gq)
            _gate_ws = {
                **worksheet_dict,
                "questions": _gate_qs,
                "requested_count": len(_gate_qs),
            }
            _qg_passed, _qg_issues = _run_qg(_gate_ws)
            if not _qg_passed:
                logger.warning("quality_gate_issues", count=len(_qg_issues), issues=_qg_issues)
        except Exception as _qg_exc:
            logger.warning("quality_gate_skipped", error=str(_qg_exc))

        # Generate PDF
        worksheet_dict["visual_theme"] = request.visual_theme or "color"
        pdf_bytes = pdf_service.generate_worksheet_pdf(
            worksheet_dict,
            pdf_type=request.pdf_type,
        )

        # Create safe filename
        type_suffix = f"_{request.pdf_type}" if request.pdf_type != "full" else ""
        raw_title = request.worksheet.title.replace(" ", "_")
        safe_title = raw_title.encode("ascii", errors="ignore").decode("ascii") or "worksheet"
        filename = f"{safe_title}{type_suffix}.pdf"

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"; filename*=UTF-8\'\'{quote(raw_title + type_suffix + ".pdf")}'
            },
        )
    except Exception as exc:
        logger.exception("pdf_export_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to generate PDF")


# ── 6. Regenerate worksheet ───────────────────────────────────────────────────

@router.post("/regenerate/{worksheet_id}")
async def regenerate_worksheet(
    worksheet_id: str,
    authorization: str = Header(None),
):
    """Regenerate a worksheet with the same settings using v2 generator."""
    user_id = _get_user_id(authorization)

    try:
        # Get original worksheet
        result = (
            supabase.table("worksheets")
            .select("*")
            .eq("id", worksheet_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=404, detail="Worksheet not found")

        original = result.data

        # Use v2 generator
        from app.services.worksheets_v2 import generate_worksheet
        from app.services.ai_client import get_ai_client

        client = get_ai_client()
        data, elapsed_ms, warnings = generate_worksheet(
            client=client,
            board=original.get("board", "CBSE"),
            grade_level=original["grade"],
            subject=original["subject"],
            topic=original["topic"],
            difficulty=original.get("difficulty", "mixed"),
            num_questions=len(original.get("questions", [])) or 10,
            language=original.get("language", "English"),
        )

        # Increment regeneration count
        regen_count = original.get("regeneration_count", 0)
        supabase.table("worksheets").update({
            "regeneration_count": regen_count + 1,
            "updated_at": datetime.now().isoformat(),
        }).eq("id", worksheet_id).execute()

        return {
            "worksheet": {
                "title": data.get("title", f"Worksheet: {original['topic']}"),
                "grade": original["grade"],
                "subject": original["subject"],
                "topic": original["topic"],
                "difficulty": original.get("difficulty", "Mixed"),
                "language": original.get("language", "English"),
                "questions": data.get("questions", []),
                "skill_focus": data.get("skill_focus", ""),
                "common_mistake": data.get("common_mistake", ""),
                "parent_tip": data.get("parent_tip", ""),
                "learning_objectives": data.get("learning_objectives", []),
            },
            "generation_time_ms": elapsed_ms,
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("regenerate_failed", error=str(exc), worksheet_id=worksheet_id)
        raise HTTPException(status_code=500, detail="Failed to regenerate worksheet")


# ── 7. Teacher analytics ──────────────────────────────────────────────────────

@router.get("/analytics")
async def get_teacher_analytics(authorization: str = Header(None)):
    """Get light analytics for a teacher."""
    user_id = _get_user_id(authorization)

    try:
        result = (
            supabase.table("worksheets")
            .select("topic, subject, created_at")
            .eq("user_id", user_id)
            .execute()
        )

        rows = result.data or []
        total_worksheets = len(rows)

        if total_worksheets == 0:
            return {
                "total_worksheets": 0,
                "topic_reuse_rate": 0,
                "active_weeks": 0,
                "subjects_covered": 0,
                "top_topics": [],
            }

        # Topic frequency
        topic_counts: dict[str, int] = {}
        for row in rows:
            t = row.get("topic", "Unknown")
            topic_counts[t] = topic_counts.get(t, 0) + 1

        repeated = sum(c for c in topic_counts.values() if c > 1)
        topic_reuse_rate = round(repeated / total_worksheets, 2)

        top_topics = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        top_topics_list = [{"topic": t, "count": c} for t, c in top_topics]

        weeks = set()
        for row in rows:
            created = row.get("created_at", "")
            try:
                dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                weeks.add(dt.isocalendar()[:2])
            except (ValueError, AttributeError):
                pass

        subjects = set(row.get("subject", "") for row in rows)

        return {
            "total_worksheets": total_worksheets,
            "topic_reuse_rate": topic_reuse_rate,
            "active_weeks": len(weeks),
            "subjects_covered": len(subjects),
            "top_topics": top_topics_list,
        }

    except Exception as exc:
        logger.error("analytics_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to get analytics")
