"""
Quality Reviewer Agent — Agent 3 of 4 in the generation pipeline.

Runs four deterministic checks on the assembled question list, in order:

  CHECK 1 — Maths answer verification (Maths subject only)
    Uses AnswerAuthority to verify ALL maths answers (including error_detection)
    via AST evaluation. Sets q['_answer_mismatch'] = True on mismatch
    (does NOT auto-correct — verify-and-block approach).

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

  CHECK 9 — LLM artifact detection (all subjects)
    Flags questions containing LLM conversational patterns ("As an AI…",
    "Here's a…", "Let me…").  Nulls hint if artifact found there.

  CHECK 10 — Hindi language purity (Hindi worksheets)
    Flags questions where Devanagari text contains Latin-script words
    (code-mixing like "कितने pencils हैं?").

  CHECK 14 — MCQ answer-in-options validation (all subjects)
    If an MCQ answer is not in the options list, tries to match from
    the explanation text. If no match found, flags for regeneration.

  CHECK 15 — True/False answer format enforcement (all subjects)
    If a true_false question has an answer that isn't "True" or "False"
    (e.g. "1/3"), derives the boolean from the explanation and corrects.

  CHECK 16 — Hindi question instruction vs answer consistency
    If a Hindi question asks for बहुवचन (plural) but the answer/explanation
    gives एकवचन (singular), flags for regeneration.

  CHECK 17 — Round number auto-fix for simple arithmetic (Maths only)
    If a simple A op B question has both operands as multiples of 5,
    nudges one operand by +1..3 and recomputes the answer. Skips word
    problems, error_detection, and complex expressions.

CHECK 1 is fail-CLOSED for arithmetic: if extraction succeeds but correction
throws, the question is marked _math_unverified=True so the caller can act.
All other checks are fail-open: an exception is logged and skipped.
"""

from __future__ import annotations

import ast
import json
import logging
import operator
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from app.services.topic_intelligence import GenerationContext

# ---------------------------------------------------------------------------
# Grade profiles — loaded once at module start (avoids circular import)
# ---------------------------------------------------------------------------
_GRADE_PROFILES_PATH = Path(__file__).parent.parent / "data" / "grade_profiles.json"
GRADE_PROFILES: dict = json.loads(_GRADE_PROFILES_PATH.read_text(encoding="utf-8"))

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Parent confidence block validation (CHECK 22)
# ---------------------------------------------------------------------------

_GENERIC_PARENT_RE = re.compile(
    r"(?i)^(practice regularly|keep practicing|revise daily|"
    r"help your child|encourage your child|make sure to practice|"
    r"practice makes perfect|review the concepts)$"
)


def validate_parent_blocks(worksheet: dict) -> tuple[bool, list[str]]:
    """
    Validate worksheet-level parent confidence fields.

    Returns (all_complete, warnings) where all_complete is True only when
    all parent blocks are present and non-generic.
    """
    warnings: list[str] = []
    skill_focus = (worksheet.get("skill_focus") or "").strip()
    common_mistake = (worksheet.get("common_mistake") or "").strip()
    parent_tip = (worksheet.get("parent_tip") or "").strip()
    learning_objectives = worksheet.get("learning_objectives") or []

    if not skill_focus:
        warnings.append("[parent_block] missing skill_focus")
    if not common_mistake:
        warnings.append("[parent_block] missing common_mistake")
    if not learning_objectives or len(learning_objectives) < 1:
        warnings.append("[parent_block] missing learning_objectives")
    if parent_tip and _GENERIC_PARENT_RE.match(parent_tip):
        warnings.append("[parent_block] generic parent_tip")
    if common_mistake and _GENERIC_PARENT_RE.match(common_mistake):
        warnings.append("[parent_block] generic common_mistake")

    all_complete = len(warnings) == 0
    return all_complete, warnings


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
    except Exception as e:
        logger.warning("Safe eval failed for expression '%s': %s", expr, e)
        return None


# ---------------------------------------------------------------------------
# Arithmetic extractor
# ---------------------------------------------------------------------------

# Normalise Unicode operators to Python equivalents before parsing
_OP_NORMALISE = str.maketrans({"×": "*", "÷": "/", "–": "-", "−": "-"})

# Regex: exactly two non-negative integers separated by a basic operator
# Anchored loosely so it can appear inside longer question text
_SIMPLE_EXPR_RE = re.compile(r"(?<!\d)(\d+)\s*([+\-×÷*/])\s*(\d+)(?!\d)")

# Words that reliably indicate a word problem / narrative context
_NARRATIVE_WORDS = re.compile(
    r"\b(had|has|have|bought|sold|gave|gives|gets|took|left|total|many|much|"
    r"more|less|fewer|each|altogether|riya|aman|sneha|kiran|arjun|rohit|"
    r"priya|divya|school|class|teacher|students|children|bag|box|basket|"
    r"price|cost|pay|rupees|₹|kilometre|metre|litre|kilogram)\b",
    re.IGNORECASE,
)


# ── Word-problem operation keywords ──────────────────────────────────────
_WP_ADD_WORDS = re.compile(r"\b(total|altogether|combined|in all|sum|more than|added|gave .* more)\b", re.I)
_WP_SUB_WORDS = re.compile(r"\b(left|remaining|gave away|took away|fewer|less than|difference|ate|lost|spent)\b", re.I)
_WP_MUL_WORDS = re.compile(r"\b(each|every|per|times|groups of|rows of|sets of)\b", re.I)

# Matches integers and decimals (e.g. 5, 0.75, 12.5) — not preceded/followed by word chars
_WP_NUM_RE = re.compile(r"(?<!\w)(\d+(?:\.\d+)?)(?!\w)")


def _fmt(n: float) -> str:
    """Format a number: show as int if whole, else as float."""
    return str(int(n)) if n == int(n) else str(n)


def _extract_word_problem_arithmetic(question_text: str) -> Optional[tuple[str, float]]:
    """Try to extract operation + numbers from a word problem.

    Returns (expression_str, computed_value) or None.
    Handles 2-number and 3-number word problems (Class 1-5).

    3-number patterns handled:
      - "X items at Y each and Z more" → X*Y + Z
      - "had X, gave Y, then gave Z"  → X - Y - Z
      - "X + Y + Z altogether"        → X + Y + Z
      - "X groups of Y each, ate Z"   → X*Y - Z
    """
    raw_matches = _WP_NUM_RE.findall(question_text)
    numbers = [float(n) for n in raw_matches if 0 < float(n) < 100000]

    if len(numbers) == 2:
        a, b = numbers
        has_add = _WP_ADD_WORDS.search(question_text)
        has_sub = _WP_SUB_WORDS.search(question_text)
        has_mul = _WP_MUL_WORDS.search(question_text)

        # Addition keywords trump subtraction when both present
        # e.g. "ate 2... ate 4... How many in all?" → addition
        if has_add and has_sub:
            return (f"{_fmt(a)} + {_fmt(b)}", float(a + b))
        elif has_mul:
            return (f"{_fmt(a)} * {_fmt(b)}", float(a * b))
        elif has_sub:
            big, small = max(a, b), min(a, b)
            return (f"{_fmt(big)} - {_fmt(small)}", float(big - small))
        elif has_add:
            return (f"{_fmt(a)} + {_fmt(b)}", float(a + b))
        return None

    if len(numbers) == 3:
        a, b, c = numbers
        has_mul = _WP_MUL_WORDS.search(question_text)
        has_sub = _WP_SUB_WORDS.search(question_text)
        has_add = _WP_ADD_WORDS.search(question_text)

        # Pattern: "X items at Y each, then spent/gave/lost Z" → X*Y - Z
        if has_mul and has_sub:
            return (f"{_fmt(a)} * {_fmt(b)} - {_fmt(c)}", float(a * b - c))

        # Pattern: "X items at Y each, plus Z more" → X*Y + Z
        if has_mul and has_add:
            return (f"{_fmt(a)} * {_fmt(b)} + {_fmt(c)}", float(a * b + c))

        # Pattern: "X groups/sets of Y each" (c is the question number, e.g. "how many")
        # Only if multiplication is clear and no other operation
        if has_mul and not has_sub and not has_add:
            return (f"{_fmt(a)} * {_fmt(b)}", float(a * b))

        # Pattern: "had X, gave Y, then gave Z" → X - Y - Z
        if has_sub and not has_mul:
            big = max(numbers)
            rest = sorted([n for n in numbers if n != big], reverse=True)
            result = big - sum(rest)
            expr = f"{_fmt(big)} - {_fmt(rest[0])} - {_fmt(rest[1])}"
            return (expr, float(result))

        # Pattern: "X + Y + Z altogether/total/in all" → sum
        if has_add and not has_sub and not has_mul:
            return (f"{_fmt(a)} + {_fmt(b)} + {_fmt(c)}", float(a + b + c))

    # 4+ numbers — too ambiguous, skip
    return None


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


# Regex: a run of digits, operators (+−*/), optional parens, with ≥1 operator
_MULTI_EXPR_RE = re.compile(
    r"(?<![a-zA-Z\d])"
    r"(\(?\d+(?:\.\d+)?\)?"
    r"(?:\s*[+\-*/]\s*\(?\d+(?:\.\d+)?\)?)+)"
    r"(?![a-zA-Z\d])"
)


def _extract_arithmetic_expression(question_text: str) -> Optional[tuple[str, float]]:
    """Extract a (possibly multi-step) arithmetic expression from question text.

    Handles: a+b+c, a*b+c, (a+b)*c. Falls back to _extract_simple_arithmetic.
    Skips word problems and blank-marker questions (same guards).
    """
    if _NARRATIVE_WORDS.search(question_text):
        return None
    if re.search(r"_+|\?{2,}", question_text):
        return None

    normalised = question_text.translate(_OP_NORMALISE)
    matches = _MULTI_EXPR_RE.findall(normalised)
    if matches:
        best = max(matches, key=len).strip()
        result = _safe_eval(best)
        if result is not None:
            return (best, result)

    # Fallback to simple binary extraction
    return _extract_simple_arithmetic(question_text)


def _answers_match(stored: str, computed: float) -> bool:
    """
    Return True if the stored answer (string) matches the computed result.

    Uses the centralized answer normalizer for exact comparison (handles
    fractions, decimals, integers). Falls back to float tolerance (±0.01)
    if normalization is unavailable.
    Returns True (no correction) when stored is not parseable as a number.
    """
    try:
        from app.utils.answer_normalizer import normalize_numeric

        stored_norm = normalize_numeric(str(stored).strip())
        computed_norm = normalize_numeric(str(computed))
        if stored_norm is not None and computed_norm is not None:
            if stored_norm == computed_norm:
                return True
            # Don't return False yet — fall through to float tolerance
            # for cases like "3.33" vs 3.333... (rounding)
    except Exception as exc:
        logger.debug("[quality_reviewer] answer normalizer unavailable, using float fallback: %s", exc)

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
_FRAC_ADD_SUB_RE = re.compile(r"(\d+)/(\d+)\s*([+\-])\s*(\d+)/(\d+)")

# "A/B as a decimal" — fraction-to-decimal conversion questions
_FRAC_AS_DEC_RE = re.compile(
    r"(\d+)/(\d+)\s+as\s+a\s+decimal",
    re.IGNORECASE,
)

# "A op B = WRONG_ANSWER" — error_detection question pattern
_ERROR_DETECT_EXPR_RE = re.compile(r"(\d+)\s*([+\-×÷*/])\s*(\d+)\s*=\s*(\d+)")

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
        int(m.group(1)),
        int(m.group(2)),
        m.group(3),
        int(m.group(4)),
        int(m.group(5)),
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
        correct_str = str(int(result)) if result == int(result) else f"{result:.4f}".rstrip("0").rstrip(".")
        return correct_str

    return None


# ---------------------------------------------------------------------------
# CHECK 5 — Time fact validator
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Hint answer-leakage detector (used in CHECK 6)
# ---------------------------------------------------------------------------

_REVEALS_ANSWER_RE = re.compile(r"the\s+(?:correct\s+)?answer\s+is", re.IGNORECASE)


def _hint_leaks_answer(hint: str, answer: str) -> bool:
    """
    Return True when the hint effectively gives away the answer.

    Catches two patterns:
      1. Explicit "the answer is …" phrase in the hint.
      2. The hint contains a 3-consecutive-word run that also appears in the
         answer string (answer phrases embedded verbatim in the hint).
    """
    if not hint or not answer:
        return False
    hint_lower = hint.lower()
    # Pattern 1 — "the answer is" / "the correct answer is"
    if _REVEALS_ANSWER_RE.search(hint_lower):
        return True
    # Pattern 2 — 3-word overlap window
    answer_words = answer.lower().split()
    for i in range(len(answer_words) - 2):
        phrase = " ".join(answer_words[i : i + 3])
        if phrase in hint_lower:
            return True
    return False


# Map (question pattern) → correct string answer for common factual time blanks.
# Each entry: (compiled regex to match question_text, correct answer string)
_TIME_FACT_MAP: list[tuple] = [
    (re.compile(r"seconds?\s+in\s+(?:a\s+)?(?:1\s+)?minute", re.I), "60"),
    (re.compile(r"minutes?\s+in\s+(?:a\s+)?(?:1\s+)?hour", re.I), "60"),
    (re.compile(r"hours?\s+in\s+(?:a\s+)?(?:1\s+)?day", re.I), "24"),
    (re.compile(r"days?\s+in\s+(?:a\s+)?(?:1\s+)?week", re.I), "7"),
    (re.compile(r"months?\s+in\s+(?:a\s+)?(?:1\s+)?year", re.I), "12"),
    (re.compile(r"days?\s+in\s+(?:a\s+)?(?:1\s+)?year", re.I), "365"),
    (re.compile(r"weeks?\s+in\s+(?:a\s+)?(?:1\s+)?year", re.I), "52"),
]


def _check_time_fact(question_text: str, answer: str) -> Optional[str]:
    """
    Return the correct answer if the stored answer contradicts a known time fact,
    or None if no correction is needed.

    Only fires for fill-in-the-blank questions (question contains '_').
    Only corrects when the stored answer is a plain number that differs from
    the expected value.
    """
    # Only fill-in-the-blank questions are relevant
    if "_" not in question_text:
        return None

    for pattern, expected in _TIME_FACT_MAP:
        if not pattern.search(question_text):
            continue
        # Answer matches expected — all good
        stored_clean = str(answer).strip().lstrip("0") or "0"
        if stored_clean == expected:
            return None
        # Answer is a non-empty number that differs — correct it
        try:
            float(str(answer).strip())  # parseable as number
            return expected
        except (ValueError, TypeError):
            pass  # non-numeric answer (e.g. "sixty") — leave it alone
    return None


# ---------------------------------------------------------------------------
# Word-count limits by grade
# ---------------------------------------------------------------------------


def _word_limit(grade: int) -> int:
    return 15 if grade <= 2 else 25


# Filler phrases that can be removed without changing question meaning
_FILLER_PATTERNS = [
    (re.compile(r"\b[Ii]n the following\s*", re.I), ""),
    (re.compile(r"\bthe following\s+", re.I), "the "),  # bare "the following X" → "the X"
    (re.compile(r"\bLook at the (?:picture|diagram|image|triangle|figure|shape)(?:\s+given)?\.\s*", re.I), ""),
    (re.compile(r"\bRead the (?:passage|text|paragraph) (?:below|given)\s*(?:and|\.)\s*", re.I), ""),
    (re.compile(r"\bGiven (?:below|that)\s*,?\s*", re.I), ""),
    (re.compile(r"\b(?:mentioned|shown|listed) below\s*,?\s*", re.I), ""),
    # LLM-ism prefixes: "Help X figure out:", "Can you find:", "Let's figure out:"
    (re.compile(r"\bHelp \w+ (?:figure out|solve this|solve|find|at the|with the|during)\b[:\.\s]*", re.I), ""),
    (re.compile(r"\bCan you (?:find|solve|figure out|help|tell)\b[:\.\s]*", re.I), ""),
    (re.compile(r"\bLet'?s (?:figure out|find out|solve|help|try)\b[:\.\s]*", re.I), ""),
    (re.compile(r"\bHere'?s a\b[:\.\s]*", re.I), ""),
]


def _strip_filler_phrases(text: str) -> str:
    """Remove phantom-reference filler phrases unconditionally."""
    cleaned = text
    for pattern, replacement in _FILLER_PATTERNS:
        cleaned = pattern.sub(replacement, cleaned).strip()
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned


_AGGRESSIVE_TRIM_PATTERNS = [
    # Remove "please" / "try to" / "now"
    (re.compile(r"\bplease\b\s*", re.I), ""),
    (re.compile(r"\bnow\b,?\s*", re.I), ""),
    # Remove scene-setting adjectives
    (re.compile(r"\b(big|small|little|beautiful|lovely|nice|colourful|special|favourite)\s+", re.I), ""),
    # Remove "very" / "really"
    (re.compile(r"\b(very|really|so)\s+", re.I), ""),
    # Remove "his/her mother/father told him/her to" patterns
    (re.compile(r"\b\w+ (?:told|asked|tells|asks) (?:him|her|them) to\s+", re.I), ""),
    # Simplify "How many X does she/he have in total?" → "How many X in total?"
    (re.compile(r"\bdoes (?:she|he|they) have\b", re.I), "are there"),
    # Remove "one day, " / "once upon a time, "
    (re.compile(r"\b(one day|once upon a time),?\s+", re.I), ""),
    # Remove "together" when redundant in "how many ... together"
    (re.compile(r"\btogether\b\s*", re.I), ""),
]


def _trim_question_text(text: str, limit: int) -> str | None:
    """Remove common filler phrases and verbose patterns to reduce word count.

    First tries light filler stripping, then aggressive trimming if needed.
    Returns trimmed text if word count was reduced, else None.
    """
    # Phase 1: light filler strip
    trimmed = _strip_filler_phrases(text)
    if len(trimmed.split()) <= limit:
        return trimmed if len(trimmed.split()) < len(text.split()) else None

    # Phase 2: aggressive trimming
    for pattern, replacement in _AGGRESSIVE_TRIM_PATTERNS:
        trimmed = pattern.sub(replacement, trimmed).strip()
    trimmed = re.sub(r"\s{2,}", " ", trimmed)
    return trimmed if len(trimmed.split()) < len(text.split()) else None


# ---------------------------------------------------------------------------
# LLM artifact detection (CHECK 9)
# ---------------------------------------------------------------------------

_LLM_ARTIFACT_RE = re.compile(
    r"(?i)\b(as an ai|here'?s a|let me|i'?ll help|i am a language model"
    r"|sure!? (?:here|let)|certainly!? (?:here|let)|i'?d be happy to)",
)


def _contains_llm_artifact(text: str) -> bool:
    """Return True if text contains LLM conversational artifacts."""
    return bool(_LLM_ARTIFACT_RE.search(text))


# ---------------------------------------------------------------------------
# Hindi language purity check (CHECK 10)
# ---------------------------------------------------------------------------

_LATIN_IN_DEVANAGARI_RE = re.compile(r"[a-zA-Z]{2,}")
_DEVANAGARI_CHAR_RE = re.compile(r"[\u0900-\u097F]")

# Legitimate English abbreviations/units that may appear in Hindi text.
# These should NOT trigger code-mixing detection.
_HINDI_ENGLISH_ALLOWLIST = {
    # Units of measurement
    "km",
    "cm",
    "mm",
    "kg",
    "mg",
    "ml",
    # Common abbreviations
    "TV",
    "AC",
    "DNA",
    "RNA",
    "NCERT",
    "CBSE",
    "UPI",
    "ATM",
    "OTP",
    "SMS",
    "SIM",
    "USB",
    "CD",
    "DVD",
    "LED",
    "FM",
    "AM",
    "PM",
}

# Indian proper names (from worksheet_generator._INDIAN_NAMES) are legitimate
# in Hindi text and should not trigger code-mixing detection.
# Dynamically loaded to stay in sync.
try:
    from app.services.worksheet_generator import _INDIAN_NAMES as _NAMES_LIST

    _HINDI_ENGLISH_ALLOWLIST |= set(_NAMES_LIST)
except ImportError:
    pass

# Engagement framing words injected by the LLM or CHECK 11 — these get
# stripped later but should not trigger code-mixing detection before that.
_HINDI_ENGLISH_ALLOWLIST |= {
    "Help",
    "help",
    "solve",
    "Solve",
    "find",
    "Find",
    "figure",
    "Figure",
    "out",
    "this",
    "Can",
    "can",
    "you",
    "Try",
    "try",
    "Let",
    "let",
    "Guess",
    "guess",
    "count",
    "Count",
    "work",
    "Work",
}

# Devanagari transliterations of common English words that LLMs inject into
# Hindi text.  These are pure Devanagari Unicode but semantically English.
_HINDI_TRANSLITERATION_BLOCKLIST = {
    # LLM-isms
    "हेल्प",
    "फिगर",
    "आउट",
    "फाइंड",
    "सॉल्व",
    "लेट्स",
    # English nouns commonly transliterated instead of using Hindi words
    "लोटस",
    "स्टार",
    "मून",
    "फ्लावर",
    "ट्री",
    "पेंसिल",
    "पेंसिल्स",
    "बुक",
    "बुक्स",
    "बॉल",
    "बॉक्स",
    "टेबल",
    "चेयर",
    "बैग",
    "ट्रेन",
    "कंप्यूटर",
    "प्रोजेक्ट",
    "डिज़ाइन",
    "पैटर्न",
    # Colors
    "रेड",
    "ब्लू",
    "ग्रीन",
    "यलो",
    "पिंक",
    "ऑरेंज",
    "पर्पल",
    "ब्लैक",
    "व्हाइट",
    "ब्राउन",
    # Animals
    "डॉग",
    "कैट",
    "रैबिट",
    "फिश",
    "बर्ड",
    "लायन",
    "टाइगर",
    "एलिफेंट",
    "मंकी",
    # Body parts
    "हैंड",
    "फेस",
    "नोज़",
    "आई",
    "ईयर",
    "फिंगर",
    "लेग",
    "फुट",
    # School items
    "रबर",
    "शार्पनर",
    "स्केल",
    "नोटबुक",
    "क्लास",
    "टीचर",
    "स्टूडेंट",
    "स्कूल",
    # Food / kitchen
    "गिलास",
    "प्लेट",
    "कप",
    "बोतल",
    "मिल्क",
    "ब्रेड",
    "केक",
    "बिस्किट",
    "जूस",
    # LLM verbs (transliterated English verbs)
    "कैलकुलेट",
    "ऑब्ज़र्व",
    "कंपेयर",
    "एक्सप्लेन",
    "अनालाइज़",
    # Additional LLM-isms and verbs
    "चेक",
    "मैच",
    "लिस्ट",
    "ग्रुप",
    "काउंट",
    "सिलेक्ट",
    "करेक्ट",
    "इनकरेक्ट",
    "ट्रू",
    "फॉल्स",
    "आंसर",
    "क्वेश्चन",
    "ऑप्शन",
    "एग्ज़ाम्पल",
    "प्रैक्टिस",
    "रिपीट",
    "कम्प्लीट",
    # Clothing / household
    "ड्रेस",
    "शर्ट",
    "पैंट",
    "शूज़",
    "सॉक्स",
    # Fruits / vegetables
    "एप्पल",
    "ऑरेंज",  # fruit sense
    "बनाना",  # banana (not Hindi बनाना=to make)
    "मैंगो",
    "ग्रेप्स",
    "टोमैटो",
    "पोटैटो",
    # Grammar terms transliterated
    "सिंगुलर",
    "प्लूरल",
    "एडजेक्टिव",
    "नाउन",
    "वर्ब",
    "सेंटेंस",
    "पैराग्राफ",
    # Numbers transliterated
    "नंबर",
    "ज़ीरो",
    "डबल",
    "ट्रिपल",
    # Misc common leaks
    "पिक्चर",
    "फोटो",
    "वीडियो",
    "गेम",
    "प्ले",
    "टाइम",
    "क्लॉक",
    "कलर",
    "शेप",
    "सर्कल",
    "स्क्वेयर",
    "ट्रायंगल",
    "रेक्टैंगल",
}


def _has_hindi_code_mixing(text: str) -> bool:
    """Return True if Devanagari text contains Latin-script words (code-mixing).

    Legitimate abbreviations/units in _HINDI_ENGLISH_ALLOWLIST are excluded.
    """
    if not _DEVANAGARI_CHAR_RE.search(text):
        return False  # Not Hindi text — skip
    matches = _LATIN_IN_DEVANAGARI_RE.findall(text)
    non_allowed = [m for m in matches if m not in _HINDI_ENGLISH_ALLOWLIST]
    return bool(non_allowed)


def _has_hindi_transliteration(text: str) -> bool:
    """Return True if Hindi text contains Devanagari-transliterated English words."""
    if not _DEVANAGARI_CHAR_RE.search(text):
        return False
    # Extract Devanagari word sequences (handles punctuation like "सन," or "बॉल।")
    words = set(re.findall(r"[\u0900-\u097F]+", text))
    return bool(words & _HINDI_TRANSLITERATION_BLOCKLIST)


# ---------------------------------------------------------------------------
# Render integrity patterns (CHECK 21)
_VISUAL_REF_RE = re.compile(
    r"(?i)\b(?:look at|see|observe|refer to|check|examine|study)"
    r"\s+(?:the\s+)?(?:picture|diagram|image|figure|table|chart|graph|number line|clock|grid|map|pattern)"
)
_TABLE_REF_RE = re.compile(r"(?i)\b(?:the following|given|below)\s+(?:table|chart|graph|diagram)")

# Fill-in-the-blank ambiguity patterns (CHECK 20)
# ---------------------------------------------------------------------------

_FB_BLANK_RE = re.compile(r"_{2,}|\.{3,}|\?{2,}|______|\[blank\]|\[___\]", re.IGNORECASE)
_FB_GENERIC_ANSWERS = frozenset(
    {
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "it",
        "this",
        "that",
        "of",
        "in",
        "on",
        "at",
        "to",
        "for",
        "with",
        "by",
        "from",
        "and",
        "or",
        "but",
        "not",
        "yes",
        "no",
        "very",
        "so",
        "too",
    }
)
_FB_SUBJECTIVE_RE = re.compile(
    r"(?i)(write a|write any|give an example|give a|name a|name any|"
    r"your own|your favou?rite|anything|any word|any name|any number|any suitable)"
)


# ---------------------------------------------------------------------------
# Self-contradiction detector (CHECK 7)
# ---------------------------------------------------------------------------


def _check_answer_self_contradiction(answer: str) -> bool:
    """
    Returns True if answer contains a self-contradiction pattern.
    Examples: starts with "More than X" but later says "less than X"
    """
    if not answer or len(answer) < 30:
        return False
    lower = answer.lower()
    # Pattern: "more than X" followed by "less than X" (or vice versa) for same value
    more_matches = re.findall(r"more than (\d+)", lower)
    less_matches = re.findall(r"less than (\d+)", lower)
    # If same number appears in both → contradiction
    if set(more_matches) & set(less_matches):
        return True
    # Pattern: explicit admission of initial error
    if "my initial reasoning was incorrect" in lower or "i was wrong" in lower:
        return True
    return False


# ---------------------------------------------------------------------------
# ReviewResult
# ---------------------------------------------------------------------------


@dataclass
class ReviewResult:
    """Output of QualityReviewerAgent.review_worksheet()."""

    questions: list = field(default_factory=list)  # possibly corrected
    corrections: list = field(default_factory=list)  # human-readable log of corrections
    warnings: list = field(default_factory=list)  # grade-level language warnings
    errors: list = field(default_factory=list)  # skill-tag replacement log
    stamps: dict = field(default_factory=dict)  # metadata stamps (e.g. parent_blocks_complete)


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

        # P2-B: Unconditional filler stripping (before word-count check)
        for q in result.questions:
            qt = q.get("question_text", q.get("text", ""))
            cleaned = _strip_filler_phrases(qt)
            # Only update if filler was actually removed (ignore whitespace-only diffs)
            if cleaned != re.sub(r"\s{2,}", " ", qt).strip():
                q["question_text"] = cleaned
                q["text"] = cleaned
                result.corrections.append(f"Q{q.get('id', '?')}: removed filler phrases")

        for q in result.questions:
            q_id = q.get("id", "?")
            slot_type = q.get("slot_type", "")
            question_text = q.get("question_text", "")

            # ── CHECK 1: Answer verification (all subjects) ────────────────
            # Uses AnswerAuthority to verify answers across all subjects:
            #   Maths: arithmetic, fraction, word-problem, error-detection
            #   Non-Maths: T/F canonical check, MCQ answer-in-options, fill_blank
            # If mismatch: sets _answer_mismatch=True (downstream R15 blocks).
            # If extraction fails (Maths only): sets _math_unverified=True.
            try:
                from app.services.answer_authority import get_answer_authority

                verdict = get_answer_authority().verify_question(q, context.subject)
                if verdict.match is False:
                    msg = (
                        f"Q{q_id}: answer mismatch — declared '{verdict.declared_answer}', "
                        f"authoritative '{verdict.authoritative_answer}' (method={verdict.method})"
                    )
                    logger.warning("[quality_reviewer] %s", msg)
                    q["_answer_mismatch"] = True
                    q["_answer_mismatch_debug"] = verdict.debug
                    result.corrections.append(msg)
                elif is_maths and verdict.match is None and verdict.method not in ("unverifiable", "error_detection"):
                    q["_math_unverified"] = True
                    result.warnings.append(f"Q{q_id}: math answer could not be verified ({verdict.debug})")
            except Exception as exc:
                if is_maths:
                    # HARD BLOCK: mark question as unverified instead of silently skipping
                    logger.error("[quality_reviewer] Check 1 FAILED for Q%s — marking unverified: %s", q_id, exc)
                    q["_math_unverified"] = True
                    result.warnings.append(f"Q{q_id}: math answer could not be verified ({exc})")
                else:
                    logger.debug("[quality_reviewer] Check 1 skipped for non-Maths Q%s: %s", q_id, exc)

            # ── CHECK 2: Skill tag validation ────────────────────────────
            try:
                valid_tags = context.valid_skill_tags
                if valid_tags:
                    skill_tag = q.get("skill_tag", "")
                    if skill_tag not in valid_tags:
                        replacement = valid_tags[0]
                        msg = f"Q{q_id}: invalid skill_tag '{skill_tag}' replaced with '{replacement}'"
                        logger.error("[quality_reviewer] %s", msg)
                        q["skill_tag"] = replacement
                        result.errors.append(msg)
            except Exception as exc:
                logger.debug("[quality_reviewer] Check 2 skipped for Q%s: %s", q_id, exc)

            # ── CHECK 3: Grade-level word count (ENFORCED) ────────────────
            try:
                grade = int(context.grade)
                limit = _word_limit(grade)
                word_count = len(question_text.split())
                if word_count > limit:
                    ratio = word_count / limit
                    msg = f"Q{q_id}: question has {word_count} words (Grade {grade} limit is {limit})"
                    logger.warning("[quality_reviewer] %s", msg)
                    result.warnings.append(msg)

                    if ratio > 2.0:
                        # >2x limit: unsalvageable — flag for regeneration
                        q["_needs_regen"] = True
                        result.corrections.append(
                            f"Q{q_id}: word count {word_count} is >{limit * 2}, flagged for regeneration"
                        )
                    else:
                        # >1.0x limit: try aggressive trimming, else flag for regen
                        trimmed = _trim_question_text(question_text, limit)
                        if trimmed and len(trimmed.split()) <= limit:
                            q["question_text"] = trimmed
                            q["text"] = trimmed
                            question_text = trimmed  # update for downstream checks
                            result.corrections.append(
                                f"Q{q_id}: question trimmed from {word_count} to {len(trimmed.split())} words"
                            )
                        elif ratio > 1.5:
                            q["_needs_regen"] = True
                            result.corrections.append(
                                f"Q{q_id}: word count {word_count} exceeds limit, flagged for regeneration"
                            )
                        # 1.0-1.5x with failed trim: warn only (soft violation)
            except Exception as exc:
                logger.debug("[quality_reviewer] Check 3 skipped for Q%s: %s", q_id, exc)

            # ── CHECK 4: Fraction and decimal answer verification ──────────
            # Handled by AnswerAuthority in CHECK 1 above (unified verification).
            # No separate auto-correction pass needed.

            # ── CHECK 5: Time fact answer validation ─────────────────────
            try:
                stored_answer = q.get("answer", "")
                tf_correction = _check_time_fact(question_text, stored_answer)
                if tf_correction is not None:
                    msg = f"Q{q_id}: time-fact answer corrected ('{stored_answer}' → '{tf_correction}')"
                    logger.warning("[quality_reviewer] %s", msg)
                    q["answer"] = tf_correction
                    q["_format_corrected"] = True
                    result.corrections.append(msg)
            except Exception as exc:
                logger.debug("[quality_reviewer] Check 5 skipped for Q%s: %s", q_id, exc)

            # ── CHECK 6: Hint answer-leakage detection ────────────────────
            try:
                hint = q.get("hint") or ""
                answer_for_leak = q.get("answer") or q.get("correct_answer") or ""
                if hint and _hint_leaks_answer(hint, answer_for_leak):
                    msg = f"Q{q_id}: hint reveals answer — nulled (hint='{hint[:60]}')"
                    logger.warning("[quality_reviewer] %s", msg)
                    q["hint"] = None
                    result.warnings.append(msg)
            except Exception as exc:
                logger.debug("[quality_reviewer] Check 6 skipped for Q%s: %s", q_id, exc)

            # ── CHECK 7: Self-contradiction in thinking answer ────────────
            if slot_type == "thinking":
                try:
                    raw_answer = q.get("answer") or q.get("correct_answer") or ""
                    if _check_answer_self_contradiction(str(raw_answer)):
                        msg = f"Q{q_id}: contradictory answer — reject and regenerate ('{str(raw_answer)[:80]}')"
                        logger.warning("[quality_reviewer] %s", msg)
                        q["_needs_regen"] = True
                        result.corrections.append(msg)
                except Exception as exc:
                    logger.debug("[quality_reviewer] Check 7 skipped for Q%s: %s", q_id, exc)

            # ── CHECK 8: Word problem answer verification ──────────────────
            # Handled by AnswerAuthority in CHECK 1 above (unified verification).
            # No separate auto-correction pass needed.

            # ── CHECK 18: Grade-appropriate arithmetic bounds ─────────────
            # Class 1 single-digit addition: answer must be ≤ 18 (9+9).
            # Class 1-2: flag answers that exceed grade expectations.
            if is_maths and slot_type != "error_detection":
                try:
                    answer_str = q.get("answer", "")
                    if answer_str and answer_str.lstrip("-").isdigit():
                        answer_val = int(answer_str)
                        grade = context.grade
                        topic_lower = context.topic_slug.lower() if hasattr(context, "topic_slug") else ""
                        if grade == 1 and "single" in topic_lower and answer_val > 18:
                            q["_needs_regen"] = True
                            msg = f"Q{q_id}: answer {answer_val} exceeds Class 1 single-digit range (max 18)"
                            result.corrections.append(msg)
                            logger.warning("[quality_reviewer] %s", msg)
                        elif grade == 1 and answer_val > 20:
                            q["_needs_regen"] = True
                            msg = f"Q{q_id}: answer {answer_val} exceeds Class 1 range (max 20)"
                            result.corrections.append(msg)
                            logger.warning("[quality_reviewer] %s", msg)
                except Exception as exc:
                    logger.debug("[quality_reviewer] Check 18 skipped for Q%s: %s", q_id, exc)

            # ── CHECK 9: LLM artifact detection ────────────────────────────
            try:
                if _contains_llm_artifact(question_text):
                    msg = f"Q{q_id}: LLM artifact detected in question text"
                    logger.warning("[quality_reviewer] %s", msg)
                    result.warnings.append(msg)
                hint = q.get("hint") or ""
                if hint and _contains_llm_artifact(hint):
                    msg = f"Q{q_id}: LLM artifact in hint — nulled"
                    logger.warning("[quality_reviewer] %s", msg)
                    q["hint"] = None
                    result.warnings.append(msg)
            except Exception as exc:
                logger.debug("[quality_reviewer] Check 9 skipped for Q%s: %s", q_id, exc)

            # ── CHECK 10-pre: Auto-fix Hindi impurities before detection ────
            # A) True/False → सही/गलत
            # B) Auto-replace common Devanagari-transliterated English words
            try:
                if context.subject.lower() == "hindi":
                    _TF_REPLACEMENTS = {
                        "True": "सही",
                        "true": "सही",
                        "False": "गलत",
                        "false": "गलत",
                        "Correct": "सही",
                        "correct": "सही",
                        "Incorrect": "गलत",
                        "incorrect": "गलत",
                    }
                    q_type = q.get("type", q.get("slot_type", ""))
                    # Fix options
                    opts = q.get("options")
                    if isinstance(opts, list):
                        new_opts = [_TF_REPLACEMENTS.get(str(o).strip(), o) for o in opts]
                        if new_opts != opts:
                            q["options"] = new_opts
                            result.corrections.append(f"Q{q_id}: True/False options → सही/गलत")
                    # Fix answer fields
                    for _tf_field in ("answer", "correct_answer"):
                        _tf_val = str(q.get(_tf_field, "") or "").strip()
                        if _tf_val in _TF_REPLACEMENTS:
                            q[_tf_field] = _TF_REPLACEMENTS[_tf_val]
                            result.corrections.append(
                                f"Q{q_id}: {_tf_field} '{_tf_val}' → '{_TF_REPLACEMENTS[_tf_val]}'"
                            )
                    # Fix question text containing "True or False" / "True/False"
                    qt = q.get("question_text", q.get("text", ""))
                    if qt:
                        _cleaned_qt = (
                            qt.replace("True or False", "सही या गलत")
                            .replace("true or false", "सही या गलत")
                            .replace("True/False", "सही/गलत")
                            .replace("true/false", "सही/गलत")
                        )
                        if _cleaned_qt != qt:
                            q["question_text"] = _cleaned_qt
                            q["text"] = _cleaned_qt
                            question_text = _cleaned_qt  # update local var for CHECK 10
                            result.corrections.append(f"Q{q_id}: 'True or False' → 'सही या गलत' in text")

                    # B) Auto-replace common transliterated words across all fields
                    _TRANSLIT_FIXES = {
                        "बॉल": "गेंद",
                        "बुक": "किताब",
                        "बुक्स": "किताबें",
                        "टेबल": "मेज़",
                        "चेयर": "कुर्सी",
                        "पेंसिल": "कलम",
                        "पेंसिल्स": "कलमें",
                        "स्कूल": "विद्यालय",
                        "टीचर": "शिक्षक",
                        "स्टूडेंट": "विद्यार्थी",
                        "कलर": "रंग",
                        "फ्लावर": "फूल",
                        "ट्री": "पेड़",
                        "बर्ड": "पक्षी",
                        "कैट": "बिल्ली",
                        "डॉग": "कुत्ता",
                        "फिश": "मछली",
                        "रैबिट": "खरगोश",
                        "स्टार": "तारा",
                        "बैग": "थैला",
                        "ट्रेन": "रेलगाड़ी",
                        "बॉक्स": "डिब्बा",
                        "हेल्प": "मदद",
                        "सॉल्व": "हल करो",
                        "फाइंड": "ढूँढो",
                        "लेट्स": "चलो",
                        "चेक": "जाँचो",
                        "काउंट": "गिनो",
                        "करेक्ट": "सही",
                        "इनकरेक्ट": "गलत",
                        "नंबर": "संख्या",
                        "प्लेट": "थाली",
                        "कप": "प्याला",
                        "गिलास": "गिलास",
                        "मिल्क": "दूध",
                        "ब्रेड": "रोटी",
                        "रेड": "लाल",
                        "ब्लू": "नीला",
                        "ग्रीन": "हरा",
                        "यलो": "पीला",
                        "पिंक": "गुलाबी",
                        "ऑरेंज": "नारंगी",
                        "ब्लैक": "काला",
                        "व्हाइट": "सफ़ेद",
                    }
                    _translit_fixed = False
                    for _field in ("question_text", "text", "answer", "correct_answer", "explanation", "hint"):
                        _fv = str(q.get(_field, "") or "")
                        if not _fv.strip():
                            continue
                        _new_fv = _fv
                        for _bad, _good in _TRANSLIT_FIXES.items():
                            if _bad in _new_fv:
                                _new_fv = _new_fv.replace(_bad, _good)
                        if _new_fv != _fv:
                            q[_field] = _new_fv
                            if _field in ("question_text", "text"):
                                question_text = _new_fv
                            _translit_fixed = True
                    if _translit_fixed:
                        result.corrections.append(f"Q{q_id}: auto-replaced transliterated words with Hindi equivalents")
                    # Also fix options
                    _opts = q.get("options")
                    if isinstance(_opts, list):
                        _new_opts = []
                        for _o in _opts:
                            _os = str(_o or "")
                            for _bad, _good in _TRANSLIT_FIXES.items():
                                _os = _os.replace(_bad, _good)
                            _new_opts.append(_os)
                        if _new_opts != [str(o or "") for o in _opts]:
                            q["options"] = _new_opts
                            result.corrections.append(f"Q{q_id}: auto-replaced transliterated words in options")
            except Exception as exc:
                logger.debug("[quality_reviewer] Check 10-pre skipped for Q%s: %s", q_id, exc)

            # ── CHECK 10: Hindi language purity ─────────────────────────────
            # Code-mixing check runs on any text with Devanagari.
            # Transliteration blocklist only runs on Hindi subject worksheets
            # to avoid false positives (e.g., "सन" = year in Hindi, not "sun").
            try:
                _impure_found = False

                # CHECK 10a: Question text
                if _has_hindi_code_mixing(question_text):
                    msg = f"Q{q_id}: Hindi code-mixing detected (Latin script in Devanagari text)"
                    logger.warning("[quality_reviewer] %s", msg)
                    result.warnings.append(msg)
                    q["_needs_regen"] = True
                    q["_hindi_impure"] = True
                    _impure_found = True
                    result.corrections.append(f"Q{q_id}: flagged for regen (Latin code-mixing)")
                elif context.subject.lower() == "hindi" and _has_hindi_transliteration(question_text):
                    msg = f"Q{q_id}: Hindi transliterated English detected (Devanagari-English words)"
                    logger.warning("[quality_reviewer] %s", msg)
                    result.warnings.append(msg)
                    q["_needs_regen"] = True
                    q["_hindi_impure"] = True
                    _impure_found = True
                    result.corrections.append(f"Q{q_id}: flagged for regen (transliterated English)")

                # CHECK 10b: Scan answer, hint, explanation for Hindi impurity
                # Only answer fields are student-facing and trigger _hindi_impure.
                # Explanation/hint impurity is logged as a warning but does NOT
                # trigger R17 BLOCK — it's teacher-facing and cosmetic.
                for _field_name in ("answer", "correct_answer", "explanation", "hint"):
                    _field_val = str(q.get(_field_name, "") or "")
                    if not _field_val.strip():
                        continue
                    _is_student_facing = _field_name in ("answer", "correct_answer")
                    if _has_hindi_code_mixing(_field_val):
                        msg = f"Q{q_id}: Hindi code-mixing in {_field_name}"
                        logger.warning("[quality_reviewer] %s", msg)
                        result.warnings.append(msg)
                        if _is_student_facing:
                            _impure_found = True
                    elif context.subject.lower() == "hindi" and _has_hindi_transliteration(_field_val):
                        msg = f"Q{q_id}: Hindi transliteration in {_field_name}"
                        logger.warning("[quality_reviewer] %s", msg)
                        result.warnings.append(msg)
                        if _is_student_facing:
                            _impure_found = True

                # CHECK 10c: MCQ options
                options = q.get("options")
                if isinstance(options, list):
                    for opt in options:
                        opt_str = str(opt or "")
                        if not opt_str.strip():
                            continue
                        if _has_hindi_code_mixing(opt_str):
                            msg = f"Q{q_id}: Hindi code-mixing in MCQ option"
                            logger.warning("[quality_reviewer] %s", msg)
                            result.warnings.append(msg)
                            _impure_found = True
                        elif context.subject.lower() == "hindi" and _has_hindi_transliteration(opt_str):
                            msg = f"Q{q_id}: Hindi transliteration in MCQ option"
                            logger.warning("[quality_reviewer] %s", msg)
                            result.warnings.append(msg)
                            _impure_found = True

                if _impure_found:
                    q["_hindi_impure"] = True
            except Exception as exc:
                logger.debug("[quality_reviewer] Check 10 skipped for Q%s: %s", q_id, exc)

            # ── CHECK 19: Science/EVS subject contamination ───────────────
            # Flag questions that are purely arithmetic in Science/EVS worksheets.
            if context.subject.lower() in ("science", "evs"):
                try:
                    qt_lower = question_text.lower()
                    # Detect pure arithmetic: "How many X" + answer is a plain integer
                    ans = q.get("answer", "")
                    is_pure_math = (
                        bool(re.search(r"how many|total|in all|altogether", qt_lower))
                        and isinstance(ans, str)
                        and ans.strip().isdigit()
                        and not re.search(r"species|type|kind|name|organ|part|group|nutrient|vitamin", qt_lower)
                    )
                    if is_pure_math:
                        msg = f"Q{q_id}: Science/EVS question appears to be pure arithmetic"
                        logger.warning("[quality_reviewer] %s", msg)
                        result.warnings.append(msg)
                        q["_needs_regen"] = True
                        result.corrections.append(f"Q{q_id}: flagged for regen (subject contamination)")
                except Exception as exc:
                    logger.debug("[quality_reviewer] Check 19 skipped for Q%s: %s", q_id, exc)

            # ── CHECK 20: Fill-in-the-blank ambiguity ────────────────────
            try:
                q_type = q.get("type", q.get("format", ""))
                if q_type in ("fill_blank", "fill_in_blank"):
                    _fb_issues = []
                    if not _FB_BLANK_RE.search(question_text):
                        _fb_issues.append("missing blank marker")
                    if _FB_SUBJECTIVE_RE.search(question_text):
                        _fb_issues.append("subjective/open-ended prompt")
                    _fb_answer = str(q.get("answer", q.get("correct_answer", "")) or "").strip().lower()
                    if _fb_answer in _FB_GENERIC_ANSWERS:
                        _fb_issues.append(f"generic answer '{_fb_answer}'")
                    if _fb_issues:
                        q["_fill_blank_ambiguous"] = True
                        msg = f"Q{q_id}: fill-blank ambiguity ({', '.join(_fb_issues)})"
                        logger.warning("[quality_reviewer] %s", msg)
                        result.warnings.append(msg)
            except Exception as exc:
                logger.debug("[quality_reviewer] Check 20 skipped for Q%s: %s", q_id, exc)

            # ── CHECK 21: Render integrity — phantom visual references ────
            try:
                if _VISUAL_REF_RE.search(question_text) or _TABLE_REF_RE.search(question_text):
                    has_visual = bool(q.get("visual_type") or q.get("visual_data") or q.get("images"))
                    if not has_visual:
                        q["_phantom_visual_ref"] = True
                        match_str = (
                            _VISUAL_REF_RE.search(question_text) or _TABLE_REF_RE.search(question_text)
                        ).group()
                        msg = f"Q{q_id}: render integrity — phantom visual reference ('{match_str}')"
                        logger.warning("[quality_reviewer] %s", msg)
                        result.warnings.append(msg)
            except Exception as exc:
                logger.debug("[quality_reviewer] Check 21 skipped for Q%s: %s", q_id, exc)

        # ── CHECK 11: Engagement framing injection (P0-A) ──────────────
        # If <20% of questions use warm framing, inject it on eligible questions.
        # Step 1: Strip any existing engagement prefixes FIRST to avoid double-framing.
        # Step 2: Count engagement-framed questions.
        # Step 3: Inject new framing if below target, preserving original case.
        try:
            _ENGAGEMENT_RE = re.compile(r"(?i)^(help|can you|try to|let'?s|guess)")
            _HINDI_ENGAGEMENT_RE = re.compile(r"की मदद करो")
            # Patterns to strip old engagement prefixes (including name variants)
            _STRIP_ENGAGEMENT_RE = re.compile(
                r"(?i)^(?:help\s+\w+\s+(?:solve this|figure out|find|count|work out)\s*:\s*"
                r"|can you\s+(?:help\s+\w+\s+)?(?:solve|find|figure out)\s*[:\?]?\s*"
                r"|try to\s+(?:find|solve|figure out)\s*:\s*"
                r"|let'?s\s+(?:figure out|find|solve|help\s+\w+)\s*:\s*"
                r"|with\s+\w+\s*:\s*)"
            )
            _STRIP_HINDI_ENGAGEMENT_RE = re.compile(r"^\w+\s+की मदद करो\s*:\s*")

            # Step 1: Strip existing engagement prefixes from ALL questions
            for q in result.questions:
                q_text = (q.get("text") or q.get("question_text") or "").strip()
                if not q_text:
                    continue
                cleaned = _STRIP_ENGAGEMENT_RE.sub("", q_text).strip()
                cleaned = _STRIP_HINDI_ENGAGEMENT_RE.sub("", cleaned).strip()
                if cleaned != q_text and cleaned:
                    # Ensure first character is uppercase after stripping
                    cleaned = cleaned[0].upper() + cleaned[1:] if len(cleaned) > 1 else cleaned.upper()
                    q["text"] = cleaned
                    q["question_text"] = cleaned

            # Step 2: Count (should be 0 after stripping)
            engagement_count = sum(
                1
                for q in result.questions
                if _ENGAGEMENT_RE.match((q.get("text") or q.get("question_text") or "").strip())
                or _HINDI_ENGAGEMENT_RE.search((q.get("text") or q.get("question_text") or ""))
            )
            import random as _rng

            # P3-A: Vary engagement target (2-3 for 10Q) instead of fixed 2
            _base = max(2, len(result.questions) // 5)
            target = _rng.choice([_base, _base + 1]) if len(result.questions) >= 8 else _base

            # Step 3: Inject fresh framing
            if engagement_count < target:
                from app.services.worksheet_generator import _INDIAN_NAMES

                names_pool = list(_INDIAN_NAMES)
                _rng.shuffle(names_pool)
                name_idx = 0
                injected = 0
                for q in result.questions:
                    if injected >= (target - engagement_count):
                        break
                    q_text = (q.get("text") or q.get("question_text") or "").strip()
                    q_type = q.get("type", "")
                    # Only inject on word_problem / fill_blank — not MCQ/true_false
                    if q_type not in ("word_problem", "fill_blank", "short_answer"):
                        continue
                    if _ENGAGEMENT_RE.match(q_text) or _HINDI_ENGAGEMENT_RE.search(q_text):
                        continue  # already has framing
                    if not q_text:
                        continue
                    name = names_pool[name_idx % len(names_pool)]
                    name_idx += 1
                    # Detect Hindi: check if question has Devanagari script
                    _is_hindi = bool(re.search(r"[\u0900-\u097F]", q_text))
                    if _is_hindi:
                        new_text = f"{name} की मदद करो: {q_text}"
                    else:
                        # Preserve original case — don't lowercase the first char
                        new_text = f"Help {name} solve this: {q_text}"
                    # Guard: ensure result is not garbled (starts with letter, reasonable length)
                    if len(new_text) < 10 or not new_text[0].isalpha():
                        continue
                    q["text"] = new_text
                    q["question_text"] = new_text
                    injected += 1
                    _framing_label = f"{name} की मदद करो:" if _is_hindi else f"Help {name} solve this:"
                    result.corrections.append(
                        f"Q{q.get('id', '?')}: engagement framing injected ('{_framing_label} …')"
                    )
                if injected > 0:
                    logger.info("[quality_reviewer] Injected engagement framing on %d question(s)", injected)
        except Exception as exc:
            logger.debug("[quality_reviewer] Check 11 (engagement injection) skipped: %s", exc)

        # ── CHECK 13: Error detection answer/explanation consistency (P0) ──
        # If an error_detection question's answer ("No"/"Yes") contradicts its
        # own explanation OR the mathematical truth, fix the answer.
        try:
            _YES_RE = re.compile(r"(?i)\b(correct|right|yes)\b")
            _NO_RE = re.compile(r"(?i)\b(incorrect|wrong|not correct|no)\b")
            # Pattern: "X says A is the largest/smallest/greatest among ..."
            _COMPARISON_CLAIM_RE = re.compile(
                r"(?:says?\s+)?(\d+(?:\.\d+)?)\s+is\s+(?:the\s+)?"
                r"(largest|smallest|greatest|biggest|least|most|highest|lowest)"
                r"(?:\s+(?:among|of|in|from))?",
                re.IGNORECASE,
            )
            # Extract numbers from question text
            _ALL_NUMS_RE = re.compile(r"\d+(?:\.\d+)?")

            for q in result.questions:
                q_type = q.get("type", q.get("slot_type", ""))
                if q_type not in ("error_detection", "error_spot"):
                    continue
                answer = str(q.get("answer") or q.get("correct_answer") or "")
                explanation = str(q.get("explanation") or "")
                q_text = q.get("text") or q.get("question_text") or ""
                if not answer:
                    continue
                q_id = q.get("id", "?")

                # Determine answer sentiment
                ans_lower = answer.lower().strip().rstrip(".")
                ans_says_correct = _YES_RE.search(ans_lower) is not None
                ans_says_incorrect = _NO_RE.search(ans_lower) is not None

                # --- 13a: Mathematical verification of comparison claims ---
                claim_match = _COMPARISON_CLAIM_RE.search(q_text)
                if claim_match and (ans_says_correct or ans_says_incorrect):
                    claimed_val = float(claim_match.group(1))
                    claim_type = claim_match.group(2).lower()
                    all_nums = [float(n) for n in _ALL_NUMS_RE.findall(q_text)]
                    # Need at least 3 numbers (the claim value + 2 comparisons)
                    if len(all_nums) >= 3:
                        is_max_claim = claim_type in ("largest", "greatest", "biggest", "highest", "most")
                        is_min_claim = claim_type in ("smallest", "least", "lowest")
                        if is_max_claim:
                            claim_is_true = claimed_val >= max(all_nums)
                        elif is_min_claim:
                            claim_is_true = claimed_val <= min(all_nums)
                        else:
                            claim_is_true = None

                        if claim_is_true is not None:
                            if claim_is_true and ans_says_incorrect:
                                new_answer = (
                                    answer.replace("No", "Yes")
                                    .replace("no", "yes")
                                    .replace("incorrect", "correct")
                                    .replace("Incorrect", "Correct")
                                    .replace("not correct", "correct")
                                    .replace("Not correct", "Correct")
                                )
                                q["answer"] = new_answer
                                q["correct_answer"] = new_answer
                                msg = f"Q{q_id}: error_detection math verification — claim IS true but answer said no, flipped to '{new_answer[:50]}'"
                                logger.warning("[quality_reviewer] %s", msg)
                                result.corrections.append(msg)
                                continue  # already fixed
                            elif not claim_is_true and ans_says_correct:
                                new_answer = (
                                    answer.replace("Yes", "No").replace("yes", "no").replace("correct", "incorrect")
                                )
                                q["answer"] = new_answer
                                q["correct_answer"] = new_answer
                                msg = f"Q{q_id}: error_detection math verification — claim IS false but answer said yes, flipped to '{new_answer[:50]}'"
                                logger.warning("[quality_reviewer] %s", msg)
                                result.corrections.append(msg)
                                continue

                # --- 13b: Answer vs explanation sentiment (original check, improved) ---
                if not explanation:
                    continue

                # Scan ALL sentences for verdict (not just last)
                expl_sentences = [s.strip() for s in explanation.split(".") if s.strip()]
                expl_says_correct = False
                expl_says_incorrect = False
                for sent in expl_sentences:
                    sent_lower = sent.lower()
                    if re.search(
                        r"\b(is correct|is right|he is correct|she is correct|statement is correct|claim is correct)\b",
                        sent_lower,
                    ) and not re.search(r"\b(not correct|incorrect|is not right)\b", sent_lower):
                        expl_says_correct = True
                    if re.search(
                        r"\b(incorrect|wrong|not correct|is not right|he is wrong|she is wrong)\b", sent_lower
                    ):
                        expl_says_incorrect = True

                # Last sentence gets priority if it has a clear verdict
                if expl_sentences:
                    last_lower = expl_sentences[-1].lower()
                    if re.search(r"\b(is correct|is right)\b", last_lower) and not re.search(
                        r"\b(not correct|incorrect)\b", last_lower
                    ):
                        expl_says_correct = True
                        expl_says_incorrect = False
                    elif re.search(r"\b(incorrect|wrong|not correct)\b", last_lower):
                        expl_says_incorrect = True
                        expl_says_correct = False

                # Contradiction: answer says "No" but explanation says correct (or vice versa)
                if ans_says_incorrect and expl_says_correct and not expl_says_incorrect:
                    new_answer = (
                        answer.replace("No", "Yes")
                        .replace("no", "yes")
                        .replace("incorrect", "correct")
                        .replace("Incorrect", "Correct")
                    )
                    q["answer"] = new_answer
                    q["correct_answer"] = new_answer
                    msg = f"Q{q_id}: error_detection answer contradicted explanation — flipped to '{new_answer[:50]}'"
                    logger.warning("[quality_reviewer] %s", msg)
                    result.corrections.append(msg)
                elif ans_says_correct and expl_says_incorrect and not expl_says_correct:
                    new_answer = answer.replace("Yes", "No").replace("yes", "no").replace("correct", "incorrect")
                    q["answer"] = new_answer
                    q["correct_answer"] = new_answer
                    msg = f"Q{q_id}: error_detection answer contradicted explanation — flipped to '{new_answer[:50]}'"
                    logger.warning("[quality_reviewer] %s", msg)
                    result.corrections.append(msg)
        except Exception as exc:
            logger.debug("[quality_reviewer] Check 13 (error_detection consistency) skipped: %s", exc)

        # ── CHECK 14: MCQ answer must exist in options list ──────────────
        # If the LLM hallucinated an answer that isn't one of the options,
        # try to find the correct option from the explanation text.
        try:
            for q in result.questions:
                q_type = q.get("type", q.get("slot_type", ""))
                if q_type != "mcq":
                    continue
                options = q.get("options") or []
                if not options:
                    continue
                answer = str(q.get("answer") or q.get("correct_answer") or "").strip()
                opts_stripped = [str(o).strip() for o in options]
                if answer in opts_stripped:
                    continue  # all good
                # Answer not in options — try to match from explanation
                explanation = str(q.get("explanation") or "")
                matched_opt = None
                for opt in opts_stripped:
                    # Check if option value appears in the explanation as the answer
                    if opt and opt.lower() in explanation.lower():
                        matched_opt = opt
                        break
                if matched_opt:
                    q_id = q.get("id", "?")
                    msg = f"Q{q_id}: MCQ answer '{answer}' not in options — corrected to '{matched_opt}'"
                    logger.warning("[quality_reviewer] %s", msg)
                    q["answer"] = matched_opt
                    q["correct_answer"] = matched_opt
                    q["_format_corrected"] = True
                    result.corrections.append(msg)
                else:
                    # Can't auto-fix — flag for regeneration
                    q_id = q.get("id", "?")
                    msg = f"Q{q_id}: MCQ answer '{answer}' not in options {opts_stripped} — flagged for regen"
                    logger.warning("[quality_reviewer] %s", msg)
                    q["_needs_regen"] = True
                    result.warnings.append(msg)
        except Exception as exc:
            logger.debug("[quality_reviewer] Check 14 (MCQ answer-in-options) skipped: %s", exc)

        # ── CHECK 23: MCQ multi-correct detection ────────────────────────
        # If >1 option is numerically equivalent to the answer, flag it.
        try:
            from app.utils.answer_normalizer import normalize_numeric

            for q in result.questions:
                q_type = q.get("type", q.get("slot_type", ""))
                if q_type != "mcq":
                    continue
                options = q.get("options") or []
                if len(options) < 2:
                    continue
                answer = str(q.get("answer") or q.get("correct_answer") or "").strip()
                answer_norm = normalize_numeric(answer)
                if answer_norm is None:
                    continue
                equiv_count = sum(1 for opt in options if normalize_numeric(str(opt).strip()) == answer_norm)
                if equiv_count > 1:
                    q_id = q.get("id", "?")
                    q["_mcq_multi_correct"] = True
                    msg = f"Q{q_id}: MCQ has {equiv_count} equivalent correct options"
                    logger.warning("[quality_reviewer] %s", msg)
                    result.warnings.append(msg)
        except Exception as exc:
            logger.debug("[quality_reviewer] Check 23 (MCQ multi-correct) skipped: %s", exc)

        # ── CHECK 15: True/False answer must be "True" or "False" ────────
        # LLM sometimes answers a T/F question with the actual value (e.g. "1/3")
        # instead of "True" or "False". Derive the correct boolean from the content.
        try:
            _is_hindi_subject = context.subject.lower() == "hindi"
            _valid_tf = {"True", "False", "सही", "गलत"} if _is_hindi_subject else {"True", "False"}
            _true_label = "सही" if _is_hindi_subject else "True"
            _false_label = "गलत" if _is_hindi_subject else "False"

            for q in result.questions:
                q_type = q.get("type", q.get("slot_type", ""))
                if q_type != "true_false":
                    continue
                answer = str(q.get("answer") or q.get("correct_answer") or "").strip()
                if answer in _valid_tf:
                    continue  # already correct format
                # Answer is not in valid T/F form — derive from explanation
                explanation = str(q.get("explanation") or "").lower()
                q_id = q.get("id", "?")
                # Check affirmative/negative in both English and Hindi
                _affirmative_forms = {"true", "yes", "correct", "right", "सही", "हाँ", "हां"}
                _negative_forms = {"false", "no", "incorrect", "wrong", "गलत", "नहीं"}
                ans_lower = answer.lower()
                if ans_lower in _affirmative_forms:
                    new_answer = _true_label
                elif ans_lower in _negative_forms:
                    new_answer = _false_label
                else:
                    # Heuristic from explanation
                    _true_signals = bool(
                        re.search(
                            r"\b(is correct|is true|is right|statement is true|so,? true|the answer is true|सही है)\b",
                            explanation,
                        )
                    )
                    _false_signals = bool(
                        re.search(
                            r"\b(incorrect|not correct|is wrong|is false|not true|the answer is false|is not|गलत है|सही नहीं)\b",
                            explanation,
                        )
                    )
                    if _true_signals and not _false_signals:
                        new_answer = _true_label
                    elif _false_signals and not _true_signals:
                        new_answer = _false_label
                    else:
                        new_answer = _true_label  # default: assume LLM gave the correct value
                msg = f"Q{q_id}: T/F answer was '{answer}' (not {_true_label}/{_false_label}) — corrected to '{new_answer}'"
                logger.warning("[quality_reviewer] %s", msg)
                q["answer"] = new_answer
                q["correct_answer"] = new_answer
                q["_format_corrected"] = True
                result.corrections.append(msg)
        except Exception as exc:
            logger.debug("[quality_reviewer] Check 15 (T/F answer format) skipped: %s", exc)

        # ── CHECK 16: Hindi question instruction vs answer consistency ───
        # If a Hindi question asks for बहुवचन (plural) but answer is singular
        # (or vice versa), flag for regeneration since auto-fix is unreliable.
        try:
            _BAHUVACHAN_RE = re.compile(r"बहुवचन|plural", re.IGNORECASE)
            _EKVACHAN_RE = re.compile(r"एकवचन|singular", re.IGNORECASE)
            for q in result.questions:
                q_text = q.get("text") or q.get("question_text") or ""
                # Only check if question explicitly mentions vachan terms
                asks_plural = bool(_BAHUVACHAN_RE.search(q_text))
                asks_singular = bool(_EKVACHAN_RE.search(q_text))
                if not asks_plural and not asks_singular:
                    continue
                explanation = str(q.get("explanation") or "").lower()
                q_id = q.get("id", "?")
                # Check contradiction: question asks for plural but explanation says singular
                if asks_plural and "एकवचन" in explanation and "बहुवचन" not in explanation:
                    msg = f"Q{q_id}: question asks for बहुवचन but answer/explanation gives एकवचन — flagged for regen"
                    logger.warning("[quality_reviewer] %s", msg)
                    q["_needs_regen"] = True
                    result.warnings.append(msg)
                elif asks_singular and "बहुवचन" in explanation and "एकवचन" not in explanation:
                    msg = f"Q{q_id}: question asks for एकवचन but answer/explanation gives बहुवचन — flagged for regen"
                    logger.warning("[quality_reviewer] %s", msg)
                    q["_needs_regen"] = True
                    result.warnings.append(msg)
        except Exception as exc:
            logger.debug("[quality_reviewer] Check 16 (Hindi vachan consistency) skipped: %s", exc)

        # ── CHECK 12: Sentence structure diversity (P4-A upgrade) ──────
        # Ensure ≥3 distinct structure types for 10Q, ≥2 for <10Q.
        # Rewrites question openings to add missing types.
        try:
            _QW_RE = re.compile(r"(?i)^(what|which|how|who|where|when|why)\b")
            _IMP_RE = re.compile(
                r"(?i)^(find|solve|write|fill|complete|calculate|match|draw|circle|count"
                r"|add|subtract|multiply|divide|arrange|list|name|identify|help|can you|try to|let'?s)\b"
            )
            _COND_RE = re.compile(r"(?i)^(if|suppose|imagine|given)\b")
            _HINDI_QW_RE = re.compile(r"^(किस|कौन|कैसे|क्या|कितन|कहाँ|कब)")
            _HINDI_IMP_RE = re.compile(r"^(लिख|बताओ|चुन|मिला|पूरा कर|ढूँढ|गिन)")

            def _classify(txt: str) -> str:
                if _QW_RE.match(txt) or _HINDI_QW_RE.match(txt):
                    return "question_word"
                if _IMP_RE.match(txt) or _HINDI_IMP_RE.match(txt):
                    return "imperative"
                if _COND_RE.match(txt):
                    return "conditional"
                return "statement"

            structure_counts: dict[str, int] = {"question_word": 0, "imperative": 0, "conditional": 0, "statement": 0}
            q_types: list[str] = []
            for q in result.questions:
                text = (q.get("text") or q.get("question_text") or "").strip()
                stype = _classify(text)
                structure_counts[stype] += 1
                q_types.append(stype)

            distinct = sum(1 for v in structure_counts.values() if v > 0)
            min_needed = 3 if len(result.questions) >= 10 else 2
            if distinct < min_needed and len(result.questions) >= 5:
                _sample = result.questions[0].get("text") or result.questions[0].get("question_text") or ""
                _is_hindi_ws = bool(re.search(r"[\u0900-\u097F]", _sample))

                # Rewrite map: source_type → [(old_prefix, new_prefix, target_type), ...]
                _REWRITE_MAP: dict[str, list[tuple[str, str, str]]] = {
                    "question_word": [
                        ("What is ", "Find ", "imperative"),
                        ("How many ", "Count the number of ", "imperative"),
                        ("Which ", "Identify the ", "imperative"),
                        ("What ", "If we look at ", "conditional"),
                    ],
                    "imperative": [
                        ("Find ", "What is ", "question_word"),
                        ("Solve ", "What is the answer to ", "question_word"),
                        ("Calculate ", "What is ", "question_word"),
                        ("Find ", "If you find ", "conditional"),
                    ],
                    "statement": [
                        ("There are ", "How many are there if there are ", "conditional"),
                        ("A ", "What happens when a ", "question_word"),
                    ],
                    "conditional": [
                        ("If ", "Find out: if ", "imperative"),
                    ],
                }
                _HINDI_REWRITE_MAP: dict[str, list[tuple[str, str, str]]] = {
                    "statement": [
                        ("'", "किस शब्द में '", "question_word"),
                    ],
                    "imperative": [
                        ("लिख", "कौन सा शब्द ", "question_word"),
                    ],
                }
                rewrite_map = _HINDI_REWRITE_MAP if _is_hindi_ws else _REWRITE_MAP

                # Find which types are missing and which are dominant
                missing = [
                    t for t in ("question_word", "imperative", "conditional", "statement") if structure_counts[t] == 0
                ]
                dominant = max(structure_counts, key=structure_counts.get)  # type: ignore[arg-type]

                rewrites_done = 0
                for target_type in missing:
                    if distinct + rewrites_done >= min_needed:
                        break
                    # Find a question of the dominant type and rewrite to target_type
                    for i, q in enumerate(result.questions):
                        if q_types[i] != dominant:
                            continue
                        text = (q.get("text") or q.get("question_text") or "").strip()
                        rewritten = False
                        for old_pf, new_pf, tgt in rewrite_map.get(dominant, []):
                            if tgt == target_type and text.startswith(old_pf):
                                new_text = new_pf + text[len(old_pf) :]
                                q["text"] = new_text
                                q["question_text"] = new_text
                                q_types[i] = target_type
                                structure_counts[dominant] -= 1
                                structure_counts[target_type] += 1
                                rewrites_done += 1
                                result.corrections.append(
                                    f"Q{q.get('id', '?')}: starter diversified '{old_pf.strip()}' → '{new_pf.strip()}' ({dominant}→{target_type})"
                                )
                                rewritten = True
                                break
                        if rewritten:
                            break
                if rewrites_done > 0:
                    logger.info(
                        "[quality_reviewer] CHECK 12: diversified %d sentence starter(s) → %d types",
                        rewrites_done,
                        distinct + rewrites_done,
                    )
        except Exception as exc:
            logger.debug("[quality_reviewer] Check 12 (sentence diversity) skipped: %s", exc)

        # ── CHECK 17: Round number auto-fix for simple arithmetic (P4-B) ──
        # For simple "A op B" questions, if both numbers are round (mult of 5),
        # nudge one number by ±1..3 and recompute the answer.
        try:
            if is_maths:
                import random as _rng17

                _SIMPLE_ARITH_RE = re.compile(r"^.*?(\d+)\s*([+\-×÷xX*/])\s*(\d+)")
                _round_fixes = 0
                for q in result.questions:
                    if q.get("_is_bonus") or q.get("_math_unverified"):
                        continue
                    qtype = (q.get("type") or q.get("format") or "").lower()
                    if qtype in ("word_problem", "error_detection"):
                        continue
                    text = (q.get("text") or q.get("question_text") or "").strip()
                    m = _SIMPLE_ARITH_RE.match(text)
                    if not m:
                        continue
                    a_str, op, b_str = m.group(1), m.group(2), m.group(3)
                    a, b = int(a_str), int(b_str)
                    if a <= 1 or b <= 1:
                        continue
                    both_round = (a % 5 == 0) and (b % 5 == 0)
                    if not both_round:
                        continue
                    # Nudge one of them
                    nudge = _rng17.choice([1, 2, 3])
                    new_a = a + nudge
                    # Recompute answer
                    if op in ("+",):
                        new_ans = new_a + b
                    elif op in ("-",):
                        if new_a < b:
                            continue  # skip if result would go negative
                        new_ans = new_a - b
                    elif op in ("×", "x", "X", "*"):
                        new_ans = new_a * b
                    elif op in ("÷", "/"):
                        if b == 0 or new_a % b != 0:
                            continue  # skip if not evenly divisible
                        new_ans = new_a // b
                    else:
                        continue
                    new_text = text.replace(a_str, str(new_a), 1)
                    q["text"] = new_text
                    q["question_text"] = new_text
                    q["answer"] = str(new_ans)
                    q["correct_answer"] = str(new_ans)
                    _round_fixes += 1
                    if _round_fixes >= 3:
                        break  # Don't over-correct
                if _round_fixes > 0:
                    logger.info(
                        "[quality_reviewer] CHECK 17: de-rounded %d simple arithmetic question(s)", _round_fixes
                    )
        except Exception as exc:
            logger.debug("[quality_reviewer] Check 17 (round number fix) skipped: %s", exc)

        logger.info(
            "[quality_reviewer] Review complete: %d question(s), %d correction(s), %d warning(s), %d error(s)",
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


# ---------------------------------------------------------------------------
# Grade-appropriateness validator (Step 4 — post-generation filter)
# ---------------------------------------------------------------------------

# Patterns that signal explanation/justification requests (forbidden ≤ Class 2)
_EXPLAIN_RE = re.compile(r"\b(explain|why|justify|prove|describe how)\b", re.IGNORECASE)


def validate_grade_appropriateness(
    questions: list[dict],
    grade_num: int,
) -> tuple[list, list]:
    """Filter questions that violate grade-level cognitive guardrails.

    Args:
        questions: List of question dicts (each may have 'role', 'correct_answer',
                   'question' / 'text' keys).
        grade_num: Integer grade level (1-5). Unknown grades are permissive.

    Returns:
        (valid_questions, rejected_questions) where each rejected question has
        an extra '_rejection_reasons' key listing what was violated.
    """
    profile = GRADE_PROFILES.get(str(grade_num), {})
    forbidden = set(profile.get("forbidden_question_types", []))
    max_words = profile.get("answer_constraints", {}).get("max_words", 999)

    valid: list[dict] = []
    rejected: list[dict] = []

    for q in questions:
        reasons: list[str] = []
        # slot_type is always set by the backend pipeline; role is a legacy alias
        # used in tests and some older code paths — check both.
        role = q.get("slot_type") or q.get("role", "")
        answer = str(q.get("correct_answer", "") or q.get("answer", ""))
        q_text = (q.get("question") or q.get("question_text") or q.get("text") or "").lower()

        # Rule 1: forbidden question type for this grade
        if role in forbidden:
            reasons.append(f"slot_type='{role}' forbidden for Class {grade_num}")

        # Rule 2: answer exceeds max word count
        # error_detection answers are structurally longer — they must explain
        # the mistake AND state the correction, so double the cap for them.
        word_count = len(answer.split())
        is_error_detection = role in ("error_detection", "error_spot")
        effective_max = max_words * 2 if is_error_detection else max_words
        if word_count > effective_max:
            reasons.append(f"answer too long ({word_count} words, max {effective_max})")

        # Rule 3: explanation requests forbidden for Class 1-2
        if grade_num <= 2 and _EXPLAIN_RE.search(q_text):
            reasons.append(f"question asks for explanation — forbidden for Class {grade_num}")

        if reasons:
            rejected.append({**q, "_rejection_reasons": reasons})
        else:
            valid.append(q)

    return valid, rejected
