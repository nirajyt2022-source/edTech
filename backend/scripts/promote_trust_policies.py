#!/usr/bin/env python3
"""Promote canary trust policies if they pass safety gates.

Safety gates:
- no new P0 failures for policy fingerprint scopes
- P1 reduction >= configured minimum
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.config import get_settings
from app.core.deps import get_supabase_client


def main() -> int:
    settings = get_settings()
    min_improvement = float(settings.trust_autopolicy_p1_improvement_min)
    db = get_supabase_client()

    canary = db.table("trust_policies").select("*").eq("status", "canary").execute()
    policies = list(getattr(canary, "data", []) or [])
    if not policies:
        print("No canary policies.")
        return 0

    since = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    promoted = 0

    for p in policies:
        fp = p.get("source_failure_fingerprint")
        if not fp:
            continue
        rows = (
            db.table("trust_failures")
            .select("severity,created_at")
            .eq("fingerprint", fp)
            .gte("created_at", since)
            .execute()
        )
        failures = list(getattr(rows, "data", []) or [])
        p0 = sum(1 for r in failures if r.get("severity") == "P0")
        p1 = sum(1 for r in failures if r.get("severity") == "P1")

        # Conservative baseline proxy: threshold value from repeat trigger.
        baseline_p1 = max(1, int(settings.trust_autopolicy_repeat_threshold))
        improvement = (baseline_p1 - p1) / baseline_p1

        if p0 == 0 and improvement >= min_improvement:
            db.table("trust_policies").update({"status": "active"}).eq("policy_id", p["policy_id"]).execute()
            promoted += 1
        elif p0 > 0:
            db.table("trust_policies").update({"status": "rolled_back"}).eq("policy_id", p["policy_id"]).execute()

    print(f"Promoted {promoted} canary policies.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

