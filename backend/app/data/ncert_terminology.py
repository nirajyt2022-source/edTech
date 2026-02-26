"""
NCERT preferred terminology mapping.

Maps commonly used informal/Western terms to NCERT-preferred equivalents,
filtered by subject and grade. Injected into the LLM prompt so generated
content uses the exact vocabulary students see in their textbooks.
"""

from __future__ import annotations

NCERT_TERMINOLOGY: dict[str, dict[str, dict]] = {
    "Maths": {
        "carrying": {"preferred": "regrouping", "grades": [1, 2, 3, 4, 5]},
        "borrowing": {"preferred": "regrouping", "grades": [1, 2, 3, 4, 5]},
        "times table": {"preferred": "multiplication table", "grades": [2, 3, 4, 5]},
        "take away": {"preferred": "subtract", "grades": [3, 4, 5]},
        "reduce": {"preferred": "simplify", "grades": [4, 5]},
    },
    "English": {
        "grammar rules": {"preferred": "language patterns", "grades": [1, 2, 3]},
    },
    "Science": {
        "experiment": {"preferred": "activity", "grades": [1, 2, 3]},
    },
}


def get_terminology_instructions(subject: str, grade: int) -> str:
    """Build a compact terminology instruction block.

    Returns '' if no terms apply for the given subject and grade.
    """
    subject_terms = NCERT_TERMINOLOGY.get(subject, {})
    if not subject_terms:
        return ""

    lines: list[str] = []
    for informal, info in subject_terms.items():
        if grade in info["grades"]:
            lines.append(f'  - Use "{info["preferred"]}" instead of "{informal}"')

    if not lines:
        return ""

    return "NCERT TERMINOLOGY (use exact textbook vocabulary):\n" + "\n".join(lines)
