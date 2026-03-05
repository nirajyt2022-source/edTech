"""
Worksheets v3 API — deterministic slot-builder pipeline.

Mounts at /api/v3/worksheets. Uses the v3 slot builder that makes all
structural decisions in Python and only asks Gemini to write question text.
"""

from __future__ import annotations

import asyncio

import sentry_sdk
import structlog
from fastapi import APIRouter, HTTPException, Request

from app.core.deps import DbClient, OpenAICompat, UserId
from app.middleware.rate_limit import limiter
from app.models.worksheet import (
    Question,
    Worksheet,
    WorksheetGenerationRequest,
    WorksheetGenerationResponse,
)
from app.services.subscription_check import check_and_increment_usage

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v3/worksheets", tags=["worksheets-v3"])


def _map_question(q: dict, index: int) -> Question:
    """Map a raw v3 question dict to the API Question model."""
    q_type = q.get("type", "short_answer")
    options = q.get("options")
    return Question(
        id=q.get("id", f"q{index + 1}"),
        type=q_type,
        text=q.get("text", ""),
        options=options,
        correct_answer=q.get("correct_answer"),
        explanation=q.get("explanation"),
        difficulty=q.get("difficulty"),
        hint=q.get("hint"),
        role=q.get("role"),
        images=q.get("images"),
        visual_type=q.get("visual_type"),
        visual_data=q.get("visual_data"),
        skill_tag=q.get("skill_tag"),
        format=q.get("format", _infer_render_format(q_type, options)),
        verified=q.get("verified", True),
    )


def _infer_render_format(q_type: str, options: list | None) -> str:
    """Map question type to the frontend's render format."""
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
async def generate_worksheet_v3_endpoint(
    request: Request, body: WorksheetGenerationRequest, user_id: UserId, db: DbClient, client: OpenAICompat
):
    """Generate a worksheet using the v3 slot-builder pipeline."""
    sentry_sdk.set_tag("topic", body.topic)
    sentry_sdk.set_tag("subject", body.subject)

    # ── Auth + Subscription enforcement ───────────────────────
    usage = await check_and_increment_usage(user_id, db)
    if not usage["allowed"]:
        raise HTTPException(status_code=402, detail=usage["message"])
    from app.services.telemetry import emit_event
    from app.services.v3 import generate_worksheet_v3

    try:
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
            ),
            timeout=90.0,
        )
    except asyncio.TimeoutError:
        emit_event(
            "worksheet_generation",
            route="/api/v3/worksheets/generate",
            version="v3",
            topic=body.topic,
            ok=False,
            error_type="TimeoutError",
        )
        logger.error("[v3] Generation timed out (90s) topic=%s", body.topic)
        raise HTTPException(status_code=504, detail="Worksheet generation timed out. Please try again.")
    except ValueError as exc:
        emit_event(
            "worksheet_generation",
            route="/api/v3/worksheets/generate",
            version="v3",
            topic=body.topic,
            ok=False,
            error_type="ValueError",
        )
        logger.error("[v3] Generation failed: %s", exc)
        raise HTTPException(status_code=502, detail="Worksheet generation failed. Please try again.")

    emit_event(
        "worksheet_generation",
        route="/api/v3/worksheets/generate",
        version="v3",
        topic=body.topic,
        skill_tag=data.get("skill_focus"),
        latency_ms=elapsed_ms,
        ok=True,
    )

    raw_questions = data.get("questions", [])
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
        skill_coverage=skill_coverage or None,
    )

    has_warnings = bool(warnings)
    qg = data.get("_quality_gate", {}) or {}
    qg_passed = bool(qg.get("passed", True))
    qg_severity = str(qg.get("severity", "ok"))
    if not qg_passed:
        verdict = "blocked"
    elif qg_severity == "warning" or has_warnings:
        verdict = "best_effort"
    else:
        verdict = "released"
    failed_rules: list[str] = []
    block_reasons: list[str] = []
    if not qg_passed:
        failed_rules = ["V3_QUALITY_GATE_BLOCK"]
        block_reasons = [f"[V3_QUALITY_GATE_BLOCK] {len(qg.get('issues', []))} quality-gate issue(s)"]
    elif verdict == "best_effort":
        failed_rules = ["V3_QUALITY_GATE_WARNING"]
    trust_summary = {
        "severity_max": "P0" if block_reasons else ("P1" if failed_rules else None),
        "failed_rules_count": len(failed_rules),
        "policy_version": "v1",
        "blocked_reason_codes": [],
    }
    quality_tier = "low" if verdict == "blocked" else ("medium" if verdict == "best_effort" else "high")

    return WorksheetGenerationResponse(
        worksheet=worksheet,
        generation_time_ms=elapsed_ms,
        warnings={"generation": warnings} if has_warnings else None,
        verdict=verdict,
        quality_stamps={"quality_gate": qg} if qg else None,
        quality_tier=quality_tier,
        quality_score=None,
        trust_summary=trust_summary,
    )
