"""Trust failure memory storage and fingerprinting."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.services.trust_policy import severity_for_rule


def build_failure_fingerprint(
    *,
    grade_level: str,
    subject: str,
    topic: str,
    rule_id: str,
    detail: str = "",
) -> str:
    seed = f"{grade_level}|{subject}|{topic}|{rule_id}|{detail[:120]}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]


def _hash_text(text: str) -> str:
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def log_release_failures(
    db,
    *,
    request_id: str,
    grade_level: str,
    subject: str,
    topic: str,
    user_id: str | None,
    failed_rules: list[str],
    block_reasons: list[str],
    degrade_reasons: list[str],
    prompt_text: str = "",
    profile_key: str = "",
    model_version: str = "",
    was_served: bool,
) -> None:
    """Persist release-gate failures to trust_failures table."""
    if not failed_rules:
        return

    reason_map: dict[str, str] = {}
    for msg in block_reasons + degrade_reasons:
        if msg.startswith("[") and "]" in msg:
            rid = msg[1 : msg.index("]")]
            reason_map[rid] = msg

    rows: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()
    prompt_hash = _hash_text(prompt_text)
    payload_blob = {
        "block_reasons": block_reasons,
        "degrade_reasons": degrade_reasons,
        "failed_rules": failed_rules,
    }

    for rid in failed_rules:
        detail = reason_map.get(rid, "")
        rows.append(
            {
                "created_at": now,
                "request_id": request_id,
                "user_id": user_id,
                "grade": grade_level,
                "subject": subject,
                "topic": topic,
                "rule_id": rid,
                "severity": severity_for_rule(rid).value,
                "question_id": None,
                "fingerprint": build_failure_fingerprint(
                    grade_level=grade_level,
                    subject=subject,
                    topic=topic,
                    rule_id=rid,
                    detail=detail,
                ),
                "payload_json": payload_blob,
                "prompt_hash": prompt_hash or None,
                "profile_key": profile_key or None,
                "model_version": model_version or None,
                "was_served": was_served,
            }
        )

    try:
        db.table("trust_failures").insert(rows).execute()
    except Exception:
        # Fail-open for observability sink.
        return


def summarize_trust_for_response(
    *,
    failed_rules: list[str],
    block_reasons: list[str],
    policy_version: str = "v1",
) -> dict[str, Any]:
    severities = [severity_for_rule(r).value for r in failed_rules]
    if "P0" in severities:
        max_sev = "P0"
    elif "P1" in severities:
        max_sev = "P1"
    elif "P2" in severities:
        max_sev = "P2"
    else:
        max_sev = None

    codes = []
    for r in block_reasons:
        if r.startswith("[") and "]" in r:
            codes.append(r[1 : r.index("]")])

    return {
        "severity_max": max_sev,
        "failed_rules_count": len(failed_rules),
        "policy_version": policy_version,
        "blocked_reason_codes": sorted(set(codes)),
    }


def serialize_payload_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
