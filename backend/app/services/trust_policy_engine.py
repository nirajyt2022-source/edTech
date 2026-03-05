"""Deterministic trust policy application for pre-generation request hardening."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from app.core.config import get_settings


@dataclass
class AppliedPolicy:
    policy_id: str
    action_type: str
    scope_type: str
    scope_key: str
    status: str


def _scope_rank(scope_type: str) -> int:
    # Higher precedence first
    if scope_type == "topic":
        return 3
    if scope_type == "grade_subject":
        return 2
    return 1  # global


def _in_canary(policy: dict[str, Any], request_key: str) -> bool:
    if policy.get("status") != "canary":
        return True
    pct = max(0, min(100, int(get_settings().trust_canary_percent)))
    if pct == 0:
        return False
    digest = hashlib.sha256(request_key.encode("utf-8")).hexdigest()
    bucket = int(digest[:8], 16) % 100
    return bucket < pct


def load_applicable_policies(
    db,
    *,
    grade_level: str,
    subject: str,
    topic: str,
    request_key: str,
) -> list[dict[str, Any]]:
    """Load active/canary policies and filter by scope and canary assignment."""
    try:
        res = db.table("trust_policies").select("*").in_("status", ["active", "canary"]).execute()
        rows = list(getattr(res, "data", []) or [])
    except Exception:
        return []

    grade_subject = f"{grade_level}|{subject}".lower()
    topic_key = f"{grade_level}|{subject}|{topic}".lower()

    applicable: list[dict[str, Any]] = []
    for p in rows:
        scope_type = (p.get("scope_type") or "").strip().lower()
        scope_key = (p.get("scope_key") or "").strip().lower()
        if scope_type == "topic" and scope_key != topic_key:
            continue
        if scope_type == "grade_subject" and scope_key != grade_subject:
            continue
        if scope_type == "global":
            pass
        if not _in_canary(p, request_key):
            continue
        applicable.append(p)

    applicable.sort(key=lambda p: _scope_rank((p.get("scope_type") or "").lower()), reverse=True)
    return applicable


def apply_policies_to_request(
    req: dict[str, Any], policies: list[dict[str, Any]]
) -> tuple[dict[str, Any], list[AppliedPolicy]]:
    """Apply deterministic policy actions to worksheet generation request payload."""
    out = dict(req)
    applied: list[AppliedPolicy] = []

    for p in policies:
        action_type = (p.get("action_type") or "").strip()
        payload = p.get("action_payload_json") or {}
        scope_type = (p.get("scope_type") or "").strip()
        scope_key = (p.get("scope_key") or "").strip()
        policy_id = str(p.get("policy_id") or p.get("id") or "")
        status = str(p.get("status") or "")

        if action_type == "topic_alias_override":
            new_topic = payload.get("topic")
            if new_topic:
                out["topic"] = new_topic
        elif action_type == "profile_override":
            # We represent profile overrides as canonical topic keys.
            new_topic = payload.get("profile_key")
            if new_topic:
                out["topic"] = new_topic
        elif action_type == "force_problem_style":
            style = payload.get("problem_style")
            if style in ("standard", "visual", "mixed"):
                out["problem_style"] = style
        elif action_type == "min_visual_ratio":
            ratio = payload.get("min_visual_ratio")
            if isinstance(ratio, (int, float)):
                out["min_visual_ratio"] = float(max(0.0, min(1.0, ratio)))
                out["visuals_only"] = out.get("visuals_only", False) or out["min_visual_ratio"] >= 0.9
        elif action_type == "forbid_question_types":
            types = payload.get("question_types", [])
            if types:
                note = f"Forbid question types: {', '.join(map(str, types))}."
                ci = (out.get("custom_instructions") or "").strip()
                out["custom_instructions"] = (ci + " " + note).strip()
        elif action_type == "stricter_word_limit":
            max_words = payload.get("max_words")
            if isinstance(max_words, int) and max_words > 0:
                note = f"HARD LIMIT: Keep each question under {max_words} words."
                ci = (out.get("custom_instructions") or "").strip()
                out["custom_instructions"] = (ci + " " + note).strip()
        elif action_type == "number_clamp":
            minimum = payload.get("min")
            maximum = payload.get("max")
            if isinstance(minimum, int) and isinstance(maximum, int) and minimum <= maximum:
                note = f"Use numbers only in range [{minimum}, {maximum}] when applicable."
                ci = (out.get("custom_instructions") or "").strip()
                out["custom_instructions"] = (ci + " " + note).strip()
        else:
            continue

        applied.append(
            AppliedPolicy(
                policy_id=policy_id,
                action_type=action_type,
                scope_type=scope_type,
                scope_key=scope_key,
                status=status,
            )
        )

    return out, applied
