"""
Worksheet Generator v2 — simplified prompt-to-Gemini pipeline.

Replaces the 18,000-line slot_engine.py for generation.  Everything else
(PDF export, mastery tracking, auth, subscription, save/load) is untouched.

Architecture:
    build_prompt(params) -> system + user prompt
        -> call_gemini(prompt) -> Gemini 2.5 Flash, temp=0.3, JSON mode
            -> validate(response) -> schema + maths verification + topic drift
                -> return WorksheetGenerationResponse (same shape as v1)
"""
from __future__ import annotations

import json
import logging
import math
import re
import time
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 1A  System Prompt — universal, works for all topics
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an expert CBSE school teacher creating worksheets for Indian primary school students.

RULES:
1. Generate questions ONLY about the given topic. If the topic is "Telling Time", every question must be about time — never about addition, subtraction, or any other topic.
2. All questions must be age-appropriate for the given class level.
3. Follow NCERT/CBSE curriculum standards for the given class and subject.
4. Every question must have a correct answer. For maths, compute the answer precisely.
5. Never repeat the same question pattern. Vary the question formats.
6. Use Indian context (₹ for money, Indian names, Indian festivals, Indian cities, etc.)

DIFFICULTY LEVELS:
- Easy: Single-step, direct recall, recognition. Example for Class 3 Maths Time: "What time does this clock show?" (with a described clock face)
- Medium: Two-step, application, requires some reasoning. Example: "School starts at 8:30 AM. If Priya takes 45 minutes to get ready, what time should she wake up?"
- Hard: Multi-step, word problems, error detection, reasoning. Example: "Rahul says 90 minutes is the same as 1 hour 20 minutes. Is he correct? Explain why."

QUESTION TYPES (use a mix based on what fits the topic):
- mcq: Multiple choice with 4 options (one correct)
- fill_blank: Fill in the blank
- true_false: True or False
- short_answer: Short written answer
- word_problem: Contextual word problem
- error_detection: Find the mistake (for Medium/Hard)

VISUAL TYPES (include when problem_style is "visual" or "mixed"):
- For Maths: number_line, base_ten_blocks, clock_face, fraction_bar, shape_grid, bar_chart, tally_chart
- For English: sentence_diagram, word_web
- For EVS/Science: diagram_label, food_chain, lifecycle
- Only include visual_type and visual_data when the question genuinely needs a visual.
- For "standard" problem_style, minimize visuals.

OUTPUT FORMAT — respond with ONLY this JSON, no other text:
{
  "title": "Worksheet: {topic}",
  "skill_focus": "<one-line summary of the skill being tested>",
  "common_mistake": "<one common mistake students make on this topic>",
  "parent_tip": "<one tip for parents to help their child with this topic>",
  "learning_objectives": ["<objective 1>", "<objective 2>", "<objective 3>"],
  "questions": [
    {
      "id": "q1",
      "type": "<mcq|fill_blank|true_false|short_answer|word_problem|error_detection>",
      "text": "<question text>",
      "options": ["<option A>", "<option B>", "<option C>", "<option D>"] or null,
      "correct_answer": "<the correct answer — MUST be accurate>",
      "explanation": "<brief explanation of how to solve it>",
      "difficulty": "<easy|medium|hard>",
      "hint": "<a helpful hint that does NOT reveal the answer>",
      "visual_type": "<type or null>",
      "visual_data": null
    }
  ]
}
"""

# ---------------------------------------------------------------------------
# 1B  User Prompt Builder
# ---------------------------------------------------------------------------


def build_user_prompt(
    board: str,
    grade_level: str,
    subject: str,
    topic: str,
    difficulty: str,
    num_questions: int,
    language: str,
    problem_style: str = "standard",
    custom_instructions: str | None = None,
) -> str:
    """Build a concise user prompt that reinforces the topic constraint."""
    style_hint = {
        "visual": "visual (include visual elements in most questions)",
        "mixed": "mixed (include some visual questions)",
        "standard": "standard (text-based, minimize visuals)",
    }.get(problem_style, "standard")

    prompt = (
        f"Board: {board}\n"
        f"Class: {grade_level}\n"
        f"Subject: {subject}\n"
        f"Topic: {topic}\n"
        f"Difficulty: {difficulty}\n"
        f"Number of questions: {num_questions}\n"
        f"Language: {language}\n"
        f"Problem style: {style_hint}\n\n"
        f"Generate a worksheet following the system instructions. "
        f'Every single question must be strictly about "{topic}" and nothing else.'
    )

    if custom_instructions:
        prompt += f"\n\nAdditional teacher instructions: {custom_instructions}"

    return prompt


# ---------------------------------------------------------------------------
# 1C  Gemini Caller
# ---------------------------------------------------------------------------


def call_gemini(client, system_prompt: str, user_prompt: str) -> str:
    """Call the LLM via the existing adapter and return raw text."""
    response = client.chat.completions.create(
        model="gemini-2.5-flash",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
        max_tokens=4096,
    )
    return response.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# 1D  Validator
# ---------------------------------------------------------------------------

# Broad topic keywords — NOT 198 profiles, just ~20 categories
_TOPIC_KEYWORDS: dict[str, list[str]] = {
    "time": ["time", "clock", "hour", "minute", "o'clock", "half past", "quarter", "am", "pm", "calendar", "month", "day", "week"],
    "addition": ["add", "sum", "plus", "carry", "total", "+"],
    "subtraction": ["subtract", "minus", "borrow", "difference", "take away", "-"],
    "multiplication": ["multiply", "times", "product", "table", "×"],
    "division": ["divide", "share", "quotient", "remainder", "÷"],
    "fraction": ["fraction", "half", "quarter", "numerator", "denominator", "/"],
    "money": ["money", "coin", "rupee", "₹", "price", "cost", "change", "buy", "sell"],
    "shape": ["shape", "triangle", "circle", "square", "rectangle", "side", "corner", "edge"],
    "measurement": ["measure", "length", "weight", "height", "cm", "metre", "kg", "gram", "litre"],
    "pattern": ["pattern", "sequence", "next", "rule", "repeat"],
    "number": ["number", "count", "digit", "place value", "ones", "tens", "hundreds"],
    "data": ["data", "graph", "chart", "tally", "pictograph", "table"],
    "symmetry": ["symmetry", "symmetric", "line of symmetry", "mirror"],
    "spatial": ["in", "out", "near", "far", "above", "below", "left", "right", "position"],
    "grammar": ["noun", "verb", "pronoun", "adjective", "adverb", "tense", "sentence", "punctuation"],
    "comprehension": ["passage", "read", "comprehension", "paragraph", "story"],
    "vocabulary": ["word", "meaning", "synonym", "antonym", "spelling"],
    "hindi": ["matra", "shabd", "vakya", "kaal", "sangya", "sarvanam", "kriya", "varnamala"],
    "science": ["plant", "animal", "body", "water", "air", "food", "weather", "environment", "habitat", "material", "force", "energy"],
    "evs": ["environment", "family", "community", "shelter", "transport", "safety", "festival", "food", "water"],
}


def _detect_topic_category(topic: str) -> str | None:
    """Return the broad topic category for a given topic string."""
    t_lower = topic.lower()
    for category, keywords in _TOPIC_KEYWORDS.items():
        if any(kw in t_lower for kw in keywords):
            return category
    return None


def _is_question_on_topic(question_text: str, topic_category: str | None) -> bool:
    """Check if a question mentions at least one keyword from the topic category."""
    if not topic_category:
        return True  # unknown category — can't check
    keywords = _TOPIC_KEYWORDS.get(topic_category, [])
    q_lower = question_text.lower()
    return any(kw in q_lower for kw in keywords)


def _verify_maths_answer(question: dict) -> str | None:
    """For simple arithmetic questions, compute the answer and auto-correct if wrong.

    Returns the corrected answer, or None if no correction was needed/possible.
    """
    text = question.get("text", "")
    answer = str(question.get("correct_answer", ""))

    # Try to find a simple arithmetic expression in the question
    # Match patterns like "234 + 567", "45 × 8", "100 - 37", "84 ÷ 4"
    pattern = r"(\d+(?:\.\d+)?)\s*([+\-×÷*/])\s*(\d+(?:\.\d+)?)"
    match = re.search(pattern, text)
    if not match:
        return None

    a_str, op, b_str = match.groups()
    try:
        a, b = float(a_str), float(b_str)
    except ValueError:
        return None

    op_map = {"+": a + b, "-": a - b, "×": a * b, "*": a * b}
    if op in ("÷", "/") and b != 0:
        op_map[op] = a / b

    computed = op_map.get(op)
    if computed is None:
        return None

    # Format: prefer integer if whole number
    if computed == int(computed):
        computed_str = str(int(computed))
    else:
        computed_str = str(round(computed, 2))

    # Check if the LLM answer matches
    try:
        llm_val = float(answer.replace(",", "").strip())
        if math.isclose(llm_val, computed, rel_tol=1e-6):
            return None  # correct — no fix needed
    except (ValueError, TypeError):
        pass

    logger.warning(
        "Maths auto-correct: Q '%s' — LLM said '%s', computed '%s'",
        text[:60], answer, computed_str,
    )
    return computed_str


def validate_response(
    raw_text: str,
    subject: str,
    topic: str,
    num_questions: int,
) -> tuple[dict[str, Any], list[str]]:
    """Validate and repair the LLM response.

    Returns (validated_dict, warnings).
    Raises ValueError if the response is completely unusable.
    """
    warnings: list[str] = []

    # --- JSON parse ---
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        # Try stripping markdown fences
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw_text.strip())
        cleaned = re.sub(r"\s*```$", "", cleaned)
        data = json.loads(cleaned)  # let it raise if still bad

    questions = data.get("questions", [])
    if not questions:
        raise ValueError("LLM returned no questions")

    # --- Schema check ---
    valid_types = {"mcq", "fill_blank", "true_false", "short_answer", "word_problem", "error_detection"}
    for i, q in enumerate(questions):
        qid = q.get("id") or f"q{i + 1}"
        q["id"] = qid

        if "text" not in q or not q["text"]:
            warnings.append(f"{qid}: missing question text")

        if "correct_answer" not in q or q["correct_answer"] is None:
            warnings.append(f"{qid}: missing correct_answer")

        q_type = q.get("type", "short_answer")
        if q_type not in valid_types:
            q["type"] = "short_answer"
            warnings.append(f"{qid}: unknown type '{q_type}', defaulted to short_answer")

        if q_type == "mcq":
            opts = q.get("options") or []
            if len(opts) != 4:
                warnings.append(f"{qid}: MCQ should have 4 options, got {len(opts)}")

    # --- Count check ---
    count_diff = abs(len(questions) - num_questions)
    if count_diff > 1:
        warnings.append(
            f"Requested {num_questions} questions, got {len(questions)}"
        )

    # --- Maths answer verification ---
    if subject.lower() in ("maths", "mathematics", "math"):
        for q in questions:
            correction = _verify_maths_answer(q)
            if correction is not None:
                q["correct_answer"] = correction
                warnings.append(f"{q['id']}: answer auto-corrected to {correction}")

    # --- Topic drift check ---
    topic_cat = _detect_topic_category(topic)
    if topic_cat:
        off_topic_count = sum(
            1 for q in questions
            if not _is_question_on_topic(q.get("text", ""), topic_cat)
        )
        drift_ratio = off_topic_count / max(len(questions), 1)
        if drift_ratio > 0.3:
            warnings.append(
                f"Topic drift: {off_topic_count}/{len(questions)} questions "
                f"appear off-topic for '{topic}' (category: {topic_cat})"
            )

    data["questions"] = questions
    return data, warnings


# ---------------------------------------------------------------------------
# 1E  Generate — single entry-point
# ---------------------------------------------------------------------------


def generate_worksheet(
    client,
    board: str,
    grade_level: str,
    subject: str,
    topic: str,
    difficulty: str,
    num_questions: int = 10,
    language: str = "English",
    problem_style: str = "standard",
    custom_instructions: str | None = None,
) -> tuple[dict[str, Any], int, list[str]]:
    """Generate a validated worksheet via Gemini.

    Returns (worksheet_dict, elapsed_ms, warnings).
    Raises ValueError if generation fails after retries.
    """
    user_prompt = build_user_prompt(
        board=board,
        grade_level=grade_level,
        subject=subject,
        topic=topic,
        difficulty=difficulty,
        num_questions=num_questions,
        language=language,
        problem_style=problem_style,
        custom_instructions=custom_instructions,
    )

    max_attempts = 2
    last_error: Exception | None = None
    all_warnings: list[str] = []

    for attempt in range(1, max_attempts + 1):
        t0 = time.perf_counter()
        try:
            raw = call_gemini(client, SYSTEM_PROMPT, user_prompt)
            data, warnings = validate_response(raw, subject, topic, num_questions)
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            all_warnings.extend(warnings)

            # Check if retry is needed for topic drift
            drift_warnings = [w for w in warnings if "Topic drift" in w]
            if drift_warnings and attempt < max_attempts:
                logger.warning("[v2] Attempt %d: topic drift detected, retrying", attempt)
                # Strengthen the prompt for retry
                user_prompt += (
                    f"\n\nI REPEAT: only generate questions about {topic}. "
                    f"Do NOT include any questions about other topics."
                )
                all_warnings.append(f"Retry {attempt}: topic drift detected")
                continue

            logger.info(
                "[v2] Generated %d questions in %d ms (attempt %d)",
                len(data.get("questions", [])), elapsed_ms, attempt,
            )
            return data, elapsed_ms, all_warnings

        except (json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            logger.warning("[v2] Attempt %d failed (%s): %s", attempt, type(exc).__name__, exc)
            all_warnings.append(f"Attempt {attempt} failed: {exc}")
            if attempt < max_attempts:
                user_prompt += "\n\nIMPORTANT: Respond with ONLY valid JSON. No markdown, no extra text."
                continue

    raise ValueError(
        f"Worksheet generation failed after {max_attempts} attempts. "
        f"Last error: {last_error}"
    )
