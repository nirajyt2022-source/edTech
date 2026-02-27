"""
Diagnostic Recorder — records per-question attempts with misconception classification.

Follows the audit.py best-effort pattern:
  - Gated by ENABLE_DIAGNOSTIC_DB env var
  - Never raises
  - Batch inserts to question_attempts table
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Optional

logger = logging.getLogger(__name__)


def _diagnostic_enabled() -> bool:
    return os.getenv("ENABLE_DIAGNOSTIC_DB", "0") == "1"


def record_question_attempts(
    child_id: str,
    worksheet_data: dict,
    grading_results: list[dict],
    questions: list[dict],
    worksheet_id: Optional[str] = None,
) -> None:
    """
    Record per-question attempt data with misconception classification.

    Best-effort: never raises. Gated by ENABLE_DIAGNOSTIC_DB.

    Args:
        child_id: UUID of the child
        worksheet_data: Full worksheet dict (for metadata)
        grading_results: List of grading result dicts from Gemini Vision
        questions: Original question list from the worksheet
        worksheet_id: Optional worksheet UUID
    """
    if not _diagnostic_enabled():
        logger.debug("[diagnostic_recorder] disabled — ENABLE_DIAGNOSTIC_DB is not '1'")
        return

    try:
        from app.data.misconception_taxonomy import classify_misconception
        from app.services.supabase_client import get_supabase_client

        sb = get_supabase_client()
        session_id = str(uuid.uuid4())
        rows = []

        for result in grading_results:
            q_num = result.get("question_number", 0)
            q_index = q_num - 1
            if q_index < 0 or q_index >= len(questions):
                continue

            question = questions[q_index]
            is_correct = result.get("is_correct", False)
            correct_answer = str(question.get("correct_answer", ""))
            student_answer = str(result.get("student_answer", ""))
            skill_tag = result.get("skill_tag", "") or question.get("skill_tag", "")
            question_text = question.get("text", question.get("question_text", ""))

            # Classify misconception for incorrect answers
            misconception_id = None
            if not is_correct and student_answer and student_answer != "BLANK":
                misconception_id = classify_misconception(
                    skill_tag=skill_tag,
                    correct_answer=correct_answer,
                    student_answer=student_answer,
                    question_text=question_text,
                )

            rows.append(
                {
                    "child_id": child_id,
                    "worksheet_id": worksheet_id,
                    "session_id": session_id,
                    "question_index": q_num,
                    "skill_tag": skill_tag or "unknown",
                    "question_format": question.get("format", question.get("type", "")),
                    "difficulty": question.get("difficulty", ""),
                    "role": question.get("role", ""),
                    "correct_answer": correct_answer,
                    "student_answer": student_answer if student_answer else None,
                    "is_correct": is_correct,
                    "confidence": result.get("confidence"),
                    "needs_review": result.get("needs_review", False),
                    "misconception_id": misconception_id,
                }
            )

        if rows:
            sb.table("question_attempts").insert(rows).execute()
            logger.info(
                "[diagnostic_recorder] Recorded %d question attempts for child=%s",
                len(rows),
                child_id,
            )

    except Exception as exc:
        logger.error("[diagnostic_recorder] Failed to record attempts: %s", exc, exc_info=True)
