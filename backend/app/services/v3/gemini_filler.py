"""Gemini text filler — calls LLM to write question text for pre-built slots.

Uses Bloom's taxonomy + topic anchoring + few-shot examples for high-quality
question generation. Gemini writes question text, hint, explanation, options,
and per-question emoji. All structure, numbers, visuals, and answers come
from slot_builder.
"""

from __future__ import annotations

import json
import logging
import re

from .slot_builder import Slot

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt — Bloom's taxonomy + topic lock + per-question emoji
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are an expert CBSE curriculum designer creating a worksheet for Indian primary school students.

YOUR ROLE: Create high-quality, curriculum-aligned questions that test specific skills at the right cognitive level for the student's age.

BLOOM'S TAXONOMY — Your questions must match these cognitive levels:
- REMEMBER (Foundation/Easy): Recall facts. "What is...?", "Name the...", "True or False: ..."
  Example: "The sun rises in the east. True or False?"
- UNDERSTAND (Foundation/Easy): Explain in own words. "Why...?", "Describe...", "What does ___ mean?"
  Example: "Why do we water plants?"
- APPLY (Application/Medium): Use knowledge in new situations. "If... then what?", word problems, fill-blanks
  Example: "Rohan has 8 marbles. Priya gives him 5 more. How many does he have now?"
- ANALYZE (Application/Medium): Compare, contrast, classify. "How is ___ different from ___?", "Which does NOT belong?"
  Example: "Which of these is NOT a season? Summer, Rainy, Football, Winter"
- EVALUATE (Stretch/Hard): Judge, defend, critique. "Is this correct? Explain why.", "Do you agree? Why?"
  Example: "Rani says 5+8=12. Is she right? Explain your answer."
- CREATE (Stretch/Hard): Produce something new. "Write a sentence using...", "Draw...", "Make up a problem about..."
  Example: "Write two sentences about your favourite season."

QUALITY RULES:
1. TOPIC LOCK: Every question MUST test the specific topic given. Do NOT drift to other topics.
2. UNIQUE ANGLES: Each question must test a DIFFERENT aspect. Never ask the same concept twice.
   BAD: Q1 "What letter does Apple start with?" + Q3 "What letter does Ant start with?" (both test letter A)
   GOOD: Q1 "letter A recognition" + Q3 "alphabetical order" + Q5 "capital vs small letter"
3. CORRECT ANSWERS: Double-check every answer. For MCQ, the correct answer MUST be in the options.
4. AGE-APPROPRIATE: Use vocabulary and sentence length suitable for the grade.
5. INDIAN CONTEXT: Use Indian names (Aarav, Meera, Rohan, Priya), Indian settings (mela, Diwali, school, market), ₹ for money.
6. NATURAL LANGUAGE: Questions should sound like a kind teacher talking to the child, not a textbook.
7. NO REPETITION: Different objects, scenarios, and question angles for every question.
8. For fill_blank: include exactly one "______" in the text.
9. For word problems: tell a mini-story, don't just state bare numbers.

VISUAL/EMOJI RULES:
For each question, include an "emoji" field:
- Pick 1-2 emoji that DIRECTLY illustrate THIS specific question's content
- Question about a cow → "emoji": "🐄"
- Question about adding apples → "emoji": "🍎"
- Question about the letter B → "emoji": "⚽" (Ball)
- Question about summer → "emoji": "☀️"
- Question about a leaf → "emoji": "🍃"
- If the question is abstract with no concrete object → "emoji": null
- NEVER use the same emoji for all questions. Each question gets its own matching emoji.

For MATHS questions with visual_data provided in the slot:
- The visual (number line, object group, clock, etc.) is pre-computed. Just write the question text to match it.
- Reference the visual naturally: "Look at the number line", "Count the apples shown"

RESPONSE FORMAT — JSON array, no markdown:
[
  {
    "slot": 1,
    "text": "question text here",
    "correct_answer": "exact correct answer",
    "hint": "helpful hint that does NOT give away the answer",
    "explanation": "1-2 sentence explanation of why this is the answer",
    "options": ["A", "B", "C", "D"] or null,
    "emoji": "🍎" or null,
    "common_mistake": "one common mistake (SLOT 1 ONLY, null for others)",
    "parent_tip": "tip for parents (SLOT 1 ONLY, null for others)"
  }
]

MANDATORY:
- "correct_answer" is REQUIRED for every slot
- For MCQ: correct_answer must EXACTLY match one of the 4 options
- For true_false: correct_answer must be exactly "True" or "False"
- For fill_blank: correct_answer is the word(s) that fill the blank
- "emoji" is REQUIRED — pick matching emoji or null if abstract
- "options" must be exactly 4 items for MCQ, null for other types
- Only include "common_mistake" and "parent_tip" for slot 1
"""


# ---------------------------------------------------------------------------
# Build user prompt from slots
# ---------------------------------------------------------------------------
def _build_user_prompt(slots: list[Slot], language: str, curriculum_context: str | None = None) -> str:
    """Build a rich, contextual prompt that gives Gemini full worksheet awareness."""

    parts = []

    # ── WORKSHEET CONTEXT (the most important part) ──
    parts.append("=" * 60)
    parts.append("WORKSHEET CONTEXT")
    parts.append("=" * 60)
    parts.append(f"Total questions: {len(slots)}")
    parts.append(f"Language: {language}")

    if curriculum_context:
        parts.append(f"\nCURRICULUM REFERENCE:\n{curriculum_context}")

    parts.append("")
    parts.append("Think step by step about each question:")
    parts.append("1. What specific skill is being tested?")
    parts.append("2. What cognitive level (Bloom's) does this slot require?")
    parts.append("3. What would be a creative, age-appropriate way to test this?")
    parts.append("4. What emoji best illustrates this specific question?")
    parts.append("5. Is the answer definitely correct?")
    parts.append("")

    # ── INDIVIDUAL SLOTS ──
    parts.append("=" * 60)
    parts.append("QUESTIONS TO GENERATE")
    parts.append("=" * 60)

    for slot in slots:
        parts.append(f"\n--- SLOT {slot.slot_number} ---")
        parts.append(slot.llm_instruction)
        parts.append("")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Parse LLM response
# ---------------------------------------------------------------------------
def _parse_response(raw: str) -> list[dict]:
    """Parse JSON array from LLM response, with fallback for markdown fences."""
    text = raw.strip()

    # Strip markdown fences
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    # Strip control characters
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to extract JSON array
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            data = json.loads(match.group())
        else:
            logger.error("[gemini_filler] Failed to parse JSON from response")
            return []

    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "questions" in data:
        return data["questions"]
    return []


# ---------------------------------------------------------------------------
# Single LLM call
# ---------------------------------------------------------------------------
def _single_call(client, slots: list[Slot], language: str, curriculum_context: str | None = None) -> list[dict]:
    """Make a single LLM call for a batch of slots."""
    user_prompt = _build_user_prompt(slots, language, curriculum_context)

    # Determine temperature and tokens
    has_maths = any(s.numbers for s in slots)
    temp = 0.5 if has_maths else 0.8
    max_tokens = min(8192, 4096 + (len(slots) - 10) * 400) if len(slots) > 10 else 4096

    # Thinking budget for maths
    thinking_budget = 1024 if has_maths else 0

    if thinking_budget > 0:
        user_prompt += (
            "\n\nCHAIN-OF-THOUGHT: Before writing each answer, mentally compute "
            "the arithmetic step by step. Verify your answer is correct before "
            "writing it."
        )

    logger.info("[gemini_filler] Calling LLM for %d slots", len(slots))

    response = client.chat.completions.create(
        model="gemini-2.5-flash",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temp,
        max_tokens=max_tokens,
        thinking_budget=thinking_budget,
    )

    raw = response.choices[0].message.content or ""
    filled = _parse_response(raw)

    logger.info("[gemini_filler] Got %d filled slots from LLM", len(filled))
    return filled


# ---------------------------------------------------------------------------
# Main entry: fill_slots()
# ---------------------------------------------------------------------------
def fill_slots(client, slots: list[Slot], language: str, curriculum_context: str | None = None) -> list[dict]:
    """Fill all slots with LLM-generated text. Batches for 10+ slots."""
    if len(slots) <= 10:
        return _single_call(client, slots, language, curriculum_context)

    results = []
    for i in range(0, len(slots), 10):
        batch = slots[i : i + 10]
        filled = _single_call(client, batch, language, curriculum_context)
        results.extend(filled)
    return results


# ---------------------------------------------------------------------------
# AI Review — optional second Gemini call for QA
# ---------------------------------------------------------------------------
REVIEW_PROMPT = """You are a CBSE curriculum quality reviewer. Review these {num_questions} questions for a {grade} {subject} worksheet on "{topic}".

CHECK EACH QUESTION:
1. Is it actually about {topic}? (NOT about some other topic)
2. Is the correct_answer actually correct?
3. For MCQ: is correct_answer one of the 4 options?
4. For true_false: is correct_answer "True" or "False"?
5. Is the language age-appropriate for {grade}?
6. Is this question different from all other questions? (no concept repetition)
7. Does the emoji match the question content?

QUESTIONS TO REVIEW:
{questions_json}

If ALL questions pass, respond with exactly: {{"status": "pass"}}

If ANY question has issues, respond with the CORRECTED full JSON array (same format as input).
Only fix what's broken — don't rewrite questions that are fine.
"""


def review_worksheet(client, worksheet: dict) -> dict:
    """Optional second Gemini call to QA the generated questions."""
    questions = worksheet.get("questions", [])
    if not questions:
        return worksheet

    # Build review payload
    review_items = []
    for q in questions:
        review_items.append(
            {
                "slot": int(q["id"].replace("q", "")),
                "text": q.get("text", ""),
                "correct_answer": q.get("correct_answer", ""),
                "options": q.get("options"),
                "type": q.get("type", ""),
                "hint": q.get("hint", ""),
                "emoji": q.get("emoji"),
            }
        )

    grade = worksheet.get("grade", "Class 1")
    subject = worksheet.get("subject", "")
    topic = worksheet.get("topic", "")

    prompt = REVIEW_PROMPT.format(
        num_questions=len(questions),
        grade=grade,
        subject=subject,
        topic=topic,
        questions_json=json.dumps(review_items, indent=2, ensure_ascii=False),
    )

    try:
        response = client.chat.completions.create(
            model="gemini-2.5-flash",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=6000,
        )

        result_text = response.choices[0].message.content.strip()

        # If passes review, return unchanged
        if '"status"' in result_text and '"pass"' in result_text:
            logger.info("[review] All questions passed review")
            return worksheet

        # Parse corrections
        corrections = _parse_response(result_text)
        if corrections:
            # Build set of maths slots (Python-computed answers — NEVER override)
            maths_slots = set()
            for q in worksheet["questions"]:
                if q.get("visual_data") or q.get("visual_type"):
                    maths_slots.add(q["id"])

            corrections_by_slot = {c.get("slot", 0): c for c in corrections}
            fixed_count = 0
            for q in worksheet["questions"]:
                slot_num = int(q["id"].replace("q", ""))
                if slot_num in corrections_by_slot:
                    fix = corrections_by_slot[slot_num]
                    if fix.get("text") and fix["text"] != q.get("text"):
                        q["text"] = fix["text"]
                        fixed_count += 1
                    # NEVER override Python-computed maths answers
                    if fix.get("correct_answer") and q["id"] not in maths_slots:
                        q["correct_answer"] = fix["correct_answer"]
                    if fix.get("options") and q["id"] not in maths_slots:
                        q["options"] = fix["options"]
                    if fix.get("emoji"):
                        q["emoji"] = fix["emoji"]
                    if fix.get("hint"):
                        q["hint"] = fix["hint"]

            logger.info("[review] Fixed %d questions (skipped %d maths slots)", fixed_count, len(maths_slots))

    except Exception as e:
        logger.warning("[review] Review call failed (non-blocking): %s", e)

    return worksheet
