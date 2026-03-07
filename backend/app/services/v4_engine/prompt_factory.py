"""V4 Prompt Factory — builds rich, curriculum-grounded prompts for Gemini.

Uses the curriculum map (LEARNING_OBJECTIVES, TOPIC_PROFILES) to inject
specific learning goals, skill tags, and pedagogical context into every prompt.
"""

from __future__ import annotations

import random
import re
import string

from app.data.learning_objectives import LEARNING_OBJECTIVES
from app.data.topic_profiles import get_topic_profile

# ---------------------------------------------------------------------------
# Question type distribution by difficulty
# ---------------------------------------------------------------------------
DISTRIBUTION = {
    "easy": {
        "MCQ": 0.40,
        "True/False": 0.20,
        "FillBlank": 0.20,
        "ShortAnswer": 0.10,
        "ErrorDetection": 0.10,
    },
    "medium": {
        "MCQ": 0.20,
        "FillBlank": 0.20,
        "ShortAnswer": 0.20,
        "WordProblem": 0.20,
        "ErrorDetection": 0.10,
        "True/False": 0.10,
    },
    "hard": {
        "MCQ": 0.10,
        "ShortAnswer": 0.20,
        "WordProblem": 0.30,
        "ErrorDetection": 0.20,
        "FillBlank": 0.10,
        "True/False": 0.10,
    },
}


def _compute_type_counts(num_questions: int, difficulty: str) -> dict[str, int]:
    """Compute how many questions of each type to generate."""
    dist = DISTRIBUTION.get(difficulty, DISTRIBUTION["medium"])
    counts: dict[str, int] = {}

    # Allocate proportionally
    for q_type, ratio in dist.items():
        count = max(0, round(num_questions * ratio))
        counts[q_type] = count

    # Fix rounding errors
    total = sum(counts.values())
    if total < num_questions:
        # Add to the largest bucket
        biggest = max(counts, key=counts.get)
        counts[biggest] += num_questions - total
    elif total > num_questions:
        # Remove from the largest bucket
        biggest = max(counts, key=counts.get)
        counts[biggest] -= total - num_questions

    # Remove zero-count types
    return {k: v for k, v in counts.items() if v > 0}


def _get_difficulty_spread(num_questions: int, difficulty: str) -> str:
    """Return a difficulty spread instruction."""
    if difficulty == "easy":
        return f"Difficulty spread: {round(num_questions * 0.6)} Easy, {round(num_questions * 0.3)} Medium, {num_questions - round(num_questions * 0.6) - round(num_questions * 0.3)} Hard"
    elif difficulty == "hard":
        return f"Difficulty spread: {round(num_questions * 0.2)} Easy, {round(num_questions * 0.3)} Medium, {num_questions - round(num_questions * 0.2) - round(num_questions * 0.3)} Hard"
    else:
        return f"Difficulty spread: {round(num_questions * 0.3)} Easy, {round(num_questions * 0.4)} Medium, {num_questions - round(num_questions * 0.3) - round(num_questions * 0.4)} Hard"


def build_system_prompt() -> str:
    """Build the system prompt for worksheet generation."""
    return """You are a Senior CBSE Curriculum Expert creating worksheets for Indian primary school students (Classes 1-5).

QUALITY STANDARDS:
1. Every question must be factually correct and age-appropriate.
2. Use Indian context: Indian names (Aarav, Priya, Meera, Rohan, Ananya, Kabir), Indian currency (₹, Rupees), Indian cities, festivals, and units (Lakhs/Crores for Class 4-5).
3. NEVER start two questions with the same word.
4. For MCQ: provide exactly 4 options. The correct answer MUST be one of the options.
5. For FillBlank: include exactly one "______" in the question text.
6. For True/False: the answer must be exactly "True" or "False".
7. For ErrorDetection: present a statement with a deliberate mistake that tests a common misconception for the age group. The answer should explain the error.
8. For WordProblem: tell a mini-story using Indian context, don't just state bare numbers.
9. Explanations must be parent-friendly — explain HOW to solve it, not just the answer.
10. Each question's learning_goal_tag must reference one of the provided learning goals.
11. Vary scenarios, contexts, and phrasing. Never use the same setup twice.
12. For Maths: double-check all arithmetic. Show your working mentally before writing the answer.
13. Keep language simple and age-appropriate for the given class level.

Respond with ONLY valid JSON matching the required schema. No markdown fences, no extra text."""


def build_user_prompt(
    board: str,
    grade_level: str,
    subject: str,
    topic: str,
    difficulty: str,
    num_questions: int,
    language: str,
    custom_instructions: str | None = None,
) -> str:
    """Build the user prompt with curriculum context and generation instructions."""
    # Extract class number
    match = re.search(r"\d+", str(grade_level))
    grade_num = int(match.group()) if match else 3

    # Get learning objectives
    learning_goals = LEARNING_OBJECTIVES.get(topic, [])
    if isinstance(learning_goals, str):
        learning_goals = [learning_goals]
    if not learning_goals:
        # Try partial match
        for key, val in LEARNING_OBJECTIVES.items():
            if key.lower() in topic.lower() or topic.lower() in key.lower():
                learning_goals = val if isinstance(val, list) else [val]
                break

    # Get topic profile for skill tags and disallowed keywords
    profile = get_topic_profile(topic, subject, grade_level)
    skill_tags = []
    disallowed = []
    if profile:
        skill_tags = profile.get("allowed_skill_tags", [])
        disallowed = profile.get("disallowed_keywords", [])

    # Compute question type distribution
    type_counts = _compute_type_counts(num_questions, difficulty)
    type_spec = ", ".join(f"{count} {qtype}" for qtype, count in type_counts.items())

    # Difficulty spread
    diff_spread = _get_difficulty_spread(num_questions, difficulty)

    # Variation seed
    seed = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))

    # Age-appropriate language guidance
    if grade_num <= 2:
        lang_guide = "Use ONLY words a 6-7 year old knows. Keep sentences under 15 words. No complex vocabulary."
    elif grade_num <= 3:
        lang_guide = "Use simple words. Keep sentences under 20 words. Avoid technical terms."
    elif grade_num <= 4:
        lang_guide = "Use grade-appropriate vocabulary. Sentences can be up to 25 words."
    else:
        lang_guide = "Use Class 5 level vocabulary. Sentences can be up to 30 words."

    # Maths-specific guidance
    is_maths = subject.lower() in ("maths", "math", "mathematics")
    maths_note = ""
    if is_maths:
        if grade_num <= 2:
            maths_note = "Numbers should be within 100 for Class 1, within 1000 for Class 2. Use objects children can visualize (apples, marbles, pencils)."
        elif grade_num == 3:
            maths_note = "Numbers can go up to 9,999. Use real-world scenarios (shopping, sharing sweets)."
        elif grade_num == 4:
            maths_note = "Numbers can go up to 1,00,000. Use Indian number system (lakhs). Include multi-step problems."
        else:
            maths_note = "Numbers can go up to 10,00,000. Use Indian number system. Include multi-step and cross-concept problems."

    parts = [
        f"GENERATION REQUEST (Variation: {seed})",
        f"Board: {board} | Class: {grade_num} | Subject: {subject}",
        f"Topic: {topic}",
        f"Language: {language}",
        f"Total questions: {num_questions}",
        f"Question type distribution: {type_spec}",
        diff_spread,
        "",
    ]

    if learning_goals:
        parts.append("LEARNING GOALS (tag each question with one of these):")
        for i, goal in enumerate(learning_goals, 1):
            parts.append(f"  {i}. {goal}")
        parts.append("")

    if skill_tags:
        parts.append(f"SKILL TAGS to use: {', '.join(skill_tags)}")
        parts.append("")

    if disallowed:
        parts.append(f"DISALLOWED KEYWORDS (never use these): {', '.join(disallowed)}")
        parts.append("")

    parts.append(f"LANGUAGE LEVEL: {lang_guide}")

    if maths_note:
        parts.append(f"MATHS GUIDANCE: {maths_note}")

    if custom_instructions:
        parts.append(f"\nCUSTOM INSTRUCTIONS: {custom_instructions}")

    parts.append(
        "\nIMPORTANT: Generate EXACTLY the requested number of questions. "
        "Every question must have a non-empty answer and explanation. "
        "For MCQ, options must be a 4-element array including the correct answer."
    )

    return "\n".join(parts)
