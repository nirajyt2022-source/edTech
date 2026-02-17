import asyncio
import logging
import uuid
from datetime import datetime, timezone
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
# Gold-G7: Parent Insight Messages
# ──────────────────────────────────────────────

WATCH_FOR_MESSAGES: dict[str, str] = {
    "carry_tens": "Your child may be forgetting to carry when the tens column adds up to more than 9. Watch for answers that are 10 less than expected.",
    "carry_ones": "Your child may be forgetting to carry from the ones column. Look for answers where the ones digit is correct but tens are wrong.",
    "borrow_tens": "Your child may struggle with borrowing from the tens column. They might subtract the smaller digit from the larger in each column instead.",
    "borrow_ones": "Your child may be confusing when borrowing is needed. Check if they recognise when the top digit is smaller than the bottom.",
    "place_value_confusion": "Your child may be mixing up the value of digits in different places. Practice reading numbers aloud and identifying hundreds, tens, and ones.",
    "multiplication_facts": "Your child needs more practice with multiplication tables. Short daily drills (5 minutes) help build automatic recall.",
    "division_remainder": "Your child may forget about remainders or not understand what they represent. Use sharing problems with physical objects.",
    "fraction_equivalence": "Your child may not yet see that fractions like 1/2 and 2/4 are the same amount. Cutting paper or folding shapes can help.",
    "wrong_operation": "Your child may be confusing which operation to use. Help them identify keywords: 'total' and 'altogether' mean add, 'left' and 'remaining' mean subtract.",
    "calculation_error": "Your child understands the concept but makes calculation errors. Encourage checking work by doing the inverse operation.",
}

NEXT_STEP_MESSAGES: dict[str, dict[str, str]] = {
    "mastered": {
        "default": "Excellent work! Try a harder difficulty level or move to the next topic to keep the challenge going.",
        "Addition (carries)": "Great mastery of addition with carrying! Try 'Addition and subtraction (3-digit)' for mixed practice.",
        "Subtraction (borrowing)": "Borrowing is solid! Move on to 'Addition and subtraction (3-digit)' for combined practice.",
        "Multiplication (tables 2-10)": "Multiplication facts are strong! Try 'Division basics' as the natural next step.",
        "Division basics": "Division is well understood! Try 'Fractions (halves, quarters)' — division is the foundation of fractions.",
        "Fractions (halves, quarters)": "Fractions basics mastered! Try 'Fractions' for broader fraction work.",
    },
    "improving": {
        "default": "Good progress! Keep practising at this level. Consistency is more important than speed.",
    },
    "learning": {
        "default": "Keep going — every worksheet builds understanding. Try reducing the number of questions to 5 and focus on getting them right.",
    },
    "unknown": {
        "default": "This is a new topic. Start with 'easy' difficulty and build confidence before moving up.",
    },
}


def build_parent_insight(mastery_state: dict | None, topic: str = "") -> dict | None:
    """Build a parent-friendly insight dict from mastery state after grading."""
    if not mastery_state:
        return None
    level = mastery_state.get("mastery_level", "unknown")
    streak = mastery_state.get("streak", 0)
    error_type = mastery_state.get("last_error_type")

    watch_for = ""
    if error_type and error_type in WATCH_FOR_MESSAGES:
        watch_for = WATCH_FOR_MESSAGES[error_type]

    level_messages = NEXT_STEP_MESSAGES.get(level, NEXT_STEP_MESSAGES["unknown"])
    next_step = level_messages.get(topic, level_messages["default"])

    return {
        "mastery_level": level,
        "streak": streak,
        "watch_for": watch_for,
        "next_step": next_step,
    }


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
    child_id: str | None = None  # Gold-G2: mastery-aware slot adjustment


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
    learning_objectives: list[str] = []
    mastery_snapshot: dict | None = None  # Gold-G2: child's mastery state at generation time


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

    # Gold-G7: Build parent insight from mastery state after grading
    mastery_after_for_insight = out.get("mastery_state")
    if mastery_after_for_insight and isinstance(mastery_after_for_insight, dict):
        out["insight"] = build_parent_insight(
            mastery_after_for_insight,
            topic=payload.topic or "",
        )

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


# ──────────────────────────────────────────────
# Bulk generation models
# ──────────────────────────────────────────────

class BulkGenerationRequest(BaseModel):
    topics: list[str]
    num_questions: int = 10
    grade: str = "Class 3"
    count_per_topic: int = 1
    difficulty: str = "medium"
    language: str = "English"
    board: str = "CBSE"
    child_id: str | None = None


class BulkGenerationResponse(BaseModel):
    worksheets: list[dict]
    failed: list[dict]
    total_generated: int
    total_failed: int


# ──────────────────────────────────────────────
# Bulk generation endpoint
# ──────────────────────────────────────────────

VALID_NUM_QUESTIONS = {5, 10, 15, 20}


async def _generate_single_worksheet(
    topic: str,
    num_questions: int,
    difficulty: str,
    grade: str,
    language: str,
    board: str,
    region: str,
    user_id: str,
    child_id: str | None,
) -> dict:
    """Generate a single worksheet and save it to the database.

    Returns the worksheet dict on success; raises on failure.
    """
    from app.api.worksheets import (
        client, supabase, _slot_to_question, _fill_role_explanations,
        Worksheet,
    )
    from app.services.slot_engine import (
        run_slot_pipeline, hydrate_visuals, build_worksheet_plan,
        get_learning_objectives,
    )

    # Build worksheet plan for arithmetic topics
    worksheet_plan = None
    if any(kw in topic.lower() for kw in ("3-digit", "3 digit", "addition", "subtraction")):
        worksheet_plan = build_worksheet_plan(
            q_count=num_questions,
            mix_recipe=None,
            constraints=None,
            topic=topic,
        )

    # run_slot_pipeline is synchronous (makes LLM calls); wrap in thread
    # so asyncio.gather can run multiple generations in parallel.
    meta, slot_questions = await asyncio.to_thread(
        run_slot_pipeline,
        client=client,
        grade=grade,
        subject="Mathematics",
        topic=topic,
        q_count=num_questions,
        difficulty=difficulty,
        region=region,
        language=language,
        worksheet_plan=worksheet_plan,
        constraints=None,
        child_id=child_id,
    )

    hydrate_visuals(slot_questions, visuals_only=False)

    questions = [_slot_to_question(q, i) for i, q in enumerate(slot_questions)]
    _fill_role_explanations(questions)

    common_mistakes = meta.get("common_mistakes") or []
    worksheet = Worksheet(
        title=f"{meta.get('micro_skill', topic)} - Practice",
        grade=grade,
        subject="Mathematics",
        topic=topic,
        difficulty=meta.get("difficulty", difficulty).capitalize(),
        language=language,
        questions=questions,
        skill_focus=meta.get("skill_focus", ""),
        common_mistake=common_mistakes[0] if common_mistakes else "",
        parent_tip=meta.get("parent_tip", ""),
        learning_objectives=get_learning_objectives(topic),
        mastery_snapshot=meta.get("mastery_snapshot"),
    )

    # Save to database
    questions_data = [q.model_dump() for q in worksheet.questions]
    save_result = supabase.table("worksheets").insert({
        "user_id": user_id,
        "title": worksheet.title,
        "board": board,
        "grade": grade,
        "subject": "Mathematics",
        "topic": topic,
        "difficulty": worksheet.difficulty,
        "language": language,
        "questions": questions_data,
        "child_id": child_id,
        "region": region,
    }).execute()

    ws_dict = jsonable_encoder(worksheet.model_dump())
    if save_result.data:
        ws_dict["worksheet_id"] = save_result.data[0]["id"]
    else:
        logger.warning("Bulk: worksheet save returned no data for topic=%s", topic)

    return ws_dict


@router.post("/bulk", response_model=BulkGenerationResponse)
@instrument(route="/api/v1/worksheets/bulk", version="v1")
async def bulk_generate_v1(
    request: BulkGenerationRequest,
    authorization: str = Header(None),
):
    """Generate multiple worksheets across topics in parallel. Paid tier only."""

    # ── 1. Auth check ──
    from app.api.worksheets import get_user_id_from_token, supabase

    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header is required")
    user_id = get_user_id_from_token(authorization)

    # ── 2. Subscription check — paid tier only ──
    try:
        sub_result = supabase.table("user_subscriptions") \
            .select("tier") \
            .eq("user_id", user_id) \
            .execute()

        tier = "free"
        if sub_result.data:
            tier = sub_result.data[0].get("tier", "free")

        if tier != "paid":
            raise HTTPException(
                status_code=402,
                detail="Bulk generation is available for paid users only.",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Bulk: subscription tier check failed for user %s: %s", user_id, e)
        # Fail closed for bulk — require paid confirmation
        raise HTTPException(
            status_code=402,
            detail="Bulk generation is available for paid users only.",
        )

    # ── 3. Validate limits ──
    if request.num_questions not in VALID_NUM_QUESTIONS:
        raise HTTPException(
            status_code=422,
            detail=f"num_questions must be one of {sorted(VALID_NUM_QUESTIONS)}",
        )

    if len(request.topics) > 5:
        raise HTTPException(status_code=422, detail="Maximum 5 topics per bulk request")

    if len(request.topics) == 0:
        raise HTTPException(status_code=422, detail="At least 1 topic is required")

    if request.count_per_topic > 3:
        raise HTTPException(status_code=422, detail="Maximum 3 worksheets per topic")

    if request.count_per_topic < 1:
        raise HTTPException(status_code=422, detail="count_per_topic must be at least 1")

    total_worksheets = len(request.topics) * request.count_per_topic
    if total_worksheets > 15:
        raise HTTPException(status_code=422, detail="Maximum 15 worksheets per bulk request")

    # ── 4. Generate worksheets in parallel ──
    tasks = []
    task_topics = []  # Track which topic each task corresponds to
    for topic in request.topics:
        for _ in range(request.count_per_topic):
            task_topics.append(topic)
            tasks.append(
                _generate_single_worksheet(
                    topic=topic,
                    num_questions=request.num_questions,
                    difficulty=request.difficulty,
                    grade=request.grade,
                    language=request.language,
                    board=request.board,
                    region="India",
                    user_id=user_id,
                    child_id=request.child_id,
                )
            )

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # ── 5. Separate successes from failures ──
    worksheets = []
    failed = []
    for i, result in enumerate(results):
        topic = task_topics[i]
        if isinstance(result, Exception):
            logger.error("Bulk: generation failed for topic=%s: %s", topic, result, exc_info=result)
            failed.append({"topic": topic, "error": str(result)})
        else:
            worksheets.append(result)

    # ── 6. Increment subscription usage for successful generations ──
    if worksheets:
        try:
            from app.services.subscription_check import check_and_increment_usage
            # Increment once per successful worksheet
            for _ in worksheets:
                await check_and_increment_usage(user_id, supabase)
        except Exception as e:
            logger.error("Bulk: failed to increment usage for user %s: %s", user_id, e)

    logger.info(
        "Bulk generation complete: user=%s generated=%d failed=%d topics=%s",
        user_id, len(worksheets), len(failed), request.topics,
    )

    return BulkGenerationResponse(
        worksheets=worksheets,
        failed=failed,
        total_generated=len(worksheets),
        total_failed=len(failed),
    )
