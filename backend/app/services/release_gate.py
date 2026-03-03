"""
Release Gate Engine — deterministic contract enforcement.

Runs AFTER all 4 agents (topic intelligence → prompt builder → quality reviewer
→ difficulty calibrator), BEFORE the API serializes the response.

13 rules, each a standalone function registered via decorator.
3 enforcement levels:
  BLOCK   — reject + retry (if attempts remain)
  DEGRADE — serve as `best_effort` with degradation reasons
  STAMP   — attach metadata, always serve

All rules are fail-open: a crashing rule counts as failed with its declared
enforcement level, never blocks the entire gate.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

VALID_QUESTION_TYPES: frozenset[str] = frozenset(
    {"mcq", "fill_blank", "true_false", "short_answer", "word_problem", "error_detection"}
)


class Enforcement(str, Enum):
    BLOCK = "block"
    DEGRADE = "degrade"
    STAMP = "stamp"


@dataclass
class RuleResult:
    rule_name: str
    passed: bool
    enforcement: Enforcement
    detail: str = ""
    stamps: dict = field(default_factory=dict)


@dataclass
class ReleaseVerdict:
    passed: bool  # True if zero BLOCK rules failed
    verdict: str  # "released" | "best_effort" | "blocked"
    failed_rules: list[str] = field(default_factory=list)
    rule_results: list[RuleResult] = field(default_factory=list)
    stamps: dict = field(default_factory=dict)
    block_reasons: list[str] = field(default_factory=list)
    degrade_reasons: list[str] = field(default_factory=list)


@dataclass
class GateContext:
    questions: list[dict]
    grade_level: str
    grade_num: int
    subject: str
    topic: str
    num_questions: int
    difficulty: str
    warnings: list[str]
    generation_context: Any | None = None  # GenerationContext or None
    curriculum_available: bool = True


# ---------------------------------------------------------------------------
# Rule Registry
# ---------------------------------------------------------------------------

RuleFunc = Callable[[GateContext], RuleResult]
RULE_REGISTRY: list[tuple[str, Enforcement, RuleFunc]] = []


def register_rule(name: str, enforcement: Enforcement):
    """Decorator to register a rule function."""

    def decorator(func: RuleFunc) -> RuleFunc:
        RULE_REGISTRY.append((name, enforcement, func))
        return func

    return decorator


# ---------------------------------------------------------------------------
# Format mapping (shared with difficulty_calibrator)
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

_NUMBER_RE = re.compile(r"\b\d+\b")


# ---------------------------------------------------------------------------
# R01 — ARITHMETIC_VERIFIED (BLOCK)
# ---------------------------------------------------------------------------


@register_rule("R01_ARITHMETIC_VERIFIED", Enforcement.BLOCK)
def r01_arithmetic_verified(ctx: GateContext) -> RuleResult:
    """Maths: 0 questions may have _math_unverified=True."""
    if ctx.subject.lower() != "maths":
        return RuleResult("R01_ARITHMETIC_VERIFIED", True, Enforcement.BLOCK, "Non-Maths: skipped")

    unverified = [q for q in ctx.questions if q.get("_math_unverified")]
    passed = len(unverified) == 0
    return RuleResult(
        "R01_ARITHMETIC_VERIFIED",
        passed,
        Enforcement.BLOCK,
        f"{len(unverified)} unverified math question(s)" if not passed else "All verified",
    )


# ---------------------------------------------------------------------------
# R02 — KNOWN_TYPES_ONLY (BLOCK)
# ---------------------------------------------------------------------------


@register_rule("R02_KNOWN_TYPES_ONLY", Enforcement.BLOCK)
def r02_known_types_only(ctx: GateContext) -> RuleResult:
    """Every question type must be in VALID_QUESTION_TYPES."""
    bad_types = []
    for i, q in enumerate(ctx.questions):
        qt = q.get("type", "")
        if not qt or qt not in VALID_QUESTION_TYPES:
            bad_types.append(f"Q{i + 1}: '{qt}'")

    passed = len(bad_types) == 0
    return RuleResult(
        "R02_KNOWN_TYPES_ONLY",
        passed,
        Enforcement.BLOCK,
        f"Unknown types: {', '.join(bad_types)}" if not passed else "All types valid",
    )


# ---------------------------------------------------------------------------
# R03 — FORMAT_MIX_TOLERANCE (DEGRADE)
# ---------------------------------------------------------------------------


@register_rule("R03_FORMAT_MIX_TOLERANCE", Enforcement.DEGRADE)
def r03_format_mix_tolerance(ctx: GateContext) -> RuleResult:
    """Max 15pp drift per format category from format_mix target."""
    gc = ctx.generation_context
    if gc is None or not getattr(gc, "format_mix", None):
        return RuleResult("R03_FORMAT_MIX_TOLERANCE", True, Enforcement.DEGRADE, "No format_mix target")

    total = len(ctx.questions)
    if total == 0:
        return RuleResult("R03_FORMAT_MIX_TOLERANCE", True, Enforcement.DEGRADE, "No questions")

    target = gc.format_mix
    q_keys = [_FMT_TO_KEY.get(q.get("format", "other"), q.get("format", "other")) for q in ctx.questions]
    actual_counts = Counter(q_keys)

    drifts = []
    for key, target_pct in target.items():
        actual_pct = actual_counts.get(key, 0) / total * 100
        drift = abs(actual_pct - target_pct)
        if drift > 15:
            drifts.append(f"'{key}' target={target_pct}% actual={actual_pct:.0f}% drift={drift:.0f}pp")

    passed = len(drifts) == 0
    return RuleResult(
        "R03_FORMAT_MIX_TOLERANCE",
        passed,
        Enforcement.DEGRADE,
        f"Format drift: {'; '.join(drifts)}" if not passed else "Within tolerance",
    )


# ---------------------------------------------------------------------------
# R04 — CURRICULUM_GROUNDED (DEGRADE)
# ---------------------------------------------------------------------------


@register_rule("R04_CURRICULUM_GROUNDED", Enforcement.DEGRADE)
def r04_curriculum_grounded(ctx: GateContext) -> RuleResult:
    """Check curriculum_available flag and warnings for unavailable curriculum."""
    if not ctx.curriculum_available:
        return RuleResult(
            "R04_CURRICULUM_GROUNDED",
            False,
            Enforcement.DEGRADE,
            "Curriculum not available for this topic",
        )

    curriculum_warnings = [w for w in ctx.warnings if "[curriculum]" in w.lower() and "unavailable" in w.lower()]
    passed = len(curriculum_warnings) == 0
    return RuleResult(
        "R04_CURRICULUM_GROUNDED",
        passed,
        Enforcement.DEGRADE,
        f"Curriculum warnings: {curriculum_warnings[0]}" if not passed else "Curriculum grounded",
    )


# ---------------------------------------------------------------------------
# R05 — QUESTION_COUNT_EXACT (BLOCK)
# ---------------------------------------------------------------------------


@register_rule("R05_QUESTION_COUNT_EXACT", Enforcement.BLOCK)
def r05_question_count_exact(ctx: GateContext) -> RuleResult:
    """Non-bonus count >= requested-1 (for 10+), exact (for <10)."""
    non_bonus = [q for q in ctx.questions if not q.get("_is_bonus")]
    actual = len(non_bonus)
    requested = ctx.num_questions

    if requested >= 10:
        passed = actual >= requested - 1
        detail = f"Got {actual}/{requested} (min {requested - 1})"
    else:
        passed = actual >= requested
        detail = f"Got {actual}/{requested} (exact required)"

    return RuleResult("R05_QUESTION_COUNT_EXACT", passed, Enforcement.BLOCK, detail)


# ---------------------------------------------------------------------------
# R06 — ADAPTIVE_EXPLICIT (STAMP)
# ---------------------------------------------------------------------------


@register_rule("R06_ADAPTIVE_EXPLICIT", Enforcement.STAMP)
def r06_adaptive_explicit(ctx: GateContext) -> RuleResult:
    """Stamp adaptive_fallback and adaptive_source on every worksheet."""
    gc = ctx.generation_context
    fallback = getattr(gc, "adaptive_fallback", True) if gc else True
    source = "defaults" if fallback else "learning_graph"

    return RuleResult(
        "R06_ADAPTIVE_EXPLICIT",
        True,  # Always passes
        Enforcement.STAMP,
        f"adaptive_fallback={fallback}, source={source}",
        stamps={"adaptive_fallback": fallback, "adaptive_source": source},
    )


# ---------------------------------------------------------------------------
# R07 — WORD_PROBLEM_VERIFIED (DEGRADE)
# ---------------------------------------------------------------------------


@register_rule("R07_WORD_PROBLEM_VERIFIED", Enforcement.DEGRADE)
def r07_word_problem_verified(ctx: GateContext) -> RuleResult:
    """Maths: ≤20% of word problems with 4+ numbers and no _answer_corrected."""
    if ctx.subject.lower() != "maths":
        return RuleResult("R07_WORD_PROBLEM_VERIFIED", True, Enforcement.DEGRADE, "Non-Maths: skipped")

    wp_formats = {"word_problem", "word_problem_english", "word_problem_science", "word_problem_hindi"}
    word_problems = [q for q in ctx.questions if q.get("format", q.get("type", "")) in wp_formats]

    if not word_problems:
        return RuleResult("R07_WORD_PROBLEM_VERIFIED", True, Enforcement.DEGRADE, "No word problems")

    complex_unverified = 0
    for q in word_problems:
        text = q.get("question_text", q.get("text", ""))
        nums = _NUMBER_RE.findall(text)
        if len(nums) >= 4 and not q.get("_answer_corrected"):
            complex_unverified += 1

    ratio = complex_unverified / len(word_problems) if word_problems else 0
    passed = ratio <= 0.20
    return RuleResult(
        "R07_WORD_PROBLEM_VERIFIED",
        passed,
        Enforcement.DEGRADE,
        f"{complex_unverified}/{len(word_problems)} complex WPs unverified ({ratio:.0%})",
    )


# ---------------------------------------------------------------------------
# R08 — MINIMUM_QUALITY_BAR (BLOCK)
# ---------------------------------------------------------------------------


@register_rule("R08_MINIMUM_QUALITY_BAR", Enforcement.BLOCK)
def r08_minimum_quality_bar(ctx: GateContext) -> RuleResult:
    """≤2 combined serious issues across non-bonus questions."""
    serious = 0
    details = []
    for i, q in enumerate(ctx.questions):
        if q.get("_is_bonus"):
            continue
        if q.get("_math_unverified"):
            serious += 1
            details.append(f"Q{i + 1}: math_unverified")
        if q.get("_needs_regen"):
            serious += 1
            details.append(f"Q{i + 1}: needs_regen")
        text = q.get("question_text", q.get("text", ""))
        if not text or not text.strip():
            serious += 1
            details.append(f"Q{i + 1}: empty_text")
        answer = q.get("answer", q.get("correct_answer", ""))
        if not answer and not q.get("options"):
            serious += 1
            details.append(f"Q{i + 1}: missing_answer")

    passed = serious <= 2
    return RuleResult(
        "R08_MINIMUM_QUALITY_BAR",
        passed,
        Enforcement.BLOCK,
        f"{serious} serious issue(s): {', '.join(details[:5])}" if details else "Clean",
    )


# ---------------------------------------------------------------------------
# R09 — SKILL_TAGS_VALID (DEGRADE)
# ---------------------------------------------------------------------------


@register_rule("R09_SKILL_TAGS_VALID", Enforcement.DEGRADE)
def r09_skill_tags_valid(ctx: GateContext) -> RuleResult:
    """All tags in valid_skill_tags; no single tag >60% when 3+ available."""
    gc = ctx.generation_context
    valid_tags = set(getattr(gc, "valid_skill_tags", [])) if gc else set()

    if not valid_tags:
        return RuleResult("R09_SKILL_TAGS_VALID", True, Enforcement.DEGRADE, "No valid_skill_tags defined")

    # Check for invalid tags
    tag_counts: Counter = Counter()
    invalid = []
    for i, q in enumerate(ctx.questions):
        if q.get("_is_bonus"):
            continue
        tag = q.get("skill_tag", "")
        if tag:
            tag_counts[tag] += 1
            if tag not in valid_tags:
                invalid.append(f"Q{i + 1}: '{tag}'")

    issues = []
    if invalid:
        issues.append(f"Invalid tags: {', '.join(invalid[:3])}")

    # Check diversity: no single tag >60% when 3+ valid tags
    total_tagged = sum(tag_counts.values())
    if len(valid_tags) >= 3 and total_tagged > 0:
        for tag, count in tag_counts.most_common(1):
            pct = count / total_tagged * 100
            if pct > 60:
                issues.append(f"Tag '{tag}' dominates at {pct:.0f}% (max 60%)")

    passed = len(issues) == 0
    return RuleResult(
        "R09_SKILL_TAGS_VALID",
        passed,
        Enforcement.DEGRADE,
        "; ".join(issues) if issues else "Tags valid and diverse",
    )


# ---------------------------------------------------------------------------
# R10 — WARNINGS_TRANSPARENT (STAMP)
# ---------------------------------------------------------------------------

# Warning classification patterns
_CRITICAL_PATTERNS = [
    "math answer",
    "math incorrect",
    "empty question",
    "MCQ answer not in options",
    "BLOCKED",
    "count_mismatch",
    "_math_unverified",
]
_MODERATE_PATTERNS = [
    "Topic drift",
    "Near-duplicate",
    "type_error",
    "format drift",
    "word_count",
    "skill_tag",
    "curriculum",
]


@register_rule("R10_WARNINGS_TRANSPARENT", Enforcement.STAMP)
def r10_warnings_transparent(ctx: GateContext) -> RuleResult:
    """Classify warnings → stamp quality_tier and severity_score."""
    crit = mod = info = 0
    for w in ctx.warnings:
        wl = w.lower()
        if any(p.lower() in wl for p in _CRITICAL_PATTERNS):
            crit += 1
        elif any(p.lower() in wl for p in _MODERATE_PATTERNS):
            mod += 1
        else:
            info += 1

    severity_score = crit * 3 + mod * 2 + info * 1

    if crit > 0 or severity_score >= 10:
        quality_tier = "low"
    elif mod > 0 or severity_score >= 4:
        quality_tier = "medium"
    else:
        quality_tier = "high"

    return RuleResult(
        "R10_WARNINGS_TRANSPARENT",
        True,  # Always passes
        Enforcement.STAMP,
        f"crit={crit} mod={mod} info={info} score={severity_score} tier={quality_tier}",
        stamps={
            "quality_tier": quality_tier,
            "severity_score": severity_score,
            "warning_breakdown": {"critical": crit, "moderate": mod, "info": info},
        },
    )


# ---------------------------------------------------------------------------
# R11 — TOPIC_DRIFT_GUARD (DEGRADE)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# R12 — ROUND_NUMBER_GUARD (DEGRADE)
# ---------------------------------------------------------------------------


@register_rule("R12_ROUND_NUMBER_GUARD", Enforcement.DEGRADE)
def r12_round_number_guard(ctx: GateContext) -> RuleResult:
    """Degrade if >40% of numbers are round (multiples of 5/10). Only for Maths."""
    import re as _re

    if ctx.subject.lower() not in ("maths", "mathematics", "math"):
        return RuleResult("R12_ROUND_NUMBER_GUARD", True, Enforcement.DEGRADE, "Non-maths — skipped")

    all_nums: list[int] = []
    for q in ctx.questions:
        text = q.get("text", q.get("question_text", ""))
        for n_str in _re.findall(r"\b(\d+)\b", text):
            n = int(n_str)
            if n > 1:
                all_nums.append(n)

    if len(all_nums) < 5:
        return RuleResult("R12_ROUND_NUMBER_GUARD", True, Enforcement.DEGRADE, "Too few numbers to check")

    round_count = sum(1 for n in all_nums if n % 5 == 0)
    ratio = round_count / len(all_nums)
    passed = ratio <= 0.40
    return RuleResult(
        "R12_ROUND_NUMBER_GUARD",
        passed,
        Enforcement.DEGRADE,
        f"{round_count}/{len(all_nums)} round ({ratio:.0%})"
        if not passed
        else f"{round_count}/{len(all_nums)} within tolerance",
    )


@register_rule("R11_TOPIC_DRIFT_GUARD", Enforcement.DEGRADE)
def r11_topic_drift_guard(ctx: GateContext) -> RuleResult:
    """Degrade if >50% of questions appear off-topic based on warnings."""
    import re as _re

    drift_match = None
    for w in ctx.warnings:
        m = _re.search(r"Topic drift:\s*(\d+)/(\d+)", w)
        if m:
            drift_match = m
            break

    if not drift_match:
        return RuleResult("R11_TOPIC_DRIFT_GUARD", True, Enforcement.DEGRADE, "No drift detected")

    off_topic = int(drift_match.group(1))
    total = int(drift_match.group(2))
    ratio = off_topic / max(total, 1)

    passed = ratio <= 0.50
    return RuleResult(
        "R11_TOPIC_DRIFT_GUARD",
        passed,
        Enforcement.DEGRADE,
        f"{off_topic}/{total} off-topic ({ratio:.0%})" if not passed else f"{off_topic}/{total} within tolerance",
    )


# ---------------------------------------------------------------------------
# R13 — SENTENCE_STRUCTURE_GUARD (DEGRADE)
# ---------------------------------------------------------------------------


@register_rule("R13_SENTENCE_STRUCTURE_GUARD", Enforcement.DEGRADE)
def r13_sentence_structure_guard(ctx: GateContext) -> RuleResult:
    """Degrade if sentence structure diversity is too low (≥5 questions)."""
    if len(ctx.questions) < 5:
        return RuleResult("R13_SENTENCE_STRUCTURE_GUARD", True, Enforcement.DEGRADE, "Too few questions")

    import re as _re

    _qw = _re.compile(r"(?i)^(what|which|how|who|where|when|why)\b")
    _imp = _re.compile(
        r"(?i)^(find|solve|write|fill|complete|calculate|match|draw|circle|count"
        r"|add|subtract|multiply|divide|arrange|list|name|identify|help|can you|try to|let'?s)\b"
    )
    _cond = _re.compile(r"(?i)^(if|suppose|imagine|given)\b")

    types: set[str] = set()
    for q in ctx.questions:
        text = q.get("text", q.get("question_text", "")).strip()
        if _qw.match(text):
            types.add("question_word")
        elif _imp.match(text):
            types.add("imperative")
        elif _cond.match(text):
            types.add("conditional")
        else:
            types.add("statement")

    min_needed = 3 if len(ctx.questions) >= 10 else 2
    passed = len(types) >= min_needed
    return RuleResult(
        "R13_SENTENCE_STRUCTURE_GUARD",
        passed,
        Enforcement.DEGRADE,
        f"Only {len(types)} structure type(s) ({', '.join(sorted(types))}), need ≥{min_needed}"
        if not passed
        else f"{len(types)} structure types — OK",
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def run_release_gate(
    questions: list[dict],
    grade_level: str,
    subject: str,
    topic: str,
    num_questions: int,
    difficulty: str,
    warnings: list[str],
    generation_context: Any | None = None,
    curriculum_available: bool = True,
) -> ReleaseVerdict:
    """
    Run all registered rules and produce a ReleaseVerdict.

    Returns:
        ReleaseVerdict with verdict in {"released", "best_effort", "blocked"}.
    """
    # Parse grade number
    grade_num = 3  # safe default
    for part in grade_level.replace("-", " ").split():
        if part.isdigit():
            grade_num = int(part)
            break

    ctx = GateContext(
        questions=questions,
        grade_level=grade_level,
        grade_num=grade_num,
        subject=subject,
        topic=topic,
        num_questions=num_questions,
        difficulty=difficulty,
        warnings=list(warnings),
        generation_context=generation_context,
        curriculum_available=curriculum_available,
    )

    results: list[RuleResult] = []
    merged_stamps: dict = {}
    block_reasons: list[str] = []
    degrade_reasons: list[str] = []
    failed_rules: list[str] = []

    for name, enforcement, func in RULE_REGISTRY:
        try:
            result = func(ctx)
        except Exception as exc:
            logger.warning("[release_gate] Rule %s crashed: %s", name, exc)
            result = RuleResult(name, False, enforcement, f"Crashed: {exc}")

        results.append(result)
        merged_stamps.update(result.stamps)

        if not result.passed:
            failed_rules.append(name)
            if result.enforcement == Enforcement.BLOCK:
                block_reasons.append(f"[{name}] {result.detail}")
            elif result.enforcement == Enforcement.DEGRADE:
                degrade_reasons.append(f"[{name}] {result.detail}")

    # Determine verdict
    if block_reasons:
        verdict = "blocked"
        passed = False
    elif degrade_reasons:
        verdict = "best_effort"
        passed = True
    else:
        verdict = "released"
        passed = True

    logger.info(
        "[release_gate] verdict=%s failed=%d blocked=%d degraded=%d",
        verdict,
        len(failed_rules),
        len(block_reasons),
        len(degrade_reasons),
    )

    return ReleaseVerdict(
        passed=passed,
        verdict=verdict,
        failed_rules=failed_rules,
        rule_results=results,
        stamps=merged_stamps,
        block_reasons=block_reasons,
        degrade_reasons=degrade_reasons,
    )
