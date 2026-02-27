"""
Misconception Taxonomy — deterministic classification of student errors.

Scope: Maths Class 1–3 (addition, subtraction, number sense, place value,
multiplication, division, word problems, time, money).

All detection is pure arithmetic + regex. No LLM.
"""

from __future__ import annotations

import ast
import logging
import operator
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Taxonomy — flat dict of misconception types
# ---------------------------------------------------------------------------

MISCONCEPTION_TAXONOMY: dict[str, dict] = {
    "ADD_NO_CARRY": {
        "display": "Forgets to carry in addition",
        "domain": "addition",
    },
    "ADD_CARRY_WRONG_COLUMN": {
        "display": "Carries to wrong column",
        "domain": "addition",
    },
    "ADD_DIGIT_CONCAT": {
        "display": "Concatenates digits instead of adding",
        "domain": "addition",
    },
    "SUB_NO_BORROW": {
        "display": "Forgets to borrow in subtraction",
        "domain": "subtraction",
    },
    "SUB_REVERSE_OPERANDS": {
        "display": "Subtracts smaller from larger per column",
        "domain": "subtraction",
    },
    "SUB_BORROW_NOT_DECREMENTED": {
        "display": "Borrows but doesn't reduce next column",
        "domain": "subtraction",
    },
    "NUM_REVERSE_DIGITS": {
        "display": "Reverses digit order",
        "domain": "number_sense",
    },
    "NUM_PLACE_VALUE_CONFUSION": {
        "display": "Confuses tens and ones",
        "domain": "place_value",
    },
    "MULT_TABLE_ERROR": {
        "display": "Wrong multiplication fact",
        "domain": "multiplication",
    },
    "MULT_ADD_INSTEAD": {
        "display": "Adds instead of multiplying",
        "domain": "multiplication",
    },
    "DIV_REMAINDER_IGNORED": {
        "display": "Ignores remainder",
        "domain": "division",
    },
    "WP_WRONG_OPERATION": {
        "display": "Wrong operation for word problem",
        "domain": "word_problems",
    },
    "TIME_HOUR_MINUTE_SWAP": {
        "display": "Confuses hours and minutes",
        "domain": "time",
    },
    "MONEY_UNIT_CONFUSION": {
        "display": "Confuses rupees and paise",
        "domain": "money",
    },
    "UNKNOWN": {
        "display": "Unclassified error",
        "domain": "general",
    },
}

# ---------------------------------------------------------------------------
# Safe eval (same pattern as quality_reviewer.py)
# ---------------------------------------------------------------------------

_SAFE_OPS: dict = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
}


def _eval_node(node: ast.AST) -> Optional[float]:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_OPS:
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        if left is not None and right is not None:
            try:
                return _SAFE_OPS[type(node.op)](left, right)
            except (ZeroDivisionError, OverflowError):
                return None
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        val = _eval_node(node.operand)
        return -val if val is not None else None
    return None


def _safe_eval(expr: str) -> Optional[float]:
    try:
        tree = ast.parse(expr.strip(), mode="eval")
        return _eval_node(tree.body)
    except (SyntaxError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Operand extraction patterns
# ---------------------------------------------------------------------------

_OP_NORMALISE = str.maketrans({"×": "*", "÷": "/", "–": "-", "−": "-"})
_SIMPLE_EXPR_RE = re.compile(r"(\d+)\s*([+\-×÷*/])\s*(\d+)")
_WORD_PROBLEM_OPS_RE = re.compile(
    r"\b(add|plus|sum|total|more|gave|bought|got|together|"
    r"subtract|minus|less|took|gave away|remaining|left|difference|"
    r"multiply|times|groups of|each|"
    r"divide|share|split|equally|per)\b",
    re.IGNORECASE,
)


def _extract_operands(question_text: str) -> Optional[tuple[int, str, int]]:
    """Extract (a, op, b) from question text. Returns None if not found."""
    norm = question_text.translate(_OP_NORMALISE)
    m = _SIMPLE_EXPR_RE.search(norm)
    if m:
        try:
            a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
            return (a, op, b)
        except ValueError:
            pass
    return None


def _parse_int(s: str) -> Optional[int]:
    """Parse a string as an integer, stripping whitespace and common suffixes."""
    s = s.strip().rstrip(".").strip()
    # Handle answers like "23 apples" — take the leading number
    m = re.match(r"^(-?\d+)", s)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    return None


def _digits_reversed(a: int, b: int) -> bool:
    """Check if b is the digit-reversal of a (e.g., 32 vs 23)."""
    sa, sb = str(abs(a)), str(abs(b))
    return len(sa) == len(sb) and len(sa) >= 2 and sa == sb[::-1]


# ---------------------------------------------------------------------------
# Column-wise arithmetic helpers (for carry/borrow detection)
# ---------------------------------------------------------------------------


def _no_carry_addition(a: int, b: int) -> int:
    """Add a + b without carrying: 28 + 35 → 53 (not 63)."""
    sa, sb = str(a), str(b)
    max_len = max(len(sa), len(sb))
    sa, sb = sa.zfill(max_len), sb.zfill(max_len)
    result = ""
    for da, db in zip(sa, sb):
        col_sum = int(da) + int(db)
        result += str(col_sum % 10)
    try:
        return int(result)
    except ValueError:
        return -1


def _no_borrow_subtraction(a: int, b: int) -> int:
    """Subtract a - b without borrowing: each column is |digit_a - digit_b|."""
    sa, sb = str(a), str(b)
    max_len = max(len(sa), len(sb))
    sa, sb = sa.zfill(max_len), sb.zfill(max_len)
    result = ""
    for da, db in zip(sa, sb):
        result += str(abs(int(da) - int(db)))
    try:
        return int(result)
    except ValueError:
        return -1


def _reversed_column_subtraction(a: int, b: int) -> int:
    """Subtract column-by-column, always larger - smaller per column."""
    sa, sb = str(a), str(b)
    max_len = max(len(sa), len(sb))
    sa, sb = sa.zfill(max_len), sb.zfill(max_len)
    result = ""
    for da, db in zip(sa, sb):
        result += str(abs(int(da) - int(db)))
    try:
        return int(result)
    except ValueError:
        return -1


# ---------------------------------------------------------------------------
# Classification function
# ---------------------------------------------------------------------------


def classify_misconception(
    skill_tag: str,
    correct_answer: str,
    student_answer: str,
    question_text: str = "",
) -> str:
    """
    Deterministic classification of a student error.

    Returns a misconception ID from MISCONCEPTION_TAXONOMY.
    Called only when the answer is known to be incorrect.
    """
    correct_int = _parse_int(correct_answer)
    student_int = _parse_int(student_answer)
    operands = _extract_operands(question_text)
    skill_lower = (skill_tag or "").lower()

    # ── Addition misconceptions ──
    if "add" in skill_lower or "carry" in skill_lower:
        if operands and correct_int is not None and student_int is not None:
            a, op, b = operands
            if op in ("+",):
                # Digit concatenation: 5 + 7 = 57
                concat_result = _parse_int(f"{a}{b}")
                if student_int == concat_result:
                    return "ADD_DIGIT_CONCAT"

                # No carry: 28 + 35 = 53 (instead of 63)
                no_carry = _no_carry_addition(a, b)
                if student_int == no_carry and no_carry != (a + b):
                    return "ADD_NO_CARRY"

                # Carry to wrong column: off by a power of 10
                diff = abs(student_int - correct_int)
                if diff in (10, 100, 1000) and student_int != correct_int:
                    return "ADD_CARRY_WRONG_COLUMN"

    # ── Subtraction misconceptions ──
    if "sub" in skill_lower or "borrow" in skill_lower:
        if operands and correct_int is not None and student_int is not None:
            a, op, b = operands
            if op in ("-",):
                # No borrow
                no_borrow = _no_borrow_subtraction(a, b)
                if student_int == no_borrow and no_borrow != (a - b):
                    return "SUB_NO_BORROW"

                # Reversed column subtraction
                reversed_col = _reversed_column_subtraction(a, b)
                if student_int == reversed_col and reversed_col != (a - b):
                    return "SUB_REVERSE_OPERANDS"

                # Borrow not decremented: off by exactly 10
                if abs(student_int - correct_int) == 10:
                    return "SUB_BORROW_NOT_DECREMENTED"

    # ── Multiplication misconceptions ──
    if "mult" in skill_lower or "times" in skill_lower:
        if operands and correct_int is not None and student_int is not None:
            a, op, b = operands
            if op in ("*", "×"):
                # Added instead of multiplying
                if student_int == a + b:
                    return "MULT_ADD_INSTEAD"

                # Close to correct (off by one factor) → table error
                if correct_int != 0 and abs(student_int - correct_int) <= max(a, b):
                    return "MULT_TABLE_ERROR"

    # ── Division misconceptions ──
    if "div" in skill_lower or "share" in skill_lower:
        if operands and correct_int is not None and student_int is not None:
            a, op, b = operands
            if op in ("/", "÷") and b != 0:
                # Ignored remainder: gave floor instead of full answer
                if student_int == a // b and correct_int != a // b:
                    return "DIV_REMAINDER_IGNORED"

    # ── Number sense / place value ──
    if "number" in skill_lower or "place" in skill_lower or "digit" in skill_lower:
        if correct_int is not None and student_int is not None:
            if _digits_reversed(correct_int, student_int):
                return "NUM_REVERSE_DIGITS"

            # Place value confusion: off by factor of 10
            if correct_int != 0 and student_int != 0:
                ratio = student_int / correct_int
                if ratio in (10, 0.1):
                    return "NUM_PLACE_VALUE_CONFUSION"

    # ── Word problem: wrong operation ──
    if "word" in skill_lower or "wp" in skill_lower:
        if operands and correct_int is not None and student_int is not None:
            a, _, b = operands
            alt_results = {a + b, a - b, abs(a - b), a * b}
            if b != 0:
                alt_results.add(a // b)
            alt_results.discard(correct_int)
            if student_int in alt_results:
                return "WP_WRONG_OPERATION"

    # ── Time: hour/minute swap ──
    if "time" in skill_lower or "clock" in skill_lower:
        # Check for HH:MM swap pattern in answers
        time_re = re.compile(r"(\d{1,2}):(\d{2})")
        c_match = time_re.search(correct_answer)
        s_match = time_re.search(student_answer)
        if c_match and s_match:
            ch, cm = c_match.group(1), c_match.group(2)
            sh, sm = s_match.group(1), s_match.group(2)
            if ch == sm and cm == sh:
                return "TIME_HOUR_MINUTE_SWAP"

    # ── Money: unit confusion ──
    if "money" in skill_lower or "rupee" in skill_lower or "coin" in skill_lower:
        if correct_int is not None and student_int is not None:
            if correct_int != 0:
                ratio = student_int / correct_int
                if ratio in (100, 0.01):
                    return "MONEY_UNIT_CONFUSION"

    return "UNKNOWN"
