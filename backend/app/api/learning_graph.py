from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Header, Query
from supabase import create_client

from app.core.config import get_settings
from app.services.learning_graph import (
    get_learning_graph_service,
    _clean_topic_name,
    _build_recommendation_reason,
    _build_report_text,
)

logger = logging.getLogger(__name__)

settings = get_settings()
supabase = create_client(settings.supabase_url, settings.supabase_service_key)

router = APIRouter(prefix="/api/children", tags=["learning-graph"])


# ---------------------------------------------------------------------------
# Auth helpers (same pattern as children.py)
# ---------------------------------------------------------------------------

def _get_user_id(authorization: str) -> str:
    """Extract user_id from Supabase JWT token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = authorization.replace("Bearer ", "")
    try:
        resp = supabase.auth.get_user(token)
        if not resp or not resp.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        return resp.user.id
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {exc}")


def _verify_ownership(child_id: str, user_id: str) -> dict:
    """Raise 403 if the user does not own this child. Returns the child row."""
    try:
        r = (
            supabase.table("children")
            .select("id, name, grade, user_id")
            .eq("id", child_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        child = getattr(r, "data", None)
    except Exception as exc:
        logger.error("[learning_graph._verify_ownership] DB error: %s", exc)
        raise HTTPException(status_code=500, detail="Database error verifying ownership")
    if not child:
        raise HTTPException(status_code=403, detail="Access denied or child not found")
    return child


# ---------------------------------------------------------------------------
# Endpoint 1: Full graph
# ---------------------------------------------------------------------------

@router.get("/{child_id}/graph")
def get_child_graph(
    child_id: str,
    authorization: str = Header(None),
):
    """Return the full learning graph for a child, grouped by subject."""
    user_id = _get_user_id(authorization)
    _verify_ownership(child_id, user_id)
    try:
        svc = get_learning_graph_service()
        graph = svc.get_child_graph(child_id)
    except Exception as exc:
        logger.error("[learning_graph.get_child_graph] Error for child %s: %s", child_id, exc)
        raise HTTPException(status_code=500, detail="Failed to load learning graph")
    return {"child_id": child_id, "graph": graph}


# ---------------------------------------------------------------------------
# Endpoint 2: Summary
# ---------------------------------------------------------------------------

@router.get("/{child_id}/graph/summary")
def get_child_graph_summary(
    child_id: str,
    authorization: str = Header(None),
):
    """Return the mastery summary (mastered/improving/needs_attention lists)."""
    user_id = _get_user_id(authorization)
    _verify_ownership(child_id, user_id)
    try:
        svc = get_learning_graph_service()
        summary = svc.get_child_summary(child_id)
    except Exception as exc:
        logger.error("[learning_graph.get_child_graph_summary] Error for child %s: %s", child_id, exc)
        raise HTTPException(status_code=500, detail="Failed to load summary")
    return summary


# ---------------------------------------------------------------------------
# Endpoint 3: History
# ---------------------------------------------------------------------------

@router.get("/{child_id}/graph/history")
def get_child_graph_history(
    child_id: str,
    limit: int = Query(default=20, ge=1, le=50),
    authorization: str = Header(None),
):
    """Return recent learning sessions for a child, newest first."""
    user_id = _get_user_id(authorization)
    _verify_ownership(child_id, user_id)
    try:
        r = (
            supabase.table("learning_sessions")
            .select(
                "topic_slug, subject, score_pct, mastery_before, mastery_after, "
                "created_at, questions_total, questions_correct"
            )
            .eq("child_id", child_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        rows = getattr(r, "data", None) or []
    except Exception as exc:
        logger.error(
            "[learning_graph.get_child_graph_history] DB error for child %s: %s", child_id, exc
        )
        raise HTTPException(status_code=500, detail="Failed to load history")
    return {"child_id": child_id, "sessions": rows, "count": len(rows)}


# ---------------------------------------------------------------------------
# Endpoint 4: Recommendation
# ---------------------------------------------------------------------------

# Priority order: unknown (0) and learning (1) before improving (2) before mastered (3)
_MASTERY_PRIORITY = {"unknown": 0, "learning": 1, "improving": 2, "mastered": 3}


def _pick_recommendation(rows: list[dict]) -> Optional[dict]:
    """Return the highest-priority topic to practice next from topic_mastery rows."""
    if not rows:
        return None

    def _sort_key(row: dict):
        level = row.get("mastery_level", "unknown")
        priority = _MASTERY_PRIORITY.get(level, 0)
        # None → treat as oldest (highest priority within bucket)
        last = row.get("last_practiced_at") or "0000-00-00"
        return (priority, last)

    return sorted(rows, key=_sort_key)[0]


@router.get("/{child_id}/graph/recommendation")
def get_child_next_recommendation(
    child_id: str,
    authorization: str = Header(None),
):
    """Return the single highest-priority topic to practice next."""
    user_id = _get_user_id(authorization)
    _verify_ownership(child_id, user_id)
    try:
        r = (
            supabase.table("topic_mastery")
            .select("topic_slug, subject, mastery_level, last_practiced_at")
            .eq("child_id", child_id)
            .execute()
        )
        rows = getattr(r, "data", None) or []
    except Exception as exc:
        logger.error(
            "[learning_graph.get_child_next_recommendation] DB error for child %s: %s",
            child_id, exc,
        )
        raise HTTPException(status_code=500, detail="Failed to load topic mastery")

    if not rows:
        return {"recommendation": None, "reason": "No practice history yet. Start any topic!"}

    best = _pick_recommendation(rows)
    level = best.get("mastery_level", "unknown")

    if level in ("unknown", "learning"):
        reason = "This topic needs more practice to build confidence."
    elif level == "improving":
        reason = "You're making progress — keep going to reach mastery!"
    else:
        reason = "You've mastered this topic — review it to keep it fresh."

    return {
        "recommendation": {
            "topic_slug": best.get("topic_slug"),
            "subject": best.get("subject"),
            "mastery_level": level,
            "last_practiced_at": best.get("last_practiced_at"),
            "reason": reason,
        }
    }


# ---------------------------------------------------------------------------
# Endpoint 5: Plain-English Report
# ---------------------------------------------------------------------------

@router.get("/{child_id}/graph/report")
def get_child_graph_report(
    child_id: str,
    authorization: str = Header(None),
):
    """Return a plain-English parent-friendly progress report.

    No LLM calls — all text is built from deterministic string templates.
    Response shape:
        { child_name, report_text,
          recommendation: { topic_slug, topic_name, reason, subject } | null }
    """
    user_id = _get_user_id(authorization)
    child = _verify_ownership(child_id, user_id)
    child_name: str = child.get("name", "Your child")

    # ── 1. Fetch mastery summary (mastered / improving lists) ────────────
    try:
        svc = get_learning_graph_service()
        summary = svc.get_child_summary(child_id)
    except Exception as exc:
        logger.error(
            "[learning_graph.get_child_graph_report] Summary error for child %s: %s",
            child_id, exc,
        )
        raise HTTPException(status_code=500, detail="Failed to load summary")

    mastered: list = summary.get("mastered_topics") or []
    improving: list = summary.get("improving_topics") or []

    # ── 2. Build report_text (pure templates — no slugs, no underscores) ─
    report_text = _build_report_text(child_name, mastered, improving)

    # ── 3. Build recommendation ───────────────────────────────────────────
    recommendation: Optional[dict] = None
    try:
        r = (
            supabase.table("topic_mastery")
            .select(
                "topic_slug, subject, mastery_level, "
                "streak, sessions_total, last_practiced_at"
            )
            .eq("child_id", child_id)
            .execute()
        )
        mastery_rows = getattr(r, "data", None) or []
        best = _pick_recommendation(mastery_rows)
        if best:
            slug: str = best.get("topic_slug") or ""
            recommendation = {
                "topic_slug": slug,
                "topic_name": _clean_topic_name(slug),
                "reason": _build_recommendation_reason(best),
                "subject": best.get("subject") or "",
            }
    except Exception as exc:
        logger.warning(
            "[learning_graph.get_child_graph_report] Recommendation lookup failed: %s", exc
        )

    return {
        "child_name": child_name,
        "report_text": report_text,
        "recommendation": recommendation,
    }
