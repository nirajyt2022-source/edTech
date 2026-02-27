"""
Insight Generator — deterministic parent-facing insights from diagnostic data.

All text from templates. No LLM. Pattern: learning_graph._build_report_text().
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class InsightItem:
    skill_tag: str
    display: str
    detail: str


@dataclass
class ChildInsight:
    child_name: str
    strengths: list[InsightItem] = field(default_factory=list)
    struggles: list[InsightItem] = field(default_factory=list)
    improving: list[InsightItem] = field(default_factory=list)
    weekly_summary: str = ""
    actionable_tip: str = ""
    next_worksheet_suggestion: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Template helpers
# ---------------------------------------------------------------------------

_STRENGTH_TEMPLATES = [
    "{name} is doing great with {skill}!",
    "{name} has shown strong understanding of {skill}.",
    "{skill} is a strength area — keep it up!",
]

_STRUGGLE_TEMPLATES = [
    "{name} might need more practice with {skill}.",
    "{skill} seems challenging — try a focused worksheet.",
    "Consider reviewing {skill} with {name} together.",
]

_IMPROVING_TEMPLATES = [
    "{name} is getting better at {skill} — practice is paying off!",
    "Great progress on {skill} — keep the momentum going.",
    "{skill} accuracy is improving with each session.",
]

_TIP_MAP = {
    "addition": "Try using physical objects like buttons or coins to practice addition at home.",
    "subtraction": "Use a number line drawn on paper to help visualize subtraction.",
    "multiplication": "Practice multiplication facts with a fun song or rhyme at bedtime.",
    "division": "Share snacks equally among family members to make division real.",
    "number_sense": "Play 'guess my number' games to build number sense.",
    "place_value": "Use bundled sticks (ones and tens) to explore place value.",
    "word_problems": "Read word problems aloud together and ask 'what are we finding?'",
    "time": "Let your child read the clock at regular intervals throughout the day.",
    "money": "Give your child small amounts to handle at the local shop.",
    "general": "Regular short practice sessions work better than long cramming.",
}


def _humanize_skill(skill_tag: str) -> str:
    """Convert skill_tag to a human-readable name."""
    return skill_tag.replace("_", " ").replace("col ", "column ").replace("wp ", "word problem ").title()


# ---------------------------------------------------------------------------
# Core insight generation
# ---------------------------------------------------------------------------


def generate_child_insights(
    child_id: str,
    child_name: str,
) -> ChildInsight:
    """
    Generate deterministic insights for a child based on their diagnostic data.

    Returns an empty-ish ChildInsight on any failure (fail-open).
    """
    default = ChildInsight(
        child_name=child_name,
        weekly_summary=f"No recent data for {child_name} yet. Generate a worksheet to get started!",
        actionable_tip=_TIP_MAP["general"],
    )

    if os.getenv("ENABLE_DIAGNOSTIC_DB", "0") != "1":
        return default

    try:
        from app.services.error_pattern_detector import get_error_pattern_detector
        from app.services.supabase_client import get_supabase_client

        sb = get_supabase_client()
        detector = get_error_pattern_detector()

        # Get recent attempts (last 30 days)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        res = (
            sb.table("question_attempts")
            .select("skill_tag, is_correct, misconception_id, created_at")
            .eq("child_id", child_id)
            .gte("created_at", cutoff)
            .order("created_at")
            .execute()
        )
        attempts = getattr(res, "data", None) or []

        if not attempts:
            return default

        # Aggregate by skill_tag
        skill_stats: dict[str, dict] = {}
        for att in attempts:
            st = att.get("skill_tag", "unknown")
            if st not in skill_stats:
                skill_stats[st] = {"total": 0, "correct": 0, "recent": []}
            skill_stats[st]["total"] += 1
            if att.get("is_correct", False):
                skill_stats[st]["correct"] += 1
            skill_stats[st]["recent"].append(att)

        # Classify: strength (≥80%), struggle (≤40%), improving (trend up)
        strengths: list[InsightItem] = []
        struggles: list[InsightItem] = []
        improving_items: list[InsightItem] = []

        from app.services.error_pattern_detector import compute_trend

        for st, stats in skill_stats.items():
            if stats["total"] < 2:
                continue

            acc = stats["correct"] / stats["total"]
            trend = compute_trend(stats["recent"])
            display = _humanize_skill(st)

            if acc >= 0.80:
                strengths.append(
                    InsightItem(
                        skill_tag=st,
                        display=display,
                        detail=f"{round(acc * 100)}% accuracy over {stats['total']} questions",
                    )
                )
            elif acc <= 0.40:
                struggles.append(
                    InsightItem(
                        skill_tag=st,
                        display=display,
                        detail=f"{round(acc * 100)}% accuracy — needs more practice",
                    )
                )

            if trend == "improving":
                improving_items.append(
                    InsightItem(
                        skill_tag=st,
                        display=display,
                        detail="Accuracy is trending upward",
                    )
                )

        # Sort by relevance
        strengths.sort(key=lambda x: x.detail, reverse=True)
        struggles.sort(key=lambda x: x.detail)

        # Weekly summary
        total_attempts = len(attempts)
        total_correct = sum(1 for a in attempts if a.get("is_correct", False))
        overall_acc = round(total_correct / total_attempts * 100) if total_attempts > 0 else 0
        weekly_summary = (
            f"{child_name} attempted {total_attempts} questions in the last 30 days "
            f"with {overall_acc}% overall accuracy."
        )
        if strengths:
            weekly_summary += f" Strongest in {strengths[0].display}."
        if struggles:
            weekly_summary += f" Needs more work on {struggles[0].display}."

        # Actionable tip based on first struggle domain
        tip_domain = "general"
        if struggles:
            patterns = detector.detect_patterns(child_id, lookback_days=30)
            for p in patterns:
                if p.is_systematic:
                    tip_domain = p.domain
                    break
        actionable_tip = _TIP_MAP.get(tip_domain, _TIP_MAP["general"])

        # Next worksheet suggestion
        suggestion: dict = {}
        if struggles:
            suggestion = {
                "focus_skill": struggles[0].skill_tag,
                "difficulty": "easy",
                "rationale": f"Target {struggles[0].display} — currently at low accuracy",
            }
        elif improving_items:
            suggestion = {
                "focus_skill": improving_items[0].skill_tag,
                "difficulty": "medium",
                "rationale": f"Build on progress in {improving_items[0].display}",
            }

        return ChildInsight(
            child_name=child_name,
            strengths=strengths[:5],
            struggles=struggles[:5],
            improving=improving_items[:5],
            weekly_summary=weekly_summary,
            actionable_tip=actionable_tip,
            next_worksheet_suggestion=suggestion,
        )

    except Exception as exc:
        logger.error("[insight_generator] generate_child_insights failed: %s", exc, exc_info=True)
        return default


# ---------------------------------------------------------------------------
# Weekly digest
# ---------------------------------------------------------------------------


def generate_weekly_digest(
    child_id: str,
    child_name: str,
) -> dict:
    """
    7-day lookback: sessions, accuracy trend, new mastered, persistent struggles.

    Returns a dict suitable for API response or email template.
    """
    default_digest = {
        "child_name": child_name,
        "period": "last 7 days",
        "total_sessions": 0,
        "total_questions": 0,
        "accuracy_trend": "stable",
        "newly_mastered": [],
        "persistent_struggles": [],
        "summary": f"No activity in the last 7 days for {child_name}.",
    }

    if os.getenv("ENABLE_DIAGNOSTIC_DB", "0") != "1":
        return default_digest

    try:
        from app.services.error_pattern_detector import compute_trend
        from app.services.supabase_client import get_supabase_client

        sb = get_supabase_client()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

        res = (
            sb.table("question_attempts")
            .select("skill_tag, is_correct, misconception_id, created_at, session_id")
            .eq("child_id", child_id)
            .gte("created_at", cutoff)
            .order("created_at")
            .execute()
        )
        attempts = getattr(res, "data", None) or []

        if not attempts:
            return default_digest

        # Session count (unique session_ids)
        session_ids = set(a.get("session_id") for a in attempts if a.get("session_id"))
        total_sessions = len(session_ids) or 1
        total_questions = len(attempts)
        trend = compute_trend(attempts, window=min(5, total_questions // 2 or 1))

        # Skill accuracy
        skill_stats: dict[str, dict] = {}
        for att in attempts:
            st = att.get("skill_tag", "unknown")
            if st not in skill_stats:
                skill_stats[st] = {"total": 0, "correct": 0}
            skill_stats[st]["total"] += 1
            if att.get("is_correct", False):
                skill_stats[st]["correct"] += 1

        newly_mastered = [
            _humanize_skill(st) for st, s in skill_stats.items() if s["total"] >= 5 and s["correct"] / s["total"] >= 0.9
        ]
        persistent_struggles = [
            _humanize_skill(st) for st, s in skill_stats.items() if s["total"] >= 3 and s["correct"] / s["total"] <= 0.3
        ]

        overall_acc = round(sum(1 for a in attempts if a.get("is_correct", False)) / total_questions * 100)

        summary_parts = [
            f"{child_name} completed {total_sessions} session(s) with {total_questions} questions this week.",
            f"Overall accuracy: {overall_acc}%.",
        ]
        if newly_mastered:
            summary_parts.append(f"Newly mastered: {', '.join(newly_mastered)}.")
        if persistent_struggles:
            summary_parts.append(f"Still needs work on: {', '.join(persistent_struggles)}.")

        return {
            "child_name": child_name,
            "period": "last 7 days",
            "total_sessions": total_sessions,
            "total_questions": total_questions,
            "accuracy_trend": trend,
            "newly_mastered": newly_mastered,
            "persistent_struggles": persistent_struggles,
            "overall_accuracy": overall_acc,
            "summary": " ".join(summary_parts),
        }

    except Exception as exc:
        logger.error("[insight_generator] generate_weekly_digest failed: %s", exc, exc_info=True)
        return default_digest
