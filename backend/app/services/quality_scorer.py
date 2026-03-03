"""
Worksheet Quality Scoring Engine.

Standalone, deterministic, no LLM calls. Evaluates any worksheet dict
against all quality standards and returns a composite score 0-100 with
per-dimension breakdowns and structured failure reasons.

Usage:
    from app.services.quality_scorer import score_worksheet
    result = score_worksheet(worksheet_dict)
    # result.total_score  -> 0-100
    # result.dimensions   -> {name: DimensionResult}
    # result.failures     -> [FailureReason]
    # result.export_allowed -> bool
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field

logger = logging.getLogger("skolar.quality_scorer")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DIMENSION_WEIGHTS = {
    "structural": 20,
    "content": 25,
    "pedagogical": 20,
    "ai_smell": 20,
    "curriculum": 15,
}


def _get_export_threshold() -> int:
    """Read threshold from settings, falling back to env var."""
    try:
        from app.core.config import get_settings

        return get_settings().worksheet_export_min_score
    except Exception:
        return int(os.environ.get("WORKSHEET_EXPORT_MIN_SCORE", "40"))


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class FailureReason:
    """Structured failure — not just a string."""

    dimension: str  # "structural" | "content" | "pedagogical" | "ai_smell" | "curriculum"
    check_id: str  # e.g. "STRUCT_01"
    severity: str  # "critical" | "major" | "minor"
    message: str
    question_ids: list[str] = field(default_factory=list)
    points_deducted: float = 0.0


@dataclass
class DimensionResult:
    """Score for a single dimension."""

    name: str
    weight: int
    raw_score: float  # 0.0–1.0
    weighted_score: float  # raw_score * weight
    failures: list[FailureReason] = field(default_factory=list)


@dataclass
class QualityScore:
    """Complete scoring result."""

    total_score: float
    dimensions: dict[str, DimensionResult]
    failures: list[FailureReason]
    export_allowed: bool
    export_threshold: int
    ai_smell_flags: list[FailureReason]
    question_count: int
    grade: str
    subject: str


# ---------------------------------------------------------------------------
# OutputValidator error → dimension classifier
# ---------------------------------------------------------------------------

# Each tuple: (regex_pattern, dimension, check_id, severity, deduction)
_ERROR_CLASSIFIERS: list[tuple[str, str, str, str, float]] = [
    # Structural
    (r"\[count_mismatch\]", "structural", "STRUCT_01", "critical", 0.30),
    (r"empty question text", "structural", "STRUCT_02", "critical", 0.15),
    (r"missing correct_answer", "structural", "STRUCT_03", "major", 0.10),
    (r"MCQ needs at least", "structural", "STRUCT_04", "major", 0.10),
    (r"MCQ answer .* not in options", "structural", "STRUCT_05", "major", 0.10),
    (r"true_false answer must be", "structural", "STRUCT_07", "minor", 0.05),
    (r"No answer key and no answers", "structural", "STRUCT_08", "critical", 0.25),
    # AI smell
    (r"Duplicate question detected", "ai_smell", "AI_01", "critical", 0.25),
    (r"Near-duplicate pattern", "ai_smell", "AI_02", "major", 0.20),
    (r"Opening verb .* repeats", "ai_smell", "AI_03", "minor", 0.10),
    (r"Round number overuse", "ai_smell", "AI_04", "minor", 0.10),
    (r"Number pair monotony", "ai_smell", "AI_05", "minor", 0.10),
    (r"Countable object .* appears", "ai_smell", "AI_09", "minor", 0.05),
    (r"Sentence structure monotony", "ai_smell", "AI_10", "minor", 0.10),
    (r"filler phrase", "ai_smell", "AI_11", "minor", 0.05),
    (r"Scenario .* repeated", "ai_smell", "AI_07", "minor", 0.10),
    (r"Number .* appears in .* questions", "ai_smell", "AI_09B", "minor", 0.05),
    (r"No engagement framing", "ai_smell", "AI_12", "minor", 0.05),
    (r"Sequence step monotony", "ai_smell", "AI_13", "minor", 0.05),
    # Curriculum
    (r"complex vocabulary", "curriculum", "CUR_04", "minor", 0.05),
    (r"question too long", "curriculum", "CUR_05", "minor", 0.05),
    # Content
    (r"disallowed keyword", "content", "CONTENT_07", "minor", 0.05),
    (r"math answer appears incorrect", "content", "CONTENT_08", "critical", 0.40),
    (r"visual data does not match", "content", "CONTENT_05", "major", 0.15),
    (r"visual type .* is disallowed", "content", "CONTENT_09", "minor", 0.05),
    # Pedagogical
    (r"Type diversity", "pedagogical", "PED_02", "major", 0.15),
]

# Compile patterns once at module level
_COMPILED_CLASSIFIERS = [
    (re.compile(pat, re.IGNORECASE), dim, cid, sev, ded) for pat, dim, cid, sev, ded in _ERROR_CLASSIFIERS
]

# Placeholder / stub patterns
_PLACEHOLDER_RE = re.compile(r"\[Generation failed|\[Slot fill|\[TODO|\[PLACEHOLDER", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Classify OutputValidator errors into dimension buckets
# ---------------------------------------------------------------------------


def _classify_ov_errors(
    ov_errors: list[str],
    buckets: dict[str, list[FailureReason]],
) -> None:
    """Parse OutputValidator error strings and sort into dimension buckets."""
    for error_msg in ov_errors:
        matched = False
        # Try to extract question ID from error prefix (e.g. "Q3: empty question text")
        qid_match = re.match(r"^(Q?\d+):\s*", error_msg)
        qids = [qid_match.group(1)] if qid_match else []

        for pattern, dim, check_id, severity, deduction in _COMPILED_CLASSIFIERS:
            if pattern.search(error_msg):
                buckets[dim].append(
                    FailureReason(
                        dimension=dim,
                        check_id=check_id,
                        severity=severity,
                        message=error_msg,
                        question_ids=qids,
                        points_deducted=deduction,
                    )
                )
                matched = True
                break

        if not matched:
            # Unclassified OV errors go to structural as minor
            buckets["structural"].append(
                FailureReason(
                    dimension="structural",
                    check_id="STRUCT_99",
                    severity="minor",
                    message=error_msg,
                    question_ids=qids,
                    points_deducted=0.03,
                )
            )


# ---------------------------------------------------------------------------
# Supplementary checks — things OutputValidator doesn't cover
# ---------------------------------------------------------------------------


def _run_content_checks(
    questions: list[dict],
    subject: str,
    buckets: dict[str, list[FailureReason]],
) -> None:
    """Content accuracy checks beyond OutputValidator."""
    for q in questions:
        qid = q.get("id", "?")

        # CONTENT_01: _math_unverified flag
        if q.get("_math_unverified"):
            buckets["content"].append(
                FailureReason(
                    dimension="content",
                    check_id="CONTENT_01",
                    severity="critical",
                    message="Math answer unverified by AST checker",
                    question_ids=[qid],
                    points_deducted=0.30,
                )
            )

        # CONTENT_03: _needs_regen flag from quality reviewer
        if q.get("_needs_regen"):
            buckets["content"].append(
                FailureReason(
                    dimension="content",
                    check_id="CONTENT_03",
                    severity="critical",
                    message="Question flagged for regeneration by quality reviewer",
                    question_ids=[qid],
                    points_deducted=0.30,
                )
            )

        # CONTENT_02: _answer_corrected (was wrong, got auto-fixed)
        if q.get("_answer_corrected"):
            buckets["content"].append(
                FailureReason(
                    dimension="content",
                    check_id="CONTENT_02",
                    severity="minor",
                    message="Answer was auto-corrected by QualityReviewer",
                    question_ids=[qid],
                    points_deducted=0.05,
                )
            )

        # CONTENT_06: Fallback/stub question
        if q.get("is_fallback"):
            buckets["content"].append(
                FailureReason(
                    dimension="content",
                    check_id="CONTENT_06",
                    severity="critical",
                    message="Fallback stub question — LLM failed all retries",
                    question_ids=[qid],
                    points_deducted=0.30,
                )
            )

        # CONTENT_04: Self-contradiction in answer
        answer = str(q.get("correct_answer", q.get("answer", "")))
        try:
            from app.services.quality_reviewer import _check_answer_self_contradiction

            if _check_answer_self_contradiction(answer):
                buckets["content"].append(
                    FailureReason(
                        dimension="content",
                        check_id="CONTENT_04",
                        severity="critical",
                        message="Self-contradictory answer detected",
                        question_ids=[qid],
                        points_deducted=0.20,
                    )
                )
        except ImportError:
            pass


def _run_ai_smell_checks(
    questions: list[dict],
    buckets: dict[str, list[FailureReason]],
) -> None:
    """AI-smell checks beyond OutputValidator."""
    for q in questions:
        qid = q.get("id", "?")
        text = q.get("text", q.get("question_text", ""))

        # AI_06: LLM conversational artifacts
        try:
            from app.services.quality_reviewer import _contains_llm_artifact

            if _contains_llm_artifact(text):
                buckets["ai_smell"].append(
                    FailureReason(
                        dimension="ai_smell",
                        check_id="AI_06",
                        severity="critical",
                        message="LLM conversational artifact in question text",
                        question_ids=[qid],
                        points_deducted=0.20,
                    )
                )
            # Also check hint
            hint = q.get("hint", "")
            if hint and _contains_llm_artifact(hint):
                buckets["ai_smell"].append(
                    FailureReason(
                        dimension="ai_smell",
                        check_id="AI_06",
                        severity="major",
                        message="LLM conversational artifact in hint",
                        question_ids=[qid],
                        points_deducted=0.10,
                    )
                )
        except ImportError:
            pass

        # AI_08: Placeholder/generation-failed content
        if _PLACEHOLDER_RE.search(text):
            buckets["ai_smell"].append(
                FailureReason(
                    dimension="ai_smell",
                    check_id="AI_08",
                    severity="critical",
                    message="Placeholder/generation-failed content in question",
                    question_ids=[qid],
                    points_deducted=0.25,
                )
            )


def _run_curriculum_checks(
    worksheet: dict,
    questions: list[dict],
    subject: str,
    topic: str,
    buckets: dict[str, list[FailureReason]],
) -> None:
    """Curriculum alignment checks on worksheet-level fields."""
    # CUR_01: learning_objectives present
    if not worksheet.get("learning_objectives"):
        buckets["curriculum"].append(
            FailureReason(
                dimension="curriculum",
                check_id="CUR_01",
                severity="major",
                message="No learning objectives provided",
                points_deducted=0.20,
            )
        )

    # CUR_02: chapter_ref present
    if not worksheet.get("chapter_ref"):
        buckets["curriculum"].append(
            FailureReason(
                dimension="curriculum",
                check_id="CUR_02",
                severity="major",
                message="No NCERT chapter reference",
                points_deducted=0.20,
            )
        )

    # CUR_06: skill_focus present
    if not worksheet.get("skill_focus"):
        buckets["curriculum"].append(
            FailureReason(
                dimension="curriculum",
                check_id="CUR_06",
                severity="minor",
                message="No skill_focus provided",
                points_deducted=0.05,
            )
        )

    # CUR_05B: Word count violations per grade limit
    grade_match = re.search(r"\d+", worksheet.get("grade", "3"))
    grade_num = int(grade_match.group()) if grade_match else 3
    word_limit = 15 if grade_num <= 2 else 25
    for q in questions:
        text = q.get("text", q.get("question_text", ""))
        wc = len(text.split())
        if wc > word_limit * 1.5:
            buckets["curriculum"].append(
                FailureReason(
                    dimension="curriculum",
                    check_id="CUR_05B",
                    severity="major",
                    message=f"Question has {wc} words (limit {word_limit})",
                    question_ids=[q.get("id", "?")],
                    points_deducted=0.10,
                )
            )

    # CUR_03: Skill tags valid per topic profile
    if topic:
        try:
            from app.data.topic_profiles import get_topic_profile

            profile = get_topic_profile(topic, subject or None)
            if profile:
                valid_tags = set(profile.get("allowed_skill_tags", []))
                if valid_tags:
                    for q in questions:
                        tag = q.get("skill_tag", "")
                        if tag and tag not in valid_tags:
                            buckets["curriculum"].append(
                                FailureReason(
                                    dimension="curriculum",
                                    check_id="CUR_03",
                                    severity="minor",
                                    message=f"Invalid skill tag: {tag}",
                                    question_ids=[q.get("id", "?")],
                                    points_deducted=0.10,
                                )
                            )
        except Exception as exc:
            logger.debug("topic_profile_check_skipped", error=str(exc))


def _run_pedagogical_checks(
    worksheet: dict,
    questions: list[dict],
    buckets: dict[str, list[FailureReason]],
) -> None:
    """Pedagogical design checks not covered by OutputValidator."""
    if not questions:
        return
    n = len(questions)

    # PED_01: Role distribution — need ≥3 roles for 10+ Q worksheets
    expected_roles = {"recognition", "representation", "application", "error_detection", "thinking"}
    present_roles = {q.get("role", "") for q in questions} & expected_roles
    if n >= 10 and len(present_roles) < 3:
        buckets["pedagogical"].append(
            FailureReason(
                dimension="pedagogical",
                check_id="PED_01",
                severity="major",
                message=f"Only {len(present_roles)} role types present (need ≥3 for {n} questions)",
                points_deducted=0.25,
            )
        )

    # PED_05: Must have error_detection or thinking for 10+ Q worksheets
    has_higher = any(q.get("role") in ("error_detection", "thinking") for q in questions)
    if n >= 10 and not has_higher:
        buckets["pedagogical"].append(
            FailureReason(
                dimension="pedagogical",
                check_id="PED_05",
                severity="minor",
                message="No error_detection or thinking questions in 10+ worksheet",
                points_deducted=0.10,
            )
        )

    # PED_06: Hint coverage — ≥50% should have hints
    hints = sum(1 for q in questions if q.get("hint"))
    if n >= 5 and hints / n < 0.5:
        buckets["pedagogical"].append(
            FailureReason(
                dimension="pedagogical",
                check_id="PED_06",
                severity="minor",
                message=f"Only {hints}/{n} questions have hints (need ≥50%)",
                points_deducted=0.10,
            )
        )

    # PED_04: Skill tag diversity — ≥2 distinct tags for 10+ Q
    tags = {q.get("skill_tag", "") for q in questions} - {"", None}
    if n >= 10 and len(tags) < 2:
        buckets["pedagogical"].append(
            FailureReason(
                dimension="pedagogical",
                check_id="PED_04",
                severity="major",
                message=f"Only {len(tags)} distinct skill tag(s) (need ≥2 for {n} questions)",
                points_deducted=0.15,
            )
        )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def score_worksheet(
    worksheet: dict,
    *,
    expected_count: int | None = None,
    export_threshold: int | None = None,
) -> QualityScore:
    """
    Score a worksheet dict against all quality standards.

    Args:
        worksheet: Dict with keys: title, grade, subject, topic, questions, etc.
        expected_count: Expected question count (defaults to len(questions)).
        export_threshold: Override WORKSHEET_EXPORT_MIN_SCORE.

    Returns:
        QualityScore with total 0-100 and per-dimension breakdowns.
    """
    questions = worksheet.get("questions", [])
    grade_str = worksheet.get("grade", "Class 3")
    subject = worksheet.get("subject", "")
    topic = worksheet.get("topic", "")

    # Parse grade number (reserved for future grade-aware checks)
    match = re.search(r"\d+", grade_str)
    _grade_num = int(match.group()) if match else 3  # noqa: F841

    if expected_count is None:
        expected_count = len(questions)

    threshold = export_threshold if export_threshold is not None else _get_export_threshold()

    # Normalize question dicts
    q_dicts: list[dict] = []
    for q in questions:
        if hasattr(q, "model_dump"):
            q_dicts.append(q.model_dump())
        elif isinstance(q, dict):
            q_dicts.append(q)

    # Initialize dimension failure buckets
    buckets: dict[str, list[FailureReason]] = {dim: [] for dim in _DIMENSION_WEIGHTS}

    # Step 1: Run OutputValidator once, classify errors
    try:
        from app.services.output_validator import get_validator

        validator = get_validator()
        _is_valid, ov_errors = validator.validate_worksheet(
            {"questions": q_dicts},
            grade=grade_str,
            subject=subject,
            topic=topic,
            num_questions=expected_count,
        )
        _classify_ov_errors(ov_errors, buckets)
    except Exception as exc:
        logger.warning("quality_scorer: OutputValidator call failed: %s", exc)

    # Step 2: Run supplementary checks
    _run_content_checks(q_dicts, subject, buckets)
    _run_ai_smell_checks(q_dicts, buckets)
    _run_curriculum_checks(worksheet, q_dicts, subject, topic, buckets)
    _run_pedagogical_checks(worksheet, q_dicts, buckets)

    # Step 3: Compute dimension scores
    dimensions: dict[str, DimensionResult] = {}
    for dim_name, weight in _DIMENSION_WEIGHTS.items():
        failures = buckets[dim_name]
        total_deduction = min(1.0, sum(f.points_deducted for f in failures))
        raw_score = max(0.0, 1.0 - total_deduction)
        weighted = round(raw_score * weight, 2)
        dimensions[dim_name] = DimensionResult(
            name=dim_name,
            weight=weight,
            raw_score=round(raw_score, 4),
            weighted_score=weighted,
            failures=failures,
        )

    # Step 4: Compute total
    total = round(sum(d.weighted_score for d in dimensions.values()), 1)
    all_failures = [f for fs in buckets.values() for f in fs]
    ai_smell_flags = buckets.get("ai_smell", [])

    return QualityScore(
        total_score=total,
        dimensions=dimensions,
        failures=all_failures,
        export_allowed=total >= threshold,
        export_threshold=threshold,
        ai_smell_flags=ai_smell_flags,
        question_count=len(q_dicts),
        grade=grade_str,
        subject=subject,
    )
