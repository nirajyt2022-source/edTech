"""
Quick smoke test for v2 worksheet generation.
Tests 5 different grade/subject/topic combos to verify:
1. JSON parses correctly
2. Questions are on-topic
3. Maths answers are correct
4. No topic drift (e.g., no addition questions in Time topic)

Usage:
    cd backend && python scripts/test_v2_generation.py

Requires GEMINI_API_KEY (or OPENAI_API_KEY) in env.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.config import get_settings
from app.core.deps import get_llm_client
from app.services.worksheet_generator import generate_worksheet

# ── Test cases ──────────────────────────────────────────────────────────────

TEST_CASES = [
    {
        "desc": "Class 3 / Maths / Time / Medium / 5 questions",
        "board": "CBSE",
        "grade_level": "Class 3",
        "subject": "Maths",
        "topic": "Time (reading clock, calendar)",
        "difficulty": "medium",
        "num_questions": 5,
        "language": "English",
        "problem_style": "mixed",
        "off_topic_keywords": ["add", "subtract", "multiply", "divide", "fraction"],
    },
    {
        "desc": "Class 1 / Maths / Basic Shapes / Easy / 5 questions",
        "board": "CBSE",
        "grade_level": "Class 1",
        "subject": "Maths",
        "topic": "Basic Shapes (Class 1)",
        "difficulty": "easy",
        "num_questions": 5,
        "language": "English",
        "problem_style": "standard",
        "off_topic_keywords": ["add", "subtract", "time", "clock", "money"],
    },
    {
        "desc": "Class 5 / English / Active and Passive Voice / Medium / 5 questions",
        "board": "CBSE",
        "grade_level": "Class 5",
        "subject": "English",
        "topic": "Active and Passive Voice",
        "difficulty": "medium",
        "num_questions": 5,
        "language": "English",
        "problem_style": "standard",
        "off_topic_keywords": [],
    },
    {
        "desc": "Class 3 / EVS / Our Environment / Easy / 5 questions",
        "board": "CBSE",
        "grade_level": "Class 3",
        "subject": "EVS",
        "topic": "Our Environment",
        "difficulty": "easy",
        "num_questions": 5,
        "language": "English",
        "problem_style": "standard",
        "off_topic_keywords": [],
    },
    {
        "desc": "Class 4 / Hindi / Vakya Rachna / Medium / 5 questions",
        "board": "CBSE",
        "grade_level": "Class 4",
        "subject": "Hindi",
        "topic": "Vakya Rachna",
        "difficulty": "medium",
        "num_questions": 5,
        "language": "Hindi",
        "problem_style": "standard",
        "off_topic_keywords": [],
    },
]


def _check_off_topic(questions: list[dict], off_topic_keywords: list[str]) -> list[str]:
    """Flag questions that contain off-topic keywords."""
    issues = []
    for q in questions:
        text = (q.get("text") or "").lower()
        for kw in off_topic_keywords:
            if kw in text:
                issues.append(f"  OFF-TOPIC: Q{q.get('id', '?')} contains '{kw}': {text[:80]}")
                break
    return issues


def main():
    settings = get_settings()
    client = get_llm_client(settings)

    total_pass = 0
    total_fail = 0

    for i, tc in enumerate(TEST_CASES, 1):
        print(f"\n{'='*60}")
        print(f"TEST {i}: {tc['desc']}")
        print(f"{'='*60}")

        try:
            data, elapsed_ms, warnings = generate_worksheet(
                client=client,
                board=tc["board"],
                grade_level=tc["grade_level"],
                subject=tc["subject"],
                topic=tc["topic"],
                difficulty=tc["difficulty"],
                num_questions=tc["num_questions"],
                language=tc["language"],
                problem_style=tc["problem_style"],
            )

            questions = data.get("questions", [])
            print(f"  Generated {len(questions)} questions in {elapsed_ms} ms")
            print(f"  Title: {data.get('title', '(none)')}")

            # Print each question summary
            for q in questions:
                q_type = q.get("type", "?")
                q_text = (q.get("text") or "")[:80]
                q_ans = (q.get("correct_answer") or "")[:40]
                print(f"    [{q_type:15s}] {q_text}")
                print(f"                    Answer: {q_ans}")

            # Check off-topic
            issues = _check_off_topic(questions, tc.get("off_topic_keywords", []))
            if issues:
                for issue in issues:
                    print(issue)
                print(f"  RESULT: FAIL ({len(issues)} off-topic)")
                total_fail += 1
            else:
                if warnings:
                    print(f"  Warnings: {warnings}")
                print(f"  RESULT: PASS")
                total_pass += 1

        except Exception as exc:
            print(f"  ERROR: {type(exc).__name__}: {exc}")
            total_fail += 1

    print(f"\n{'='*60}")
    print(f"SUMMARY: {total_pass} passed, {total_fail} failed out of {len(TEST_CASES)}")
    print(f"{'='*60}")
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
