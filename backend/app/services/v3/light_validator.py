"""Light validator — 5 checks only, with single retry for failed slots.

Checks:
1. Text present: every question has text with length >= 5
2. Numbers present (maths only): text contains expected numbers from slot
3. Word count: question text within grade limit (max_words * 4)
4. No duplicates: Jaccard similarity between any pair < 0.6
5. MCQ answer in options: correct_answer appears in options list
"""

from __future__ import annotations

import logging

from .slot_builder import Slot

logger = logging.getLogger(__name__)


def _jaccard_similarity(text_a: str, text_b: str) -> float:
    """Compute Jaccard similarity between two texts."""
    words_a = set(text_a.lower().split())
    words_b = set(text_b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


def validate_worksheet(
    worksheet: dict,
    slots: list[Slot],
) -> tuple[bool, list[str], list[int]]:
    """Run 5 light checks on the assembled worksheet.

    Returns:
        (passed, issues, failed_slot_numbers)
    """
    questions = worksheet.get("questions", [])
    issues: list[str] = []
    failed_slots: list[int] = []

    # Index slots by number
    slots_by_num = {s.slot_number: s for s in slots}

    for i, q in enumerate(questions):
        slot_num = i + 1
        slot = slots_by_num.get(slot_num)
        text = q.get("text", "")

        # CHECK 1: Text present (>= 5 chars)
        if len(text.strip()) < 5:
            issues.append(f"Q{slot_num}: text too short ({len(text)} chars)")
            failed_slots.append(slot_num)
            continue

        # CHECK 2: Numbers present (maths only)
        if slot and slot.numbers:
            a = slot.numbers.get("a")
            b = slot.numbers.get("b")
            if a is not None and str(a) not in text and str(b) not in text:
                # For word problems, numbers might be embedded differently
                if slot.question_type not in ("true_false", "error_detection"):
                    issues.append(f"Q{slot_num}: expected numbers {a}, {b} not found in text")
                    # Don't fail — LLM may have rephrased

        # CHECK 3: Word count limit
        if slot:
            max_allowed = slot.max_words * 4  # generous limit
            word_count = len(text.split())
            if word_count > max_allowed:
                issues.append(f"Q{slot_num}: text too long ({word_count} words, max {max_allowed})")

        # CHECK 3b: Question word count for young grades
        if slot and slot.age_range:
            try:
                age_start = int(slot.age_range.split("-")[0]) if "-" in slot.age_range else 8
            except (ValueError, IndexError):
                age_start = 8
            max_question_words = 15 if age_start <= 7 else (20 if age_start <= 8 else 40)
            word_count = len(text.split())
            if word_count > max_question_words:
                issues.append(
                    f"Q{slot_num}: question too long for age {slot.age_range}"
                    f" ({word_count} words, max {max_question_words})"
                )

        # CHECK 5: MCQ answer in options
        q_type = q.get("type", "")
        options = q.get("options")
        correct = q.get("correct_answer", "")
        if q_type == "mcq" and options and correct:
            if correct not in options:
                issues.append(f"Q{slot_num}: correct_answer '{correct}' not in options {options}")
                # Auto-fix: replace first option with correct answer
                if options:
                    options[0] = correct
                    q["options"] = options

        # CHECK 7: Hindi word bank alignment — assigned word must appear in text
        if slot and getattr(slot, "assigned_word", None):
            if slot.assigned_word not in text:
                issues.append(
                    f"Q{slot_num}: assigned word '{slot.assigned_word}' not in question text — LLM may have ignored instruction"
                )
                failed_slots.append(slot_num)

        # CHECK 6: True/False answers must be "True" or "False"
        if q_type == "true_false":
            ca = str(q.get("correct_answer", ""))
            if ca not in ("True", "False"):
                issues.append(f"Q{slot_num}: true_false answer is '{ca}', must be 'True' or 'False'")
                failed_slots.append(slot_num)
            # Also flag if text is a question (contains ?) — triggers retry
            if "?" in text:
                issues.append(f"Q{slot_num}: true_false text is a question (contains '?'), should be a statement")
                failed_slots.append(slot_num)

    # CHECK 4: No duplicates (Jaccard similarity)
    texts = [q.get("text", "") for q in questions]
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            sim = _jaccard_similarity(texts[i], texts[j])
            if sim >= 0.6:
                issues.append(f"Q{i + 1} and Q{j + 1}: too similar (Jaccard={sim:.2f})")
                failed_slots.append(j + 1)

    passed = len(failed_slots) == 0
    if issues:
        logger.warning("[light_validator] %d issues found: %s", len(issues), "; ".join(issues[:5]))

    return passed, issues, list(set(failed_slots))
