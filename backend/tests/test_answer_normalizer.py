"""Tests for the centralized answer normalizer (S5.1)."""

from app.utils.answer_normalizer import (
    answers_equivalent,
    normalize_numeric,
    strip_answer_decoration,
    strip_units,
)


# ---------------------------------------------------------------------------
# strip_answer_decoration
# ---------------------------------------------------------------------------


class TestStripAnswerDecoration:
    def test_option_label_paren(self):
        assert strip_answer_decoration("A) 0.5") == "0.5"

    def test_option_label_dot(self):
        assert strip_answer_decoration("B. 42") == "42"

    def test_option_label_lowercase(self):
        assert strip_answer_decoration("c) hello") == "hello"

    def test_option_label_parens(self):
        assert strip_answer_decoration("(d) 7") == "7"

    def test_no_label(self):
        assert strip_answer_decoration("0.5") == "0.5"


# ---------------------------------------------------------------------------
# strip_units
# ---------------------------------------------------------------------------


class TestStripUnits:
    def test_laddoos(self):
        assert strip_units("33 laddoos") == "33"

    def test_cm(self):
        assert strip_units("5.5 cm") == "5.5"

    def test_no_units(self):
        assert strip_units("42") == "42"

    def test_fraction_no_units(self):
        assert strip_units("1/2") == "1/2"

    def test_hindi_unit(self):
        assert strip_units("5 सेब") == "5"


# ---------------------------------------------------------------------------
# normalize_numeric
# ---------------------------------------------------------------------------


class TestNormalizeNumeric:
    # Integers
    def test_integer(self):
        assert normalize_numeric("5") == "5"

    def test_integer_with_trailing_zero(self):
        assert normalize_numeric("5.0") == "5"

    def test_negative_integer(self):
        assert normalize_numeric("-3") == "-3"

    # Terminating decimals
    def test_half(self):
        assert normalize_numeric("0.5") == "0.5"

    def test_dot_five(self):
        assert normalize_numeric(".50") == "0.5"

    def test_quarter(self):
        assert normalize_numeric("0.25") == "0.25"

    # Fractions
    def test_half_fraction(self):
        assert normalize_numeric("1/2") == "0.5"

    def test_two_fourths(self):
        assert normalize_numeric("2/4") == "0.5"

    def test_one_third(self):
        assert normalize_numeric("1/3") == "1/3"

    def test_two_sixths(self):
        assert normalize_numeric("2/6") == "1/3"

    def test_three_fourths(self):
        assert normalize_numeric("3/4") == "0.75"

    # Non-numeric
    def test_text(self):
        assert normalize_numeric("hello") is None

    def test_empty(self):
        assert normalize_numeric("") is None

    def test_comma_separator(self):
        assert normalize_numeric("1,000") == "1000"

    # Edge cases
    def test_zero(self):
        assert normalize_numeric("0") == "0"

    def test_negative_fraction(self):
        assert normalize_numeric("-1/2") == "-0.5"


# ---------------------------------------------------------------------------
# answers_equivalent
# ---------------------------------------------------------------------------


class TestAnswersEquivalent:
    # Core equivalences
    def test_half_variants(self):
        assert answers_equivalent("0.5", "1/2")
        assert answers_equivalent(".50", "1/2")
        assert answers_equivalent("2/4", "0.5")
        assert answers_equivalent("0.5", "2/4")

    def test_integer_decimal(self):
        assert answers_equivalent("5", "5.0")

    def test_non_terminating(self):
        assert answers_equivalent("1/3", "2/6")

    # Non-equivalent
    def test_not_equal(self):
        assert not answers_equivalent("0.5", "0.25")

    def test_fraction_not_equal(self):
        assert not answers_equivalent("1/3", "1/4")

    # String fallback
    def test_string_case_insensitive(self):
        assert answers_equivalent("True", "true")
        assert answers_equivalent("HELLO", "hello")

    def test_string_not_equal(self):
        assert not answers_equivalent("True", "False")

    # With decorations
    def test_with_option_label(self):
        assert answers_equivalent("A) 0.5", "1/2")

    def test_with_units(self):
        assert answers_equivalent("33 laddoos", "33")

    # Mixed numeric/non-numeric
    def test_numeric_vs_text(self):
        assert not answers_equivalent("5", "five")
