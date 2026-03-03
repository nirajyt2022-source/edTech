"""
Correction Corpus Logger (D-02)

Captures LLM answer corrections and unverifiable flags as a persistent
corpus. Best-effort: never blocks generation, never raises.

Feature-gated by ENABLE_CORRECTION_CORPUS_DB env var (default "0").
Always logs to Python logger as single-line JSON regardless of DB flag.
"""

from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)


def log_corrections(
    raw_questions: list[dict],
    *,
    user_id: str | None,
    topic: str,
    subject: str,
    grade: str,
) -> None:
    """Extract and log correction events from raw LLM questions."""
    try:
        rows: list[dict] = []
        for q in raw_questions:
            base = {
                "user_id": user_id,
                "topic": topic,
                "subject": subject,
                "grade": grade,
                "question_id": q.get("id", ""),
                "question_text": q.get("text", ""),
                "skill_tag": q.get("skill_tag"),
                "difficulty": q.get("difficulty"),
            }

            if q.get("_answer_mismatch"):
                rows.append(
                    {
                        **base,
                        "correction_type": "answer_mismatch",
                        "before_value": q.get("answer", q.get("correct_answer")),
                        "after_value": str(q.get("_answer_mismatch_debug", {}).get("computed", "")),
                    }
                )
            if q.get("_format_corrected"):
                rows.append(
                    {
                        **base,
                        "correction_type": "format_corrected",
                        "before_value": q.get("_original_answer"),
                        "after_value": q.get("correct_answer"),
                    }
                )

            if q.get("_math_unverified"):
                rows.append(
                    {
                        **base,
                        "correction_type": "math_unverified",
                        "before_value": q.get("correct_answer"),
                        "after_value": None,
                    }
                )

        if not rows:
            return

        # Always log as single-line JSON
        for row in rows:
            logger.info("[correction_corpus] %s", json.dumps(row, default=str))

        # Best-effort DB insert
        if os.getenv("ENABLE_CORRECTION_CORPUS_DB", "0") != "1":
            return

        from app.services.supabase_client import get_supabase_client

        sb = get_supabase_client()
        sb.table("correction_corpus").insert(rows).execute()

    except Exception as e:
        logger.error("[correction_corpus] %s", e, exc_info=True)
