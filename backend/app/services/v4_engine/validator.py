"""V4 Validator — post-generation quality checks.

Validates the LLM output against structural and pedagogical rules.
Returns a clean result with issues list and pass/fail status.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .schema import WorksheetV4

logger = logging.getLogger(__name__)

VALID_QUESTION_TYPES = {"MCQ", "True/False", "FillBlank", "ShortAnswer", "ErrorDetection", "WordProblem"}
VALID_DIFFICULTIES = {"Easy", "Medium", "Hard"}


@dataclass
class ValidationResult:
    passed: bool = True
    issues: list[str] = field(default_factory=list)
    auto_fixed: list[str] = field(default_factory=list)


def validate_worksheet(worksheet: WorksheetV4, expected_count: int) -> ValidationResult:
    """Validate a V4 worksheet and auto-fix minor issues where possible."""
    result = ValidationResult()

    # 1. Question count
    actual = len(worksheet.questions)
    if actual != expected_count:
        result.issues.append(f"Expected {expected_count} questions, got {actual}")
        if actual < expected_count:
            result.passed = False

    # 2. Per-question checks
    seen_texts: set[str] = set()
    for q in worksheet.questions:
        prefix = f"Q{q.id}"

        # Question type validity
        if q.question_type not in VALID_QUESTION_TYPES:
            result.issues.append(f"{prefix}: Invalid question_type '{q.question_type}'")

        # Difficulty validity
        if q.difficulty not in VALID_DIFFICULTIES:
            result.issues.append(f"{prefix}: Invalid difficulty '{q.difficulty}'")

        # Empty text
        if not q.text or len(q.text.strip()) < 5:
            result.issues.append(f"{prefix}: Question text is empty or too short")
            result.passed = False

        # Empty answer
        if not q.answer or len(q.answer.strip()) == 0:
            result.issues.append(f"{prefix}: Answer is empty")
            result.passed = False

        # Empty explanation
        if not q.explanation or len(q.explanation.strip()) < 5:
            result.issues.append(f"{prefix}: Explanation is empty or too short")

        # MCQ must have exactly 4 options
        if q.question_type == "MCQ":
            if not q.options or len(q.options) < 4:
                result.issues.append(f"{prefix}: MCQ must have 4 options, got {len(q.options) if q.options else 0}")
                result.passed = False
            elif q.answer not in q.options:
                result.issues.append(f"{prefix}: MCQ answer '{q.answer}' not in options")
                result.passed = False

        # True/False answer must be "True" or "False"
        if q.question_type == "True/False":
            if q.answer not in ("True", "False"):
                result.issues.append(f"{prefix}: True/False answer must be 'True' or 'False', got '{q.answer}'")

        # FillBlank must have blank marker
        if q.question_type == "FillBlank":
            if "______" not in q.text and "____" not in q.text and "___" not in q.text:
                result.issues.append(f"{prefix}: FillBlank question missing blank marker (______)")

        # Duplicate detection
        text_normalized = q.text.strip().lower()[:80]
        if text_normalized in seen_texts:
            result.issues.append(f"{prefix}: Duplicate question text detected")
        seen_texts.add(text_normalized)

        # Learning goal tag present
        if not q.learning_goal_tag or len(q.learning_goal_tag.strip()) < 3:
            result.issues.append(f"{prefix}: Missing or too-short learning_goal_tag")

    # 3. Worksheet-level checks
    if not worksheet.learning_goals:
        result.issues.append("Worksheet has no learning_goals")

    if not worksheet.parent_guide or len(worksheet.parent_guide.strip()) < 10:
        result.issues.append("parent_guide is missing or too short")

    if not worksheet.common_mistake or len(worksheet.common_mistake.strip()) < 10:
        result.issues.append("common_mistake is missing or too short")

    if result.issues:
        logger.info("[v4_validator] %d issues found: %s", len(result.issues), result.issues[:5])

    return result
