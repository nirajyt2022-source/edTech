"""Assembler — merges SlotBuilderOutput + filled text into frontend JSON.

The output JSON must match the EXACT structure the frontend/PDF renderer expects.
Key rule: maths answers come from Python (slot.numbers), NEVER from Gemini.
"""

from __future__ import annotations

import random

from .slot_builder import SlotBuilderOutput


# ---------------------------------------------------------------------------
# Maths distractor generation
# ---------------------------------------------------------------------------
def generate_maths_distractors(correct: int, difficulty: str) -> list[int]:
    """3 plausible wrong answers for maths MCQs."""
    distractors: set[int] = set()
    distractors.add(correct + 1)
    distractors.add(correct - 1)
    distractors.add(correct + 10)
    distractors.add(correct - 10)
    # Digit swap
    s = str(abs(correct))
    if len(s) >= 2:
        swapped = s[:-2] + s[-1] + s[-2]
        try:
            distractors.add(int(swapped))
        except ValueError:
            pass
    distractors.discard(correct)
    distractors.discard(0)
    distractors = {d for d in distractors if d > 0}
    sorted_d = sorted(distractors)
    return sorted_d[:3]


# ---------------------------------------------------------------------------
# Render format inference
# ---------------------------------------------------------------------------
def _infer_render_format(q_type: str, options: list[str] | None) -> str:
    """Infer the PDF render format from question type and options."""
    if q_type == "mcq":
        if options and len(options) == 4:
            return "mcq_4"
        elif options and len(options) == 3:
            return "mcq_3"
        return "mcq_4"
    if q_type == "fill_blank":
        return "fill_blank"
    if q_type == "true_false":
        return "true_false"
    return "short_answer"


# ---------------------------------------------------------------------------
# Main entry: assemble_worksheet()
# ---------------------------------------------------------------------------
def assemble_worksheet(slot_output: SlotBuilderOutput, filled: list[dict]) -> dict:
    """Assemble the final worksheet dict matching frontend expectations.

    Args:
        slot_output: SlotBuilderOutput from slot_builder
        filled: list of dicts from gemini_filler (slot, text, hint, explanation, options, common_mistake, parent_tip)

    Returns:
        dict with title, skill_focus, common_mistake, parent_tip, learning_objectives, questions
    """
    # Index filled by slot number
    filled_by_slot: dict[int, dict] = {}
    for item in filled:
        slot_num = item.get("slot", 0)
        filled_by_slot[slot_num] = item

    is_maths = False
    for slot in slot_output.slots:
        if slot.numbers:
            is_maths = True
            break

    questions = []
    for slot in slot_output.slots:
        fill = filled_by_slot.get(slot.slot_number, {})
        q_type_override = None

        # Question text
        text = fill.get("text", f"Question {slot.slot_number}")

        # Correct answer: maths from Python, non-maths from Gemini
        if slot.numbers and slot.numbers.get("answer") is not None:
            correct_answer = str(slot.numbers["answer"])
        else:
            correct_answer = fill.get("correct_answer", "")

            # true_false (non-maths only): normalize correct_answer to "True" or "False"
            if slot.question_type == "true_false":
                ca_lower = str(correct_answer).strip().lower()
                if ca_lower in ("true", "t", "yes", "correct", "sahi", "सही"):
                    correct_answer = "True"
                elif ca_lower in ("false", "f", "no", "incorrect", "galat", "गलत"):
                    correct_answer = "False"
                else:
                    # LLM returned a sentence — default to True
                    correct_answer = "True"

        # Options
        options = None
        if slot.question_type == "mcq":
            if is_maths and slot.numbers and slot.numbers.get("answer") is not None:
                # Generate distractors in Python
                correct_int = slot.numbers["answer"]
                distractors = generate_maths_distractors(correct_int, slot.difficulty)
                all_options = [str(correct_int)] + [str(d) for d in distractors]
                # Pad to 4 if needed
                while len(all_options) < 4:
                    all_options.append(str(correct_int + random.randint(2, 20)))
                random.shuffle(all_options)
                options = all_options[:4]
            else:
                # Non-maths: use Gemini's options
                options = fill.get("options") or []
                if len(options) < 4:
                    if len(options) <= 1:
                        # Gemini filler failure — convert to short_answer
                        q_type_override = "short_answer"
                        options = None
                    else:
                        # Pad with "None of the above" as last resort for 2-3 options
                        while len(options) < 4:
                            options.append("None of the above")
                options = options[:4] if options else None
        elif slot.question_type == "true_false":
            options = ["True", "False"]

        # Visual data: ALWAYS from slot (Python), NEVER from Gemini
        visual_type = slot.visual_type
        visual_data = slot.visual_data

        # Image keywords
        image_keywords = slot.image_keywords
        images = None
        if image_keywords:
            from app.data.image_registry import IMAGE_REGISTRY

            images = []
            for kw in image_keywords:
                if kw in IMAGE_REGISTRY:
                    entry = IMAGE_REGISTRY[kw]
                    images.append({"path": entry["path"], "alt": entry["alt"], "category": entry.get("category", "")})

        # Build question dict
        final_type = q_type_override if q_type_override else slot.question_type
        q = {
            "id": f"q{slot.slot_number}",
            "type": final_type,
            "role": slot.role,
            "text": text,
            "options": options,
            "correct_answer": correct_answer,
            "explanation": fill.get("explanation", ""),
            "difficulty": slot.difficulty,
            "hint": fill.get("hint", ""),
            "skill_tag": slot.skill_tag,
            "image_keywords": image_keywords,
            "visual_type": visual_type,
            "visual_data": visual_data,
            "format": _infer_render_format(final_type, options),
            "images": images,
            "verified": True,
        }
        questions.append(q)

    # Worksheet-level metadata
    meta = slot_output.worksheet_meta
    common_mistake = meta.get("common_mistake", "")
    parent_tip = meta.get("parent_tip", "")

    # Override from Gemini slot 1 if available
    fill_1 = filled_by_slot.get(1, {})
    if fill_1.get("common_mistake"):
        common_mistake = fill_1["common_mistake"]
    if fill_1.get("parent_tip"):
        parent_tip = fill_1["parent_tip"]

    worksheet = {
        "title": meta.get("title", "Worksheet"),
        "skill_focus": meta.get("skill_focus", ""),
        "common_mistake": common_mistake,
        "parent_tip": parent_tip,
        "learning_objectives": meta.get("learning_objectives", []),
        "questions": questions,
    }

    return worksheet
