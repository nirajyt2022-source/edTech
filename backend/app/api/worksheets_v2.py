"""
Worksheets v2 API — simplified prompt-to-Gemini pipeline.

Mounts at /api/v2/worksheets. The old /api/worksheets (v1) is untouched.
"""
from __future__ import annotations

import logging
import time

from fastapi import APIRouter, HTTPException

from app.api.worksheets import (
    Question,
    Worksheet,
    WorksheetGenerationRequest,
    WorksheetGenerationResponse,
)
from app.core.config import get_settings
from app.core.deps import get_llm_client
from app.services.worksheet_generator import generate_worksheet

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v2/worksheets", tags=["worksheets-v2"])

settings = get_settings()
client = get_llm_client(settings)


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
        format=_infer_render_format(q.get("type", "short_answer"), q.get("options")),
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
async def generate_worksheet_v2(request: WorksheetGenerationRequest):
    """Generate a worksheet using the simplified v2 pipeline."""
    start = time.perf_counter()

    try:
        data, elapsed_ms, warnings = generate_worksheet(
            client=client,
            board=request.board,
            grade_level=request.grade_level,
            subject=request.subject,
            topic=request.topic,
            difficulty=request.difficulty,
            num_questions=request.num_questions,
            language=request.language,
            problem_style=request.problem_style,
            custom_instructions=request.custom_instructions,
        )
    except ValueError as exc:
        logger.error("[v2] Generation failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))

    raw_questions = data.get("questions", [])
    questions = [_map_question(q, i) for i, q in enumerate(raw_questions)]

    worksheet = Worksheet(
        title=data.get("title", f"Worksheet: {request.topic}"),
        grade=request.grade_level,
        subject=request.subject,
        topic=request.topic,
        difficulty=request.difficulty,
        language=request.language,
        questions=questions,
        skill_focus=data.get("skill_focus", ""),
        common_mistake=data.get("common_mistake", ""),
        parent_tip=data.get("parent_tip", ""),
        learning_objectives=data.get("learning_objectives", []),
    )

    has_warnings = bool(warnings)
    return WorksheetGenerationResponse(
        worksheet=worksheet,
        generation_time_ms=elapsed_ms,
        warnings={"generation": warnings} if has_warnings else None,
        verdict="best_effort" if has_warnings else "ok",
    )
