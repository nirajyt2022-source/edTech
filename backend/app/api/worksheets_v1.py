from fastapi import APIRouter, Response
from pydantic import BaseModel
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


class MasteryResetRequestV1(BaseModel):
    student_id: str
    skill_tag: str


# ──────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────

@router.post("/generate", response_model=GenerateResponse)
@instrument(route="/api/v1/worksheets/generate", version="v1")
async def generate_v1(request: GenerateRequestV1):
    # Re-use legacy generate logic via import to avoid duplication
    from app.api.worksheets import generate_worksheet as _legacy_generate
    from app.api.worksheets import WorksheetGenerationRequest
    legacy_req = WorksheetGenerationRequest(**request.model_dump())
    return await _legacy_generate(legacy_req)


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
    out = attempt_and_next(payload.model_dump())
    emit_event(
        "attempt",
        route="/api/v1/worksheets/attempt",
        version="v1",
        student_id=payload.student_id,
        skill_tag=(payload.question.get("skill_tag") if isinstance(payload.question, dict) else None),
        error_type=(out.get("grade_result") or {}).get("error_type"),
    )
    return out


@router.get("/mastery/get", response_model=MasteryGetResponse)
@instrument(route="/api/v1/worksheets/mastery/get", version="v1")
def mastery_get_v1(student_id: str):
    return {"student_id": student_id, "states": get_mastery(student_id)}


@router.get("/mastery/topic_summary", response_model=TopicSummaryResponse)
@instrument(route="/api/v1/worksheets/mastery/topic_summary", version="v1")
def mastery_topic_summary_v1(student_id: str, topic: str):
    return topic_summary(student_id, topic)


@router.post("/mastery/reset", response_model=ResetResponse)
@instrument(route="/api/v1/worksheets/mastery/reset", version="v1")
def mastery_reset_v1(req: MasteryResetRequestV1):
    return reset_skill(req.student_id, req.skill_tag)
