"""
Tests for the multi-step arithmetic expression parser.

All tests run fully offline — no Supabase or LLM calls required.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.quality_reviewer import _extract_arithmetic_expression


# ---------------------------------------------------------------------------
# _extract_arithmetic_expression
# ---------------------------------------------------------------------------


class TestExtractArithmeticExpression:
    def test_chained_addition(self):
        result = _extract_arithmetic_expression("What is 5 + 3 + 2?")
        assert result is not None
        _expr, value = result
        assert value == 10.0

    def test_mixed_operators(self):
        result = _extract_arithmetic_expression("Solve: 3 * 4 + 5")
        assert result is not None
        _expr, value = result
        assert value == 17.0

    def test_parenthesized(self):
        result = _extract_arithmetic_expression("Calculate (2 + 3) * 4")
        assert result is not None
        _expr, value = result
        assert value == 20.0

    def test_simple_binary_still_works(self):
        result = _extract_arithmetic_expression("What is 5 + 7?")
        assert result is not None
        _expr, value = result
        assert value == 12.0

    def test_word_problem_still_skipped(self):
        result = _extract_arithmetic_expression("Riya had 5 + 3 + 2 apples")
        assert result is None

    def test_blank_marker_still_skipped(self):
        result = _extract_arithmetic_expression("5 + 3 + __ = 10")
        assert result is None

    def test_unicode_operators(self):
        # × is normalised to * by _OP_NORMALISE
        result = _extract_arithmetic_expression("Find 5 \u00d7 3 + 2")
        assert result is not None
        _expr, value = result
        assert value == 17.0

    def test_subtraction_chain(self):
        result = _extract_arithmetic_expression("Solve 20 - 5 - 3")
        assert result is not None
        _expr, value = result
        assert value == 12.0

    def test_no_expression_returns_none(self):
        result = _extract_arithmetic_expression("What colour is the sky?")
        assert result is None
