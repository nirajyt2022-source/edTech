"""Saved worksheets API — save, list, get, delete, export-pdf, regenerate, analytics.

These endpoints were in the old worksheets.py and got deleted in Sprint A1.
Restored here as a standalone module with modern patterns.
"""

from datetime import datetime
from urllib.parse import quote

import structlog
from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from app.core.deps import AiClient, DbClient, PdfDep, UserId
from app.middleware.rate_limit import limiter

logger = structlog.get_logger("skolar.saved_worksheets")

router = APIRouter(prefix="/api/worksheets", tags=["saved-worksheets"])


# ── Pydantic models ───────────────────────────────────────────────────────────


class WorksheetForSave(BaseModel):
    title: str = Field(default="", max_length=300)
    grade: str = Field(default="", max_length=20)
    subject: str = Field(default="", max_length=50)
    topic: str = Field(default="", max_length=200)
    difficulty: str = Field(default="Mixed", max_length=20)
    language: str = Field(default="English", max_length=30)
    questions: list = Field(default_factory=list, max_length=50)
    skill_focus: str = Field(default="", max_length=200)
    common_mistake: str = Field(default="", max_length=500)
    parent_tip: str = Field(default="", max_length=500)
    learning_objectives: list = Field(default_factory=list, max_length=20)


class SaveWorksheetRequest(BaseModel):
    worksheet: WorksheetForSave
    board: str | None = None
    child_id: str | None = None
    class_id: str | None = None
    region: str | None = None


class PDFExportWorksheet(BaseModel):
    title: str = Field(default="Worksheet", max_length=300)
    grade: str = Field(default="", max_length=20)
    subject: str = Field(default="", max_length=50)
    topic: str = Field(default="", max_length=200)
    difficulty: str = Field(default="Mixed", max_length=20)
    language: str = Field(default="English", max_length=30)
    questions: list = Field(default_factory=list, max_length=50)
    skill_focus: str = Field(default="", max_length=200)
    common_mistake: str = Field(default="", max_length=500)
    parent_tip: str = Field(default="", max_length=500)
    learning_objectives: list = Field(default_factory=list, max_length=20)

    class Config:
        extra = "ignore"


class PDFExportRequest(BaseModel):
    worksheet: PDFExportWorksheet
    pdf_type: str = "full"
    visual_theme: str | None = "color"

    class Config:
        extra = "allow"


# ── 1. Save worksheet ─────────────────────────────────────────────────────────


@router.post("/save")
@limiter.limit("30/minute")
async def save_worksheet(
    request: Request,
    body: SaveWorksheetRequest,
    user_id: UserId,
    db: DbClient,
):
    """Save a generated worksheet to the database."""
    try:
        questions_data = [q if isinstance(q, dict) else q.model_dump() for q in body.worksheet.questions]

        result = (
            db.table("worksheets")
            .insert(
                {
                    "user_id": user_id,
                    "title": body.worksheet.title,
                    "board": body.board,
                    "grade": body.worksheet.grade,
                    "subject": body.worksheet.subject,
                    "topic": body.worksheet.topic,
                    "difficulty": body.worksheet.difficulty,
                    "language": body.worksheet.language,
                    "questions": questions_data,
                    "child_id": body.child_id,
                    "class_id": body.class_id,
                    "region": body.region or "India",
                }
            )
            .execute()
        )

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
@limiter.limit("60/minute")
async def list_saved_worksheets(
    request: Request,
    user_id: UserId,
    db: DbClient,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    child_id: str | None = None,
    class_id: str | None = None,
):
    """List user's saved worksheets."""
    try:
        query = db.table("worksheets").select("*, children(id, name), teacher_classes(id, name)").eq("user_id", user_id)

        if child_id:
            query = query.eq("child_id", child_id)
        if class_id:
            query = query.eq("class_id", class_id)

        result = query.order("created_at", desc=True).range(offset, offset + limit - 1).execute()

        worksheets = []
        for row in result.data:
            child_data = row.get("children")
            class_data = row.get("teacher_classes")
            worksheets.append(
                {
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
                }
            )

        return {"worksheets": worksheets, "count": len(worksheets)}

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("list_saved_worksheets_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to list worksheets")


# ── 3. Get saved worksheet ────────────────────────────────────────────────────


@router.get("/saved/{worksheet_id}")
@limiter.limit("60/minute")
async def get_saved_worksheet(
    request: Request,
    worksheet_id: str,
    user_id: UserId,
    db: DbClient,
):
    """Get a saved worksheet by ID."""
    try:
        result = db.table("worksheets").select("*").eq("id", worksheet_id).eq("user_id", user_id).single().execute()

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
@limiter.limit("30/minute")
async def delete_saved_worksheet(
    request: Request,
    worksheet_id: str,
    user_id: UserId,
    db: DbClient,
):
    """Delete a saved worksheet."""
    try:
        db.table("worksheets").delete().eq("id", worksheet_id).eq("user_id", user_id).execute()
        return {"success": True, "deleted": worksheet_id}

    except Exception as exc:
        logger.error("delete_saved_worksheet_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to delete worksheet")


# ── 5. Export PDF ─────────────────────────────────────────────────────────────


@router.post("/export-pdf")
@limiter.limit("10/minute")
async def export_worksheet_pdf(
    request: Request, body: PDFExportRequest, user_id: UserId, db: DbClient, pdf_service: PdfDep
):
    """Export a worksheet as a PDF file."""
    try:
        worksheet_dict = body.worksheet.model_dump()

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

        # Determine user tier for watermark
        _watermark = "Skolar"  # default: free tier watermark
        try:
            _sub = db.table("user_subscriptions").select("tier").eq("user_id", user_id).maybe_single().execute()
            if _sub.data and _sub.data.get("tier") == "paid":
                _watermark = None  # paid users get clean PDFs
        except Exception as _tier_exc:
            logger.warning("tier_lookup_failed", error=str(_tier_exc))

        # Encrypt answer keys with user_id prefix
        _encrypt = None
        if body.pdf_type == "answer_key":
            _encrypt = user_id[:8]

        # Generate PDF
        worksheet_dict["visual_theme"] = body.visual_theme or "color"
        pdf_bytes = pdf_service.generate_worksheet_pdf(
            worksheet_dict,
            pdf_type=body.pdf_type,
            watermark=_watermark,
            encrypt_password=_encrypt,
        )

        # Create safe filename
        type_suffix = f"_{body.pdf_type}" if body.pdf_type != "full" else ""
        raw_title = body.worksheet.title.replace(" ", "_")
        safe_title = raw_title.encode("ascii", errors="ignore").decode("ascii") or "worksheet"
        filename = f"{safe_title}{type_suffix}.pdf"

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(raw_title + type_suffix + '.pdf')}"
            },
        )
    except Exception as exc:
        logger.exception("pdf_export_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to generate PDF")


# ── 6. Regenerate worksheet ───────────────────────────────────────────────────


@router.post("/regenerate/{worksheet_id}")
@limiter.limit("10/minute")
async def regenerate_worksheet(
    request: Request,
    worksheet_id: str,
    user_id: UserId,
    db: DbClient,
    ai: AiClient,
):
    """Regenerate a worksheet with the same settings using v2 generator."""
    try:
        # Get original worksheet
        result = db.table("worksheets").select("*").eq("id", worksheet_id).eq("user_id", user_id).single().execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Worksheet not found")

        original = result.data

        # Use v2 generator
        from app.services.worksheets_v2 import generate_worksheet

        data, elapsed_ms, warnings = generate_worksheet(
            client=ai,
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
        db.table("worksheets").update(
            {
                "regeneration_count": regen_count + 1,
                "updated_at": datetime.now().isoformat(),
            }
        ).eq("id", worksheet_id).execute()

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
@limiter.limit("60/minute")
async def get_teacher_analytics(request: Request, user_id: UserId, db: DbClient):
    """Get light analytics for a teacher."""
    try:
        result = db.table("worksheets").select("topic, subject, created_at").eq("user_id", user_id).limit(500).execute()

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
