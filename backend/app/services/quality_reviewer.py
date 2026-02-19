"""
Quality Reviewer Agent — Agent 3 of 4 in the generation pipeline.

Runs four deterministic checks on the assembled question list, in order:

  CHECK 1 — Maths arithmetic validation (Maths subject only)
    Extracts simple A op B expressions from question text, computes the
    result via safe AST evaluation, and auto-corrects the stored answer
    if it is wrong. Marks q['_answer_corrected'] = True on any correction.
    Skips word problems and error_detection questions (intentionally wrong).

  CHECK 2 — Skill tag validation (all subjects)
    If q['skill_tag'] is not in context.valid_skill_tags, replaces it with
    the first valid tag and logs an error.  Skipped when valid_skill_tags
    is empty (unknown topic — no constraint to enforce).

  CHECK 3 — Grade-level word-count check (all subjects)
    Class 1–2 : flags questions with > 15 words.
    Class 3–5 : flags questions with > 25 words.
    Logs a warning but never auto-corrects language.

  CHECK 4 — Fraction and decimal answer format (Maths subject only)
    Catches three known LLM failure modes:
    A) Fraction addition stored as decimal float ("5.0" → "5/8")
    B) Fraction-to-decimal conversion stored with wrong magnitude ("3.0" → "0.3")
    C) error_detection answer agrees with the shown wrong answer instead of
       computing the real one ("334.0" → "434" for "289 + 145 = 334")

All checks are fail-open: an exception in any check is logged and skipped
so that generation is never blocked by the review layer.
"""
from __future__ import annotations

import ast
import logging
import operator
import re
from dataclasses import dataclass, field
from typing import Optional

from app.services.topic_intelligence import GenerationContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Safe arithmetic evaluator
# ---------------------------------------------------------------------------

# Allowlisted binary operators — no user-controlled code paths
_SAFE_OPS: dict = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
}


def _eval_node(node: ast.AST) -> Optional[float]:
    """Recursively evaluate an AST node. Returns None for unsupported nodes."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        operand = _eval_node(node.operand)
        return -operand if operand is not None else None
    if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_OPS:
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        if left is None or right is None:
            return None
        if isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)) and right == 0:
            return None
        return _SAFE_OPS[type(node.op)](left, right)
    return None  # variables, function calls, comparisons — all rejected


def _safe_eval(expr: str) -> Optional[float]:
    """
    Safely evaluate a simple arithmetic expression string.

    Only supports numeric literals and + - * / // % operators.
    Returns None if the expression is invalid or uses unsupported constructs.
    """
    try:
        tree = ast.parse(expr.strip(), mode="eval")
        return _eval_node(tree.body)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Arithmetic extractor
# ---------------------------------------------------------------------------

# Normalise Unicode operators to Python equivalents before parsing
_OP_NORMALISE = str.maketrans({"×": "*", "÷": "/", "–": "-", "−": "-"})

# Regex: exactly two non-negative integers separated by a basic operator
# Anchored loosely so it can appear inside longer question text
_SIMPLE_EXPR_RE = re.compile(
    r"(?<!\d)(\d+)\s*([+\-×÷*/])\s*(\d+)(?!\d)"
)

# Words that reliably indicate a word problem / narrative context
_NARRATIVE_WORDS = re.compile(
    r"\b(had|has|have|bought|sold|gave|gives|gets|took|left|total|many|much|"
    r"more|less|fewer|each|altogether|riya|aman|sneha|kiran|arjun|rohit|"
    r"priya|divya|school|class|teacher|students|children|bag|box|basket|"
    r"price|cost|pay|rupees|₹|kilometre|metre|litre|kilogram)\b",
    re.IGNORECASE,
)


def _extract_simple_arithmetic(question_text: str) -> Optional[tuple[str, float]]:
    """
    Try to extract a simple A op B expression from question text.

    Returns (python_expr_string, computed_result) or None.

    Skips questions that:
      - Contain narrative/word-problem language (> 4 narrative words or indicators)
      - Have blank/missing-number markers (_ or __)
      - Have no extractable A op B pattern
    """
    # Skip if it looks like a word problem
    if _NARRATIVE_WORDS.search(question_text):
        return None

    # Skip missing-number / fill-in-the-blank questions
    # Match underscores (fill blanks) or 2+ consecutive ? (placeholder blanks)
    # A single trailing ? is normal question punctuation — don't skip it.
    if re.search(r"_+|\?{2,}", question_text):
        return None

    # Normalise Unicode operators, then search
    normalised = question_text.translate(_OP_NORMALISE)
    m = _SIMPLE_EXPR_RE.search(normalised)
    if not m:
        return None

    a, op_sym, b = m.group(1), m.group(2), m.group(3)
    expr = f"{a} {op_sym} {b}"
    result = _safe_eval(expr)
    return (expr, result) if result is not None else None


def _answers_match(stored: str, computed: float) -> bool:
    """
    Return True if the stored answer (string) matches the computed result.

    Compares as integers when both values are whole numbers,
    floating-point otherwise (±0.01 tolerance).
    Returns True (no correction) when stored is not parseable as a number.
    """
    try:
        stored_num = float(str(stored).strip().replace(",", ""))
    except (ValueError, TypeError):
        return True  # non-numeric answer — not our job to correct
    if computed == int(computed) and stored_num == int(stored_num):
        return int(computed) == int(stored_num)
    return abs(computed - stored_num) < 0.01


# ---------------------------------------------------------------------------
# CHECK 4 — Fraction / decimal answer format validators
# ---------------------------------------------------------------------------

# A/B [+-] C/D  — same or different denominators
_FRAC_ADD_SUB_RE = re.compile(
    r"(\d+)/(\d+)\s*([+\-])\s*(\d+)/(\d+)"
)

# "A/B as a decimal" — fraction-to-decimal conversion questions
_FRAC_AS_DEC_RE = re.compile(
    r"(\d+)/(\d+)\s+as\s+a\s+decimal",
    re.IGNORECASE,
)

# "A op B = WRONG_ANSWER" — error_detection question pattern
_ERROR_DETECT_EXPR_RE = re.compile(
    r"(\d+)\s*([+\-×÷*/])\s*(\d+)\s*=\s*(\d+)"
)

_OP_NORMALISE_4 = str.maketrans({"×": "*", "÷": "/"})


def _fraction_str(numerator: int, denominator: int) -> str:
    """Return a reduced fraction string 'N/D' or whole number 'N'."""
    from math import gcd
    g = gcd(abs(numerator), abs(denominator))
    n, d = numerator // g, denominator // g
    return str(n) if d == 1 else f"{n}/{d}"


def _validate_fraction_answer(question_text: str, answer: str) -> Optional[str]:
    """
    For fraction addition/subtraction questions, ensure answer is in fraction form.

    Returns corrected answer string, or None if no correction is needed.
    Bug A: "3/8 + 2/8" → answer "5.0" should be "5/8".
    """
    m = _FRAC_ADD_SUB_RE.search(question_text)
    if not m:
        return None

    a, b, op, c, d = (
        int(m.group(1)), int(m.group(2)), m.group(3),
        int(m.group(4)), int(m.group(5)),
    )
    # Common denominator arithmetic
    if b == d:
        num = (a + c) if op == "+" else (a - c)
        correct = _fraction_str(num, b)
    else:
        # Cross-multiply
        num = (a * d + c * b) if op == "+" else (a * d - c * b)
        correct = _fraction_str(num, b * d)

    current = str(answer).strip()
    if current == correct:
        return None

    # Also accept if stored already equals the numeric value (right value, wrong format)
    # — in that case we still want fraction notation, so always return correct
    return correct


def _validate_fraction_to_decimal(question_text: str, answer: str) -> Optional[str]:
    """
    For fraction-to-decimal questions, ensure the decimal is correct.

    Returns corrected answer string, or None if no correction is needed.
    Bug B: "3/10 as a decimal" → answer "3.0" should be "0.3".
    """
    m = _FRAC_AS_DEC_RE.search(question_text)
    if not m:
        return None

    numerator, denominator = int(m.group(1)), int(m.group(2))
    if denominator == 0:
        return None

    result = numerator / denominator
    # Format: strip trailing zeros but keep at least one decimal place
    correct = f"{result:.10f}".rstrip("0")
    if correct.endswith("."):
        correct += "0"

    try:
        if abs(float(str(answer).strip()) - result) < 1e-9:
            return None  # already the right value
    except (ValueError, TypeError):
        pass

    return correct


def _validate_error_detection_answer(question_text: str, answer: str) -> Optional[str]:
    """
    For error_detection questions showing "A op B = WRONG", ensure the stored
    answer is the CORRECT computed value, not the wrong one from the question.

    Returns corrected answer string, or None if no correction is needed.
    Bug C: "289 + 145 = 334. What is the correct answer?" → "334.0" should be "434".
    """
    m = _ERROR_DETECT_EXPR_RE.search(question_text)
    if not m:
        return None

    expr = f"{m.group(1)} {m.group(2)} {m.group(3)}".translate(_OP_NORMALISE_4)
    result = _safe_eval(expr)
    if result is None:
        return None

    wrong_in_question = float(m.group(4))

    try:
        stored = float(str(answer).strip().replace(",", ""))
    except (ValueError, TypeError):
        return None

    # If stored already equals the computed correct answer → no fix needed
    if abs(stored - result) < 0.01:
        return None

    # If stored matches the wrong answer shown in the question → fix it
    if abs(stored - wrong_in_question) < 0.01:
        correct_str = (
            str(int(result)) if result == int(result)
            else f"{result:.4f}".rstrip("0").rstrip(".")
        )
        return correct_str

    return None


# ---------------------------------------------------------------------------
# Word-count limits by grade
# ---------------------------------------------------------------------------

def _word_limit(grade: int) -> int:
    return 15 if grade <= 2 else 25


# ---------------------------------------------------------------------------
# ReviewResult
# ---------------------------------------------------------------------------

@dataclass
class ReviewResult:
    """Output of QualityReviewerAgent.review_worksheet()."""
    questions: list   = field(default_factory=list)   # possibly corrected
    corrections: list = field(default_factory=list)   # human-readable log of corrections
    warnings: list    = field(default_factory=list)   # grade-level language warnings
    errors: list      = field(default_factory=list)   # skill-tag replacement log


# ---------------------------------------------------------------------------
# QualityReviewerAgent
# ---------------------------------------------------------------------------

class QualityReviewerAgent:
    """
    Agent 3 of 4 — post-generation quality gate.

    Runs three deterministic, fail-open checks on the assembled question list
    and returns a ReviewResult with (potentially corrected) questions and a
    structured log of every action taken.
    """

    def review_worksheet(
        self,
        questions: list,
        context: GenerationContext,
    ) -> ReviewResult:
        """
        Review and auto-correct the question list.

        Args:
            questions:  List of question dicts as produced by generate_all_questions().
            context:    GenerationContext from TopicIntelligenceAgent — provides
                        grade, subject, and valid_skill_tags.

        Returns:
            ReviewResult with corrected questions and structured logs.
        """
        result = ReviewResult(questions=list(questions))
        is_maths = context.subject.lower() in ("maths", "mathematics", "math")

        for q in result.questions:
            q_id = q.get("id", "?")
            slot_type = q.get("slot_type", "")
            question_text = q.get("question_text", "")

            # ── CHECK 1: Maths arithmetic validation ─────────────────────
            if is_maths and slot_type != "error_detection":
                try:
                    extracted = _extract_simple_arithmetic(question_text)
                    if extracted is not None:
                        expr, computed = extracted
                        stored = q.get("answer", "")
                        if not _answers_match(stored, computed):
                            correct_str = (
                                str(int(computed))
                                if computed == int(computed)
                                else f"{computed:.4f}".rstrip("0").rstrip(".")
                            )
                            msg = (
                                f"Q{q_id}: arithmetic corrected "
                                f"({expr} = {correct_str}, stored was '{stored}')"
                            )
                            logger.warning("[quality_reviewer] %s", msg)
                            q["answer"] = correct_str
                            q["_answer_corrected"] = True
                            result.corrections.append(msg)
                except Exception as exc:
                    logger.debug(
                        "[quality_reviewer] Check 1 skipped for Q%s: %s", q_id, exc
                    )

            # ── CHECK 2: Skill tag validation ────────────────────────────
            try:
                valid_tags = context.valid_skill_tags
                if valid_tags:
                    skill_tag = q.get("skill_tag", "")
                    if skill_tag not in valid_tags:
                        replacement = valid_tags[0]
                        msg = (
                            f"Q{q_id}: invalid skill_tag '{skill_tag}' "
                            f"replaced with '{replacement}'"
                        )
                        logger.error("[quality_reviewer] %s", msg)
                        q["skill_tag"] = replacement
                        result.errors.append(msg)
            except Exception as exc:
                logger.debug(
                    "[quality_reviewer] Check 2 skipped for Q%s: %s", q_id, exc
                )

            # ── CHECK 3: Grade-level word count ──────────────────────────
            try:
                grade = int(context.grade)
                limit = _word_limit(grade)
                word_count = len(question_text.split())
                if word_count > limit:
                    msg = (
                        f"Q{q_id}: question has {word_count} words "
                        f"(Grade {grade} limit is {limit})"
                    )
                    logger.warning("[quality_reviewer] %s", msg)
                    result.warnings.append(msg)
            except Exception as exc:
                logger.debug(
                    "[quality_reviewer] Check 3 skipped for Q%s: %s", q_id, exc
                )

            # ── CHECK 4: Fraction and decimal answer format ───────────────
            if is_maths:
                try:
                    stored_answer = q.get("answer", "")
                    correction: Optional[str] = None

                    if slot_type == "error_detection":
                        # Bug C: LLM agrees with the wrong answer shown in Q
                        correction = _validate_error_detection_answer(
                            question_text, stored_answer
                        )
                    else:
                        # Bug A: fraction addition stored as decimal float
                        correction = _validate_fraction_answer(
                            question_text, stored_answer
                        )
                        # Bug B: fraction-to-decimal stored with wrong magnitude
                        if correction is None:
                            correction = _validate_fraction_to_decimal(
                                question_text, stored_answer
                            )

                    if correction is not None:
                        msg = (
                            f"Q{q_id}: answer format corrected "
                            f"('{stored_answer}' → '{correction}')"
                        )
                        logger.warning("[quality_reviewer] %s", msg)
                        q["answer"] = correction
                        q["_answer_corrected"] = True
                        result.corrections.append(msg)
                except Exception as exc:
                    logger.debug(
                        "[quality_reviewer] Check 4 skipped for Q%s: %s", q_id, exc
                    )

        total = len(result.corrections)
        logger.info(
            "[quality_reviewer] Review complete: %d question(s), "
            "%d correction(s), %d warning(s), %d error(s)",
            len(result.questions),
            len(result.corrections),
            len(result.warnings),
            len(result.errors),
        )
        return result


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_REVIEWER: Optional[QualityReviewerAgent] = None


def get_quality_reviewer() -> QualityReviewerAgent:
    """Return the module-level singleton."""
    global _REVIEWER
    if _REVIEWER is None:
        _REVIEWER = QualityReviewerAgent()
    return _REVIEWER
