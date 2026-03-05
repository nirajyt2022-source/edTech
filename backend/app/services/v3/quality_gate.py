"""Runtime quality gate — runs structural checks on every worksheet before shipping.

Catches:
- skill=general when a profile should exist
- Wrong answers (maths)
- Missing required fields
- True/False format violations
- Age-inappropriate content indicators

If critical checks fail, generate.py retries with the resolved topic name.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class GateResult:
    passed: bool
    issues: list[str]
    severity: str  # "ok" | "warning" | "blocked"


def check_worksheet(
    worksheet: dict,
    slots: list,
    topic: str,
    subject: str,
    grade_level: str,
) -> GateResult:
    """Run structural quality checks on a generated worksheet.

    Returns GateResult with pass/fail and list of issues.
    Critical failures (P0) → blocked.
    Warnings (P1) → passed with warnings.
    """
    issues: list[str] = []
    critical = False

    questions = worksheet.get("questions", [])
    grade_match = re.search(r"\d+", str(grade_level))
    grade_num = int(grade_match.group()) if grade_match else 3

    # === CHECK 1: Has questions ===
    if len(questions) < 5:
        issues.append(f"[CRITICAL] Only {len(questions)} questions generated (minimum 5)")
        critical = True

    # === CHECK 2: All questions have text ===
    empty_count = sum(1 for q in questions if not q.get("text") or len(q.get("text", "")) < 5)
    if empty_count > 0:
        issues.append(f"[CRITICAL] {empty_count} questions have empty/short text")
        critical = True

    # === CHECK 3: Skill tags are not all 'general' when profile exists ===
    if slots:
        all_general = all(getattr(s, "skill_tag", "general") == "general" for s in slots)
        if all_general:
            try:
                from app.data.topic_lookup import resolve_topic

                g_match = re.search(r"\d+", str(grade_level))
                grade = int(g_match.group()) if g_match else None
                resolved = resolve_topic(topic, grade)
                if resolved:
                    issues.append(
                        f"[WARNING] All skills are 'general' but profile exists as '{resolved}' — name mismatch"
                    )
            except ImportError:
                pass

    # === CHECK 4: Maths answers are pre-computed where expected ===
    is_maths = subject.lower() in ("maths", "mathematics", "math")
    if is_maths and slots:
        has_arithmetic = any(kw in topic.lower() for kw in ["addition", "subtraction", "multiplication", "division"])
        if has_arithmetic:
            slots_with_numbers = sum(1 for s in slots if getattr(s, "numbers", None))
            if slots_with_numbers == 0:
                issues.append("[WARNING] Arithmetic topic has 0 pre-computed numbers")

    # === CHECK 5: True/False answers are "True" or "False" ===
    for q in questions:
        if q.get("type") == "true_false":
            ca = str(q.get("correct_answer", ""))
            if ca not in ("True", "False"):
                issues.append(f"[CRITICAL] {q.get('id', '?')}: T/F answer is '{ca}', must be True/False")
                critical = True

    # === CHECK 6: MCQ has options ===
    for q in questions:
        if q.get("type") == "mcq":
            opts = q.get("options", [])
            if not opts or len(opts) < 3:
                issues.append(f"[CRITICAL] {q.get('id', '?')}: MCQ has {len(opts) if opts else 0} options (need 3+)")
                critical = True

    # === CHECK 7: MCQ correct answer is in options ===
    for q in questions:
        if q.get("type") == "mcq" and q.get("options") and q.get("correct_answer"):
            if str(q["correct_answer"]) not in [str(o) for o in q["options"]]:
                issues.append(f"[CRITICAL] {q.get('id', '?')}: correct_answer not in options")
                critical = True

    # === CHECK 8: Maths answers are numerically correct ===
    if is_maths and slots:
        for q, s in zip(questions, slots):
            nums = getattr(s, "numbers", None)
            if nums and nums.get("answer") is not None:
                expected = str(nums["answer"])
                actual = str(q.get("correct_answer", ""))
                if q.get("type") == "true_false":
                    continue
                if actual != expected:
                    issues.append(f"[CRITICAL] {q.get('id', '?')}: expected answer {expected}, got {actual}")
                    critical = True

    # === CHECK 9: No duplicate questions (exact same text) ===
    texts = [q.get("text", "") for q in questions]
    seen: set[str] = set()
    for i, t in enumerate(texts):
        if t in seen and len(t) > 10:
            issues.append(f"[WARNING] Q{i + 1}: duplicate question text")
        seen.add(t)

    # === CHECK 10: Learning objectives exist and are specific ===
    objectives = worksheet.get("learning_objectives", [])
    if not objectives:
        issues.append("[WARNING] No learning objectives")
    elif len(objectives) == 1 and "Practice and master" in objectives[0]:
        issues.append("[WARNING] Generic fallback learning objective")

    # === CHECK 11: Word count for young grades ===
    if grade_num <= 2:
        long_questions = sum(1 for q in questions if len(q.get("text", "").split()) > 25)
        if long_questions > 3:
            issues.append(f"[WARNING] {long_questions} questions exceed 25 words for Class {grade_num}")

    # Determine severity
    if critical:
        severity = "blocked"
    elif issues:
        severity = "warning"
    else:
        severity = "ok"

    return GateResult(passed=not critical, issues=issues, severity=severity)
