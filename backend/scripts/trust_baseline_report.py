#!/usr/bin/env python3
"""Baseline trust metrics snapshot for current production path."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

from app.core.deps import get_supabase_client


def main() -> int:
    db = get_supabase_client()
    since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    res = db.table("trust_failures").select("grade,subject,topic,rule_id,was_served").gte("created_at", since).execute()
    rows = list(getattr(res, "data", []) or [])
    if not rows:
        print("No trust_failures rows found for last 7 days.")
        return 0

    served = sum(1 for r in rows if r.get("was_served"))
    blocked = len(rows) - served
    rule_counts = Counter(r.get("rule_id", "unknown") for r in rows)
    scope_counts = Counter(f"{r.get('grade')}|{r.get('subject')}|{r.get('topic')}" for r in rows)

    print("Trust baseline snapshot (last 7 days)")
    print(f"Total failures: {len(rows)}")
    print(f"Served despite failure: {served}")
    print(f"Blocked: {blocked}")
    print("Top 20 failing rules:")
    for rule, cnt in rule_counts.most_common(20):
        print(f"  {rule}: {cnt}")
    print("Top 20 failing scopes:")
    for scope, cnt in scope_counts.most_common(20):
        print(f"  {scope}: {cnt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

