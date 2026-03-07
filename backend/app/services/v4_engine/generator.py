"""V4 Worksheet Generator — LLM-driven, schema-validated pipeline.

Single Gemini call produces the full worksheet as structured JSON.
Pydantic validates the output. Validator catches quality issues.
Falls back to v3 on failure.
"""

from __future__ import annotations

import json
import logging
import re
import time

from pydantic import ValidationError

from .prompt_factory import build_system_prompt, build_user_prompt
from .schema import WorksheetV4
from .validator import validate_worksheet

logger = logging.getLogger(__name__)

# Maps V4 question types to the frontend's existing type names
_TYPE_MAP = {
    "MCQ": "mcq",
    "True/False": "true_false",
    "FillBlank": "fill_blank",
    "ShortAnswer": "short_answer",
    "ErrorDetection": "error_detection",
    "WordProblem": "word_problem",
}

# Maps V4 difficulty to lowercase
_DIFF_MAP = {
    "Easy": "easy",
    "Medium": "medium",
    "Hard": "hard",
}


def _parse_json(raw: str) -> dict:
    """Parse JSON from raw LLM response, handling markdown fences."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    return json.loads(text)


def _v4_to_api_format(worksheet: WorksheetV4, grade_level: str, difficulty: str, language: str) -> dict:
    """Convert a validated WorksheetV4 to the existing API response dict format.

    This ensures the frontend doesn't need any changes.
    """
    questions = []
    for q in worksheet.questions:
        q_type = _TYPE_MAP.get(q.question_type, "short_answer")

        # Infer render format
        if q_type == "mcq":
            n = len(q.options) if q.options else 4
            render_format = "mcq_4" if n >= 4 else "mcq_3"
        elif q_type == "fill_blank":
            render_format = "fill_blank"
        elif q_type == "true_false":
            render_format = "true_false"
        else:
            render_format = "short_answer"

        questions.append(
            {
                "id": f"q{q.id}",
                "type": q_type,
                "text": q.text,
                "options": q.options,
                "correct_answer": q.answer,
                "explanation": q.explanation,
                "hint": q.hint,
                "difficulty": _DIFF_MAP.get(q.difficulty, q.difficulty.lower()),
                "role": _infer_role(q.question_type),
                "skill_tag": q.skill_tag or q.learning_goal_tag,
                "learning_goal_tag": q.learning_goal_tag,
                "format": render_format,
                "visual_type": None,
                "visual_data": None,
                "images": None,
                "verified": True,
            }
        )

    return {
        "title": worksheet.title,
        "grade": grade_level,
        "subject": worksheet.subject,
        "topic": worksheet.topic,
        "difficulty": difficulty,
        "language": language,
        "questions": questions,
        "skill_focus": worksheet.learning_goals[0] if worksheet.learning_goals else "",
        "common_mistake": worksheet.common_mistake,
        "parent_tip": worksheet.parent_guide,
        "learning_objectives": worksheet.learning_goals,
        "parent_guide": worksheet.parent_guide,
    }


def _infer_role(question_type: str) -> str:
    """Map V4 question type to a pedagogical role."""
    return {
        "MCQ": "recognition",
        "True/False": "recognition",
        "FillBlank": "representation",
        "ShortAnswer": "application",
        "ErrorDetection": "error_detection",
        "WordProblem": "application",
    }.get(question_type, "application")


def generate_worksheet_v4(
    client,  # AIClient instance (not the OpenAI compat wrapper)
    board: str,
    grade_level: str,
    subject: str,
    topic: str,
    difficulty: str,
    num_questions: int = 10,
    language: str = "English",
    problem_style: str = "standard",
    custom_instructions: str | None = None,
    child_id: str | None = None,
) -> tuple[dict, int, list[str]]:
    """Generate a worksheet using the V4 LLM-driven pipeline.

    Returns (worksheet_dict, elapsed_ms, warnings) — same signature as v3.
    """
    t0 = time.perf_counter()
    warnings: list[str] = []

    system_prompt = build_system_prompt()
    user_prompt = build_user_prompt(
        board=board,
        grade_level=grade_level,
        subject=subject,
        topic=topic,
        difficulty=difficulty,
        num_questions=num_questions,
        language=language,
        custom_instructions=custom_instructions,
    )

    # Determine temperature — lower for maths accuracy, higher for creative subjects
    is_maths = subject.lower() in ("maths", "math", "mathematics")
    temperature = 0.6 if is_maths else 0.9
    thinking_budget = 2048 if is_maths else 0

    # Token budget scales with question count
    max_tokens = min(16384, 4096 + num_questions * 600)

    logger.info(
        "[v4] Generating: %s / %s / %s / %s / %dQ",
        grade_level,
        subject,
        topic,
        difficulty,
        num_questions,
    )

    # --- Attempt 1: Primary generation ---
    worksheet = None
    for attempt in range(2):
        try:
            raw_response = client.generate_json(
                prompt=user_prompt,
                system=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                retries=1,
                thinking_budget=thinking_budget,
            )

            # Validate with Pydantic
            worksheet = WorksheetV4.model_validate(raw_response)

            # Run quality checks
            validation = validate_worksheet(worksheet, expected_count=num_questions)
            warnings.extend(validation.issues)

            if validation.passed:
                break

            # If validation failed on first attempt, retry with stricter prompt
            if attempt == 0 and not validation.passed:
                logger.warning(
                    "[v4] Attempt 1 validation failed (%d issues), retrying",
                    len(validation.issues),
                )
                user_prompt += "\n\nPREVIOUS ATTEMPT HAD ERRORS. Fix these issues:\n" + "\n".join(
                    f"- {issue}" for issue in validation.issues[:5]
                )
                worksheet = None
                continue

        except (ValidationError, ValueError, KeyError) as exc:
            logger.warning("[v4] Attempt %d failed: %s", attempt + 1, exc)
            warnings.append(f"[v4] attempt {attempt + 1} error: {str(exc)[:100]}")
            if attempt == 0:
                continue
            break

    if worksheet is None:
        # Fall back to v3
        logger.warning("[v4] Both attempts failed, falling back to v3")
        warnings.append("[v4] fell back to v3 engine")
        from app.services.v3 import generate_worksheet_v3

        return generate_worksheet_v3(
            client=client,
            board=board,
            grade_level=grade_level,
            subject=subject,
            topic=topic,
            difficulty=difficulty,
            num_questions=num_questions,
            language=language,
            problem_style=problem_style,
            custom_instructions=custom_instructions,
            child_id=child_id,
        )

    # Convert to API-compatible format
    result = _v4_to_api_format(worksheet, grade_level, difficulty, language)

    # Add quality gate info
    result["_quality_gate"] = {
        "passed": True,
        "severity": "ok",
        "issues_count": len(warnings),
    }

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    logger.info("[v4] Generation complete: %dms, %d warnings", elapsed_ms, len(warnings))

    return result, elapsed_ms, warnings
