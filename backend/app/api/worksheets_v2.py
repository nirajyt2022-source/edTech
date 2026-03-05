"""
Worksheets v2 API — simplified prompt-to-Gemini pipeline.

Mounts at /api/v2/worksheets. The old /api/worksheets (v1) is untouched.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import sentry_sdk
import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.deps import DbClient, OpenAICompat, UserId
from app.middleware.rate_limit import limiter
from app.models.worksheet import (
    Question,
    Worksheet,
    WorksheetGenerationRequest,
    WorksheetGenerationResponse,
)
from app.services.subscription_check import check_and_increment_usage
from app.services.worksheet_generator import generate_worksheet

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v2/worksheets", tags=["worksheets-v2"])


def _map_question(q: dict, index: int) -> Question:
    """Map a raw LLM question dict to the API Question model."""
    return Question(
        id=q.get("id", f"q{index + 1}"),
        type=q.get("type", "short_answer"),
        text=q.get("text", ""),
        options=q.get("options"),
        correct_answer=q.get("correct_answer"),
        explanation=q.get("explanation"),
        difficulty=q.get("difficulty"),
        hint=q.get("hint"),
        role=q.get("role"),
        images=q.get("images"),
        visual_type=q.get("visual_type"),
        visual_data=q.get("visual_data"),
        skill_tag=q.get("skill_tag"),
        format=_infer_render_format(q.get("type", "short_answer"), q.get("options")),
        verified=not q.get("_math_unverified", False),
        ncert_alignment=q.get("ncert_alignment"),
    )


def _infer_render_format(q_type: str, options: list | None) -> str:
    """Map LLM question type to the frontend's render format."""
    if q_type == "mcq":
        n = len(options) if options else 4
        return "mcq_4" if n >= 4 else "mcq_3"
    if q_type == "fill_blank":
        return "fill_blank"
    if q_type == "true_false":
        return "true_false"
    return "short_answer"


@router.post("/generate", response_model=WorksheetGenerationResponse)
@limiter.limit("10/minute")
async def generate_worksheet_v2(
    request: Request, body: WorksheetGenerationRequest, user_id: UserId, db: DbClient, client: OpenAICompat
):
    """Generate a worksheet using the simplified v2 pipeline."""
    sentry_sdk.set_tag("topic", body.topic)
    sentry_sdk.set_tag("subject", body.subject)

    # ── Auth + Subscription enforcement ───────────────────────
    usage = await check_and_increment_usage(user_id, db)
    if not usage["allowed"]:
        raise HTTPException(status_code=402, detail=usage["message"])
    # ── End subscription enforcement ──────────────────────────

    request_id = request.headers.get("x-request-id", str(uuid.uuid4())[:8])

    from app.services.telemetry import emit_event

    engine = os.environ.get("WORKSHEET_ENGINE", "v3")

    try:
        if engine == "v3":
            from app.services.v3 import generate_worksheet_v3

            data, elapsed_ms, warnings = await asyncio.wait_for(
                asyncio.to_thread(
                    generate_worksheet_v3,
                    client=client,
                    board=body.board,
                    grade_level=body.grade_level,
                    subject=body.subject,
                    topic=body.topic,
                    difficulty=body.difficulty,
                    num_questions=body.num_questions,
                    language=body.language,
                    problem_style=body.problem_style,
                    custom_instructions=body.custom_instructions,
                    child_id=body.child_id,
                ),
                timeout=90.0,
            )
            logger.info("[v3] Generation complete: %dms, %d warnings", elapsed_ms, len(warnings))
        else:
            data, elapsed_ms, warnings = await asyncio.wait_for(
                asyncio.to_thread(
                    generate_worksheet,
                    client=client,
                    board=body.board,
                    grade_level=body.grade_level,
                    subject=body.subject,
                    topic=body.topic,
                    difficulty=body.difficulty,
                    num_questions=body.num_questions,
                    language=body.language,
                    problem_style=body.problem_style,
                    custom_instructions=body.custom_instructions,
                ),
                timeout=90.0,
            )
    except asyncio.TimeoutError:
        emit_event(
            "worksheet_generation",
            route="/api/v2/worksheets/generate",
            version=engine,
            topic=body.topic,
            ok=False,
            error_type="TimeoutError",
        )
        logger.error("[%s] Generation timed out (90s) topic=%s", engine, body.topic)
        raise HTTPException(status_code=504, detail="Worksheet generation timed out. Please try again.")
    except ValueError as exc:
        emit_event(
            "worksheet_generation",
            route="/api/v2/worksheets/generate",
            version=engine,
            topic=body.topic,
            ok=False,
            error_type="ValueError",
        )
        logger.error("[%s] Generation failed: %s", engine, exc)
        raise HTTPException(status_code=502, detail="Worksheet generation failed. Please try again.")

    emit_event(
        "worksheet_generation",
        route="/api/v2/worksheets/generate",
        version=engine,
        topic=body.topic,
        skill_tag=data.get("skill_focus"),
        latency_ms=elapsed_ms,
        ok=True,
    )

    raw_questions = data.get("questions", [])

    # Correction corpus logging (D-02) — must run before _map_question strips internal flags
    from app.services.correction_corpus import log_corrections

    log_corrections(
        raw_questions,
        user_id=user_id,
        topic=body.topic,
        subject=body.subject,
        grade=body.grade_level,
    )

    questions = [_map_question(q, i) for i, q in enumerate(raw_questions)]

    skill_coverage: dict[str, int] = {}
    for q in raw_questions:
        tag = q.get("skill_tag")
        if tag:
            skill_coverage[tag] = skill_coverage.get(tag, 0) + 1

    worksheet = Worksheet(
        title=data.get("title", f"Worksheet: {body.topic}"),
        grade=body.grade_level,
        subject=body.subject,
        topic=body.topic,
        difficulty=body.difficulty,
        language=body.language,
        questions=questions,
        skill_focus=data.get("skill_focus", ""),
        common_mistake=data.get("common_mistake", ""),
        parent_tip=data.get("parent_tip", ""),
        learning_objectives=data.get("learning_objectives", []),
        chapter_ref=data.get("chapter_ref"),
        skill_coverage=skill_coverage or None,
    )

    if engine == "v3":
        # V3 quality gate compatibility path
        qg = data.get("_quality_gate", {}) or {}
        qg_passed = bool(qg.get("passed", True))
        qg_severity = str(qg.get("severity", "ok"))
        if not qg_passed:
            release_verdict = "blocked"
        elif qg_severity == "warning":
            release_verdict = "best_effort"
        else:
            release_verdict = "released"
        release_stamps = {
            "quality_gate": qg,
            "trust_policy_version": "v1",
        }
        severity = {}
        if release_verdict == "blocked":
            failed_rules = ["V3_QUALITY_GATE_BLOCK"]
            block_reasons = [f"[V3_QUALITY_GATE_BLOCK] {qg.get('issues_count', 0)} quality issue(s)"]
        elif release_verdict == "best_effort":
            failed_rules = ["V3_QUALITY_GATE_WARNING"]
            block_reasons = []
        else:
            failed_rules = []
            block_reasons = []
    else:
        release_stamps = data.get("_release_stamps", {})
        release_verdict = data.get("_release_verdict", "released")
        severity = data.get("_warning_severity", {})
        release_meta = data.get("_release_meta", {})
        failed_rules = list(release_meta.get("failed_rules", []))
        block_reasons = list(release_meta.get("block_reasons", []))

    # Merge release stamps into severity for backward compat
    merged_stamps = {**severity, **release_stamps}
    quality_tier = merged_stamps.get("quality_tier", "high")

    has_warnings = bool(warnings)

    if release_verdict == "blocked":
        internal_verdict = "blocked"
    elif release_verdict == "best_effort" or has_warnings:
        internal_verdict = "best_effort"
    else:
        internal_verdict = "released"

    # Use pre-computed quality score from generator; recompute only as fallback
    _quality_score: float | None = data.get("_quality_score")
    if _quality_score is None:
        try:
            from app.services.quality_scorer import score_worksheet as _score_ws

            _qs = _score_ws(data, expected_count=body.num_questions)
            _quality_score = _qs.total_score
        except Exception as _qs_exc:
            logger.warning("quality_score_failed", error=str(_qs_exc))

    logger.info(
        "[worksheets_v2] internal_verdict=%s quality_score=%s quality_tier=%s request_id=%s",
        internal_verdict,
        _quality_score,
        quality_tier,
        request_id,
    )

    trust_summary = {
        "severity_max": "P0" if block_reasons else ("P1" if failed_rules else None),
        "failed_rules_count": len(failed_rules),
        "policy_version": "v1",
        "blocked_reason_codes": [],
    }
    api_verdict = internal_verdict
    api_tier = quality_tier if internal_verdict != "blocked" else "low"

    return WorksheetGenerationResponse(
        worksheet=worksheet,
        generation_time_ms=elapsed_ms,
        warnings={"generation": warnings} if has_warnings else None,
        verdict=api_verdict,
        quality_stamps=merged_stamps or None,
        quality_tier=api_tier,
        quality_score=_quality_score,
        visual_compliance=None,
        trust_summary=trust_summary,
    )


# ── Worksheet Feedback ─────────────────────────────────────────────────────


class WorksheetFeedbackRequest(BaseModel):
    child_id: str | None = Field(default=None, max_length=100)
    difficulty_rating: str = Field(..., pattern=r"^(too_easy|just_right|too_hard)$")
    comment: str | None = Field(default=None, max_length=200)


@router.post("/{worksheet_id}/feedback", status_code=201)
@limiter.limit("10/minute")
async def submit_feedback(
    request: Request,
    worksheet_id: str,
    body: WorksheetFeedbackRequest,
    user_id: UserId,
    db: DbClient,
):
    """Submit difficulty feedback for a graded worksheet."""
    try:
        db.table("worksheet_feedback").insert(
            {
                "worksheet_id": worksheet_id,
                "child_id": body.child_id,
                "user_id": user_id,
                "difficulty_rating": body.difficulty_rating,
                "comment": body.comment,
            }
        ).execute()
    except Exception:
        logger.error(
            "Failed to insert worksheet feedback",
            worksheet_id=worksheet_id,
            user_id=user_id,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Failed to save feedback.")

    return {"status": "ok"}
