"""Shadow dual-run utilities for V2/V3 migration parity."""

from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def should_run_dual_shadow(request_key: str, percent: int) -> bool:
    pct = max(0, min(100, int(percent)))
    if pct <= 0:
        return False
    if pct >= 100:
        return True
    h = int(hashlib.sha256(request_key.encode("utf-8")).hexdigest(), 16) % 100
    return h < pct


def _verdict_from_v2_payload(data: dict[str, Any], warnings: list[str]) -> str:
    release_verdict = str(data.get("_release_verdict", "released"))
    if release_verdict == "blocked":
        return "blocked"
    if release_verdict == "best_effort" or bool(warnings):
        return "best_effort"
    return "released"


def _verdict_from_v3_payload(data: dict[str, Any], warnings: list[str]) -> str:
    qg = data.get("_quality_gate", {}) or {}
    qg_passed = bool(qg.get("passed", True))
    qg_severity = str(qg.get("severity", "ok"))
    if not qg_passed:
        return "blocked"
    if qg_severity == "warning" or bool(warnings):
        return "best_effort"
    return "released"


def log_dual_run_result(
    db,
    *,
    request_id: str,
    grade_level: str,
    subject: str,
    topic: str,
    primary_engine: str,
    shadow_engine: str,
    primary_verdict: str,
    shadow_verdict: str,
    primary_quality_score: float | None,
    shadow_quality_score: float | None,
    primary_latency_ms: int | None,
    shadow_latency_ms: int | None,
) -> None:
    row = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "request_id": request_id,
        "grade": grade_level,
        "subject": subject,
        "topic": topic,
        "primary_engine": primary_engine,
        "shadow_engine": shadow_engine,
        "primary_verdict": primary_verdict,
        "shadow_verdict": shadow_verdict,
        "verdict_match": primary_verdict == shadow_verdict,
        "primary_quality_score": primary_quality_score,
        "shadow_quality_score": shadow_quality_score,
        "primary_latency_ms": primary_latency_ms,
        "shadow_latency_ms": shadow_latency_ms,
    }
    try:
        db.table("trust_dual_run_results").insert(row).execute()
    except Exception as exc:
        logger.debug("dual_run_persist_failed", error=str(exc))


def run_shadow_generation(
    *,
    db,
    client,
    primary_engine: str,
    request_id: str,
    grade_level: str,
    subject: str,
    topic: str,
    board: str,
    difficulty: str,
    num_questions: int,
    language: str,
    problem_style: str,
    custom_instructions: str | None,
    child_id: str | None,
    primary_verdict: str,
    primary_quality_score: float | None,
    primary_latency_ms: int | None,
) -> None:
    """Run opposite engine in shadow mode and log parity outcome."""
    try:
        shadow_engine = "v3" if primary_engine == "v2" else "v2"
        t0 = time.perf_counter()
        if shadow_engine == "v3":
            from app.services.v3 import generate_worksheet_v3

            data, _elapsed_ms, warnings = generate_worksheet_v3(
                client=client,
                board=board,
                grade_level=grade_level,
                subject=subject,
                topic=topic,
                difficulty=difficulty,
                num_questions=num_questions,
                language=language,
                problem_style=problem_style,
                custom_instructions=custom_instructions,
                child_id=child_id,
            )
            shadow_verdict = _verdict_from_v3_payload(data, warnings)
            shadow_score = data.get("_quality_score")
        else:
            from app.services.worksheet_generator import generate_worksheet

            data, _elapsed_ms, warnings = generate_worksheet(
                client=client,
                board=board,
                grade_level=grade_level,
                subject=subject,
                topic=topic,
                difficulty=difficulty,
                num_questions=num_questions,
                language=language,
                problem_style=problem_style,
                custom_instructions=custom_instructions,
            )
            shadow_verdict = _verdict_from_v2_payload(data, warnings)
            shadow_score = data.get("_quality_score")

        shadow_latency = int((time.perf_counter() - t0) * 1000)
        log_dual_run_result(
            db,
            request_id=request_id,
            grade_level=grade_level,
            subject=subject,
            topic=topic,
            primary_engine=primary_engine,
            shadow_engine=shadow_engine,
            primary_verdict=primary_verdict,
            shadow_verdict=shadow_verdict,
            primary_quality_score=primary_quality_score,
            shadow_quality_score=shadow_score,
            primary_latency_ms=primary_latency_ms,
            shadow_latency_ms=shadow_latency,
        )
        logger.info(
            "dual_run_completed",
            request_id=request_id,
            topic=topic,
            primary_engine=primary_engine,
            shadow_engine=shadow_engine,
            primary_verdict=primary_verdict,
            shadow_verdict=shadow_verdict,
        )
    except Exception as exc:
        logger.warning("dual_run_failed", request_id=request_id, topic=topic, error=str(exc))
