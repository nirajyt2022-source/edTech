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

  STEP D — Fix format distribution (all modes)
    Counts actual question formats and compares to context.format_mix.
    When a format drifts more than 20pp from target, actively swaps excess
    questions to the most underrepresented format.

  STEP E — Fix number-range-by-position (all modes)
    Swaps questions so warm-up (Q1-3) uses smaller numbers and stretch
    (Q8+) uses larger numbers.

All steps are fail-open: exceptions are logged and skipped so calibration
never blocks generation.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from app.services.topic_intelligence import GenerationContext

logger = logging.getLogger(__name__)

# ── Number-range extraction helper (STEP E) ──
_NUMBER_RE = re.compile(r"\b\d+\b")

# ---------------------------------------------------------------------------
# Sort helpers (STEP A)
# ---------------------------------------------------------------------------

# Formats that are considered "harder" (pushed to the end during scaffolding sort)
_HARD_FORMATS: frozenset[str] = frozenset(
    {
        "word_problem",
        "word_problem_english",
        "word_problem_science",
        "word_problem_hindi",
        "multi_step",
        "multi_step_science",
        "growing_pattern",
        "thinking",
        "thinking_science",
    }
)


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


_FMT_TO_KEY: dict[str, str] = {
    "word_problem": "word_problem",
    "word_problem_english": "word_problem",
    "word_problem_science": "word_problem",
    "word_problem_hindi": "word_problem",
    "fill_in_blank": "fill_blank",
    "fill_blank": "fill_blank",
    "paragraph_cloze": "fill_blank",
}

# Reverse: canonical key → preferred concrete format name
_KEY_TO_FMT: dict[str, str] = {
    "word_problem": "word_problem",
    "fill_blank": "fill_blank",
    "mcq": "mcq",
}


def _fix_format_distribution(questions: list, context: GenerationContext) -> list[str]:
    """
    Check actual format distribution and swap excess formats toward the target.

    Returns list of warning/action strings.
    """
    if not questions or not context.format_mix:
        return []

    total = len(questions)
    target = context.format_mix

    # Build per-question canonical key mapping
    q_keys = []
    for q in questions:
        fmt = q.get("format", "other")
        q_keys.append(_FMT_TO_KEY.get(fmt, fmt))

    # Count actuals
    from collections import Counter

    actual_counts = Counter(q_keys)
    warnings: list[str] = []

    # Compute target counts (rounded)
    target_counts: dict[str, int] = {}
    for key, pct in target.items():
        target_counts[key] = max(0, round(total * pct / 100))

    # Find over- and under-represented keys
    over: list[tuple[str, int]] = []  # (key, excess)
    under: list[tuple[str, int]] = []  # (key, deficit)

    for key in set(list(target_counts.keys()) + list(actual_counts.keys())):
        actual = actual_counts.get(key, 0)
        expected = target_counts.get(key, 0)
        diff = actual - expected
        drift_pct = abs(diff) / max(total, 1) * 100
        if drift_pct > 20 and diff > 0:
            over.append((key, diff))
        elif drift_pct > 20 and diff < 0:
            under.append((key, abs(diff)))

    if not over or not under:
        # No actionable drift
        for key, pct in target.items():
            actual_pct = actual_counts.get(key, 0) / max(total, 1) * 100
            drift = abs(actual_pct - pct)
            if drift > 20:
                warnings.append(f"Format drift: '{key}' target={pct}% actual={actual_pct:.0f}% (no swap target)")
        return warnings

    # Sort: swap from most-over to most-under
    over.sort(key=lambda x: -x[1])
    under.sort(key=lambda x: -x[1])

    swaps = 0
    for over_key, excess in over:
        for under_key, deficit in under:
            if deficit <= 0:
                continue
            # Find questions with over_key and swap their format
            for i, qk in enumerate(q_keys):
                if qk == over_key and excess > 0 and deficit > 0:
                    new_fmt = _KEY_TO_FMT.get(under_key, under_key)
                    old_fmt = questions[i].get("format", "other")
                    questions[i]["format"] = new_fmt
                    q_keys[i] = under_key
                    excess -= 1
                    deficit -= 1
                    swaps += 1
                    warnings.append(f"Q{i + 1}: format swapped '{old_fmt}' → '{new_fmt}' (drift fix)")
            # Update remaining deficit
            for j, (uk, ud) in enumerate(under):
                if uk == under_key:
                    under[j] = (uk, deficit)

    if swaps:
        logger.info("[difficulty_calibrator] STEP D: swapped %d question format(s) to reduce drift", swaps)

    logger.debug(
        "[difficulty_calibrator] Format distribution: %s",
        dict(Counter(q_keys)),
    )
    return warnings


# ---------------------------------------------------------------------------
# Number-range-by-position audit (STEP E)
# ---------------------------------------------------------------------------


def _extract_max_number(text: str) -> int:
    """Extract the largest number from question text."""
    nums = [int(n) for n in _NUMBER_RE.findall(text) if len(n) <= 6]
    return max(nums) if nums else 0


def _fix_number_range_by_position(questions: list) -> list[str]:
    """Reorder questions so number magnitudes match the position rule.

    Questions 1-3: warm-up (smaller numbers)
    Questions 4-7: practice (medium)
    Questions 8+:  stretch (larger numbers)

    Swaps violating questions into correct zones. Returns action log.
    """
    if len(questions) < 5:
        return []

    warnings: list[str] = []

    # Annotate each question with its max number
    magnitudes = [_extract_max_number(q.get("question_text", "")) for q in questions]

    # Find violations and try pairwise swaps
    swaps = 0
    for i in range(min(3, len(questions))):
        # Warm-up zone: if this Q has a large number, find a later Q with smaller
        if magnitudes[i] > 100:
            # Find best swap candidate from positions 3+
            best_j = None
            for j in range(3, len(questions)):
                if magnitudes[j] <= 100:
                    if best_j is None or magnitudes[j] < magnitudes[best_j]:
                        best_j = j
            if best_j is not None:
                questions[i], questions[best_j] = questions[best_j], questions[i]
                magnitudes[i], magnitudes[best_j] = magnitudes[best_j], magnitudes[i]
                warnings.append(f"Swapped Q{i + 1} ↔ Q{best_j + 1} (warm-up had large number)")
                swaps += 1

    for i in range(max(7, len(questions) - 1), len(questions)):
        # Stretch zone: if this Q has tiny numbers, find an earlier Q with bigger
        if 0 < magnitudes[i] < 10:
            best_j = None
            for j in range(3, 7):
                if j < len(questions) and magnitudes[j] >= 10:
                    if best_j is None or magnitudes[j] > magnitudes[best_j]:
                        best_j = j
            if best_j is not None:
                questions[i], questions[best_j] = questions[best_j], questions[i]
                magnitudes[i], magnitudes[best_j] = magnitudes[best_j], magnitudes[i]
                warnings.append(f"Swapped Q{i + 1} ↔ Q{best_j + 1} (stretch had tiny number)")
                swaps += 1

    if swaps:
        logger.info("[difficulty_calibrator] STEP E: %d swap(s) to fix number progression", swaps)

    return warnings


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
    ) -> tuple[list, list[str]]:
        """
        Calibrate the question list for this child's learning context.

        Args:
            questions: List of question dicts from the generation + review pipeline.
            context:   GenerationContext from TopicIntelligenceAgent.

        Returns:
            (calibrated_questions, calibration_warnings) — questions may be
            longer if challenge_mode=True; warnings include any swaps made.
        """
        result = list(questions)  # shallow copy — dicts are mutated in place for hints
        calibration_warnings: list[str] = []

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
                logger.debug("[difficulty_calibrator] STEP B: added %d hint(s)", hints_added)
            except Exception as exc:
                logger.warning("[difficulty_calibrator] STEP B hint injection failed: %s", exc)

        # ── STEP C: Add bonus challenge question (challenge_mode only) ────
        if context.challenge_mode:
            try:
                skill_tag = context.valid_skill_tags[0] if context.valid_skill_tags else "general"
                bonus = {
                    "question_text": f"BONUS: {context.topic_slug} challenge problem",
                    "format": "word_problem",
                    "skill_tag": skill_tag,
                    "answer": "See working",
                    "_is_bonus": True,
                }
                result.append(bonus)
                logger.info("[difficulty_calibrator] STEP C: bonus challenge question appended")
            except Exception as exc:
                logger.warning("[difficulty_calibrator] STEP C bonus append failed: %s", exc)

        # ── STEP D: Fix format distribution (active swap) ─────────────────
        try:
            fmt_warnings = _fix_format_distribution(result, context)
            calibration_warnings.extend(fmt_warnings)
        except Exception as exc:
            logger.warning("[difficulty_calibrator] STEP D format fix failed: %s", exc)

        # ── STEP E: Fix number-range-by-position (active reorder) ─────────
        try:
            nr_warnings = _fix_number_range_by_position(result)
            calibration_warnings.extend(nr_warnings)
        except Exception as exc:
            logger.warning("[difficulty_calibrator] STEP E number range fix failed: %s", exc)

        return result, calibration_warnings


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
