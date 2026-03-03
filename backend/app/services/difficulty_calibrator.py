"""
Difficulty Calibrator — Agent 4 of 4 in the generation pipeline (final step).

Runs four deterministic post-processing steps on the assembled question list:

  STEP A — Sort by difficulty (scaffolding=True only)
    Sorts questions so easier items come first. Sort key: question word count
    ascending, then word_problem format last. This gives struggling learners
    a warm-up ramp before harder formats.

  STEP A2 — Intra-band shuffle (scaffolding=True only)
    After sorting, questions with the same difficulty key are shuffled within
    their band so worksheets feel varied even with identical difficulty profiles.

  STEP B — Add scaffolding hints (scaffolding=True only)
    Injects a simple template hint into the first 2 questions that do not
    already have a non-empty 'hint' field.  The hint is deterministic and
    does not require an LLM call.
    Format: "Think about: <first meaningful word from topic_slug>"

  STEP B2 — Add encouragement at Q5 (scaffolding=True only)
    Stamps '_encouragement' on the 5th question to provide a mid-worksheet
    motivational boost for struggling learners.

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

  STEP F — Break adjacent same-format runs (all modes)
    When two or more consecutive questions share the same format, swaps
    the second one with the nearest question of a different format. This
    prevents format-clustering that makes worksheets feel formulaic.

All steps are fail-open: exceptions are logged and skipped so calibration
never blocks generation.
"""

from __future__ import annotations

import logging
import random
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
# Intra-band shuffle (STEP A2)
# ---------------------------------------------------------------------------


def _shuffle_within_bands(questions: list) -> list:
    """Shuffle questions within same-difficulty bands to add variety.

    After STEP A sorts by difficulty, questions with the same sort key are
    in a deterministic order. This step shuffles within each band so that
    worksheets with identical difficulty profiles still feel different.

    Returns a new list with bands internally shuffled.
    """
    if len(questions) < 3:
        return questions

    # Group consecutive questions that share the same sort key
    bands: list[list[dict]] = []
    current_band: list[dict] = [questions[0]]
    current_key = _sort_key(questions[0])

    for q in questions[1:]:
        key = _sort_key(q)
        if key == current_key:
            current_band.append(q)
        else:
            bands.append(current_band)
            current_band = [q]
            current_key = key
    bands.append(current_band)

    # Shuffle each band internally
    result: list[dict] = []
    for band in bands:
        if len(band) > 1:
            random.shuffle(band)
        result.extend(band)

    return result


# ---------------------------------------------------------------------------
# Adjacent same-format breaker (STEP F)
# ---------------------------------------------------------------------------


def _break_adjacent_formats(questions: list) -> list[str]:
    """Swap questions to eliminate consecutive same-format runs.

    When Q[i] and Q[i+1] share the same format, find the nearest Q[j]
    (j > i+1) with a different format and swap Q[i+1] ↔ Q[j].

    Returns action log strings.
    """
    if len(questions) < 3:
        return []

    warnings: list[str] = []
    swaps = 0

    for i in range(len(questions) - 1):
        fmt_i = questions[i].get("format", "")
        fmt_next = questions[i + 1].get("format", "")
        if fmt_i and fmt_i == fmt_next:
            # Find nearest different-format question after i+1
            best_j = None
            for j in range(i + 2, len(questions)):
                if questions[j].get("format", "") != fmt_i:
                    best_j = j
                    break
            if best_j is not None:
                questions[i + 1], questions[best_j] = questions[best_j], questions[i + 1]
                warnings.append(f"Swapped Q{i + 2} ↔ Q{best_j + 1} (adjacent format '{fmt_i}' broken)")
                swaps += 1

    if swaps:
        logger.info("[difficulty_calibrator] STEP F: %d swap(s) to break adjacent formats", swaps)

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

        # ── STEP A2: Intra-band shuffle (scaffolding only, S1) ─────────────
        if context.scaffolding:
            try:
                result = _shuffle_within_bands(result)
                logger.debug(
                    "[difficulty_calibrator] STEP A2: shuffled within difficulty bands",
                )
            except Exception as exc:
                logger.warning("[difficulty_calibrator] STEP A2 intra-band shuffle failed: %s", exc)

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

        # ── STEP B2: Add encouragement at Q5 (scaffolding only, T4) ───────
        if context.scaffolding:
            try:
                if len(result) >= 5:
                    q5 = result[4]  # 0-indexed position 4 = Q5
                    if not q5.get("_encouragement"):
                        q5["_encouragement"] = "You're doing great! Keep going!"
                        logger.debug("[difficulty_calibrator] STEP B2: encouragement added at Q5")
            except Exception as exc:
                logger.warning("[difficulty_calibrator] STEP B2 encouragement failed: %s", exc)

        # ── STEP C: Add bonus challenge question (challenge_mode only) ────
        if context.challenge_mode:
            try:
                skill_tag = context.valid_skill_tags[0] if context.valid_skill_tags else "general"
                bonus = {
                    "question_text": f"BONUS: {context.topic_slug} challenge problem",
                    "format": "word_problem",
                    "difficulty": "hard",
                    "skill_tag": skill_tag,
                    "answer": "See working",
                    "_is_bonus": True,
                }
                result.append(bonus)
                logger.info("[difficulty_calibrator] STEP C: bonus challenge question appended")
            except Exception as exc:
                logger.warning("[difficulty_calibrator] STEP C bonus append failed: %s", exc)

        # ── STEP D: Fix format distribution (active swap) ─────────────────
        fmt_swaps = 0
        try:
            fmt_warnings = _fix_format_distribution(result, context)
            fmt_swaps = sum(1 for w in fmt_warnings if "swapped" in w.lower())
            calibration_warnings.extend(fmt_warnings)
        except Exception as exc:
            logger.warning("[difficulty_calibrator] STEP D format fix failed: %s", exc)

        # ── STEP E: Fix number-range-by-position (active reorder) ─────────
        nr_swaps = 0
        try:
            nr_warnings = _fix_number_range_by_position(result)
            nr_swaps = sum(1 for w in nr_warnings if "Swapped" in w)
            calibration_warnings.extend(nr_warnings)
        except Exception as exc:
            logger.warning("[difficulty_calibrator] STEP E number range fix failed: %s", exc)

        # ── STEP F: Break adjacent same-format runs (all modes) ───────────
        adj_swaps = 0
        try:
            adj_warnings = _break_adjacent_formats(result)
            adj_swaps = sum(1 for w in adj_warnings if "Swapped" in w)
            calibration_warnings.extend(adj_warnings)
        except Exception as exc:
            logger.warning("[difficulty_calibrator] STEP F adjacent format fix failed: %s", exc)

        # ── STEP G: Ensure difficulty variety (all modes) ────────────────
        # If ALL questions have the same difficulty, relabel first 1-2 to
        # provide scaffolding. Even a "hard" worksheet needs a warmup.
        try:
            difficulties = [q.get("difficulty", "medium") for q in result if not q.get("_is_bonus")]
            unique_diffs = set(difficulties)
            if len(unique_diffs) == 1 and len(result) >= 5:
                sole_diff = difficulties[0]
                # Map: what to relabel the first questions as
                _RELABEL_MAP = {
                    "hard": ["medium", "medium"],
                    "medium": ["easy"],
                    "easy": [],  # all-easy is fine
                }
                relabels = _RELABEL_MAP.get(sole_diff, [])
                for i, new_diff in enumerate(relabels):
                    if i < len(result) and not result[i].get("_is_bonus"):
                        old_diff = result[i].get("difficulty", sole_diff)
                        result[i]["difficulty"] = new_diff
                        calibration_warnings.append(
                            f"Q{result[i].get('id', i + 1)}: difficulty relabeled '{old_diff}' → '{new_diff}' (scaffolding warmup)"
                        )
                        logger.info(
                            "[difficulty_calibrator] STEP G: Q%s relabeled %s → %s",
                            result[i].get("id", i + 1),
                            old_diff,
                            new_diff,
                        )
        except Exception as exc:
            logger.warning("[difficulty_calibrator] STEP G difficulty variety failed: %s", exc)

        # ── STEP G2: Clamp difficulty to requested bloom level ────────────
        # When user requests "easy" (bloom=recall), cap at medium.
        # When "medium" (bloom=application), allow up to hard but limit to 20%.
        try:
            bloom = context.bloom_level
            if bloom == "recall":
                # Easy worksheet: no "hard" questions
                for q in result:
                    if q.get("difficulty") == "hard" and not q.get("_is_bonus"):
                        q["difficulty"] = "medium"
                        calibration_warnings.append(
                            f"Q{q.get('id', '?')}: difficulty clamped 'hard' → 'medium' (easy worksheet)"
                        )
        except Exception as exc:
            logger.warning("[difficulty_calibrator] STEP G2 difficulty clamp failed: %s", exc)

        # ── STEP H: MCQ cap — max 40% MCQ for 10Q worksheets ────────────
        # If MCQ dominates, relabel excess to fill_blank or short_answer.
        try:
            non_bonus = [q for q in result if not q.get("_is_bonus")]
            mcq_indices = [i for i, q in enumerate(result) if q.get("type") == "mcq" and not q.get("_is_bonus")]
            mcq_cap = max(4, len(non_bonus) * 40 // 100)  # 40% cap, min 4
            if len(mcq_indices) > mcq_cap:
                # Relabel excess MCQs (from the end) to fill_blank or short_answer
                _alt_types = ["fill_blank", "short_answer"]
                excess = mcq_indices[mcq_cap:]  # indices to relabel
                for j, idx in enumerate(excess):
                    new_type = _alt_types[j % len(_alt_types)]
                    old_type = result[idx].get("type", "mcq")
                    result[idx]["type"] = new_type
                    # Remove options for non-MCQ types
                    if new_type != "mcq":
                        result[idx].pop("options", None)
                    calibration_warnings.append(
                        f"Q{result[idx].get('id', idx + 1)}: type changed '{old_type}' → '{new_type}' (MCQ cap {mcq_cap}/{len(non_bonus)})"
                    )
                    logger.info(
                        "[difficulty_calibrator] STEP H: Q%s type %s → %s (MCQ cap)",
                        result[idx].get("id", idx + 1),
                        old_type,
                        new_type,
                    )
        except Exception as exc:
            logger.warning("[difficulty_calibrator] STEP H MCQ cap failed: %s", exc)

        # ── Pre-correction quality score ──────────────────────────────────
        total_corrections = fmt_swaps + nr_swaps + adj_swaps
        calibration_warnings.append(
            f"[calibration_score] corrections={total_corrections} (format_swaps={fmt_swaps}, number_swaps={nr_swaps}, adjacent_swaps={adj_swaps})"
        )

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
