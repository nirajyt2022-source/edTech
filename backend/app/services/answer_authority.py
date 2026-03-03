"""
Answer Authority — deterministic answer verification service.

Verifies LLM-produced answers against computed results WITHOUT modifying
any answers. Returns structured verdicts that downstream gates can act on.

This replaces the silent auto-correction pattern in quality_reviewer.py
CHECKs 1, 4, 8 with a verify-and-block approach:
  - match=True  → answer is correct
  - match=False → mismatch detected, question should be regenerated
  - match=None  → can't verify (no expression found, non-numeric, etc.)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class AnswerVerdict:
    """Result of verifying a single question's answer."""

    question_id: str
    declared_answer: str  # what LLM produced
    authoritative_answer: Optional[str]  # what solver computed (None = can't verify)
    match: Optional[bool]  # True=match, False=mismatch, None=unverifiable
    method: str  # "arithmetic" | "word_problem" | "fraction" | "fraction_decimal" | "error_detection" | "unverifiable"
    debug: dict = field(default_factory=dict)


class AnswerAuthority:
    """
    Deterministic answer verification. Does NOT modify answers.

    Reuses existing solver functions from quality_reviewer.py:
      - _extract_arithmetic_expression()
      - _extract_word_problem_arithmetic()
      - _validate_fraction_answer()
      - _validate_fraction_to_decimal()
      - _validate_error_detection_answer()
      - _answers_match()
    """

    def verify_question(self, question: dict, subject: str) -> AnswerVerdict:
        """
        Verify a single question's answer.

        Returns AnswerVerdict with match=True/False/None.
        Never modifies the question dict.
        """
        from app.services.quality_reviewer import (
            _answers_match,
            _extract_arithmetic_expression,
            _extract_word_problem_arithmetic,
            _validate_error_detection_answer,
            _validate_fraction_answer,
            _validate_fraction_to_decimal,
        )

        q_id = str(question.get("id", "?"))
        slot_type = question.get("slot_type", question.get("type", ""))
        question_text = question.get("question_text", question.get("text", ""))
        stored_answer = str(question.get("answer", question.get("correct_answer", "")))
        is_maths = subject.lower() in ("maths", "mathematics", "math")

        if not is_maths:
            return AnswerVerdict(
                question_id=q_id,
                declared_answer=stored_answer,
                authoritative_answer=None,
                match=None,
                method="unverifiable",
                debug={"reason": "non-maths subject"},
            )

        # Skip error_detection for arithmetic checks (intentionally wrong)
        # but DO check error_detection answer format (Bug C)
        if slot_type in ("error_detection", "error_spot"):
            return self._verify_error_detection(q_id, question_text, stored_answer, _validate_error_detection_answer)

        # 1. Try direct arithmetic extraction (CHECK 1 equivalent)
        try:
            extracted = _extract_arithmetic_expression(question_text)
            if extracted is not None:
                expr, computed = extracted
                if _answers_match(stored_answer, computed):
                    return AnswerVerdict(
                        question_id=q_id,
                        declared_answer=stored_answer,
                        authoritative_answer=self._format_number(computed),
                        match=True,
                        method="arithmetic",
                        debug={"expression": expr, "computed": computed},
                    )
                else:
                    return AnswerVerdict(
                        question_id=q_id,
                        declared_answer=stored_answer,
                        authoritative_answer=self._format_number(computed),
                        match=False,
                        method="arithmetic",
                        debug={"expression": expr, "computed": computed},
                    )
        except Exception as exc:
            logger.error("[answer_authority] Arithmetic check failed for Q%s: %s", q_id, exc)
            return AnswerVerdict(
                question_id=q_id,
                declared_answer=stored_answer,
                authoritative_answer=None,
                match=None,
                method="arithmetic",
                debug={"error": str(exc)},
            )

        # 2. Try fraction answer validation (CHECK 4 Bug A equivalent)
        try:
            correction = _validate_fraction_answer(question_text, stored_answer)
            if correction is not None:
                return AnswerVerdict(
                    question_id=q_id,
                    declared_answer=stored_answer,
                    authoritative_answer=correction,
                    match=False,
                    method="fraction",
                    debug={"expected_format": correction},
                )
        except Exception as exc:
            logger.debug("[answer_authority] Fraction check skipped for Q%s: %s", q_id, exc)

        # 3. Try fraction-to-decimal validation (CHECK 4 Bug B equivalent)
        try:
            correction = _validate_fraction_to_decimal(question_text, stored_answer)
            if correction is not None:
                return AnswerVerdict(
                    question_id=q_id,
                    declared_answer=stored_answer,
                    authoritative_answer=correction,
                    match=False,
                    method="fraction_decimal",
                    debug={"expected_format": correction},
                )
        except Exception as exc:
            logger.debug("[answer_authority] Fraction-decimal check skipped for Q%s: %s", q_id, exc)

        # 4. Try word problem arithmetic (CHECK 8 equivalent)
        try:
            wp_result = _extract_word_problem_arithmetic(question_text)
            if wp_result is not None:
                _wp_expr, wp_computed = wp_result
                if _answers_match(stored_answer, wp_computed):
                    return AnswerVerdict(
                        question_id=q_id,
                        declared_answer=stored_answer,
                        authoritative_answer=self._format_number(wp_computed),
                        match=True,
                        method="word_problem",
                        debug={"expression": _wp_expr, "computed": wp_computed},
                    )
                else:
                    return AnswerVerdict(
                        question_id=q_id,
                        declared_answer=stored_answer,
                        authoritative_answer=self._format_number(wp_computed),
                        match=False,
                        method="word_problem",
                        debug={"expression": _wp_expr, "computed": wp_computed},
                    )
        except Exception as exc:
            logger.error("[answer_authority] Word problem check failed for Q%s: %s", q_id, exc)
            return AnswerVerdict(
                question_id=q_id,
                declared_answer=stored_answer,
                authoritative_answer=None,
                match=None,
                method="word_problem",
                debug={"error": str(exc)},
            )

        # 5. No solver could verify
        return AnswerVerdict(
            question_id=q_id,
            declared_answer=stored_answer,
            authoritative_answer=None,
            match=None,
            method="unverifiable",
            debug={"reason": "no expression found"},
        )

    def verify_worksheet(self, questions: list[dict], subject: str) -> list[AnswerVerdict]:
        """Verify all questions in a worksheet. Returns list of verdicts."""
        return [self.verify_question(q, subject) for q in questions]

    @staticmethod
    def _format_number(computed: float) -> str:
        """Format computed number as clean string."""
        if computed == int(computed):
            return str(int(computed))
        return f"{computed:.4f}".rstrip("0").rstrip(".")

    @staticmethod
    def _verify_error_detection(
        q_id: str,
        question_text: str,
        stored_answer: str,
        validator_fn,
    ) -> AnswerVerdict:
        """Verify error_detection answer format (Bug C in CHECK 4)."""
        try:
            correction = validator_fn(question_text, stored_answer)
            if correction is not None:
                return AnswerVerdict(
                    question_id=q_id,
                    declared_answer=stored_answer,
                    authoritative_answer=correction,
                    match=False,
                    method="error_detection",
                    debug={"expected": correction},
                )
            return AnswerVerdict(
                question_id=q_id,
                declared_answer=stored_answer,
                authoritative_answer=None,
                match=None,
                method="error_detection",
                debug={"reason": "no mismatch detected"},
            )
        except Exception as exc:
            logger.debug("[answer_authority] Error detection check skipped for Q%s: %s", q_id, exc)
            return AnswerVerdict(
                question_id=q_id,
                declared_answer=stored_answer,
                authoritative_answer=None,
                match=None,
                method="error_detection",
                debug={"error": str(exc)},
            )


# Module-level singleton
_authority: Optional[AnswerAuthority] = None


def get_answer_authority() -> AnswerAuthority:
    """Get or create the singleton AnswerAuthority instance."""
    global _authority
    if _authority is None:
        _authority = AnswerAuthority()
    return _authority
