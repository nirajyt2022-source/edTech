"""Gemini text filler — calls LLM to write question text for pre-built slots.

The system prompt is ~20 lines instead of the current 846-line behemoth.
Gemini writes ONLY question text, hint, explanation, and options (non-maths MCQ).
All structure, numbers, visuals, and answers come from slot_builder.
"""

from __future__ import annotations

import json
import logging
import re

from .slot_builder import Slot

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt (simple — no structural rules)
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are writing worksheet questions for Indian primary school students.
For each SLOT, write ONLY what is asked. Everything structural is already decided.

RULES:
1. Write natural, creative, age-appropriate question text.
2. Use Indian context (₹, Indian cities, festivals).
3. NEVER start two questions with the same word.
4. NEVER reference other questions.
5. For fill_blank: include exactly one "______" in the text.
6. For MCQ (non-maths): provide 4 options in "options" array.
7. For word problems: tell a mini-story, don't just state bare numbers.
8. Keep language simple for the given age.

Respond with ONLY a JSON array (no markdown, no extra text):
[
  {
    "slot": 1,
    "text": "question text",
    "correct_answer": "the correct answer",
    "hint": "helpful hint that does NOT reveal the answer",
    "explanation": "brief explanation of how to solve",
    "options": ["A", "B", "C", "D"] or null,
    "common_mistake": "one common mistake for this topic",
    "parent_tip": "one tip for parents"
  }
]

IMPORTANT:
- "correct_answer" is MANDATORY for every slot. It must be the exact correct answer.
- For MCQ: correct_answer must be one of the options.
- For true_false: correct_answer must be "True" or "False".
- For fill_blank: correct_answer must be the word(s) that fill the blank.
- Only include "common_mistake" and "parent_tip" for slot 1. Set them to null for other slots.
- "options" MUST be a 4-element array for ALL MCQ questions. Include the correct_answer as one of the 4 options. Set to null only for non-MCQ question types (fill_blank, short_answer, word_problem).
"""


# ---------------------------------------------------------------------------
# Build user prompt from slots
# ---------------------------------------------------------------------------
def _build_user_prompt(slots: list[Slot], language: str, curriculum_context: str | None = None) -> str:
    """Build user prompt listing all slots with their instructions."""
    parts = [f"Language: {language}", f"Total slots: {len(slots)}", ""]

    if curriculum_context:
        parts.append(curriculum_context)
        parts.append("")

    for slot in slots:
        parts.append(f"SLOT {slot.slot_number}:")
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
