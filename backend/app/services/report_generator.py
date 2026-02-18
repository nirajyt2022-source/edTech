"""ClassReportGenerator — deterministic class report builder.

Rules:
  - NO LLM calls.  All text is pure string templates.
  - Accepts an injected supabase_client so the service is fully offline-testable.
  - Uses _build_report_text / _clean_topic_name / _build_recommendation_reason
    from learning_graph.py (already offline-tested).
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional

from app.services.learning_graph import (
    LearningGraphService,
    _build_report_text,
    _build_recommendation_reason,
    _clean_topic_name,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Priority order for "practice next" recommendation
# ---------------------------------------------------------------------------

_MASTERY_PRIORITY: dict[str, int] = {
    "unknown":  0,
    "learning": 1,
    "improving": 2,
    "mastered": 3,
}


def _pick_best_topic(mastery_rows: list[dict]) -> Optional[dict]:
    """Return the highest-priority topic to practice next.

    Priority: unknown < learning < improving < mastered.
    Within a bucket, the topic that was practiced longest ago wins.
    """
    if not mastery_rows:
        return None

    def _key(row: dict):
        level = row.get("mastery_level", "unknown")
        priority = _MASTERY_PRIORITY.get(level, 0)
        last = row.get("last_practiced_at") or "0000-00-00"
        return (priority, last)

    return sorted(mastery_rows, key=_key)[0]


# ---------------------------------------------------------------------------
# ClassReportGenerator
# ---------------------------------------------------------------------------

class ClassReportGenerator:
    """Builds a shareable class report and persists it in class_reports."""

    def __init__(self, supabase_client=None):
        self._sb = supabase_client
        self._graph_svc = LearningGraphService(supabase_client)

    def _get_sb(self):
        if self._sb:
            return self._sb
        from app.services.supabase_client import get_supabase_client
        return get_supabase_client()

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def generate_class_report(self, class_id: str, teacher_id: str) -> dict:
        """Build a plain-text class report; store it; return token + data.

        Returns:
            {
                "token": str,
                "expires_at": str (ISO-8601),
                "report_data": { ... }   # also stored as JSONB
            }

        Raises:
            ValueError  – class not found or not owned by teacher
            RuntimeError – DB write failed
        """
        sb = self._get_sb()

        # 1. Verify class exists and belongs to teacher
        cls = self._fetch_class(sb, class_id, teacher_id)

        # 2. Find all children who have worksheets in this class
        child_ids = self._fetch_child_ids(sb, class_id)

        # 3. Get display names for each child
        child_name_map = self._fetch_child_names(sb, child_ids)

        # 4. Build per-child report sections (pure templates — no LLM)
        child_sections = self._build_child_sections(sb, child_ids, child_name_map)

        # 5. Assemble report payload
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=7)
        token = secrets.token_urlsafe(16)

        report_data: dict = {
            "class_id": class_id,
            "class_name": cls["name"],
            "grade": cls.get("grade", ""),
            "subject": cls.get("subject", ""),
            "teacher_id": teacher_id,
            "generated_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "total_students": len(child_ids),
            "children": child_sections,
        }

        # 6. Persist to class_reports
        self._store_report(sb, token, class_id, teacher_id, report_data, now, expires_at)

        return {
            "token": token,
            "expires_at": expires_at.isoformat(),
            "report_data": report_data,
        }

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    def _fetch_class(self, sb, class_id: str, teacher_id: str) -> dict:
        try:
            r = (
                sb.table("teacher_classes")
                .select("id, name, grade, subject")
                .eq("id", class_id)
                .eq("user_id", teacher_id)
                .maybe_single()
                .execute()
            )
            cls = getattr(r, "data", None)
        except Exception as exc:
            logger.error("[ClassReportGenerator._fetch_class] DB error: %s", exc)
            raise RuntimeError(f"Could not fetch class: {exc}")

        if not cls:
            raise ValueError(f"Class {class_id} not found or not owned by this teacher")
        return cls

    def _fetch_child_ids(self, sb, class_id: str) -> list[str]:
        try:
            r = (
                sb.table("worksheets")
                .select("child_id")
                .eq("class_id", class_id)
                .execute()
            )
            rows = getattr(r, "data", None) or []
        except Exception as exc:
            logger.error("[ClassReportGenerator._fetch_child_ids] DB error: %s", exc)
            raise RuntimeError(f"Could not fetch class worksheets: {exc}")

        return list({row["child_id"] for row in rows if row.get("child_id")})

    def _fetch_child_names(self, sb, child_ids: list[str]) -> dict[str, str]:
        if not child_ids:
            return {}
        try:
            r = (
                sb.table("children")
                .select("id, name")
                .in_("id", child_ids)
                .execute()
            )
            rows = getattr(r, "data", None) or []
            return {row["id"]: row["name"] for row in rows}
        except Exception as exc:
            logger.error("[ClassReportGenerator._fetch_child_names] DB error: %s", exc)
            return {}

    def _build_child_sections(
        self,
        sb,
        child_ids: list[str],
        child_name_map: dict[str, str],
    ) -> list[dict]:
        sections: list[dict] = []

        for cid in child_ids:
            name = child_name_map.get(cid, "Student")

            # Summary from child_learning_summary table (via service)
            summary = self._graph_svc.get_child_summary(cid)
            mastered: list[str] = summary.get("mastered_topics") or []
            improving: list[str] = summary.get("improving_topics") or []
            needs_attention: list[str] = summary.get("needs_attention") or []

            # Report text — pure string templates, guaranteed no underscores
            report_text = _build_report_text(name, mastered, improving)

            # Recommendation — pick best topic from topic_mastery
            recommendation_text = self._build_recommendation(sb, cid)

            sections.append(
                {
                    "child_id": cid,
                    "name": name,
                    "report_text": report_text,
                    "recommendation": recommendation_text,
                    "mastered_count": len(mastered),
                    "improving_count": len(improving),
                    "needs_attention_count": len(needs_attention),
                }
            )

        return sections

    def _build_recommendation(self, sb, child_id: str) -> str:
        """Fetch raw topic_mastery rows and build a plain-English recommendation."""
        try:
            r = (
                sb.table("topic_mastery")
                .select(
                    "topic_slug, subject, mastery_level, "
                    "streak, sessions_total, last_practiced_at"
                )
                .eq("child_id", child_id)
                .execute()
            )
            rows = getattr(r, "data", None) or []
        except Exception as exc:
            logger.warning(
                "[ClassReportGenerator._build_recommendation] DB error for child %s: %s",
                child_id, exc,
            )
            return ""

        best = _pick_best_topic(rows)
        if not best:
            return ""

        topic_name = _clean_topic_name(best.get("topic_slug", ""))
        reason = _build_recommendation_reason(best)
        return f"Practice next: {topic_name} — {reason}."

    def _store_report(
        self,
        sb,
        token: str,
        class_id: str,
        teacher_id: str,
        report_data: dict,
        generated_at: datetime,
        expires_at: datetime,
    ) -> None:
        payload = {
            "token": token,
            "class_id": class_id,
            "teacher_id": teacher_id,
            "report_data": report_data,
            "generated_at": generated_at.isoformat(),
            "expires_at": expires_at.isoformat(),
        }
        try:
            sb.table("class_reports").insert(payload).execute()
        except Exception as exc:
            logger.error("[ClassReportGenerator._store_report] DB insert failed: %s", exc)
            raise RuntimeError(f"Could not store report: {exc}")
