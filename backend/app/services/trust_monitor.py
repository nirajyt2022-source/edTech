"""Trust monitoring utilities for rollout dashboards and health checks."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any


def _as_iso_utc(hours: int) -> str:
    since = datetime.now(timezone.utc) - timedelta(hours=max(1, int(hours)))
    return since.isoformat()


def get_trust_metrics(db, *, hours: int = 24) -> dict[str, Any]:
    """Aggregate trust-failure KPIs from storage for the requested window."""
    since = _as_iso_utc(hours)

    try:
        res = (
            db.table("trust_failures")
            .select("request_id,rule_id,severity,grade,subject,topic,fingerprint,was_served")
            .gte("created_at", since)
            .execute()
        )
        rows = list(getattr(res, "data", []) or [])
    except Exception:
        rows = []

    try:
        dr = db.table("trust_dual_run_results").select("*").gte("created_at", since).execute()
        dual_rows = list(getattr(dr, "data", []) or [])
    except Exception:
        dual_rows = []

    total_fail_rows = len(rows)
    req_ids = {str(r.get("request_id") or "") for r in rows if r.get("request_id")}
    total_failed_requests = len(req_ids)
    served_rows = [r for r in rows if bool(r.get("was_served"))]
    blocked_rows = [r for r in rows if not bool(r.get("was_served"))]
    served_requests = {str(r.get("request_id") or "") for r in served_rows if r.get("request_id")}
    blocked_requests = {str(r.get("request_id") or "") for r in blocked_rows if r.get("request_id")}

    served_p0 = sum(1 for r in served_rows if str(r.get("severity")) == "P0")
    served_p1 = sum(1 for r in served_rows if str(r.get("severity")) == "P1")

    rule_counts = Counter(str(r.get("rule_id") or "") for r in rows if r.get("rule_id"))
    fp_counts = Counter(str(r.get("fingerprint") or "") for r in rows if r.get("fingerprint"))
    scope_counts = Counter(
        f"{r.get('grade', '')}|{r.get('subject', '')}|{r.get('topic', '')}"
        for r in rows
        if r.get("grade") and r.get("subject") and r.get("topic")
    )

    dual_total = len(dual_rows)
    parity_match = sum(1 for r in dual_rows if bool(r.get("verdict_match")))
    parity_mismatch = dual_total - parity_match

    return {
        "window_hours": max(1, int(hours)),
        "since_utc": since,
        "failure_rows": total_fail_rows,
        "failed_requests": total_failed_requests,
        "served_failure_rows": len(served_rows),
        "blocked_failure_rows": len(blocked_rows),
        "served_failure_requests": len(served_requests),
        "blocked_failure_requests": len(blocked_requests),
        "served_p0_rows": served_p0,
        "served_p1_rows": served_p1,
        "served_p0_rate_on_failures": (served_p0 / len(served_rows)) if served_rows else 0.0,
        "served_p1_rate_on_failures": (served_p1 / len(served_rows)) if served_rows else 0.0,
        "blocked_rate_on_failed_requests": (
            len(blocked_requests) / total_failed_requests if total_failed_requests else 0.0
        ),
        "top_failed_rules": [{"rule_id": k, "count": v} for k, v in rule_counts.most_common(10)],
        "top_fingerprints": [{"fingerprint": k, "count": v} for k, v in fp_counts.most_common(10)],
        "top_scopes": [{"scope": k, "count": v} for k, v in scope_counts.most_common(10)],
        "dual_run": {
            "sample_count": dual_total,
            "verdict_match_count": parity_match,
            "verdict_mismatch_count": parity_mismatch,
            "verdict_match_rate": (parity_match / dual_total) if dual_total else 1.0,
        },
    }
