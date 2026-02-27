"""
Error Pattern Detector — identifies systematic misconceptions from question_attempts.

Pure helpers are fully testable without DB. The ErrorPatternDetector class
queries Supabase but all analysis is delegated to pure functions.

Systematic threshold: 3+ incorrect with same misconception_id on same skill_tag
AND ≥50% of errors on that skill.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

SYSTEMATIC_MIN_OCCURRENCES = 3
SYSTEMATIC_MIN_ERROR_RATE = 0.50


@dataclass
class ErrorPattern:
    misconception_id: str
    misconception_display: str
    domain: str
    occurrences: int
    total_attempts: int
    error_rate: float
    is_systematic: bool
    affected_skill_tags: list[str] = field(default_factory=list)


@dataclass
class SkillDiagnostic:
    skill_tag: str
    total_attempts: int
    correct_count: int
    accuracy: float
    trend: str  # "improving" | "declining" | "stable"
    top_misconceptions: list[ErrorPattern] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pure helpers (testable without DB)
# ---------------------------------------------------------------------------


def classify_patterns(attempts: list[dict]) -> list[ErrorPattern]:
    """
    Group attempts by misconception_id, compute rates, flag systematic patterns.

    Args:
        attempts: List of question_attempt rows (dicts with at least
                  misconception_id, skill_tag, is_correct keys)

    Returns:
        List of ErrorPattern, sorted by occurrences descending.
    """
    from app.data.misconception_taxonomy import MISCONCEPTION_TAXONOMY

    # Group incorrect attempts by misconception_id
    misconception_counts: dict[str, dict] = {}
    total_incorrect = 0

    for att in attempts:
        if att.get("is_correct", False):
            continue
        total_incorrect += 1

        mid = att.get("misconception_id") or "UNKNOWN"
        if mid not in misconception_counts:
            misconception_counts[mid] = {
                "occurrences": 0,
                "skill_tags": set(),
            }
        misconception_counts[mid]["occurrences"] += 1
        skill = att.get("skill_tag", "")
        if skill:
            misconception_counts[mid]["skill_tags"].add(skill)

    total_attempts = len(attempts)
    patterns: list[ErrorPattern] = []

    for mid, info in misconception_counts.items():
        occ = info["occurrences"]
        taxonomy_entry = MISCONCEPTION_TAXONOMY.get(mid, MISCONCEPTION_TAXONOMY["UNKNOWN"])
        error_rate = occ / total_incorrect if total_incorrect > 0 else 0.0

        patterns.append(
            ErrorPattern(
                misconception_id=mid,
                misconception_display=taxonomy_entry["display"],
                domain=taxonomy_entry["domain"],
                occurrences=occ,
                total_attempts=total_attempts,
                error_rate=round(error_rate, 3),
                is_systematic=(occ >= SYSTEMATIC_MIN_OCCURRENCES and error_rate >= SYSTEMATIC_MIN_ERROR_RATE),
                affected_skill_tags=sorted(info["skill_tags"]),
            )
        )

    patterns.sort(key=lambda p: p.occurrences, reverse=True)
    return patterns


def compute_trend(attempts: list[dict], window: int = 5) -> str:
    """
    Compare recent vs previous accuracy to determine trend.

    Args:
        attempts: List of attempt dicts sorted by created_at ascending
        window: Number of recent attempts to compare

    Returns:
        "improving" | "declining" | "stable"
    """
    if len(attempts) < window * 2:
        return "stable"

    recent = attempts[-window:]
    previous = attempts[-window * 2 : -window]

    recent_acc = sum(1 for a in recent if a.get("is_correct", False)) / len(recent)
    prev_acc = sum(1 for a in previous if a.get("is_correct", False)) / len(previous)

    diff = recent_acc - prev_acc
    if diff > 0.15:
        return "improving"
    elif diff < -0.15:
        return "declining"
    return "stable"


# ---------------------------------------------------------------------------
# ErrorPatternDetector (DB-backed)
# ---------------------------------------------------------------------------


class ErrorPatternDetector:
    def __init__(self, supabase_client=None):
        self._sb = supabase_client

    def _get_sb(self):
        if self._sb:
            return self._sb
        from app.services.supabase_client import get_supabase_client

        return get_supabase_client()

    def detect_patterns(
        self,
        child_id: str,
        lookback_days: int = 30,
    ) -> list[ErrorPattern]:
        """
        Detect error patterns for a child over the lookback window.

        Returns empty list if diagnostic DB is disabled or on any error.
        """
        if os.getenv("ENABLE_DIAGNOSTIC_DB", "0") != "1":
            return []

        try:
            sb = self._get_sb()
            # Supabase doesn't support date arithmetic in filters easily,
            # so we compute the cutoff in Python
            from datetime import timedelta

            cutoff_dt = datetime.now(timezone.utc) - timedelta(days=lookback_days)
            cutoff_str = cutoff_dt.isoformat()

            res = (
                sb.table("question_attempts")
                .select("*")
                .eq("child_id", child_id)
                .gte("created_at", cutoff_str)
                .execute()
            )
            attempts = getattr(res, "data", None) or []
            return classify_patterns(attempts)

        except Exception as exc:
            logger.error("[error_pattern_detector] detect_patterns failed: %s", exc, exc_info=True)
            return []

    def get_skill_diagnostics(
        self,
        child_id: str,
        skill_tag: str,
    ) -> SkillDiagnostic:
        """
        Get diagnostic information for a specific skill.

        Returns a SkillDiagnostic with defaults if DB is disabled or on error.
        """
        default = SkillDiagnostic(
            skill_tag=skill_tag,
            total_attempts=0,
            correct_count=0,
            accuracy=0.0,
            trend="stable",
        )

        if os.getenv("ENABLE_DIAGNOSTIC_DB", "0") != "1":
            return default

        try:
            sb = self._get_sb()
            res = (
                sb.table("question_attempts")
                .select("*")
                .eq("child_id", child_id)
                .eq("skill_tag", skill_tag)
                .order("created_at")
                .execute()
            )
            attempts = getattr(res, "data", None) or []

            if not attempts:
                return default

            correct_count = sum(1 for a in attempts if a.get("is_correct", False))
            total = len(attempts)
            accuracy = round(correct_count / total, 3) if total > 0 else 0.0
            trend = compute_trend(attempts)

            # Get misconception patterns for this skill only
            patterns = classify_patterns(attempts)

            return SkillDiagnostic(
                skill_tag=skill_tag,
                total_attempts=total,
                correct_count=correct_count,
                accuracy=accuracy,
                trend=trend,
                top_misconceptions=patterns[:3],
            )

        except Exception as exc:
            logger.error("[error_pattern_detector] get_skill_diagnostics failed: %s", exc, exc_info=True)
            return default


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_DETECTOR: Optional[ErrorPatternDetector] = None


def get_error_pattern_detector() -> ErrorPatternDetector:
    global _DETECTOR
    if _DETECTOR is None:
        _DETECTOR = ErrorPatternDetector()
    return _DETECTOR
