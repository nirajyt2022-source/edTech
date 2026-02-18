"""
Difficulty Calibrator — Agent 4 of 4 in the generation pipeline (final step).

Runs four deterministic post-processing steps on the assembled question list:

  STEP A — Sort by difficulty (scaffolding=True only)
    Sorts questions so easier items come first. Sort key: question word count
    ascending, then word_problem format last. This gives struggling learners
    a warm-up ramp before harder formats.

  STEP B — Add scaffolding hints (scaffolding=True only)
    Injects a simple template hint into the first 2 questions that do not
    already have a non-empty 'hint' field.  The hint is deterministic and
    does not require an LLM call.
    Format: "Think about: <first meaningful word from topic_slug>"

  STEP C — Add bonus challenge question (challenge_mode=True only)
    Appends a single extra dict marked with '_is_bonus: True'.  The bonus
    item signals to the frontend/PDF renderer that an extension problem is
    present. It is never validated against the slot plan.

  STEP D — Log format distribution (all modes)
    Counts actual question formats (word_problem, fill_blank, etc.) and
    compares to context.format_mix.  Emits a WARNING for any format whose
    actual share drifts more than 20 percentage points from the target.
    Never modifies questions.

All steps are fail-open: exceptions are logged and skipped so calibration
never blocks generation.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.services.topic_intelligence import GenerationContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sort helpers (STEP A)
# ---------------------------------------------------------------------------

# Formats that are considered "harder" (pushed to the end during scaffolding sort)
_HARD_FORMATS: frozenset[str] = frozenset({
    "word_problem",
    "word_problem_english",
    "word_problem_science",
    "word_problem_hindi",
    "multi_step",
    "multi_step_science",
    "growing_pattern",
    "thinking",
    "thinking_science",
})


def _sort_key(q: dict) -> tuple:
    """
    Sort key for ascending difficulty.

    Primary:  word count of question_text (ascending — shorter = easier)
    Secondary: 1 if format is in _HARD_FORMATS, 0 otherwise (hard last)
    """
    text = q.get("question_text", "")
    word_count = len(text.split())
    is_hard = 1 if q.get("format", "") in _HARD_FORMATS else 0
    return (word_count, is_hard)


# ---------------------------------------------------------------------------
# Hint builder (STEP B)
# ---------------------------------------------------------------------------

def _make_hint(topic_slug: str) -> str:
    """
    Build a simple, deterministic hint from the topic_slug.

    Strips parenthesised suffixes like '(Class 3)' and returns a short
    "Think about: <first meaningful word>" string.

    Examples:
        "Addition (carries)"          → "Think about: Addition"
        "Multiplication (tables 2-5)" → "Think about: Multiplication"
        "Nouns (Class 2)"             → "Think about: Nouns"
    """
    # Strip anything in parentheses to get the core topic name
    core = topic_slug.split("(")[0].strip()
    # Take the first meaningful word (may be a compound like "Fractions")
    first_word = core.split()[0] if core else topic_slug
    return f"Think about: {first_word}"


# ---------------------------------------------------------------------------
# Format distribution logger (STEP D)
# ---------------------------------------------------------------------------

def _log_format_distribution(questions: list, context: GenerationContext) -> None:
    """
    Count actual format distribution and warn on large drifts from target.

    Only the three canonical format_mix keys (mcq, fill_blank, word_problem)
    are checked; any extra formats are bucketed under 'other'.
    """
    if not questions:
        return

    total = len(questions)
    counts: dict[str, int] = {}
    for q in questions:
        fmt = q.get("format", "other")
        counts[fmt] = counts.get(fmt, 0) + 1

    # Map actual format names → canonical mix keys for comparison
    _FMT_TO_KEY: dict[str, str] = {
        "word_problem": "word_problem",
        "word_problem_english": "word_problem",
        "word_problem_science": "word_problem",
        "word_problem_hindi": "word_problem",
        "fill_in_blank": "fill_blank",
        "fill_blank": "fill_blank",
        "paragraph_cloze": "fill_blank",
    }

    actual_pct: dict[str, float] = {}
    for fmt, cnt in counts.items():
        key = _FMT_TO_KEY.get(fmt, fmt)
        actual_pct[key] = actual_pct.get(key, 0.0) + (cnt / total * 100)

    target = context.format_mix or {}
    for key, target_pct in target.items():
        actual = actual_pct.get(key, 0.0)
        drift = abs(actual - target_pct)
        if drift > 20:
            logger.warning(
                "[difficulty_calibrator] Format drift: '%s' target=%d%% actual=%.0f%% drift=%.0f%%",
                key, target_pct, actual, drift,
            )

    logger.debug(
        "[difficulty_calibrator] Format distribution: %s",
        {k: f"{v:.0f}%" for k, v in actual_pct.items()},
    )


# ---------------------------------------------------------------------------
# DifficultyCalibrator
# ---------------------------------------------------------------------------

class DifficultyCalibrator:
    """
    Agent 4 of 4 — final deterministic post-processing step.

    Receives the question list after QualityReviewerAgent and applies
    four fail-open calibration passes before the worksheet is returned.
    """

    def calibrate(
        self,
        questions: list,
        context: GenerationContext,
    ) -> list:
        """
        Calibrate the question list for this child's learning context.

        Args:
            questions: List of question dicts from the generation + review pipeline.
            context:   GenerationContext from TopicIntelligenceAgent.

        Returns:
            Calibrated question list (may be longer if challenge_mode=True).
        """
        result = list(questions)  # shallow copy — dicts are mutated in place for hints

        # ── STEP A: Sort by difficulty (scaffolding only) ─────────────────
        if context.scaffolding:
            try:
                result = sorted(result, key=_sort_key)
                logger.debug(
                    "[difficulty_calibrator] STEP A: sorted %d question(s) for scaffolding",
                    len(result),
                )
            except Exception as exc:
                logger.warning("[difficulty_calibrator] STEP A sort failed: %s", exc)

        # ── STEP B: Add hints for first 2 questions (scaffolding only) ────
        if context.scaffolding:
            try:
                hint_text = _make_hint(context.topic_slug)
                hints_added = 0
                for q in result:
                    if hints_added >= 2:
                        break
                    existing_hint = q.get("hint", "")
                    if not existing_hint:
                        q["hint"] = hint_text
                        hints_added += 1
                logger.debug(
                    "[difficulty_calibrator] STEP B: added %d hint(s)", hints_added
                )
            except Exception as exc:
                logger.warning("[difficulty_calibrator] STEP B hint injection failed: %s", exc)

        # ── STEP C: Add bonus challenge question (challenge_mode only) ────
        if context.challenge_mode:
            try:
                skill_tag = (
                    context.valid_skill_tags[0]
                    if context.valid_skill_tags
                    else "general"
                )
                bonus = {
                    "question_text": f"BONUS: {context.topic_slug} challenge problem",
                    "format": "word_problem",
                    "skill_tag": skill_tag,
                    "answer": "See working",
                    "_is_bonus": True,
                }
                result.append(bonus)
                logger.info(
                    "[difficulty_calibrator] STEP C: bonus challenge question appended"
                )
            except Exception as exc:
                logger.warning(
                    "[difficulty_calibrator] STEP C bonus append failed: %s", exc
                )

        # ── STEP D: Log format distribution ───────────────────────────────
        try:
            _log_format_distribution(result, context)
        except Exception as exc:
            logger.warning(
                "[difficulty_calibrator] STEP D distribution log failed: %s", exc
            )

        return result


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_CALIBRATOR: Optional[DifficultyCalibrator] = None


def get_difficulty_calibrator() -> DifficultyCalibrator:
    """Return the module-level singleton."""
    global _CALIBRATOR
    if _CALIBRATOR is None:
        _CALIBRATOR = DifficultyCalibrator()
    return _CALIBRATOR
