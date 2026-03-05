#!/usr/bin/env python3
"""Propose canary trust policies from repeated recent trust failures.

Usage:
  cd backend
  python scripts/propose_trust_policies.py
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.core.config import get_settings
from app.core.deps import get_supabase_client


def main() -> int:
    settings = get_settings()
    threshold = max(1, int(settings.trust_autopolicy_repeat_threshold))
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    db = get_supabase_client()

    res = (
        db.table("trust_failures")
        .select("fingerprint,grade,subject,topic,rule_id")
        .gte("created_at", since)
        .in_("severity", ["P0", "P1"])
        .execute()
    )
    rows = list(getattr(res, "data", []) or [])
    if not rows:
        print("No recent P0/P1 failures.")
        return 0

    counts: dict[str, list[dict]] = {}
    for r in rows:
        fp = r.get("fingerprint")
        if not fp:
            continue
        counts.setdefault(fp, []).append(r)

    proposals = []
    for fp, group in counts.items():
        if len(group) < threshold:
            continue
        sample = group[0]
        grade = sample.get("grade", "")
        subject = sample.get("subject", "")
        topic = sample.get("topic", "")
        rule = sample.get("rule_id", "")

        # Conservative default candidate: clamp wording and enforce mixed visuals for young grades.
        action_type = "stricter_word_limit"
        payload = {"max_words": 20 if "Class 2" in grade or "Class 1" in grade else 30}
        if rule in ("R20_RENDER_INTEGRITY", "R11_TOPIC_DRIFT_GUARD"):
            action_type = "force_problem_style"
            payload = {"problem_style": "mixed"}

        scope_key = f"{grade}|{subject}|{topic}".lower()
        policy_id = f"auto-{fp[:10]}-{uuid.uuid4().hex[:6]}"
        proposals.append(
            {
                "policy_id": policy_id,
                "scope_type": "topic",
                "scope_key": scope_key,
                "action_type": action_type,
                "action_payload_json": payload,
                "status": "canary",
                "created_by": "auto",
                "source_failure_fingerprint": fp,
            }
        )

    if not proposals:
        print("No fingerprints crossed threshold.")
        return 0

    db.table("trust_policies").upsert(proposals, on_conflict="policy_id").execute()
    print(f"Proposed {len(proposals)} canary trust policies.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

