"""
Input sanitization middleware.

Strips dangerous content from request bodies before they reach endpoint handlers.
"""

import logging
import re

from fastapi import HTTPException

logger = logging.getLogger("skolar.sanitize")

# Allowed values for constrained fields
VALID_GRADES = {"Class 1", "Class 2", "Class 3", "Class 4", "Class 5"}
VALID_SUBJECTS = {
    "Maths",
    "Mathematics",
    "English",
    "Hindi",
    "EVS",
    "Science",
    "Computer",
    "Computer Science",
    "GK",
    "General Knowledge",
    "Moral Science",
    "Health & PE",
    "Urdu",
}
VALID_DIFFICULTIES = {"easy", "medium", "hard"}
VALID_LANGUAGES = {"English", "Hindi"}
VALID_PROBLEM_STYLES = {"standard", "visual", "mixed"}

# Max field lengths
MAX_LENGTHS = {
    "name": 100,
    "topic": 200,
    "custom_instructions": 1000,
    "question": 2000,
    "notes": 500,
    "board": 50,
    "grade": 20,
    "grade_level": 20,
    "subject": 50,
    "language": 20,
}

# HTML/script tag pattern
_DANGEROUS_PATTERN = re.compile(
    r"<\s*script|<\s*iframe|<\s*object|<\s*embed|<\s*form|"
    r"javascript:|data:text/html|on\w+\s*=",
    re.IGNORECASE,
)

# Prompt injection patterns (shared with ask_skolar.py)
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above|system)\s+(instructions|rules|prompts)",
    r"you\s+are\s+(now|no\s+longer)\s+",
    r"act\s+as\s+(an?\s+)?(unrestricted|unfiltered|uncensored)",
    r"(system|admin|developer)\s*:\s*",
    r"override\s+(all\s+)?(rules|safety|restrictions|guardrails)",
    r"jailbreak",
    r"DAN\s+mode",
    r"do\s+anything\s+now",
    r"pretend\s+(you\s+)?(are|have)\s+no\s+(rules|restrictions|limits)",
    r"forget\s+(all\s+)?(your\s+)?(rules|instructions|training)",
    r"new\s+instructions?\s*:",
    r"from\s+now\s+on\s+(you|ignore)",
]
INJECTION_RE = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE)


def sanitize_string(value: str, field_name: str = "") -> str:
    """Remove dangerous content from a string value."""
    if not isinstance(value, str):
        return value

    # Check max length
    max_len = MAX_LENGTHS.get(field_name, 5000)
    if len(value) > max_len:
        logger.warning(
            "Input truncated",
            extra={"field": field_name, "original_len": len(value), "max": max_len},
        )
        value = value[:max_len]

    # Strip null bytes and control characters (except newline, tab)
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value)

    # Check for dangerous patterns
    if _DANGEROUS_PATTERN.search(value):
        logger.warning(
            "Dangerous input detected and stripped",
            extra={"field": field_name, "preview": value[:100]},
        )
        # Strip HTML tags entirely
        value = re.sub(r"<[^>]+>", "", value)

    # Check for prompt injection in AI-facing fields
    if field_name in ("custom_instructions", "question") and INJECTION_RE.search(value):
        logger.warning(
            "Prompt injection detected and stripped",
            extra={"field": field_name, "preview": value[:100]},
        )
        value = INJECTION_RE.sub("", value).strip()

    return value.strip()


def validate_grade(grade: str) -> str:
    """Validate grade is in allowed set."""
    grade = grade.strip()
    if grade not in VALID_GRADES:
        raise HTTPException(400, f"Invalid grade: {grade}. Must be one of: {', '.join(sorted(VALID_GRADES))}")
    return grade


def validate_subject(subject: str) -> str:
    """Validate subject is in allowed set."""
    subject = subject.strip()
    if subject not in VALID_SUBJECTS:
        raise HTTPException(400, f"Invalid subject: {subject}")
    return subject


def validate_difficulty(difficulty: str) -> str:
    """Validate difficulty level."""
    difficulty = difficulty.strip().lower()
    if difficulty not in VALID_DIFFICULTIES:
        raise HTTPException(400, f"Invalid difficulty: {difficulty}")
    return difficulty


def validate_file_upload(content_type: str, size_bytes: int, max_mb: int = 10) -> None:
    """Validate uploaded file type and size."""
    allowed_types = {
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/webp",
        "image/gif",
        "application/pdf",
        "text/plain",
    }
    if content_type not in allowed_types:
        raise HTTPException(
            400,
            f"Invalid file type: {content_type}. Allowed: {', '.join(sorted(allowed_types))}",
        )
    max_bytes = max_mb * 1024 * 1024
    if size_bytes > max_bytes:
        raise HTTPException(400, f"File too large. Maximum: {max_mb}MB")
