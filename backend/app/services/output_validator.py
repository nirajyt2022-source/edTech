"""
Output validation for all AI-generated content.

Validates worksheet questions, revision notes, flashcards, and grading results
BEFORE they reach the user. If validation fails, triggers a retry with error feedback.

Usage:
    from app.services.output_validator import get_validator
    validator = get_validator()

    is_valid, errors = validator.validate_worksheet(data, grade="Class 4", subject="Maths", topic="Fractions", num_questions=10)
    if not is_valid:
        # retry or return with warnings
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger("skolar.validator")


class OutputValidator:
    """Validates AI-generated outputs before they reach users."""

    # ── Worksheet Validation ──────────────────────────────────────────────

    def validate_worksheet(
        self,
        data: dict[str, Any],
        grade: str = "",
        subject: str = "",
        topic: str = "",
        num_questions: int = 10,
    ) -> tuple[bool, list[str]]:
        """
        Validate a generated worksheet.
        Returns (is_valid, list_of_errors).
        """
        errors: list[str] = []
        questions = data.get("questions", [])

        # 1. Question count — exact match required (retry trigger)
        if len(questions) < num_questions:
            errors.append(f"[count_mismatch] Too few questions: got {len(questions)}, need {num_questions}")

        # 2. Every question needs required fields
        for i, q in enumerate(questions):
            qid = q.get("id", f"Q{i + 1}")

            if not q.get("text", "").strip():
                errors.append(f"{qid}: empty question text")

            if not q.get("correct_answer") and q.get("correct_answer") != 0:
                errors.append(f"{qid}: missing correct_answer")

            # MCQ must have options
            q_type = q.get("type", "")
            if q_type == "mcq" and (not q.get("options") or len(q.get("options", [])) < 3):
                errors.append(f"{qid}: MCQ needs at least 3 options")

            # True/false answer must be valid
            if q_type == "true_false":
                ans = str(q.get("correct_answer", "")).strip().lower()
                if ans not in ("true", "false"):
                    errors.append(f"{qid}: true_false answer must be 'True' or 'False', got '{ans}'")

            # MCQ answer must be in options
            if q_type == "mcq" and q.get("options") and q.get("correct_answer"):
                answer = str(q["correct_answer"]).strip()
                options_text = [str(o).strip() for o in q["options"]]
                # Check if answer matches any option (by text or by letter like A/B/C/D)
                letters = [chr(65 + j) for j in range(len(options_text))]
                if answer not in options_text and answer.upper() not in letters:
                    errors.append(f"{qid}: MCQ answer '{answer}' not in options")

        # 3. Duplicate detection — exact + pattern-based near-duplicates
        texts = [q.get("text", "").strip().lower() for q in questions if q.get("text")]
        seen = set()
        for t in texts:
            # Normalize whitespace for comparison
            normalized = re.sub(r"\s+", " ", t)
            if normalized in seen:
                errors.append("Duplicate question detected")
                break
            seen.add(normalized)

        # 3b. Near-duplicate detection — strip names/numbers/times to create templates
        if len(questions) >= 4:
            templates: list[str] = []
            for q in questions:
                text = q.get("text", "").strip().lower()
                tmpl = self._make_template(text)
                templates.append(tmpl)
            from collections import Counter

            counts = Counter(templates)
            threshold = max(3, int(len(questions) * 0.33) + 1)
            for tmpl, cnt in counts.items():
                if cnt >= threshold:
                    errors.append(
                        f"Near-duplicate pattern detected: {cnt}/{len(questions)} questions share the same structure"
                    )
                    break

        # 4. Grade-level appropriateness
        grade_num = self._parse_grade_num(grade)
        if grade_num:
            for i, q in enumerate(questions):
                qid = q.get("id", f"Q{i + 1}")
                text = q.get("text", "")

                # Class 1-2: questions shouldn't be too long
                if grade_num <= 2 and len(text.split()) > 40:
                    errors.append(f"{qid}: question too long for {grade} ({len(text.split())} words)")

                # Class 1-2: shouldn't use complex vocabulary
                if grade_num <= 2:
                    complex_words = {
                        "approximately",
                        "calculate",
                        "determine",
                        "evaluate",
                        "demonstrate",
                        "illustrate",
                        "hypothesis",
                        "consequently",
                    }
                    used_complex = [w for w in text.lower().split() if w in complex_words]
                    if used_complex:
                        errors.append(f"{qid}: complex vocabulary for {grade}: {', '.join(used_complex)}")

        # 5. Maths answer verification (basic checks)
        if subject.lower() in ("maths", "mathematics", "math"):
            for i, q in enumerate(questions):
                qid = q.get("id", f"Q{i + 1}")
                verified = self._verify_math_answer(q)
                if verified is False:
                    errors.append(f"{qid}: math answer appears incorrect")

        # 5b. Visual-answer coherence
        for i, q in enumerate(questions):
            if q.get("visual_type"):
                qid = q.get("id", f"Q{i + 1}")
                coherence = self._verify_visual_answer_coherence(q)
                if coherence is False:
                    errors.append(f"{qid}: visual data does not match correct_answer")

        # 6. Must have answer_key or answers extractable from questions
        answer_key = data.get("answer_key", {})
        if not answer_key and all(not q.get("correct_answer") for q in questions):
            errors.append("No answer key and no answers in questions")

        is_valid = len(errors) == 0
        if not is_valid:
            logger.warning("Worksheet validation failed", extra={"errors": errors, "topic": topic, "grade": grade})
        return is_valid, errors

    # ── Revision Notes Validation ─────────────────────────────────────────

    def validate_revision(self, data: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate revision notes output."""
        errors: list[str] = []

        if not data.get("key_concepts") or len(data.get("key_concepts", [])) < 2:
            errors.append("Too few key concepts (need at least 2)")

        if not data.get("worked_examples") or len(data.get("worked_examples", [])) < 1:
            errors.append("Missing worked examples")

        if not data.get("introduction", "").strip():
            errors.append("Missing introduction")

        # Each key concept should have title and explanation
        for i, concept in enumerate(data.get("key_concepts", [])):
            if not concept.get("title", "").strip():
                errors.append(f"Key concept {i + 1}: missing title")
            if not concept.get("explanation", "").strip():
                errors.append(f"Key concept {i + 1}: missing explanation")

        if not data.get("quick_quiz") or len(data.get("quick_quiz", [])) < 2:
            errors.append("Need at least 2 quick quiz questions")

        is_valid = len(errors) == 0
        if not is_valid:
            logger.warning("Revision validation failed", extra={"errors": errors})
        return is_valid, errors

    # ── Flashcard Validation ──────────────────────────────────────────────

    def validate_flashcards(self, data: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate flashcard output."""
        errors: list[str] = []
        cards = data.get("cards", [])

        if len(cards) < 8:
            errors.append(f"Too few cards: {len(cards)} (need at least 8)")

        for i, card in enumerate(cards):
            if not card.get("front", "").strip():
                errors.append(f"Card {i + 1}: empty front")
            if not card.get("back", "").strip():
                errors.append(f"Card {i + 1}: empty back")
            # Front should be short (it's a card)
            if len(card.get("front", "").split()) > 20:
                errors.append(f"Card {i + 1}: front too long ({len(card['front'].split())} words)")

        # Check for duplicate fronts
        fronts = [c.get("front", "").strip().lower() for c in cards]
        if len(fronts) != len(set(fronts)):
            errors.append("Duplicate flashcard fronts detected")

        is_valid = len(errors) == 0
        if not is_valid:
            logger.warning("Flashcard validation failed", extra={"errors": errors})
        return is_valid, errors

    # ── Grading Validation ────────────────────────────────────────────────

    def validate_grading(self, data: dict[str, Any], total_questions: int = 0) -> tuple[bool, list[str]]:
        """Validate grading results."""
        errors: list[str] = []

        results = data.get("results", [])
        if not results:
            errors.append("No grading results returned")

        score = data.get("score", -1)
        total = data.get("total", -1)

        if score < 0 or total < 0:
            errors.append("Invalid score or total")
        if total > 0 and score > total:
            errors.append(f"Score ({score}) exceeds total ({total})")

        for i, r in enumerate(results):
            if "is_correct" not in r and "status" not in r:
                errors.append(f"Result {i + 1}: missing is_correct/status field")

        is_valid = len(errors) == 0
        if not is_valid:
            logger.warning("Grading validation failed", extra={"errors": errors})
        return is_valid, errors

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _make_template(text: str) -> str:
        """Strip names, numbers, and times from question text to create a structural template.

        Used for near-duplicate detection — two questions that differ only in
        names/numbers/times will produce the same template.
        """
        # Replace time patterns (e.g. "3:45 PM", "10:30 AM")
        tmpl = re.sub(r"\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?", "<TIME>", text)
        # Replace numbers (including currency like ₹500)
        tmpl = re.sub(r"₹?\d+(?:\.\d+)?", "<NUM>", tmpl)
        # Replace common Indian names (case-insensitive)
        _NAMES_PATTERN = (
            r"\b(?:aarav|ananya|vihaan|diya|reyansh|saanvi|arjun|isha|kabir|myra|"
            r"aditya|kiara|rohan|priya|vivaan|anika|krishna|zara|rudra|pari|"
            r"atharv|navya|shaurya|aadhya|dhruv|riya|arnav|sara|dev|anvi|"
            r"ishan|tara|kian|meera|yash|nisha|aryan|siya|neil|pooja|"
            r"rahul|sneha|manav|kavya|sameer|tanvi|kunal|ritika|"
            r"ravi|kiran|anita|deepa|suresh|sunita|mohan)\b"
        )
        tmpl = re.sub(_NAMES_PATTERN, "<NAME>", tmpl, flags=re.IGNORECASE)
        # Collapse whitespace
        tmpl = re.sub(r"\s+", " ", tmpl).strip()
        return tmpl

    @staticmethod
    def _parse_grade_num(grade: str) -> int | None:
        """Extract number from 'Class 4' -> 4."""
        match = re.search(r"\d+", grade)
        return int(match.group()) if match else None

    @staticmethod
    def _verify_clock_answer(q: dict) -> bool | None:
        """Verify that clock visual_data matches the correct_answer.

        Returns True (match), False (mismatch), or None (can't verify).
        """
        vd = q.get("visual_data")
        answer = str(q.get("correct_answer", ""))
        if not vd or not isinstance(vd, dict):
            return None
        hour = vd.get("hour")
        minute = vd.get("minute")
        if hour is None or minute is None:
            return None
        match = re.search(r"(\d{1,2}):(\d{2})", answer)
        if not match:
            return None
        ans_hour = int(match.group(1))
        ans_minute = int(match.group(2))
        if ans_hour == int(hour) and ans_minute == int(minute):
            return True
        logger.warning(
            "Clock coherence failed",
            extra={"visual": {"hour": hour, "minute": minute}, "answer": answer},
        )
        return False

    @staticmethod
    def _verify_object_group_answer(q: dict) -> bool | None:
        """Verify that object_group visual_data matches the correct_answer.

        Returns True (match), False (mismatch), or None (can't verify).
        """
        vd = q.get("visual_data")
        answer = str(q.get("correct_answer", ""))
        if not vd or not isinstance(vd, dict):
            return None
        groups = vd.get("groups")
        operation = vd.get("operation", "+")
        if not groups or not isinstance(groups, list):
            return None
        counts = []
        for g in groups:
            c = g.get("count")
            if c is None:
                return None
            counts.append(int(c))
        if not counts:
            return None
        if operation == "+":
            expected = sum(counts)
        elif operation == "-":
            expected = counts[0] - sum(counts[1:])
        else:
            return None
        # Parse numeric answer (strip ₹ prefix, commas)
        cleaned = re.sub(r"[₹,\s]", "", answer)
        num_match = re.search(r"-?\d+", cleaned)
        if not num_match:
            return None
        ans_num = int(num_match.group())
        if ans_num == expected:
            return True
        logger.warning(
            "Object group coherence failed",
            extra={"expected": expected, "answer": answer, "operation": operation},
        )
        return False

    @classmethod
    def _verify_visual_answer_coherence(cls, q: dict) -> bool | None:
        """Dispatch visual-answer coherence check based on visual_type.

        Returns True (match), False (mismatch), or None (can't verify / not applicable).
        """
        vtype = q.get("visual_type", "")
        if not vtype:
            return None
        if vtype == "clock":
            return cls._verify_clock_answer(q)
        if vtype == "object_group":
            return cls._verify_object_group_answer(q)
        return None

    @staticmethod
    def _verify_math_answer(q: dict) -> bool | None:
        """
        Try to verify math answers (simple and multi-step).
        Returns True (correct), False (wrong), or None (can't verify).
        """
        from app.services.quality_reviewer import _extract_arithmetic_expression

        text = q.get("text", "")
        answer = q.get("correct_answer", "")
        q_type = q.get("type", "")

        # Only verify fill_blank/short_answer math questions with numeric answers
        if q_type not in ("fill_blank", "short_answer"):
            return None

        extracted = _extract_arithmetic_expression(text)
        if extracted is None:
            return None

        _expr, expected = extracted
        try:
            answer_num = float(str(answer).replace(",", "").strip())
        except (ValueError, TypeError):
            return None

        if abs(answer_num - expected) < 0.01:
            return True

        logger.warning(
            "Math verification failed",
            extra={"question": text[:80], "expected": expected, "got": answer_num},
        )
        return False


# Singleton
_validator: OutputValidator | None = None


def get_validator() -> OutputValidator:
    global _validator
    if _validator is None:
        _validator = OutputValidator()
    return _validator
