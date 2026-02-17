import logging
from fastapi import APIRouter, HTTPException, Header, Response
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, field_validator
from typing import Literal, Optional

from app.api.models_practice import (
    AttemptResponse,
    MasteryGetResponse,
    TopicSummaryResponse,
    ResetResponse,
    GenerateResponse,
    GradeResponse,
    ExplainResponse,
    RecommendResponse,
    DrillResponse,
)

from app.services.slot_engine import (
    attempt_and_next,
    grade_student_answer,
    explain_question,
    recommend_next_step,
    generate_isolation_drill,
    chain_drill_session,
)
from app.services.mastery_dashboard import get_mastery, topic_summary, reset_skill
from app.services.telemetry import instrument, emit_event

logger = logging.getLogger("practicecraft.v1")
router = APIRouter(prefix="/api/v1/worksheets", tags=["worksheets-v1"])


# ──────────────────────────────────────────────
# Request models (v1)
# ──────────────────────────────────────────────

class MixRecipeItemV1(BaseModel):
    skill_tag: str
    count: int
    visual_type: str | None = None
    require_student_answer: bool = False
    unique_contexts: bool = False


class WorksheetConstraintsV1(BaseModel):
    carry_required: bool = False
    allow_operations: list[str] | None = None


class GenerateRequestV1(BaseModel):
    board: str
    grade_level: str
    subject: str
    topic: str
    difficulty: Literal["easy", "medium", "hard"]
    num_questions: int = 10

    @field_validator("difficulty", mode="before")
    @classmethod
    def _lowercase_difficulty(cls, v: str) -> str:
        return v.lower() if isinstance(v, str) else v
    language: str = "English"
    custom_instructions: str | None = None
    skills: list[str] | None = None
    logic_tags: list[str] | None = None
    region: str = "India"
    problem_style: Literal["standard", "visual", "mixed"] = "standard"
    focus_skill: str | None = None
    support_skills: list[str] | None = None
    mix_recipe: list[MixRecipeItemV1] | None = None
    constraints: WorksheetConstraintsV1 | None = None
    visuals_only: bool = False
    min_visual_ratio: float | None = None


class QuestionV1(BaseModel):
    id: str
    type: str
    text: str
    options: list[str] | None = None
    correct_answer: str | None = None
    explanation: str | None = None
    difficulty: str | None = None
    answer_type: str | None = None
    sample_answer: str | None = None
    grading_notes: str | None = None
    visual_type: str | None = None
    visual_data: dict | None = None
    role: str | None = None
    skill_tag: str | None = None


class WorksheetV1(BaseModel):
    title: str
    grade: str
    subject: str
    topic: str
    difficulty: str
    language: str
    questions: list[QuestionV1]
    skill_focus: str = ""
    common_mistake: str = ""
    parent_tip: str = ""


class PDFExportRequestV1(BaseModel):
    worksheet: WorksheetV1
    pdf_type: Literal["full", "student", "answer_key"] = "full"


class GradeRequestV1(BaseModel):
    question: dict
    student_answer: str


class ExplainRequestV1(BaseModel):
    question: dict


class RecommendRequestV1(BaseModel):
    question: dict
    grade_result: dict


class DrillRequestV1(BaseModel):
    question: dict
    student_answer: str


class ChainRequestV1(BaseModel):
    root_question: dict
    attempts: list[dict]
    target_streak: int = 3


class AttemptPayloadV1(BaseModel):
    student_id: Optional[str] = None
    question: dict
    student_answer: str
    mode: str = "single"
    seed: Optional[int] = None
    worksheet_id: Optional[str] = None
    grade: Optional[str] = None
    subject: Optional[str] = None
    topic: Optional[str] = None


class MasteryResetRequestV1(BaseModel):
    student_id: str
    skill_tag: str


# ──────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────

@router.post("/generate", response_model=GenerateResponse)
@instrument(route="/api/v1/worksheets/generate", version="v1")
async def generate_v1(request: GenerateRequestV1, authorization: str = Header(None)):
    from app.api.worksheets import generate_worksheet as _legacy_generate
    from app.api.worksheets import WorksheetGenerationRequest

    # ── Subscription enforcement ──
    if authorization:
        try:
            from app.api.worksheets import get_user_id_from_token, supabase
            from app.services.subscription_check import check_and_increment_usage
            user_id = get_user_id_from_token(authorization)
            usage = await check_and_increment_usage(user_id, supabase)
            if not usage["allowed"]:
                raise HTTPException(
                    status_code=402,
                    detail={
                        "detail": usage["message"],
                        "worksheets_remaining": 0,
                        "tier": usage["tier"],
                    },
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.warning("Subscription check failed (fail-open): %s", e)

    try:
        legacy_req = WorksheetGenerationRequest(**request.model_dump())
        result = await _legacy_generate(legacy_req, authorization=None)
        ws = result.worksheet
        logger.debug(
            "v1 /generate serializing worksheet type=%s questions=%d",
            type(ws).__name__, len(getattr(ws, "questions", [])),
        )
        ws_dict = jsonable_encoder(ws.model_dump() if hasattr(ws, "model_dump") else ws)
        return GenerateResponse(
            worksheet=ws_dict,
            generation_time_ms=result.generation_time_ms,
        )
    except Exception as e:
        logger.exception("v1 /generate failed for topic=%s", request.topic)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/export-pdf")
@instrument(route="/api/v1/worksheets/export-pdf", version="v1")
async def export_pdf_v1(request: PDFExportRequestV1):
    # Returns raw PDF bytes — no JSON response model
    from app.api.worksheets import export_worksheet_pdf as _legacy_export
    from app.api.worksheets import PDFExportRequest, Worksheet
    legacy_req = PDFExportRequest(
        worksheet=Worksheet(**request.worksheet.model_dump()),
        pdf_type=request.pdf_type,
    )
    return await _legacy_export(legacy_req)


@router.post("/grade", response_model=GradeResponse)
@instrument(route="/api/v1/worksheets/grade", version="v1")
def grade_v1(req: GradeRequestV1):
    return grade_student_answer(req.question, req.student_answer)


@router.post("/explain", response_model=ExplainResponse)
@instrument(route="/api/v1/worksheets/explain", version="v1")
def explain_v1(req: ExplainRequestV1):
    return explain_question(req.question)


@router.post("/recommend", response_model=RecommendResponse)
@instrument(route="/api/v1/worksheets/recommend", version="v1")
def recommend_v1(req: RecommendRequestV1):
    return recommend_next_step(req.question, req.grade_result)


@router.post("/drill", response_model=DrillResponse)
@instrument(route="/api/v1/worksheets/drill", version="v1")
def drill_v1(req: DrillRequestV1):
    return generate_isolation_drill(req.question, req.student_answer)


@router.post("/chain")
@instrument(route="/api/v1/worksheets/chain", version="v1")
def chain_v1(req: ChainRequestV1):
    return chain_drill_session(req.root_question, req.attempts, req.target_streak)


@router.post("/attempt", response_model=AttemptResponse)
@instrument(route="/api/v1/worksheets/attempt", version="v1")
def attempt_v1(payload: AttemptPayloadV1):
    # Capture mastery_before for audit
    mastery_before = None
    skill_tag = (payload.question.get("skill_tag") if isinstance(payload.question, dict) else None)
    if payload.student_id and skill_tag:
        try:
            from app.services.mastery_store import get_mastery_store
            store = get_mastery_store()
            ms = store.get(payload.student_id, skill_tag)
            if ms:
                mastery_before = {
                    "streak": ms.streak,
                    "total_attempts": ms.total_attempts,
                    "correct_attempts": ms.correct_attempts,
                    "mastery_level": ms.mastery_level,
                }
        except Exception as e:
            logger.error(f"[worksheets_v1.attempt_v1] mastery_before capture failed: {e}", exc_info=True)

    out = attempt_and_next(payload.model_dump())

    emit_event(
        "attempt",
        route="/api/v1/worksheets/attempt",
        version="v1",
        student_id=payload.student_id,
        skill_tag=skill_tag,
        error_type=(out.get("grade_result") or {}).get("error_type"),
    )

    # Best-effort audit — never breaks the response
    try:
        from app.services.slot_engine import audit_attempt
        mastery_after_raw = out.get("mastery_state")
        mastery_after = None
        if mastery_after_raw and isinstance(mastery_after_raw, dict):
            mastery_after = {
                "streak": mastery_after_raw.get("streak"),
                "total_attempts": mastery_after_raw.get("total_attempts"),
                "correct_attempts": mastery_after_raw.get("correct_attempts"),
                "mastery_level": mastery_after_raw.get("mastery_level"),
            }
        audit_attempt(
            student_id=payload.student_id,
            worksheet_id=payload.worksheet_id,
            attempt_id=None,
            grade=payload.grade,
            subject=payload.subject,
            topic=payload.topic,
            question=payload.question,
            student_answer=payload.student_answer,
            grade_result=out.get("grade_result"),
            explanation=out.get("explanation"),
            recommendation=out.get("recommendation"),
            drill=(out.get("next") or {}).get("drill"),
            mastery_before=mastery_before,
            mastery_after=mastery_after,
        )
    except Exception as e:
        logger.error(f"[worksheets_v1.attempt_v1] audit_attempt failed: {e}", exc_info=True)

    return out


@router.get("/mastery/get", response_model=MasteryGetResponse)
@instrument(route="/api/v1/worksheets/mastery/get", version="v1")
def mastery_get_v1(student_id: str):
    return {"student_id": student_id, "skills": get_mastery(student_id)}


@router.get("/mastery/topic_summary", response_model=TopicSummaryResponse)
@instrument(route="/api/v1/worksheets/mastery/topic_summary", version="v1")
def mastery_topic_summary_v1(student_id: str, topic: str):
    return topic_summary(student_id, topic)


@router.post("/mastery/reset", response_model=ResetResponse)
@instrument(route="/api/v1/worksheets/mastery/reset", version="v1")
def mastery_reset_v1(req: MasteryResetRequestV1):
    return reset_skill(req.student_id, req.skill_tag)


@router.get("/mastery/recent_attempts")
@instrument(route="/api/v1/worksheets/mastery/recent_attempts", version="v1")
def mastery_recent_attempts_v1(student_id: str, limit: int = 50):
    import os
    if os.getenv("ENABLE_ATTEMPT_AUDIT_DB", "0") != "1":
        return {"error": "audit_disabled"}

    from app.services.supabase_client import get_supabase_client
    sb = get_supabase_client()
    result = (
        sb.table("attempt_events")
        .select("*")
        .eq("student_id", student_id)
        .order("ts", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data
