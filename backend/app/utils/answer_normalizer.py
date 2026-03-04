"""
Centralized answer normalizer — canonical form for numeric answers.

Ensures equivalent representations compare equal:
  "0.5" == "1/2" == ".50" == "2/4"
  "5.0" == "5"
  "1/3" stays "1/3" (non-terminating decimal)

Uses fractions.Fraction from stdlib for exact arithmetic.
"""

from __future__ import annotations

import re
from fractions import Fraction

# Strip leading option labels like "A)", "B.", "c)", "(d)"
_OPTION_LABEL_RE = re.compile(r"^\s*\(?[A-Da-d]\)?[.)]\s*")

# Strip trailing units (word chars after a number + space)
_UNIT_RE = re.compile(r"^([\d./\-]+)\s+[A-Za-z\u0900-\u097F].*$")

# Match fraction notation: "3/4", "-1/2"
_FRACTION_RE = re.compile(r"^-?\d+/\d+$")

# Match decimal/integer: "5", "0.5", ".50", "-3.2", "5.0"
_NUMERIC_RE = re.compile(r"^-?\d*\.?\d+$")


def strip_answer_decoration(answer: str) -> str:
    """Remove option labels like 'A) 0.5' → '0.5'."""
    return _OPTION_LABEL_RE.sub("", answer).strip()


def strip_units(answer: str) -> str:
    """Remove trailing units: '33 laddoos' → '33'."""
    answer = answer.strip()
    m = _UNIT_RE.match(answer)
    if m:
        return m.group(1)
    return answer


def normalize_numeric(answer: str) -> str | None:
    """
    Convert a numeric answer string to canonical form.

    Returns:
        Canonical string: integers as "5", terminating decimals as "0.5",
        non-terminating fractions as reduced "1/3".
        None if the answer is not numeric.
    """
    s = answer.strip().replace(",", "")
    if not s:
        return None

    try:
        frac: Fraction | None = None

        if _FRACTION_RE.match(s):
            frac = Fraction(s)
        elif _NUMERIC_RE.match(s):
            frac = Fraction(s)
        else:
            return None

        # Check if it's an integer
        if frac.denominator == 1:
            return str(frac.numerator)

        # Check if it's a terminating decimal:
        # A fraction in lowest terms has a terminating decimal iff
        # the denominator has no prime factors other than 2 and 5.
        d = frac.denominator
        for p in (2, 5):
            while d % p == 0:
                d //= p
        if d == 1:
            # Terminating decimal — convert to float string, strip trailing zeros
            float_val = float(frac)
            # Format with enough precision, then strip
            formatted = f"{float_val:.10f}".rstrip("0").rstrip(".")
            # Ensure leading zero for values like .5
            if formatted.startswith("."):
                formatted = "0" + formatted
            elif formatted.startswith("-."):
                formatted = "-0" + formatted[1:]
            return formatted
        else:
            # Non-terminating — keep as reduced fraction
            return str(frac)

    except (ValueError, ZeroDivisionError):
        return None


def answers_equivalent(a: str, b: str) -> bool:
    """
    Check if two answer strings are equivalent.

    Normalizes both sides numerically. Falls back to case-insensitive
    string comparison for non-numeric answers.
    """
    a_stripped = strip_answer_decoration(strip_units(a.strip()))
    b_stripped = strip_answer_decoration(strip_units(b.strip()))

    norm_a = normalize_numeric(a_stripped)
    norm_b = normalize_numeric(b_stripped)

    if norm_a is not None and norm_b is not None:
        return norm_a == norm_b

    # Fallback: case-insensitive string match
    return a_stripped.lower() == b_stripped.lower()
