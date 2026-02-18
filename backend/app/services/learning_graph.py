from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MASTERY_ORDER = ["unknown", "learning", "improving", "mastered"]

# How many idle days before a mastery level decays
_DECAY_DAYS: dict[str, int] = {
    "mastered": 14,   # mastered → improving after 14 days without practice
    "improving": 21,  # improving → learning after 21 days without practice
}


# ---------------------------------------------------------------------------
# Pure helper functions (no DB — fully testable without mocks)
# ---------------------------------------------------------------------------

def _apply_decay(level: str, last_practiced_at: Optional[datetime]) -> str:
    """Regress mastery level if the topic hasn't been practised recently."""
    if level not in _DECAY_DAYS:
        return level
    if last_practiced_at is None:
        return level
    days_idle = (datetime.now(timezone.utc) - last_practiced_at).days
    if days_idle >= _DECAY_DAYS[level]:
        idx = MASTERY_ORDER.index(level)
        return MASTERY_ORDER[max(0, idx - 1)]
    return level


def _compute_mastery_transition(
    current_level: str,
    current_streak: int,
    score_pct: int,
    last_practiced_at: Optional[datetime] = None,
) -> tuple[str, int]:
    """
    Pure function — no DB calls.
    Applies spaced-repetition decay, then the streak-based progression rules,
    then the regression override for failing scores.
    Returns (new_level, new_streak).
    """
    # 1. Apply spaced-repetition decay before processing the new result
    level = _apply_decay(current_level, last_practiced_at)

    # If decay dropped the level, the student has been away too long —
    # their old streak no longer reflects current ability, so reset it.
    effective_streak = 0 if level != current_level else current_streak

    # 2. Update streak
    if score_pct >= 70:
        streak = effective_streak + 1
    else:
        streak = 0

    # 3. Streak-based progression (only fires when score passed)
    if score_pct >= 70:
        if level == "unknown" and streak >= 1:
            level = "learning"
        elif level == "learning" and streak >= 3:
            level = "improving"
        elif level == "improving" and streak >= 5:
            level = "mastered"


    # 4. Hard regression for failing scores (overrides step 3)
    if score_pct < 50:
        idx = MASTERY_ORDER.index(level)
        level = MASTERY_ORDER[max(0, idx - 1)]
        streak = 0

    return level, streak


def _find_weakest_format(format_results: dict) -> Optional[str]:
    """Return the format key with the lowest correct/total ratio."""
    worst: Optional[str] = None
    worst_ratio = 2.0  # sentinel above 1.0 — any real ratio will beat it
    for fmt, counts in format_results.items():
        total = counts.get("total", 0)
        if total == 0:
            continue
        ratio = counts.get("correct", 0) / total
        if ratio < worst_ratio:
            worst_ratio = ratio
            worst = fmt
    return worst


def _build_format_mix(level: Optional[str], format_weakness: Optional[str] = None) -> dict:
    """Return format_mix percentages for a given mastery level."""
    if level in ("unknown", None):
        return {"mcq": 50, "fill_blank": 30, "word_problem": 20}

    if level == "learning":
        base: dict[str, int] = {"mcq": 33, "fill_blank": 33, "word_problem": 34}
        if format_weakness and format_weakness in base:
            # Boost the weak format by 20 percentage points
            base[format_weakness] += 20
            others = [k for k in base if k != format_weakness]
            reduction = 20 // len(others)
            for k in others:
                base[k] = max(0, base[k] - reduction)
            # Re-normalise to 100
            total = sum(base.values())
            if total:
                base = {k: round(v * 100 / total) for k, v in base.items()}
        return base

    if level == "improving":
        return {"mcq": 30, "fill_blank": 30, "word_problem": 40}

    if level == "mastered":
        return {"mcq": 20, "fill_blank": 30, "word_problem": 50}

    # Fallback
    return {"mcq": 40, "fill_blank": 30, "word_problem": 30}


def _parse_ts(ts_str: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp string to a timezone-aware datetime."""
    if not ts_str:
        return None
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, AttributeError) as exc:
        logger.warning("[learning_graph._parse_ts] Could not parse timestamp %r: %s", ts_str, exc)
        return None


# ---------------------------------------------------------------------------
# Report helpers (pure — no DB, no LLM, fully testable offline)
# ---------------------------------------------------------------------------

# Strips " (Class 1)" / " (Class 2-EVS)" suffixes from canonical topic slugs.
_SLUG_CLEANUP_RE = re.compile(r"\s*\(Class \d+(?:-[A-Z]+)?\)\s*$", re.IGNORECASE)


def _clean_topic_name(slug: str) -> str:
    """Return a human-readable display name from a topic slug.

    Examples:
      "Numbers 1 to 50 (Class 1)"  → "Numbers 1 to 50"
      "Plants (Class 2-EVS)"       → "Plants"
      "Addition (carries)"         → "Addition (carries)"  (unchanged)
    """
    return _SLUG_CLEANUP_RE.sub("", slug).strip()


def _build_recommendation_reason(row: dict) -> str:
    """Return a one-sentence plain-English reason to practise *row*'s topic.

    Uses only mastery_level, streak, sessions_total, last_practiced_at.
    No LLM call — all logic is pure string templates.
    """
    level = row.get("mastery_level") or "unknown"
    streak = int(row.get("streak") or 0)
    sessions_total = int(row.get("sessions_total") or 0)
    last_str: Optional[str] = row.get("last_practiced_at")

    days_idle: Optional[int] = None
    if last_str:
        try:
            last_dt = datetime.fromisoformat(last_str.replace("Z", "+00:00"))
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            days_idle = (datetime.now(timezone.utc) - last_dt).days
        except Exception:
            days_idle = None

    if level in ("unknown", None) or sessions_total == 0:
        return "never been practiced yet — a great place to start"

    if level == "learning":
        if days_idle is not None and days_idle >= 5:
            return f"not practiced in {days_idle} days — good time to revisit"
        return "still building confidence — a little more practice will help a lot"

    if level == "improving":
        if streak >= 3:
            return "close to mastering it — one more good session should do it"
        if days_idle is not None and days_idle >= 3:
            return f"making great progress but not practiced in {days_idle} days"
        return "making good progress — keep going to reach mastery"

    if level == "mastered":
        if days_idle is not None and days_idle >= 7:
            return f"already mastered — not reviewed in {days_idle} days, worth a quick look"
        return "already mastered — a quick review will keep it fresh"

    return "a good topic to practice next"


def _build_report_text(child_name: str, mastered: list, improving: list) -> str:
    """Build 1–2 plain-English sentences summarising a child's learning state.

    Uses only human-readable topic names (run slugs through _clean_topic_name first).
    No underscores or raw slugs will appear in the output.
    """
    sentences: list[str] = []

    # Sentence 1 — strength or getting started
    if mastered:
        topic_name = _clean_topic_name(mastered[0])
        sentences.append(f"{child_name} has mastered {topic_name}.")
    else:
        sentences.append(f"{child_name} is just getting started on their learning journey.")

    # Sentence 2 — working on (optional)
    if improving:
        topic_name = _clean_topic_name(improving[0])
        sentences.append(f"Currently working on {topic_name}.")

    return " ".join(sentences)


# ---------------------------------------------------------------------------
# LearningGraphService
# ---------------------------------------------------------------------------

class LearningGraphService:
    def __init__(self, supabase_client=None):
        self._sb = supabase_client

    def _get_sb(self):
        if self._sb:
            return self._sb
        from app.services.supabase_client import get_supabase_client
        return get_supabase_client()

    # -----------------------------------------------------------------------
    # Method 1: record_session
    # -----------------------------------------------------------------------

    def record_session(
        self,
        child_id: str,
        topic_slug: str,
        subject: str,
        grade: int,
        bloom_level: str,
        format_results: dict,
        error_tags: list,
        score_pct: int,
        questions_total: int,
        questions_correct: int,
        worksheet_id: Optional[str] = None,
    ) -> dict:
        sb = self._get_sb()

        # --- Read current mastery state ---
        current_row = self._get_topic_mastery_row(sb, child_id, topic_slug)
        if current_row:
            mastery_before = current_row.get("mastery_level", "unknown")
            old_streak = int(current_row.get("streak", 0))
            last_practiced_at = _parse_ts(current_row.get("last_practiced_at"))
            sessions_total = int(current_row.get("sessions_total", 0))
            sessions_correct = int(current_row.get("sessions_correct", 0))
        else:
            mastery_before = "unknown"
            old_streak = 0
            last_practiced_at = None
            sessions_total = 0
            sessions_correct = 0

        # --- Compute transition (pure, no DB) ---
        mastery_after, new_streak = _compute_mastery_transition(
            mastery_before, old_streak, score_pct, last_practiced_at
        )

        format_weakness = _find_weakest_format(format_results)
        now_iso = datetime.now(timezone.utc).isoformat()

        # --- Write learning_sessions row ---
        session_payload = {
            "child_id": child_id,
            "worksheet_id": worksheet_id,
            "topic_slug": topic_slug,
            "subject": subject,
            "grade": grade,
            "bloom_level": bloom_level,
            "score_pct": score_pct,
            "questions_total": questions_total,
            "questions_correct": questions_correct,
            "format_results": format_results,
            "error_tags": error_tags,
            "mastery_before": mastery_before,
            "mastery_after": mastery_after,
        }
        try:
            sb.table("learning_sessions").insert(session_payload).execute()
        except Exception as exc:
            logger.error("[learning_graph.record_session] Failed to insert learning_sessions row: %s", exc)

        # --- Upsert topic_mastery row ---
        mastery_payload = {
            "child_id": child_id,
            "topic_slug": topic_slug,
            "subject": subject,
            "grade": grade,
            "mastery_level": mastery_after,
            "streak": new_streak,
            "sessions_total": sessions_total + 1,
            "sessions_correct": sessions_correct + (1 if score_pct >= 70 else 0),
            "last_practiced_at": now_iso,
            "last_error_type": error_tags[0] if error_tags else None,
            "format_weakness": format_weakness,
            "updated_at": now_iso,
        }
        try:
            sb.table("topic_mastery").upsert(mastery_payload, on_conflict="child_id,topic_slug").execute()
        except Exception as exc:
            logger.error("[learning_graph.record_session] Failed to upsert topic_mastery row: %s", exc)

        # --- Update child summary ---
        try:
            self._update_child_summary(child_id)
        except Exception as exc:
            logger.error("[learning_graph.record_session] Failed to update child_learning_summary: %s", exc)

        return {
            "mastery_before": mastery_before,
            "mastery_after": mastery_after,
            "mastery_changed": mastery_before != mastery_after,
            "new_streak": new_streak,
        }

    # -----------------------------------------------------------------------
    # Method 2: get_child_graph
    # -----------------------------------------------------------------------

    def get_child_graph(self, child_id: str) -> dict:
        sb = self._get_sb()
        try:
            r = sb.table("topic_mastery").select("*").eq("child_id", child_id).execute()
            rows = getattr(r, "data", None) or []
        except Exception as exc:
            logger.error("[learning_graph.get_child_graph] DB error for child %s: %s", child_id, exc)
            return {}

        graph: dict = {}
        for row in rows:
            subj = row.get("subject", "unknown")
            slug = row.get("topic_slug", "")
            graph.setdefault(subj, {})[slug] = {
                "mastery_level": row.get("mastery_level", "unknown"),
                "streak": row.get("streak", 0),
                "last_practiced_at": row.get("last_practiced_at"),
            }
        return graph

    # -----------------------------------------------------------------------
    # Method 3: get_child_summary
    # -----------------------------------------------------------------------

    def get_child_summary(self, child_id: str) -> dict:
        sb = self._get_sb()
        try:
            r = (
                sb.table("child_learning_summary")
                .select("*")
                .eq("child_id", child_id)
                .maybe_single()
                .execute()
            )
            data = getattr(r, "data", None)
        except Exception as exc:
            logger.error("[learning_graph.get_child_summary] DB error for child %s: %s", child_id, exc)
            data = None

        if not data:
            return {
                "child_id": child_id,
                "mastered_topics": [],
                "improving_topics": [],
                "needs_attention": [],
                "strongest_subject": None,
                "weakest_subject": None,
                "total_sessions": 0,
                "total_questions": 0,
                "overall_accuracy": 0,
                "learning_velocity": "normal",
                "last_updated_at": None,
            }
        return data

    # -----------------------------------------------------------------------
    # Method 4: get_adaptive_difficulty
    # -----------------------------------------------------------------------

    def get_adaptive_difficulty(self, child_id: str, topic_slug: str) -> dict:
        sb = self._get_sb()
        try:
            row = self._get_topic_mastery_row(sb, child_id, topic_slug)
        except Exception as exc:
            logger.error(
                "[learning_graph.get_adaptive_difficulty] DB error for child %s / topic %s: %s",
                child_id, topic_slug, exc,
            )
            row = None

        if not row:
            return {
                "bloom_level": "recall",
                "scaffolding": True,
                "challenge_mode": False,
                "format_mix": _build_format_mix("unknown"),
            }

        level = row.get("mastery_level", "unknown")
        format_weakness = row.get("format_weakness")

        _level_config: dict[str, dict] = {
            "unknown":   {"bloom_level": "recall",       "scaffolding": True,  "challenge_mode": False},
            "learning":  {"bloom_level": "recall",       "scaffolding": True,  "challenge_mode": False},
            "improving": {"bloom_level": "application",  "scaffolding": False, "challenge_mode": False},
            "mastered":  {"bloom_level": "reasoning",    "scaffolding": False, "challenge_mode": True},
        }
        config = dict(_level_config.get(level, _level_config["unknown"]))
        config["format_mix"] = _build_format_mix(level, format_weakness)
        return config

    # -----------------------------------------------------------------------
    # Method 5 (private): _update_child_summary
    # -----------------------------------------------------------------------

    def _update_child_summary(self, child_id: str) -> None:
        sb = self._get_sb()

        # Read all mastery rows for this child
        r = sb.table("topic_mastery").select("*").eq("child_id", child_id).execute()
        mastery_rows = getattr(r, "data", None) or []

        mastered_topics: list[str] = []
        improving_topics: list[str] = []
        needs_attention: list[str] = []
        subject_mastered: dict[str, int] = {}
        subject_attention: dict[str, int] = {}

        for row in mastery_rows:
            slug = row.get("topic_slug", "")
            subj = row.get("subject", "unknown")
            level = row.get("mastery_level", "unknown")

            if level == "mastered":
                mastered_topics.append(slug)
                subject_mastered[subj] = subject_mastered.get(subj, 0) + 1
            elif level == "improving":
                improving_topics.append(slug)
            else:  # unknown or learning
                needs_attention.append(slug)
                subject_attention[subj] = subject_attention.get(subj, 0) + 1

        strongest = max(subject_mastered, key=lambda k: subject_mastered[k]) if subject_mastered else None
        weakest = max(subject_attention, key=lambda k: subject_attention[k]) if subject_attention else None

        # Aggregate from learning_sessions
        s = (
            sb.table("learning_sessions")
            .select("questions_total, score_pct")
            .eq("child_id", child_id)
            .execute()
        )
        session_rows = getattr(s, "data", None) or []
        total_sessions = len(session_rows)
        total_questions = sum(row.get("questions_total", 0) for row in session_rows)
        scores = [row["score_pct"] for row in session_rows if row.get("score_pct") is not None]
        overall_accuracy = round(sum(scores) / len(scores)) if scores else 0

        now_iso = datetime.now(timezone.utc).isoformat()
        payload = {
            "child_id": child_id,
            "mastered_topics": mastered_topics,
            "improving_topics": improving_topics,
            "needs_attention": needs_attention,
            "strongest_subject": strongest,
            "weakest_subject": weakest,
            "total_sessions": total_sessions,
            "total_questions": total_questions,
            "overall_accuracy": overall_accuracy,
            "last_updated_at": now_iso,
        }
        sb.table("child_learning_summary").upsert(payload, on_conflict="child_id").execute()

    # -----------------------------------------------------------------------
    # Private DB helper
    # -----------------------------------------------------------------------

    def _get_topic_mastery_row(self, sb, child_id: str, topic_slug: str) -> Optional[dict]:
        r = (
            sb.table("topic_mastery")
            .select("*")
            .eq("child_id", child_id)
            .eq("topic_slug", topic_slug)
            .maybe_single()
            .execute()
        )
        return getattr(r, "data", None)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

def get_learning_graph_service() -> LearningGraphService:
    """Returns a LearningGraphService backed by Supabase."""
    from app.services.supabase_client import get_supabase_client
    try:
        sb = get_supabase_client()
        return LearningGraphService(supabase_client=sb)
    except Exception as exc:
        logger.error("[learning_graph.get_learning_graph_service] Failed to get Supabase client: %s", exc)
        raise
