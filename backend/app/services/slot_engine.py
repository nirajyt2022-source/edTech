"""
Slot-based worksheet generation engine v6.0 — Controlled Variation

Backend controls structure; LLM fills content only.
Two-phase: meta generation -> per-question generation with dedup + repair.

v6.0 additions:
- Persistent history store (last 30 worksheets) for cross-worksheet dedup
- Deterministic error computation (5 carry-related misconception tags)
- History-aware variant selection with seeded RNG
- Post-generation repair for critical constraints

Pipeline:
  1. generate_meta()        -> micro_skill, common_mistakes, parent_tip
  2. get_slot_plan()        -> deterministic slot sequence
  3. get_avoid_state()      -> from history store
  4. pick variants           -> seeded RNG + history avoidance
  5. generate_question()    -> one LLM call per slot, validated inline
  6. repair pass            -> fix critical constraint violations
  7. update_history()       -> persist for next generation
"""

import hashlib
import json
import logging
import random
import re
from collections import Counter
from datetime import date

from app.services.history_store import (
    get_avoid_state,
    update_history,
    build_worksheet_record,
)
logger = logging.getLogger("practicecraft.slot_engine")


# ════════════════════════════════════════════════════════════
# A) Deterministic Slot Plans
# ════════════════════════════════════════════════════════════

SLOT_PLANS: dict[int, dict[str, int]] = {
    5:  {"recognition": 1, "application": 1, "representation": 1, "error_detection": 1, "thinking": 1},
    10: {"recognition": 2, "application": 4, "representation": 2, "error_detection": 1, "thinking": 1},
    15: {"recognition": 3, "application": 6, "representation": 3, "error_detection": 2, "thinking": 1},
    20: {"recognition": 4, "application": 8, "representation": 4, "error_detection": 2, "thinking": 2},
}

SLOT_ORDER = ["recognition", "application", "representation", "error_detection", "thinking"]

VALID_FORMATS: dict[str, set[str]] = {
    "recognition": {
        "column_setup", "place_value", "simple_identify",
        "fraction_number", "clock_question", "calendar_question",
        "money_question", "symmetry_question", "shape_pattern",
        "division_problem", "place_value_question", "comparison_question",
        "multiplication_problem",
    },
    "application": {
        "word_problem", "sequence_question", "symmetry_complete",
        "pattern_question", "ordering_question", "comparison_question",
    },
    "representation": {
        "missing_number", "estimation", "place_value", "shape_question",
        "expanded_form",
    },
    "error_detection": {"error_spot"},
    "thinking": {"thinking", "growing_pattern", "multi_step"},
}

DEFAULT_FORMAT_BY_SLOT_TYPE: dict[str, str] = {
    "recognition": "column_setup",
    "application": "word_problem",
    "representation": "missing_number",
    "error_detection": "error_spot",
    "thinking": "thinking",
}

# ════════════════════════════════════════════════════════════
# A-eng) English Language Format Dicts
# ════════════════════════════════════════════════════════════

VALID_FORMATS_ENGLISH: dict[str, set[str]] = {
    "recognition": {
        "identify_noun", "identify_verb", "identify_adjective",
        "identify_pronoun", "identify_adverb", "identify_preposition",
        "identify_conjunction", "identify_tense", "identify_sentence_type",
        "identify_prefix", "identify_suffix", "identify_rhyme",
        "identify_punctuation", "pick_correct",
    },
    "application": {
        "fill_in_blank", "rewrite_sentence", "match_columns",
        "use_in_sentence", "word_problem_english", "correct_sentence",
    },
    "representation": {
        "complete_sentence", "rearrange_words", "change_form",
        "expand_sentence", "paragraph_cloze",
    },
    "error_detection": {"error_spot_english"},
    "thinking": {"explain_why", "creative_writing"},
}

DEFAULT_FORMAT_BY_SLOT_TYPE_ENGLISH: dict[str, str] = {
    "recognition": "pick_correct",
    "application": "fill_in_blank",
    "representation": "complete_sentence",
    "error_detection": "error_spot_english",
    "thinking": "explain_why",
}

# ════════════════════════════════════════════════════════════
# A-sci) Science Format Dicts
# ════════════════════════════════════════════════════════════

VALID_FORMATS_SCIENCE: dict[str, set[str]] = {
    "recognition": {
        "identify_part", "classify_object", "true_false",
        "match_function", "label_diagram", "pick_correct_science",
    },
    "application": {
        "explain_why_science", "what_happens_if", "give_example",
        "compare_two", "word_problem_science",
    },
    "representation": {
        "fill_diagram", "sequence_steps", "cause_effect",
        "complete_sentence_science",
    },
    "error_detection": {"error_spot_science"},
    "thinking": {"thinking_science", "multi_step_science"},
}

DEFAULT_FORMAT_BY_SLOT_TYPE_SCIENCE: dict[str, str] = {
    "recognition": "pick_correct_science",
    "application": "explain_why_science",
    "representation": "sequence_steps",
    "error_detection": "error_spot_science",
    "thinking": "thinking_science",
}

# ════════════════════════════════════════════════════════════
# A-hin) Hindi Language Format Dicts
# ════════════════════════════════════════════════════════════

VALID_FORMATS_HINDI: dict[str, set[str]] = {
    "recognition": {
        "identify_letter", "identify_matra", "identify_word_type",
        "match_letter_sound", "pick_correct_hindi",
    },
    "application": {
        "fill_matra", "make_word", "make_sentence_hindi",
        "use_in_sentence_hindi", "word_problem_hindi",
    },
    "representation": {
        "complete_word", "rearrange_letters", "word_formation",
        "complete_sentence_hindi",
    },
    "error_detection": {"error_spot_hindi"},
    "thinking": {"creative_writing_hindi", "explain_meaning"},
}

DEFAULT_FORMAT_BY_SLOT_TYPE_HINDI: dict[str, str] = {
    "recognition": "pick_correct_hindi",
    "application": "fill_matra",
    "representation": "complete_word",
    "error_detection": "error_spot_hindi",
    "thinking": "explain_meaning",
}


def get_valid_formats(subject: str = "Mathematics") -> dict[str, set[str]]:
    """Return the VALID_FORMATS dict for the given subject."""
    if subject and subject.lower() == "english":
        return VALID_FORMATS_ENGLISH
    if subject and subject.lower() in ("science", "computer", "gk", "moral science", "health"):
        return VALID_FORMATS_SCIENCE
    if subject and subject.lower() == "hindi":
        return VALID_FORMATS_HINDI
    return VALID_FORMATS


def get_default_format_by_slot(subject: str = "Mathematics") -> dict[str, str]:
    """Return the DEFAULT_FORMAT_BY_SLOT_TYPE dict for the given subject."""
    if subject and subject.lower() == "english":
        return DEFAULT_FORMAT_BY_SLOT_TYPE_ENGLISH
    if subject and subject.lower() in ("science", "computer", "gk", "moral science", "health"):
        return DEFAULT_FORMAT_BY_SLOT_TYPE_SCIENCE
    if subject and subject.lower() == "hindi":
        return DEFAULT_FORMAT_BY_SLOT_TYPE_HINDI
    return DEFAULT_FORMAT_BY_SLOT_TYPE


_DOCTRINE_WEIGHTS = {
    "recognition": 0.20, "application": 0.40, "representation": 0.20,
    "error_detection": 0.10, "thinking": 0.10,
}

# Mapping from mix_recipe skill_tag → (slot_type, format)
_SKILL_TAG_TO_SLOT: dict[str, tuple[str, str]] = {
    # Generic / arithmetic
    "column_setup": ("recognition", "column_setup"),
    "place_value": ("recognition", "place_value"),
    "word_problem": ("application", "word_problem"),
    "missing_number": ("representation", "missing_number"),
    "estimation": ("representation", "estimation"),
    "error_spot": ("error_detection", "error_spot"),
    "thinking": ("thinking", "multi_step"),
    # Addition / Subtraction
    "column_add_with_carry": ("recognition", "column_setup"),
    "addition_word_problem": ("application", "word_problem"),
    "addition_error_spot": ("error_detection", "error_spot"),
    "column_sub_with_borrow": ("recognition", "column_setup"),
    "subtraction_word_problem": ("application", "word_problem"),
    "subtraction_error_spot": ("error_detection", "error_spot"),
    # Multiplication
    "multiplication_tables": ("recognition", "multiplication_problem"),
    "multiplication_word_problem": ("application", "word_problem"),
    "multiplication_fill_blank": ("representation", "missing_number"),
    "multiplication_error_spot": ("error_detection", "error_spot"),
    "multiplication_thinking": ("thinking", "multi_step"),
    # Division
    "division_basics": ("recognition", "division_problem"),
    "division_word_problem": ("application", "word_problem"),
    "division_fill_blank": ("representation", "missing_number"),
    "division_error_spot": ("error_detection", "error_spot"),
    "division_thinking": ("thinking", "multi_step"),
    # Numbers and Place Value
    "place_value_identify": ("recognition", "place_value_question"),
    "number_comparison": ("application", "comparison_question"),
    "number_sequence": ("application", "sequence_question"),
    "number_expansion": ("representation", "expanded_form"),
    "number_ordering": ("application", "ordering_question"),
    "place_value_error": ("error_detection", "error_spot"),
    "number_thinking": ("thinking", "multi_step"),
    # Fractions
    "fraction_identify_half": ("recognition", "fraction_number"),
    "fraction_identify_quarter": ("recognition", "fraction_number"),
    "fraction_word_problem": ("application", "word_problem"),
    "fraction_of_shape_shaded": ("representation", "shape_question"),
    "fraction_error_spot": ("error_detection", "error_spot"),
    "fraction_thinking": ("thinking", "multi_step"),
    # Fractions (generic profile extras)
    "fraction_compare": ("application", "comparison_question"),
    "fraction_fill_blank": ("representation", "missing_number"),
    # Time (clock, calendar)
    "clock_reading": ("recognition", "clock_question"),
    "time_word_problem": ("application", "word_problem"),
    "calendar_reading": ("recognition", "calendar_question"),
    "time_fill_blank": ("representation", "missing_number"),
    "time_error_spot": ("error_detection", "error_spot"),
    "time_thinking": ("thinking", "multi_step"),
    # Money
    "money_recognition": ("recognition", "money_question"),
    "money_word_problem": ("application", "word_problem"),
    "money_change": ("application", "word_problem"),
    "money_fill_blank": ("representation", "missing_number"),
    "money_error_spot": ("error_detection", "error_spot"),
    "money_thinking": ("thinking", "multi_step"),
    # Symmetry
    "symmetry_identify": ("recognition", "symmetry_question"),
    "symmetry_draw": ("application", "symmetry_complete"),
    "symmetry_fill_blank": ("representation", "shape_question"),
    "symmetry_error_spot": ("error_detection", "error_spot"),
    "symmetry_thinking": ("thinking", "multi_step"),
    # Patterns
    "number_pattern": ("recognition", "shape_pattern"),
    "shape_pattern": ("application", "pattern_question"),
    "pattern_fill_blank": ("representation", "missing_number"),
    "pattern_error_spot": ("error_detection", "error_spot"),
    "pattern_thinking": ("thinking", "growing_pattern"),
    # ── Class 1 specific tags ──
    # Numbers 1 to 50 (Class 1)
    "c1_count_identify": ("recognition", "simple_identify"),
    "c1_number_compare": ("application", "comparison_question"),
    "c1_number_order": ("representation", "missing_number"),
    "c1_number_error": ("error_detection", "error_spot"),
    "c1_number_think": ("thinking", "multi_step"),
    # Numbers 51 to 100 (Class 1)
    "c1_count_big_identify": ("recognition", "simple_identify"),
    "c1_number_big_compare": ("application", "comparison_question"),
    "c1_number_big_order": ("representation", "missing_number"),
    "c1_number_big_error": ("error_detection", "error_spot"),
    "c1_number_big_think": ("thinking", "multi_step"),
    # Addition up to 20 (Class 1)
    "c1_add_basic": ("recognition", "simple_identify"),
    "c1_add_word_problem": ("application", "word_problem"),
    "c1_add_missing": ("representation", "missing_number"),
    "c1_add_error": ("error_detection", "error_spot"),
    "c1_add_think": ("thinking", "multi_step"),
    # Subtraction within 20 (Class 1)
    "c1_sub_basic": ("recognition", "simple_identify"),
    "c1_sub_word_problem": ("application", "word_problem"),
    "c1_sub_missing": ("representation", "missing_number"),
    "c1_sub_error": ("error_detection", "error_spot"),
    "c1_sub_think": ("thinking", "multi_step"),
    # Basic Shapes (Class 1)
    "c1_shape_identify": ("recognition", "simple_identify"),
    "c1_shape_match": ("application", "word_problem"),
    "c1_shape_count": ("representation", "missing_number"),
    "c1_shape_error": ("error_detection", "error_spot"),
    "c1_shape_think": ("thinking", "multi_step"),
    # Measurement (Class 1)
    "c1_measure_compare": ("recognition", "simple_identify"),
    "c1_measure_order": ("application", "comparison_question"),
    "c1_measure_fill": ("representation", "missing_number"),
    "c1_measure_error": ("error_detection", "error_spot"),
    "c1_measure_think": ("thinking", "multi_step"),
    # Time (Class 1)
    "c1_time_identify": ("recognition", "simple_identify"),
    "c1_time_sequence": ("application", "word_problem"),
    "c1_time_fill": ("representation", "missing_number"),
    "c1_time_error": ("error_detection", "error_spot"),
    "c1_time_think": ("thinking", "multi_step"),
    # Money (Class 1)
    "c1_money_identify": ("recognition", "money_question"),
    "c1_money_count": ("application", "word_problem"),
    "c1_money_fill": ("representation", "missing_number"),
    "c1_money_error": ("error_detection", "error_spot"),
    "c1_money_think": ("thinking", "multi_step"),
    # ── Class 2 specific tags ──
    # Numbers up to 1000 (Class 2)
    "c2_place_value_identify": ("recognition", "place_value_question"),
    "c2_number_compare": ("application", "comparison_question"),
    "c2_number_expansion": ("representation", "expanded_form"),
    "c2_number_ordering": ("application", "ordering_question"),
    "c2_place_value_error": ("error_detection", "error_spot"),
    "c2_number_thinking": ("thinking", "multi_step"),
    # Addition (2-digit with carry)
    "c2_add_column": ("recognition", "column_setup"),
    "c2_add_word_problem": ("application", "word_problem"),
    "c2_add_missing_number": ("representation", "missing_number"),
    "c2_add_error_spot": ("error_detection", "error_spot"),
    "c2_add_thinking": ("thinking", "multi_step"),
    # Subtraction (2-digit with borrow)
    "c2_sub_column": ("recognition", "column_setup"),
    "c2_sub_word_problem": ("application", "word_problem"),
    "c2_sub_missing_number": ("representation", "missing_number"),
    "c2_sub_error_spot": ("error_detection", "error_spot"),
    "c2_sub_thinking": ("thinking", "multi_step"),
    # Multiplication (tables 2-5)
    "c2_mult_tables": ("recognition", "multiplication_problem"),
    "c2_mult_word_problem": ("application", "word_problem"),
    "c2_mult_fill_blank": ("representation", "missing_number"),
    "c2_mult_error_spot": ("error_detection", "error_spot"),
    "c2_mult_thinking": ("thinking", "multi_step"),
    # Division (sharing equally)
    "c2_div_sharing": ("recognition", "division_problem"),
    "c2_div_word_problem": ("application", "word_problem"),
    "c2_div_fill_blank": ("representation", "missing_number"),
    "c2_div_error_spot": ("error_detection", "error_spot"),
    "c2_div_thinking": ("thinking", "multi_step"),
    # Shapes and space (2D)
    "c2_shape_identify": ("recognition", "symmetry_question"),
    "c2_shape_word_problem": ("application", "word_problem"),
    "c2_shape_fill_blank": ("representation", "shape_question"),
    "c2_shape_error_spot": ("error_detection", "error_spot"),
    "c2_shape_thinking": ("thinking", "multi_step"),
    # Measurement (length, weight)
    "c2_measure_identify": ("recognition", "simple_identify"),
    "c2_measure_compare": ("application", "comparison_question"),
    "c2_measure_fill_blank": ("representation", "missing_number"),
    "c2_measure_error_spot": ("error_detection", "error_spot"),
    "c2_measure_thinking": ("thinking", "multi_step"),
    # Time (hour, half-hour)
    "c2_clock_reading": ("recognition", "clock_question"),
    "c2_time_word_problem": ("application", "word_problem"),
    "c2_time_fill_blank": ("representation", "missing_number"),
    "c2_time_error_spot": ("error_detection", "error_spot"),
    "c2_time_thinking": ("thinking", "multi_step"),
    # Money (coins and notes)
    "c2_money_identify": ("recognition", "money_question"),
    "c2_money_word_problem": ("application", "word_problem"),
    "c2_money_fill_blank": ("representation", "missing_number"),
    "c2_money_error_spot": ("error_detection", "error_spot"),
    "c2_money_thinking": ("thinking", "multi_step"),
    # Data handling (pictographs)
    "c2_data_read": ("recognition", "simple_identify"),
    "c2_data_word_problem": ("application", "word_problem"),
    "c2_data_fill_blank": ("representation", "missing_number"),
    "c2_data_error_spot": ("error_detection", "error_spot"),
    "c2_data_thinking": ("thinking", "multi_step"),
    # ── Class 4 specific tags ──────────────────────────────
    # Large numbers (up to 1,00,000)
    "c4_large_number_identify": ("recognition", "place_value_question"),
    "c4_large_number_compare": ("application", "comparison_question"),
    "c4_large_number_order": ("application", "ordering_question"),
    "c4_large_number_expand": ("representation", "expanded_form"),
    "c4_large_number_error": ("error_detection", "error_spot"),
    "c4_large_number_thinking": ("thinking", "multi_step"),
    # Addition and subtraction (5-digit)
    "c4_add5_column": ("recognition", "column_setup"),
    "c4_add5_word_problem": ("application", "word_problem"),
    "c4_sub5_column": ("recognition", "column_setup"),
    "c4_sub5_word_problem": ("application", "word_problem"),
    "c4_addsub5_missing": ("representation", "missing_number"),
    "c4_addsub5_error": ("error_detection", "error_spot"),
    "c4_addsub5_thinking": ("thinking", "multi_step"),
    # Multiplication (3-digit x 2-digit)
    "c4_mult_setup": ("recognition", "multiplication_problem"),
    "c4_mult_word_problem": ("application", "word_problem"),
    "c4_mult_missing": ("representation", "missing_number"),
    "c4_mult_error": ("error_detection", "error_spot"),
    "c4_mult_thinking": ("thinking", "multi_step"),
    # Division (long division)
    "c4_div_setup": ("recognition", "division_problem"),
    "c4_div_word_problem": ("application", "word_problem"),
    "c4_div_missing": ("representation", "missing_number"),
    "c4_div_error": ("error_detection", "error_spot"),
    "c4_div_thinking": ("thinking", "multi_step"),
    # Fractions (equivalent, comparison)
    "c4_fraction_identify": ("recognition", "fraction_number"),
    "c4_fraction_compare": ("application", "comparison_question"),
    "c4_fraction_equivalent": ("application", "word_problem"),
    "c4_fraction_represent": ("representation", "missing_number"),
    "c4_fraction_error": ("error_detection", "error_spot"),
    "c4_fraction_thinking": ("thinking", "multi_step"),
    # Decimals (tenths, hundredths)
    "c4_decimal_identify": ("recognition", "place_value_question"),
    "c4_decimal_compare": ("application", "comparison_question"),
    "c4_decimal_word_problem": ("application", "word_problem"),
    "c4_decimal_represent": ("representation", "expanded_form"),
    "c4_decimal_error": ("error_detection", "error_spot"),
    "c4_decimal_thinking": ("thinking", "multi_step"),
    # Geometry (angles, lines)
    "c4_geometry_identify": ("recognition", "simple_identify"),
    "c4_geometry_classify": ("application", "comparison_question"),
    "c4_geometry_represent": ("representation", "shape_question"),
    "c4_geometry_error": ("error_detection", "error_spot"),
    "c4_geometry_thinking": ("thinking", "multi_step"),
    # Perimeter and area
    "c4_perimeter_identify": ("recognition", "simple_identify"),
    "c4_perimeter_word_problem": ("application", "word_problem"),
    "c4_area_word_problem": ("application", "word_problem"),
    "c4_perimeter_area_missing": ("representation", "missing_number"),
    "c4_perimeter_area_error": ("error_detection", "error_spot"),
    "c4_perimeter_area_thinking": ("thinking", "multi_step"),
    # Time (minutes, 24-hour clock)
    "c4_time_reading": ("recognition", "clock_question"),
    "c4_time_word_problem": ("application", "word_problem"),
    "c4_time_convert": ("application", "word_problem"),
    "c4_time_missing": ("representation", "missing_number"),
    "c4_time_error": ("error_detection", "error_spot"),
    "c4_time_thinking": ("thinking", "multi_step"),
    # Money (bills, profit/loss)
    "c4_money_identify": ("recognition", "money_question"),
    "c4_money_word_problem": ("application", "word_problem"),
    "c4_money_profit_loss": ("application", "word_problem"),
    "c4_money_missing": ("representation", "missing_number"),
    "c4_money_error": ("error_detection", "error_spot"),
    "c4_money_thinking": ("thinking", "multi_step"),
    # ── Class 5 specific tags ──────────────────────────────
    # Numbers up to 10 lakh (Class 5)
    "c5_lakh_identify": ("recognition", "place_value_question"),
    "c5_lakh_compare": ("application", "comparison_question"),
    "c5_lakh_expand": ("representation", "expanded_form"),
    "c5_lakh_error": ("error_detection", "error_spot"),
    "c5_lakh_think": ("thinking", "multi_step"),
    # Factors and multiples (Class 5)
    "c5_factor_identify": ("recognition", "simple_identify"),
    "c5_factor_apply": ("application", "word_problem"),
    "c5_factor_missing": ("representation", "missing_number"),
    "c5_factor_error": ("error_detection", "error_spot"),
    "c5_factor_think": ("thinking", "multi_step"),
    # HCF and LCM (Class 5)
    "c5_hcf_identify": ("recognition", "simple_identify"),
    "c5_hcf_apply": ("application", "word_problem"),
    "c5_hcf_missing": ("representation", "missing_number"),
    "c5_hcf_error": ("error_detection", "error_spot"),
    "c5_hcf_think": ("thinking", "multi_step"),
    # Fractions (add and subtract) (Class 5)
    "c5_frac_identify": ("recognition", "fraction_number"),
    "c5_frac_apply": ("application", "word_problem"),
    "c5_frac_missing": ("representation", "missing_number"),
    "c5_frac_error": ("error_detection", "error_spot"),
    "c5_frac_think": ("thinking", "multi_step"),
    # Decimals (all operations) (Class 5)
    "c5_dec_identify": ("recognition", "place_value_question"),
    "c5_dec_apply": ("application", "word_problem"),
    "c5_dec_missing": ("representation", "missing_number"),
    "c5_dec_error": ("error_detection", "error_spot"),
    "c5_dec_think": ("thinking", "multi_step"),
    # Percentage (Class 5)
    "c5_percent_identify": ("recognition", "simple_identify"),
    "c5_percent_apply": ("application", "word_problem"),
    "c5_percent_missing": ("representation", "missing_number"),
    "c5_percent_error": ("error_detection", "error_spot"),
    "c5_percent_think": ("thinking", "multi_step"),
    # Area and volume (Class 5)
    "c5_area_identify": ("recognition", "simple_identify"),
    "c5_area_apply": ("application", "word_problem"),
    "c5_area_missing": ("representation", "missing_number"),
    "c5_area_error": ("error_detection", "error_spot"),
    "c5_area_think": ("thinking", "multi_step"),
    # Geometry (circles, symmetry) (Class 5)
    "c5_geo_identify": ("recognition", "simple_identify"),
    "c5_geo_apply": ("application", "word_problem"),
    "c5_geo_missing": ("representation", "shape_question"),
    "c5_geo_error": ("error_detection", "error_spot"),
    "c5_geo_think": ("thinking", "multi_step"),
    # Data handling (pie charts) (Class 5)
    "c5_data_identify": ("recognition", "simple_identify"),
    "c5_data_apply": ("application", "word_problem"),
    "c5_data_missing": ("representation", "missing_number"),
    "c5_data_error": ("error_detection", "error_spot"),
    "c5_data_think": ("thinking", "multi_step"),
    # Speed distance time (Class 5)
    "c5_speed_identify": ("recognition", "simple_identify"),
    "c5_speed_apply": ("application", "word_problem"),
    "c5_speed_missing": ("representation", "missing_number"),
    "c5_speed_error": ("error_detection", "error_spot"),
    "c5_speed_think": ("thinking", "multi_step"),
    # ── English Language skill tags ──────────────────────────
    # Class 1 English
    "eng_c1_alpha_identify": ("recognition", "pick_correct"),
    "eng_c1_alpha_match": ("application", "match_columns"),
    "eng_c1_alpha_fill": ("representation", "complete_sentence"),
    "eng_c1_alpha_error": ("error_detection", "error_spot_english"),
    "eng_c1_alpha_think": ("thinking", "explain_why"),
    "eng_c1_phonics_identify": ("recognition", "pick_correct"),
    "eng_c1_phonics_match": ("application", "fill_in_blank"),
    "eng_c1_phonics_fill": ("representation", "complete_sentence"),
    "eng_c1_phonics_error": ("error_detection", "error_spot_english"),
    "eng_c1_phonics_think": ("thinking", "explain_why"),
    "eng_c1_family_identify": ("recognition", "pick_correct"),
    "eng_c1_family_match": ("application", "fill_in_blank"),
    "eng_c1_family_fill": ("representation", "complete_sentence"),
    "eng_c1_family_error": ("error_detection", "error_spot_english"),
    "eng_c1_family_think": ("thinking", "explain_why"),
    "eng_c1_animals_identify": ("recognition", "pick_correct"),
    "eng_c1_animals_match": ("application", "match_columns"),
    "eng_c1_animals_fill": ("representation", "complete_sentence"),
    "eng_c1_animals_error": ("error_detection", "error_spot_english"),
    "eng_c1_animals_think": ("thinking", "explain_why"),
    "eng_c1_greetings_identify": ("recognition", "pick_correct"),
    "eng_c1_greetings_match": ("application", "fill_in_blank"),
    "eng_c1_greetings_fill": ("representation", "complete_sentence"),
    "eng_c1_greetings_error": ("error_detection", "error_spot_english"),
    "eng_c1_greetings_think": ("thinking", "explain_why"),
    "eng_c1_seasons_identify": ("recognition", "pick_correct"),
    "eng_c1_seasons_match": ("application", "fill_in_blank"),
    "eng_c1_seasons_fill": ("representation", "complete_sentence"),
    "eng_c1_seasons_error": ("error_detection", "error_spot_english"),
    "eng_c1_seasons_think": ("thinking", "explain_why"),
    "eng_c1_simple_identify": ("recognition", "pick_correct"),
    "eng_c1_simple_rewrite": ("application", "rewrite_sentence"),
    "eng_c1_simple_fill": ("representation", "complete_sentence"),
    "eng_c1_simple_error": ("error_detection", "error_spot_english"),
    "eng_c1_simple_think": ("thinking", "creative_writing"),
    # Class 2 English
    "eng_noun_identify": ("recognition", "identify_noun"),
    "eng_noun_use": ("application", "fill_in_blank"),
    "eng_noun_complete": ("representation", "complete_sentence"),
    "eng_noun_error": ("error_detection", "error_spot_english"),
    "eng_noun_thinking": ("thinking", "explain_why"),
    "eng_verb_identify": ("recognition", "identify_verb"),
    "eng_verb_use": ("application", "fill_in_blank"),
    "eng_verb_complete": ("representation", "complete_sentence"),
    "eng_verb_error": ("error_detection", "error_spot_english"),
    "eng_verb_thinking": ("thinking", "explain_why"),
    "eng_pronoun_identify": ("recognition", "identify_pronoun"),
    "eng_pronoun_use": ("application", "fill_in_blank"),
    "eng_pronoun_complete": ("representation", "complete_sentence"),
    "eng_pronoun_error": ("error_detection", "error_spot_english"),
    "eng_pronoun_thinking": ("thinking", "explain_why"),
    "eng_sentence_identify": ("recognition", "identify_sentence_type"),
    "eng_sentence_rewrite": ("application", "rewrite_sentence"),
    "eng_sentence_rearrange": ("representation", "rearrange_words"),
    "eng_sentence_error": ("error_detection", "error_spot_english"),
    "eng_sentence_thinking": ("thinking", "creative_writing"),
    "eng_rhyme_identify": ("recognition", "identify_rhyme"),
    "eng_rhyme_match": ("application", "match_columns"),
    "eng_rhyme_complete": ("representation", "complete_sentence"),
    "eng_rhyme_error": ("error_detection", "error_spot_english"),
    "eng_rhyme_thinking": ("thinking", "creative_writing"),
    "eng_punctuation_identify": ("recognition", "identify_punctuation"),
    "eng_punctuation_use": ("application", "correct_sentence"),
    "eng_punctuation_complete": ("representation", "complete_sentence"),
    "eng_punctuation_error": ("error_detection", "error_spot_english"),
    "eng_punctuation_thinking": ("thinking", "explain_why"),
    # Class 3 English
    "eng_adjective_identify": ("recognition", "identify_adjective"),
    "eng_adjective_use": ("application", "fill_in_blank"),
    "eng_adjective_complete": ("representation", "complete_sentence"),
    "eng_adjective_error": ("error_detection", "error_spot_english"),
    "eng_adjective_thinking": ("thinking", "creative_writing"),
    "eng_tense_identify": ("recognition", "identify_tense"),
    "eng_tense_change": ("application", "rewrite_sentence"),
    "eng_tense_complete": ("representation", "change_form"),
    "eng_tense_error": ("error_detection", "error_spot_english"),
    "eng_tense_thinking": ("thinking", "explain_why"),
    "eng_vocabulary_identify": ("recognition", "pick_correct"),
    "eng_vocabulary_use": ("application", "use_in_sentence"),
    "eng_vocabulary_match": ("application", "match_columns"),
    "eng_vocabulary_complete": ("representation", "complete_sentence"),
    "eng_vocabulary_error": ("error_detection", "error_spot_english"),
    "eng_vocabulary_thinking": ("thinking", "explain_why"),
    "eng_comprehension_identify": ("recognition", "pick_correct"),
    "eng_comprehension_answer": ("application", "word_problem_english"),
    "eng_comprehension_complete": ("representation", "paragraph_cloze"),
    "eng_comprehension_error": ("error_detection", "error_spot_english"),
    "eng_comprehension_thinking": ("thinking", "explain_why"),
    # Class 4 English
    "eng_conjunction_identify": ("recognition", "identify_conjunction"),
    "eng_conjunction_use": ("application", "fill_in_blank"),
    "eng_conjunction_complete": ("representation", "complete_sentence"),
    "eng_conjunction_error": ("error_detection", "error_spot_english"),
    "eng_conjunction_thinking": ("thinking", "explain_why"),
    "eng_preposition_identify": ("recognition", "identify_preposition"),
    "eng_preposition_use": ("application", "fill_in_blank"),
    "eng_preposition_complete": ("representation", "complete_sentence"),
    "eng_preposition_error": ("error_detection", "error_spot_english"),
    "eng_preposition_thinking": ("thinking", "explain_why"),
    "eng_adverb_identify": ("recognition", "identify_adverb"),
    "eng_adverb_use": ("application", "fill_in_blank"),
    "eng_adverb_complete": ("representation", "complete_sentence"),
    "eng_adverb_error": ("error_detection", "error_spot_english"),
    "eng_adverb_thinking": ("thinking", "explain_why"),
    "eng_prefix_identify": ("recognition", "identify_prefix"),
    "eng_suffix_identify": ("recognition", "identify_suffix"),
    "eng_affix_use": ("application", "fill_in_blank"),
    "eng_affix_change": ("representation", "change_form"),
    "eng_affix_error": ("error_detection", "error_spot_english"),
    "eng_affix_thinking": ("thinking", "explain_why"),
    "eng_sentence_type_identify": ("recognition", "identify_sentence_type"),
    "eng_sentence_type_rewrite": ("application", "rewrite_sentence"),
    "eng_sentence_type_rearrange": ("representation", "rearrange_words"),
    "eng_sentence_type_error": ("error_detection", "error_spot_english"),
    "eng_sentence_type_thinking": ("thinking", "creative_writing"),
    # ── Class 5 English skill tags ──
    "eng_c5_voice_identify": ("recognition", "pick_correct"),
    "eng_c5_voice_convert": ("application", "rewrite_sentence"),
    "eng_c5_voice_complete": ("representation", "change_form"),
    "eng_c5_voice_error": ("error_detection", "error_spot_english"),
    "eng_c5_voice_thinking": ("thinking", "explain_why"),
    "eng_c5_speech_identify": ("recognition", "pick_correct"),
    "eng_c5_speech_convert": ("application", "rewrite_sentence"),
    "eng_c5_speech_complete": ("representation", "change_form"),
    "eng_c5_speech_error": ("error_detection", "error_spot_english"),
    "eng_c5_speech_thinking": ("thinking", "explain_why"),
    "eng_c5_complex_identify": ("recognition", "identify_sentence_type"),
    "eng_c5_complex_rewrite": ("application", "rewrite_sentence"),
    "eng_c5_complex_complete": ("representation", "complete_sentence"),
    "eng_c5_complex_error": ("error_detection", "error_spot_english"),
    "eng_c5_complex_thinking": ("thinking", "creative_writing"),
    "eng_c5_summary_identify": ("recognition", "pick_correct"),
    "eng_c5_summary_write": ("application", "word_problem_english"),
    "eng_c5_summary_complete": ("representation", "paragraph_cloze"),
    "eng_c5_summary_error": ("error_detection", "error_spot_english"),
    "eng_c5_summary_thinking": ("thinking", "explain_why"),
    "eng_c5_comprehension_identify": ("recognition", "pick_correct"),
    "eng_c5_comprehension_answer": ("application", "word_problem_english"),
    "eng_c5_comprehension_complete": ("representation", "paragraph_cloze"),
    "eng_c5_comprehension_error": ("error_detection", "error_spot_english"),
    "eng_c5_comprehension_thinking": ("thinking", "explain_why"),
    "eng_c5_synonym_identify": ("recognition", "pick_correct"),
    "eng_c5_synonym_match": ("application", "match_columns"),
    "eng_c5_synonym_use": ("representation", "complete_sentence"),
    "eng_c5_synonym_error": ("error_detection", "error_spot_english"),
    "eng_c5_synonym_thinking": ("thinking", "explain_why"),
    "eng_c5_letter_identify": ("recognition", "pick_correct"),
    "eng_c5_letter_write": ("application", "word_problem_english"),
    "eng_c5_letter_complete": ("representation", "paragraph_cloze"),
    "eng_c5_letter_error": ("error_detection", "error_spot_english"),
    "eng_c5_letter_thinking": ("thinking", "creative_writing"),
    "eng_c5_creative_identify": ("recognition", "pick_correct"),
    "eng_c5_creative_use": ("application", "use_in_sentence"),
    "eng_c5_creative_expand": ("representation", "expand_sentence"),
    "eng_c5_creative_error": ("error_detection", "error_spot_english"),
    "eng_c5_creative_thinking": ("thinking", "creative_writing"),
    "eng_c5_clause_identify": ("recognition", "identify_sentence_type"),
    "eng_c5_clause_rewrite": ("application", "rewrite_sentence"),
    "eng_c5_clause_complete": ("representation", "complete_sentence"),
    "eng_c5_clause_error": ("error_detection", "error_spot_english"),
    "eng_c5_clause_thinking": ("thinking", "explain_why"),
    # ── Science Class 3 skill tags ──
    "sci_plants_identify": ("recognition", "pick_correct_science"),
    "sci_plants_apply": ("application", "explain_why_science"),
    "sci_plants_represent": ("representation", "sequence_steps"),
    "sci_plants_error": ("error_detection", "error_spot_science"),
    "sci_plants_thinking": ("thinking", "thinking_science"),
    "sci_animals_identify": ("recognition", "classify_object"),
    "sci_animals_apply": ("application", "compare_two"),
    "sci_animals_represent": ("representation", "cause_effect"),
    "sci_animals_error": ("error_detection", "error_spot_science"),
    "sci_animals_thinking": ("thinking", "thinking_science"),
    "sci_food_identify": ("recognition", "pick_correct_science"),
    "sci_food_apply": ("application", "give_example"),
    "sci_food_represent": ("representation", "fill_diagram"),
    "sci_food_error": ("error_detection", "error_spot_science"),
    "sci_food_thinking": ("thinking", "thinking_science"),
    "sci_shelter_identify": ("recognition", "match_function"),
    "sci_shelter_apply": ("application", "compare_two"),
    "sci_shelter_represent": ("representation", "cause_effect"),
    "sci_shelter_error": ("error_detection", "error_spot_science"),
    "sci_shelter_thinking": ("thinking", "thinking_science"),
    "sci_water_identify": ("recognition", "true_false"),
    "sci_water_apply": ("application", "what_happens_if"),
    "sci_water_represent": ("representation", "sequence_steps"),
    "sci_water_error": ("error_detection", "error_spot_science"),
    "sci_water_thinking": ("thinking", "multi_step_science"),
    "sci_air_identify": ("recognition", "true_false"),
    "sci_air_apply": ("application", "explain_why_science"),
    "sci_air_represent": ("representation", "cause_effect"),
    "sci_air_error": ("error_detection", "error_spot_science"),
    "sci_air_thinking": ("thinking", "thinking_science"),
    "sci_body_identify": ("recognition", "identify_part"),
    "sci_body_apply": ("application", "explain_why_science"),
    "sci_body_represent": ("representation", "fill_diagram"),
    "sci_body_error": ("error_detection", "error_spot_science"),
    "sci_body_thinking": ("thinking", "multi_step_science"),
    # ── EVS Class 1 skill tags (6 topics) ──────────────────
    # My Family (Class 1)
    "sci_c1_family_identify": ("recognition", "pick_correct_science"),
    "sci_c1_family_apply": ("application", "give_example"),
    "sci_c1_family_represent": ("representation", "fill_diagram"),
    "sci_c1_family_error": ("error_detection", "error_spot_science"),
    "sci_c1_family_thinking": ("thinking", "thinking_science"),
    # My Body (Class 1)
    "sci_c1_body_identify": ("recognition", "identify_part"),
    "sci_c1_body_apply": ("application", "explain_why_science"),
    "sci_c1_body_represent": ("representation", "fill_diagram"),
    "sci_c1_body_error": ("error_detection", "error_spot_science"),
    "sci_c1_body_thinking": ("thinking", "thinking_science"),
    # Plants Around Us (Class 1)
    "sci_c1_plants_identify": ("recognition", "pick_correct_science"),
    "sci_c1_plants_apply": ("application", "give_example"),
    "sci_c1_plants_represent": ("representation", "sequence_steps"),
    "sci_c1_plants_error": ("error_detection", "error_spot_science"),
    "sci_c1_plants_thinking": ("thinking", "thinking_science"),
    # Animals Around Us (Class 1)
    "sci_c1_animals_identify": ("recognition", "classify_object"),
    "sci_c1_animals_apply": ("application", "compare_two"),
    "sci_c1_animals_represent": ("representation", "cause_effect"),
    "sci_c1_animals_error": ("error_detection", "error_spot_science"),
    "sci_c1_animals_thinking": ("thinking", "thinking_science"),
    # Food We Eat (Class 1)
    "sci_c1_food_identify": ("recognition", "pick_correct_science"),
    "sci_c1_food_apply": ("application", "give_example"),
    "sci_c1_food_represent": ("representation", "fill_diagram"),
    "sci_c1_food_error": ("error_detection", "error_spot_science"),
    "sci_c1_food_thinking": ("thinking", "thinking_science"),
    # Seasons and Weather (Class 1)
    "sci_c1_seasons_identify": ("recognition", "pick_correct_science"),
    "sci_c1_seasons_apply": ("application", "what_happens_if"),
    "sci_c1_seasons_represent": ("representation", "cause_effect"),
    "sci_c1_seasons_error": ("error_detection", "error_spot_science"),
    "sci_c1_seasons_thinking": ("thinking", "thinking_science"),
    # ── EVS Class 2 skill tags (6 topics) ──────────────────
    # Plants (Class 2)
    "sci_c2_plants_identify": ("recognition", "pick_correct_science"),
    "sci_c2_plants_apply": ("application", "explain_why_science"),
    "sci_c2_plants_represent": ("representation", "sequence_steps"),
    "sci_c2_plants_error": ("error_detection", "error_spot_science"),
    "sci_c2_plants_thinking": ("thinking", "thinking_science"),
    # Animals and Habitats (Class 2)
    "sci_c2_animals_identify": ("recognition", "classify_object"),
    "sci_c2_animals_apply": ("application", "compare_two"),
    "sci_c2_animals_represent": ("representation", "cause_effect"),
    "sci_c2_animals_error": ("error_detection", "error_spot_science"),
    "sci_c2_animals_thinking": ("thinking", "thinking_science"),
    # Food and Nutrition (Class 2)
    "sci_c2_food_identify": ("recognition", "pick_correct_science"),
    "sci_c2_food_apply": ("application", "give_example"),
    "sci_c2_food_represent": ("representation", "fill_diagram"),
    "sci_c2_food_error": ("error_detection", "error_spot_science"),
    "sci_c2_food_thinking": ("thinking", "thinking_science"),
    # Water (Class 2)
    "sci_c2_water_identify": ("recognition", "true_false"),
    "sci_c2_water_apply": ("application", "what_happens_if"),
    "sci_c2_water_represent": ("representation", "sequence_steps"),
    "sci_c2_water_error": ("error_detection", "error_spot_science"),
    "sci_c2_water_thinking": ("thinking", "thinking_science"),
    # Shelter (Class 2)
    "sci_c2_shelter_identify": ("recognition", "match_function"),
    "sci_c2_shelter_apply": ("application", "compare_two"),
    "sci_c2_shelter_represent": ("representation", "cause_effect"),
    "sci_c2_shelter_error": ("error_detection", "error_spot_science"),
    "sci_c2_shelter_thinking": ("thinking", "thinking_science"),
    # Our Senses (Class 2)
    "sci_c2_senses_identify": ("recognition", "identify_part"),
    "sci_c2_senses_apply": ("application", "give_example"),
    "sci_c2_senses_represent": ("representation", "fill_diagram"),
    "sci_c2_senses_error": ("error_detection", "error_spot_science"),
    "sci_c2_senses_thinking": ("thinking", "thinking_science"),
    # ── Science Class 4 skill tags (7 topics) ──────────────────
    # Living Things (Class 4)
    "sci_c4_living_identify": ("recognition", "classify_object"),
    "sci_c4_living_apply": ("application", "compare_two"),
    "sci_c4_living_represent": ("representation", "fill_diagram"),
    "sci_c4_living_error": ("error_detection", "error_spot_science"),
    "sci_c4_living_thinking": ("thinking", "thinking_science"),
    # Human Body (Class 4)
    "sci_c4_humanbody_identify": ("recognition", "identify_part"),
    "sci_c4_humanbody_apply": ("application", "explain_why_science"),
    "sci_c4_humanbody_represent": ("representation", "fill_diagram"),
    "sci_c4_humanbody_error": ("error_detection", "error_spot_science"),
    "sci_c4_humanbody_thinking": ("thinking", "multi_step_science"),
    # States of Matter (Class 4)
    "sci_c4_matter_identify": ("recognition", "pick_correct_science"),
    "sci_c4_matter_apply": ("application", "what_happens_if"),
    "sci_c4_matter_represent": ("representation", "cause_effect"),
    "sci_c4_matter_error": ("error_detection", "error_spot_science"),
    "sci_c4_matter_thinking": ("thinking", "thinking_science"),
    # Force and Motion (Class 4)
    "sci_c4_force_identify": ("recognition", "true_false"),
    "sci_c4_force_apply": ("application", "explain_why_science"),
    "sci_c4_force_represent": ("representation", "cause_effect"),
    "sci_c4_force_error": ("error_detection", "error_spot_science"),
    "sci_c4_force_thinking": ("thinking", "thinking_science"),
    # Simple Machines (Class 4)
    "sci_c4_machines_identify": ("recognition", "match_function"),
    "sci_c4_machines_apply": ("application", "give_example"),
    "sci_c4_machines_represent": ("representation", "fill_diagram"),
    "sci_c4_machines_error": ("error_detection", "error_spot_science"),
    "sci_c4_machines_thinking": ("thinking", "multi_step_science"),
    # Photosynthesis (Class 4)
    "sci_c4_photosyn_identify": ("recognition", "pick_correct_science"),
    "sci_c4_photosyn_apply": ("application", "explain_why_science"),
    "sci_c4_photosyn_represent": ("representation", "sequence_steps"),
    "sci_c4_photosyn_error": ("error_detection", "error_spot_science"),
    "sci_c4_photosyn_thinking": ("thinking", "thinking_science"),
    # Animal Adaptation (Class 4)
    "sci_c4_adapt_identify": ("recognition", "classify_object"),
    "sci_c4_adapt_apply": ("application", "compare_two"),
    "sci_c4_adapt_represent": ("representation", "cause_effect"),
    "sci_c4_adapt_error": ("error_detection", "error_spot_science"),
    "sci_c4_adapt_thinking": ("thinking", "thinking_science"),
    # ── Science Class 5 skill tags (7 topics) ──────────────────
    # Circulatory System (Class 5)
    "sci_c5_circulatory_identify": ("recognition", "identify_part"),
    "sci_c5_circulatory_apply": ("application", "explain_why_science"),
    "sci_c5_circulatory_represent": ("representation", "sequence_steps"),
    "sci_c5_circulatory_error": ("error_detection", "error_spot_science"),
    "sci_c5_circulatory_thinking": ("thinking", "multi_step_science"),
    # Respiratory and Nervous System (Class 5)
    "sci_c5_respnerv_identify": ("recognition", "identify_part"),
    "sci_c5_respnerv_apply": ("application", "explain_why_science"),
    "sci_c5_respnerv_represent": ("representation", "fill_diagram"),
    "sci_c5_respnerv_error": ("error_detection", "error_spot_science"),
    "sci_c5_respnerv_thinking": ("thinking", "thinking_science"),
    # Reproduction in Plants and Animals (Class 5)
    "sci_c5_reprod_identify": ("recognition", "pick_correct_science"),
    "sci_c5_reprod_apply": ("application", "compare_two"),
    "sci_c5_reprod_represent": ("representation", "sequence_steps"),
    "sci_c5_reprod_error": ("error_detection", "error_spot_science"),
    "sci_c5_reprod_thinking": ("thinking", "thinking_science"),
    # Physical and Chemical Changes (Class 5)
    "sci_c5_changes_identify": ("recognition", "classify_object"),
    "sci_c5_changes_apply": ("application", "what_happens_if"),
    "sci_c5_changes_represent": ("representation", "cause_effect"),
    "sci_c5_changes_error": ("error_detection", "error_spot_science"),
    "sci_c5_changes_thinking": ("thinking", "thinking_science"),
    # Forms of Energy (Class 5)
    "sci_c5_energy_identify": ("recognition", "pick_correct_science"),
    "sci_c5_energy_apply": ("application", "give_example"),
    "sci_c5_energy_represent": ("representation", "cause_effect"),
    "sci_c5_energy_error": ("error_detection", "error_spot_science"),
    "sci_c5_energy_thinking": ("thinking", "multi_step_science"),
    # Solar System and Earth (Class 5)
    "sci_c5_solar_identify": ("recognition", "true_false"),
    "sci_c5_solar_apply": ("application", "explain_why_science"),
    "sci_c5_solar_represent": ("representation", "sequence_steps"),
    "sci_c5_solar_error": ("error_detection", "error_spot_science"),
    "sci_c5_solar_thinking": ("thinking", "thinking_science"),
    # Ecosystem and Food Chains (Class 5)
    "sci_c5_ecosystem_identify": ("recognition", "classify_object"),
    "sci_c5_ecosystem_apply": ("application", "explain_why_science"),
    "sci_c5_ecosystem_represent": ("representation", "sequence_steps"),
    "sci_c5_ecosystem_error": ("error_detection", "error_spot_science"),
    "sci_c5_ecosystem_thinking": ("thinking", "thinking_science"),
    # ── Hindi Language skill tags ──────────────────────────
    # Varnamala (Class 3)
    "hin_varna_identify": ("recognition", "identify_letter"),
    "hin_varna_use": ("application", "fill_matra"),
    "hin_varna_complete": ("representation", "complete_word"),
    "hin_varna_error": ("error_detection", "error_spot_hindi"),
    "hin_varna_thinking": ("thinking", "explain_meaning"),
    # Matras (Class 3)
    "hin_matra_identify": ("recognition", "identify_matra"),
    "hin_matra_fill": ("application", "fill_matra"),
    "hin_matra_complete": ("representation", "complete_word"),
    "hin_matra_error": ("error_detection", "error_spot_hindi"),
    "hin_matra_thinking": ("thinking", "explain_meaning"),
    # Shabd Rachna (Class 3)
    "hin_shabd_identify": ("recognition", "identify_word_type"),
    "hin_shabd_make": ("application", "make_word"),
    "hin_shabd_complete": ("representation", "word_formation"),
    "hin_shabd_error": ("error_detection", "error_spot_hindi"),
    "hin_shabd_thinking": ("thinking", "explain_meaning"),
    # Vakya Rachna (Class 3)
    "hin_vakya_identify": ("recognition", "pick_correct_hindi"),
    "hin_vakya_make": ("application", "make_sentence_hindi"),
    "hin_vakya_rearrange": ("representation", "rearrange_letters"),
    "hin_vakya_error": ("error_detection", "error_spot_hindi"),
    "hin_vakya_thinking": ("thinking", "creative_writing_hindi"),
    # Kahani Lekhan (Class 3)
    "hin_kahani_identify": ("recognition", "pick_correct_hindi"),
    "hin_kahani_answer": ("application", "word_problem_hindi"),
    "hin_kahani_complete": ("representation", "complete_sentence_hindi"),
    "hin_kahani_error": ("error_detection", "error_spot_hindi"),
    "hin_kahani_thinking": ("thinking", "creative_writing_hindi"),
    # ── Computer Science skill tags ──────────────────────────
    # Parts of Computer (Class 1)
    "comp_c1_parts_identify": ("recognition", "pick_correct_science"),
    "comp_c1_parts_apply": ("application", "explain_why_science"),
    "comp_c1_parts_represent": ("representation", "fill_diagram"),
    "comp_c1_parts_error": ("error_detection", "error_spot_science"),
    "comp_c1_parts_thinking": ("thinking", "thinking_science"),
    # Using Mouse and Keyboard (Class 1)
    "comp_c1_mouse_identify": ("recognition", "true_false"),
    "comp_c1_mouse_apply": ("application", "give_example"),
    "comp_c1_mouse_represent": ("representation", "sequence_steps"),
    "comp_c1_mouse_error": ("error_detection", "error_spot_science"),
    "comp_c1_mouse_thinking": ("thinking", "thinking_science"),
    # Desktop and Icons (Class 2)
    "comp_c2_desktop_identify": ("recognition", "pick_correct_science"),
    "comp_c2_desktop_apply": ("application", "explain_why_science"),
    "comp_c2_desktop_represent": ("representation", "fill_diagram"),
    "comp_c2_desktop_error": ("error_detection", "error_spot_science"),
    "comp_c2_desktop_thinking": ("thinking", "thinking_science"),
    # Basic Typing (Class 2)
    "comp_c2_typing_identify": ("recognition", "true_false"),
    "comp_c2_typing_apply": ("application", "give_example"),
    "comp_c2_typing_represent": ("representation", "sequence_steps"),
    "comp_c2_typing_error": ("error_detection", "error_spot_science"),
    "comp_c2_typing_thinking": ("thinking", "thinking_science"),
    # Special Keys (Class 2)
    "comp_c2_special_identify": ("recognition", "pick_correct_science"),
    "comp_c2_special_apply": ("application", "explain_why_science"),
    "comp_c2_special_represent": ("representation", "fill_diagram"),
    "comp_c2_special_error": ("error_detection", "error_spot_science"),
    "comp_c2_special_thinking": ("thinking", "thinking_science"),
    # MS Paint Basics (Class 3)
    "comp_c3_paint_identify": ("recognition", "pick_correct_science"),
    "comp_c3_paint_apply": ("application", "give_example"),
    "comp_c3_paint_represent": ("representation", "sequence_steps"),
    "comp_c3_paint_error": ("error_detection", "error_spot_science"),
    "comp_c3_paint_thinking": ("thinking", "thinking_science"),
    # Keyboard Shortcuts (Class 3)
    "comp_c3_shortcuts_identify": ("recognition", "pick_correct_science"),
    "comp_c3_shortcuts_apply": ("application", "explain_why_science"),
    "comp_c3_shortcuts_represent": ("representation", "fill_diagram"),
    "comp_c3_shortcuts_error": ("error_detection", "error_spot_science"),
    "comp_c3_shortcuts_thinking": ("thinking", "thinking_science"),
    # Files and Folders (Class 3)
    "comp_c3_files_identify": ("recognition", "true_false"),
    "comp_c3_files_apply": ("application", "give_example"),
    "comp_c3_files_represent": ("representation", "sequence_steps"),
    "comp_c3_files_error": ("error_detection", "error_spot_science"),
    "comp_c3_files_thinking": ("thinking", "thinking_science"),
    # MS Word Basics (Class 4)
    "comp_c4_word_identify": ("recognition", "pick_correct_science"),
    "comp_c4_word_apply": ("application", "explain_why_science"),
    "comp_c4_word_represent": ("representation", "sequence_steps"),
    "comp_c4_word_error": ("error_detection", "error_spot_science"),
    "comp_c4_word_thinking": ("thinking", "thinking_science"),
    # Introduction to Scratch (Class 4)
    "comp_c4_scratch_identify": ("recognition", "pick_correct_science"),
    "comp_c4_scratch_apply": ("application", "give_example"),
    "comp_c4_scratch_represent": ("representation", "sequence_steps"),
    "comp_c4_scratch_error": ("error_detection", "error_spot_science"),
    "comp_c4_scratch_thinking": ("thinking", "thinking_science"),
    # Internet Safety (Class 4)
    "comp_c4_safety_identify": ("recognition", "true_false"),
    "comp_c4_safety_apply": ("application", "explain_why_science"),
    "comp_c4_safety_represent": ("representation", "sequence_steps"),
    "comp_c4_safety_error": ("error_detection", "error_spot_science"),
    "comp_c4_safety_thinking": ("thinking", "thinking_science"),
    # Scratch Programming (Class 5)
    "comp_c5_scratch_identify": ("recognition", "pick_correct_science"),
    "comp_c5_scratch_apply": ("application", "explain_why_science"),
    "comp_c5_scratch_represent": ("representation", "sequence_steps"),
    "comp_c5_scratch_error": ("error_detection", "error_spot_science"),
    "comp_c5_scratch_thinking": ("thinking", "thinking_science"),
    # Internet Basics (Class 5)
    "comp_c5_internet_identify": ("recognition", "pick_correct_science"),
    "comp_c5_internet_apply": ("application", "give_example"),
    "comp_c5_internet_represent": ("representation", "sequence_steps"),
    "comp_c5_internet_error": ("error_detection", "error_spot_science"),
    "comp_c5_internet_thinking": ("thinking", "thinking_science"),
    # MS PowerPoint Basics (Class 5)
    "comp_c5_ppt_identify": ("recognition", "pick_correct_science"),
    "comp_c5_ppt_apply": ("application", "explain_why_science"),
    "comp_c5_ppt_represent": ("representation", "sequence_steps"),
    "comp_c5_ppt_error": ("error_detection", "error_spot_science"),
    "comp_c5_ppt_thinking": ("thinking", "thinking_science"),
    # Digital Citizenship (Class 5)
    "comp_c5_digital_identify": ("recognition", "true_false"),
    "comp_c5_digital_apply": ("application", "explain_why_science"),
    "comp_c5_digital_represent": ("representation", "sequence_steps"),
    "comp_c5_digital_error": ("error_detection", "error_spot_science"),
    "comp_c5_digital_thinking": ("thinking", "thinking_science"),
    # ── General Knowledge skill tags ──────────────────────────
    # Famous Landmarks (Class 3)
    "gk_c3_landmarks_identify": ("recognition", "pick_correct_science"),
    "gk_c3_landmarks_apply": ("application", "explain_why_science"),
    "gk_c3_landmarks_represent": ("representation", "sequence_steps"),
    "gk_c3_landmarks_error": ("error_detection", "error_spot_science"),
    "gk_c3_landmarks_thinking": ("thinking", "thinking_science"),
    # National Symbols (Class 3)
    "gk_c3_symbols_identify": ("recognition", "pick_correct_science"),
    "gk_c3_symbols_apply": ("application", "give_example"),
    "gk_c3_symbols_represent": ("representation", "fill_diagram"),
    "gk_c3_symbols_error": ("error_detection", "error_spot_science"),
    "gk_c3_symbols_thinking": ("thinking", "thinking_science"),
    # Solar System Basics (Class 3)
    "gk_c3_solar_identify": ("recognition", "pick_correct_science"),
    "gk_c3_solar_apply": ("application", "explain_why_science"),
    "gk_c3_solar_represent": ("representation", "sequence_steps"),
    "gk_c3_solar_error": ("error_detection", "error_spot_science"),
    "gk_c3_solar_thinking": ("thinking", "thinking_science"),
    # Current Awareness (Class 3)
    "gk_c3_current_identify": ("recognition", "true_false"),
    "gk_c3_current_apply": ("application", "give_example"),
    "gk_c3_current_represent": ("representation", "fill_diagram"),
    "gk_c3_current_error": ("error_detection", "error_spot_science"),
    "gk_c3_current_thinking": ("thinking", "thinking_science"),
    # Continents and Oceans (Class 4)
    "gk_c4_continents_identify": ("recognition", "pick_correct_science"),
    "gk_c4_continents_apply": ("application", "explain_why_science"),
    "gk_c4_continents_represent": ("representation", "fill_diagram"),
    "gk_c4_continents_error": ("error_detection", "error_spot_science"),
    "gk_c4_continents_thinking": ("thinking", "thinking_science"),
    # Famous Scientists (Class 4)
    "gk_c4_scientists_identify": ("recognition", "pick_correct_science"),
    "gk_c4_scientists_apply": ("application", "give_example"),
    "gk_c4_scientists_represent": ("representation", "cause_effect"),
    "gk_c4_scientists_error": ("error_detection", "error_spot_science"),
    "gk_c4_scientists_thinking": ("thinking", "thinking_science"),
    # Festivals of India (Class 4)
    "gk_c4_festivals_identify": ("recognition", "true_false"),
    "gk_c4_festivals_apply": ("application", "give_example"),
    "gk_c4_festivals_represent": ("representation", "fill_diagram"),
    "gk_c4_festivals_error": ("error_detection", "error_spot_science"),
    "gk_c4_festivals_thinking": ("thinking", "thinking_science"),
    # Sports and Games (Class 4)
    "gk_c4_sports_identify": ("recognition", "pick_correct_science"),
    "gk_c4_sports_apply": ("application", "explain_why_science"),
    "gk_c4_sports_represent": ("representation", "cause_effect"),
    "gk_c4_sports_error": ("error_detection", "error_spot_science"),
    "gk_c4_sports_thinking": ("thinking", "thinking_science"),
    # Indian Constitution (Class 5)
    "gk_c5_constitution_identify": ("recognition", "true_false"),
    "gk_c5_constitution_apply": ("application", "explain_why_science"),
    "gk_c5_constitution_represent": ("representation", "cause_effect"),
    "gk_c5_constitution_error": ("error_detection", "error_spot_science"),
    "gk_c5_constitution_thinking": ("thinking", "thinking_science"),
    # World Heritage Sites (Class 5)
    "gk_c5_heritage_identify": ("recognition", "pick_correct_science"),
    "gk_c5_heritage_apply": ("application", "give_example"),
    "gk_c5_heritage_represent": ("representation", "fill_diagram"),
    "gk_c5_heritage_error": ("error_detection", "error_spot_science"),
    "gk_c5_heritage_thinking": ("thinking", "thinking_science"),
    # Space Missions (Class 5)
    "gk_c5_space_identify": ("recognition", "pick_correct_science"),
    "gk_c5_space_apply": ("application", "explain_why_science"),
    "gk_c5_space_represent": ("representation", "sequence_steps"),
    "gk_c5_space_error": ("error_detection", "error_spot_science"),
    "gk_c5_space_thinking": ("thinking", "thinking_science"),
    # Environmental Awareness (Class 5)
    "gk_c5_environment_identify": ("recognition", "true_false"),
    "gk_c5_environment_apply": ("application", "explain_why_science"),
    "gk_c5_environment_represent": ("representation", "cause_effect"),
    "gk_c5_environment_error": ("error_detection", "error_spot_science"),
    "gk_c5_environment_thinking": ("thinking", "thinking_science"),
    # ── Moral Science skill tags ──────────────────────────
    # Sharing (Class 1)
    "moral_c1_sharing_identify": ("recognition", "pick_correct_science"),
    "moral_c1_sharing_apply": ("application", "give_example"),
    "moral_c1_sharing_represent": ("representation", "sequence_steps"),
    "moral_c1_sharing_error": ("error_detection", "error_spot_science"),
    "moral_c1_sharing_thinking": ("thinking", "thinking_science"),
    # Honesty (Class 1)
    "moral_c1_honesty_identify": ("recognition", "true_false"),
    "moral_c1_honesty_apply": ("application", "give_example"),
    "moral_c1_honesty_represent": ("representation", "sequence_steps"),
    "moral_c1_honesty_error": ("error_detection", "error_spot_science"),
    "moral_c1_honesty_thinking": ("thinking", "thinking_science"),
    # Kindness (Class 2)
    "moral_c2_kindness_identify": ("recognition", "pick_correct_science"),
    "moral_c2_kindness_apply": ("application", "give_example"),
    "moral_c2_kindness_represent": ("representation", "sequence_steps"),
    "moral_c2_kindness_error": ("error_detection", "error_spot_science"),
    "moral_c2_kindness_thinking": ("thinking", "thinking_science"),
    # Respecting Elders (Class 2)
    "moral_c2_respect_identify": ("recognition", "true_false"),
    "moral_c2_respect_apply": ("application", "give_example"),
    "moral_c2_respect_represent": ("representation", "sequence_steps"),
    "moral_c2_respect_error": ("error_detection", "error_spot_science"),
    "moral_c2_respect_thinking": ("thinking", "thinking_science"),
    # Teamwork (Class 3)
    "moral_c3_teamwork_identify": ("recognition", "pick_correct_science"),
    "moral_c3_teamwork_apply": ("application", "explain_why_science"),
    "moral_c3_teamwork_represent": ("representation", "sequence_steps"),
    "moral_c3_teamwork_error": ("error_detection", "error_spot_science"),
    "moral_c3_teamwork_thinking": ("thinking", "thinking_science"),
    # Empathy (Class 3)
    "moral_c3_empathy_identify": ("recognition", "true_false"),
    "moral_c3_empathy_apply": ("application", "give_example"),
    "moral_c3_empathy_represent": ("representation", "cause_effect"),
    "moral_c3_empathy_error": ("error_detection", "error_spot_science"),
    "moral_c3_empathy_thinking": ("thinking", "thinking_science"),
    # Environmental Care (Class 3)
    "moral_c3_envcare_identify": ("recognition", "pick_correct_science"),
    "moral_c3_envcare_apply": ("application", "explain_why_science"),
    "moral_c3_envcare_represent": ("representation", "cause_effect"),
    "moral_c3_envcare_error": ("error_detection", "error_spot_science"),
    "moral_c3_envcare_thinking": ("thinking", "thinking_science"),
    # Leadership (Class 4)
    "moral_c4_leadership_identify": ("recognition", "pick_correct_science"),
    "moral_c4_leadership_apply": ("application", "explain_why_science"),
    "moral_c4_leadership_represent": ("representation", "sequence_steps"),
    "moral_c4_leadership_error": ("error_detection", "error_spot_science"),
    "moral_c4_leadership_thinking": ("thinking", "thinking_science"),
    # Global Citizenship (Class 5)
    "moral_c5_global_identify": ("recognition", "true_false"),
    "moral_c5_global_apply": ("application", "explain_why_science"),
    "moral_c5_global_represent": ("representation", "cause_effect"),
    "moral_c5_global_error": ("error_detection", "error_spot_science"),
    "moral_c5_global_thinking": ("thinking", "thinking_science"),
    # Digital Ethics (Class 5)
    "moral_c5_digital_identify": ("recognition", "true_false"),
    "moral_c5_digital_apply": ("application", "explain_why_science"),
    "moral_c5_digital_represent": ("representation", "sequence_steps"),
    "moral_c5_digital_error": ("error_detection", "error_spot_science"),
    "moral_c5_digital_thinking": ("thinking", "thinking_science"),
    # ── Health & Physical Education skill tags ──────────────────────────
    # Personal Hygiene (Class 1)
    "health_c1_hygiene_identify": ("recognition", "pick_correct_science"),
    "health_c1_hygiene_apply": ("application", "explain_why_science"),
    "health_c1_hygiene_represent": ("representation", "sequence_steps"),
    "health_c1_hygiene_error": ("error_detection", "error_spot_science"),
    "health_c1_hygiene_thinking": ("thinking", "thinking_science"),
    # Good Posture (Class 1)
    "health_c1_posture_identify": ("recognition", "true_false"),
    "health_c1_posture_apply": ("application", "give_example"),
    "health_c1_posture_represent": ("representation", "sequence_steps"),
    "health_c1_posture_error": ("error_detection", "error_spot_science"),
    "health_c1_posture_thinking": ("thinking", "thinking_science"),
    # Basic Physical Activities (Class 1)
    "health_c1_physical_identify": ("recognition", "pick_correct_science"),
    "health_c1_physical_apply": ("application", "give_example"),
    "health_c1_physical_represent": ("representation", "sequence_steps"),
    "health_c1_physical_error": ("error_detection", "error_spot_science"),
    "health_c1_physical_thinking": ("thinking", "thinking_science"),
    # Healthy Eating Habits (Class 2)
    "health_c2_eating_identify": ("recognition", "pick_correct_science"),
    "health_c2_eating_apply": ("application", "explain_why_science"),
    "health_c2_eating_represent": ("representation", "sequence_steps"),
    "health_c2_eating_error": ("error_detection", "error_spot_science"),
    "health_c2_eating_thinking": ("thinking", "thinking_science"),
    # Outdoor Play (Class 2)
    "health_c2_outdoor_identify": ("recognition", "true_false"),
    "health_c2_outdoor_apply": ("application", "give_example"),
    "health_c2_outdoor_represent": ("representation", "sequence_steps"),
    "health_c2_outdoor_error": ("error_detection", "error_spot_science"),
    "health_c2_outdoor_thinking": ("thinking", "thinking_science"),
    # Basic Stretching (Class 2)
    "health_c2_stretching_identify": ("recognition", "pick_correct_science"),
    "health_c2_stretching_apply": ("application", "give_example"),
    "health_c2_stretching_represent": ("representation", "sequence_steps"),
    "health_c2_stretching_error": ("error_detection", "error_spot_science"),
    "health_c2_stretching_thinking": ("thinking", "thinking_science"),
    # Balanced Diet (Class 3)
    "health_c3_diet_identify": ("recognition", "pick_correct_science"),
    "health_c3_diet_apply": ("application", "explain_why_science"),
    "health_c3_diet_represent": ("representation", "cause_effect"),
    "health_c3_diet_error": ("error_detection", "error_spot_science"),
    "health_c3_diet_thinking": ("thinking", "thinking_science"),
    # Team Sports Rules (Class 3)
    "health_c3_sports_identify": ("recognition", "true_false"),
    "health_c3_sports_apply": ("application", "explain_why_science"),
    "health_c3_sports_represent": ("representation", "sequence_steps"),
    "health_c3_sports_error": ("error_detection", "error_spot_science"),
    "health_c3_sports_thinking": ("thinking", "thinking_science"),
    # Safety at Play (Class 3)
    "health_c3_safety_identify": ("recognition", "pick_correct_science"),
    "health_c3_safety_apply": ("application", "explain_why_science"),
    "health_c3_safety_represent": ("representation", "sequence_steps"),
    "health_c3_safety_error": ("error_detection", "error_spot_science"),
    "health_c3_safety_thinking": ("thinking", "thinking_science"),
    # First Aid Basics (Class 4)
    "health_c4_firstaid_identify": ("recognition", "pick_correct_science"),
    "health_c4_firstaid_apply": ("application", "explain_why_science"),
    "health_c4_firstaid_represent": ("representation", "sequence_steps"),
    "health_c4_firstaid_error": ("error_detection", "error_spot_science"),
    "health_c4_firstaid_thinking": ("thinking", "thinking_science"),
    # Yoga Introduction (Class 4)
    "health_c4_yoga_identify": ("recognition", "true_false"),
    "health_c4_yoga_apply": ("application", "give_example"),
    "health_c4_yoga_represent": ("representation", "sequence_steps"),
    "health_c4_yoga_error": ("error_detection", "error_spot_science"),
    "health_c4_yoga_thinking": ("thinking", "thinking_science"),
    # Importance of Sleep (Class 4)
    "health_c4_sleep_identify": ("recognition", "true_false"),
    "health_c4_sleep_apply": ("application", "explain_why_science"),
    "health_c4_sleep_represent": ("representation", "cause_effect"),
    "health_c4_sleep_error": ("error_detection", "error_spot_science"),
    "health_c4_sleep_thinking": ("thinking", "thinking_science"),
    # Fitness and Stamina (Class 5)
    "health_c5_fitness_identify": ("recognition", "pick_correct_science"),
    "health_c5_fitness_apply": ("application", "explain_why_science"),
    "health_c5_fitness_represent": ("representation", "sequence_steps"),
    "health_c5_fitness_error": ("error_detection", "error_spot_science"),
    "health_c5_fitness_thinking": ("thinking", "thinking_science"),
    # Nutrition Labels Reading (Class 5)
    "health_c5_nutrition_identify": ("recognition", "true_false"),
    "health_c5_nutrition_apply": ("application", "explain_why_science"),
    "health_c5_nutrition_represent": ("representation", "cause_effect"),
    "health_c5_nutrition_error": ("error_detection", "error_spot_science"),
    "health_c5_nutrition_thinking": ("thinking", "thinking_science"),
    # Mental Health Awareness (Class 5)
    "health_c5_mental_identify": ("recognition", "pick_correct_science"),
    "health_c5_mental_apply": ("application", "explain_why_science"),
    "health_c5_mental_represent": ("representation", "cause_effect"),
    "health_c5_mental_error": ("error_detection", "error_spot_science"),
    "health_c5_mental_thinking": ("thinking", "thinking_science"),
}

SLOT_INSTRUCTIONS: dict[str, str] = {
    "clock_question": "Generate a question about reading clocks.",
    "calendar_question": "Generate a question about calendar/dates.",
}

# Default mix recipe for 3-digit addition/subtraction (base 20, scaled for other counts)
DEFAULT_MIX_RECIPE_20: list[dict] = [
    {"skill_tag": "column_setup", "count": 6},
    {"skill_tag": "word_problem", "count": 4, "unique_contexts": True},
    {"skill_tag": "missing_number", "count": 4},
    {"skill_tag": "error_spot", "count": 3, "require_student_answer": True},
    {"skill_tag": "thinking", "count": 3},
]

# ── Learning Objectives (Gold-G5) ──────────────────────────
# Deterministic, no LLM call. Hardcoded per topic.
# Rendered as header box on worksheet and PDF.

LEARNING_OBJECTIVES: dict[str, list[str]] = {
    # ── Class 3 topics ──
    "Addition (carries)": [
        "Add 3-digit numbers where carrying is needed",
        "Spot common addition mistakes and fix them",
        "Solve real-life addition word problems",
    ],
    "Subtraction (borrowing)": [
        "Subtract 3-digit numbers where borrowing is needed",
        "Identify and correct common subtraction errors",
        "Solve real-life subtraction word problems",
    ],
    "Addition and subtraction (3-digit)": [
        "Add and subtract 3-digit numbers fluently",
        "Choose the correct operation for a word problem",
        "Spot errors in both addition and subtraction",
    ],
    "Multiplication (tables 2-10)": [
        "Recall multiplication facts for tables 2 to 10",
        "Solve multiplication word problems",
        "Spot and fix errors in multiplication calculations",
    ],
    "Division basics": [
        "Divide numbers using equal sharing and grouping",
        "Solve simple division word problems",
        "Understand the relationship between multiplication and division",
    ],
    "Numbers up to 10000": [
        "Read, write, and compare numbers up to 10,000",
        "Identify place value of digits in 4-digit numbers",
        "Arrange numbers in ascending and descending order",
    ],
    "Fractions (halves, quarters)": [
        "Identify halves and quarters of shapes and quantities",
        "Compare simple fractions using visual models",
        "Solve problems involving halves and quarters",
    ],
    "Fractions": [
        "Read and write fractions with different denominators",
        "Compare and order simple fractions",
        "Solve word problems involving fractions",
    ],
    "Time (reading clock, calendar)": [
        "Read time on analog and digital clocks",
        "Solve problems involving days, weeks, and months",
        "Calculate simple time durations",
    ],
    "Money (bills and change)": [
        "Add and subtract amounts of money",
        "Make change and calculate totals when shopping",
        "Solve real-life money word problems",
    ],
    "Symmetry": [
        "Identify lines of symmetry in shapes and patterns",
        "Complete symmetric figures on a grid",
        "Recognise symmetry in everyday objects",
    ],
    "Patterns and sequences": [
        "Identify and extend number and shape patterns",
        "Describe the rule behind a pattern",
        "Create growing and repeating patterns",
    ],
    # ── Class 1 topics ──
    "Numbers 1 to 50 (Class 1)": [
        "Count objects and write numbers from 1 to 50",
        "Compare two numbers and say which is greater or smaller",
        "Put numbers in order from smallest to largest",
    ],
    "Numbers 51 to 100 (Class 1)": [
        "Count objects and write numbers from 51 to 100",
        "Compare two numbers up to 100",
        "Find the number that comes before or after a given number",
    ],
    "Addition up to 20 (Class 1)": [
        "Add two small numbers with sums up to 20",
        "Solve simple addition word problems",
        "Find the missing number in an addition sentence",
    ],
    "Subtraction within 20 (Class 1)": [
        "Subtract one small number from another within 20",
        "Solve simple subtraction word problems",
        "Find the missing number in a subtraction sentence",
    ],
    "Basic Shapes (Class 1)": [
        "Identify circles, squares, triangles, and rectangles",
        "Count the sides and corners of basic shapes",
        "Spot shapes in everyday objects around us",
    ],
    "Measurement (Class 1)": [
        "Compare objects by length (longer, shorter)",
        "Compare objects by weight (heavier, lighter)",
        "Use words like taller, shorter, heavier, lighter correctly",
    ],
    "Time (Class 1)": [
        "Name the days of the week in order",
        "Tell the difference between morning, afternoon, and night",
        "Describe daily routines and when they happen",
    ],
    "Money (Class 1)": [
        "Identify Indian coins of 1, 2, and 5 rupees",
        "Count a small group of coins up to 20 rupees",
        "Solve simple problems about buying with coins",
    ],
    # ── Class 2 topics ──
    "Numbers up to 1000 (Class 2)": [
        "Read, write, and compare numbers up to 1,000",
        "Identify place value of hundreds, tens, and ones",
        "Arrange 3-digit numbers in order",
    ],
    "Addition (2-digit with carry)": [
        "Add 2-digit numbers with carrying",
        "Solve addition word problems with small numbers",
        "Spot mistakes in 2-digit addition",
    ],
    "Subtraction (2-digit with borrow)": [
        "Subtract 2-digit numbers with borrowing",
        "Solve subtraction word problems with small numbers",
        "Spot mistakes in 2-digit subtraction",
    ],
    "Multiplication (tables 2-5)": [
        "Recall multiplication facts for tables 2 to 5",
        "Use multiplication to solve simple word problems",
        "Understand multiplication as repeated addition",
    ],
    "Division (sharing equally)": [
        "Share objects equally into groups",
        "Solve simple division problems (no remainders)",
        "Understand division as equal sharing",
    ],
    "Shapes and space (2D)": [
        "Identify and name basic 2D shapes",
        "Describe properties of circles, squares, triangles, and rectangles",
        "Spot shapes in everyday objects",
    ],
    "Measurement (length, weight)": [
        "Measure lengths in centimetres and metres",
        "Compare and order objects by weight",
        "Solve simple measurement word problems",
    ],
    "Time (hour, half-hour)": [
        "Tell time to the hour and half-hour",
        "Read o'clock and half-past on a clock face",
        "Solve simple problems about daily routines and time",
    ],
    "Money (coins and notes)": [
        "Identify Indian coins and notes up to Rs 100",
        "Add small amounts of money",
        "Solve simple shopping word problems",
    ],
    "Data handling (pictographs)": [
        "Read and interpret simple pictographs",
        "Answer questions based on pictograph data",
        "Collect and organise data into a pictograph",
    ],
    # ── Class 4 topics ──
    "Large numbers (up to 1,00,000)": [
        "Read, write, and compare numbers up to 1,00,000",
        "Use the Indian place value system for 5-digit numbers",
        "Expand and compose large numbers",
    ],
    "Addition and subtraction (5-digit)": [
        "Add and subtract 5-digit numbers fluently",
        "Solve multi-step word problems with large numbers",
        "Estimate sums and differences of large numbers",
    ],
    "Multiplication (3-digit × 2-digit)": [
        "Multiply a 3-digit number by a 2-digit number",
        "Solve multiplication word problems with larger numbers",
        "Estimate products using rounding",
    ],
    "Division (long division)": [
        "Divide 3-digit numbers by 1-digit numbers using long division",
        "Interpret remainders in word problems",
        "Check division answers using multiplication",
    ],
    "Fractions (equivalent, comparison)": [
        "Find equivalent fractions",
        "Compare and order fractions with different denominators",
        "Solve word problems involving fractions",
    ],
    "Decimals (tenths, hundredths)": [
        "Read and write decimals to the hundredths place",
        "Convert between fractions and decimals",
        "Compare and order decimal numbers",
    ],
    "Geometry (angles, lines)": [
        "Identify and classify angles as acute, right, or obtuse",
        "Recognise parallel and perpendicular lines",
        "Measure angles using simple tools",
    ],
    "Perimeter and area": [
        "Calculate the perimeter of rectangles and squares",
        "Calculate the area of rectangles and squares",
        "Solve real-life problems involving perimeter and area",
    ],
    "Time (minutes, 24-hour clock)": [
        "Tell time to the nearest minute",
        "Convert between 12-hour and 24-hour clock formats",
        "Calculate durations across hours",
    ],
    "Money (bills, profit/loss)": [
        "Calculate total cost, change, and bills",
        "Understand simple profit and loss",
        "Solve multi-step money word problems",
    ],
    # ── Class 5 topics ──
    "Numbers up to 10 lakh (Class 5)": [
        "Read, write, and compare numbers up to 10,00,000",
        "Use the Indian place value system for 6- and 7-digit numbers",
        "Expand and compose large numbers using lakhs and ten-thousands",
    ],
    "Factors and multiples (Class 5)": [
        "Find all factors of a given number",
        "Identify multiples and common multiples of numbers",
        "Determine if a number is prime or composite",
    ],
    "HCF and LCM (Class 5)": [
        "Find the Highest Common Factor of two numbers",
        "Find the Least Common Multiple of two numbers",
        "Solve word problems using HCF and LCM",
    ],
    "Fractions (add and subtract) (Class 5)": [
        "Add fractions with like and unlike denominators",
        "Subtract fractions with like and unlike denominators",
        "Solve word problems involving addition and subtraction of fractions",
    ],
    "Decimals (all operations) (Class 5)": [
        "Add and subtract decimals up to two decimal places",
        "Multiply and divide simple decimals",
        "Solve real-life problems involving decimal operations",
    ],
    "Percentage (Class 5)": [
        "Convert fractions and decimals to percentages and vice versa",
        "Find a given percentage of a number",
        "Solve simple percentage word problems",
    ],
    "Area and volume (Class 5)": [
        "Calculate area of triangles and composite shapes",
        "Find volume of cubes and cuboids",
        "Solve real-life problems involving area and volume",
    ],
    "Geometry (circles, symmetry) (Class 5)": [
        "Identify radius, diameter, and circumference of a circle",
        "Identify and draw lines of symmetry in shapes",
        "Understand rotational symmetry at a basic level",
    ],
    "Data handling (pie charts) (Class 5)": [
        "Read and interpret pie charts",
        "Compare data shown in pie charts",
        "Solve problems using data from pie charts and tables",
    ],
    "Speed distance time (Class 5)": [
        "Understand the relationship Speed = Distance / Time",
        "Calculate speed, distance, or time when two are given",
        "Solve word problems involving travel and speed",
    ],
    # ── English Language Learning Objectives ──
    # ── Class 1 English ──
    "Alphabet (Class 1)": [
        "Recognise and name all 26 capital and small letters",
        "Match capital letters to their small letter forms",
        "Write missing letters in alphabetical order",
    ],
    "Phonics (Class 1)": [
        "Identify the beginning sound of simple words",
        "Match letters to their common sounds",
        "Say a word that starts with a given letter sound",
    ],
    "Self and Family Vocabulary (Class 1)": [
        "Name family members using English words (mother, father, sister, brother)",
        "Say and read words for body parts (hand, eye, nose)",
        "Use simple words about myself and my family",
    ],
    "Animals and Food Vocabulary (Class 1)": [
        "Name common animals in English (cat, dog, cow, hen)",
        "Name common fruits and foods (apple, banana, rice, roti)",
        "Match animal or food names to pictures",
    ],
    "Greetings and Polite Words (Class 1)": [
        "Use greetings like Hello, Good morning, Goodbye",
        "Say polite words: Please, Thank you, Sorry",
        "Know when to use each greeting or polite word",
    ],
    "Seasons (Class 1)": [
        "Name the seasons (summer, winter, rainy)",
        "Say what we wear or do in each season",
        "Match season names to simple descriptions",
    ],
    "Simple Sentences (Class 1)": [
        "Read simple 3-4 word sentences",
        "Put words in order to make a sentence",
        "Say a simple sentence about a picture",
    ],
    # ── Class 2 English ──
    "Nouns (Class 2)": [
        "Identify naming words (nouns) in sentences",
        "Use nouns correctly in simple sentences",
        "Tell the difference between names of people, places, and things",
    ],
    "Verbs (Class 2)": [
        "Identify action words (verbs) in sentences",
        "Use action words to complete sentences",
        "Match actions to the correct pictures or descriptions",
    ],
    "Pronouns (Class 2)": [
        "Identify pronouns (he, she, it, they) in sentences",
        "Replace nouns with the correct pronouns",
        "Use pronouns to avoid repeating names",
    ],
    "Sentences (Class 2)": [
        "Form simple sentences with a subject and verb",
        "Begin sentences with a capital letter and end with a full stop",
        "Arrange words in the correct order to make sentences",
    ],
    "Rhyming Words (Class 2)": [
        "Identify words that rhyme (sound the same at the end)",
        "Match rhyming word pairs",
        "Think of new words that rhyme with given words",
    ],
    "Punctuation (Class 2)": [
        "Use full stops and capital letters correctly",
        "Use question marks for asking sentences",
        "Read sentences with correct pauses",
    ],
    "Nouns (Class 3)": [
        "Classify nouns as common, proper, or collective",
        "Change singular nouns to plural and vice versa",
        "Use nouns correctly in different contexts",
    ],
    "Verbs (Class 3)": [
        "Identify main verbs and helping verbs",
        "Use correct verb forms in sentences",
        "Match verbs with their subjects",
    ],
    "Adjectives (Class 3)": [
        "Identify adjectives (describing words) in sentences",
        "Use degrees of comparison (big, bigger, biggest)",
        "Add adjectives to make sentences more descriptive",
    ],
    "Pronouns (Class 3)": [
        "Use personal and possessive pronouns correctly",
        "Replace nouns with pronouns in paragraphs",
        "Identify the noun a pronoun refers to",
    ],
    "Tenses (Class 3)": [
        "Identify simple present, past, and future tenses",
        "Change sentences from one tense to another",
        "Use correct tense forms in context",
    ],
    "Punctuation (Class 3)": [
        "Use commas, apostrophes, and exclamation marks correctly",
        "Add missing punctuation to sentences",
        "Explain why specific punctuation is used",
    ],
    "Vocabulary (Class 3)": [
        "Understand and use new words in context",
        "Find synonyms and antonyms for given words",
        "Choose the correct word meaning from options",
    ],
    "Reading Comprehension (Class 3)": [
        "Read a short passage and answer questions about it",
        "Find specific information in a passage",
        "Understand the main idea of a passage",
    ],
    "Tenses (Class 4)": [
        "Use simple, continuous, and perfect tenses correctly",
        "Convert sentences between different tense forms",
        "Identify tense errors and correct them",
    ],
    "Sentence Types (Class 4)": [
        "Identify declarative, interrogative, exclamatory, and imperative sentences",
        "Convert sentences from one type to another",
        "Use correct punctuation for each sentence type",
    ],
    "Conjunctions (Class 4)": [
        "Join sentences using conjunctions (and, but, or, because)",
        "Choose the correct conjunction for meaning",
        "Write compound sentences using conjunctions",
    ],
    "Prepositions (Class 4)": [
        "Identify prepositions in sentences",
        "Use prepositions of place, time, and direction correctly",
        "Complete sentences with appropriate prepositions",
    ],
    "Adverbs (Class 4)": [
        "Identify adverbs of manner, time, place, and frequency",
        "Use adverbs to add detail to sentences",
        "Form adverbs from adjectives (-ly)",
    ],
    "Prefixes and Suffixes (Class 4)": [
        "Add prefixes (un-, re-, dis-, pre-) to change word meaning",
        "Add suffixes (-ful, -less, -ness, -ly) to form new words",
        "Identify root words in words with prefixes/suffixes",
    ],
    "Vocabulary (Class 4)": [
        "Use context clues to guess word meanings",
        "Identify homophones and use them correctly",
        "Understand and use common idioms",
    ],
    "Reading Comprehension (Class 4)": [
        "Read passages and answer inferential questions",
        "Identify main ideas and supporting details",
        "Make predictions based on text clues",
    ],
    # ── Class 5 English Learning Objectives ──
    "Active and Passive Voice (Class 5)": [
        "Identify active and passive voice in sentences",
        "Convert sentences between active and passive voice",
        "Understand when passive voice is appropriate",
    ],
    "Direct and Indirect Speech (Class 5)": [
        "Identify direct and indirect speech in sentences",
        "Convert direct speech to indirect speech and vice versa",
        "Use correct punctuation for reported speech",
    ],
    "Complex Sentences (Class 5)": [
        "Identify main and subordinate clauses in complex sentences",
        "Join simple sentences using subordinating conjunctions",
        "Write complex sentences with correct punctuation",
    ],
    "Summary Writing (Class 5)": [
        "Identify the main idea and key points in a passage",
        "Write a concise summary in own words",
        "Distinguish between important and unimportant details",
    ],
    "Comprehension (Class 5)": [
        "Read passages and answer inferential and evaluative questions",
        "Identify themes, tone, and author's purpose",
        "Make inferences and draw conclusions from text",
    ],
    "Synonyms and Antonyms (Class 5)": [
        "Identify synonyms and antonyms of given words",
        "Use synonyms and antonyms correctly in sentences",
        "Choose the best synonym or antonym from context",
    ],
    "Formal Letter Writing (Class 5)": [
        "Understand the format of a formal letter",
        "Write formal letters with correct salutation, body, and closing",
        "Use polite and formal language appropriately",
    ],
    "Creative Writing (Class 5)": [
        "Write descriptive paragraphs using vivid language",
        "Develop a story with a clear beginning, middle, and end",
        "Use figurative language and varied sentence structures",
    ],
    "Clauses (Class 5)": [
        "Identify main (independent) and subordinate (dependent) clauses",
        "Distinguish between noun, adjective, and adverb clauses",
        "Combine clauses to form complex sentences",
    ],
    # ── Science Class 3 Learning Objectives ──
    "Plants (Class 3)": [
        "Identify parts of a plant and their functions",
        "Understand how plants make food and grow",
        "Classify plants based on their features",
    ],
    "Animals (Class 3)": [
        "Classify animals by habitat, food, and body covering",
        "Understand how animals move and protect themselves",
        "Compare features of different animal groups",
    ],
    "Food and Nutrition (Class 3)": [
        "Identify different food groups and their sources",
        "Understand why a balanced diet is important",
        "Classify foods as energy-giving, body-building, or protective",
    ],
    "Shelter (Class 3)": [
        "Understand why living things need shelter",
        "Compare different types of animal and human shelters",
        "Relate shelter types to climate and materials available",
    ],
    "Water (Class 3)": [
        "Identify sources and uses of water",
        "Understand the water cycle in simple terms",
        "Explain why saving water is important",
    ],
    "Air (Class 3)": [
        "Understand that air is everywhere and has weight",
        "Identify what air is made of and why it matters",
        "Explain how air pollution affects living things",
    ],
    "Our Body (Class 3)": [
        "Identify major body parts and their functions",
        "Understand the importance of hygiene and exercise",
        "Explain how different organs help us stay healthy",
    ],
    # ── EVS Class 1 Learning Objectives ──
    "My Family (Class 1)": [
        "Name and identify family members (mother, father, siblings, grandparents)",
        "Understand that families care for and help each other",
        "Describe simple activities done with family",
    ],
    "My Body (Class 1)": [
        "Name and point to major body parts (head, hands, legs, eyes, ears, nose)",
        "Understand that each body part helps us do different things",
        "Learn simple hygiene habits (washing hands, brushing teeth)",
    ],
    "Plants Around Us (Class 1)": [
        "Identify common plants and trees seen around us",
        "Know that plants need water and sunlight to grow",
        "Name simple parts of a plant (leaf, flower, stem)",
    ],
    "Animals Around Us (Class 1)": [
        "Name common animals seen at home and around us",
        "Tell where different animals live (land, water, air)",
        "Know what different animals eat",
    ],
    "Food We Eat (Class 1)": [
        "Name common foods we eat every day",
        "Know that food comes from plants and animals",
        "Understand that we need food to stay healthy and strong",
    ],
    "Seasons and Weather (Class 1)": [
        "Name the main seasons (summer, rainy, winter)",
        "Describe weather using simple words (hot, cold, rainy, windy)",
        "Know what clothes we wear in different seasons",
    ],
    # ── EVS Class 2 Learning Objectives ──
    "Plants (Class 2)": [
        "Identify parts of a plant and what each part does",
        "Know that plants give us food, shade, and fresh air",
        "Understand how a seed grows into a plant",
    ],
    "Animals and Habitats (Class 2)": [
        "Classify animals as pet, farm, or wild animals",
        "Match animals to where they live (habitat)",
        "Describe how animals move and what they eat",
    ],
    "Food and Nutrition (Class 2)": [
        "Sort foods into groups (fruits, vegetables, grains, dairy)",
        "Understand why eating different foods keeps us healthy",
        "Know where common foods come from (plant or animal)",
    ],
    "Water (Class 2)": [
        "Name sources of water (rain, river, well, tap)",
        "List different uses of water in daily life",
        "Understand why we should not waste water",
    ],
    "Shelter (Class 2)": [
        "Know that all living things need a home or shelter",
        "Name different types of houses people live in",
        "Match animals to their homes (nest, burrow, den)",
    ],
    "Our Senses (Class 2)": [
        "Name the five sense organs and what each does",
        "Match senses to the correct body part (eyes see, ears hear)",
        "Understand how senses help us learn about the world",
    ],
    # ── Science Class 4 Learning Objectives ──
    "Living Things (Class 4)": [
        "Classify objects as living or non-living and explain why",
        "Identify basic features of plant and animal cells",
        "Compare characteristics of plants and animals",
    ],
    "Human Body (Class 4)": [
        "Describe the main parts of the digestive system and their roles",
        "Identify major bones and joints of the skeletal system",
        "Explain how the digestive and skeletal systems work together",
    ],
    "States of Matter (Class 4)": [
        "Identify the three states of matter and their properties",
        "Explain how matter changes from one state to another",
        "Relate changes of state to everyday situations",
    ],
    "Force and Motion (Class 4)": [
        "Understand that a push or pull is a force that causes motion",
        "Describe how friction affects the movement of objects",
        "Explain the role of gravity in keeping things on the ground",
    ],
    "Simple Machines (Class 4)": [
        "Identify the six types of simple machines and their uses",
        "Explain how simple machines make work easier",
        "Give real-life examples of levers, pulleys, and inclined planes",
    ],
    "Photosynthesis (Class 4)": [
        "Explain what plants need to make their own food",
        "Describe the process of photosynthesis in simple terms",
        "Understand the role of sunlight, water, and carbon dioxide in photosynthesis",
    ],
    "Animal Adaptation (Class 4)": [
        "Explain how animals adapt to survive in their habitats",
        "Compare adaptations of desert, aquatic, and polar animals",
        "Identify body features that help animals find food and stay safe",
    ],
    # ── Science Class 5 Learning Objectives ──
    "Circulatory System (Class 5)": [
        "Identify the main parts of the circulatory system (heart, blood vessels, blood)",
        "Describe how blood flows through the body",
        "Explain why the circulatory system is important for health",
    ],
    "Respiratory and Nervous System (Class 5)": [
        "Describe how the lungs help us breathe",
        "Explain the role of the brain and nerves in controlling the body",
        "Understand how the respiratory and nervous systems work together",
    ],
    "Reproduction in Plants and Animals (Class 5)": [
        "Describe how plants reproduce through pollination and seeds",
        "Compare egg-laying and live-birth reproduction in animals",
        "Identify parts of a flower involved in reproduction",
    ],
    "Physical and Chemical Changes (Class 5)": [
        "Distinguish between physical and chemical changes",
        "Identify reversible and irreversible changes with examples",
        "Explain what happens during common chemical changes like rusting",
    ],
    "Forms of Energy (Class 5)": [
        "Name different forms of energy (heat, light, sound, electrical)",
        "Explain how energy changes from one form to another",
        "Give examples of energy use in daily life",
    ],
    "Solar System and Earth (Class 5)": [
        "Name the planets in our solar system in order",
        "Explain why we have day and night (rotation) and seasons (revolution)",
        "Describe the role of the sun in our solar system",
    ],
    "Ecosystem and Food Chains (Class 5)": [
        "Identify producers, consumers, and decomposers in an ecosystem",
        "Draw and explain a simple food chain",
        "Understand how living things depend on each other in a food web",
    ],
    # ── Hindi Class 3 topics ──
    "Varnamala (Class 3)": [
        "Identify and write Hindi vowels (swar) and consonants (vyanjan)",
        "Match letters to their sounds and use them in words",
        "Spot and correct mistakes in Hindi letter writing",
    ],
    "Matras (Class 3)": [
        "Identify different matras (vowel signs) and their sounds",
        "Use matras correctly to form Hindi words",
        "Read and write words with aa, ee, oo, and other matras",
    ],
    "Shabd Rachna (Class 3)": [
        "Form new words using prefixes and suffixes in Hindi",
        "Break compound words into their parts",
        "Build words from given letters and syllables",
    ],
    "Vakya Rachna (Class 3)": [
        "Write simple Hindi sentences with correct word order",
        "Use punctuation marks correctly in Hindi sentences",
        "Identify and correct errors in Hindi sentences",
    ],
    "Kahani Lekhan (Class 3)": [
        "Read and understand short Hindi stories and passages",
        "Answer comprehension questions about a Hindi passage",
        "Write a short paragraph or story in Hindi",
    ],
    # ── Computer Science Class 1 (2 topics) ──
    "Parts of Computer (Class 1)": [
        "Identify the main parts of a computer: monitor, keyboard, mouse, CPU, speaker",
        "Describe the function of each computer part",
        "Explain how computer parts work together",
    ],
    "Using Mouse and Keyboard (Class 1)": [
        "Demonstrate basic mouse actions: left click, right click, drag",
        "Identify the keys on a keyboard and practise typing letters",
        "Follow step-by-step instructions to use the mouse and keyboard",
    ],
    # ── Computer Science Class 2 (3 topics) ──
    "Desktop and Icons (Class 2)": [
        "Identify parts of the desktop: icons, taskbar, start menu, wallpaper",
        "Open and close applications using desktop icons",
        "Navigate the start menu to find programs",
    ],
    "Basic Typing (Class 2)": [
        "Place fingers correctly on the home row keys",
        "Type simple words and sentences using proper posture",
        "Identify and use special keys: Space, Enter, Backspace",
    ],
    "Special Keys (Class 2)": [
        "Identify special keys: Enter, Space, Backspace, Shift, Caps Lock, Tab",
        "Explain the function of each special key",
        "Use special keys correctly while typing",
    ],
    # ── Computer Science Class 3 (3 topics) ──
    "MS Paint Basics (Class 3)": [
        "Use drawing tools in MS Paint: pencil, brush, fill, eraser",
        "Draw basic shapes and colour them using the colour palette",
        "Save and open a drawing file in MS Paint",
    ],
    "Keyboard Shortcuts (Class 3)": [
        "Recall common keyboard shortcuts: Ctrl+C, Ctrl+V, Ctrl+Z, Ctrl+S",
        "Use keyboard shortcuts to copy, paste, undo, and save",
        "Explain when and why keyboard shortcuts are useful",
    ],
    "Files and Folders (Class 3)": [
        "Create, rename, and delete files and folders",
        "Organise files into appropriate folders",
        "Navigate folder structures to find saved files",
    ],
    # ── Computer Science Class 4 (3 topics) ──
    "MS Word Basics (Class 4)": [
        "Type and format text in MS Word: bold, italic, underline",
        "Change font size, font style, and text colour",
        "Save, open, and print a document in MS Word",
    ],
    "Introduction to Scratch (Class 4)": [
        "Identify Scratch interface elements: stage, sprites, script area",
        "Create simple animations using motion and looks blocks",
        "Use event blocks to start and control scripts",
    ],
    "Internet Safety (Class 4)": [
        "Create strong passwords and keep them safe",
        "Identify personal information that should not be shared online",
        "Recognise unsafe websites and cyberbullying situations",
    ],
    # ── Computer Science Class 5 (4 topics) ──
    "Scratch Programming (Class 5)": [
        "Use variables, conditionals, and loops in Scratch programs",
        "Create interactive games with broadcasting and events",
        "Debug and improve Scratch projects logically",
    ],
    "Internet Basics (Class 5)": [
        "Navigate a web browser and enter URLs to visit websites",
        "Use search engines to find information safely",
        "Compose and send an email with proper format",
    ],
    "MS PowerPoint Basics (Class 5)": [
        "Create a presentation with text, images, and shapes",
        "Add slide transitions and basic animations",
        "Present a slideshow to an audience effectively",
    ],
    "Digital Citizenship (Class 5)": [
        "Practise online etiquette and respectful communication",
        "Understand the concept of digital footprint and privacy",
        "Recognise copyright rules and responsible use of digital content",
    ],
    # ── General Knowledge ──────────────────────────
    "Famous Landmarks (Class 3)": [
        "Identify famous landmarks of India and the world",
        "Know the location and significance of major monuments",
        "Connect landmarks to the country and culture they represent",
    ],
    "National Symbols (Class 3)": [
        "Identify the national symbols of India",
        "Understand the significance of the flag, emblem, and anthem",
        "Know India's national animal, bird, flower, and fruit",
    ],
    "Solar System Basics (Class 3)": [
        "Name the planets of our solar system in order",
        "Understand basic facts about the Sun, Earth, and Moon",
        "Differentiate between stars, planets, and satellites",
    ],
    "Current Awareness (Class 3)": [
        "Know the major festivals celebrated in India",
        "Identify the seasons and their characteristics",
        "Recall important national and international days",
    ],
    "Continents and Oceans (Class 4)": [
        "Name and locate the 7 continents and 5 oceans",
        "Know major countries on each continent",
        "Understand basic geography of continents and oceans",
    ],
    "Famous Scientists (Class 4)": [
        "Know the contributions of famous Indian and world scientists",
        "Match scientists with their key discoveries or inventions",
        "Appreciate the role of science in everyday life",
    ],
    "Festivals of India (Class 4)": [
        "Know major festivals of different religions in India",
        "Understand the significance and customs of each festival",
        "Appreciate the diversity and unity in Indian festivals",
    ],
    "Sports and Games (Class 4)": [
        "Know popular sports played in India and the world",
        "Identify famous Indian sportspersons and their achievements",
        "Understand basic rules and facts about major sports",
    ],
    "Indian Constitution (Class 5)": [
        "Understand the basic structure of the Indian Constitution",
        "Know fundamental rights and duties of Indian citizens",
        "Appreciate the contributions of Dr B.R. Ambedkar and the Preamble",
    ],
    "World Heritage Sites (Class 5)": [
        "Know UNESCO World Heritage Sites in India",
        "Identify globally famous heritage sites and their significance",
        "Understand why heritage conservation is important",
    ],
    "Space Missions (Class 5)": [
        "Know about ISRO and its key missions like Chandrayaan and Mangalyaan",
        "Understand the purpose of satellites and space exploration",
        "Compare Indian and global space achievements",
    ],
    "Environmental Awareness (Class 5)": [
        "Understand different types of pollution and their causes",
        "Know the importance of conservation and recycling",
        "Appreciate the role of individuals in protecting the environment",
    ],
    # ── Moral Science ──────────────────────────
    "Sharing (Class 1)": [
        "Understand why sharing is important",
        "Give examples of sharing in everyday life",
        "Recognise how sharing makes others feel happy",
    ],
    "Honesty (Class 1)": [
        "Understand why telling the truth is important",
        "Identify honest and dishonest actions in stories",
        "Practise being fair and truthful in daily life",
    ],
    "Kindness (Class 2)": [
        "Understand what kindness means in actions and words",
        "Give examples of being kind to people and animals",
        "Recognise how kindness helps build friendships",
    ],
    "Respecting Elders (Class 2)": [
        "Understand why we should respect elders",
        "Practise good manners like greeting and listening",
        "Know the importance of following instructions from elders",
    ],
    "Teamwork (Class 3)": [
        "Understand the value of working together as a team",
        "Identify different roles people play in a team",
        "Practise cooperation and support in group activities",
    ],
    "Empathy (Class 3)": [
        "Understand what empathy means and why it matters",
        "Identify feelings of others in different situations",
        "Practise being supportive and understanding",
    ],
    "Environmental Care (Class 3)": [
        "Understand how human actions affect the environment",
        "Practise reduce, reuse, and recycle in daily life",
        "Know why protecting nature is everyone's responsibility",
    ],
    "Leadership (Class 4)": [
        "Identify qualities of a good leader",
        "Understand the importance of responsibility and decision-making",
        "Give examples of leaders who inspire others",
    ],
    "Global Citizenship (Class 5)": [
        "Understand cultural diversity and respect for all cultures",
        "Know basic concepts of human rights and world peace",
        "Appreciate the importance of global cooperation",
    ],
    "Digital Ethics (Class 5)": [
        "Understand responsible behaviour in the digital world",
        "Know about online privacy and digital footprint",
        "Practise safe and ethical use of the internet",
    ],
    # ── Health & Physical Education ──────────────────────────
    "Personal Hygiene (Class 1)": [
        "Understand the importance of handwashing and brushing teeth",
        "Know when and how to keep the body clean",
        "Practise good hygiene habits like bathing and wearing clean clothes",
    ],
    "Good Posture (Class 1)": [
        "Understand why sitting and standing straight is important",
        "Know the correct way to carry a school bag",
        "Practise good posture while reading and writing",
    ],
    "Basic Physical Activities (Class 1)": [
        "Identify different physical activities like running, jumping, throwing",
        "Understand why exercise and active play are important",
        "Practise basic movements and coordination skills",
    ],
    "Healthy Eating Habits (Class 2)": [
        "Understand why eating fruits and vegetables is important",
        "Know the importance of drinking enough water every day",
        "Identify healthy food choices and avoid junk food",
    ],
    "Outdoor Play (Class 2)": [
        "Understand the benefits of playing outside every day",
        "Identify different types of outdoor games and activities",
        "Know how outdoor play helps the body and mind",
    ],
    "Basic Stretching (Class 2)": [
        "Know why warming up before exercise is important",
        "Identify simple stretches for arms, legs, and back",
        "Practise a basic warm-up routine before physical activity",
    ],
    "Balanced Diet (Class 3)": [
        "Understand the five food groups and their importance",
        "Know what a balanced Indian thali looks like",
        "Identify different nutrients and their role in the body",
    ],
    "Team Sports Rules (Class 3)": [
        "Know the basic rules of cricket, football, kabaddi, and kho-kho",
        "Understand the importance of fair play and sportsmanship",
        "Identify different positions and roles in team sports",
    ],
    "Safety at Play (Class 3)": [
        "Understand playground safety rules and precautions",
        "Know what a first aid kit contains and when to use it",
        "Identify safe and unsafe behaviours during play",
    ],
    "First Aid Basics (Class 4)": [
        "Know how to treat minor cuts, burns, and bruises",
        "Understand when and how to bandage a wound",
        "Know when to call an adult or seek medical help",
    ],
    "Yoga Introduction (Class 4)": [
        "Identify basic yoga asanas like Tadasana, Vrikshasana, and Balasana",
        "Understand the benefits of yoga for body and mind",
        "Practise basic breathing exercises (pranayama)",
    ],
    "Importance of Sleep (Class 4)": [
        "Understand how many hours of sleep children need",
        "Know the effects of screen time before bedtime",
        "Practise good sleep hygiene habits",
    ],
    "Fitness and Stamina (Class 5)": [
        "Understand what physical fitness and stamina mean",
        "Know different exercises that build strength and endurance",
        "Learn how to measure basic fitness levels",
    ],
    "Nutrition Labels Reading (Class 5)": [
        "Understand how to read a food label on packaged foods",
        "Know what calories, protein, fat, and sugar mean on labels",
        "Make healthier food choices by comparing nutrition labels",
    ],
    "Mental Health Awareness (Class 5)": [
        "Understand what mental health means and why it matters",
        "Know healthy ways to manage stress and difficult feelings",
        "Practise mindfulness and talking about emotions",
    ],
}


def get_learning_objectives(topic: str) -> list[str]:
    """Return learning objectives for a topic. Falls back to empty list."""
    from app.services.slot_engine import get_topic_profile, TOPIC_PROFILES as _TP
    # Resolve to canonical key
    profile = get_topic_profile(topic)
    if profile:
        for key, prof in _TP.items():
            if prof is profile:
                return LEARNING_OBJECTIVES.get(key, [])
    return LEARNING_OBJECTIVES.get(topic, [])


# ── Topic Context Bank (Gold-G3) ────────────────────────────
# Rich Indian contexts for word problems, keyed by canonical topic name.
# Note: CONTEXT_BANK is already used as the application variant picker (list).
# This dict is named TOPIC_CONTEXT_BANK and exposed as get_context_bank().

TOPIC_CONTEXT_BANK: dict[str, list[str]] = {
    # Class 3 topics
    "Addition (carries)": [
        "cricket runs scored across overs", "mango picking in an orchard",
        "stamp collection counting", "marbles game tally",
        "rangoli dots pattern", "school library books",
        "train passengers boarding", "Diwali gift money from relatives",
        "school canteen sales", "kite festival string lengths",
    ],
    "Subtraction (borrowing)": [
        "bus passengers getting off at stops", "remaining rotis after dinner",
        "rakhi money spent on gifts", "water tank draining litres",
        "cricket runs needed to win", "sweets left after distribution",
        "pages left to read in a storybook", "distance left on a road trip",
        "coins spent at a mela stall", "marbles lost in a game",
    ],
    "Addition and subtraction (3-digit)": [
        "school attendance across days", "shop sales and returns",
        "cricket match run chase", "Diwali cracker budget spent and saved",
        "bus passengers boarding and alighting", "pocket money earned and spent",
        "library books borrowed and returned", "mela ticket sales",
        "harvest baskets filled and emptied", "stamp album additions and trades",
    ],
    "Multiplication (tables 2-10)": [
        "rows of diyas in Diwali decoration", "legs of animals in a farm",
        "packets of biscuits for a class party", "seating rows in a cinema hall",
        "wheels on auto-rickshaws in a stand", "petals on flowers in a garden",
        "pages read per day over a week", "cricket overs and balls",
        "bangles in sets for Diwali", "idli plates served at breakfast",
    ],
    "Division basics": [
        "sharing laddoos equally among friends", "splitting auto fare among riders",
        "distributing sweets on birthday", "dividing marbles into equal groups",
        "sharing mangoes from a tree", "splitting pocket money across days",
        "equal rows of students in assembly", "distributing notebooks in class",
        "sharing rotis at a family meal", "dividing Diwali crackers among siblings",
    ],
    "Numbers up to 10000": [
        "population of a small village", "distance between two Indian cities in km",
        "price of a bicycle in rupees", "number of students in a big school",
        "railway station daily passengers", "library total book count",
        "village panchayat election votes", "mela daily footfall",
        "school annual day audience count", "pin codes of nearby areas",
    ],
    "Fractions (halves, quarters)": [
        "cutting a paratha into halves", "sharing a pizza with family",
        "dividing a rangoli design", "half-time in a cricket match",
        "quarter of a watermelon", "folding a dupatta in half",
        "half a glass of lassi", "quarter turn on a playground roundabout",
        "sharing a bar of chocolate", "half the length of a cricket pitch",
    ],
    "Fractions": [
        "slicing a cake at a birthday party", "portions of a thali plate",
        "fraction of students wearing white", "part of a garden with flowers",
        "fraction of a day spent in school", "piece of sugarcane shared",
        "portion of rangoli pattern coloured", "fraction of pocket money saved",
        "part of a book read this week", "share of chores done by siblings",
    ],
    "Time (reading clock, calendar)": [
        "school bell timings", "cricket match overs and breaks",
        "train departure from station", "prayer assembly time",
        "lunch break duration", "festival dates on calendar",
        "morning walk routine", "cartoon show timing on TV",
        "exam schedule across days", "bus arrival intervals",
    ],
    "Money (bills and change)": [
        "auto-rickshaw fares in the city", "chai stall change calculation",
        "mela shopping for toys and snacks", "Diwali gift money budgeting",
        "school canteen lunch buying", "buying notebooks at a stationery shop",
        "paying for ice cream from a cart", "saving in a piggy bank",
        "buying fruits from a sabzi mandi", "ticket price at a local cinema",
    ],
    "Symmetry": [
        "rangoli design with fold line", "butterfly wing patterns",
        "mehendi design on both hands", "temple gopuram architecture",
        "kolam pattern symmetry", "Indian flag layout",
        "peacock feather eye pattern", "diya lamp shape",
        "lotus flower petals", "kite shape for Makar Sankranti",
    ],
    "Patterns and sequences": [
        "kolam dot patterns on the ground", "bangle colour sequences",
        "rangoli border tile patterns", "clapping rhythm in a song",
        "number plate sequences on a street", "train coach number patterns",
        "flower garland bead patterns", "floor tile patterns in a temple",
        "embroidery stitch patterns", "day-night cycle counting",
    ],
    # Class 1 topics
    "Numbers 1 to 50 (Class 1)": [
        "counting crayons in a box", "counting flowers in a garden",
        "students standing in a line", "birds sitting on a wire",
        "beads on a necklace", "marbles in a bag",
        "bangles on Dadi's wrist", "rotis on a plate",
        "fingers on hands", "toffees in a jar",
    ],
    "Numbers 51 to 100 (Class 1)": [
        "pages in a storybook", "mangoes in a basket",
        "steps to climb to the terrace", "beads on an abacus",
        "shells collected at the beach", "stickers in a collection",
        "seeds in a sunflower", "ants marching in a row",
        "leaves picked from the garden", "stars drawn on a chart",
    ],
    "Addition up to 20 (Class 1)": [
        "Raju collecting marbles from friends", "Meena picking flowers for Amma",
        "toffees shared by Bablu and Priya", "birds joining a flock on a tree",
        "crayons in two pencil boxes", "bananas from two bunches",
        "Dadi giving rotis to children", "balloons at a birthday party",
        "toy cars from two shelves", "stickers on two pages",
    ],
    "Subtraction within 20 (Class 1)": [
        "Raju eating toffees from a packet", "birds flying away from a tree",
        "Meena giving away her bangles", "balloons popping at a party",
        "marbles lost during a game", "Bablu sharing crayons with friends",
        "flowers wilting in a garden", "Priya eating fruits from a basket",
        "Dadi distributing laddoos", "leaves falling from a plant",
    ],
    "Basic Shapes (Class 1)": [
        "shapes of rotis on a plate", "windows and doors in a house",
        "wheels of a bicycle", "face of a clock",
        "shape of a samosa", "bangles and coins",
        "kite flying on Makar Sankranti", "tiles on the kitchen floor",
        "shape of a chapati board", "traffic signs on the road",
    ],
    "Measurement (Class 1)": [
        "comparing pencils in a pencil box", "ribbons for tying braids",
        "two friends standing side by side", "a cat and a dog",
        "a watermelon and a lemon", "Amma's dupatta and Raju's scarf",
        "a school bag and a lunch box", "a cricket bat and a stump",
        "Dadi's walking stick and an umbrella", "a chapati roller and a spoon",
    ],
    "Time (Class 1)": [
        "Raju's morning routine before school", "Amma cooking breakfast",
        "Bablu playing in the park after school", "Priya doing homework in the evening",
        "Dadi telling a bedtime story", "days of the school week",
        "Sunday visit to the temple", "morning assembly at school",
        "lunch break with friends", "Meena's evening prayer time",
    ],
    "Money (Class 1)": [
        "buying a toffee from a shop", "Bablu's piggy bank coins",
        "Priya buying a pencil from the canteen", "coins in Dadi's purse",
        "Raju saving one-rupee coins", "buying a balloon at a mela",
        "Meena counting coins after Diwali", "paying for an ice cream bar",
        "coins found under the sofa cushion", "buying a eraser at the stationery shop",
    ],
    # Class 2 topics
    "Numbers up to 1000 (Class 2)": [
        "houses in a colony", "beads on an abacus",
        "pages in a thick storybook", "steps walked to school",
        "grains of rice in a handful", "blocks in a building set",
        "stickers in a collection", "ants in a line near the kitchen",
        "leaves on a small plant branch", "people at a village fair",
    ],
    "Addition (2-digit with carry)": [
        "toffees collected at a birthday party", "runs scored in a gully cricket match",
        "stickers traded between friends", "flowers picked for puja",
        "steps climbed in a temple", "birds counted in the morning",
        "shells collected at the beach", "pages of drawing done this month",
        "chapatis made for a family meal", "toy cars in two boxes combined",
    ],
    "Subtraction (2-digit with borrow)": [
        "balloons that burst at a party", "toffees eaten from a pack",
        "pages torn from an old notebook", "birds that flew away from a tree",
        "beads fallen off a necklace", "cookies eaten from a jar",
        "crayons broken in a box", "stickers given to a friend",
        "leaves fallen from a plant", "samosas eaten at tea time",
    ],
    "Multiplication (tables 2-5)": [
        "pairs of shoes in a family", "wheels on cycles in a parking stand",
        "eyes of children in a group", "legs of chairs in a classroom",
        "petals on simple flowers", "fingers on hands of friends",
        "packets of chips for a party", "rows of desks in class",
        "rotis on each plate at dinner", "pencils in sets at a shop",
    ],
    "Division (sharing equally)": [
        "sharing toffees among classmates", "dividing crayons into equal groups",
        "splitting chapatis for family members", "sharing toys between siblings",
        "equal groups for a relay race", "distributing laddu at prasad",
        "sharing colour pencils in art class", "equal piles of building blocks",
        "dividing fruits for tiffin boxes", "sharing stickers with friends",
    ],
    "Shapes and space (2D)": [
        "shapes of rotis and parathas", "wheels of vehicles on the road",
        "windows and doors of a house", "tiles on the kitchen floor",
        "rangoli shapes drawn at Diwali", "shape of a cricket ground",
        "kite shapes flying at Makar Sankranti", "traffic signs on the road",
        "shapes of Indian sweets", "patterns on a bedsheet",
    ],
    "Measurement (length, weight)": [
        "height of friends in class", "length of a school corridor",
        "weight of fruit bags at a sabzi mandi", "length of a dupatta or saree",
        "distance from home to school", "weight of a school bag",
        "height of a coconut tree", "length of a train platform",
        "weight of a watermelon", "distance of a running race in school",
    ],
    "Time (hour, half-hour)": [
        "school start and end time", "cartoon show on TV",
        "morning prayer assembly", "lunch time at home",
        "evening play time", "bed time routine",
        "weekend temple visit", "half-hour bus ride to grandma's house",
        "birthday party start time", "daily milk delivery time",
    ],
    "Money (coins and notes)": [
        "buying a pencil from the school stall", "ice cream from the cart",
        "coins in a piggy bank", "pocket money for the week",
        "paying for auto-rickshaw to school", "buying a balloon at a fair",
        "saving coins for a toy", "buying snacks at the canteen",
        "change from a 10-rupee note", "counting coins after Diwali",
    ],
    "Data handling (pictographs)": [
        "favourite fruits survey in class", "vehicles passing the school gate",
        "birds spotted in the garden", "favourite colours of classmates",
        "pets owned by students", "favourite games in the class",
        "types of trees in the school garden", "lunch box items survey",
        "modes of transport to school", "favourite festivals of classmates",
    ],
    # Class 4 topics
    "Large numbers (up to 1,00,000)": [
        "population of a town", "cost of a second-hand car in rupees",
        "annual visitors to a national park", "seats in a cricket stadium",
        "distance between major Indian cities", "monthly electricity units in a building",
        "books in a city library", "votes in a local election",
        "daily newspaper circulation", "annual rainfall in millimetres",
    ],
    "Addition and subtraction (5-digit)": [
        "school fundraiser totals across branches", "train passengers across stations",
        "city population growth over years", "annual school fee calculations",
        "distance covered in a road trip", "factory production units per month",
        "event ticket revenue", "hospital patient counts across months",
        "village water supply litres", "government scheme beneficiaries",
    ],
    "Multiplication (3-digit × 2-digit)": [
        "cost of chairs for a school hall", "notebooks needed for all students in a school",
        "tiles needed to floor a room", "daily bus passengers over a month",
        "packets produced in a factory per day", "cost of uniforms for an entire school",
        "bricks needed to build a wall", "seeds planted in rows in a farm",
        "pages printed by a press in a week", "rice bags supplied to ration shops",
    ],
    "Division (long division)": [
        "distributing textbooks equally to classrooms", "splitting harvest produce into bags",
        "equal installments for a bicycle purchase", "dividing sweets for a school event",
        "sharing prize money among team members", "distributing saplings to villages",
        "equal portions of cloth for uniforms", "splitting fuel cost on a group trip",
        "pages to read per day to finish a book", "dividing budget across school departments",
    ],
    "Fractions (equivalent, comparison)": [
        "comparing slices of different sized cakes", "fraction of a cricket pitch length",
        "portion of a wall painted by two workers", "share of a farm's harvest",
        "fraction of students present on different days", "comparing fuel tank fill levels",
        "portion of homework done by evening", "share of chores between siblings",
        "fraction of a garden with vegetables vs flowers", "comparing distances walked on two days",
    ],
    "Decimals (tenths, hundredths)": [
        "measuring height in metres and centimetres", "price tags in a supermarket",
        "cricket batting averages", "temperature readings at a weather station",
        "race timings in seconds at sports day", "measuring fabric at a tailor shop",
        "weighing gold at a jewellery shop", "petrol pump meter readings",
        "measuring medicine doses in ml", "school exam marks as percentages",
    ],
    "Geometry (angles, lines)": [
        "corners of a carrom board", "clock hands forming angles",
        "railway tracks as parallel lines", "corners of a cricket field boundary",
        "ladder leaning against a wall", "edges of an Indian kite",
        "angles in rangoli star patterns", "road intersections in a city grid",
        "roof slopes of different houses", "angles of a temple gopuram",
    ],
    "Perimeter and area": [
        "fencing a school playground", "tiling a kitchen floor",
        "border wire for a picture frame", "area of a classroom for new carpet",
        "perimeter of a cricket pitch", "fencing a vegetable garden",
        "painting a wall of a room", "area of a table top for a cover",
        "border for a rangoli square", "land area of a house plot",
    ],
    "Time (minutes, 24-hour clock)": [
        "railway timetable departures", "school period durations",
        "cooking time for different dishes", "cricket innings duration",
        "bus route schedule across the city", "flight departure in 24-hour format",
        "exam time allocation per section", "TV show schedule in 24-hour clock",
        "factory shift timings", "hospital visiting hours",
    ],
    "Money (bills, profit/loss)": [
        "shopkeeper buying and selling notebooks", "auto-rickshaw daily earnings and fuel cost",
        "fruit vendor profit at a mandi", "school canteen monthly expenses and income",
        "buying wholesale and selling retail sweets", "craft fair stall earnings",
        "farmer selling crops at market", "tailor's cloth cost vs stitching charge",
        "mobile recharge shop profit", "Diwali gift hamper business",
    ],
    # Class 5 topics
    "Numbers up to 10 lakh (Class 5)": [
        "population of Indian cities", "annual budget of a school",
        "cricket stadium seating capacity", "distance between Indian cities in km",
        "railway passengers in a month", "votes counted in a Lok Sabha election",
        "number of books in a state library", "annual rainfall across states",
        "sales figures of a Diwali mela", "Aadhaar card numbers and PIN codes",
    ],
    "Factors and multiples (Class 5)": [
        "arranging students in equal rows for assembly", "grouping sweets into equal boxes for Diwali",
        "packing biscuit packets into cartons", "dividing land into equal plots",
        "bus departure intervals from a station", "flower arrangements in a temple",
        "seating arrangements in a marriage hall", "distributing textbooks to classrooms",
        "tiling a floor with square tiles", "organising cricket teams from a player pool",
    ],
    "HCF and LCM (Class 5)": [
        "two buses starting together and meeting again", "cutting cloth and ribbon into equal pieces",
        "traffic signal timing at a crossing", "bells ringing at different intervals in a temple",
        "making gift hampers with equal items", "scheduling two recurring school events",
        "packing fruits equally into baskets", "finding common free period for two classes",
        "dividing sweets and namkeen equally for guests", "overlapping train schedules at a junction",
    ],
    "Fractions (add and subtract) (Class 5)": [
        "sharing a pizza among friends", "dividing a paratha into parts at lunch",
        "adding lengths of ribbon for gift wrapping", "combining fractions of work done by siblings",
        "mixing ingredients for a recipe", "fraction of homework done over two days",
        "combining portions of a tank filled by two taps", "adding distances walked in two trips",
        "fraction of a cricket ground mowed in two days", "sharing a watermelon at a picnic",
    ],
    "Decimals (all operations) (Class 5)": [
        "shopping bill at a supermarket", "measuring heights of students in metres",
        "petrol pump readings in litres", "cricket batting and bowling averages",
        "race timing in seconds at sports day", "weighing gold at a jewellery shop",
        "temperature readings from a weather station", "electricity meter readings",
        "tailor measuring cloth in metres", "distance run during a morning jog",
    ],
    "Percentage (Class 5)": [
        "exam marks as percentage", "discount on Diwali shopping",
        "school attendance percentage", "cricket win percentage of a team",
        "election voting percentage", "savings as percentage of pocket money",
        "marks needed to pass an exam", "percentage of students in a bus vs walking",
        "sale discount at a garment shop", "nutrient percentage on a food packet label",
    ],
    "Area and volume (Class 5)": [
        "painting walls of a classroom", "volume of a water tank on the roof",
        "area of a school playground", "tiling a courtyard at home",
        "volume of a cuboidal lunch box", "fencing and planting a garden",
        "area of cloth for making a curtain", "volume of a brick for construction",
        "carpeting a room for a puja ceremony", "area of a triangular park in a colony",
    ],
    "Geometry (circles, symmetry) (Class 5)": [
        "wheel of a bicycle", "rangoli designs using circles",
        "bangle shapes and sizes", "circular garden in a park",
        "clock face as a circle", "symmetry of a butterfly",
        "kolam patterns for Pongal", "circular rotis and parathas",
        "Indian flag symmetry", "ashoka chakra wheel spokes",
    ],
    "Data handling (pie charts) (Class 5)": [
        "favourite sports survey in school", "monthly household expenses",
        "types of vehicles passing school gate", "how students travel to school",
        "subjects liked by students in a class", "sales of different items at a canteen",
        "time spent on activities in a day", "rainfall data across months",
        "population distribution of a village", "favourite festival survey results",
    ],
    "Speed distance time (Class 5)": [
        "train journey between cities", "auto-rickshaw ride to school",
        "running race at sports day", "cycling trip to a friend's house",
        "aeroplane travel between Indian metros", "walking to the market and back",
        "bus speed on a highway", "boat crossing a river",
        "relay race in school sports meet", "delivery van reaching on time",
    ],
    # ── English Language Context Banks ──
    # ── Class 1 English ──
    "Alphabet (Class 1)": [
        "letters on a classroom board", "letters on building blocks",
        "alphabet chart on the wall", "letters in Raju's name",
        "letters on Amma's shopping list", "letters on a school bus",
        "letters in a picture book", "letters on a birthday card",
        "letters on a lunch box", "letters on a colourful poster",
    ],
    "Phonics (Class 1)": [
        "sounds of animals at a farm", "sounds of things at school",
        "sounds heard at a mela", "sounds of objects in the kitchen",
        "sounds of toys", "sounds of vehicles on the road",
        "sounds at a park", "sounds during a rainy day",
        "sounds of birds in the garden", "sounds at a Diwali celebration",
    ],
    "Self and Family Vocabulary (Class 1)": [
        "Meena's family photo", "Raju talking about his Dadi",
        "a family having dinner together", "Amma combing Priya's hair",
        "Papa reading a story at bedtime", "visiting Nani's house",
        "brother and sister playing together", "family going to a temple",
        "helping Amma in the kitchen", "family celebrating a birthday",
    ],
    "Animals and Food Vocabulary (Class 1)": [
        "animals at a village farm", "pets at Raju's home",
        "birds near a pond", "fruits at a fruit cart",
        "vegetables in Amma's basket", "food on a banana leaf",
        "animals at a small zoo", "a cow in the field",
        "a hen and her chicks", "lunch boxes at school",
    ],
    "Greetings and Polite Words (Class 1)": [
        "greeting the teacher in the morning", "saying goodbye to Amma at the school gate",
        "thanking a friend for sharing lunch", "saying sorry after bumping into someone",
        "welcoming a guest at home", "saying good night to Dadi",
        "meeting a new friend at school", "asking for water politely",
        "thanking the auto-rickshaw driver", "greeting neighbours during Diwali",
    ],
    "Seasons (Class 1)": [
        "playing in the rain during monsoon", "wearing sweaters in winter",
        "drinking lassi in summer", "flying kites on Makar Sankranti",
        "picking mangoes in summer", "jumping in puddles during rain",
        "a cold morning at school", "flowers blooming in spring",
        "a hot afternoon at the park", "Holi celebrations in spring",
    ],
    "Simple Sentences (Class 1)": [
        "things Meena sees at school", "what Raju does in the morning",
        "a day at the park", "things in my school bag",
        "my pet dog", "what I eat for lunch",
        "playing with friends", "helping Amma at home",
        "a visit to Dadi's house", "things I see on the road",
    ],
    # ── Class 2 English ──
    "Nouns (Class 2)": [
        "things in a school bag", "animals at a zoo", "fruits at a market",
        "people in a family", "places in a town", "things in a kitchen",
        "toys in a room", "birds in a garden", "things at a park", "vehicles on a road",
    ],
    "Verbs (Class 2)": [
        "things children do at school", "actions at a playground", "morning routine activities",
        "cooking actions in kitchen", "festival celebration activities", "actions at a cricket match",
        "things a pet dog does", "actions at a birthday party", "rainy day activities", "garden activities",
    ],
    "Pronouns (Class 2)": [
        "talking about a friend at school", "describing family members", "a day at the park with friends",
        "Meera and her new pet", "Arjun and his cricket match", "children playing in the rain",
        "helping grandmother in the kitchen", "visiting grandparents during holidays",
        "Priya sharing her lunch", "going to the market with mother",
    ],
    "Sentences (Class 2)": [
        "describing a school day", "a visit to the zoo", "a rainy day at home",
        "going to a Diwali mela", "playing with friends", "helping at home",
        "a birthday celebration", "visiting a farm", "a picnic at the park", "a day at the beach",
    ],
    "Rhyming Words (Class 2)": [
        "animals and their sounds", "things at school", "colours and objects",
        "food items", "body parts", "weather words",
        "action words", "family members", "nature words", "playground words",
    ],
    "Punctuation (Class 2)": [
        "questions about school", "sentences about family", "talking about pets",
        "describing a festival", "telling about a holiday", "asking about food",
        "sentences about friends", "talking about weather", "describing a picture", "telling a story",
    ],
    "Nouns (Class 3)": [
        "visiting a historical monument", "a cricket tournament at school", "Diwali shopping at a bazaar",
        "animals at a wildlife sanctuary", "a train journey across India",
        "school assembly activities", "things at a science exhibition",
        "Independence Day celebration", "market day in a village", "a visit to a temple",
    ],
    "Verbs (Class 3)": [
        "activities during a school sports day", "cooking a meal with family",
        "a day at a hill station", "celebrating Holi", "a morning at the river ghat",
        "playing kabaddi", "helping in the school garden",
        "activities at a book fair", "a rainy day adventure", "packing for a trip",
    ],
    "Adjectives (Class 3)": [
        "describing Indian festivals", "comparing animals at a zoo", "describing Indian food",
        "weather in different seasons", "comparing fruits at a market",
        "describing a new classroom", "beautiful places in India",
        "comparing cricketers", "describing a monsoon day", "things at a craft mela",
    ],
    "Pronouns (Class 3)": [
        "a school trip to a museum", "siblings doing homework together",
        "Aarav and his science project", "a joint family gathering",
        "teammates at a cricket match", "children at a summer camp",
        "Diya helping her neighbour", "festival preparations at home",
        "a teacher and her students", "friends at a birthday party",
    ],
    "Tenses (Class 3)": [
        "a school day routine", "what happened at the mela yesterday",
        "plans for the summer holidays", "a cricket match story",
        "cooking with grandmother", "a rainy day experience",
        "visiting the Taj Mahal", "a school picnic", "festival celebrations", "daily morning routine",
    ],
    "Punctuation (Class 3)": [
        "a letter to a friend", "a diary entry about a holiday",
        "a conversation between friends", "instructions for a game",
        "an invitation to a party", "a notice for school",
        "questions in a quiz", "exclamations at a magic show", "a shopping list dialogue", "a news report",
    ],
    "Vocabulary (Class 3)": [
        "words about Indian festivals", "school-related vocabulary", "nature and environment words",
        "food and cooking terms", "transport and travel words",
        "sports vocabulary", "family and relationships", "weather words",
        "market and shopping terms", "animal habitats",
    ],
    "Reading Comprehension (Class 3)": [
        "a story about a brave girl from a village", "a passage about Indian wildlife",
        "an article about healthy eating", "a story about a school competition",
        "a passage about Indian festivals", "a story about helping others",
        "an article about saving water", "a story about a train journey",
        "a passage about Indian monuments", "a story about friendship",
    ],
    "Tenses (Class 4)": [
        "describing a historical event", "a diary entry about today",
        "plans for a school annual day", "a news report about a cricket match",
        "writing about a science experiment", "a story with flashbacks",
        "describing a festival that just ended", "future plans for summer camp",
        "what is happening right now at school", "a letter about yesterday's trip",
    ],
    "Sentence Types (Class 4)": [
        "a classroom discussion", "a trip to a national park",
        "giving instructions for a recipe", "a surprise birthday party",
        "a school debate", "emergency instructions",
        "a science experiment", "a football match commentary", "a shopping conversation", "a fire drill",
    ],
    "Conjunctions (Class 4)": [
        "comparing two Indian cities", "reasons for being late to school",
        "choosing between two activities", "a cause-and-effect story",
        "describing two friends who are different", "advantages and disadvantages of TV",
        "a story with multiple events", "explaining choices at a restaurant",
        "contrasting seasons", "connecting ideas about a holiday",
    ],
    "Prepositions (Class 4)": [
        "describing a room layout", "giving directions to the library",
        "describing a picture of a market", "a treasure hunt at school",
        "where things are in a classroom", "a journey through a city",
        "describing positions in a cricket field", "a map of a village",
        "objects in a school bag", "a scene at a railway station",
    ],
    "Adverbs (Class 4)": [
        "describing how animals move", "a sports commentary",
        "telling about daily routines", "a detective story",
        "comparing how two children study", "a cooking show description",
        "weather report", "describing a dance performance",
        "how people travel to school", "actions during a fire drill",
    ],
    "Prefixes and Suffixes (Class 4)": [
        "words about feelings and emotions", "words describing people",
        "words about doing things again", "opposite meanings",
        "words about states and conditions", "science-related words",
        "words about abilities", "words from daily life",
        "words about size and quantity", "words about actions and results",
    ],
    "Vocabulary (Class 4)": [
        "words from an Indian newspaper", "vocabulary about Indian cuisine",
        "words related to Indian geography", "vocabulary from a science textbook",
        "words about Indian art and culture", "environmental vocabulary",
        "words about technology", "vocabulary from Indian stories",
        "words about health and fitness", "words from a travel brochure",
    ],
    "Reading Comprehension (Class 4)": [
        "a passage about Mahatma Gandhi", "an article about Indian space programme",
        "a story about a village school", "a passage about endangered animals in India",
        "an article about Indian classical music", "a story about a young inventor",
        "a passage about the water cycle", "an article about Indian railways",
        "a story about courage and kindness", "a passage about healthy habits",
    ],
    # ── Class 5 English Context Banks ──
    "Active and Passive Voice (Class 5)": [
        "The cricket match was won by India", "Amma cooked biryani for Diwali",
        "The Taj Mahal was built by Shah Jahan", "Ravi planted a mango tree in the garden",
        "The rangoli was drawn by Meena", "The teacher praised the students",
        "The kite was flown by Arjun during Makar Sankranti", "Dadi told us a bedtime story",
        "The school was decorated for Republic Day", "The postman delivered the letter",
    ],
    "Direct and Indirect Speech (Class 5)": [
        "Amma said to Priya, 'Finish your homework before dinner'",
        "The teacher said, 'India got independence in 1947'",
        "Raju asked, 'Can we play cricket after school?'",
        "Dadi said, 'I will make ladoos for Diwali'",
        "The shopkeeper said, 'Mangoes cost fifty rupees a kilo'",
        "Papa said, 'We are going to Jaipur next week'",
        "Meena said, 'I love reading Panchatantra stories'",
        "The doctor said, 'Drink plenty of water in summer'",
        "Arjun said, 'I scored the highest in the maths test'",
        "The conductor said, 'The bus to Agra leaves at 8 AM'",
    ],
    "Complex Sentences (Class 5)": [
        "Ravi could not play because it was raining during monsoon",
        "Meena finished her homework before she went to the mela",
        "Although the exam was difficult, Priya scored well",
        "The farmer was happy when the monsoon arrived",
        "Arjun will go to the library after he eats his tiffin",
        "Since Diwali is near, the market is very crowded",
        "The train was late because there was fog in Delhi",
        "Amma made kheer while Dadi told us a story",
        "If you study hard, you will pass the exam with good marks",
        "The children played kabaddi until it became dark",
    ],
    "Summary Writing (Class 5)": [
        "a passage about the Indian freedom struggle", "an article about saving tigers in India",
        "a story about a young girl winning a science competition", "a passage about the water crisis in villages",
        "an article about ISRO's Mars mission", "a story about a farmer and the monsoon",
        "a passage about the importance of yoga", "an article about Indian folk dances",
        "a story about a village library", "a passage about protecting the Ganges river",
    ],
    "Comprehension (Class 5)": [
        "a passage about Swami Vivekananda", "an article about the Indian Constitution",
        "a story about a girl from Ladakh", "a passage about Indian classical dance forms",
        "an article about renewable energy in India", "a story about a school trip to Hampi",
        "a passage about the history of Indian textiles", "an article about child education in rural India",
        "a story about a brave boy during a flood", "a passage about Indian cuisine and its diversity",
    ],
    "Synonyms and Antonyms (Class 5)": [
        "words from an Indian newspaper editorial", "vocabulary about the environment",
        "words from a story about an Indian festival", "vocabulary about health and hygiene",
        "words describing Indian monuments", "vocabulary from a science article",
        "words about sports and sportsmanship", "vocabulary from an Indian fable",
        "words about school life and studies", "vocabulary about nature and wildlife",
    ],
    "Formal Letter Writing (Class 5)": [
        "writing to the principal about a school event", "writing to the municipality about road repairs",
        "writing to the editor about traffic near school", "writing to a company to order school supplies",
        "writing to the headmaster requesting leave", "writing to the librarian about new books",
        "writing to an NGO about a cleanliness drive", "writing to the district collector about water supply",
        "writing to a pen friend about your city", "writing to the sports teacher about forming a cricket team",
    ],
    "Creative Writing (Class 5)": [
        "a rainy day at school during monsoon", "visiting a mela in your village",
        "my favourite Indian festival", "a day without electricity at home",
        "a trip to the mountains in Himachal", "helping Amma in the kitchen during Pongal",
        "a school picnic to a historical fort", "my best friend and our adventures",
        "what I want to be when I grow up", "a funny incident on a train journey",
    ],
    "Clauses (Class 5)": [
        "Ravi, who lives in Jaipur, loves flying kites", "The book that Meena borrowed was very interesting",
        "Priya waited at the bus stop until the rain stopped", "The mango tree which Dadi planted has grown tall",
        "Arjun ran fast because he was late for school", "Amma said that she would cook rajma for dinner",
        "The boy who won the kabaddi match is my friend", "We visited the fort where Shivaji Maharaj lived",
        "If the monsoon comes early, the farmers will be happy", "The girl whose painting won first prize is from our class",
    ],
    # ── Science Class 3 Context Banks ──
    "Plants (Class 3)": [
        "neem tree in the school compound", "tulsi plant at home",
        "mango tree in the garden", "rice paddy fields in a village",
        "lotus in a pond", "banyan tree in the park",
        "coconut trees on a beach", "sunflower in a pot",
        "cactus in Rajasthan", "bamboo grove near a river",
    ],
    "Animals (Class 3)": [
        "a peacock dancing in the rain", "cows at a gaushala",
        "monkeys in a forest", "camels in the Thar desert",
        "elephants at a wildlife sanctuary", "sparrows nesting on a window",
        "fish in a village pond", "a snake in the garden",
        "hens in a backyard", "a dog guarding the house",
    ],
    "Food and Nutrition (Class 3)": [
        "dal-roti lunch at school", "rice and sambar from a mess",
        "fruits at a pushcart vendor", "milk from the local dairy",
        "vegetables at a sabzi mandi", "a thali with all food groups",
        "curd and buttermilk in summer", "jaggery and peanuts as a snack",
        "eggs and paneer for protein", "seasonal fruits like guava and papaya",
    ],
    "Shelter (Class 3)": [
        "a kutcha house in a village", "a pucca house in a city",
        "a bird's nest on a tree", "a beehive under the roof",
        "an igloo in cold regions", "a tent at a camping site",
        "a burrow of a rabbit", "a spider's web in the corner",
        "a houseboat in Kashmir", "stilt houses in Assam",
    ],
    "Water (Class 3)": [
        "collecting rainwater during monsoon", "a village hand pump",
        "the Ganga river flowing through a city", "a farmer irrigating fields",
        "boiling water before drinking", "a water tanker in summer",
        "a pond where clothes are washed", "an overhead water tank in a colony",
        "a well in a Rajasthani village", "water purifier at home",
    ],
    "Air (Class 3)": [
        "flying a kite on Makar Sankranti", "a windy day during monsoon",
        "smoke from a factory chimney", "breathing during morning exercise",
        "a balloon filled with air", "Diwali fireworks and smoke",
        "a fan spinning in a classroom", "drying clothes on a rooftop",
        "a windmill in a village", "air pollution from vehicles on the road",
    ],
    "Our Body (Class 3)": [
        "brushing teeth in the morning", "stretching during PT class",
        "eating lunch at school", "washing hands before meals",
        "a visit to the school nurse", "running in a race on sports day",
        "getting a vaccination at the health centre", "breathing during yoga",
        "wearing spectacles for reading", "a dentist visit",
    ],
    # ── EVS Class 1 Context Banks ──
    "My Family (Class 1)": [
        "Amma cooking roti in the kitchen", "Appa dropping Raju at school",
        "Dadi telling a bedtime story", "Nani making mango pickle",
        "playing with brother and sister in the park", "celebrating Diwali with the whole family",
        "going to the temple with grandparents", "eating dinner together at the table",
        "helping Amma water the tulsi plant", "visiting Nana-Nani during summer holidays",
    ],
    "My Body (Class 1)": [
        "clapping hands during a rhyme", "running in the school playground",
        "washing hands before eating tiffin", "brushing teeth every morning",
        "touching toes during PT class", "waving goodbye to Amma at the school gate",
        "using eyes to read a picture book", "listening to a story with ears",
        "smelling flowers in the garden", "kicking a ball with friends",
    ],
    "Plants Around Us (Class 1)": [
        "watering the tulsi plant at home", "a big neem tree in the school ground",
        "mango tree in Dadi's garden", "lotus flowers in a village pond",
        "coconut trees at the beach", "marigold flowers for Diwali puja",
        "a banana plant behind the house", "sunflower seeds for parrots",
        "a banyan tree at the park", "growing coriander in a pot",
    ],
    "Animals Around Us (Class 1)": [
        "a cow at the local gaushala", "sparrows on the window ledge",
        "a dog guarding the house gate", "a cat sleeping on the chair",
        "parrots eating guava on a tree", "a hen and chicks in the backyard",
        "fish in a glass bowl at home", "a monkey on the school roof",
        "squirrels running in the park", "buffaloes near the village pond",
    ],
    "Food We Eat (Class 1)": [
        "eating roti and dal for lunch", "drinking milk every morning",
        "Amma making rice and sambar", "eating a banana after school",
        "sharing tiffin with friends", "buying fruits from a pushcart",
        "eating curd-rice on a hot day", "Dadi making jaggery ladoo",
        "having idli-chutney for breakfast", "eating seasonal guava",
    ],
    "Seasons and Weather (Class 1)": [
        "playing in the rain during monsoon", "wearing a sweater in winter",
        "drinking lassi in hot summer", "flying kites on Makar Sankranti",
        "using an umbrella on a rainy day", "sitting under a fan in summer",
        "wrapping up in a shawl like Dadi", "jumping in puddles after rain",
        "dry leaves falling from trees in autumn", "morning fog on the way to school",
    ],
    # ── EVS Class 2 Context Banks ──
    "Plants (Class 2)": [
        "parts of the tulsi plant at home", "seeds sprouting in a wet cloth",
        "mango tree flowering in spring", "neem leaves used as medicine",
        "lotus growing in the village pond", "a farmer planting rice seedlings",
        "marigold garlands at the temple", "a banyan tree with hanging roots",
        "coconut palm at the seaside", "bamboo growing near the river",
    ],
    "Animals and Habitats (Class 2)": [
        "a peacock dancing in the rain", "cows resting at the gaushala",
        "a camel walking in the Thar desert", "monkeys in the forest near a hill",
        "fish swimming in a village tank", "an elephant at the wildlife sanctuary",
        "sparrows building a nest on the window", "a frog jumping near the pond",
        "hens pecking grain in the yard", "a snake spotted in the garden",
    ],
    "Food and Nutrition (Class 2)": [
        "a school lunch of dal-roti-sabzi", "fruits from a village orchard",
        "milk from the local dairy", "vegetables from the sabzi mandi",
        "Amma cooking paneer at home", "eating curd and chaas in summer",
        "a balanced thali with all food groups", "jaggery and peanut chikki",
        "eggs for breakfast at home", "seasonal mangoes in summer",
    ],
    "Water (Class 2)": [
        "filling water from a hand pump", "rainwater collecting on the roof",
        "the Ganga river flowing through the city", "a water tanker in the colony",
        "watering plants with a bucket", "a well in the village square",
        "boiling water before drinking", "washing clothes by the pond",
        "a farmer irrigating the field", "a water purifier at school",
    ],
    "Shelter (Class 2)": [
        "a kutcha house in a village", "a pucca flat in the city",
        "a bird's nest on the neem tree", "a beehive under the school roof",
        "a tent at the Kumbh Mela ground", "a rabbit's burrow in the field",
        "a houseboat on Dal Lake in Kashmir", "a stilt house in Assam",
        "a spider's web in the corner", "a dog kennel in the garden",
    ],
    "Our Senses (Class 2)": [
        "smelling marigold flowers in the garden", "listening to bhajan in morning assembly",
        "tasting sweet jalebi at the mela", "touching a soft cotton dupatta",
        "seeing colourful rangoli on Diwali", "hearing the school bell ring",
        "smelling fresh roti being made", "feeling raindrops on the hand",
        "watching a kite in the sky", "tasting sour lemon pickle",
    ],
    # ── Science Class 4 Context Banks ──
    "Living Things (Class 4)": [
        "observing ants carrying food near the school gate", "a tulsi plant growing in a pot at home",
        "watching fish swim in a village pond", "comparing a stone and a puppy in the park",
        "a banyan tree in the school compound", "mushrooms growing on a wet log after monsoon",
        "a lizard on the classroom wall", "a cactus plant in a Rajasthani garden",
        "butterflies in a mustard field in Punjab", "a cow chewing cud at a gaushala",
    ],
    "Human Body (Class 4)": [
        "eating roti-sabzi in the school canteen", "running a race on sports day",
        "bending and stretching during yoga class", "visiting a doctor at the PHC",
        "brushing teeth after eating jalebi", "drinking water after PT period",
        "a skeleton model in the science lab", "getting a health check-up at school",
        "chewing sugarcane at a mela", "doing surya namaskar in morning assembly",
    ],
    "States of Matter (Class 4)": [
        "making ice candy (gola) in summer", "boiling milk on a gas stove at home",
        "steam rising from a pressure cooker", "drying clothes on the terrace in summer",
        "water turning to ice in the freezer", "morning dew on grass in winter",
        "fog covering the road on a Delhi morning", "melting ghee in a kadhai",
        "water droplets on a cold glass of lassi", "Amma making jaggery from sugarcane juice",
    ],
    "Force and Motion (Class 4)": [
        "pushing a heavy trunk across the room", "pulling a bucket of water from a well",
        "a cricket ball rolling on the pitch", "riding a bicycle on a village road",
        "sliding down a slide in the school playground", "a bullock cart moving on a muddy path",
        "a marble rolling on the classroom floor", "Appa pushing a car that won't start",
        "a child on a swing in the park", "a kite being pulled by the wind on Sankranti",
    ],
    "Simple Machines (Class 4)": [
        "using a see-saw in the school playground", "pulling water from a well with a pulley",
        "opening a bottle cap with a lever", "rolling heavy drums up a ramp at a godown",
        "using scissors to cut paper in art class", "a ramp at the railway station for luggage",
        "a flagpole pulley during Republic Day", "using a screwdriver to tighten a screw",
        "a wheelbarrow at a construction site", "a nutcracker to crack walnuts from Kashmir",
    ],
    "Photosynthesis (Class 4)": [
        "a neem tree making food in sunlight", "tulsi leaves turning green in the balcony",
        "rice paddy fields turning green in monsoon", "a mango tree with broad green leaves",
        "lotus leaves floating on a pond", "indoor money plant near a window",
        "banana plants in a Kerala garden", "tea gardens on the hills of Assam",
        "sunflowers facing the sun in a field", "coconut palms along the Goa coast",
    ],
    "Animal Adaptation (Class 4)": [
        "a camel walking in the Thar desert", "fish breathing underwater in a river",
        "a polar bear at a zoo exhibit", "a frog near a village pond in monsoon",
        "an eagle soaring high in the Himalayas", "a chameleon changing colour on a branch",
        "a snake shedding its skin in the garden", "ducks floating on Dal Lake in Kashmir",
        "a yak in the Ladakh mountains", "a monkey swinging from tree to tree in a forest",
    ],
    # ── Science Class 5 Context Banks ──
    "Circulatory System (Class 5)": [
        "feeling the pulse after running in PT class", "a doctor using a stethoscope at a clinic",
        "heart beating faster during a cricket match", "blood flowing from a small cut on the knee",
        "donating blood at a camp in the colony", "veins visible on the back of your hand",
        "a model of the heart in the science lab", "resting after climbing stairs at school",
        "Dadi taking blood pressure medicine", "a Red Cross poster at the hospital",
    ],
    "Respiratory and Nervous System (Class 5)": [
        "breathing heavily after running a race", "doing pranayam during morning yoga",
        "blowing up balloons for a birthday party", "sneezing during a dusty day in summer",
        "feeling pain when touching a hot tawa", "the brain telling your hand to write in class",
        "holding your breath while diving in a pool", "the smell of biryani reaching your nose",
        "a reflex action when stepping on a thorn", "a doctor checking reflexes at the PHC",
    ],
    "Reproduction in Plants and Animals (Class 5)": [
        "bees buzzing around marigold flowers", "a mango tree flowering in spring",
        "seeds sprouting in a wet cloth at school", "a hen sitting on eggs in the backyard",
        "coconut seeds floating in ocean water", "a butterfly laying eggs on a leaf",
        "cotton bolls bursting open in a Gujarat field", "puppies born at the neighbour's house",
        "lotus seeds in a village pond", "a farmer planting rice seedlings in a paddy field",
    ],
    "Physical and Chemical Changes (Class 5)": [
        "Amma making paneer by adding lemon to milk", "an iron gate rusting during monsoon",
        "ice cream melting at a summer mela", "burning wood for a bonfire on Lohri",
        "folding a paper boat during class", "curd forming from warm milk overnight",
        "tearing a page from a notebook", "cooking a chapati on a tawa",
        "dissolving sugar in chai", "a matchstick burning with a bright flame",
    ],
    "Forms of Energy (Class 5)": [
        "a solar panel on the school rooftop", "a torch lighting up a dark room during a power cut",
        "a tabla being played at a school function", "a windmill generating electricity in Rajasthan",
        "an electric heater warming the room in winter", "a pressure cooker whistling in the kitchen",
        "Diwali diyas glowing with heat and light", "a radio playing songs at a chai stall",
        "a microwave oven heating food at home", "lightning and thunder during monsoon",
    ],
    "Solar System and Earth (Class 5)": [
        "watching the sunrise from a hilltop in Munnar", "a globe on the teacher's desk at school",
        "the moon shining bright on Sharad Purnima", "visiting a planetarium on a school trip",
        "shadows changing size during the day", "stars visible on a clear winter night in a village",
        "the sun setting behind the Qutub Minar", "a solar eclipse watched with special glasses",
        "reading about Chandrayaan in the newspaper", "seasons changing from summer to monsoon",
    ],
    "Ecosystem and Food Chains (Class 5)": [
        "a frog eating insects near a rice paddy", "grass growing in a park where deer graze",
        "a tiger hunting in Ranthambore National Park", "mushrooms growing on a fallen tree in a forest",
        "a hawk catching a mouse in a wheat field", "fish eating algae in a Ganga tributary",
        "an owl hunting at night near a village", "earthworms in the school garden compost",
        "a food web poster in the science classroom", "vultures at a carcass in a wildlife sanctuary",
    ],
    # ── Hindi Class 3 Context Banks ──
    "Varnamala (Class 3)": [
        "writing letters on a slate at school", "singing the barakhadi in morning assembly",
        "tracing letters in a Hindi textbook", "a chart of swar and vyanjan on the classroom wall",
        "learning to write your name in Hindi", "matching letters to pictures of animals",
        "a Hindi alphabet puzzle game", "copying letters from the blackboard",
        "practising ka-kha-ga in a notebook", "reading a Hindi storybook with large letters",
    ],
    "Matras (Class 3)": [
        "reading signboards in the bazaar", "spelling words on a Diwali greeting card",
        "labelling pictures in a Hindi workbook", "singing a Hindi rhyme with matra words",
        "reading a menu at a dhaba", "writing names of fruits and vegetables in Hindi",
        "filling in matras on a classroom worksheet", "reading a poster at a mela",
        "a shopkeeper writing prices in Hindi", "writing an invitation card for a birthday party",
    ],
    "Shabd Rachna (Class 3)": [
        "making new words from a Hindi crossword puzzle", "finding opposite words in a story",
        "learning compound words from a Hindi newspaper headline", "a word-building game in class",
        "adding prefixes to words in a Hindi grammar exercise", "breaking long words into parts during reading",
        "making rhyming words for a Hindi poem", "sorting words by type in a workbook",
        "creating a word chain with friends", "finding similar-sounding words in a song",
    ],
    "Vakya Rachna (Class 3)": [
        "writing about a school picnic", "describing your best friend in Hindi",
        "making sentences about a festival celebration", "writing a letter to grandmother",
        "describing a picture of a village scene", "writing about what you did on Sunday",
        "making sentences about animals at the zoo", "writing about your favourite food",
        "describing the weather today in Hindi", "writing about a trip to the market",
    ],
    "Kahani Lekhan (Class 3)": [
        "a story about a clever fox in a jungle", "a tale about a farmer and his golden goose",
        "a story about Birbal's wisdom", "a passage about Holi celebrations in a village",
        "a story about a kind auto-rickshaw driver", "a tale about sharing tiffin at school",
        "a passage about planting trees on Van Mahotsav", "a story about a brave girl saving a bird",
        "a tale about Diwali preparations at home", "a passage about a visit to the Taj Mahal",
    ],
    # ── Computer Science Class 1 (2 topics) ──
    "Parts of Computer (Class 1)": [
        "Riya learning computer parts in her school lab", "Aman pointing to the monitor during IT class",
        "a computer lab in a government school in Jaipur", "Meena using the mouse for the first time",
        "a new computer arriving at a village school", "Arjun asking his teacher about the CPU box",
        "Priya listening to a rhyme on computer speakers", "the keyboard in the Atal Tinkering Lab",
        "Dadi watching her grandson use a computer", "a computer corner in a Delhi library",
    ],
    "Using Mouse and Keyboard (Class 1)": [
        "Ravi practising left-click to open a game", "Ananya learning to type her name on the keyboard",
        "dragging an icon in the school computer lab", "Kiran right-clicking to see a menu",
        "a typing game in an Atal Tinkering Lab", "Sita learning mouse clicks on a donated laptop",
        "Arun scrolling through a picture gallery", "practising mouse control in a Pune school",
        "clicking on letters in an alphabet game", "a teacher showing double-click in IT class",
    ],
    # ── Computer Science Class 2 (3 topics) ──
    "Desktop and Icons (Class 2)": [
        "Priya finding the Recycle Bin icon on her desktop", "Rohit opening Paint from the Start Menu",
        "the school computer showing a Taj Mahal wallpaper", "Meena spotting the taskbar at the bottom",
        "Aman arranging desktop icons in his father's shop", "finding the My Computer icon in the school lab",
        "a desktop with folders named Hindi, Maths, English", "Kavita clicking the Start button for the first time",
        "the computer teacher explaining the desktop layout", "desktop icons at a cyber cafe in a small town",
    ],
    "Basic Typing (Class 2)": [
        "Arjun placing fingers on A-S-D-F in typing class", "Sneha typing her school name in Notepad",
        "a typing speed test in the school computer lab", "Ravi learning correct sitting posture for typing",
        "practising home row keys in an IT period", "Meena typing a short Hindi sentence using a keyboard",
        "a typing tutor game in the Atal Tinkering Lab", "Kiran practising J-K-L keys in her school",
        "typing a Diwali greeting card message", "Aman learning to type without looking at the keyboard",
    ],
    "Special Keys (Class 2)": [
        "Riya pressing Enter to go to the next line", "Aman using Backspace to erase a spelling mistake",
        "Sneha pressing Space bar between two words", "the teacher explaining Shift key for capital letters",
        "Kiran pressing Caps Lock to type her name in capitals", "using Tab key to indent a paragraph",
        "Arjun pressing Escape to close a dialog box", "practising Delete key in a school typing exercise",
        "Meena using Shift+A to type a capital A", "exploring special keys during IT period in a Bangalore school",
    ],
    # ── Computer Science Class 3 (3 topics) ──
    "MS Paint Basics (Class 3)": [
        "Riya drawing the Indian flag in MS Paint", "Aman colouring a rangoli pattern using the fill tool",
        "drawing a mango tree using pencil and brush tools", "Sneha erasing a mistake with the eraser tool",
        "creating a Diwali greeting card in MS Paint", "drawing shapes for a maths diagram",
        "Kiran painting a sunset scene using the colour palette", "saving a drawing as 'MyArt' on the desktop",
        "the IT teacher showing the text tool in Paint", "drawing a cricket bat and ball in the school lab",
    ],
    "Keyboard Shortcuts (Class 3)": [
        "Aman pressing Ctrl+C to copy text for a school project", "Riya using Ctrl+V to paste a paragraph",
        "pressing Ctrl+Z to undo a mistake in a document", "Sneha saving her essay with Ctrl+S",
        "using Alt+Tab to switch between Paint and Word", "the teacher showing Ctrl+A to select all text",
        "Kiran pressing Ctrl+P to print a Diwali card", "using Ctrl+B to make a heading bold",
        "pressing Ctrl+X to cut a sentence and move it", "practising shortcuts during a school computer quiz",
    ],
    "Files and Folders (Class 3)": [
        "Riya creating a folder called 'Class 3 Homework'", "Aman renaming a file from 'Untitled' to 'MyEssay'",
        "organising photos from a school picnic into folders", "deleting an old file from the Downloads folder",
        "Sneha moving her drawing from Desktop to My Documents", "creating subject-wise folders: Maths, Science, English",
        "finding a saved project in the school computer", "the teacher explaining file extensions like .txt and .png",
        "copying a file to a pen drive for a school project", "Kiran searching for a lost file using the search bar",
    ],
    # ── Computer Science Class 4 (3 topics) ──
    "MS Word Basics (Class 4)": [
        "Riya typing an essay about Mahatma Gandhi in MS Word", "Aman making a heading bold and underlined",
        "changing the font to Comic Sans for a school poster", "Sneha inserting a page border for her project",
        "typing a letter to the principal using MS Word", "Kiran changing font colour to red for a title",
        "saving a document as 'IndependenceDay_Essay'", "the teacher showing how to insert a table",
        "Arjun increasing font size to 16 for the heading", "printing a holiday homework sheet from MS Word",
    ],
    "Introduction to Scratch (Class 4)": [
        "Riya making a cat sprite walk across the stage", "Aman adding a cricket ground backdrop in Scratch",
        "creating a Diwali animation with fireworks sprites", "Sneha using a loop to make a sprite dance",
        "programming a sprite to say 'Namaste' when clicked", "the teacher explaining the green flag event block",
        "Kiran changing a sprite costume for animation", "making a mango fall from a tree using motion blocks",
        "creating a simple quiz game about Indian states", "Arjun using repeat block to draw a square",
    ],
    "Internet Safety (Class 4)": [
        "Riya creating a strong password for her school account", "Aman learning not to share his address online",
        "a lesson about safe browsing in the school IT lab", "Sneha spotting a suspicious email and not clicking the link",
        "the teacher explaining why we should not talk to strangers online", "Kiran reporting a mean comment to her teacher",
        "understanding privacy settings on a kids' website", "Arjun learning what personal information means",
        "a poster about cyberbullying at a Bangalore school", "discussing online safety rules during IT period",
    ],
    # ── Computer Science Class 5 (4 topics) ──
    "Scratch Programming (Class 5)": [
        "Riya using a variable to keep score in a cricket game", "Aman using if-else to check quiz answers in Scratch",
        "creating a maze game with arrow key controls", "Sneha using broadcast to switch scenes in a story",
        "programming a Diwali fireworks animation with loops", "Kiran debugging a script that moves the wrong way",
        "making a multiplication quiz game in Scratch", "using a repeat-until block for a racing game",
        "Arjun creating a clone-based game with falling mangoes", "presenting a Scratch project in the school science fair",
    ],
    "Internet Basics (Class 5)": [
        "Riya typing a URL in the browser to visit a kids' encyclopedia", "Aman using Google to search for Indian freedom fighters",
        "Sneha composing an email to her teacher about homework", "learning about browser tabs in the school IT lab",
        "Kiran downloading a PDF worksheet from her school website", "the teacher explaining what a search engine does",
        "Arjun bookmarking a useful maths practice website", "understanding the address bar and home button in Chrome",
        "sending an email with an attachment for a school project", "comparing different search engines like Google and Bing",
    ],
    "MS PowerPoint Basics (Class 5)": [
        "Riya creating a presentation about the Solar System", "Aman adding a slide transition for a science project",
        "inserting a photo of the Taj Mahal into a slide", "Sneha adding bullet points about Indian festivals",
        "the teacher showing how to add animation to text", "Kiran presenting her PPT on Indian wildlife to the class",
        "creating a title slide with the school name and logo", "Arjun adding a chart showing monsoon rainfall data",
        "saving a presentation as 'MyProject.pptx'", "practising slideshow mode before the school assembly",
    ],
    "Digital Citizenship (Class 5)": [
        "Riya learning about digital footprint in her IT class", "Aman understanding why copying images without permission is wrong",
        "a class discussion about online etiquette at a Delhi school", "Sneha learning the difference between sharing and oversharing",
        "the teacher explaining Creative Commons licenses", "Kiran reporting a fake account to the school counsellor",
        "Arjun learning responsible use of Wikipedia for projects", "understanding what cyberbullying looks like and how to stop it",
        "a poster-making activity about safe internet use", "discussing respectful comments and replies during IT class",
    ],
    # ── General Knowledge ──────────────────────────
    "Famous Landmarks (Class 3)": [
        "a school trip to see the Taj Mahal in Agra", "Riya reading about the Qutub Minar in her GK book",
        "Aman watching a documentary about the Great Wall of China", "a quiz about the Eiffel Tower during morning assembly",
        "Sneha drawing the India Gate for her project", "learning about the Hawa Mahal in Jaipur during summer camp",
        "a poster on the Statue of Unity in Gujarat", "the teacher showing photos of the Gateway of India in Mumbai",
        "Kiran writing about the Red Fort in a GK competition", "a virtual tour of the Mysore Palace in class",
    ],
    "National Symbols (Class 3)": [
        "Republic Day celebrations at school with the Indian flag", "Aman learning about the Ashoka Chakra on the flag",
        "a class discussion about the national anthem 'Jana Gana Mana'", "Riya drawing the national emblem for her notebook",
        "the teacher talking about the Bengal tiger as the national animal", "Sneha reading about the Indian peacock in her GK textbook",
        "learning about the lotus as the national flower", "a quiz on national symbols during Independence Day week",
        "Kiran making a chart of Indian national symbols", "a class presentation about the mango as the national fruit",
    ],
    "Solar System Basics (Class 3)": [
        "Aman making a model of the solar system for a school exhibition", "Riya learning the names of planets in order",
        "a planetarium visit during the school's science week", "the teacher explaining why the Sun is a star",
        "Sneha reading about the Moon's phases in her science book", "Kiran drawing Earth and labelling continents and oceans",
        "a quiz about which planet is the largest", "learning about why we have day and night",
        "making a chart showing the distance of planets from the Sun", "a class discussion about satellites orbiting Earth",
    ],
    "Current Awareness (Class 3)": [
        "celebrating Diwali with a rangoli competition at school", "Aman preparing for Republic Day in January",
        "Riya learning about Children's Day on 14th November", "a class chart showing the six seasons of India",
        "Sneha writing about Holi in her GK notebook", "the teacher explaining why we celebrate Independence Day",
        "Kiran talking about Makar Sankranti and kite flying", "preparing for World Environment Day at school",
        "a quiz about important days in the month of August", "learning about Eid and Christmas celebrations across India",
    ],
    "Continents and Oceans (Class 4)": [
        "Riya labelling continents on a world map in her atlas", "Aman learning about Australia as the smallest continent",
        "a geography quiz about the Pacific Ocean being the largest", "Sneha marking the Indian Ocean on her map project",
        "the teacher explaining how many countries are in Africa", "Kiran reading about Antarctica and its ice caps",
        "a class project on the countries of Asia", "learning about South America and the Amazon rainforest",
        "a chart comparing the size of different oceans", "a group activity locating India on the world map",
    ],
    "Famous Scientists (Class 4)": [
        "Aman reading about APJ Abdul Kalam in a biography", "Riya learning about Newton discovering gravity",
        "a class presentation about C.V. Raman and his Nobel Prize", "Sneha writing about Marie Curie for a science project",
        "the teacher telling the story of Thomas Edison and the light bulb", "Kiran making a chart of Indian scientists and their inventions",
        "a quiz on who invented the telephone", "learning about Homi Bhabha and India's nuclear programme",
        "a biography reading week featuring Vikram Sarabhai", "a science day poster about Srinivasa Ramanujan's mathematics",
    ],
    "Festivals of India (Class 4)": [
        "Diwali decorations and rangoli at school", "Aman writing about the story behind Holi",
        "Riya learning about Eid-ul-Fitr and its significance", "Christmas carol singing during the school's winter festival",
        "Sneha presenting about Pongal and harvest celebrations", "the teacher explaining Baisakhi and its importance in Punjab",
        "Kiran making a chart of festivals from different states", "a class discussion about Onam and boat races in Kerala",
        "learning about Navratri and Durga Puja celebrations", "a school assembly about Guru Nanak Jayanti",
    ],
    "Sports and Games (Class 4)": [
        "Aman watching the cricket World Cup with his family", "Riya reading about PV Sindhu winning a medal at the Olympics",
        "a sports day at school with races and relay events", "Sneha learning about hockey being India's national game",
        "the teacher talking about Sachin Tendulkar's records", "Kiran reading about Neeraj Chopra's gold medal in javelin",
        "a class quiz about football World Cup host countries", "learning about kabaddi and its popularity in India",
        "a school assembly presentation on the Olympics", "a poster about Mary Kom and her boxing achievements",
    ],
    "Indian Constitution (Class 5)": [
        "Republic Day celebrations and reading the Preamble", "Aman learning about fundamental rights in civics class",
        "Riya preparing a chart about Dr B.R. Ambedkar", "a class discussion about the Right to Education",
        "Sneha writing about why India is called a republic", "the teacher explaining fundamental duties of citizens",
        "Kiran acting in a skit about the Constituent Assembly", "learning about the Indian Parliament in social studies",
        "a quiz on who was the first President of India", "a debate about children's rights in the Constitution",
    ],
    "World Heritage Sites (Class 5)": [
        "Riya making a project on the Ajanta and Ellora caves", "Aman learning about the Sun Temple at Konark",
        "a class presentation about Hampi ruins in Karnataka", "Sneha reading about the Great Barrier Reef in Australia",
        "the teacher explaining why Machu Picchu is a heritage site", "Kiran visiting the Kaziranga National Park during vacation",
        "a chart comparing Indian and world heritage sites", "learning about the Sundarbans and its mangrove forests",
        "a school quiz about how many UNESCO sites India has", "a virtual tour of the Khajuraho temples during GK class",
    ],
    "Space Missions (Class 5)": [
        "Aman watching the Chandrayaan-3 landing on TV", "Riya reading about Mangalyaan in her GK textbook",
        "a class presentation about ISRO and its achievements", "Sneha learning about NASA's Mars rover missions",
        "the teacher explaining how satellites help with weather forecasting", "Kiran making a timeline of India's space missions",
        "learning about Rakesh Sharma as the first Indian in space", "a quiz about which country launched the first satellite",
        "a school science day poster about the International Space Station", "a debate about the benefits of space exploration",
    ],
    "Environmental Awareness (Class 5)": [
        "Riya planting trees during Van Mahotsav at school", "Aman learning about air pollution in Delhi during winter",
        "a class project on reduce, reuse, and recycle", "Sneha reading about the Ganga cleaning programme",
        "the teacher explaining climate change and global warming", "Kiran making a poster for World Environment Day",
        "a school drive to reduce plastic use in the canteen", "learning about renewable energy sources like solar and wind",
        "a debate about why water conservation matters in India", "a class discussion about composting kitchen waste at home",
    ],
    # ── Moral Science ──────────────────────────
    "Sharing (Class 1)": [
        "Riya sharing her crayons with a new classmate", "Aman giving half his tiffin to a friend who forgot lunch",
        "sharing toys during playtime in the school garden", "Sneha sharing her storybook with her younger brother",
        "the teacher asking children to share art supplies during craft class", "Kiran sharing his umbrella with a friend on a rainy day",
        "sharing sweets during Diwali celebrations at school", "a story about a little bird sharing food with its friends",
        "children sharing the swing during recess", "Aman sharing his favourite game with the class",
    ],
    "Honesty (Class 1)": [
        "Riya telling the truth about breaking a flower pot", "Aman returning a pencil he found on the classroom floor",
        "a story about a boy who told the truth and was praised", "Sneha admitting she forgot to do her homework",
        "the teacher reading a story about an honest woodcutter", "Kiran telling his mother he ate the last biscuit",
        "being honest about who spilled the water in class", "a class discussion about why lying makes things worse",
        "returning extra change to the shopkeeper", "Aman confessing he accidentally tore a library book",
    ],
    "Kindness (Class 2)": [
        "Riya helping a classmate who fell during games period", "Aman being kind to a stray dog near the school gate",
        "Sneha writing a kind note for her teacher on Teachers' Day", "helping an elderly person carry bags at the market",
        "Kiran sharing his snack with a friend who was sad", "the teacher reading a story about a kind elephant",
        "children making get-well cards for a sick classmate", "being kind to the new student on the first day of school",
        "Aman helping his grandmother water the plants", "a story about a kind farmer who helped everyone in the village",
    ],
    "Respecting Elders (Class 2)": [
        "Riya touching her grandmother's feet during Diwali", "Aman saying 'Namaste' to the principal every morning",
        "listening quietly when the teacher is explaining a lesson", "Sneha helping her grandfather find his spectacles",
        "Kiran standing up when an elder enters the classroom", "saying 'thank you' and 'please' to parents and teachers",
        "not interrupting when elders are talking", "Aman carrying his father's bag when he comes home from work",
        "a class discussion about why we respect our grandparents", "greeting the school guard every morning with a smile",
    ],
    "Teamwork (Class 3)": [
        "Riya's group working together for the science exhibition", "Aman and his friends cleaning the classroom together",
        "a cricket team practising cooperation during a school match", "Sneha dividing tasks for a group project on Indian states",
        "the teacher explaining how ants work as a team", "Kiran helping his team win the relay race by passing the baton well",
        "children working together to decorate the classroom for Diwali", "a group of friends building a sandcastle together",
        "working together to organise a charity drive at school", "Aman's team performing a group dance for the annual day",
    ],
    "Empathy (Class 3)": [
        "Riya comforting a friend who lost her water bottle", "Aman understanding why his classmate was feeling sad",
        "the teacher reading a story about walking in someone else's shoes", "Sneha feeling happy when she helped a younger child find their class",
        "Kiran noticing his friend was left out and including him in the game", "understanding why a classmate cried when scolded",
        "a story about a boy who helped a blind man cross the road", "thinking about how the new student feels on their first day",
        "Aman imagining how he would feel if someone took his lunch", "a class discussion about treating others the way you want to be treated",
    ],
    "Environmental Care (Class 3)": [
        "Riya picking up litter during a school cleanliness drive", "Aman switching off lights when leaving a room",
        "Sneha making a compost pit in her garden", "a class project on saving water during summer",
        "Kiran planting a sapling on World Environment Day", "using both sides of paper during art class",
        "the teacher explaining why plastic bags harm animals", "separating dry and wet waste at the school canteen",
        "Aman carrying a cloth bag to the market with his mother", "a poster-making competition about saving the Earth",
    ],
    "Leadership (Class 4)": [
        "Riya being elected class monitor and helping maintain discipline", "Aman leading his team to clean up the school garden",
        "a class discussion about qualities of good leaders like Mahatma Gandhi", "Sneha organising a book donation drive at school",
        "the teacher explaining how leaders make fair decisions", "Kiran taking responsibility when his team lost the quiz competition",
        "leading the morning assembly and speaking confidently", "Aman helping resolve a disagreement between two friends",
        "a story about a student leader who helped improve the school library", "Sneha encouraging shy classmates to participate in the annual day",
    ],
    "Global Citizenship (Class 5)": [
        "Riya learning about different cultures for a school project", "Aman reading about human rights on Human Rights Day",
        "a class debate about world peace and cooperation between nations", "Sneha understanding why cultural diversity makes the world richer",
        "the teacher explaining the United Nations and its role", "Kiran making a chart of children's rights around the world",
        "learning about refugees and how we can help them", "a school assembly about respecting all religions and cultures",
        "Aman discussing why education is a right for every child", "a poster about saying 'no' to discrimination and inequality",
    ],
    "Digital Ethics (Class 5)": [
        "Riya learning not to share her password with friends online", "Aman understanding why copying homework from the internet is wrong",
        "a class discussion about cyberbullying at a Delhi school", "Sneha learning about privacy settings on her tablet",
        "the teacher explaining what a digital footprint is", "Kiran understanding screen time limits set by his parents",
        "learning about not clicking on unknown links or pop-ups", "Aman asking permission before posting a friend's photo online",
        "a school poster about being kind in online comments", "a quiz about safe and responsible internet use",
    ],
    # ── Health & Physical Education ──────────────────────────
    "Personal Hygiene (Class 1)": [
        "Riya washing her hands before eating tiffin at school", "Aman brushing his teeth every morning and night",
        "Sneha taking a bath before getting ready for school", "Kiran wearing a clean uniform to school every day",
        "the teacher showing children how to wash hands with soap", "Arjun keeping his nails trimmed and clean",
        "Riya covering her mouth when she sneezes during assembly", "Aman learning to comb his hair neatly before school",
        "a hygiene chart on the classroom wall with gold stars", "Sneha carrying a clean handkerchief in her pocket every day",
    ],
    "Good Posture (Class 1)": [
        "Riya sitting up straight at her desk during class", "Aman learning to carry his school bag on both shoulders",
        "Sneha standing tall during the national anthem at assembly", "Kiran practising good posture while reading a storybook",
        "the teacher reminding children not to slouch on the bench", "Arjun bending his knees to pick up his tiffin box from the floor",
        "Riya keeping her back straight while writing in her notebook", "Aman adjusting his school bag straps to fit properly",
        "a classroom poster showing correct sitting and standing posture", "Sneha not leaning on one side while sitting on the bench",
    ],
    "Basic Physical Activities (Class 1)": [
        "Riya running in the school ground during games period", "Aman jumping over small hurdles in a relay race",
        "Sneha throwing a ball to her friend during recess", "Kiran catching a bean bag during a class activity",
        "the PT teacher asking children to hop on one foot", "Arjun skipping along the school corridor with his friends",
        "Riya balancing on one leg during a fun exercise", "Aman clapping and marching during the morning warm-up",
        "children playing catch in the school playground", "Sneha rolling a ball to her partner during sports class",
    ],
    "Healthy Eating Habits (Class 2)": [
        "Riya eating a roti-sabzi tiffin instead of chips at school", "Aman drinking a glass of milk every morning before school",
        "Sneha choosing fruit over biscuits for her evening snack", "Kiran drinking water from his bottle during recess",
        "the teacher explaining why junk food is bad for health", "Arjun eating dal-chawal with salad at lunchtime",
        "Riya's mother packing a healthy tiffin with paratha and curd", "Aman refusing to buy samosa from the canteen every day",
        "a classroom chart showing healthy vs unhealthy food choices", "Sneha eating seasonal fruits like mango, guava, and banana",
    ],
    "Outdoor Play (Class 2)": [
        "Riya playing kho-kho with her friends during recess", "Aman riding his bicycle in the park every evening",
        "Sneha playing hopscotch in the school playground", "Kiran flying a kite with his father on Makar Sankranti",
        "the PT teacher explaining why outdoor play is better than TV", "Arjun playing cricket with neighbourhood friends after school",
        "Riya running races with her classmates during sports day", "Aman playing hide-and-seek in the society garden",
        "children skipping rope during the games period", "Sneha playing with a frisbee in the park on Sunday",
    ],
    "Basic Stretching (Class 2)": [
        "Riya stretching her arms above her head before games period", "Aman touching his toes during the morning PT class",
        "Sneha doing neck rolls before starting exercises", "Kiran stretching his legs on the school ground",
        "the PT teacher leading a warm-up before the relay race", "Arjun doing side bends with his classmates",
        "Riya rotating her wrists before writing practice", "Aman learning butterfly stretch during sports class",
        "children doing jumping jacks as a warm-up exercise", "Sneha stretching her calf muscles before running",
    ],
    "Balanced Diet (Class 3)": [
        "Riya learning about the five food groups from a chart in class", "Aman's mother preparing a balanced thali with dal, roti, sabzi, and curd",
        "Sneha understanding why proteins from dal and paneer help muscles grow", "Kiran learning that rice and roti give energy (carbohydrates)",
        "the teacher explaining why a colourful plate is a healthy plate", "Arjun reading about vitamins in fruits like amla, orange, and guava",
        "Riya eating a mix of cereals, pulses, vegetables, and milk products", "Aman learning that calcium from milk makes bones strong",
        "a school project on what an ideal Indian lunch plate should look like", "Sneha comparing a balanced tiffin with an unbalanced one",
    ],
    "Team Sports Rules (Class 3)": [
        "Riya learning the rules of kabaddi during PT class", "Aman understanding the LBW rule in cricket",
        "Sneha playing kho-kho and learning about tagging and chasing", "Kiran understanding offside in football",
        "the PT teacher explaining fair play and not arguing with the referee", "Arjun learning that each player has a specific role in cricket",
        "Riya understanding the rules of passing in basketball", "Aman learning about innings and overs during a cricket match",
        "children practising sportsmanship by shaking hands after a game", "Sneha learning about scoring rules in badminton",
    ],
    "Safety at Play (Class 3)": [
        "Riya wearing proper shoes before going to the playground", "Aman checking the swing for broken parts before sitting on it",
        "Sneha not pushing others on the slide at school", "Kiran learning what to do if someone falls and gets hurt",
        "the teacher showing the first aid kit and explaining its contents", "Arjun learning to warm up before running to avoid injuries",
        "Riya knowing not to play near the road or construction areas", "Aman telling the teacher when a friend scraped her knee",
        "children following queue rules while using the playground equipment", "Sneha understanding why drinking water during play is important",
    ],
    "First Aid Basics (Class 4)": [
        "Riya learning to clean a small cut with water and apply a bandage", "Aman knowing to put cold water on a minor burn immediately",
        "Sneha learning the contents of a first aid kit in the school nurse's room", "Kiran knowing to call an adult when someone faints",
        "the teacher demonstrating how to apply an antiseptic and plaster", "Arjun learning the difference between a sprain and a fracture",
        "Riya knowing not to touch someone else's wound without gloves", "Aman learning to press a clean cloth on a bleeding nose",
        "a school drill on what to do if someone gets stung by a bee", "Sneha learning to keep a hurt friend calm and comfortable until help arrives",
    ],
    "Yoga Introduction (Class 4)": [
        "Riya practising Tadasana (Mountain Pose) during the morning assembly", "Aman learning Vrikshasana (Tree Pose) for balance during PT class",
        "Sneha doing Balasana (Child's Pose) to relax after study time", "Kiran practising deep breathing (pranayama) before an exam",
        "the yoga teacher explaining the benefits of Surya Namaskar", "Arjun doing Bhujangasana (Cobra Pose) to strengthen his back",
        "Riya learning Shavasana (Corpse Pose) for relaxation at the end of yoga class", "Aman practising Sukhasana (Easy Pose) for meditation",
        "a school celebration on International Yoga Day (21 June)", "Sneha learning how yoga helps both body and mind",
    ],
    "Importance of Sleep (Class 4)": [
        "Riya going to bed by 9 PM every school night", "Aman understanding why watching TV before sleep is harmful",
        "Sneha keeping her phone outside the bedroom at night", "Kiran learning that children need 9-11 hours of sleep",
        "the teacher explaining how sleep helps the brain learn and remember", "Arjun feeling tired at school because he slept late playing games",
        "Riya having a fixed bedtime routine — brush, read, sleep", "Aman not drinking cola or tea close to bedtime",
        "a school poster about good sleep habits for children", "Sneha waking up fresh after a full night's sleep before a test",
    ],
    "Fitness and Stamina (Class 5)": [
        "Riya running laps around the school ground to build stamina", "Aman doing push-ups and sit-ups during the PT period",
        "Sneha measuring her fitness by timing a 100-metre sprint", "Kiran practising skipping rope to improve endurance",
        "the PT teacher explaining the difference between strength and stamina", "Arjun jogging every morning in the park near his house",
        "Riya participating in the school cross-country race", "Aman learning that regular exercise keeps the heart healthy",
        "a school fitness test measuring running speed, flexibility, and strength", "Sneha setting a personal goal to run without stopping for 10 minutes",
    ],
    "Nutrition Labels Reading (Class 5)": [
        "Riya reading the nutrition label on a packet of biscuits at the shop", "Aman comparing two brands of juice to find which has less sugar",
        "Sneha checking the expiry date and ingredients on a chips packet", "Kiran learning what 'per serving' means on food labels",
        "the teacher explaining calories, protein, fat, and sugar on labels", "Arjun discovering that his favourite noodles have very high sodium",
        "Riya choosing a cereal with less sugar by reading the label", "Aman learning that 'trans fat: 0g' is a healthier choice",
        "a class activity comparing nutrition labels of packaged foods", "Sneha understanding why preservatives are listed on food packets",
    ],
    "Mental Health Awareness (Class 5)": [
        "Riya talking to her teacher when she felt anxious about exams", "Aman practising deep breathing when he felt angry during a game",
        "Sneha writing in a feelings journal every evening", "Kiran understanding that it is okay to feel sad sometimes",
        "the teacher explaining mindfulness and a 5-minute calm exercise", "Arjun learning to take a break when he felt overwhelmed with homework",
        "Riya telling her parents when she felt worried about something", "Aman being kind to himself after making a mistake in class",
        "a class discussion about managing stress during exam season", "Sneha supporting a friend who was feeling lonely at school",
    ],
}


def get_context_bank(topic: str) -> list[str]:
    """Return Indian context bank entries for a topic, resolving aliases."""
    profile = get_topic_profile(topic)
    if profile:
        for key, prof in TOPIC_PROFILES.items():
            if prof is profile:
                return TOPIC_CONTEXT_BANK.get(key, [])
    return TOPIC_CONTEXT_BANK.get(topic, [])


# ── Topic Profiles ──────────────────────────────────────────

TOPIC_PROFILES: dict[str, dict] = {
    # ── Arithmetic topics (carry/borrow enforcement handled elsewhere) ──
    "Addition (carries)": {
        "allowed_skill_tags": [
            "column_add_with_carry", "addition_word_problem", "addition_error_spot",
            "missing_number", "estimation", "thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": [],
        "disallowed_visual_types": [],
        "default_recipe": [
            {"skill_tag": "column_add_with_carry", "count": 3},
            {"skill_tag": "addition_word_problem", "count": 3},
            {"skill_tag": "missing_number", "count": 2},
            {"skill_tag": "addition_error_spot", "count": 1},
            {"skill_tag": "thinking", "count": 1},
        ],
    },
    "Subtraction (borrowing)": {
        "allowed_skill_tags": [
            "column_sub_with_borrow", "subtraction_word_problem", "subtraction_error_spot",
            "missing_number", "estimation", "thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": [],
        "disallowed_visual_types": [],
        "default_recipe": [
            {"skill_tag": "column_sub_with_borrow", "count": 3},
            {"skill_tag": "subtraction_word_problem", "count": 3},
            {"skill_tag": "missing_number", "count": 2},
            {"skill_tag": "subtraction_error_spot", "count": 1},
            {"skill_tag": "thinking", "count": 1},
        ],
    },
    # ── Combined Addition + Subtraction ──
    "Addition and subtraction (3-digit)": {
        "allowed_skill_tags": [
            "column_add_with_carry", "addition_word_problem", "addition_error_spot",
            "column_sub_with_borrow", "subtraction_word_problem", "subtraction_error_spot",
            "missing_number", "estimation", "thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": [],
        "disallowed_visual_types": [],
        "default_recipe": [
            {"skill_tag": "column_add_with_carry", "count": 2},
            {"skill_tag": "column_sub_with_borrow", "count": 2},
            {"skill_tag": "addition_word_problem", "count": 1},
            {"skill_tag": "subtraction_word_problem", "count": 1},
            {"skill_tag": "addition_error_spot", "count": 1},
            {"skill_tag": "subtraction_error_spot", "count": 1},
            {"skill_tag": "thinking", "count": 1},
        ],
        # Explicit recipes for common question counts
        "recipes_by_count": {
            5: [
                {"skill_tag": "column_add_with_carry", "count": 1},
                {"skill_tag": "column_sub_with_borrow", "count": 1},
                {"skill_tag": "addition_word_problem", "count": 1},
                {"skill_tag": "subtraction_word_problem", "count": 1},
                {"skill_tag": "addition_error_spot", "count": 1},
            ],
            10: [
                {"skill_tag": "column_add_with_carry", "count": 2},
                {"skill_tag": "column_sub_with_borrow", "count": 2},
                {"skill_tag": "addition_word_problem", "count": 1},
                {"skill_tag": "subtraction_word_problem", "count": 1},
                {"skill_tag": "missing_number", "count": 1},
                {"skill_tag": "addition_error_spot", "count": 1},
                {"skill_tag": "subtraction_error_spot", "count": 1},
                {"skill_tag": "thinking", "count": 1},
            ],
            15: [
                {"skill_tag": "column_add_with_carry", "count": 3},
                {"skill_tag": "column_sub_with_borrow", "count": 3},
                {"skill_tag": "addition_word_problem", "count": 2},
                {"skill_tag": "subtraction_word_problem", "count": 2},
                {"skill_tag": "missing_number", "count": 2},
                {"skill_tag": "addition_error_spot", "count": 1},
                {"skill_tag": "subtraction_error_spot", "count": 1},
                {"skill_tag": "thinking", "count": 1},
            ],
            20: [
                {"skill_tag": "column_add_with_carry", "count": 4},
                {"skill_tag": "column_sub_with_borrow", "count": 4},
                {"skill_tag": "addition_word_problem", "count": 2},
                {"skill_tag": "subtraction_word_problem", "count": 3},
                {"skill_tag": "missing_number", "count": 2},
                {"skill_tag": "addition_error_spot", "count": 1},
                {"skill_tag": "subtraction_error_spot", "count": 1},
                {"skill_tag": "thinking", "count": 1},
                {"skill_tag": "estimation", "count": 2},
            ],
        },
    },
    # ── Multiplication / Division ──
    "Multiplication (tables 2-10)": {
        "allowed_skill_tags": [
            "multiplication_tables", "multiplication_word_problem",
            "multiplication_fill_blank", "multiplication_error_spot",
            "multiplication_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": [
            "carry", "borrow", "add", "subtract", "column form",
            "plus", "minus", "regroup",
        ],
        "disallowed_visual_types": ["base_ten_regrouping"],
        "default_recipe": [
            {"skill_tag": "multiplication_tables", "count": 3},
            {"skill_tag": "multiplication_word_problem", "count": 3},
            {"skill_tag": "multiplication_fill_blank", "count": 2},
            {"skill_tag": "multiplication_error_spot", "count": 1},
            {"skill_tag": "multiplication_thinking", "count": 1},
        ],
    },
    "Division basics": {
        "allowed_skill_tags": [
            "division_basics", "division_word_problem",
            "division_fill_blank", "division_error_spot", "division_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["carry", "borrow", "decimal"],
        "disallowed_visual_types": ["base_ten_regrouping"],
        "default_recipe": [
            {"skill_tag": "division_basics", "count": 3},
            {"skill_tag": "division_word_problem", "count": 3},
            {"skill_tag": "division_fill_blank", "count": 2},
            {"skill_tag": "division_error_spot", "count": 1},
            {"skill_tag": "division_thinking", "count": 1},
        ],
    },
    # ── Numbers / Place Value ──
    "Numbers up to 10000": {
        "allowed_skill_tags": [
            "place_value_identify",
            "number_comparison",
            "number_expansion",
            "number_ordering",
            "place_value_error",
            "number_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": [
            "carry", "regroup", "base ten", "column form",
            "rupees", "dirhams", "multiply", "divide", "addition", "subtraction",
        ],
        "disallowed_visual_types": ["base_ten_regrouping"],
        "allowed_visual_types": [None],
        "default_recipe": [
            {"skill_tag": "place_value_identify", "count": 3},
            {"skill_tag": "number_comparison", "count": 2},
            {"skill_tag": "number_expansion", "count": 2},
            {"skill_tag": "number_ordering", "count": 1},
            {"skill_tag": "place_value_error", "count": 1},
            {"skill_tag": "number_thinking", "count": 1},
        ],
    },
    # ── Fractions ──
    "Fractions (halves, quarters)": {
        "allowed_skill_tags": [
            "fraction_identify_half",
            "fraction_identify_quarter",
            "fraction_word_problem",
            "fraction_of_shape_shaded",
            "fraction_error_spot",
            "fraction_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": [
            "thirds", "third", "eighths", "decimals", "percentage",
            "improper fraction", "mixed number", "add fractions", "subtract fractions",
        ],
        "disallowed_visual_types": ["base_ten_regrouping", "clock_face"],
        "allowed_visual_types": [None, "fraction_circle", "fraction_rectangle"],
        "default_recipe": [
            {"skill_tag": "fraction_identify_half", "count": 2},
            {"skill_tag": "fraction_identify_quarter", "count": 1},
            {"skill_tag": "fraction_word_problem", "count": 2},
            {"skill_tag": "fraction_of_shape_shaded", "count": 2},
            {"skill_tag": "fraction_error_spot", "count": 1},
            {"skill_tag": "fraction_thinking", "count": 2},
        ],
    },
    "Fractions": {
        "allowed_skill_tags": [
            "fraction_identify_half", "fraction_identify_quarter",
            "fraction_compare", "fraction_word_problem",
            "fraction_fill_blank", "fraction_error_spot", "fraction_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["carry", "borrow", "decimal", "percentage"],
        "disallowed_visual_types": ["base_ten_regrouping"],
        "default_recipe": [
            {"skill_tag": "fraction_identify_half", "count": 2},
            {"skill_tag": "fraction_identify_quarter", "count": 1},
            {"skill_tag": "fraction_word_problem", "count": 3},
            {"skill_tag": "fraction_fill_blank", "count": 2},
            {"skill_tag": "fraction_error_spot", "count": 1},
            {"skill_tag": "fraction_thinking", "count": 1},
        ],
    },
    # ── Time ──
    "Time (reading clock, calendar)": {
        "allowed_skill_tags": [
            "clock_reading", "time_word_problem", "calendar_reading",
            "time_fill_blank", "time_error_spot", "time_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": [
            "pencils", "points", "students", "chocolates",
            "pages", "marbles", "rupees",
            "round", "estimate", "hundred", "thousand",
            "base ten", "regrouping", "carry", "borrow",
        ],
        "disallowed_visual_types": ["base_ten_regrouping", "number_line"],
        "default_recipe": [
            {"skill_tag": "clock_reading", "count": 3},
            {"skill_tag": "time_word_problem", "count": 3},
            {"skill_tag": "time_fill_blank", "count": 2},
            {"skill_tag": "time_error_spot", "count": 1},
            {"skill_tag": "time_thinking", "count": 1},
        ],
    },
    # ── Money ──
    "Money (bills and change)": {
        "allowed_skill_tags": [
            "money_recognition", "money_word_problem", "money_change",
            "money_fill_blank", "money_error_spot", "money_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["carry", "borrow", "fraction"],
        "disallowed_visual_types": ["base_ten_regrouping"],
        "default_recipe": [
            {"skill_tag": "money_recognition", "count": 2},
            {"skill_tag": "money_word_problem", "count": 3},
            {"skill_tag": "money_fill_blank", "count": 2},
            {"skill_tag": "money_change", "count": 1},
            {"skill_tag": "money_error_spot", "count": 1},
            {"skill_tag": "money_thinking", "count": 1},
        ],
    },
    # ── Symmetry ──
    "Symmetry": {
        "allowed_skill_tags": [
            "symmetry_identify", "symmetry_draw",
            "symmetry_fill_blank", "symmetry_error_spot", "symmetry_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": [
            "carry", "borrow", "addition", "subtraction", "multiply",
            "divide", "plus", "minus", "column",
        ],
        "disallowed_visual_types": ["base_ten_regrouping", "number_line"],
        "default_recipe": [
            {"skill_tag": "symmetry_identify", "count": 3},
            {"skill_tag": "symmetry_draw", "count": 2},
            {"skill_tag": "symmetry_fill_blank", "count": 2},
            {"skill_tag": "symmetry_error_spot", "count": 2},
            {"skill_tag": "symmetry_thinking", "count": 1},
        ],
    },
    # ── Patterns ──
    "Patterns and sequences": {
        "allowed_skill_tags": [
            "number_pattern", "shape_pattern",
            "pattern_fill_blank", "pattern_error_spot", "pattern_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["carry", "borrow", "symmetry", "fraction"],
        "disallowed_visual_types": ["base_ten_regrouping"],
        "default_recipe": [
            {"skill_tag": "number_pattern", "count": 3},
            {"skill_tag": "shape_pattern", "count": 3},
            {"skill_tag": "pattern_fill_blank", "count": 2},
            {"skill_tag": "pattern_error_spot", "count": 1},
            {"skill_tag": "pattern_thinking", "count": 1},
        ],
    },
    # ══════════════════════════════════════════════════════════
    # ══════════════════════════════════════════════════════════
    # Class 1 Topic Profiles
    # ══════════════════════════════════════════════════════════
    # ── Numbers 1 to 50 (Class 1) ──
    "Numbers 1 to 50 (Class 1)": {
        "allowed_skill_tags": [
            "c1_count_identify", "c1_number_compare",
            "c1_number_order", "c1_number_error", "c1_number_think",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["multiply", "divide", "fraction", "decimal", "carry", "borrow"],
        "disallowed_visual_types": ["base_ten_regrouping"],
        "default_recipe": [
            {"skill_tag": "c1_count_identify", "count": 3},
            {"skill_tag": "c1_number_compare", "count": 3},
            {"skill_tag": "c1_number_order", "count": 2},
            {"skill_tag": "c1_number_error", "count": 1},
            {"skill_tag": "c1_number_think", "count": 1},
        ],
    },
    # ── Numbers 51 to 100 (Class 1) ──
    "Numbers 51 to 100 (Class 1)": {
        "allowed_skill_tags": [
            "c1_count_big_identify", "c1_number_big_compare",
            "c1_number_big_order", "c1_number_big_error", "c1_number_big_think",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["multiply", "divide", "fraction", "decimal", "carry", "borrow"],
        "disallowed_visual_types": ["base_ten_regrouping"],
        "default_recipe": [
            {"skill_tag": "c1_count_big_identify", "count": 3},
            {"skill_tag": "c1_number_big_compare", "count": 3},
            {"skill_tag": "c1_number_big_order", "count": 2},
            {"skill_tag": "c1_number_big_error", "count": 1},
            {"skill_tag": "c1_number_big_think", "count": 1},
        ],
    },
    # ── Addition up to 20 (Class 1) ──
    "Addition up to 20 (Class 1)": {
        "allowed_skill_tags": [
            "c1_add_basic", "c1_add_word_problem",
            "c1_add_missing", "c1_add_error", "c1_add_think",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["multiply", "divide", "fraction", "decimal", "carry", "borrow", "column form"],
        "disallowed_visual_types": ["base_ten_regrouping"],
        "default_recipe": [
            {"skill_tag": "c1_add_basic", "count": 3},
            {"skill_tag": "c1_add_word_problem", "count": 3},
            {"skill_tag": "c1_add_missing", "count": 2},
            {"skill_tag": "c1_add_error", "count": 1},
            {"skill_tag": "c1_add_think", "count": 1},
        ],
    },
    # ── Subtraction within 20 (Class 1) ──
    "Subtraction within 20 (Class 1)": {
        "allowed_skill_tags": [
            "c1_sub_basic", "c1_sub_word_problem",
            "c1_sub_missing", "c1_sub_error", "c1_sub_think",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["multiply", "divide", "fraction", "decimal", "carry", "borrow", "column form"],
        "disallowed_visual_types": ["base_ten_regrouping"],
        "default_recipe": [
            {"skill_tag": "c1_sub_basic", "count": 3},
            {"skill_tag": "c1_sub_word_problem", "count": 3},
            {"skill_tag": "c1_sub_missing", "count": 2},
            {"skill_tag": "c1_sub_error", "count": 1},
            {"skill_tag": "c1_sub_think", "count": 1},
        ],
    },
    # ── Basic Shapes (Class 1) ──
    "Basic Shapes (Class 1)": {
        "allowed_skill_tags": [
            "c1_shape_identify", "c1_shape_match",
            "c1_shape_count", "c1_shape_error", "c1_shape_think",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": [
            "add", "subtract", "multiply", "divide", "fraction", "decimal",
            "carry", "borrow", "plus", "minus", "column",
        ],
        "disallowed_visual_types": ["base_ten_regrouping", "number_line"],
        "default_recipe": [
            {"skill_tag": "c1_shape_identify", "count": 3},
            {"skill_tag": "c1_shape_match", "count": 3},
            {"skill_tag": "c1_shape_count", "count": 2},
            {"skill_tag": "c1_shape_error", "count": 1},
            {"skill_tag": "c1_shape_think", "count": 1},
        ],
    },
    # ── Measurement (Class 1) ──
    "Measurement (Class 1)": {
        "allowed_skill_tags": [
            "c1_measure_compare", "c1_measure_order",
            "c1_measure_fill", "c1_measure_error", "c1_measure_think",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": [
            "add", "subtract", "multiply", "divide", "fraction", "decimal",
            "carry", "borrow", "cm", "m", "kg", "g",
        ],
        "disallowed_visual_types": ["base_ten_regrouping", "number_line"],
        "default_recipe": [
            {"skill_tag": "c1_measure_compare", "count": 3},
            {"skill_tag": "c1_measure_order", "count": 3},
            {"skill_tag": "c1_measure_fill", "count": 2},
            {"skill_tag": "c1_measure_error", "count": 1},
            {"skill_tag": "c1_measure_think", "count": 1},
        ],
    },
    # ── Time (Class 1) ──
    "Time (Class 1)": {
        "allowed_skill_tags": [
            "c1_time_identify", "c1_time_sequence",
            "c1_time_fill", "c1_time_error", "c1_time_think",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": [
            "add", "subtract", "multiply", "divide", "fraction", "decimal",
            "carry", "borrow", "o'clock", "half past", "quarter", "minutes", "hours",
        ],
        "disallowed_visual_types": ["base_ten_regrouping", "number_line", "clock"],
        "default_recipe": [
            {"skill_tag": "c1_time_identify", "count": 3},
            {"skill_tag": "c1_time_sequence", "count": 3},
            {"skill_tag": "c1_time_fill", "count": 2},
            {"skill_tag": "c1_time_error", "count": 1},
            {"skill_tag": "c1_time_think", "count": 1},
        ],
    },
    # ── Money (Class 1) ──
    "Money (Class 1)": {
        "allowed_skill_tags": [
            "c1_money_identify", "c1_money_count",
            "c1_money_fill", "c1_money_error", "c1_money_think",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": [
            "multiply", "divide", "fraction", "decimal",
            "carry", "borrow", "notes", "bills",
        ],
        "disallowed_visual_types": ["base_ten_regrouping"],
        "default_recipe": [
            {"skill_tag": "c1_money_identify", "count": 3},
            {"skill_tag": "c1_money_count", "count": 3},
            {"skill_tag": "c1_money_fill", "count": 2},
            {"skill_tag": "c1_money_error", "count": 1},
            {"skill_tag": "c1_money_think", "count": 1},
        ],
    },
    # ══════════════════════════════════════════════════════════
    # Class 2 Topic Profiles
    # ══════════════════════════════════════════════════════════
    # ── Numbers up to 1000 (Class 2) ──
    "Numbers up to 1000 (Class 2)": {
        "allowed_skill_tags": [
            "c2_place_value_identify", "c2_number_compare",
            "c2_number_expansion", "c2_number_ordering",
            "c2_place_value_error", "c2_number_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": [
            "carry", "regroup", "base ten", "column form",
            "rupees", "multiply", "divide", "addition", "subtraction",
            "thousand", "10000",
        ],
        "disallowed_visual_types": ["base_ten_regrouping"],
        "default_recipe": [
            {"skill_tag": "c2_place_value_identify", "count": 3},
            {"skill_tag": "c2_number_compare", "count": 2},
            {"skill_tag": "c2_number_expansion", "count": 2},
            {"skill_tag": "c2_number_ordering", "count": 1},
            {"skill_tag": "c2_place_value_error", "count": 1},
            {"skill_tag": "c2_number_thinking", "count": 1},
        ],
    },
    # ── Addition (2-digit with carry) ──
    "Addition (2-digit with carry)": {
        "allowed_skill_tags": [
            "c2_add_column", "c2_add_word_problem",
            "c2_add_missing_number", "c2_add_error_spot", "c2_add_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["3-digit", "thousand", "hundred"],
        "disallowed_visual_types": [],
        "default_recipe": [
            {"skill_tag": "c2_add_column", "count": 3},
            {"skill_tag": "c2_add_word_problem", "count": 3},
            {"skill_tag": "c2_add_missing_number", "count": 2},
            {"skill_tag": "c2_add_error_spot", "count": 1},
            {"skill_tag": "c2_add_thinking", "count": 1},
        ],
    },
    # ── Subtraction (2-digit with borrow) ──
    "Subtraction (2-digit with borrow)": {
        "allowed_skill_tags": [
            "c2_sub_column", "c2_sub_word_problem",
            "c2_sub_missing_number", "c2_sub_error_spot", "c2_sub_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["3-digit", "thousand", "hundred"],
        "disallowed_visual_types": [],
        "default_recipe": [
            {"skill_tag": "c2_sub_column", "count": 3},
            {"skill_tag": "c2_sub_word_problem", "count": 3},
            {"skill_tag": "c2_sub_missing_number", "count": 2},
            {"skill_tag": "c2_sub_error_spot", "count": 1},
            {"skill_tag": "c2_sub_thinking", "count": 1},
        ],
    },
    # ── Multiplication (tables 2-5) ──
    "Multiplication (tables 2-5)": {
        "allowed_skill_tags": [
            "c2_mult_tables", "c2_mult_word_problem",
            "c2_mult_fill_blank", "c2_mult_error_spot", "c2_mult_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": [
            "carry", "borrow", "add", "subtract", "column form",
            "plus", "minus", "regroup",
        ],
        "disallowed_visual_types": ["base_ten_regrouping"],
        "default_recipe": [
            {"skill_tag": "c2_mult_tables", "count": 3},
            {"skill_tag": "c2_mult_word_problem", "count": 3},
            {"skill_tag": "c2_mult_fill_blank", "count": 2},
            {"skill_tag": "c2_mult_error_spot", "count": 1},
            {"skill_tag": "c2_mult_thinking", "count": 1},
        ],
    },
    # ── Division (sharing equally) ──
    "Division (sharing equally)": {
        "allowed_skill_tags": [
            "c2_div_sharing", "c2_div_word_problem",
            "c2_div_fill_blank", "c2_div_error_spot", "c2_div_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["carry", "borrow", "decimal", "remainder"],
        "disallowed_visual_types": ["base_ten_regrouping"],
        "default_recipe": [
            {"skill_tag": "c2_div_sharing", "count": 3},
            {"skill_tag": "c2_div_word_problem", "count": 3},
            {"skill_tag": "c2_div_fill_blank", "count": 2},
            {"skill_tag": "c2_div_error_spot", "count": 1},
            {"skill_tag": "c2_div_thinking", "count": 1},
        ],
    },
    # ── Shapes and space (2D) ──
    "Shapes and space (2D)": {
        "allowed_skill_tags": [
            "c2_shape_identify", "c2_shape_word_problem",
            "c2_shape_fill_blank", "c2_shape_error_spot", "c2_shape_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": [
            "carry", "borrow", "addition", "subtraction", "multiply",
            "divide", "plus", "minus", "column",
        ],
        "disallowed_visual_types": ["base_ten_regrouping", "number_line"],
        "default_recipe": [
            {"skill_tag": "c2_shape_identify", "count": 3},
            {"skill_tag": "c2_shape_word_problem", "count": 3},
            {"skill_tag": "c2_shape_fill_blank", "count": 2},
            {"skill_tag": "c2_shape_error_spot", "count": 1},
            {"skill_tag": "c2_shape_thinking", "count": 1},
        ],
    },
    # ── Measurement (length, weight) ──
    "Measurement (length, weight)": {
        "allowed_skill_tags": [
            "c2_measure_identify", "c2_measure_compare",
            "c2_measure_fill_blank", "c2_measure_error_spot", "c2_measure_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": [
            "carry", "borrow", "fraction", "symmetry", "multiply", "divide",
        ],
        "disallowed_visual_types": ["base_ten_regrouping"],
        "default_recipe": [
            {"skill_tag": "c2_measure_identify", "count": 3},
            {"skill_tag": "c2_measure_compare", "count": 3},
            {"skill_tag": "c2_measure_fill_blank", "count": 2},
            {"skill_tag": "c2_measure_error_spot", "count": 1},
            {"skill_tag": "c2_measure_thinking", "count": 1},
        ],
    },
    # ── Time (hour, half-hour) ──
    "Time (hour, half-hour)": {
        "allowed_skill_tags": [
            "c2_clock_reading", "c2_time_word_problem",
            "c2_time_fill_blank", "c2_time_error_spot", "c2_time_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": [
            "quarter", "quarter-hour", "15 minutes",
            "carry", "borrow", "base ten", "regrouping",
            "round", "estimate", "hundred", "thousand",
        ],
        "disallowed_visual_types": ["base_ten_regrouping", "number_line"],
        "default_recipe": [
            {"skill_tag": "c2_clock_reading", "count": 3},
            {"skill_tag": "c2_time_word_problem", "count": 3},
            {"skill_tag": "c2_time_fill_blank", "count": 2},
            {"skill_tag": "c2_time_error_spot", "count": 1},
            {"skill_tag": "c2_time_thinking", "count": 1},
        ],
    },
    # ── Money (coins and notes) ──
    "Money (coins and notes)": {
        "allowed_skill_tags": [
            "c2_money_identify", "c2_money_word_problem",
            "c2_money_fill_blank", "c2_money_error_spot", "c2_money_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["carry", "borrow", "fraction", "bills"],
        "disallowed_visual_types": ["base_ten_regrouping"],
        "default_recipe": [
            {"skill_tag": "c2_money_identify", "count": 2},
            {"skill_tag": "c2_money_word_problem", "count": 3},
            {"skill_tag": "c2_money_fill_blank", "count": 3},
            {"skill_tag": "c2_money_error_spot", "count": 1},
            {"skill_tag": "c2_money_thinking", "count": 1},
        ],
    },
    # ── Data handling (pictographs) ──
    "Data handling (pictographs)": {
        "allowed_skill_tags": [
            "c2_data_read", "c2_data_word_problem",
            "c2_data_fill_blank", "c2_data_error_spot", "c2_data_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": [
            "carry", "borrow", "fraction", "symmetry", "multiply", "divide",
        ],
        "disallowed_visual_types": ["base_ten_regrouping"],
        "default_recipe": [
            {"skill_tag": "c2_data_read", "count": 3},
            {"skill_tag": "c2_data_word_problem", "count": 3},
            {"skill_tag": "c2_data_fill_blank", "count": 2},
            {"skill_tag": "c2_data_error_spot", "count": 1},
            {"skill_tag": "c2_data_thinking", "count": 1},
        ],
    },
    # ══════════════════════════════════════════════════════════
    # Class 4 Topic Profiles
    # ══════════════════════════════════════════════════════════
    # ── Large numbers (up to 1,00,000) ──
    "Large numbers (up to 1,00,000)": {
        "allowed_skill_tags": [
            "c4_large_number_identify", "c4_large_number_compare",
            "c4_large_number_order", "c4_large_number_expand",
            "c4_large_number_error", "c4_large_number_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": [
            "carry", "regroup", "base ten", "column form",
            "rupees", "multiply", "divide", "addition", "subtraction",
        ],
        "disallowed_visual_types": ["base_ten_regrouping"],
        "default_recipe": [
            {"skill_tag": "c4_large_number_identify", "count": 3},
            {"skill_tag": "c4_large_number_compare", "count": 2},
            {"skill_tag": "c4_large_number_order", "count": 1},
            {"skill_tag": "c4_large_number_expand", "count": 2},
            {"skill_tag": "c4_large_number_error", "count": 1},
            {"skill_tag": "c4_large_number_thinking", "count": 1},
        ],
    },
    # ── Addition and subtraction (5-digit) ──
    "Addition and subtraction (5-digit)": {
        "allowed_skill_tags": [
            "c4_add5_column", "c4_add5_word_problem",
            "c4_sub5_column", "c4_sub5_word_problem",
            "c4_addsub5_missing", "c4_addsub5_error", "c4_addsub5_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["fraction", "decimal", "angle", "perimeter"],
        "disallowed_visual_types": [],
        "default_recipe": [
            {"skill_tag": "c4_add5_column", "count": 2},
            {"skill_tag": "c4_sub5_column", "count": 1},
            {"skill_tag": "c4_add5_word_problem", "count": 2},
            {"skill_tag": "c4_sub5_word_problem", "count": 1},
            {"skill_tag": "c4_addsub5_missing", "count": 2},
            {"skill_tag": "c4_addsub5_error", "count": 1},
            {"skill_tag": "c4_addsub5_thinking", "count": 1},
        ],
    },
    # ── Multiplication (3-digit x 2-digit) ──
    "Multiplication (3-digit × 2-digit)": {
        "allowed_skill_tags": [
            "c4_mult_setup", "c4_mult_word_problem",
            "c4_mult_missing", "c4_mult_error", "c4_mult_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": [
            "carry", "borrow", "add", "subtract", "column form",
            "plus", "minus", "regroup", "fraction", "decimal",
        ],
        "disallowed_visual_types": ["base_ten_regrouping"],
        "default_recipe": [
            {"skill_tag": "c4_mult_setup", "count": 3},
            {"skill_tag": "c4_mult_word_problem", "count": 3},
            {"skill_tag": "c4_mult_missing", "count": 2},
            {"skill_tag": "c4_mult_error", "count": 1},
            {"skill_tag": "c4_mult_thinking", "count": 1},
        ],
    },
    # ── Division (long division) ──
    "Division (long division)": {
        "allowed_skill_tags": [
            "c4_div_setup", "c4_div_word_problem",
            "c4_div_missing", "c4_div_error", "c4_div_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": [
            "carry", "borrow", "add", "subtract", "fraction", "decimal",
        ],
        "disallowed_visual_types": ["base_ten_regrouping"],
        "default_recipe": [
            {"skill_tag": "c4_div_setup", "count": 3},
            {"skill_tag": "c4_div_word_problem", "count": 3},
            {"skill_tag": "c4_div_missing", "count": 2},
            {"skill_tag": "c4_div_error", "count": 1},
            {"skill_tag": "c4_div_thinking", "count": 1},
        ],
    },
    # ── Fractions (equivalent, comparison) ──
    "Fractions (equivalent, comparison)": {
        "allowed_skill_tags": [
            "c4_fraction_identify", "c4_fraction_compare",
            "c4_fraction_equivalent", "c4_fraction_represent",
            "c4_fraction_error", "c4_fraction_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": [
            "carry", "borrow", "decimal", "percentage", "angle", "perimeter",
        ],
        "disallowed_visual_types": ["base_ten_regrouping"],
        "default_recipe": [
            {"skill_tag": "c4_fraction_identify", "count": 2},
            {"skill_tag": "c4_fraction_compare", "count": 2},
            {"skill_tag": "c4_fraction_equivalent", "count": 2},
            {"skill_tag": "c4_fraction_represent", "count": 2},
            {"skill_tag": "c4_fraction_error", "count": 1},
            {"skill_tag": "c4_fraction_thinking", "count": 1},
        ],
    },
    # ── Decimals (tenths, hundredths) ──
    "Decimals (tenths, hundredths)": {
        "allowed_skill_tags": [
            "c4_decimal_identify", "c4_decimal_compare",
            "c4_decimal_word_problem", "c4_decimal_represent",
            "c4_decimal_error", "c4_decimal_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": [
            "carry", "borrow", "column form", "regroup",
            "angle", "perimeter", "symmetry",
        ],
        "disallowed_visual_types": ["base_ten_regrouping"],
        "default_recipe": [
            {"skill_tag": "c4_decimal_identify", "count": 3},
            {"skill_tag": "c4_decimal_compare", "count": 2},
            {"skill_tag": "c4_decimal_word_problem", "count": 1},
            {"skill_tag": "c4_decimal_represent", "count": 2},
            {"skill_tag": "c4_decimal_error", "count": 1},
            {"skill_tag": "c4_decimal_thinking", "count": 1},
        ],
    },
    # ── Geometry (angles, lines) ──
    "Geometry (angles, lines)": {
        "allowed_skill_tags": [
            "c4_geometry_identify", "c4_geometry_classify",
            "c4_geometry_represent", "c4_geometry_error", "c4_geometry_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": [
            "carry", "borrow", "addition", "subtraction", "multiply",
            "divide", "plus", "minus", "fraction", "decimal",
        ],
        "disallowed_visual_types": ["base_ten_regrouping", "number_line"],
        "default_recipe": [
            {"skill_tag": "c4_geometry_identify", "count": 3},
            {"skill_tag": "c4_geometry_classify", "count": 3},
            {"skill_tag": "c4_geometry_represent", "count": 2},
            {"skill_tag": "c4_geometry_error", "count": 1},
            {"skill_tag": "c4_geometry_thinking", "count": 1},
        ],
    },
    # ── Perimeter and area ──
    "Perimeter and area": {
        "allowed_skill_tags": [
            "c4_perimeter_identify", "c4_perimeter_word_problem",
            "c4_area_word_problem", "c4_perimeter_area_missing",
            "c4_perimeter_area_error", "c4_perimeter_area_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": [
            "carry", "borrow", "fraction", "decimal", "angle",
            "symmetry", "pattern",
        ],
        "disallowed_visual_types": ["base_ten_regrouping", "number_line"],
        "default_recipe": [
            {"skill_tag": "c4_perimeter_identify", "count": 2},
            {"skill_tag": "c4_perimeter_word_problem", "count": 2},
            {"skill_tag": "c4_area_word_problem", "count": 2},
            {"skill_tag": "c4_perimeter_area_missing", "count": 2},
            {"skill_tag": "c4_perimeter_area_error", "count": 1},
            {"skill_tag": "c4_perimeter_area_thinking", "count": 1},
        ],
    },
    # ── Time (minutes, 24-hour clock) ──
    "Time (minutes, 24-hour clock)": {
        "allowed_skill_tags": [
            "c4_time_reading", "c4_time_word_problem", "c4_time_convert",
            "c4_time_missing", "c4_time_error", "c4_time_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": [
            "carry", "borrow", "base ten", "regrouping", "column form",
            "fraction", "decimal", "angle", "perimeter",
        ],
        "disallowed_visual_types": ["base_ten_regrouping", "number_line"],
        "default_recipe": [
            {"skill_tag": "c4_time_reading", "count": 2},
            {"skill_tag": "c4_time_word_problem", "count": 3},
            {"skill_tag": "c4_time_convert", "count": 1},
            {"skill_tag": "c4_time_missing", "count": 2},
            {"skill_tag": "c4_time_error", "count": 1},
            {"skill_tag": "c4_time_thinking", "count": 1},
        ],
    },
    # ── Money (bills, profit/loss) ──
    "Money (bills, profit/loss)": {
        "allowed_skill_tags": [
            "c4_money_identify", "c4_money_word_problem",
            "c4_money_profit_loss", "c4_money_missing",
            "c4_money_error", "c4_money_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": [
            "carry", "borrow", "fraction", "decimal", "angle", "perimeter",
        ],
        "disallowed_visual_types": ["base_ten_regrouping"],
        "default_recipe": [
            {"skill_tag": "c4_money_identify", "count": 2},
            {"skill_tag": "c4_money_word_problem", "count": 2},
            {"skill_tag": "c4_money_profit_loss", "count": 2},
            {"skill_tag": "c4_money_missing", "count": 2},
            {"skill_tag": "c4_money_error", "count": 1},
            {"skill_tag": "c4_money_thinking", "count": 1},
        ],
    },
    # ══════════════════════════════════════════════════════════
    # Class 5 Topic Profiles
    # ══════════════════════════════════════════════════════════
    # ── Numbers up to 10 lakh (Class 5) ──
    "Numbers up to 10 lakh (Class 5)": {
        "allowed_skill_tags": [
            "c5_lakh_identify", "c5_lakh_compare",
            "c5_lakh_expand", "c5_lakh_error", "c5_lakh_think",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": [
            "carry", "regroup", "base ten", "column form",
            "multiply", "divide", "fraction", "decimal",
        ],
        "disallowed_visual_types": ["base_ten_regrouping"],
        "default_recipe": [
            {"skill_tag": "c5_lakh_identify", "count": 3},
            {"skill_tag": "c5_lakh_compare", "count": 3},
            {"skill_tag": "c5_lakh_expand", "count": 2},
            {"skill_tag": "c5_lakh_error", "count": 1},
            {"skill_tag": "c5_lakh_think", "count": 1},
        ],
    },
    # ── Factors and multiples (Class 5) ──
    "Factors and multiples (Class 5)": {
        "allowed_skill_tags": [
            "c5_factor_identify", "c5_factor_apply",
            "c5_factor_missing", "c5_factor_error", "c5_factor_think",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": [
            "carry", "borrow", "column form", "decimal", "percentage",
            "angle", "perimeter", "symmetry",
        ],
        "disallowed_visual_types": ["base_ten_regrouping"],
        "default_recipe": [
            {"skill_tag": "c5_factor_identify", "count": 3},
            {"skill_tag": "c5_factor_apply", "count": 3},
            {"skill_tag": "c5_factor_missing", "count": 2},
            {"skill_tag": "c5_factor_error", "count": 1},
            {"skill_tag": "c5_factor_think", "count": 1},
        ],
    },
    # ── HCF and LCM (Class 5) ──
    "HCF and LCM (Class 5)": {
        "allowed_skill_tags": [
            "c5_hcf_identify", "c5_hcf_apply",
            "c5_hcf_missing", "c5_hcf_error", "c5_hcf_think",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": [
            "carry", "borrow", "column form", "decimal", "percentage",
            "angle", "perimeter", "symmetry",
        ],
        "disallowed_visual_types": ["base_ten_regrouping"],
        "default_recipe": [
            {"skill_tag": "c5_hcf_identify", "count": 3},
            {"skill_tag": "c5_hcf_apply", "count": 3},
            {"skill_tag": "c5_hcf_missing", "count": 2},
            {"skill_tag": "c5_hcf_error", "count": 1},
            {"skill_tag": "c5_hcf_think", "count": 1},
        ],
    },
    # ── Fractions (add and subtract) (Class 5) ──
    "Fractions (add and subtract) (Class 5)": {
        "allowed_skill_tags": [
            "c5_frac_identify", "c5_frac_apply",
            "c5_frac_missing", "c5_frac_error", "c5_frac_think",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": [
            "carry", "borrow", "column form", "decimal", "percentage",
            "angle", "perimeter", "symmetry",
        ],
        "disallowed_visual_types": ["base_ten_regrouping"],
        "default_recipe": [
            {"skill_tag": "c5_frac_identify", "count": 3},
            {"skill_tag": "c5_frac_apply", "count": 3},
            {"skill_tag": "c5_frac_missing", "count": 2},
            {"skill_tag": "c5_frac_error", "count": 1},
            {"skill_tag": "c5_frac_think", "count": 1},
        ],
    },
    # ── Decimals (all operations) (Class 5) ──
    "Decimals (all operations) (Class 5)": {
        "allowed_skill_tags": [
            "c5_dec_identify", "c5_dec_apply",
            "c5_dec_missing", "c5_dec_error", "c5_dec_think",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": [
            "carry", "borrow", "column form", "angle", "perimeter", "symmetry",
        ],
        "disallowed_visual_types": ["base_ten_regrouping"],
        "default_recipe": [
            {"skill_tag": "c5_dec_identify", "count": 3},
            {"skill_tag": "c5_dec_apply", "count": 3},
            {"skill_tag": "c5_dec_missing", "count": 2},
            {"skill_tag": "c5_dec_error", "count": 1},
            {"skill_tag": "c5_dec_think", "count": 1},
        ],
    },
    # ── Percentage (Class 5) ──
    "Percentage (Class 5)": {
        "allowed_skill_tags": [
            "c5_percent_identify", "c5_percent_apply",
            "c5_percent_missing", "c5_percent_error", "c5_percent_think",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": [
            "carry", "borrow", "column form", "angle", "perimeter", "symmetry",
        ],
        "disallowed_visual_types": ["base_ten_regrouping"],
        "default_recipe": [
            {"skill_tag": "c5_percent_identify", "count": 3},
            {"skill_tag": "c5_percent_apply", "count": 3},
            {"skill_tag": "c5_percent_missing", "count": 2},
            {"skill_tag": "c5_percent_error", "count": 1},
            {"skill_tag": "c5_percent_think", "count": 1},
        ],
    },
    # ── Area and volume (Class 5) ──
    "Area and volume (Class 5)": {
        "allowed_skill_tags": [
            "c5_area_identify", "c5_area_apply",
            "c5_area_missing", "c5_area_error", "c5_area_think",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": [
            "carry", "borrow", "column form", "fraction", "percentage",
        ],
        "disallowed_visual_types": ["base_ten_regrouping"],
        "default_recipe": [
            {"skill_tag": "c5_area_identify", "count": 3},
            {"skill_tag": "c5_area_apply", "count": 3},
            {"skill_tag": "c5_area_missing", "count": 2},
            {"skill_tag": "c5_area_error", "count": 1},
            {"skill_tag": "c5_area_think", "count": 1},
        ],
    },
    # ── Geometry (circles, symmetry) (Class 5) ──
    "Geometry (circles, symmetry) (Class 5)": {
        "allowed_skill_tags": [
            "c5_geo_identify", "c5_geo_apply",
            "c5_geo_missing", "c5_geo_error", "c5_geo_think",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": [
            "carry", "borrow", "column form", "fraction", "decimal",
            "percentage", "multiply", "divide",
        ],
        "disallowed_visual_types": ["base_ten_regrouping", "number_line"],
        "default_recipe": [
            {"skill_tag": "c5_geo_identify", "count": 3},
            {"skill_tag": "c5_geo_apply", "count": 3},
            {"skill_tag": "c5_geo_missing", "count": 2},
            {"skill_tag": "c5_geo_error", "count": 1},
            {"skill_tag": "c5_geo_think", "count": 1},
        ],
    },
    # ── Data handling (pie charts) (Class 5) ──
    "Data handling (pie charts) (Class 5)": {
        "allowed_skill_tags": [
            "c5_data_identify", "c5_data_apply",
            "c5_data_missing", "c5_data_error", "c5_data_think",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": [
            "carry", "borrow", "column form", "fraction", "symmetry",
        ],
        "disallowed_visual_types": ["base_ten_regrouping"],
        "default_recipe": [
            {"skill_tag": "c5_data_identify", "count": 3},
            {"skill_tag": "c5_data_apply", "count": 3},
            {"skill_tag": "c5_data_missing", "count": 2},
            {"skill_tag": "c5_data_error", "count": 1},
            {"skill_tag": "c5_data_think", "count": 1},
        ],
    },
    # ── Speed distance time (Class 5) ──
    "Speed distance time (Class 5)": {
        "allowed_skill_tags": [
            "c5_speed_identify", "c5_speed_apply",
            "c5_speed_missing", "c5_speed_error", "c5_speed_think",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": [
            "carry", "borrow", "column form", "fraction", "symmetry",
            "angle", "perimeter",
        ],
        "disallowed_visual_types": ["base_ten_regrouping"],
        "default_recipe": [
            {"skill_tag": "c5_speed_identify", "count": 3},
            {"skill_tag": "c5_speed_apply", "count": 3},
            {"skill_tag": "c5_speed_missing", "count": 2},
            {"skill_tag": "c5_speed_error", "count": 1},
            {"skill_tag": "c5_speed_think", "count": 1},
        ],
    },
    # ════════════════════════════════════════════════════════════
    # English Language Topics (29 topics: 7 Class 1, 6 Class 2, 8 Class 3, 8 Class 4)
    # ════════════════════════════════════════════════════════════
    # ── Class 1 English (7 topics) ──
    "Alphabet (Class 1)": {
        "allowed_skill_tags": [
            "eng_c1_alpha_identify", "eng_c1_alpha_match", "eng_c1_alpha_fill",
            "eng_c1_alpha_error", "eng_c1_alpha_think",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product"],
        "disallowed_visual_types": [],
        "subject": "English",
        "default_recipe": [
            {"skill_tag": "eng_c1_alpha_identify", "count": 3},
            {"skill_tag": "eng_c1_alpha_match", "count": 3},
            {"skill_tag": "eng_c1_alpha_fill", "count": 2},
            {"skill_tag": "eng_c1_alpha_error", "count": 1},
            {"skill_tag": "eng_c1_alpha_think", "count": 1},
        ],
    },
    "Phonics (Class 1)": {
        "allowed_skill_tags": [
            "eng_c1_phonics_identify", "eng_c1_phonics_match", "eng_c1_phonics_fill",
            "eng_c1_phonics_error", "eng_c1_phonics_think",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product"],
        "disallowed_visual_types": [],
        "subject": "English",
        "default_recipe": [
            {"skill_tag": "eng_c1_phonics_identify", "count": 3},
            {"skill_tag": "eng_c1_phonics_match", "count": 3},
            {"skill_tag": "eng_c1_phonics_fill", "count": 2},
            {"skill_tag": "eng_c1_phonics_error", "count": 1},
            {"skill_tag": "eng_c1_phonics_think", "count": 1},
        ],
    },
    "Self and Family Vocabulary (Class 1)": {
        "allowed_skill_tags": [
            "eng_c1_family_identify", "eng_c1_family_match", "eng_c1_family_fill",
            "eng_c1_family_error", "eng_c1_family_think",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product"],
        "disallowed_visual_types": [],
        "subject": "English",
        "default_recipe": [
            {"skill_tag": "eng_c1_family_identify", "count": 3},
            {"skill_tag": "eng_c1_family_match", "count": 3},
            {"skill_tag": "eng_c1_family_fill", "count": 2},
            {"skill_tag": "eng_c1_family_error", "count": 1},
            {"skill_tag": "eng_c1_family_think", "count": 1},
        ],
    },
    "Animals and Food Vocabulary (Class 1)": {
        "allowed_skill_tags": [
            "eng_c1_animals_identify", "eng_c1_animals_match", "eng_c1_animals_fill",
            "eng_c1_animals_error", "eng_c1_animals_think",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product"],
        "disallowed_visual_types": [],
        "subject": "English",
        "default_recipe": [
            {"skill_tag": "eng_c1_animals_identify", "count": 3},
            {"skill_tag": "eng_c1_animals_match", "count": 3},
            {"skill_tag": "eng_c1_animals_fill", "count": 2},
            {"skill_tag": "eng_c1_animals_error", "count": 1},
            {"skill_tag": "eng_c1_animals_think", "count": 1},
        ],
    },
    "Greetings and Polite Words (Class 1)": {
        "allowed_skill_tags": [
            "eng_c1_greetings_identify", "eng_c1_greetings_match", "eng_c1_greetings_fill",
            "eng_c1_greetings_error", "eng_c1_greetings_think",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product"],
        "disallowed_visual_types": [],
        "subject": "English",
        "default_recipe": [
            {"skill_tag": "eng_c1_greetings_identify", "count": 3},
            {"skill_tag": "eng_c1_greetings_match", "count": 3},
            {"skill_tag": "eng_c1_greetings_fill", "count": 2},
            {"skill_tag": "eng_c1_greetings_error", "count": 1},
            {"skill_tag": "eng_c1_greetings_think", "count": 1},
        ],
    },
    "Seasons (Class 1)": {
        "allowed_skill_tags": [
            "eng_c1_seasons_identify", "eng_c1_seasons_match", "eng_c1_seasons_fill",
            "eng_c1_seasons_error", "eng_c1_seasons_think",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product"],
        "disallowed_visual_types": [],
        "subject": "English",
        "default_recipe": [
            {"skill_tag": "eng_c1_seasons_identify", "count": 3},
            {"skill_tag": "eng_c1_seasons_match", "count": 3},
            {"skill_tag": "eng_c1_seasons_fill", "count": 2},
            {"skill_tag": "eng_c1_seasons_error", "count": 1},
            {"skill_tag": "eng_c1_seasons_think", "count": 1},
        ],
    },
    "Simple Sentences (Class 1)": {
        "allowed_skill_tags": [
            "eng_c1_simple_identify", "eng_c1_simple_rewrite", "eng_c1_simple_fill",
            "eng_c1_simple_error", "eng_c1_simple_think",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product"],
        "disallowed_visual_types": [],
        "subject": "English",
        "default_recipe": [
            {"skill_tag": "eng_c1_simple_identify", "count": 3},
            {"skill_tag": "eng_c1_simple_rewrite", "count": 3},
            {"skill_tag": "eng_c1_simple_fill", "count": 2},
            {"skill_tag": "eng_c1_simple_error", "count": 1},
            {"skill_tag": "eng_c1_simple_think", "count": 1},
        ],
    },
    # ── Class 2 English (6 topics) ──
    "Nouns (Class 2)": {
        "allowed_skill_tags": [
            "eng_noun_identify", "eng_noun_use", "eng_noun_complete",
            "eng_noun_error", "eng_noun_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product"],
        "disallowed_visual_types": [],
        "subject": "English",
        "default_recipe": [
            {"skill_tag": "eng_noun_identify", "count": 3},
            {"skill_tag": "eng_noun_use", "count": 3},
            {"skill_tag": "eng_noun_complete", "count": 2},
            {"skill_tag": "eng_noun_error", "count": 1},
            {"skill_tag": "eng_noun_thinking", "count": 1},
        ],
    },
    "Verbs (Class 2)": {
        "allowed_skill_tags": [
            "eng_verb_identify", "eng_verb_use", "eng_verb_complete",
            "eng_verb_error", "eng_verb_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product"],
        "disallowed_visual_types": [],
        "subject": "English",
        "default_recipe": [
            {"skill_tag": "eng_verb_identify", "count": 3},
            {"skill_tag": "eng_verb_use", "count": 3},
            {"skill_tag": "eng_verb_complete", "count": 2},
            {"skill_tag": "eng_verb_error", "count": 1},
            {"skill_tag": "eng_verb_thinking", "count": 1},
        ],
    },
    "Pronouns (Class 2)": {
        "allowed_skill_tags": [
            "eng_pronoun_identify", "eng_pronoun_use", "eng_pronoun_complete",
            "eng_pronoun_error", "eng_pronoun_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product"],
        "disallowed_visual_types": [],
        "subject": "English",
        "default_recipe": [
            {"skill_tag": "eng_pronoun_identify", "count": 3},
            {"skill_tag": "eng_pronoun_use", "count": 3},
            {"skill_tag": "eng_pronoun_complete", "count": 2},
            {"skill_tag": "eng_pronoun_error", "count": 1},
            {"skill_tag": "eng_pronoun_thinking", "count": 1},
        ],
    },
    "Sentences (Class 2)": {
        "allowed_skill_tags": [
            "eng_sentence_identify", "eng_sentence_rewrite", "eng_sentence_rearrange",
            "eng_sentence_error", "eng_sentence_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product"],
        "disallowed_visual_types": [],
        "subject": "English",
        "default_recipe": [
            {"skill_tag": "eng_sentence_identify", "count": 3},
            {"skill_tag": "eng_sentence_rewrite", "count": 3},
            {"skill_tag": "eng_sentence_rearrange", "count": 2},
            {"skill_tag": "eng_sentence_error", "count": 1},
            {"skill_tag": "eng_sentence_thinking", "count": 1},
        ],
    },
    "Rhyming Words (Class 2)": {
        "allowed_skill_tags": [
            "eng_rhyme_identify", "eng_rhyme_match", "eng_rhyme_complete",
            "eng_rhyme_error", "eng_rhyme_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product"],
        "disallowed_visual_types": [],
        "subject": "English",
        "default_recipe": [
            {"skill_tag": "eng_rhyme_identify", "count": 3},
            {"skill_tag": "eng_rhyme_match", "count": 3},
            {"skill_tag": "eng_rhyme_complete", "count": 2},
            {"skill_tag": "eng_rhyme_error", "count": 1},
            {"skill_tag": "eng_rhyme_thinking", "count": 1},
        ],
    },
    "Punctuation (Class 2)": {
        "allowed_skill_tags": [
            "eng_punctuation_identify", "eng_punctuation_use", "eng_punctuation_complete",
            "eng_punctuation_error", "eng_punctuation_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product"],
        "disallowed_visual_types": [],
        "subject": "English",
        "default_recipe": [
            {"skill_tag": "eng_punctuation_identify", "count": 3},
            {"skill_tag": "eng_punctuation_use", "count": 3},
            {"skill_tag": "eng_punctuation_complete", "count": 2},
            {"skill_tag": "eng_punctuation_error", "count": 1},
            {"skill_tag": "eng_punctuation_thinking", "count": 1},
        ],
    },
    # ── Class 3 English (8 topics) ──
    "Nouns (Class 3)": {
        "allowed_skill_tags": [
            "eng_noun_identify", "eng_noun_use", "eng_noun_complete",
            "eng_noun_error", "eng_noun_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product"],
        "disallowed_visual_types": [],
        "subject": "English",
        "default_recipe": [
            {"skill_tag": "eng_noun_identify", "count": 3},
            {"skill_tag": "eng_noun_use", "count": 3},
            {"skill_tag": "eng_noun_complete", "count": 2},
            {"skill_tag": "eng_noun_error", "count": 1},
            {"skill_tag": "eng_noun_thinking", "count": 1},
        ],
    },
    "Verbs (Class 3)": {
        "allowed_skill_tags": [
            "eng_verb_identify", "eng_verb_use", "eng_verb_complete",
            "eng_verb_error", "eng_verb_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product"],
        "disallowed_visual_types": [],
        "subject": "English",
        "default_recipe": [
            {"skill_tag": "eng_verb_identify", "count": 3},
            {"skill_tag": "eng_verb_use", "count": 3},
            {"skill_tag": "eng_verb_complete", "count": 2},
            {"skill_tag": "eng_verb_error", "count": 1},
            {"skill_tag": "eng_verb_thinking", "count": 1},
        ],
    },
    "Adjectives (Class 3)": {
        "allowed_skill_tags": [
            "eng_adjective_identify", "eng_adjective_use", "eng_adjective_complete",
            "eng_adjective_error", "eng_adjective_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product"],
        "disallowed_visual_types": [],
        "subject": "English",
        "default_recipe": [
            {"skill_tag": "eng_adjective_identify", "count": 3},
            {"skill_tag": "eng_adjective_use", "count": 3},
            {"skill_tag": "eng_adjective_complete", "count": 2},
            {"skill_tag": "eng_adjective_error", "count": 1},
            {"skill_tag": "eng_adjective_thinking", "count": 1},
        ],
    },
    "Pronouns (Class 3)": {
        "allowed_skill_tags": [
            "eng_pronoun_identify", "eng_pronoun_use", "eng_pronoun_complete",
            "eng_pronoun_error", "eng_pronoun_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product"],
        "disallowed_visual_types": [],
        "subject": "English",
        "default_recipe": [
            {"skill_tag": "eng_pronoun_identify", "count": 3},
            {"skill_tag": "eng_pronoun_use", "count": 3},
            {"skill_tag": "eng_pronoun_complete", "count": 2},
            {"skill_tag": "eng_pronoun_error", "count": 1},
            {"skill_tag": "eng_pronoun_thinking", "count": 1},
        ],
    },
    "Tenses (Class 3)": {
        "allowed_skill_tags": [
            "eng_tense_identify", "eng_tense_change", "eng_tense_complete",
            "eng_tense_error", "eng_tense_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product"],
        "disallowed_visual_types": [],
        "subject": "English",
        "default_recipe": [
            {"skill_tag": "eng_tense_identify", "count": 3},
            {"skill_tag": "eng_tense_change", "count": 3},
            {"skill_tag": "eng_tense_complete", "count": 2},
            {"skill_tag": "eng_tense_error", "count": 1},
            {"skill_tag": "eng_tense_thinking", "count": 1},
        ],
    },
    "Punctuation (Class 3)": {
        "allowed_skill_tags": [
            "eng_punctuation_identify", "eng_punctuation_use", "eng_punctuation_complete",
            "eng_punctuation_error", "eng_punctuation_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product"],
        "disallowed_visual_types": [],
        "subject": "English",
        "default_recipe": [
            {"skill_tag": "eng_punctuation_identify", "count": 3},
            {"skill_tag": "eng_punctuation_use", "count": 3},
            {"skill_tag": "eng_punctuation_complete", "count": 2},
            {"skill_tag": "eng_punctuation_error", "count": 1},
            {"skill_tag": "eng_punctuation_thinking", "count": 1},
        ],
    },
    "Vocabulary (Class 3)": {
        "allowed_skill_tags": [
            "eng_vocabulary_identify", "eng_vocabulary_use", "eng_vocabulary_match",
            "eng_vocabulary_complete", "eng_vocabulary_error", "eng_vocabulary_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product"],
        "disallowed_visual_types": [],
        "subject": "English",
        "default_recipe": [
            {"skill_tag": "eng_vocabulary_identify", "count": 2},
            {"skill_tag": "eng_vocabulary_use", "count": 2},
            {"skill_tag": "eng_vocabulary_match", "count": 2},
            {"skill_tag": "eng_vocabulary_complete", "count": 2},
            {"skill_tag": "eng_vocabulary_error", "count": 1},
            {"skill_tag": "eng_vocabulary_thinking", "count": 1},
        ],
    },
    "Reading Comprehension (Class 3)": {
        "allowed_skill_tags": [
            "eng_comprehension_identify", "eng_comprehension_answer",
            "eng_comprehension_complete", "eng_comprehension_error",
            "eng_comprehension_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product"],
        "disallowed_visual_types": [],
        "subject": "English",
        "default_recipe": [
            {"skill_tag": "eng_comprehension_identify", "count": 3},
            {"skill_tag": "eng_comprehension_answer", "count": 3},
            {"skill_tag": "eng_comprehension_complete", "count": 2},
            {"skill_tag": "eng_comprehension_error", "count": 1},
            {"skill_tag": "eng_comprehension_thinking", "count": 1},
        ],
    },
    # ── Class 4 English (8 topics) ──
    "Tenses (Class 4)": {
        "allowed_skill_tags": [
            "eng_tense_identify", "eng_tense_change", "eng_tense_complete",
            "eng_tense_error", "eng_tense_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product"],
        "disallowed_visual_types": [],
        "subject": "English",
        "default_recipe": [
            {"skill_tag": "eng_tense_identify", "count": 3},
            {"skill_tag": "eng_tense_change", "count": 3},
            {"skill_tag": "eng_tense_complete", "count": 2},
            {"skill_tag": "eng_tense_error", "count": 1},
            {"skill_tag": "eng_tense_thinking", "count": 1},
        ],
    },
    "Sentence Types (Class 4)": {
        "allowed_skill_tags": [
            "eng_sentence_type_identify", "eng_sentence_type_rewrite",
            "eng_sentence_type_rearrange", "eng_sentence_type_error",
            "eng_sentence_type_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product"],
        "disallowed_visual_types": [],
        "subject": "English",
        "default_recipe": [
            {"skill_tag": "eng_sentence_type_identify", "count": 3},
            {"skill_tag": "eng_sentence_type_rewrite", "count": 3},
            {"skill_tag": "eng_sentence_type_rearrange", "count": 2},
            {"skill_tag": "eng_sentence_type_error", "count": 1},
            {"skill_tag": "eng_sentence_type_thinking", "count": 1},
        ],
    },
    "Conjunctions (Class 4)": {
        "allowed_skill_tags": [
            "eng_conjunction_identify", "eng_conjunction_use", "eng_conjunction_complete",
            "eng_conjunction_error", "eng_conjunction_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product"],
        "disallowed_visual_types": [],
        "subject": "English",
        "default_recipe": [
            {"skill_tag": "eng_conjunction_identify", "count": 3},
            {"skill_tag": "eng_conjunction_use", "count": 3},
            {"skill_tag": "eng_conjunction_complete", "count": 2},
            {"skill_tag": "eng_conjunction_error", "count": 1},
            {"skill_tag": "eng_conjunction_thinking", "count": 1},
        ],
    },
    "Prepositions (Class 4)": {
        "allowed_skill_tags": [
            "eng_preposition_identify", "eng_preposition_use", "eng_preposition_complete",
            "eng_preposition_error", "eng_preposition_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product"],
        "disallowed_visual_types": [],
        "subject": "English",
        "default_recipe": [
            {"skill_tag": "eng_preposition_identify", "count": 3},
            {"skill_tag": "eng_preposition_use", "count": 3},
            {"skill_tag": "eng_preposition_complete", "count": 2},
            {"skill_tag": "eng_preposition_error", "count": 1},
            {"skill_tag": "eng_preposition_thinking", "count": 1},
        ],
    },
    "Adverbs (Class 4)": {
        "allowed_skill_tags": [
            "eng_adverb_identify", "eng_adverb_use", "eng_adverb_complete",
            "eng_adverb_error", "eng_adverb_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product"],
        "disallowed_visual_types": [],
        "subject": "English",
        "default_recipe": [
            {"skill_tag": "eng_adverb_identify", "count": 3},
            {"skill_tag": "eng_adverb_use", "count": 3},
            {"skill_tag": "eng_adverb_complete", "count": 2},
            {"skill_tag": "eng_adverb_error", "count": 1},
            {"skill_tag": "eng_adverb_thinking", "count": 1},
        ],
    },
    "Prefixes and Suffixes (Class 4)": {
        "allowed_skill_tags": [
            "eng_prefix_identify", "eng_suffix_identify", "eng_affix_use",
            "eng_affix_change", "eng_affix_error", "eng_affix_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product"],
        "disallowed_visual_types": [],
        "subject": "English",
        "default_recipe": [
            {"skill_tag": "eng_prefix_identify", "count": 2},
            {"skill_tag": "eng_suffix_identify", "count": 2},
            {"skill_tag": "eng_affix_use", "count": 2},
            {"skill_tag": "eng_affix_change", "count": 2},
            {"skill_tag": "eng_affix_error", "count": 1},
            {"skill_tag": "eng_affix_thinking", "count": 1},
        ],
    },
    "Vocabulary (Class 4)": {
        "allowed_skill_tags": [
            "eng_vocabulary_identify", "eng_vocabulary_use", "eng_vocabulary_match",
            "eng_vocabulary_complete", "eng_vocabulary_error", "eng_vocabulary_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product"],
        "disallowed_visual_types": [],
        "subject": "English",
        "default_recipe": [
            {"skill_tag": "eng_vocabulary_identify", "count": 2},
            {"skill_tag": "eng_vocabulary_use", "count": 2},
            {"skill_tag": "eng_vocabulary_match", "count": 2},
            {"skill_tag": "eng_vocabulary_complete", "count": 2},
            {"skill_tag": "eng_vocabulary_error", "count": 1},
            {"skill_tag": "eng_vocabulary_thinking", "count": 1},
        ],
    },
    "Reading Comprehension (Class 4)": {
        "allowed_skill_tags": [
            "eng_comprehension_identify", "eng_comprehension_answer",
            "eng_comprehension_complete", "eng_comprehension_error",
            "eng_comprehension_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product"],
        "disallowed_visual_types": [],
        "subject": "English",
        "default_recipe": [
            {"skill_tag": "eng_comprehension_identify", "count": 3},
            {"skill_tag": "eng_comprehension_answer", "count": 3},
            {"skill_tag": "eng_comprehension_complete", "count": 2},
            {"skill_tag": "eng_comprehension_error", "count": 1},
            {"skill_tag": "eng_comprehension_thinking", "count": 1},
        ],
    },
    # ════════════════════════════════════════════════════════════
    # ── Class 5 English (9 topics) ──
    # ════════════════════════════════════════════════════════════
    "Active and Passive Voice (Class 5)": {
        "allowed_skill_tags": [
            "eng_c5_voice_identify", "eng_c5_voice_convert",
            "eng_c5_voice_complete", "eng_c5_voice_error", "eng_c5_voice_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "fraction", "decimal", "number line"],
        "disallowed_visual_types": [],
        "subject": "English",
        "default_recipe": [
            {"skill_tag": "eng_c5_voice_identify", "count": 3},
            {"skill_tag": "eng_c5_voice_convert", "count": 3},
            {"skill_tag": "eng_c5_voice_complete", "count": 2},
            {"skill_tag": "eng_c5_voice_error", "count": 1},
            {"skill_tag": "eng_c5_voice_thinking", "count": 1},
        ],
    },
    "Direct and Indirect Speech (Class 5)": {
        "allowed_skill_tags": [
            "eng_c5_speech_identify", "eng_c5_speech_convert",
            "eng_c5_speech_complete", "eng_c5_speech_error", "eng_c5_speech_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "fraction", "decimal", "number line"],
        "disallowed_visual_types": [],
        "subject": "English",
        "default_recipe": [
            {"skill_tag": "eng_c5_speech_identify", "count": 3},
            {"skill_tag": "eng_c5_speech_convert", "count": 3},
            {"skill_tag": "eng_c5_speech_complete", "count": 2},
            {"skill_tag": "eng_c5_speech_error", "count": 1},
            {"skill_tag": "eng_c5_speech_thinking", "count": 1},
        ],
    },
    "Complex Sentences (Class 5)": {
        "allowed_skill_tags": [
            "eng_c5_complex_identify", "eng_c5_complex_rewrite",
            "eng_c5_complex_complete", "eng_c5_complex_error", "eng_c5_complex_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "fraction", "decimal", "number line"],
        "disallowed_visual_types": [],
        "subject": "English",
        "default_recipe": [
            {"skill_tag": "eng_c5_complex_identify", "count": 3},
            {"skill_tag": "eng_c5_complex_rewrite", "count": 3},
            {"skill_tag": "eng_c5_complex_complete", "count": 2},
            {"skill_tag": "eng_c5_complex_error", "count": 1},
            {"skill_tag": "eng_c5_complex_thinking", "count": 1},
        ],
    },
    "Summary Writing (Class 5)": {
        "allowed_skill_tags": [
            "eng_c5_summary_identify", "eng_c5_summary_write",
            "eng_c5_summary_complete", "eng_c5_summary_error", "eng_c5_summary_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "fraction", "decimal", "number line"],
        "disallowed_visual_types": [],
        "subject": "English",
        "default_recipe": [
            {"skill_tag": "eng_c5_summary_identify", "count": 3},
            {"skill_tag": "eng_c5_summary_write", "count": 3},
            {"skill_tag": "eng_c5_summary_complete", "count": 2},
            {"skill_tag": "eng_c5_summary_error", "count": 1},
            {"skill_tag": "eng_c5_summary_thinking", "count": 1},
        ],
    },
    "Comprehension (Class 5)": {
        "allowed_skill_tags": [
            "eng_c5_comprehension_identify", "eng_c5_comprehension_answer",
            "eng_c5_comprehension_complete", "eng_c5_comprehension_error",
            "eng_c5_comprehension_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "fraction", "decimal", "number line"],
        "disallowed_visual_types": [],
        "subject": "English",
        "default_recipe": [
            {"skill_tag": "eng_c5_comprehension_identify", "count": 3},
            {"skill_tag": "eng_c5_comprehension_answer", "count": 3},
            {"skill_tag": "eng_c5_comprehension_complete", "count": 2},
            {"skill_tag": "eng_c5_comprehension_error", "count": 1},
            {"skill_tag": "eng_c5_comprehension_thinking", "count": 1},
        ],
    },
    "Synonyms and Antonyms (Class 5)": {
        "allowed_skill_tags": [
            "eng_c5_synonym_identify", "eng_c5_synonym_match",
            "eng_c5_synonym_use", "eng_c5_synonym_error", "eng_c5_synonym_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "fraction", "decimal", "number line"],
        "disallowed_visual_types": [],
        "subject": "English",
        "default_recipe": [
            {"skill_tag": "eng_c5_synonym_identify", "count": 3},
            {"skill_tag": "eng_c5_synonym_match", "count": 3},
            {"skill_tag": "eng_c5_synonym_use", "count": 2},
            {"skill_tag": "eng_c5_synonym_error", "count": 1},
            {"skill_tag": "eng_c5_synonym_thinking", "count": 1},
        ],
    },
    "Formal Letter Writing (Class 5)": {
        "allowed_skill_tags": [
            "eng_c5_letter_identify", "eng_c5_letter_write",
            "eng_c5_letter_complete", "eng_c5_letter_error", "eng_c5_letter_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "fraction", "decimal", "number line"],
        "disallowed_visual_types": [],
        "subject": "English",
        "default_recipe": [
            {"skill_tag": "eng_c5_letter_identify", "count": 3},
            {"skill_tag": "eng_c5_letter_write", "count": 3},
            {"skill_tag": "eng_c5_letter_complete", "count": 2},
            {"skill_tag": "eng_c5_letter_error", "count": 1},
            {"skill_tag": "eng_c5_letter_thinking", "count": 1},
        ],
    },
    "Creative Writing (Class 5)": {
        "allowed_skill_tags": [
            "eng_c5_creative_identify", "eng_c5_creative_use",
            "eng_c5_creative_expand", "eng_c5_creative_error", "eng_c5_creative_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "fraction", "decimal", "number line"],
        "disallowed_visual_types": [],
        "subject": "English",
        "default_recipe": [
            {"skill_tag": "eng_c5_creative_identify", "count": 3},
            {"skill_tag": "eng_c5_creative_use", "count": 3},
            {"skill_tag": "eng_c5_creative_expand", "count": 2},
            {"skill_tag": "eng_c5_creative_error", "count": 1},
            {"skill_tag": "eng_c5_creative_thinking", "count": 1},
        ],
    },
    "Clauses (Class 5)": {
        "allowed_skill_tags": [
            "eng_c5_clause_identify", "eng_c5_clause_rewrite",
            "eng_c5_clause_complete", "eng_c5_clause_error", "eng_c5_clause_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "fraction", "decimal", "number line"],
        "disallowed_visual_types": [],
        "subject": "English",
        "default_recipe": [
            {"skill_tag": "eng_c5_clause_identify", "count": 3},
            {"skill_tag": "eng_c5_clause_rewrite", "count": 3},
            {"skill_tag": "eng_c5_clause_complete", "count": 2},
            {"skill_tag": "eng_c5_clause_error", "count": 1},
            {"skill_tag": "eng_c5_clause_thinking", "count": 1},
        ],
    },
    # ════════════════════════════════════════════════════════════
    # ── Science Class 3 (7 topics) ──
    # ════════════════════════════════════════════════════════════
    "Plants (Class 3)": {
        "allowed_skill_tags": [
            "sci_plants_identify", "sci_plants_apply", "sci_plants_represent",
            "sci_plants_error", "sci_plants_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product", "fraction"],
        "disallowed_visual_types": [],
        "subject": "Science",
        "default_recipe": [
            {"skill_tag": "sci_plants_identify", "count": 3},
            {"skill_tag": "sci_plants_apply", "count": 3},
            {"skill_tag": "sci_plants_represent", "count": 2},
            {"skill_tag": "sci_plants_error", "count": 1},
            {"skill_tag": "sci_plants_thinking", "count": 1},
        ],
    },
    "Animals (Class 3)": {
        "allowed_skill_tags": [
            "sci_animals_identify", "sci_animals_apply", "sci_animals_represent",
            "sci_animals_error", "sci_animals_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product", "fraction"],
        "disallowed_visual_types": [],
        "subject": "Science",
        "default_recipe": [
            {"skill_tag": "sci_animals_identify", "count": 3},
            {"skill_tag": "sci_animals_apply", "count": 3},
            {"skill_tag": "sci_animals_represent", "count": 2},
            {"skill_tag": "sci_animals_error", "count": 1},
            {"skill_tag": "sci_animals_thinking", "count": 1},
        ],
    },
    "Food and Nutrition (Class 3)": {
        "allowed_skill_tags": [
            "sci_food_identify", "sci_food_apply", "sci_food_represent",
            "sci_food_error", "sci_food_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product", "fraction"],
        "disallowed_visual_types": [],
        "subject": "Science",
        "default_recipe": [
            {"skill_tag": "sci_food_identify", "count": 3},
            {"skill_tag": "sci_food_apply", "count": 3},
            {"skill_tag": "sci_food_represent", "count": 2},
            {"skill_tag": "sci_food_error", "count": 1},
            {"skill_tag": "sci_food_thinking", "count": 1},
        ],
    },
    "Shelter (Class 3)": {
        "allowed_skill_tags": [
            "sci_shelter_identify", "sci_shelter_apply", "sci_shelter_represent",
            "sci_shelter_error", "sci_shelter_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product", "fraction"],
        "disallowed_visual_types": [],
        "subject": "Science",
        "default_recipe": [
            {"skill_tag": "sci_shelter_identify", "count": 3},
            {"skill_tag": "sci_shelter_apply", "count": 3},
            {"skill_tag": "sci_shelter_represent", "count": 2},
            {"skill_tag": "sci_shelter_error", "count": 1},
            {"skill_tag": "sci_shelter_thinking", "count": 1},
        ],
    },
    "Water (Class 3)": {
        "allowed_skill_tags": [
            "sci_water_identify", "sci_water_apply", "sci_water_represent",
            "sci_water_error", "sci_water_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product", "fraction"],
        "disallowed_visual_types": [],
        "subject": "Science",
        "default_recipe": [
            {"skill_tag": "sci_water_identify", "count": 3},
            {"skill_tag": "sci_water_apply", "count": 3},
            {"skill_tag": "sci_water_represent", "count": 2},
            {"skill_tag": "sci_water_error", "count": 1},
            {"skill_tag": "sci_water_thinking", "count": 1},
        ],
    },
    "Air (Class 3)": {
        "allowed_skill_tags": [
            "sci_air_identify", "sci_air_apply", "sci_air_represent",
            "sci_air_error", "sci_air_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product", "fraction"],
        "disallowed_visual_types": [],
        "subject": "Science",
        "default_recipe": [
            {"skill_tag": "sci_air_identify", "count": 3},
            {"skill_tag": "sci_air_apply", "count": 3},
            {"skill_tag": "sci_air_represent", "count": 2},
            {"skill_tag": "sci_air_error", "count": 1},
            {"skill_tag": "sci_air_thinking", "count": 1},
        ],
    },
    "Our Body (Class 3)": {
        "allowed_skill_tags": [
            "sci_body_identify", "sci_body_apply", "sci_body_represent",
            "sci_body_error", "sci_body_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product", "fraction"],
        "disallowed_visual_types": [],
        "subject": "Science",
        "default_recipe": [
            {"skill_tag": "sci_body_identify", "count": 3},
            {"skill_tag": "sci_body_apply", "count": 3},
            {"skill_tag": "sci_body_represent", "count": 2},
            {"skill_tag": "sci_body_error", "count": 1},
            {"skill_tag": "sci_body_thinking", "count": 1},
        ],
    },
    # ════════════════════════════════════════════════════════════
    # ── EVS Class 1 (6 topics) ──
    # ════════════════════════════════════════════════════════════
    "My Family (Class 1)": {
        "allowed_skill_tags": [
            "sci_c1_family_identify", "sci_c1_family_apply", "sci_c1_family_represent",
            "sci_c1_family_error", "sci_c1_family_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product", "fraction", "decimal", "number line", "equation"],
        "disallowed_visual_types": [],
        "subject": "Science",
        "default_recipe": [
            {"skill_tag": "sci_c1_family_identify", "count": 3},
            {"skill_tag": "sci_c1_family_apply", "count": 3},
            {"skill_tag": "sci_c1_family_represent", "count": 2},
            {"skill_tag": "sci_c1_family_error", "count": 1},
            {"skill_tag": "sci_c1_family_thinking", "count": 1},
        ],
    },
    "My Body (Class 1)": {
        "allowed_skill_tags": [
            "sci_c1_body_identify", "sci_c1_body_apply", "sci_c1_body_represent",
            "sci_c1_body_error", "sci_c1_body_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product", "fraction", "decimal", "number line", "equation"],
        "disallowed_visual_types": [],
        "subject": "Science",
        "default_recipe": [
            {"skill_tag": "sci_c1_body_identify", "count": 3},
            {"skill_tag": "sci_c1_body_apply", "count": 3},
            {"skill_tag": "sci_c1_body_represent", "count": 2},
            {"skill_tag": "sci_c1_body_error", "count": 1},
            {"skill_tag": "sci_c1_body_thinking", "count": 1},
        ],
    },
    "Plants Around Us (Class 1)": {
        "allowed_skill_tags": [
            "sci_c1_plants_identify", "sci_c1_plants_apply", "sci_c1_plants_represent",
            "sci_c1_plants_error", "sci_c1_plants_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product", "fraction", "decimal", "number line", "equation"],
        "disallowed_visual_types": [],
        "subject": "Science",
        "default_recipe": [
            {"skill_tag": "sci_c1_plants_identify", "count": 3},
            {"skill_tag": "sci_c1_plants_apply", "count": 3},
            {"skill_tag": "sci_c1_plants_represent", "count": 2},
            {"skill_tag": "sci_c1_plants_error", "count": 1},
            {"skill_tag": "sci_c1_plants_thinking", "count": 1},
        ],
    },
    "Animals Around Us (Class 1)": {
        "allowed_skill_tags": [
            "sci_c1_animals_identify", "sci_c1_animals_apply", "sci_c1_animals_represent",
            "sci_c1_animals_error", "sci_c1_animals_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product", "fraction", "decimal", "number line", "equation"],
        "disallowed_visual_types": [],
        "subject": "Science",
        "default_recipe": [
            {"skill_tag": "sci_c1_animals_identify", "count": 3},
            {"skill_tag": "sci_c1_animals_apply", "count": 3},
            {"skill_tag": "sci_c1_animals_represent", "count": 2},
            {"skill_tag": "sci_c1_animals_error", "count": 1},
            {"skill_tag": "sci_c1_animals_thinking", "count": 1},
        ],
    },
    "Food We Eat (Class 1)": {
        "allowed_skill_tags": [
            "sci_c1_food_identify", "sci_c1_food_apply", "sci_c1_food_represent",
            "sci_c1_food_error", "sci_c1_food_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product", "fraction", "decimal", "number line", "equation"],
        "disallowed_visual_types": [],
        "subject": "Science",
        "default_recipe": [
            {"skill_tag": "sci_c1_food_identify", "count": 3},
            {"skill_tag": "sci_c1_food_apply", "count": 3},
            {"skill_tag": "sci_c1_food_represent", "count": 2},
            {"skill_tag": "sci_c1_food_error", "count": 1},
            {"skill_tag": "sci_c1_food_thinking", "count": 1},
        ],
    },
    "Seasons and Weather (Class 1)": {
        "allowed_skill_tags": [
            "sci_c1_seasons_identify", "sci_c1_seasons_apply", "sci_c1_seasons_represent",
            "sci_c1_seasons_error", "sci_c1_seasons_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product", "fraction", "decimal", "number line", "equation"],
        "disallowed_visual_types": [],
        "subject": "Science",
        "default_recipe": [
            {"skill_tag": "sci_c1_seasons_identify", "count": 3},
            {"skill_tag": "sci_c1_seasons_apply", "count": 3},
            {"skill_tag": "sci_c1_seasons_represent", "count": 2},
            {"skill_tag": "sci_c1_seasons_error", "count": 1},
            {"skill_tag": "sci_c1_seasons_thinking", "count": 1},
        ],
    },
    # ════════════════════════════════════════════════════════════
    # ── EVS Class 2 (6 topics) ──
    # ════════════════════════════════════════════════════════════
    "Plants (Class 2)": {
        "allowed_skill_tags": [
            "sci_c2_plants_identify", "sci_c2_plants_apply", "sci_c2_plants_represent",
            "sci_c2_plants_error", "sci_c2_plants_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product", "fraction", "decimal", "number line", "equation"],
        "disallowed_visual_types": [],
        "subject": "Science",
        "default_recipe": [
            {"skill_tag": "sci_c2_plants_identify", "count": 3},
            {"skill_tag": "sci_c2_plants_apply", "count": 3},
            {"skill_tag": "sci_c2_plants_represent", "count": 2},
            {"skill_tag": "sci_c2_plants_error", "count": 1},
            {"skill_tag": "sci_c2_plants_thinking", "count": 1},
        ],
    },
    "Animals and Habitats (Class 2)": {
        "allowed_skill_tags": [
            "sci_c2_animals_identify", "sci_c2_animals_apply", "sci_c2_animals_represent",
            "sci_c2_animals_error", "sci_c2_animals_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product", "fraction", "decimal", "number line", "equation"],
        "disallowed_visual_types": [],
        "subject": "Science",
        "default_recipe": [
            {"skill_tag": "sci_c2_animals_identify", "count": 3},
            {"skill_tag": "sci_c2_animals_apply", "count": 3},
            {"skill_tag": "sci_c2_animals_represent", "count": 2},
            {"skill_tag": "sci_c2_animals_error", "count": 1},
            {"skill_tag": "sci_c2_animals_thinking", "count": 1},
        ],
    },
    "Food and Nutrition (Class 2)": {
        "allowed_skill_tags": [
            "sci_c2_food_identify", "sci_c2_food_apply", "sci_c2_food_represent",
            "sci_c2_food_error", "sci_c2_food_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product", "fraction", "decimal", "number line", "equation"],
        "disallowed_visual_types": [],
        "subject": "Science",
        "default_recipe": [
            {"skill_tag": "sci_c2_food_identify", "count": 3},
            {"skill_tag": "sci_c2_food_apply", "count": 3},
            {"skill_tag": "sci_c2_food_represent", "count": 2},
            {"skill_tag": "sci_c2_food_error", "count": 1},
            {"skill_tag": "sci_c2_food_thinking", "count": 1},
        ],
    },
    "Water (Class 2)": {
        "allowed_skill_tags": [
            "sci_c2_water_identify", "sci_c2_water_apply", "sci_c2_water_represent",
            "sci_c2_water_error", "sci_c2_water_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product", "fraction", "decimal", "number line", "equation"],
        "disallowed_visual_types": [],
        "subject": "Science",
        "default_recipe": [
            {"skill_tag": "sci_c2_water_identify", "count": 3},
            {"skill_tag": "sci_c2_water_apply", "count": 3},
            {"skill_tag": "sci_c2_water_represent", "count": 2},
            {"skill_tag": "sci_c2_water_error", "count": 1},
            {"skill_tag": "sci_c2_water_thinking", "count": 1},
        ],
    },
    "Shelter (Class 2)": {
        "allowed_skill_tags": [
            "sci_c2_shelter_identify", "sci_c2_shelter_apply", "sci_c2_shelter_represent",
            "sci_c2_shelter_error", "sci_c2_shelter_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product", "fraction", "decimal", "number line", "equation"],
        "disallowed_visual_types": [],
        "subject": "Science",
        "default_recipe": [
            {"skill_tag": "sci_c2_shelter_identify", "count": 3},
            {"skill_tag": "sci_c2_shelter_apply", "count": 3},
            {"skill_tag": "sci_c2_shelter_represent", "count": 2},
            {"skill_tag": "sci_c2_shelter_error", "count": 1},
            {"skill_tag": "sci_c2_shelter_thinking", "count": 1},
        ],
    },
    "Our Senses (Class 2)": {
        "allowed_skill_tags": [
            "sci_c2_senses_identify", "sci_c2_senses_apply", "sci_c2_senses_represent",
            "sci_c2_senses_error", "sci_c2_senses_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product", "fraction", "decimal", "number line", "equation"],
        "disallowed_visual_types": [],
        "subject": "Science",
        "default_recipe": [
            {"skill_tag": "sci_c2_senses_identify", "count": 3},
            {"skill_tag": "sci_c2_senses_apply", "count": 3},
            {"skill_tag": "sci_c2_senses_represent", "count": 2},
            {"skill_tag": "sci_c2_senses_error", "count": 1},
            {"skill_tag": "sci_c2_senses_thinking", "count": 1},
        ],
    },
    # ── Science Class 4 (7 topics) ──────────────────────────
    "Living Things (Class 4)": {
        "allowed_skill_tags": [
            "sci_c4_living_identify", "sci_c4_living_apply", "sci_c4_living_represent",
            "sci_c4_living_error", "sci_c4_living_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "compute", "sum", "difference"],
        "disallowed_visual_types": [],
        "subject": "Science",
        "default_recipe": [
            {"skill_tag": "sci_c4_living_identify", "count": 2},
            {"skill_tag": "sci_c4_living_apply", "count": 3},
            {"skill_tag": "sci_c4_living_represent", "count": 2},
            {"skill_tag": "sci_c4_living_error", "count": 2},
            {"skill_tag": "sci_c4_living_thinking", "count": 1},
        ],
    },
    "Human Body (Class 4)": {
        "allowed_skill_tags": [
            "sci_c4_humanbody_identify", "sci_c4_humanbody_apply", "sci_c4_humanbody_represent",
            "sci_c4_humanbody_error", "sci_c4_humanbody_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "compute", "sum", "difference"],
        "disallowed_visual_types": [],
        "subject": "Science",
        "default_recipe": [
            {"skill_tag": "sci_c4_humanbody_identify", "count": 2},
            {"skill_tag": "sci_c4_humanbody_apply", "count": 3},
            {"skill_tag": "sci_c4_humanbody_represent", "count": 2},
            {"skill_tag": "sci_c4_humanbody_error", "count": 2},
            {"skill_tag": "sci_c4_humanbody_thinking", "count": 1},
        ],
    },
    "States of Matter (Class 4)": {
        "allowed_skill_tags": [
            "sci_c4_matter_identify", "sci_c4_matter_apply", "sci_c4_matter_represent",
            "sci_c4_matter_error", "sci_c4_matter_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "compute", "sum", "difference"],
        "disallowed_visual_types": [],
        "subject": "Science",
        "default_recipe": [
            {"skill_tag": "sci_c4_matter_identify", "count": 2},
            {"skill_tag": "sci_c4_matter_apply", "count": 3},
            {"skill_tag": "sci_c4_matter_represent", "count": 2},
            {"skill_tag": "sci_c4_matter_error", "count": 2},
            {"skill_tag": "sci_c4_matter_thinking", "count": 1},
        ],
    },
    "Force and Motion (Class 4)": {
        "allowed_skill_tags": [
            "sci_c4_force_identify", "sci_c4_force_apply", "sci_c4_force_represent",
            "sci_c4_force_error", "sci_c4_force_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "compute", "sum", "difference"],
        "disallowed_visual_types": [],
        "subject": "Science",
        "default_recipe": [
            {"skill_tag": "sci_c4_force_identify", "count": 2},
            {"skill_tag": "sci_c4_force_apply", "count": 3},
            {"skill_tag": "sci_c4_force_represent", "count": 2},
            {"skill_tag": "sci_c4_force_error", "count": 2},
            {"skill_tag": "sci_c4_force_thinking", "count": 1},
        ],
    },
    "Simple Machines (Class 4)": {
        "allowed_skill_tags": [
            "sci_c4_machines_identify", "sci_c4_machines_apply", "sci_c4_machines_represent",
            "sci_c4_machines_error", "sci_c4_machines_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "compute", "sum", "difference"],
        "disallowed_visual_types": [],
        "subject": "Science",
        "default_recipe": [
            {"skill_tag": "sci_c4_machines_identify", "count": 2},
            {"skill_tag": "sci_c4_machines_apply", "count": 3},
            {"skill_tag": "sci_c4_machines_represent", "count": 2},
            {"skill_tag": "sci_c4_machines_error", "count": 2},
            {"skill_tag": "sci_c4_machines_thinking", "count": 1},
        ],
    },
    "Photosynthesis (Class 4)": {
        "allowed_skill_tags": [
            "sci_c4_photosyn_identify", "sci_c4_photosyn_apply", "sci_c4_photosyn_represent",
            "sci_c4_photosyn_error", "sci_c4_photosyn_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "compute", "sum", "difference"],
        "disallowed_visual_types": [],
        "subject": "Science",
        "default_recipe": [
            {"skill_tag": "sci_c4_photosyn_identify", "count": 2},
            {"skill_tag": "sci_c4_photosyn_apply", "count": 3},
            {"skill_tag": "sci_c4_photosyn_represent", "count": 2},
            {"skill_tag": "sci_c4_photosyn_error", "count": 2},
            {"skill_tag": "sci_c4_photosyn_thinking", "count": 1},
        ],
    },
    "Animal Adaptation (Class 4)": {
        "allowed_skill_tags": [
            "sci_c4_adapt_identify", "sci_c4_adapt_apply", "sci_c4_adapt_represent",
            "sci_c4_adapt_error", "sci_c4_adapt_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "compute", "sum", "difference"],
        "disallowed_visual_types": [],
        "subject": "Science",
        "default_recipe": [
            {"skill_tag": "sci_c4_adapt_identify", "count": 2},
            {"skill_tag": "sci_c4_adapt_apply", "count": 3},
            {"skill_tag": "sci_c4_adapt_represent", "count": 2},
            {"skill_tag": "sci_c4_adapt_error", "count": 2},
            {"skill_tag": "sci_c4_adapt_thinking", "count": 1},
        ],
    },
    # ── Science Class 5 (7 topics) ──────────────────────────
    "Circulatory System (Class 5)": {
        "allowed_skill_tags": [
            "sci_c5_circulatory_identify", "sci_c5_circulatory_apply", "sci_c5_circulatory_represent",
            "sci_c5_circulatory_error", "sci_c5_circulatory_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "compute", "sum", "difference"],
        "disallowed_visual_types": [],
        "subject": "Science",
        "default_recipe": [
            {"skill_tag": "sci_c5_circulatory_identify", "count": 2},
            {"skill_tag": "sci_c5_circulatory_apply", "count": 3},
            {"skill_tag": "sci_c5_circulatory_represent", "count": 2},
            {"skill_tag": "sci_c5_circulatory_error", "count": 2},
            {"skill_tag": "sci_c5_circulatory_thinking", "count": 1},
        ],
    },
    "Respiratory and Nervous System (Class 5)": {
        "allowed_skill_tags": [
            "sci_c5_respnerv_identify", "sci_c5_respnerv_apply", "sci_c5_respnerv_represent",
            "sci_c5_respnerv_error", "sci_c5_respnerv_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "compute", "sum", "difference"],
        "disallowed_visual_types": [],
        "subject": "Science",
        "default_recipe": [
            {"skill_tag": "sci_c5_respnerv_identify", "count": 2},
            {"skill_tag": "sci_c5_respnerv_apply", "count": 3},
            {"skill_tag": "sci_c5_respnerv_represent", "count": 2},
            {"skill_tag": "sci_c5_respnerv_error", "count": 2},
            {"skill_tag": "sci_c5_respnerv_thinking", "count": 1},
        ],
    },
    "Reproduction in Plants and Animals (Class 5)": {
        "allowed_skill_tags": [
            "sci_c5_reprod_identify", "sci_c5_reprod_apply", "sci_c5_reprod_represent",
            "sci_c5_reprod_error", "sci_c5_reprod_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "compute", "sum", "difference"],
        "disallowed_visual_types": [],
        "subject": "Science",
        "default_recipe": [
            {"skill_tag": "sci_c5_reprod_identify", "count": 2},
            {"skill_tag": "sci_c5_reprod_apply", "count": 3},
            {"skill_tag": "sci_c5_reprod_represent", "count": 2},
            {"skill_tag": "sci_c5_reprod_error", "count": 2},
            {"skill_tag": "sci_c5_reprod_thinking", "count": 1},
        ],
    },
    "Physical and Chemical Changes (Class 5)": {
        "allowed_skill_tags": [
            "sci_c5_changes_identify", "sci_c5_changes_apply", "sci_c5_changes_represent",
            "sci_c5_changes_error", "sci_c5_changes_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "compute", "sum", "difference"],
        "disallowed_visual_types": [],
        "subject": "Science",
        "default_recipe": [
            {"skill_tag": "sci_c5_changes_identify", "count": 2},
            {"skill_tag": "sci_c5_changes_apply", "count": 3},
            {"skill_tag": "sci_c5_changes_represent", "count": 2},
            {"skill_tag": "sci_c5_changes_error", "count": 2},
            {"skill_tag": "sci_c5_changes_thinking", "count": 1},
        ],
    },
    "Forms of Energy (Class 5)": {
        "allowed_skill_tags": [
            "sci_c5_energy_identify", "sci_c5_energy_apply", "sci_c5_energy_represent",
            "sci_c5_energy_error", "sci_c5_energy_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "compute", "sum", "difference"],
        "disallowed_visual_types": [],
        "subject": "Science",
        "default_recipe": [
            {"skill_tag": "sci_c5_energy_identify", "count": 2},
            {"skill_tag": "sci_c5_energy_apply", "count": 3},
            {"skill_tag": "sci_c5_energy_represent", "count": 2},
            {"skill_tag": "sci_c5_energy_error", "count": 2},
            {"skill_tag": "sci_c5_energy_thinking", "count": 1},
        ],
    },
    "Solar System and Earth (Class 5)": {
        "allowed_skill_tags": [
            "sci_c5_solar_identify", "sci_c5_solar_apply", "sci_c5_solar_represent",
            "sci_c5_solar_error", "sci_c5_solar_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "compute", "sum", "difference"],
        "disallowed_visual_types": [],
        "subject": "Science",
        "default_recipe": [
            {"skill_tag": "sci_c5_solar_identify", "count": 2},
            {"skill_tag": "sci_c5_solar_apply", "count": 3},
            {"skill_tag": "sci_c5_solar_represent", "count": 2},
            {"skill_tag": "sci_c5_solar_error", "count": 2},
            {"skill_tag": "sci_c5_solar_thinking", "count": 1},
        ],
    },
    "Ecosystem and Food Chains (Class 5)": {
        "allowed_skill_tags": [
            "sci_c5_ecosystem_identify", "sci_c5_ecosystem_apply", "sci_c5_ecosystem_represent",
            "sci_c5_ecosystem_error", "sci_c5_ecosystem_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "compute", "sum", "difference"],
        "disallowed_visual_types": [],
        "subject": "Science",
        "default_recipe": [
            {"skill_tag": "sci_c5_ecosystem_identify", "count": 2},
            {"skill_tag": "sci_c5_ecosystem_apply", "count": 3},
            {"skill_tag": "sci_c5_ecosystem_represent", "count": 2},
            {"skill_tag": "sci_c5_ecosystem_error", "count": 2},
            {"skill_tag": "sci_c5_ecosystem_thinking", "count": 1},
        ],
    },
    # ── Hindi Class 3 topic profiles ──────────────────────────
    "Varnamala (Class 3)": {
        "allowed_skill_tags": [
            "hin_varna_identify", "hin_varna_use", "hin_varna_complete",
            "hin_varna_error", "hin_varna_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product", "fraction"],
        "disallowed_visual_types": [],
        "subject": "Hindi",
        "default_recipe": [
            {"skill_tag": "hin_varna_identify", "count": 3},
            {"skill_tag": "hin_varna_use", "count": 3},
            {"skill_tag": "hin_varna_complete", "count": 2},
            {"skill_tag": "hin_varna_error", "count": 1},
            {"skill_tag": "hin_varna_thinking", "count": 1},
        ],
    },
    "Matras (Class 3)": {
        "allowed_skill_tags": [
            "hin_matra_identify", "hin_matra_fill", "hin_matra_complete",
            "hin_matra_error", "hin_matra_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product", "fraction"],
        "disallowed_visual_types": [],
        "subject": "Hindi",
        "default_recipe": [
            {"skill_tag": "hin_matra_identify", "count": 3},
            {"skill_tag": "hin_matra_fill", "count": 3},
            {"skill_tag": "hin_matra_complete", "count": 2},
            {"skill_tag": "hin_matra_error", "count": 1},
            {"skill_tag": "hin_matra_thinking", "count": 1},
        ],
    },
    "Shabd Rachna (Class 3)": {
        "allowed_skill_tags": [
            "hin_shabd_identify", "hin_shabd_make", "hin_shabd_complete",
            "hin_shabd_error", "hin_shabd_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product", "fraction"],
        "disallowed_visual_types": [],
        "subject": "Hindi",
        "default_recipe": [
            {"skill_tag": "hin_shabd_identify", "count": 3},
            {"skill_tag": "hin_shabd_make", "count": 3},
            {"skill_tag": "hin_shabd_complete", "count": 2},
            {"skill_tag": "hin_shabd_error", "count": 1},
            {"skill_tag": "hin_shabd_thinking", "count": 1},
        ],
    },
    "Vakya Rachna (Class 3)": {
        "allowed_skill_tags": [
            "hin_vakya_identify", "hin_vakya_make", "hin_vakya_rearrange",
            "hin_vakya_error", "hin_vakya_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product", "fraction"],
        "disallowed_visual_types": [],
        "subject": "Hindi",
        "default_recipe": [
            {"skill_tag": "hin_vakya_identify", "count": 3},
            {"skill_tag": "hin_vakya_make", "count": 3},
            {"skill_tag": "hin_vakya_rearrange", "count": 2},
            {"skill_tag": "hin_vakya_error", "count": 1},
            {"skill_tag": "hin_vakya_thinking", "count": 1},
        ],
    },
    "Kahani Lekhan (Class 3)": {
        "allowed_skill_tags": [
            "hin_kahani_identify", "hin_kahani_answer", "hin_kahani_complete",
            "hin_kahani_error", "hin_kahani_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "sum", "difference", "product", "fraction"],
        "disallowed_visual_types": [],
        "subject": "Hindi",
        "default_recipe": [
            {"skill_tag": "hin_kahani_identify", "count": 3},
            {"skill_tag": "hin_kahani_answer", "count": 3},
            {"skill_tag": "hin_kahani_complete", "count": 2},
            {"skill_tag": "hin_kahani_error", "count": 1},
            {"skill_tag": "hin_kahani_thinking", "count": 1},
        ],
    },
    # ── Computer Science Class 1 (2 topics) ──────────────────────────
    "Parts of Computer (Class 1)": {
        "allowed_skill_tags": [
            "comp_c1_parts_identify", "comp_c1_parts_apply", "comp_c1_parts_represent",
            "comp_c1_parts_error", "comp_c1_parts_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "Computer",
        "default_recipe": [
            {"skill_tag": "comp_c1_parts_identify", "count": 2},
            {"skill_tag": "comp_c1_parts_apply", "count": 3},
            {"skill_tag": "comp_c1_parts_represent", "count": 2},
            {"skill_tag": "comp_c1_parts_error", "count": 2},
            {"skill_tag": "comp_c1_parts_thinking", "count": 1},
        ],
    },
    "Using Mouse and Keyboard (Class 1)": {
        "allowed_skill_tags": [
            "comp_c1_mouse_identify", "comp_c1_mouse_apply", "comp_c1_mouse_represent",
            "comp_c1_mouse_error", "comp_c1_mouse_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "Computer",
        "default_recipe": [
            {"skill_tag": "comp_c1_mouse_identify", "count": 2},
            {"skill_tag": "comp_c1_mouse_apply", "count": 3},
            {"skill_tag": "comp_c1_mouse_represent", "count": 2},
            {"skill_tag": "comp_c1_mouse_error", "count": 2},
            {"skill_tag": "comp_c1_mouse_thinking", "count": 1},
        ],
    },
    # ── Computer Science Class 2 (3 topics) ──────────────────────────
    "Desktop and Icons (Class 2)": {
        "allowed_skill_tags": [
            "comp_c2_desktop_identify", "comp_c2_desktop_apply", "comp_c2_desktop_represent",
            "comp_c2_desktop_error", "comp_c2_desktop_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "Computer",
        "default_recipe": [
            {"skill_tag": "comp_c2_desktop_identify", "count": 2},
            {"skill_tag": "comp_c2_desktop_apply", "count": 3},
            {"skill_tag": "comp_c2_desktop_represent", "count": 2},
            {"skill_tag": "comp_c2_desktop_error", "count": 2},
            {"skill_tag": "comp_c2_desktop_thinking", "count": 1},
        ],
    },
    "Basic Typing (Class 2)": {
        "allowed_skill_tags": [
            "comp_c2_typing_identify", "comp_c2_typing_apply", "comp_c2_typing_represent",
            "comp_c2_typing_error", "comp_c2_typing_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "Computer",
        "default_recipe": [
            {"skill_tag": "comp_c2_typing_identify", "count": 2},
            {"skill_tag": "comp_c2_typing_apply", "count": 3},
            {"skill_tag": "comp_c2_typing_represent", "count": 2},
            {"skill_tag": "comp_c2_typing_error", "count": 2},
            {"skill_tag": "comp_c2_typing_thinking", "count": 1},
        ],
    },
    "Special Keys (Class 2)": {
        "allowed_skill_tags": [
            "comp_c2_special_identify", "comp_c2_special_apply", "comp_c2_special_represent",
            "comp_c2_special_error", "comp_c2_special_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "Computer",
        "default_recipe": [
            {"skill_tag": "comp_c2_special_identify", "count": 2},
            {"skill_tag": "comp_c2_special_apply", "count": 3},
            {"skill_tag": "comp_c2_special_represent", "count": 2},
            {"skill_tag": "comp_c2_special_error", "count": 2},
            {"skill_tag": "comp_c2_special_thinking", "count": 1},
        ],
    },
    # ── Computer Science Class 3 (3 topics) ──────────────────────────
    "MS Paint Basics (Class 3)": {
        "allowed_skill_tags": [
            "comp_c3_paint_identify", "comp_c3_paint_apply", "comp_c3_paint_represent",
            "comp_c3_paint_error", "comp_c3_paint_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "Computer",
        "default_recipe": [
            {"skill_tag": "comp_c3_paint_identify", "count": 2},
            {"skill_tag": "comp_c3_paint_apply", "count": 3},
            {"skill_tag": "comp_c3_paint_represent", "count": 2},
            {"skill_tag": "comp_c3_paint_error", "count": 2},
            {"skill_tag": "comp_c3_paint_thinking", "count": 1},
        ],
    },
    "Keyboard Shortcuts (Class 3)": {
        "allowed_skill_tags": [
            "comp_c3_shortcuts_identify", "comp_c3_shortcuts_apply", "comp_c3_shortcuts_represent",
            "comp_c3_shortcuts_error", "comp_c3_shortcuts_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "Computer",
        "default_recipe": [
            {"skill_tag": "comp_c3_shortcuts_identify", "count": 2},
            {"skill_tag": "comp_c3_shortcuts_apply", "count": 3},
            {"skill_tag": "comp_c3_shortcuts_represent", "count": 2},
            {"skill_tag": "comp_c3_shortcuts_error", "count": 2},
            {"skill_tag": "comp_c3_shortcuts_thinking", "count": 1},
        ],
    },
    "Files and Folders (Class 3)": {
        "allowed_skill_tags": [
            "comp_c3_files_identify", "comp_c3_files_apply", "comp_c3_files_represent",
            "comp_c3_files_error", "comp_c3_files_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "Computer",
        "default_recipe": [
            {"skill_tag": "comp_c3_files_identify", "count": 2},
            {"skill_tag": "comp_c3_files_apply", "count": 3},
            {"skill_tag": "comp_c3_files_represent", "count": 2},
            {"skill_tag": "comp_c3_files_error", "count": 2},
            {"skill_tag": "comp_c3_files_thinking", "count": 1},
        ],
    },
    # ── Computer Science Class 4 (3 topics) ──────────────────────────
    "MS Word Basics (Class 4)": {
        "allowed_skill_tags": [
            "comp_c4_word_identify", "comp_c4_word_apply", "comp_c4_word_represent",
            "comp_c4_word_error", "comp_c4_word_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "Computer",
        "default_recipe": [
            {"skill_tag": "comp_c4_word_identify", "count": 2},
            {"skill_tag": "comp_c4_word_apply", "count": 3},
            {"skill_tag": "comp_c4_word_represent", "count": 2},
            {"skill_tag": "comp_c4_word_error", "count": 2},
            {"skill_tag": "comp_c4_word_thinking", "count": 1},
        ],
    },
    "Introduction to Scratch (Class 4)": {
        "allowed_skill_tags": [
            "comp_c4_scratch_identify", "comp_c4_scratch_apply", "comp_c4_scratch_represent",
            "comp_c4_scratch_error", "comp_c4_scratch_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "Computer",
        "default_recipe": [
            {"skill_tag": "comp_c4_scratch_identify", "count": 2},
            {"skill_tag": "comp_c4_scratch_apply", "count": 3},
            {"skill_tag": "comp_c4_scratch_represent", "count": 2},
            {"skill_tag": "comp_c4_scratch_error", "count": 2},
            {"skill_tag": "comp_c4_scratch_thinking", "count": 1},
        ],
    },
    "Internet Safety (Class 4)": {
        "allowed_skill_tags": [
            "comp_c4_safety_identify", "comp_c4_safety_apply", "comp_c4_safety_represent",
            "comp_c4_safety_error", "comp_c4_safety_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "Computer",
        "default_recipe": [
            {"skill_tag": "comp_c4_safety_identify", "count": 2},
            {"skill_tag": "comp_c4_safety_apply", "count": 3},
            {"skill_tag": "comp_c4_safety_represent", "count": 2},
            {"skill_tag": "comp_c4_safety_error", "count": 2},
            {"skill_tag": "comp_c4_safety_thinking", "count": 1},
        ],
    },
    # ── Computer Science Class 5 (4 topics) ──────────────────────────
    "Scratch Programming (Class 5)": {
        "allowed_skill_tags": [
            "comp_c5_scratch_identify", "comp_c5_scratch_apply", "comp_c5_scratch_represent",
            "comp_c5_scratch_error", "comp_c5_scratch_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "Computer",
        "default_recipe": [
            {"skill_tag": "comp_c5_scratch_identify", "count": 2},
            {"skill_tag": "comp_c5_scratch_apply", "count": 3},
            {"skill_tag": "comp_c5_scratch_represent", "count": 2},
            {"skill_tag": "comp_c5_scratch_error", "count": 2},
            {"skill_tag": "comp_c5_scratch_thinking", "count": 1},
        ],
    },
    "Internet Basics (Class 5)": {
        "allowed_skill_tags": [
            "comp_c5_internet_identify", "comp_c5_internet_apply", "comp_c5_internet_represent",
            "comp_c5_internet_error", "comp_c5_internet_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "Computer",
        "default_recipe": [
            {"skill_tag": "comp_c5_internet_identify", "count": 2},
            {"skill_tag": "comp_c5_internet_apply", "count": 3},
            {"skill_tag": "comp_c5_internet_represent", "count": 2},
            {"skill_tag": "comp_c5_internet_error", "count": 2},
            {"skill_tag": "comp_c5_internet_thinking", "count": 1},
        ],
    },
    "MS PowerPoint Basics (Class 5)": {
        "allowed_skill_tags": [
            "comp_c5_ppt_identify", "comp_c5_ppt_apply", "comp_c5_ppt_represent",
            "comp_c5_ppt_error", "comp_c5_ppt_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "Computer",
        "default_recipe": [
            {"skill_tag": "comp_c5_ppt_identify", "count": 2},
            {"skill_tag": "comp_c5_ppt_apply", "count": 3},
            {"skill_tag": "comp_c5_ppt_represent", "count": 2},
            {"skill_tag": "comp_c5_ppt_error", "count": 2},
            {"skill_tag": "comp_c5_ppt_thinking", "count": 1},
        ],
    },
    "Digital Citizenship (Class 5)": {
        "allowed_skill_tags": [
            "comp_c5_digital_identify", "comp_c5_digital_apply", "comp_c5_digital_represent",
            "comp_c5_digital_error", "comp_c5_digital_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "Computer",
        "default_recipe": [
            {"skill_tag": "comp_c5_digital_identify", "count": 2},
            {"skill_tag": "comp_c5_digital_apply", "count": 3},
            {"skill_tag": "comp_c5_digital_represent", "count": 2},
            {"skill_tag": "comp_c5_digital_error", "count": 2},
            {"skill_tag": "comp_c5_digital_thinking", "count": 1},
        ],
    },
    # ── General Knowledge Class 3 (4 topics) ──────────────────────────
    "Famous Landmarks (Class 3)": {
        "allowed_skill_tags": [
            "gk_c3_landmarks_identify", "gk_c3_landmarks_apply", "gk_c3_landmarks_represent",
            "gk_c3_landmarks_error", "gk_c3_landmarks_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "GK",
        "default_recipe": [
            {"skill_tag": "gk_c3_landmarks_identify", "count": 2},
            {"skill_tag": "gk_c3_landmarks_apply", "count": 3},
            {"skill_tag": "gk_c3_landmarks_represent", "count": 2},
            {"skill_tag": "gk_c3_landmarks_error", "count": 2},
            {"skill_tag": "gk_c3_landmarks_thinking", "count": 1},
        ],
    },
    "National Symbols (Class 3)": {
        "allowed_skill_tags": [
            "gk_c3_symbols_identify", "gk_c3_symbols_apply", "gk_c3_symbols_represent",
            "gk_c3_symbols_error", "gk_c3_symbols_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "GK",
        "default_recipe": [
            {"skill_tag": "gk_c3_symbols_identify", "count": 2},
            {"skill_tag": "gk_c3_symbols_apply", "count": 3},
            {"skill_tag": "gk_c3_symbols_represent", "count": 2},
            {"skill_tag": "gk_c3_symbols_error", "count": 2},
            {"skill_tag": "gk_c3_symbols_thinking", "count": 1},
        ],
    },
    "Solar System Basics (Class 3)": {
        "allowed_skill_tags": [
            "gk_c3_solar_identify", "gk_c3_solar_apply", "gk_c3_solar_represent",
            "gk_c3_solar_error", "gk_c3_solar_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "GK",
        "default_recipe": [
            {"skill_tag": "gk_c3_solar_identify", "count": 2},
            {"skill_tag": "gk_c3_solar_apply", "count": 3},
            {"skill_tag": "gk_c3_solar_represent", "count": 2},
            {"skill_tag": "gk_c3_solar_error", "count": 2},
            {"skill_tag": "gk_c3_solar_thinking", "count": 1},
        ],
    },
    "Current Awareness (Class 3)": {
        "allowed_skill_tags": [
            "gk_c3_current_identify", "gk_c3_current_apply", "gk_c3_current_represent",
            "gk_c3_current_error", "gk_c3_current_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "GK",
        "default_recipe": [
            {"skill_tag": "gk_c3_current_identify", "count": 2},
            {"skill_tag": "gk_c3_current_apply", "count": 3},
            {"skill_tag": "gk_c3_current_represent", "count": 2},
            {"skill_tag": "gk_c3_current_error", "count": 2},
            {"skill_tag": "gk_c3_current_thinking", "count": 1},
        ],
    },
    # ── General Knowledge Class 4 (4 topics) ──────────────────────────
    "Continents and Oceans (Class 4)": {
        "allowed_skill_tags": [
            "gk_c4_continents_identify", "gk_c4_continents_apply", "gk_c4_continents_represent",
            "gk_c4_continents_error", "gk_c4_continents_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "GK",
        "default_recipe": [
            {"skill_tag": "gk_c4_continents_identify", "count": 2},
            {"skill_tag": "gk_c4_continents_apply", "count": 3},
            {"skill_tag": "gk_c4_continents_represent", "count": 2},
            {"skill_tag": "gk_c4_continents_error", "count": 2},
            {"skill_tag": "gk_c4_continents_thinking", "count": 1},
        ],
    },
    "Famous Scientists (Class 4)": {
        "allowed_skill_tags": [
            "gk_c4_scientists_identify", "gk_c4_scientists_apply", "gk_c4_scientists_represent",
            "gk_c4_scientists_error", "gk_c4_scientists_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "GK",
        "default_recipe": [
            {"skill_tag": "gk_c4_scientists_identify", "count": 2},
            {"skill_tag": "gk_c4_scientists_apply", "count": 3},
            {"skill_tag": "gk_c4_scientists_represent", "count": 2},
            {"skill_tag": "gk_c4_scientists_error", "count": 2},
            {"skill_tag": "gk_c4_scientists_thinking", "count": 1},
        ],
    },
    "Festivals of India (Class 4)": {
        "allowed_skill_tags": [
            "gk_c4_festivals_identify", "gk_c4_festivals_apply", "gk_c4_festivals_represent",
            "gk_c4_festivals_error", "gk_c4_festivals_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "GK",
        "default_recipe": [
            {"skill_tag": "gk_c4_festivals_identify", "count": 2},
            {"skill_tag": "gk_c4_festivals_apply", "count": 3},
            {"skill_tag": "gk_c4_festivals_represent", "count": 2},
            {"skill_tag": "gk_c4_festivals_error", "count": 2},
            {"skill_tag": "gk_c4_festivals_thinking", "count": 1},
        ],
    },
    "Sports and Games (Class 4)": {
        "allowed_skill_tags": [
            "gk_c4_sports_identify", "gk_c4_sports_apply", "gk_c4_sports_represent",
            "gk_c4_sports_error", "gk_c4_sports_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "GK",
        "default_recipe": [
            {"skill_tag": "gk_c4_sports_identify", "count": 2},
            {"skill_tag": "gk_c4_sports_apply", "count": 3},
            {"skill_tag": "gk_c4_sports_represent", "count": 2},
            {"skill_tag": "gk_c4_sports_error", "count": 2},
            {"skill_tag": "gk_c4_sports_thinking", "count": 1},
        ],
    },
    # ── General Knowledge Class 5 (4 topics) ──────────────────────────
    "Indian Constitution (Class 5)": {
        "allowed_skill_tags": [
            "gk_c5_constitution_identify", "gk_c5_constitution_apply", "gk_c5_constitution_represent",
            "gk_c5_constitution_error", "gk_c5_constitution_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "GK",
        "default_recipe": [
            {"skill_tag": "gk_c5_constitution_identify", "count": 2},
            {"skill_tag": "gk_c5_constitution_apply", "count": 3},
            {"skill_tag": "gk_c5_constitution_represent", "count": 2},
            {"skill_tag": "gk_c5_constitution_error", "count": 2},
            {"skill_tag": "gk_c5_constitution_thinking", "count": 1},
        ],
    },
    "World Heritage Sites (Class 5)": {
        "allowed_skill_tags": [
            "gk_c5_heritage_identify", "gk_c5_heritage_apply", "gk_c5_heritage_represent",
            "gk_c5_heritage_error", "gk_c5_heritage_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "GK",
        "default_recipe": [
            {"skill_tag": "gk_c5_heritage_identify", "count": 2},
            {"skill_tag": "gk_c5_heritage_apply", "count": 3},
            {"skill_tag": "gk_c5_heritage_represent", "count": 2},
            {"skill_tag": "gk_c5_heritage_error", "count": 2},
            {"skill_tag": "gk_c5_heritage_thinking", "count": 1},
        ],
    },
    "Space Missions (Class 5)": {
        "allowed_skill_tags": [
            "gk_c5_space_identify", "gk_c5_space_apply", "gk_c5_space_represent",
            "gk_c5_space_error", "gk_c5_space_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "GK",
        "default_recipe": [
            {"skill_tag": "gk_c5_space_identify", "count": 2},
            {"skill_tag": "gk_c5_space_apply", "count": 3},
            {"skill_tag": "gk_c5_space_represent", "count": 2},
            {"skill_tag": "gk_c5_space_error", "count": 2},
            {"skill_tag": "gk_c5_space_thinking", "count": 1},
        ],
    },
    "Environmental Awareness (Class 5)": {
        "allowed_skill_tags": [
            "gk_c5_environment_identify", "gk_c5_environment_apply", "gk_c5_environment_represent",
            "gk_c5_environment_error", "gk_c5_environment_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "GK",
        "default_recipe": [
            {"skill_tag": "gk_c5_environment_identify", "count": 2},
            {"skill_tag": "gk_c5_environment_apply", "count": 3},
            {"skill_tag": "gk_c5_environment_represent", "count": 2},
            {"skill_tag": "gk_c5_environment_error", "count": 2},
            {"skill_tag": "gk_c5_environment_thinking", "count": 1},
        ],
    },
    # ── Moral Science Class 1 (2 topics) ──────────────────────────
    "Sharing (Class 1)": {
        "allowed_skill_tags": [
            "moral_c1_sharing_identify", "moral_c1_sharing_apply", "moral_c1_sharing_represent",
            "moral_c1_sharing_error", "moral_c1_sharing_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "Moral Science",
        "default_recipe": [
            {"skill_tag": "moral_c1_sharing_identify", "count": 2},
            {"skill_tag": "moral_c1_sharing_apply", "count": 3},
            {"skill_tag": "moral_c1_sharing_represent", "count": 2},
            {"skill_tag": "moral_c1_sharing_error", "count": 2},
            {"skill_tag": "moral_c1_sharing_thinking", "count": 1},
        ],
    },
    "Honesty (Class 1)": {
        "allowed_skill_tags": [
            "moral_c1_honesty_identify", "moral_c1_honesty_apply", "moral_c1_honesty_represent",
            "moral_c1_honesty_error", "moral_c1_honesty_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "Moral Science",
        "default_recipe": [
            {"skill_tag": "moral_c1_honesty_identify", "count": 2},
            {"skill_tag": "moral_c1_honesty_apply", "count": 3},
            {"skill_tag": "moral_c1_honesty_represent", "count": 2},
            {"skill_tag": "moral_c1_honesty_error", "count": 2},
            {"skill_tag": "moral_c1_honesty_thinking", "count": 1},
        ],
    },
    # ── Moral Science Class 2 (2 topics) ──────────────────────────
    "Kindness (Class 2)": {
        "allowed_skill_tags": [
            "moral_c2_kindness_identify", "moral_c2_kindness_apply", "moral_c2_kindness_represent",
            "moral_c2_kindness_error", "moral_c2_kindness_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "Moral Science",
        "default_recipe": [
            {"skill_tag": "moral_c2_kindness_identify", "count": 2},
            {"skill_tag": "moral_c2_kindness_apply", "count": 3},
            {"skill_tag": "moral_c2_kindness_represent", "count": 2},
            {"skill_tag": "moral_c2_kindness_error", "count": 2},
            {"skill_tag": "moral_c2_kindness_thinking", "count": 1},
        ],
    },
    "Respecting Elders (Class 2)": {
        "allowed_skill_tags": [
            "moral_c2_respect_identify", "moral_c2_respect_apply", "moral_c2_respect_represent",
            "moral_c2_respect_error", "moral_c2_respect_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "Moral Science",
        "default_recipe": [
            {"skill_tag": "moral_c2_respect_identify", "count": 2},
            {"skill_tag": "moral_c2_respect_apply", "count": 3},
            {"skill_tag": "moral_c2_respect_represent", "count": 2},
            {"skill_tag": "moral_c2_respect_error", "count": 2},
            {"skill_tag": "moral_c2_respect_thinking", "count": 1},
        ],
    },
    # ── Moral Science Class 3 (3 topics) ──────────────────────────
    "Teamwork (Class 3)": {
        "allowed_skill_tags": [
            "moral_c3_teamwork_identify", "moral_c3_teamwork_apply", "moral_c3_teamwork_represent",
            "moral_c3_teamwork_error", "moral_c3_teamwork_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "Moral Science",
        "default_recipe": [
            {"skill_tag": "moral_c3_teamwork_identify", "count": 2},
            {"skill_tag": "moral_c3_teamwork_apply", "count": 3},
            {"skill_tag": "moral_c3_teamwork_represent", "count": 2},
            {"skill_tag": "moral_c3_teamwork_error", "count": 2},
            {"skill_tag": "moral_c3_teamwork_thinking", "count": 1},
        ],
    },
    "Empathy (Class 3)": {
        "allowed_skill_tags": [
            "moral_c3_empathy_identify", "moral_c3_empathy_apply", "moral_c3_empathy_represent",
            "moral_c3_empathy_error", "moral_c3_empathy_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "Moral Science",
        "default_recipe": [
            {"skill_tag": "moral_c3_empathy_identify", "count": 2},
            {"skill_tag": "moral_c3_empathy_apply", "count": 3},
            {"skill_tag": "moral_c3_empathy_represent", "count": 2},
            {"skill_tag": "moral_c3_empathy_error", "count": 2},
            {"skill_tag": "moral_c3_empathy_thinking", "count": 1},
        ],
    },
    "Environmental Care (Class 3)": {
        "allowed_skill_tags": [
            "moral_c3_envcare_identify", "moral_c3_envcare_apply", "moral_c3_envcare_represent",
            "moral_c3_envcare_error", "moral_c3_envcare_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "Moral Science",
        "default_recipe": [
            {"skill_tag": "moral_c3_envcare_identify", "count": 2},
            {"skill_tag": "moral_c3_envcare_apply", "count": 3},
            {"skill_tag": "moral_c3_envcare_represent", "count": 2},
            {"skill_tag": "moral_c3_envcare_error", "count": 2},
            {"skill_tag": "moral_c3_envcare_thinking", "count": 1},
        ],
    },
    # ── Moral Science Class 4 (1 topic) ──────────────────────────
    "Leadership (Class 4)": {
        "allowed_skill_tags": [
            "moral_c4_leadership_identify", "moral_c4_leadership_apply", "moral_c4_leadership_represent",
            "moral_c4_leadership_error", "moral_c4_leadership_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "Moral Science",
        "default_recipe": [
            {"skill_tag": "moral_c4_leadership_identify", "count": 2},
            {"skill_tag": "moral_c4_leadership_apply", "count": 3},
            {"skill_tag": "moral_c4_leadership_represent", "count": 2},
            {"skill_tag": "moral_c4_leadership_error", "count": 2},
            {"skill_tag": "moral_c4_leadership_thinking", "count": 1},
        ],
    },
    # ── Moral Science Class 5 (2 topics) ──────────────────────────
    "Global Citizenship (Class 5)": {
        "allowed_skill_tags": [
            "moral_c5_global_identify", "moral_c5_global_apply", "moral_c5_global_represent",
            "moral_c5_global_error", "moral_c5_global_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "Moral Science",
        "default_recipe": [
            {"skill_tag": "moral_c5_global_identify", "count": 2},
            {"skill_tag": "moral_c5_global_apply", "count": 3},
            {"skill_tag": "moral_c5_global_represent", "count": 2},
            {"skill_tag": "moral_c5_global_error", "count": 2},
            {"skill_tag": "moral_c5_global_thinking", "count": 1},
        ],
    },
    "Digital Ethics (Class 5)": {
        "allowed_skill_tags": [
            "moral_c5_digital_identify", "moral_c5_digital_apply", "moral_c5_digital_represent",
            "moral_c5_digital_error", "moral_c5_digital_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "Moral Science",
        "default_recipe": [
            {"skill_tag": "moral_c5_digital_identify", "count": 2},
            {"skill_tag": "moral_c5_digital_apply", "count": 3},
            {"skill_tag": "moral_c5_digital_represent", "count": 2},
            {"skill_tag": "moral_c5_digital_error", "count": 2},
            {"skill_tag": "moral_c5_digital_thinking", "count": 1},
        ],
    },
    # ── Health & Physical Education Class 1 (3 topics) ──────────────────────────
    "Personal Hygiene (Class 1)": {
        "allowed_skill_tags": [
            "health_c1_hygiene_identify", "health_c1_hygiene_apply", "health_c1_hygiene_represent",
            "health_c1_hygiene_error", "health_c1_hygiene_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "Health",
        "default_recipe": [
            {"skill_tag": "health_c1_hygiene_identify", "count": 2},
            {"skill_tag": "health_c1_hygiene_apply", "count": 3},
            {"skill_tag": "health_c1_hygiene_represent", "count": 2},
            {"skill_tag": "health_c1_hygiene_error", "count": 2},
            {"skill_tag": "health_c1_hygiene_thinking", "count": 1},
        ],
    },
    "Good Posture (Class 1)": {
        "allowed_skill_tags": [
            "health_c1_posture_identify", "health_c1_posture_apply", "health_c1_posture_represent",
            "health_c1_posture_error", "health_c1_posture_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "Health",
        "default_recipe": [
            {"skill_tag": "health_c1_posture_identify", "count": 2},
            {"skill_tag": "health_c1_posture_apply", "count": 3},
            {"skill_tag": "health_c1_posture_represent", "count": 2},
            {"skill_tag": "health_c1_posture_error", "count": 2},
            {"skill_tag": "health_c1_posture_thinking", "count": 1},
        ],
    },
    "Basic Physical Activities (Class 1)": {
        "allowed_skill_tags": [
            "health_c1_physical_identify", "health_c1_physical_apply", "health_c1_physical_represent",
            "health_c1_physical_error", "health_c1_physical_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "Health",
        "default_recipe": [
            {"skill_tag": "health_c1_physical_identify", "count": 2},
            {"skill_tag": "health_c1_physical_apply", "count": 3},
            {"skill_tag": "health_c1_physical_represent", "count": 2},
            {"skill_tag": "health_c1_physical_error", "count": 2},
            {"skill_tag": "health_c1_physical_thinking", "count": 1},
        ],
    },
    # ── Health & Physical Education Class 2 (3 topics) ──────────────────────────
    "Healthy Eating Habits (Class 2)": {
        "allowed_skill_tags": [
            "health_c2_eating_identify", "health_c2_eating_apply", "health_c2_eating_represent",
            "health_c2_eating_error", "health_c2_eating_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "Health",
        "default_recipe": [
            {"skill_tag": "health_c2_eating_identify", "count": 2},
            {"skill_tag": "health_c2_eating_apply", "count": 3},
            {"skill_tag": "health_c2_eating_represent", "count": 2},
            {"skill_tag": "health_c2_eating_error", "count": 2},
            {"skill_tag": "health_c2_eating_thinking", "count": 1},
        ],
    },
    "Outdoor Play (Class 2)": {
        "allowed_skill_tags": [
            "health_c2_outdoor_identify", "health_c2_outdoor_apply", "health_c2_outdoor_represent",
            "health_c2_outdoor_error", "health_c2_outdoor_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "Health",
        "default_recipe": [
            {"skill_tag": "health_c2_outdoor_identify", "count": 2},
            {"skill_tag": "health_c2_outdoor_apply", "count": 3},
            {"skill_tag": "health_c2_outdoor_represent", "count": 2},
            {"skill_tag": "health_c2_outdoor_error", "count": 2},
            {"skill_tag": "health_c2_outdoor_thinking", "count": 1},
        ],
    },
    "Basic Stretching (Class 2)": {
        "allowed_skill_tags": [
            "health_c2_stretching_identify", "health_c2_stretching_apply", "health_c2_stretching_represent",
            "health_c2_stretching_error", "health_c2_stretching_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "Health",
        "default_recipe": [
            {"skill_tag": "health_c2_stretching_identify", "count": 2},
            {"skill_tag": "health_c2_stretching_apply", "count": 3},
            {"skill_tag": "health_c2_stretching_represent", "count": 2},
            {"skill_tag": "health_c2_stretching_error", "count": 2},
            {"skill_tag": "health_c2_stretching_thinking", "count": 1},
        ],
    },
    # ── Health & Physical Education Class 3 (3 topics) ──────────────────────────
    "Balanced Diet (Class 3)": {
        "allowed_skill_tags": [
            "health_c3_diet_identify", "health_c3_diet_apply", "health_c3_diet_represent",
            "health_c3_diet_error", "health_c3_diet_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "Health",
        "default_recipe": [
            {"skill_tag": "health_c3_diet_identify", "count": 2},
            {"skill_tag": "health_c3_diet_apply", "count": 3},
            {"skill_tag": "health_c3_diet_represent", "count": 2},
            {"skill_tag": "health_c3_diet_error", "count": 2},
            {"skill_tag": "health_c3_diet_thinking", "count": 1},
        ],
    },
    "Team Sports Rules (Class 3)": {
        "allowed_skill_tags": [
            "health_c3_sports_identify", "health_c3_sports_apply", "health_c3_sports_represent",
            "health_c3_sports_error", "health_c3_sports_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "Health",
        "default_recipe": [
            {"skill_tag": "health_c3_sports_identify", "count": 2},
            {"skill_tag": "health_c3_sports_apply", "count": 3},
            {"skill_tag": "health_c3_sports_represent", "count": 2},
            {"skill_tag": "health_c3_sports_error", "count": 2},
            {"skill_tag": "health_c3_sports_thinking", "count": 1},
        ],
    },
    "Safety at Play (Class 3)": {
        "allowed_skill_tags": [
            "health_c3_safety_identify", "health_c3_safety_apply", "health_c3_safety_represent",
            "health_c3_safety_error", "health_c3_safety_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "Health",
        "default_recipe": [
            {"skill_tag": "health_c3_safety_identify", "count": 2},
            {"skill_tag": "health_c3_safety_apply", "count": 3},
            {"skill_tag": "health_c3_safety_represent", "count": 2},
            {"skill_tag": "health_c3_safety_error", "count": 2},
            {"skill_tag": "health_c3_safety_thinking", "count": 1},
        ],
    },
    # ── Health & Physical Education Class 4 (3 topics) ──────────────────────────
    "First Aid Basics (Class 4)": {
        "allowed_skill_tags": [
            "health_c4_firstaid_identify", "health_c4_firstaid_apply", "health_c4_firstaid_represent",
            "health_c4_firstaid_error", "health_c4_firstaid_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "Health",
        "default_recipe": [
            {"skill_tag": "health_c4_firstaid_identify", "count": 2},
            {"skill_tag": "health_c4_firstaid_apply", "count": 3},
            {"skill_tag": "health_c4_firstaid_represent", "count": 2},
            {"skill_tag": "health_c4_firstaid_error", "count": 2},
            {"skill_tag": "health_c4_firstaid_thinking", "count": 1},
        ],
    },
    "Yoga Introduction (Class 4)": {
        "allowed_skill_tags": [
            "health_c4_yoga_identify", "health_c4_yoga_apply", "health_c4_yoga_represent",
            "health_c4_yoga_error", "health_c4_yoga_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "Health",
        "default_recipe": [
            {"skill_tag": "health_c4_yoga_identify", "count": 2},
            {"skill_tag": "health_c4_yoga_apply", "count": 3},
            {"skill_tag": "health_c4_yoga_represent", "count": 2},
            {"skill_tag": "health_c4_yoga_error", "count": 2},
            {"skill_tag": "health_c4_yoga_thinking", "count": 1},
        ],
    },
    "Importance of Sleep (Class 4)": {
        "allowed_skill_tags": [
            "health_c4_sleep_identify", "health_c4_sleep_apply", "health_c4_sleep_represent",
            "health_c4_sleep_error", "health_c4_sleep_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "Health",
        "default_recipe": [
            {"skill_tag": "health_c4_sleep_identify", "count": 2},
            {"skill_tag": "health_c4_sleep_apply", "count": 3},
            {"skill_tag": "health_c4_sleep_represent", "count": 2},
            {"skill_tag": "health_c4_sleep_error", "count": 2},
            {"skill_tag": "health_c4_sleep_thinking", "count": 1},
        ],
    },
    # ── Health & Physical Education Class 5 (3 topics) ──────────────────────────
    "Fitness and Stamina (Class 5)": {
        "allowed_skill_tags": [
            "health_c5_fitness_identify", "health_c5_fitness_apply", "health_c5_fitness_represent",
            "health_c5_fitness_error", "health_c5_fitness_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "Health",
        "default_recipe": [
            {"skill_tag": "health_c5_fitness_identify", "count": 2},
            {"skill_tag": "health_c5_fitness_apply", "count": 3},
            {"skill_tag": "health_c5_fitness_represent", "count": 2},
            {"skill_tag": "health_c5_fitness_error", "count": 2},
            {"skill_tag": "health_c5_fitness_thinking", "count": 1},
        ],
    },
    "Nutrition Labels Reading (Class 5)": {
        "allowed_skill_tags": [
            "health_c5_nutrition_identify", "health_c5_nutrition_apply", "health_c5_nutrition_represent",
            "health_c5_nutrition_error", "health_c5_nutrition_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "Health",
        "default_recipe": [
            {"skill_tag": "health_c5_nutrition_identify", "count": 2},
            {"skill_tag": "health_c5_nutrition_apply", "count": 3},
            {"skill_tag": "health_c5_nutrition_represent", "count": 2},
            {"skill_tag": "health_c5_nutrition_error", "count": 2},
            {"skill_tag": "health_c5_nutrition_thinking", "count": 1},
        ],
    },
    "Mental Health Awareness (Class 5)": {
        "allowed_skill_tags": [
            "health_c5_mental_identify", "health_c5_mental_apply", "health_c5_mental_represent",
            "health_c5_mental_error", "health_c5_mental_thinking",
        ],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["add", "subtract", "multiply", "divide", "calculate", "fraction", "decimal"],
        "disallowed_visual_types": [],
        "subject": "Health",
        "default_recipe": [
            {"skill_tag": "health_c5_mental_identify", "count": 2},
            {"skill_tag": "health_c5_mental_apply", "count": 3},
            {"skill_tag": "health_c5_mental_represent", "count": 2},
            {"skill_tag": "health_c5_mental_error", "count": 2},
            {"skill_tag": "health_c5_mental_thinking", "count": 1},
        ],
    },
}


def normalize_topic(topic: str) -> str:
    return (topic or "").strip()


# Fuzzy aliases: frontend may send short names like "Multiplication"
# but TOPIC_PROFILES uses full names like "Multiplication (tables 2-10)"
_TOPIC_ALIASES: dict[str, str] = {
    "addition": "Addition (carries)",
    "subtraction": "Subtraction (borrowing)",
    "addition and subtraction": "Addition and subtraction (3-digit)",
    "add/sub": "Addition and subtraction (3-digit)",
    "multiplication": "Multiplication (tables 2-10)",
    "division": "Division basics",
    "fractions": "Fractions",
    "time": "Time (reading clock, calendar)",
    "money": "Money (bills and change)",
    "symmetry": "Symmetry",
    "patterns": "Patterns and sequences",
    "numbers": "Numbers up to 10000",
    "place value": "Numbers up to 10000",
    # Class 1 aliases
    "numbers 1 to 50": "Numbers 1 to 50 (Class 1)",
    "counting to 50": "Numbers 1 to 50 (Class 1)",
    "c1 numbers small": "Numbers 1 to 50 (Class 1)",
    "class 1 numbers small": "Numbers 1 to 50 (Class 1)",
    "numbers 51 to 100": "Numbers 51 to 100 (Class 1)",
    "counting to 100": "Numbers 51 to 100 (Class 1)",
    "c1 numbers big": "Numbers 51 to 100 (Class 1)",
    "class 1 numbers big": "Numbers 51 to 100 (Class 1)",
    "addition up to 20": "Addition up to 20 (Class 1)",
    "c1 addition": "Addition up to 20 (Class 1)",
    "class 1 addition": "Addition up to 20 (Class 1)",
    "add up to 20": "Addition up to 20 (Class 1)",
    "subtraction within 20": "Subtraction within 20 (Class 1)",
    "c1 subtraction": "Subtraction within 20 (Class 1)",
    "class 1 subtraction": "Subtraction within 20 (Class 1)",
    "subtract within 20": "Subtraction within 20 (Class 1)",
    "basic shapes": "Basic Shapes (Class 1)",
    "c1 shapes": "Basic Shapes (Class 1)",
    "class 1 shapes": "Basic Shapes (Class 1)",
    "measurement class 1": "Measurement (Class 1)",
    "c1 measurement": "Measurement (Class 1)",
    "class 1 measurement": "Measurement (Class 1)",
    "compare lengths": "Measurement (Class 1)",
    "time class 1": "Time (Class 1)",
    "c1 time": "Time (Class 1)",
    "class 1 time": "Time (Class 1)",
    "day routines": "Time (Class 1)",
    "money class 1": "Money (Class 1)",
    "c1 money": "Money (Class 1)",
    "class 1 money": "Money (Class 1)",
    "coins": "Money (Class 1)",
    # Class 2 aliases
    "class 2 numbers": "Numbers up to 1000 (Class 2)",
    "class 2 addition": "Addition (2-digit with carry)",
    "class 2 subtraction": "Subtraction (2-digit with borrow)",
    "class 2 multiplication": "Multiplication (tables 2-5)",
    "class 2 division": "Division (sharing equally)",
    "class 2 shapes": "Shapes and space (2D)",
    "class 2 measurement": "Measurement (length, weight)",
    "class 2 time": "Time (hour, half-hour)",
    "class 2 money": "Money (coins and notes)",
    "class 2 data handling": "Data handling (pictographs)",
    "class 2 data": "Data handling (pictographs)",
    "c2 numbers": "Numbers up to 1000 (Class 2)",
    "c2 addition": "Addition (2-digit with carry)",
    "c2 subtraction": "Subtraction (2-digit with borrow)",
    "c2 multiplication": "Multiplication (tables 2-5)",
    "c2 division": "Division (sharing equally)",
    "c2 shapes": "Shapes and space (2D)",
    "c2 measurement": "Measurement (length, weight)",
    "c2 time": "Time (hour, half-hour)",
    "c2 money": "Money (coins and notes)",
    "c2 data": "Data handling (pictographs)",
    "sharing equally": "Division (sharing equally)",
    "pictographs": "Data handling (pictographs)",
    "2d shapes": "Shapes and space (2D)",
    "shapes 2d": "Shapes and space (2D)",
    "length weight": "Measurement (length, weight)",
    # Class 4 aliases
    "class 4 large numbers": "Large numbers (up to 1,00,000)",
    "c4 large numbers": "Large numbers (up to 1,00,000)",
    "large numbers": "Large numbers (up to 1,00,000)",
    "numbers up to 100000": "Large numbers (up to 1,00,000)",
    "class 4 addition subtraction": "Addition and subtraction (5-digit)",
    "class 4 add/sub": "Addition and subtraction (5-digit)",
    "c4 add/sub": "Addition and subtraction (5-digit)",
    "5-digit addition": "Addition and subtraction (5-digit)",
    "class 4 multiplication": "Multiplication (3-digit × 2-digit)",
    "c4 multiplication": "Multiplication (3-digit × 2-digit)",
    "multi-digit multiplication": "Multiplication (3-digit × 2-digit)",
    "class 4 division": "Division (long division)",
    "c4 division": "Division (long division)",
    "long division": "Division (long division)",
    "class 4 fractions": "Fractions (equivalent, comparison)",
    "c4 fractions": "Fractions (equivalent, comparison)",
    "equivalent fractions": "Fractions (equivalent, comparison)",
    "class 4 decimals": "Decimals (tenths, hundredths)",
    "c4 decimals": "Decimals (tenths, hundredths)",
    "decimals": "Decimals (tenths, hundredths)",
    "class 4 geometry": "Geometry (angles, lines)",
    "c4 geometry": "Geometry (angles, lines)",
    "angles and lines": "Geometry (angles, lines)",
    "class 4 perimeter": "Perimeter and area",
    "c4 perimeter": "Perimeter and area",
    "perimeter and area": "Perimeter and area",
    "perimeter": "Perimeter and area",
    "area": "Perimeter and area",
    "class 4 time": "Time (minutes, 24-hour clock)",
    "c4 time": "Time (minutes, 24-hour clock)",
    "24-hour clock": "Time (minutes, 24-hour clock)",
    "class 4 money": "Money (bills, profit/loss)",
    "c4 money": "Money (bills, profit/loss)",
    "profit and loss": "Money (bills, profit/loss)",
    "profit/loss": "Money (bills, profit/loss)",
    # Class 5 aliases
    "class 5 numbers": "Numbers up to 10 lakh (Class 5)",
    "c5 numbers": "Numbers up to 10 lakh (Class 5)",
    "numbers up to 10 lakh": "Numbers up to 10 lakh (Class 5)",
    "lakhs": "Numbers up to 10 lakh (Class 5)",
    "class 5 factors": "Factors and multiples (Class 5)",
    "c5 factors": "Factors and multiples (Class 5)",
    "factors and multiples": "Factors and multiples (Class 5)",
    "prime numbers": "Factors and multiples (Class 5)",
    "class 5 hcf lcm": "HCF and LCM (Class 5)",
    "c5 hcf": "HCF and LCM (Class 5)",
    "hcf and lcm": "HCF and LCM (Class 5)",
    "hcf": "HCF and LCM (Class 5)",
    "lcm": "HCF and LCM (Class 5)",
    "class 5 fractions": "Fractions (add and subtract) (Class 5)",
    "c5 fractions": "Fractions (add and subtract) (Class 5)",
    "add subtract fractions": "Fractions (add and subtract) (Class 5)",
    "fraction addition": "Fractions (add and subtract) (Class 5)",
    "class 5 decimals": "Decimals (all operations) (Class 5)",
    "c5 decimals": "Decimals (all operations) (Class 5)",
    "decimal operations": "Decimals (all operations) (Class 5)",
    "class 5 percentage": "Percentage (Class 5)",
    "c5 percentage": "Percentage (Class 5)",
    "percentage": "Percentage (Class 5)",
    "percent": "Percentage (Class 5)",
    "class 5 area volume": "Area and volume (Class 5)",
    "c5 area": "Area and volume (Class 5)",
    "area and volume": "Area and volume (Class 5)",
    "volume": "Area and volume (Class 5)",
    "class 5 geometry": "Geometry (circles, symmetry) (Class 5)",
    "c5 geometry": "Geometry (circles, symmetry) (Class 5)",
    "circles and symmetry": "Geometry (circles, symmetry) (Class 5)",
    "class 5 data": "Data handling (pie charts) (Class 5)",
    "c5 data": "Data handling (pie charts) (Class 5)",
    "pie charts": "Data handling (pie charts) (Class 5)",
    "class 5 speed": "Speed distance time (Class 5)",
    "c5 speed": "Speed distance time (Class 5)",
    "speed distance time": "Speed distance time (Class 5)",
    "speed time distance": "Speed distance time (Class 5)",
    # ── English Language aliases ──
    # ── Class 1 English aliases ──
    "alphabet": "Alphabet (Class 1)",
    "class 1 alphabet": "Alphabet (Class 1)",
    "c1 alphabet": "Alphabet (Class 1)",
    "abc": "Alphabet (Class 1)",
    "phonics": "Phonics (Class 1)",
    "class 1 phonics": "Phonics (Class 1)",
    "c1 phonics": "Phonics (Class 1)",
    "letter sounds": "Phonics (Class 1)",
    "self and family vocabulary": "Self and Family Vocabulary (Class 1)",
    "class 1 family": "Self and Family Vocabulary (Class 1)",
    "c1 family": "Self and Family Vocabulary (Class 1)",
    "family vocabulary": "Self and Family Vocabulary (Class 1)",
    "animals and food vocabulary": "Animals and Food Vocabulary (Class 1)",
    "class 1 animals": "Animals and Food Vocabulary (Class 1)",
    "c1 animals": "Animals and Food Vocabulary (Class 1)",
    "animals and food": "Animals and Food Vocabulary (Class 1)",
    "greetings and polite words": "Greetings and Polite Words (Class 1)",
    "class 1 greetings": "Greetings and Polite Words (Class 1)",
    "c1 greetings": "Greetings and Polite Words (Class 1)",
    "polite words": "Greetings and Polite Words (Class 1)",
    "seasons": "Seasons (Class 1)",
    "class 1 seasons": "Seasons (Class 1)",
    "c1 seasons": "Seasons (Class 1)",
    "simple sentences": "Simple Sentences (Class 1)",
    "class 1 sentences": "Simple Sentences (Class 1)",
    "c1 sentences": "Simple Sentences (Class 1)",
    "class 1 simple sentences": "Simple Sentences (Class 1)",
    # ── Class 2+ English aliases ──
    "nouns": "Nouns (Class 3)",
    "verbs": "Verbs (Class 3)",
    "adjectives": "Adjectives (Class 3)",
    "pronouns": "Pronouns (Class 3)",
    "tenses": "Tenses (Class 3)",
    "punctuation": "Punctuation (Class 3)",
    "vocabulary": "Vocabulary (Class 3)",
    "reading comprehension": "Reading Comprehension (Class 3)",
    "comprehension": "Reading Comprehension (Class 3)",
    "conjunctions": "Conjunctions (Class 4)",
    "prepositions": "Prepositions (Class 4)",
    "adverbs": "Adverbs (Class 4)",
    "prefixes and suffixes": "Prefixes and Suffixes (Class 4)",
    "prefixes": "Prefixes and Suffixes (Class 4)",
    "suffixes": "Prefixes and Suffixes (Class 4)",
    "sentence types": "Sentence Types (Class 4)",
    "rhyming words": "Rhyming Words (Class 2)",
    "rhyming": "Rhyming Words (Class 2)",
    "sentences": "Sentences (Class 2)",
    "class 2 nouns": "Nouns (Class 2)",
    "class 2 verbs": "Verbs (Class 2)",
    "class 2 pronouns": "Pronouns (Class 2)",
    "class 2 sentences": "Sentences (Class 2)",
    "class 2 rhyming": "Rhyming Words (Class 2)",
    "class 2 punctuation": "Punctuation (Class 2)",
    "class 3 nouns": "Nouns (Class 3)",
    "class 3 verbs": "Verbs (Class 3)",
    "class 3 adjectives": "Adjectives (Class 3)",
    "class 3 pronouns": "Pronouns (Class 3)",
    "class 3 tenses": "Tenses (Class 3)",
    "class 3 punctuation": "Punctuation (Class 3)",
    "class 3 vocabulary": "Vocabulary (Class 3)",
    "class 3 comprehension": "Reading Comprehension (Class 3)",
    "class 4 tenses": "Tenses (Class 4)",
    "class 4 sentence types": "Sentence Types (Class 4)",
    "class 4 conjunctions": "Conjunctions (Class 4)",
    "class 4 prepositions": "Prepositions (Class 4)",
    "class 4 adverbs": "Adverbs (Class 4)",
    "class 4 prefixes": "Prefixes and Suffixes (Class 4)",
    "class 4 vocabulary": "Vocabulary (Class 4)",
    "class 4 comprehension": "Reading Comprehension (Class 4)",
    # ── Class 5 English aliases ──
    "active and passive voice": "Active and Passive Voice (Class 5)",
    "class 5 voice": "Active and Passive Voice (Class 5)",
    "c5 voice": "Active and Passive Voice (Class 5)",
    "active passive": "Active and Passive Voice (Class 5)",
    "direct and indirect speech": "Direct and Indirect Speech (Class 5)",
    "class 5 speech": "Direct and Indirect Speech (Class 5)",
    "c5 speech": "Direct and Indirect Speech (Class 5)",
    "reported speech": "Direct and Indirect Speech (Class 5)",
    "complex sentences": "Complex Sentences (Class 5)",
    "class 5 complex sentences": "Complex Sentences (Class 5)",
    "c5 complex sentences": "Complex Sentences (Class 5)",
    "summary writing": "Summary Writing (Class 5)",
    "class 5 summary": "Summary Writing (Class 5)",
    "c5 summary": "Summary Writing (Class 5)",
    "class 5 comprehension": "Comprehension (Class 5)",
    "c5 comprehension": "Comprehension (Class 5)",
    "class 5 reading comprehension": "Comprehension (Class 5)",
    "synonyms and antonyms": "Synonyms and Antonyms (Class 5)",
    "class 5 synonyms": "Synonyms and Antonyms (Class 5)",
    "c5 synonyms": "Synonyms and Antonyms (Class 5)",
    "class 5 antonyms": "Synonyms and Antonyms (Class 5)",
    "formal letter writing": "Formal Letter Writing (Class 5)",
    "class 5 letter writing": "Formal Letter Writing (Class 5)",
    "c5 letter writing": "Formal Letter Writing (Class 5)",
    "formal letter": "Formal Letter Writing (Class 5)",
    "creative writing": "Creative Writing (Class 5)",
    "class 5 creative writing": "Creative Writing (Class 5)",
    "c5 creative writing": "Creative Writing (Class 5)",
    "clauses": "Clauses (Class 5)",
    "class 5 clauses": "Clauses (Class 5)",
    "c5 clauses": "Clauses (Class 5)",
    "main and subordinate clauses": "Clauses (Class 5)",
    # ── Science Class 3 aliases ──
    "plants": "Plants (Class 3)",
    "class 3 plants": "Plants (Class 3)",
    "parts of a plant": "Plants (Class 3)",
    "animals": "Animals (Class 3)",
    "class 3 animals": "Animals (Class 3)",
    "animal habitats": "Animals (Class 3)",
    "food and nutrition": "Food and Nutrition (Class 3)",
    "class 3 food": "Food and Nutrition (Class 3)",
    "food groups": "Food and Nutrition (Class 3)",
    "nutrition": "Food and Nutrition (Class 3)",
    "balanced diet": "Food and Nutrition (Class 3)",
    "shelter": "Shelter (Class 3)",
    "class 3 shelter": "Shelter (Class 3)",
    "houses and shelters": "Shelter (Class 3)",
    "water": "Water (Class 3)",
    "class 3 water": "Water (Class 3)",
    "sources of water": "Water (Class 3)",
    "water cycle": "Water (Class 3)",
    "air": "Air (Class 3)",
    "class 3 air": "Air (Class 3)",
    "air around us": "Air (Class 3)",
    "our body": "Our Body (Class 3)",
    "class 3 body": "Our Body (Class 3)",
    "human body": "Our Body (Class 3)",
    "body parts": "Our Body (Class 3)",
    # ── EVS Class 1 aliases ──
    "my family": "My Family (Class 1)",
    "c1 my family": "My Family (Class 1)",
    "c1 family evs": "My Family (Class 1)",
    "class 1 family evs": "My Family (Class 1)",
    "my body": "My Body (Class 1)",
    "c1 my body": "My Body (Class 1)",
    "c1 body evs": "My Body (Class 1)",
    "class 1 body evs": "My Body (Class 1)",
    "plants around us": "Plants Around Us (Class 1)",
    "c1 plants": "Plants Around Us (Class 1)",
    "class 1 plants": "Plants Around Us (Class 1)",
    "c1 plants evs": "Plants Around Us (Class 1)",
    "animals around us": "Animals Around Us (Class 1)",
    "c1 animals": "Animals Around Us (Class 1)",
    "class 1 animals": "Animals Around Us (Class 1)",
    "c1 animals evs": "Animals Around Us (Class 1)",
    "food we eat": "Food We Eat (Class 1)",
    "c1 food": "Food We Eat (Class 1)",
    "class 1 food": "Food We Eat (Class 1)",
    "c1 food evs": "Food We Eat (Class 1)",
    "seasons and weather": "Seasons and Weather (Class 1)",
    "c1 seasons": "Seasons and Weather (Class 1)",
    "c1 weather": "Seasons and Weather (Class 1)",
    "class 1 weather": "Seasons and Weather (Class 1)",
    # ── EVS Class 2 aliases ──
    "c2 plants": "Plants (Class 2)",
    "class 2 plants": "Plants (Class 2)",
    "c2 plants evs": "Plants (Class 2)",
    "animals and habitats": "Animals and Habitats (Class 2)",
    "c2 animals": "Animals and Habitats (Class 2)",
    "class 2 animals": "Animals and Habitats (Class 2)",
    "c2 habitats": "Animals and Habitats (Class 2)",
    "food and nutrition class 2": "Food and Nutrition (Class 2)",
    "c2 food": "Food and Nutrition (Class 2)",
    "class 2 food": "Food and Nutrition (Class 2)",
    "c2 nutrition": "Food and Nutrition (Class 2)",
    "water class 2": "Water (Class 2)",
    "c2 water": "Water (Class 2)",
    "class 2 water": "Water (Class 2)",
    "c2 water evs": "Water (Class 2)",
    "shelter class 2": "Shelter (Class 2)",
    "c2 shelter": "Shelter (Class 2)",
    "class 2 shelter": "Shelter (Class 2)",
    "c2 shelter evs": "Shelter (Class 2)",
    "our senses": "Our Senses (Class 2)",
    "c2 senses": "Our Senses (Class 2)",
    "class 2 senses": "Our Senses (Class 2)",
    "five senses": "Our Senses (Class 2)",
    # ── Science Class 4 aliases ──
    "living things": "Living Things (Class 4)",
    "class 4 living things": "Living Things (Class 4)",
    "c4 living things": "Living Things (Class 4)",
    "living and nonliving": "Living Things (Class 4)",
    "living and non-living": "Living Things (Class 4)",
    "human body class 4": "Human Body (Class 4)",
    "class 4 human body": "Human Body (Class 4)",
    "c4 human body": "Human Body (Class 4)",
    "digestive system": "Human Body (Class 4)",
    "skeletal system": "Human Body (Class 4)",
    "states of matter": "States of Matter (Class 4)",
    "class 4 matter": "States of Matter (Class 4)",
    "c4 matter": "States of Matter (Class 4)",
    "solid liquid gas": "States of Matter (Class 4)",
    "force and motion": "Force and Motion (Class 4)",
    "class 4 force": "Force and Motion (Class 4)",
    "c4 force": "Force and Motion (Class 4)",
    "push and pull": "Force and Motion (Class 4)",
    "friction": "Force and Motion (Class 4)",
    "simple machines": "Simple Machines (Class 4)",
    "class 4 machines": "Simple Machines (Class 4)",
    "c4 machines": "Simple Machines (Class 4)",
    "lever and pulley": "Simple Machines (Class 4)",
    "photosynthesis": "Photosynthesis (Class 4)",
    "class 4 photosynthesis": "Photosynthesis (Class 4)",
    "c4 photosynthesis": "Photosynthesis (Class 4)",
    "how plants make food": "Photosynthesis (Class 4)",
    "animal adaptation": "Animal Adaptation (Class 4)",
    "class 4 adaptation": "Animal Adaptation (Class 4)",
    "c4 adaptation": "Animal Adaptation (Class 4)",
    "animal adaptations": "Animal Adaptation (Class 4)",
    "desert aquatic polar": "Animal Adaptation (Class 4)",
    # ── Science Class 5 aliases ──
    "circulatory system": "Circulatory System (Class 5)",
    "class 5 circulatory": "Circulatory System (Class 5)",
    "c5 circulatory": "Circulatory System (Class 5)",
    "heart and blood": "Circulatory System (Class 5)",
    "blood circulation": "Circulatory System (Class 5)",
    "respiratory and nervous system": "Respiratory and Nervous System (Class 5)",
    "class 5 respiratory": "Respiratory and Nervous System (Class 5)",
    "c5 respiratory": "Respiratory and Nervous System (Class 5)",
    "lungs and brain": "Respiratory and Nervous System (Class 5)",
    "nervous system": "Respiratory and Nervous System (Class 5)",
    "reproduction in plants and animals": "Reproduction in Plants and Animals (Class 5)",
    "class 5 reproduction": "Reproduction in Plants and Animals (Class 5)",
    "c5 reproduction": "Reproduction in Plants and Animals (Class 5)",
    "pollination and seeds": "Reproduction in Plants and Animals (Class 5)",
    "physical and chemical changes": "Physical and Chemical Changes (Class 5)",
    "class 5 changes": "Physical and Chemical Changes (Class 5)",
    "c5 changes": "Physical and Chemical Changes (Class 5)",
    "reversible irreversible": "Physical and Chemical Changes (Class 5)",
    "chemical changes": "Physical and Chemical Changes (Class 5)",
    "forms of energy": "Forms of Energy (Class 5)",
    "class 5 energy": "Forms of Energy (Class 5)",
    "c5 energy": "Forms of Energy (Class 5)",
    "heat light sound": "Forms of Energy (Class 5)",
    "solar system and earth": "Solar System and Earth (Class 5)",
    "class 5 solar system": "Solar System and Earth (Class 5)",
    "c5 solar system": "Solar System and Earth (Class 5)",
    "planets and earth": "Solar System and Earth (Class 5)",
    "solar system": "Solar System and Earth (Class 5)",
    "ecosystem and food chains": "Ecosystem and Food Chains (Class 5)",
    "class 5 ecosystem": "Ecosystem and Food Chains (Class 5)",
    "c5 ecosystem": "Ecosystem and Food Chains (Class 5)",
    "food chains": "Ecosystem and Food Chains (Class 5)",
    "food web": "Ecosystem and Food Chains (Class 5)",
    # ── Hindi Class 3 aliases ──
    "varnamala": "Varnamala (Class 3)",
    "class 3 varnamala": "Varnamala (Class 3)",
    "hindi alphabet": "Varnamala (Class 3)",
    "hindi varnamala": "Varnamala (Class 3)",
    "matras": "Matras (Class 3)",
    "class 3 matras": "Matras (Class 3)",
    "hindi matras": "Matras (Class 3)",
    "vowel signs": "Matras (Class 3)",
    "shabd rachna": "Shabd Rachna (Class 3)",
    "class 3 shabd rachna": "Shabd Rachna (Class 3)",
    "word formation hindi": "Shabd Rachna (Class 3)",
    "hindi word formation": "Shabd Rachna (Class 3)",
    "vakya rachna": "Vakya Rachna (Class 3)",
    "class 3 vakya rachna": "Vakya Rachna (Class 3)",
    "sentence formation hindi": "Vakya Rachna (Class 3)",
    "hindi sentence formation": "Vakya Rachna (Class 3)",
    "kahani lekhan": "Kahani Lekhan (Class 3)",
    "class 3 kahani lekhan": "Kahani Lekhan (Class 3)",
    "hindi story": "Kahani Lekhan (Class 3)",
    "hindi stories": "Kahani Lekhan (Class 3)",
    "hindi comprehension": "Kahani Lekhan (Class 3)",
    # ── Computer Science aliases ──
    "parts of computer": "Parts of Computer (Class 1)",
    "class 1 parts of computer": "Parts of Computer (Class 1)",
    "computer parts": "Parts of Computer (Class 1)",
    "computer parts class 1": "Parts of Computer (Class 1)",
    "using mouse and keyboard": "Using Mouse and Keyboard (Class 1)",
    "class 1 mouse and keyboard": "Using Mouse and Keyboard (Class 1)",
    "mouse and keyboard": "Using Mouse and Keyboard (Class 1)",
    "mouse keyboard": "Using Mouse and Keyboard (Class 1)",
    "desktop and icons": "Desktop and Icons (Class 2)",
    "class 2 desktop and icons": "Desktop and Icons (Class 2)",
    "desktop icons": "Desktop and Icons (Class 2)",
    "basic typing": "Basic Typing (Class 2)",
    "class 2 basic typing": "Basic Typing (Class 2)",
    "typing basics": "Basic Typing (Class 2)",
    "typing class 2": "Basic Typing (Class 2)",
    "special keys": "Special Keys (Class 2)",
    "class 2 special keys": "Special Keys (Class 2)",
    "keyboard special keys": "Special Keys (Class 2)",
    "ms paint basics": "MS Paint Basics (Class 3)",
    "class 3 ms paint": "MS Paint Basics (Class 3)",
    "ms paint": "MS Paint Basics (Class 3)",
    "paint basics": "MS Paint Basics (Class 3)",
    "keyboard shortcuts": "Keyboard Shortcuts (Class 3)",
    "class 3 keyboard shortcuts": "Keyboard Shortcuts (Class 3)",
    "shortcuts": "Keyboard Shortcuts (Class 3)",
    "files and folders": "Files and Folders (Class 3)",
    "class 3 files and folders": "Files and Folders (Class 3)",
    "file management": "Files and Folders (Class 3)",
    "ms word basics": "MS Word Basics (Class 4)",
    "class 4 ms word": "MS Word Basics (Class 4)",
    "ms word": "MS Word Basics (Class 4)",
    "word basics": "MS Word Basics (Class 4)",
    "introduction to scratch": "Introduction to Scratch (Class 4)",
    "class 4 scratch": "Introduction to Scratch (Class 4)",
    "scratch class 4": "Introduction to Scratch (Class 4)",
    "scratch intro": "Introduction to Scratch (Class 4)",
    "internet safety": "Internet Safety (Class 4)",
    "class 4 internet safety": "Internet Safety (Class 4)",
    "online safety": "Internet Safety (Class 4)",
    "cyber safety": "Internet Safety (Class 4)",
    "scratch programming": "Scratch Programming (Class 5)",
    "class 5 scratch": "Scratch Programming (Class 5)",
    "scratch class 5": "Scratch Programming (Class 5)",
    "advanced scratch": "Scratch Programming (Class 5)",
    "internet basics": "Internet Basics (Class 5)",
    "class 5 internet": "Internet Basics (Class 5)",
    "internet class 5": "Internet Basics (Class 5)",
    "ms powerpoint basics": "MS PowerPoint Basics (Class 5)",
    "class 5 powerpoint": "MS PowerPoint Basics (Class 5)",
    "powerpoint basics": "MS PowerPoint Basics (Class 5)",
    "ms powerpoint": "MS PowerPoint Basics (Class 5)",
    "ppt basics": "MS PowerPoint Basics (Class 5)",
    "digital citizenship": "Digital Citizenship (Class 5)",
    "class 5 digital citizenship": "Digital Citizenship (Class 5)",
    "digital citizen": "Digital Citizenship (Class 5)",
    "online etiquette": "Digital Citizenship (Class 5)",
    # ── General Knowledge aliases ──────────────────────────
    "famous landmarks": "Famous Landmarks (Class 3)",
    "class 3 landmarks": "Famous Landmarks (Class 3)",
    "landmarks": "Famous Landmarks (Class 3)",
    "monuments": "Famous Landmarks (Class 3)",
    "national symbols": "National Symbols (Class 3)",
    "class 3 national symbols": "National Symbols (Class 3)",
    "indian symbols": "National Symbols (Class 3)",
    "national flag": "National Symbols (Class 3)",
    "solar system basics": "Solar System Basics (Class 3)",
    "class 3 solar system": "Solar System Basics (Class 3)",
    "solar system": "Solar System Basics (Class 3)",
    "planets": "Solar System Basics (Class 3)",
    "current awareness": "Current Awareness (Class 3)",
    "class 3 current awareness": "Current Awareness (Class 3)",
    "festivals and seasons": "Current Awareness (Class 3)",
    "important days": "Current Awareness (Class 3)",
    "continents and oceans": "Continents and Oceans (Class 4)",
    "class 4 continents": "Continents and Oceans (Class 4)",
    "continents": "Continents and Oceans (Class 4)",
    "oceans": "Continents and Oceans (Class 4)",
    "famous scientists": "Famous Scientists (Class 4)",
    "class 4 scientists": "Famous Scientists (Class 4)",
    "scientists": "Famous Scientists (Class 4)",
    "inventions": "Famous Scientists (Class 4)",
    "festivals of india": "Festivals of India (Class 4)",
    "class 4 festivals": "Festivals of India (Class 4)",
    "indian festivals": "Festivals of India (Class 4)",
    "sports and games": "Sports and Games (Class 4)",
    "class 4 sports": "Sports and Games (Class 4)",
    "sports": "Sports and Games (Class 4)",
    "indian sports": "Sports and Games (Class 4)",
    "indian constitution": "Indian Constitution (Class 5)",
    "class 5 constitution": "Indian Constitution (Class 5)",
    "constitution": "Indian Constitution (Class 5)",
    "fundamental rights": "Indian Constitution (Class 5)",
    "world heritage sites": "World Heritage Sites (Class 5)",
    "class 5 heritage": "World Heritage Sites (Class 5)",
    "heritage sites": "World Heritage Sites (Class 5)",
    "unesco sites": "World Heritage Sites (Class 5)",
    "space missions": "Space Missions (Class 5)",
    "class 5 space": "Space Missions (Class 5)",
    "isro": "Space Missions (Class 5)",
    "chandrayaan": "Space Missions (Class 5)",
    "environmental awareness": "Environmental Awareness (Class 5)",
    "class 5 environment": "Environmental Awareness (Class 5)",
    "pollution": "Environmental Awareness (Class 5)",
    "conservation": "Environmental Awareness (Class 5)",
    # ── Moral Science aliases ──────────────────────────
    "sharing": "Sharing (Class 1)",
    "class 1 sharing": "Sharing (Class 1)",
    "sharing toys": "Sharing (Class 1)",
    "being generous": "Sharing (Class 1)",
    "honesty": "Honesty (Class 1)",
    "class 1 honesty": "Honesty (Class 1)",
    "telling truth": "Honesty (Class 1)",
    "being honest": "Honesty (Class 1)",
    "kindness": "Kindness (Class 2)",
    "class 2 kindness": "Kindness (Class 2)",
    "being kind": "Kindness (Class 2)",
    "helping others": "Kindness (Class 2)",
    "respecting elders": "Respecting Elders (Class 2)",
    "class 2 respecting elders": "Respecting Elders (Class 2)",
    "good manners": "Respecting Elders (Class 2)",
    "respect elders": "Respecting Elders (Class 2)",
    "teamwork": "Teamwork (Class 3)",
    "class 3 teamwork": "Teamwork (Class 3)",
    "working together": "Teamwork (Class 3)",
    "cooperation": "Teamwork (Class 3)",
    "empathy": "Empathy (Class 3)",
    "class 3 empathy": "Empathy (Class 3)",
    "understanding feelings": "Empathy (Class 3)",
    "being supportive": "Empathy (Class 3)",
    "environmental care": "Environmental Care (Class 3)",
    "class 3 environmental care": "Environmental Care (Class 3)",
    "protect nature": "Environmental Care (Class 3)",
    "reduce reuse recycle": "Environmental Care (Class 3)",
    "leadership": "Leadership (Class 4)",
    "class 4 leadership": "Leadership (Class 4)",
    "good leader": "Leadership (Class 4)",
    "being a leader": "Leadership (Class 4)",
    "global citizenship": "Global Citizenship (Class 5)",
    "class 5 global citizenship": "Global Citizenship (Class 5)",
    "cultural diversity": "Global Citizenship (Class 5)",
    "world peace": "Global Citizenship (Class 5)",
    "digital ethics": "Digital Ethics (Class 5)",
    "class 5 digital ethics": "Digital Ethics (Class 5)",
    "online safety": "Digital Ethics (Class 5)",
    "digital footprint": "Digital Ethics (Class 5)",
    # ── Health & Physical Education aliases ──────────────────────────
    "personal hygiene": "Personal Hygiene (Class 1)",
    "class 1 hygiene": "Personal Hygiene (Class 1)",
    "c1 hygiene": "Personal Hygiene (Class 1)",
    "handwashing": "Personal Hygiene (Class 1)",
    "good posture": "Good Posture (Class 1)",
    "class 1 posture": "Good Posture (Class 1)",
    "c1 posture": "Good Posture (Class 1)",
    "sitting straight": "Good Posture (Class 1)",
    "basic physical activities": "Basic Physical Activities (Class 1)",
    "class 1 physical activities": "Basic Physical Activities (Class 1)",
    "c1 physical": "Basic Physical Activities (Class 1)",
    "running jumping": "Basic Physical Activities (Class 1)",
    "healthy eating habits": "Healthy Eating Habits (Class 2)",
    "class 2 healthy eating": "Healthy Eating Habits (Class 2)",
    "c2 eating": "Healthy Eating Habits (Class 2)",
    "healthy food": "Healthy Eating Habits (Class 2)",
    "outdoor play": "Outdoor Play (Class 2)",
    "class 2 outdoor play": "Outdoor Play (Class 2)",
    "c2 outdoor": "Outdoor Play (Class 2)",
    "playing outside": "Outdoor Play (Class 2)",
    "basic stretching": "Basic Stretching (Class 2)",
    "class 2 stretching": "Basic Stretching (Class 2)",
    "c2 stretching": "Basic Stretching (Class 2)",
    "warm up exercises": "Basic Stretching (Class 2)",
    "balanced diet": "Balanced Diet (Class 3)",
    "class 3 balanced diet": "Balanced Diet (Class 3)",
    "c3 diet": "Balanced Diet (Class 3)",
    "food groups": "Balanced Diet (Class 3)",
    "team sports rules": "Team Sports Rules (Class 3)",
    "class 3 team sports": "Team Sports Rules (Class 3)",
    "c3 sports": "Team Sports Rules (Class 3)",
    "cricket rules": "Team Sports Rules (Class 3)",
    "safety at play": "Safety at Play (Class 3)",
    "class 3 safety": "Safety at Play (Class 3)",
    "c3 safety": "Safety at Play (Class 3)",
    "playground safety": "Safety at Play (Class 3)",
    "first aid basics": "First Aid Basics (Class 4)",
    "class 4 first aid": "First Aid Basics (Class 4)",
    "c4 first aid": "First Aid Basics (Class 4)",
    "treating cuts": "First Aid Basics (Class 4)",
    "yoga introduction": "Yoga Introduction (Class 4)",
    "class 4 yoga": "Yoga Introduction (Class 4)",
    "c4 yoga": "Yoga Introduction (Class 4)",
    "basic yoga": "Yoga Introduction (Class 4)",
    "importance of sleep": "Importance of Sleep (Class 4)",
    "class 4 sleep": "Importance of Sleep (Class 4)",
    "c4 sleep": "Importance of Sleep (Class 4)",
    "sleep hygiene": "Importance of Sleep (Class 4)",
    "fitness and stamina": "Fitness and Stamina (Class 5)",
    "class 5 fitness": "Fitness and Stamina (Class 5)",
    "c5 fitness": "Fitness and Stamina (Class 5)",
    "stamina building": "Fitness and Stamina (Class 5)",
    "nutrition labels reading": "Nutrition Labels Reading (Class 5)",
    "class 5 nutrition": "Nutrition Labels Reading (Class 5)",
    "c5 nutrition": "Nutrition Labels Reading (Class 5)",
    "reading food labels": "Nutrition Labels Reading (Class 5)",
    "mental health awareness": "Mental Health Awareness (Class 5)",
    "class 5 mental health": "Mental Health Awareness (Class 5)",
    "c5 mental health": "Mental Health Awareness (Class 5)",
    "managing stress": "Mental Health Awareness (Class 5)",
}


def get_topic_profile(topic: str) -> dict | None:
    normalized = normalize_topic(topic)
    # Exact match first
    profile = TOPIC_PROFILES.get(normalized)
    if profile:
        return profile
    # Try alias (case-insensitive)
    alias_key = normalized.lower()
    if alias_key in _TOPIC_ALIASES:
        return TOPIC_PROFILES.get(_TOPIC_ALIASES[alias_key])
    # Substring match: "Multiplication" should match "Multiplication (tables 2-10)"
    for key in TOPIC_PROFILES:
        if key.lower().startswith(alias_key) or alias_key.startswith(key.lower().split("(")[0].strip()):
            return TOPIC_PROFILES[key]
    return None


def _apply_topic_profile(directives: list[dict], profile: dict) -> list[dict]:
    """Override directives with topic-specific constraints.

    For arithmetic-carry topics (Addition, Subtraction, combined Add+Sub),
    preserve carry_required and allow_operations from the original directive
    so that deterministic carry/borrow pairs are generated.
    """
    skills = profile["allowed_skill_tags"]
    allowed_skills = set(skills)
    slot_types = profile.get("allowed_slot_types", SLOT_ORDER)
    allowed_slots = set(slot_types)

    # Detect if this is an arithmetic profile that needs carry/borrow
    _carry_skills = {"column_add_with_carry", "column_sub_with_borrow"}
    _is_carry_profile = bool(_carry_skills & allowed_skills)

    out = []
    for i, d in enumerate(directives):
        nd = dict(d)
        if nd.get("skill_tag", "") not in allowed_skills:
            nd["skill_tag"] = skills[i % len(skills)]
        if nd.get("slot_type", "") not in allowed_slots:
            nd["slot_type"] = slot_types[i % len(slot_types)]
        if not _is_carry_profile:
            nd["carry_required"] = False
            nd["allow_operations"] = []
        out.append(nd)
    return out


# ════════════════════════════════════════════════════════════
# B) Variation Banks
# ════════════════════════════════════════════════════════════

CONTEXT_BANK: list[dict[str, str]] = [
    {"item": "books", "scenario": "arranging books in a library"},
    {"item": "stickers", "scenario": "collecting stickers at school"},
    {"item": "pencils", "scenario": "organising pencils in the classroom"},
    {"item": "coins", "scenario": "saving coins in a piggy bank"},
    {"item": "rupees", "scenario": "counting money at a shop"},
    {"item": "pages", "scenario": "reading pages of a storybook"},
    {"item": "steps", "scenario": "counting steps walked in a day"},
    {"item": "points", "scenario": "scoring points in a game"},
    {"item": "toy cars", "scenario": "collecting toy cars"},
    {"item": "flowers", "scenario": "planting flowers in a garden"},
    {"item": "water bottles", "scenario": "packing water bottles for a trip"},
    {"item": "bus tickets", "scenario": "buying bus tickets for a field trip"},
    {"item": "marbles", "scenario": "playing marbles in the park"},
    {"item": "cookies", "scenario": "baking cookies for a sale"},
    {"item": "students", "scenario": "counting students in class"},
    {"item": "crayons", "scenario": "sharing crayons in art class"},
    {"item": "lego blocks", "scenario": "building with lego blocks"},
    {"item": "chocolates", "scenario": "distributing chocolates on a festival"},
]

NAME_BANKS: dict[str, list[str]] = {
    "India": ["Aarav", "Priya", "Rohan", "Ananya", "Meera", "Kabir", "Diya", "Arjun",
              "Ishaan", "Saanvi", "Vivaan", "Anika", "Advait", "Zara", "Reyansh", "Tara"],
    "UAE": ["Ahmed", "Fatima", "Omar", "Mariam", "Sara", "Yusuf", "Layla", "Ali",
            "Hassan", "Amira", "Khalid", "Noor", "Zain", "Hana", "Rayan", "Lina"],
}

THINKING_STYLE_BANK: list[dict[str, str]] = [
    {"style": "closer_to",
     "instruction": "Without calculating, decide which of two given values the answer is closer to and explain why."},
    {"style": "threshold_check",
     "instruction": "Without calculating, decide whether the answer is more or less than a given number and explain."},
    {"style": "bounds_range",
     "instruction": "Without calculating exactly, find a range (between A and B) that the answer falls in."},
    {"style": "round_nearest_10",
     "instruction": "Round each number to the nearest 10 first, then estimate the answer."},
    {"style": "round_nearest_100",
     "instruction": "Round each number to the nearest 100 first, then estimate the answer."},
    {"style": "reasonable_estimate",
     "instruction": "Given three possible answers, pick the most reasonable one and explain why the others are wrong."},
]


# ════════════════════════════════════════════════════════════
# C) Deterministic Error Computation
# ════════════════════════════════════════════════════════════

# Number pairs that require carrying in BOTH ones and tens columns
CARRY_PAIRS: list[tuple[int, int]] = [
    (345, 278), (456, 367), (289, 145), (178, 456), (267, 385),
    (386, 247), (163, 479), (548, 276), (637, 185), (429, 383),
    (356, 467), (274, 558), (185, 347), (493, 238), (567, 265),
]

ERROR_TAGS: list[str] = [
    "lost_carry_ones",
    "lost_carry_tens",
    "double_carry",
    "carry_to_wrong_col",
    "no_carry_digitwise",
]

_ERROR_TAG_HINTS: dict[str, str] = {
    "lost_carry_ones": "ignored carry from ones to tens",
    "lost_carry_tens": "ignored carry from tens to hundreds",
    "double_carry": "added carry twice",
    "carry_to_wrong_col": "carry applied to wrong column",
    "no_carry_digitwise": "added digits without regrouping",
}


def compute_wrong(a: int, b: int, tag: str) -> int:
    """Deterministically compute a wrong answer based on carry error tag."""
    a_o, a_t, a_h = a % 10, (a // 10) % 10, a // 100
    b_o, b_t, b_h = b % 10, (b // 10) % 10, b // 100

    ones_sum = a_o + b_o
    carry_ones = 1 if ones_sum >= 10 else 0

    if tag == "lost_carry_ones":
        r_o = ones_sum % 10
        tens_raw = a_t + b_t  # no carry from ones
        r_t = tens_raw % 10
        carry_t = 1 if tens_raw >= 10 else 0
        r_h = a_h + b_h + carry_t

    elif tag == "lost_carry_tens":
        r_o = ones_sum % 10
        tens_with_carry = a_t + b_t + carry_ones
        r_t = tens_with_carry % 10
        r_h = a_h + b_h  # no carry from tens

    elif tag == "double_carry":
        r_o = ones_sum % 10
        tens_double = a_t + b_t + carry_ones * 2
        r_t = tens_double % 10
        carry_t_d = 1 if tens_double >= 10 else 0
        r_h = a_h + b_h + carry_t_d

    elif tag == "carry_to_wrong_col":
        r_o = ones_sum % 10
        tens_no_carry = a_t + b_t  # ones carry didn't come here
        r_t = tens_no_carry % 10
        carry_from_tens = 1 if tens_no_carry >= 10 else 0
        r_h = a_h + b_h + carry_ones + carry_from_tens  # ones carry to hundreds

    elif tag == "no_carry_digitwise":
        r_o = (a_o + b_o) % 10
        r_t = (a_t + b_t) % 10
        r_h = (a_h + b_h) % 10

    else:
        return a + b

    return r_h * 100 + r_t * 10 + r_o


# Precompute and validate ALL error patterns at module load
_ALL_ERRORS: list[dict] = []
for _a, _b in CARRY_PAIRS:
    _correct = _a + _b
    for _tag in ERROR_TAGS:
        _wrong = compute_wrong(_a, _b, _tag)
        assert _wrong != _correct, f"Bug: wrong==correct for ({_a},{_b},{_tag})"
        assert 100 <= _wrong <= 999, f"Bug: wrong={_wrong} out of 3-digit range for ({_a},{_b},{_tag})"
        _ALL_ERRORS.append({
            "id": f"{_tag}_{_a}_{_b}",
            "a": _a, "b": _b,
            "correct": _correct,
            "wrong": _wrong,
            "tag": _tag,
            "hint": _ERROR_TAG_HINTS[_tag],
        })
# Clean up module-level loop vars
del _a, _b, _correct, _tag, _wrong


def has_carry(a: int, b: int) -> bool:
    """Check if a + b requires carrying in ones or tens column."""
    return (a % 10) + (b % 10) >= 10 or ((a // 10) % 10) + ((b // 10) % 10) >= 10


def has_borrow(a: int, b: int) -> bool:
    """Check if a - b requires borrowing in ones or tens column (a > b assumed)."""
    if a < b:
        a, b = b, a
    return (a % 10) < (b % 10) or ((a // 10) % 10) < ((b // 10) % 10)


def make_carry_pair(rng: random.Random, operation: str = "addition") -> tuple[int, int]:
    """Generate a 3-digit pair requiring carry (addition) or borrow (subtraction)."""
    if operation == "subtraction":
        for _ in range(50):
            a = rng.randint(200, 999)
            b = rng.randint(100, a - 1)
            if has_borrow(a, b):
                return a, b
        return 502, 178  # guaranteed borrow fallback

    for _ in range(50):
        a = rng.randint(100, 899)
        b = rng.randint(100, 899)
        if has_carry(a, b) and a + b <= 999:
            return a, b
    return 345, 278  # guaranteed carry fallback


# ════════════════════════════════════════════════════════════
# D) Seeded Selection (history-aware)
# ════════════════════════════════════════════════════════════

def _make_seed(grade: str, topic: str, q_count: int, history_count: int) -> int:
    """Deterministic seed. history_count ensures uniqueness across requests."""
    key = f"{grade}|{topic}|{date.today().isoformat()}|{q_count}|{history_count}"
    return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)


def pick_context(rng: random.Random, avoid_contexts: list[str]) -> dict:
    """Pick a word problem context, avoiding recently used ones."""
    avoid_set = set(avoid_contexts)
    candidates = [c for c in CONTEXT_BANK if c["item"] not in avoid_set]
    if not candidates:
        candidates = list(CONTEXT_BANK)
        logger.info("All contexts used recently; allowing repeats")
    return rng.choice(candidates)


def pick_name(rng: random.Random, region: str) -> str:
    """Pick a name, rotating randomly."""
    names = NAME_BANKS.get(region, NAME_BANKS["India"])
    return rng.choice(names)


def pick_error(rng: random.Random, avoid_error_ids: list[str]) -> dict:
    """Pick an error pattern from _ALL_ERRORS, avoiding recently used ones."""
    avoid_set = set(avoid_error_ids)
    candidates = [e for e in _ALL_ERRORS if e["id"] not in avoid_set]
    if not candidates:
        candidates = list(_ALL_ERRORS)
        logger.info("All error patterns used recently; allowing repeats")
    return rng.choice(candidates)


def pick_thinking_style(rng: random.Random, avoid_styles: list[str]) -> dict:
    """Pick a thinking style, avoiding recently used ones."""
    avoid_set = set(avoid_styles)
    candidates = [s for s in THINKING_STYLE_BANK if s["style"] not in avoid_set]
    if not candidates:
        candidates = list(THINKING_STYLE_BANK)
        logger.info("All thinking styles used recently; allowing repeats")
    return rng.choice(candidates)


# ════════════════════════════════════════════════════════════
# E) Slot Plan Generation
# ════════════════════════════════════════════════════════════

def _compute_proportional_plan(n: int) -> dict[str, int]:
    """Proportional allocation for non-standard q_counts."""
    plan = {s: int(_DOCTRINE_WEIGHTS[s] * n) for s in SLOT_ORDER}
    remainders = {s: _DOCTRINE_WEIGHTS[s] * n - plan[s] for s in SLOT_ORDER}
    leftover = n - sum(plan.values())
    for s in sorted(remainders, key=lambda k: remainders[k], reverse=True):
        if leftover <= 0:
            break
        plan[s] += 1
        leftover -= 1
    for mandatory in ("error_detection", "thinking"):
        if plan[mandatory] < 1 and n >= 2:
            donor = max((s for s in SLOT_ORDER if s != mandatory), key=lambda s: plan[s])
            if plan[donor] > 0:
                plan[donor] -= 1
                plan[mandatory] = 1
    return plan


def get_slot_plan(q_count: int) -> list[str]:
    """Return ordered list of slot_types for q_count questions."""
    if q_count <= 0:
        return []
    plan = SLOT_PLANS.get(q_count) or _compute_proportional_plan(q_count)
    seq: list[str] = []
    for slot_type in SLOT_ORDER:
        seq.extend([slot_type] * plan.get(slot_type, 0))
    return seq


def get_question_difficulty(slot_type: str, worksheet_difficulty: str) -> str:
    """Determine per-question difficulty from slot type + worksheet level."""
    if slot_type == "recognition":
        return "easy"
    if slot_type == "error_detection":
        return "medium" if worksheet_difficulty in ("easy", "medium") else "hard"
    if slot_type == "thinking":
        return "hard" if worksheet_difficulty == "hard" else "medium"
    return worksheet_difficulty


def _scale_recipe(recipe: list[dict], target: int) -> list[dict]:
    """Scale recipe counts proportionally to hit target total."""
    total = sum(item.get("count", 1) for item in recipe)
    if total == target:
        return [dict(item) for item in recipe]

    n_items = len(recipe)

    # When target <= number of recipe items, give each 1 and trim excess items.
    # Prioritize keeping error_detection and thinking slots.
    if target <= n_items:
        # Identify which items map to critical slot types
        critical_indices = set()  # error_detection and thinking
        other_indices = []
        for idx, item in enumerate(recipe):
            mapping = _SKILL_TAG_TO_SLOT.get(item["skill_tag"])
            slot_type = mapping[0] if mapping else "application"
            if slot_type in ("error_detection", "thinking"):
                critical_indices.add(idx)
            else:
                other_indices.append(idx)
        # Keep all critical items, fill remaining from others (preserve order)
        keep = sorted(critical_indices)
        remaining = target - len(keep)
        keep.extend(other_indices[:max(0, remaining)])
        keep = sorted(keep)[:target]
        scaled = [{**recipe[i], "count": 1} for i in keep]
        return scaled

    # Normal proportional scaling (target > n_items, so each gets at least 1)
    scaled = []
    assigned = 0
    for i, item in enumerate(recipe):
        if i == len(recipe) - 1:
            count = max(1, target - assigned)
        else:
            count = max(1, round(item.get("count", 1) * target / total))
        scaled.append({**item, "count": count})
        assigned += count

    actual_total = sum(s["count"] for s in scaled)
    while actual_total > target:
        idx = max(range(len(scaled)), key=lambda j: scaled[j]["count"])
        if scaled[idx]["count"] > 1:
            scaled[idx]["count"] -= 1
            actual_total -= 1
        else:
            break
    while actual_total < target:
        scaled[0]["count"] += 1
        actual_total += 1

    return scaled


def build_worksheet_plan(
    q_count: int,
    mix_recipe: list[dict] | None = None,
    constraints: dict | None = None,
    topic: str = "",
) -> list[dict]:
    """Build a deterministic worksheet plan from mix_recipe or defaults.

    Returns list of slot directives, each with:
      slot_type, format_hint, skill_tag, carry_required, require_student_answer, allow_operations
    """
    profile = get_topic_profile(topic)

    if mix_recipe is None:
        if profile:
            # Check for explicit recipe by count first
            if "recipes_by_count" in profile and q_count in profile["recipes_by_count"]:
                recipe = profile["recipes_by_count"][q_count]
            elif "default_recipe" in profile:
                recipe = _scale_recipe(profile["default_recipe"], q_count)
            else:
                recipe = _scale_recipe(DEFAULT_MIX_RECIPE_20, q_count)
        else:
            recipe = _scale_recipe(DEFAULT_MIX_RECIPE_20, q_count)
    else:
        total = sum(item.get("count", 0) for item in mix_recipe)
        recipe = mix_recipe if total == q_count else _scale_recipe(mix_recipe, q_count)

    constraints = constraints or {}
    carry_required = constraints.get("carry_required", False)
    allow_operations = constraints.get("allow_operations") or ["addition", "subtraction"]

    plan: list[dict] = []
    for item in recipe:
        skill_tag = item["skill_tag"]
        mapping = _SKILL_TAG_TO_SLOT.get(skill_tag)
        slot_type, format_hint = mapping if mapping else ("application", "word_problem")

        for _ in range(item.get("count", 1)):
            directive = {
                "slot_type": slot_type,
                "format_hint": format_hint,
                "skill_tag": skill_tag,
                "carry_required": carry_required,
                "require_student_answer": item.get("require_student_answer", False),
                "allow_operations": allow_operations,
                "visual_type": item.get("visual_type"),
                "unique_contexts": item.get("unique_contexts", False),
            }
            if slot_type == "thinking":
                directive["estimation_rule"] = item.get(
                    "estimation_rule", "round_to_nearest_hundred"
                )
            plan.append(directive)

    if profile:
        plan = _apply_topic_profile(plan, profile)

    # For combined add/sub topic, set operation flags
    _norm_topic = normalize_topic(topic).lower()
    if "addition and subtraction" in _norm_topic or "add/sub" in _norm_topic:
        for d in plan:
            if d.get("skill_tag", "").startswith("column_add") or d.get("skill_tag", "").startswith("addition"):
                d["allow_operations"] = ["addition"]
            elif d.get("skill_tag", "").startswith("column_sub") or d.get("skill_tag", "").startswith("subtraction"):
                d["allow_operations"] = ["subtraction"]

    # Minimal injection: ensure at least one multiplication_table_recall directive
    if "multiplication tables" in _norm_topic:
        has_mult = any(d.get("skill_tag") == "multiplication_table_recall" for d in plan)
        if not has_mult and plan:
            plan[0] = {
                **plan[0],
                "skill_tag": "multiplication_table_recall",
                "slot_type": "recognition",
                "format_hint": "simple_identify",
                "carry_required": False,
            }

    # Backfill: guarantee every directive has a non-empty format_hint
    for d in plan:
        if not d.get("format_hint"):
            d["format_hint"] = DEFAULT_FORMAT_BY_SLOT_TYPE.get(d["slot_type"], "")

    return plan


# ════════════════════════════════════════════════════════════
# F) Slot Instructions (backend builds per-question instructions)
# ════════════════════════════════════════════════════════════

def _build_slot_instruction(
    slot_type: str,
    chosen_variant: dict | None,
    directive: dict | None = None,
    topic: str = "",
) -> str:
    """Build backend-chosen specific instructions for a slot question.

    chosen_variant contains the picked context/error/style for this slot.
    directive (optional) carries plan-level overrides (carry_required, format_hint, etc).
    topic (optional) is the canonical topic name used to look up CONTEXT_BANK for word problems.
    """
    # Topic-specific short instructions (token-efficient)
    _skill_tag = (directive or {}).get("skill_tag", "")
    # Fractions
    if _skill_tag in ("fraction_identify_half", "fraction_identify_quarter", "fraction_word_problem",
                       "fraction_of_shape_shaded", "fraction_error_spot", "fraction_thinking"):
        _fmt = (directive or {}).get("format_hint", "fraction_number")
        frac_instructions = {
            "fraction_identify_half": "Find half of a number. Half = number ÷ 2. VERIFY: half × 2 = original.",
            "fraction_identify_quarter": "Find quarter of a number. Quarter = number ÷ 4. VERIFY: quarter × 4 = original.",
            "fraction_word_problem": "Read carefully. Identify whole and fraction asked. Common: 1/2, 1/4, 3/4. VERIFY your answer.",
            "fraction_of_shape_shaded": "Count total parts (denominator) and shaded parts (numerator). Write as numerator/denominator. Use DIFFERENT shapes each time: circle OR rectangle OR square OR triangle. DO NOT repeat same shape in consecutive questions.",
            "fraction_error_spot": "Present a scenario with a WRONG fraction claim. Error must be clear (impossible shading, wrong calculation). Ask student to identify AND correct the mistake.",
            "fraction_thinking": "Multi-step fraction problem. Step 1: Calculate amount each person gets. Step 2: Express as fraction. Fraction each = 1 ÷ number_of_people. VERIFY: (amount each) × (number of people) = total. DOUBLE-CHECK before finalizing.",
        }
        return (
            f"format: {_fmt}. "
            f"Topic: Fractions (halves, quarters). skill: {_skill_tag}. "
            f"{frac_instructions.get(_skill_tag, 'About fractions.')} "
            "Numbers must be divisible by 2 or 4. "
            "Use DIFFERENT numbers and contexts each time. "
            "DO NOT repeat similar questions."
        )

    # Combined Addition/Subtraction - recognition and application only
    # Error_spot skill tags fall through to the generic error_detection handler
    # which properly injects pick_error() variant numbers
    if _skill_tag in ("column_add_with_carry", "addition_word_problem",
                       "column_sub_with_borrow", "subtraction_word_problem"):
        _fmt = (directive or {}).get("format_hint", "column_setup")
        is_add = "add" in _skill_tag
        if is_add:
            op = "addition"
            constraint = "Require carrying in ones/tens columns."
        else:
            op = "subtraction"
            constraint = "Require borrowing in ones/tens columns."

        if "word_problem" in _skill_tag:
            return (
                f"format: word_problem. Topic: {op.capitalize()} (3-digit). "
                f"Create a word problem about {op} with 3-digit numbers. "
                f"Include a complete story with character names, context, and clear question. "
                f"{constraint} "
                f"Question text must be at least 80 characters. "
                f"DO NOT use number pairs that have been used before."
            )
        else:
            return (
                f"format: {_fmt}. Topic: {op.capitalize()} (3-digit). "
                f"Present a 3-digit {op} problem in column form. "
                f"{constraint} "
                f"Question text must include the full problem written out. "
                f"DO NOT use number pairs that have been used before."
            )

    if _skill_tag in ("clock_reading", "time_word_problem", "calendar_reading", "time_fill_blank", "time_error_spot", "time_thinking"):
        _fmt = (directive or {}).get("format_hint", SLOT_INSTRUCTIONS.get(_skill_tag, ""))
        topic_ctx = (
            f"Topic: Time (reading clock, calendar). skill: {_skill_tag}. "
            "Generate ONLY time-related questions. "
            "Do NOT use addition/subtraction of plain numbers, carry, regroup, "
            "column form, base ten, place value, estimation, rounding. "
            "DO NOT repeat the same numbers or scenarios. Each question must use DIFFERENT numbers and contexts. "
        )
        if _skill_tag == "clock_reading":
            return topic_ctx + "Ask about reading analog/digital clocks (hours, half-hours, quarter-hours)."
        elif _skill_tag == "time_word_problem":
            return topic_ctx + "Word problem about duration, elapsed time, or scheduling using clocks/calendars."
        elif _skill_tag == "calendar_reading":
            return topic_ctx + "Ask about days, weeks, months, or reading a calendar."
        elif _skill_tag == "time_fill_blank":
            return topic_ctx + "format: fill_blank. Fill-in-the-blank about time. Example: 'There are ___ minutes in 1 hour.' or '2 hours = ___ minutes.'"
        elif _skill_tag == "time_error_spot":
            return topic_ctx + (
                "format: error_spot. A student made a SPECIFIC WRONG answer about time. "
                "The wrong answer and correct answer MUST be DIFFERENT. "
                "Pick ONE of these error types:\n"
                "1) Clock misread: 'The hour hand is on 2 and the minute hand is on 3. "
                "Riya said the time is 2:30.' WRONG=2:30, CORRECT=2:15 "
                "(minute hand on 3 means 3×5=15 minutes, not 30).\n"
                "2) Clock misread: 'The minute hand is on 6. "
                "Amit said it shows 6 minutes past the hour.' WRONG=X:06, CORRECT=X:30 "
                "(minute hand on 6 means 6×5=30 minutes).\n"
                "3) Elapsed time error: 'A movie starts at 3:15 and ends at 5:45. "
                "Priya said the movie is 2 hours long.' WRONG=2 hours, CORRECT=2 hours 30 minutes.\n"
                "State the student's WRONG answer clearly, then ask: "
                "What mistake did they make? What is the correct answer?\n"
                "The answer field must contain the CORRECT answer (not the wrong one)."
            )
        elif _skill_tag == "time_thinking":
            return topic_ctx + "format: multi_step. Reasoning question about time — e.g., elapsed time across hours, comparing durations, scheduling multiple events. NOT pure computation."
        return topic_ctx

    if _skill_tag in ("multiplication_tables", "multiplication_word_problem", "multiplication_fill_blank", "multiplication_error_spot", "multiplication_thinking"):
        mult_ctx = (
            "Topic: Multiplication tables (2-10). "
            "ONLY use multiplication (×). "
            "Do NOT use addition, subtraction, carry, borrow, column form, +, -. "
            "DO NOT repeat the same numbers or scenarios. Each question must use DIFFERENT numbers and contexts. "
        )
        if _skill_tag == "multiplication_tables":
            return mult_ctx + "Ask a multiplication fact (e.g., 'What is 7 × 8?'). Answer is the product."
        elif _skill_tag == "multiplication_word_problem":
            return mult_ctx + "format: word_problem. Real-world scenario using multiplication only."
        elif _skill_tag == "multiplication_fill_blank":
            return mult_ctx + "format: fill_blank. Fill-in-the-blank multiplication. Example: '___ × 6 = 42' or '8 × ___ = 56'. Answer is the missing number."
        elif _skill_tag == "multiplication_error_spot":
            return mult_ctx + (
                "format: error_spot. Show a student who got a multiplication fact WRONG. "
                "Example: 'Riya says 6 × 7 = 48. Is she correct? What is the right answer?' "
                "The wrong product and correct product MUST be different. "
                "Answer must be the CORRECT product."
            )
        elif _skill_tag == "multiplication_thinking":
            return mult_ctx + "format: multi_step. Reasoning about multiplication — e.g., 'Which is greater: 4 × 9 or 5 × 7? Explain.' NOT pure computation."
        return mult_ctx

    # Numbers and Place Value
    if _skill_tag in ("place_value_identify", "number_comparison", "number_sequence",
                       "number_expansion", "number_ordering", "place_value_error", "number_thinking"):
        _fmt = (directive or {}).get("format_hint", "place_value_question")
        num_instructions = {
            "place_value_identify": "Identify place value (ones, tens, hundreds, thousands) in 4-digit numbers.",
            "number_comparison": "Compare two numbers using greater than (>) or less than (<). Example: Which is greater: 4532 or 4523?",
            "number_sequence": "Complete number sequences or skip counting by 10s, 100s, 1000s.",
            "number_expansion": "Write a number in expanded form. Example: 4532 = 4000 + 500 + 30 + 2",
            "number_ordering": "Arrange numbers in ascending (smallest to largest) or descending (largest to smallest) order.",
            "place_value_error": "Find the mistake in identifying place value. Example: Student says 7 in 5729 is in thousands place (wrong - it's hundreds).",
            "number_thinking": "Multi-step reasoning about numbers. Example: What is 100 more than 4532? What number comes before 4000?",
        }
        return (
            f"format: {_fmt}. "
            f"Topic: Numbers up to 10000. skill: {_skill_tag}. "
            f"{num_instructions.get(_skill_tag, 'About numbers.')} "
            "Use numbers up to 4 digits (1000-9999). "
            "Do NOT use addition/subtraction operations, money, time, fractions. "
            "DO NOT repeat the same numbers or scenarios. Each question must use DIFFERENT numbers and contexts."
        )

    # Money
    if _skill_tag in ("money_recognition", "money_word_problem", "money_change",
                       "money_fill_blank", "money_error_spot", "money_thinking"):
        _fmt = (directive or {}).get("format_hint", "money_question")
        money_instructions = {
            "money_recognition": "Identify coins and notes, or state the value of a set of coins/notes.",
            "money_word_problem": "Calculate total cost AND change. VERIFY: total cost must be LESS than payment amount. ALWAYS show both: Total = X, Change = payment - total.",
            "money_change": "When calculating change: Change = Payment - Total Cost. Double-check your math.",
            "money_fill_blank": "Fill-in-the-blank about money. Example: '₹50 + ₹20 + ₹5 = ₹___' or '₹100 - ₹37 = ₹___'.",
            "money_error_spot": "Verify the math in the scenario. Common errors: wrong subtraction, forgot to multiply quantity × price.",
            "money_thinking": "First check if customer CAN afford the items (total ≤ payment). If not, answer should say 'Not enough money'.",
        }
        return (
            f"format: {_fmt}. "
            f"Topic: Money (bills and change). skill: {_skill_tag}. "
            f"{money_instructions.get(_skill_tag, 'About money.')} "
            "Use rupees (₹) with realistic prices. "
            "Do NOT use plain addition/subtraction without money context, fractions, time. "
            "DO NOT repeat the same numbers or scenarios. Each question must use DIFFERENT numbers and contexts."
        )

    # Patterns
    if _skill_tag in ("number_pattern", "shape_pattern", "pattern_error_spot", "pattern_thinking"):
        _fmt = (directive or {}).get("format_hint", "shape_pattern")
        pattern_instructions = {
            "number_pattern": "Generate a number pattern with a CLEAR rule. Rules: +2, +5, +10, ×2, -3. Pattern length: 5-6 numbers with 1-2 blanks. VERIFY: apply rule forward and backward to confirm pattern is consistent.",
            "shape_pattern": "Generate a repeating shape pattern. Use 2-3 shapes in a cycle. Pattern length: 8-10 shapes with 2-3 blanks. VERIFY: the pattern repeats consistently.",
            "pattern_error_spot": "Present a number pattern where ONE number is WRONG. The error must be a SINGLE number that breaks the rule. Example: 2, 4, 7, 8, 10 (7 should be 6). VERIFY: identify the wrong number AND provide correct number.",
            "pattern_thinking": "Multi-step pattern problem. First identify the rule, then extend the pattern, then answer a question about it. VERIFY each step.",
        }
        return (
            f"format: {_fmt}. "
            f"Topic: Patterns and sequences. skill: {_skill_tag}. "
            f"{pattern_instructions.get(_skill_tag, 'About patterns.')} "
            "The pattern rule must be SIMPLE and CONSISTENT. "
            "DO NOT use complex rules. "
            "VERIFY your pattern before finalizing. "
            "DO NOT repeat the same numbers or scenarios. Each question must use DIFFERENT numbers and contexts."
        )

    # ── Class 4 instruction builders ──────────────────────────

    # Large numbers (up to 1,00,000)
    if _skill_tag in ("c4_large_number_identify", "c4_large_number_compare",
                       "c4_large_number_order", "c4_large_number_expand",
                       "c4_large_number_error", "c4_large_number_thinking"):
        _fmt = (directive or {}).get("format_hint", "place_value_question")
        c4_num_instructions = {
            "c4_large_number_identify": "Identify place value (ten-thousands, thousands, hundreds, tens, ones) in 5-digit numbers. Use Indian numbering system (e.g., 45,678).",
            "c4_large_number_compare": "Compare two 5-digit numbers using > or <. Example: Which is greater: 45,678 or 45,687?",
            "c4_large_number_order": "Arrange 4-5 five-digit numbers in ascending or descending order.",
            "c4_large_number_expand": "Write a 5-digit number in expanded form. Example: 45,678 = 40,000 + 5,000 + 600 + 70 + 8",
            "c4_large_number_error": "A student made a WRONG statement about place value of a 5-digit number. Ask student to find and correct the mistake.",
            "c4_large_number_thinking": "Multi-step reasoning about 5-digit numbers. Example: What number is 1000 more than 45,678? Which digit changes when you add 100 to 39,950?",
        }
        return (
            f"format: {_fmt}. "
            f"Topic: Large numbers (up to 1,00,000). skill: {_skill_tag}. "
            f"{c4_num_instructions.get(_skill_tag, 'About large numbers.')} "
            "Use 5-digit numbers (10000-99999) in Indian system. "
            "Do NOT use addition/subtraction operations, fractions, decimals. "
            "DO NOT repeat the same numbers or scenarios. Each question must use DIFFERENT numbers and contexts."
        )

    # Addition and subtraction (5-digit)
    if _skill_tag in ("c4_add5_column", "c4_add5_word_problem",
                       "c4_sub5_column", "c4_sub5_word_problem",
                       "c4_addsub5_missing", "c4_addsub5_error", "c4_addsub5_thinking"):
        _fmt = (directive or {}).get("format_hint", "column_setup")
        is_add = "add5" in _skill_tag
        is_sub = "sub5" in _skill_tag
        if is_add:
            op_ctx = "addition with 5-digit numbers. Require carrying in at least one column."
        elif is_sub:
            op_ctx = "subtraction with 5-digit numbers. Require borrowing in at least one column."
        else:
            op_ctx = "addition or subtraction with 5-digit numbers (10000-99999)."
        c4_addsub_instructions = {
            "c4_add5_column": f"Present a 5-digit addition problem in column form. {op_ctx}",
            "c4_add5_word_problem": f"Create a word problem about {op_ctx} Include a story with character names.",
            "c4_sub5_column": f"Present a 5-digit subtraction problem in column form. {op_ctx}",
            "c4_sub5_word_problem": f"Create a word problem about {op_ctx} Include a story with character names.",
            "c4_addsub5_missing": "Fill-in-the-blank: ___ + 23456 = 56789 or 78901 - ___ = 45678. Answer is the missing number.",
            "c4_addsub5_error": "A student added or subtracted two 5-digit numbers and got a WRONG answer. The error must involve carrying/borrowing mistake. Ask student to find and correct.",
            "c4_addsub5_thinking": "Multi-step reasoning about 5-digit addition/subtraction. Example: estimate the sum, compare two expressions, or explain which is greater.",
        }
        return (
            f"format: {_fmt}. "
            f"Topic: Addition and subtraction (5-digit). skill: {_skill_tag}. "
            f"{c4_addsub_instructions.get(_skill_tag, 'About 5-digit add/sub.')} "
            "Use numbers in range 10000-99999. "
            "DO NOT repeat the same numbers or scenarios. Each question must use DIFFERENT numbers and contexts."
        )

    # Multiplication (3-digit x 2-digit)
    if _skill_tag in ("c4_mult_setup", "c4_mult_word_problem",
                       "c4_mult_missing", "c4_mult_error", "c4_mult_thinking"):
        c4_mult_ctx = (
            "Topic: Multiplication (3-digit × 2-digit). "
            "ONLY use multiplication (×). "
            "Do NOT use addition, subtraction, carry, borrow, column form, +, -. "
            "DO NOT repeat the same numbers or scenarios. Each question must use DIFFERENT numbers and contexts. "
        )
        c4_mult_map = {
            "c4_mult_setup": "Compute the product. Example: 'What is 234 × 56?' Answer is the product.",
            "c4_mult_word_problem": "format: word_problem. Real-world scenario using multi-digit multiplication. Use 3-digit × 1-digit or 3-digit × 2-digit.",
            "c4_mult_missing": "format: fill_blank. Fill-in-the-blank multiplication. Example: '___ × 45 = 5400' or '120 × ___ = 3600'. Answer is the missing number.",
            "c4_mult_error": "format: error_spot. Show a student who got a multi-digit multiplication WRONG. The wrong product and correct product MUST be different. Answer must be the CORRECT product.",
            "c4_mult_thinking": "format: multi_step. Reasoning about multiplication — e.g., 'Which is greater: 125 × 32 or 250 × 16? Explain.' NOT pure computation.",
        }
        return c4_mult_ctx + c4_mult_map.get(_skill_tag, "About multi-digit multiplication.")

    # Division (long division)
    if _skill_tag in ("c4_div_setup", "c4_div_word_problem",
                       "c4_div_missing", "c4_div_error", "c4_div_thinking"):
        c4_div_ctx = (
            "Topic: Division (long division). "
            "ONLY use division (÷). "
            "Use 3-digit ÷ 1-digit (divisor 2-9). May have remainder. "
            "Do NOT use addition, subtraction, carry, borrow, +, -. "
            "DO NOT repeat the same numbers or scenarios. Each question must use DIFFERENT numbers and contexts. "
        )
        c4_div_map = {
            "c4_div_setup": "Compute the quotient and remainder. Example: 'What is 456 ÷ 7?' Answer: quotient = 65, remainder = 1.",
            "c4_div_word_problem": "format: word_problem. Real-world equal sharing/grouping scenario using long division. Include remainder if applicable.",
            "c4_div_missing": "format: fill_blank. Fill-in-the-blank division. Example: '___ ÷ 8 = 45 remainder 3' or '567 ÷ ___ = 81'. Answer is the missing number.",
            "c4_div_error": "format: error_spot. Show a student who got a long division WRONG. Common errors: wrong quotient digit, subtraction mistake in steps. Answer must be the CORRECT quotient.",
            "c4_div_thinking": "format: multi_step. Reasoning about division — e.g., 'Will 789 ÷ 6 have a remainder? How do you know?' NOT pure computation.",
        }
        return c4_div_ctx + c4_div_map.get(_skill_tag, "About long division.")

    # Fractions (equivalent, comparison)
    if _skill_tag in ("c4_fraction_identify", "c4_fraction_compare",
                       "c4_fraction_equivalent", "c4_fraction_represent",
                       "c4_fraction_error", "c4_fraction_thinking"):
        _fmt = (directive or {}).get("format_hint", "fraction_number")
        c4_frac_instructions = {
            "c4_fraction_identify": "Identify a fraction from a picture or description. Use proper fractions (numerator < denominator). Denominators: 2-12.",
            "c4_fraction_compare": "Compare two fractions. Use same denominator or convert to common denominator. Example: Which is greater: 3/4 or 2/3?",
            "c4_fraction_equivalent": "Find equivalent fractions. Example: 1/2 = ?/6 or 2/3 = 4/?. Multiply or divide both numerator and denominator by same number.",
            "c4_fraction_represent": "Fill-in-the-blank with equivalent fraction or simplification. Example: 4/8 = ___/2 or 6/9 simplified = ___.",
            "c4_fraction_error": "A student made a WRONG statement about equivalent fractions or comparison. Ask student to find and correct the mistake.",
            "c4_fraction_thinking": "Multi-step fraction reasoning. Example: arrange fractions in order, find fraction between two given fractions, or real-world problem with equivalent fractions.",
        }
        return (
            f"format: {_fmt}. "
            f"Topic: Fractions (equivalent, comparison). skill: {_skill_tag}. "
            f"{c4_frac_instructions.get(_skill_tag, 'About fractions.')} "
            "Use proper fractions with denominators 2-12. "
            "Do NOT use decimals, percentages, or mixed numbers. "
            "DO NOT repeat the same numbers or scenarios. Each question must use DIFFERENT numbers and contexts."
        )

    # Decimals (tenths, hundredths)
    if _skill_tag in ("c4_decimal_identify", "c4_decimal_compare",
                       "c4_decimal_word_problem", "c4_decimal_represent",
                       "c4_decimal_error", "c4_decimal_thinking"):
        _fmt = (directive or {}).get("format_hint", "place_value_question")
        c4_dec_instructions = {
            "c4_decimal_identify": "Identify the decimal place value. Example: 'In 3.45, what digit is in the tenths place?' or 'Write 7 tenths as a decimal.'",
            "c4_decimal_compare": "Compare two decimals using > or <. Example: Which is greater: 0.45 or 0.5? Always compare with same number of decimal places.",
            "c4_decimal_word_problem": "Word problem involving decimals in measurement or money context. Example: 'A pencil is 12.5 cm and a pen is 13.2 cm. Which is longer?'",
            "c4_decimal_represent": "Write a decimal in expanded form. Example: 4.56 = 4 + 0.5 + 0.06. Or convert fraction to decimal: 3/10 = ?",
            "c4_decimal_error": "A student made a WRONG statement about decimals. Example: '0.5 < 0.45 because 5 < 45'. Ask student to find and correct the mistake.",
            "c4_decimal_thinking": "Multi-step decimal reasoning. Example: 'Arrange these decimals in order: 0.5, 0.45, 0.54' or 'Which fraction equals 0.25?'",
        }
        return (
            f"format: {_fmt}. "
            f"Topic: Decimals (tenths, hundredths). skill: {_skill_tag}. "
            f"{c4_dec_instructions.get(_skill_tag, 'About decimals.')} "
            "Use decimals with 1-2 decimal places only (tenths, hundredths). "
            "Do NOT use fractions with denominators other than 10 or 100. "
            "DO NOT repeat the same numbers or scenarios. Each question must use DIFFERENT numbers and contexts."
        )

    # Geometry (angles, lines)
    if _skill_tag in ("c4_geometry_identify", "c4_geometry_classify",
                       "c4_geometry_represent", "c4_geometry_error", "c4_geometry_thinking"):
        _fmt = (directive or {}).get("format_hint", "simple_identify")
        c4_geo_instructions = {
            "c4_geometry_identify": "Identify types of angles (acute, right, obtuse, straight) or lines (parallel, perpendicular, intersecting).",
            "c4_geometry_classify": "Classify a given angle or pair of lines. Example: 'An angle of 120° is _____ (acute/right/obtuse).'",
            "c4_geometry_represent": "Draw or describe a geometric figure with specific properties. Example: 'Draw a shape with exactly 2 right angles.'",
            "c4_geometry_error": "A student made a WRONG classification of an angle or line type. Ask student to find and correct the mistake.",
            "c4_geometry_thinking": "Multi-step geometric reasoning. Example: 'A triangle has one right angle and one 45° angle. What is the third angle?'",
        }
        return (
            f"format: {_fmt}. "
            f"Topic: Geometry (angles, lines). skill: {_skill_tag}. "
            f"{c4_geo_instructions.get(_skill_tag, 'About geometry.')} "
            "Use acute (<90°), right (90°), obtuse (>90°), straight (180°) angles. "
            "Use parallel, perpendicular, and intersecting lines. "
            "Do NOT use arithmetic, fractions, or decimals. "
            "DO NOT repeat the same scenarios. Each question must use DIFFERENT shapes and angles."
        )

    # Perimeter and area
    if _skill_tag in ("c4_perimeter_identify", "c4_perimeter_word_problem",
                       "c4_area_word_problem", "c4_perimeter_area_missing",
                       "c4_perimeter_area_error", "c4_perimeter_area_thinking"):
        _fmt = (directive or {}).get("format_hint", "simple_identify")
        c4_pa_instructions = {
            "c4_perimeter_identify": "State the formula and compute perimeter of a rectangle or square. Use whole number dimensions (cm or m).",
            "c4_perimeter_word_problem": "Word problem about perimeter. Example: 'A garden is 12 m long and 8 m wide. How much fencing is needed?'",
            "c4_area_word_problem": "Word problem about area. Example: 'A room is 5 m long and 4 m wide. What is the area of the floor?'",
            "c4_perimeter_area_missing": "Fill-in-the-blank. Example: 'A rectangle has length 10 cm and perimeter 30 cm. Width = ___ cm.'",
            "c4_perimeter_area_error": "A student computed perimeter or area WRONG. Common error: confusing perimeter with area or using wrong formula.",
            "c4_perimeter_area_thinking": "Multi-step reasoning. Example: 'Two rectangles have the same perimeter. One is 10×5, the other is 8×7. Which has greater area?'",
        }
        return (
            f"format: {_fmt}. "
            f"Topic: Perimeter and area. skill: {_skill_tag}. "
            f"{c4_pa_instructions.get(_skill_tag, 'About perimeter and area.')} "
            "Use rectangles and squares only. Dimensions in whole numbers (cm or m). "
            "Perimeter = 2 × (L + W). Area = L × W. "
            "Do NOT use fractions, decimals, or angles. "
            "DO NOT repeat the same dimensions. Each question must use DIFFERENT numbers."
        )

    # Time (minutes, 24-hour clock)
    if _skill_tag in ("c4_time_reading", "c4_time_word_problem",
                       "c4_time_convert", "c4_time_missing",
                       "c4_time_error", "c4_time_thinking"):
        c4_time_ctx = (
            "Topic: Time (minutes, 24-hour clock). "
            "Generate ONLY time-related questions. "
            "Use 24-hour clock format and minutes. "
            "Do NOT use addition/subtraction of plain numbers, carry, regroup, "
            "column form, base ten, place value, estimation, rounding. "
            "DO NOT repeat the same numbers or scenarios. Each question must use DIFFERENT times. "
        )
        c4_time_map = {
            "c4_time_reading": "Read a 24-hour clock. Example: 'What is 15:45 in 12-hour format?' or 'A clock shows 2:30 PM. Write in 24-hour format.'",
            "c4_time_word_problem": "Word problem about duration in hours and minutes. Example: 'A train departs at 14:30 and arrives at 17:15. How long is the journey?'",
            "c4_time_convert": "Convert between 12-hour and 24-hour format. Example: '3:45 PM = ___:___ (24-hour)' or '20:15 = ___:___ PM.'",
            "c4_time_missing": "Fill-in-the-blank about time. Example: '2 hours 30 minutes = ___ minutes' or 'From 09:15 to 11:45 = ___ hours ___ minutes.'",
            "c4_time_error": "A student made a WRONG time conversion or duration calculation. Example: 'Rani said 15:00 is 5 PM' (wrong — it is 3 PM). Ask student to correct.",
            "c4_time_thinking": "Multi-step time reasoning. Example: scheduling multiple events, finding overlap, or calculating total duration across midnight.",
        }
        return c4_time_ctx + c4_time_map.get(_skill_tag, "About 24-hour time.")

    # Money (bills, profit/loss)
    if _skill_tag in ("c4_money_identify", "c4_money_word_problem",
                       "c4_money_profit_loss", "c4_money_missing",
                       "c4_money_error", "c4_money_thinking"):
        _fmt = (directive or {}).get("format_hint", "money_question")
        c4_money_instructions = {
            "c4_money_identify": "Identify denominations of Indian currency notes and coins. State the total value of a set of notes/coins.",
            "c4_money_word_problem": "Word problem about buying, selling, making bills. Use realistic prices. VERIFY: total cost < payment amount when computing change.",
            "c4_money_profit_loss": "Profit/loss problem. Cost Price (CP) and Selling Price (SP). Profit = SP - CP (when SP > CP). Loss = CP - SP (when CP > SP).",
            "c4_money_missing": "Fill-in-the-blank. Example: 'CP = ₹450, SP = ₹520. Profit = ₹___' or '₹200 + ₹350 + ₹150 = ₹___.'",
            "c4_money_error": "A student calculated profit/loss or change WRONG. Common error: subtracting in wrong direction, forgetting to multiply by quantity.",
            "c4_money_thinking": "Multi-step money reasoning. Example: comparing two deals, budgeting for multiple items, or deciding if there is profit or loss.",
        }
        return (
            f"format: {_fmt}. "
            f"Topic: Money (bills, profit/loss). skill: {_skill_tag}. "
            f"{c4_money_instructions.get(_skill_tag, 'About money.')} "
            "Use rupees (₹) with realistic prices. "
            "Do NOT use plain arithmetic without money context. "
            "DO NOT repeat the same numbers or scenarios. Each question must use DIFFERENT numbers and contexts."
        )

    # ── Class 1: Numbers 1 to 50 ──
    if _skill_tag in ("c1_count_identify", "c1_number_compare", "c1_number_order",
                       "c1_number_error", "c1_number_think"):
        _fmt = (directive or {}).get("format_hint", "simple_identify")
        c1_num_small = {
            "c1_count_identify": "Count objects or identify the number shown. Numbers 1-50 only.",
            "c1_number_compare": "Compare two numbers (1-50). Which is greater? Which is smaller?",
            "c1_number_order": "Arrange 3-4 numbers (1-50) from smallest to largest or largest to smallest.",
            "c1_number_error": "Find the mistake in counting or ordering numbers 1-50. Show a student who counted WRONG. Answer must be the correct count.",
            "c1_number_think": "Reasoning about numbers 1-50. What comes before/after? What is between two numbers?",
        }
        return (
            f"format: {_fmt}. "
            f"Topic: Numbers 1 to 50 (Class 1). skill: {_skill_tag}. "
            f"{c1_num_small.get(_skill_tag, 'About numbers 1-50.')} "
            "GRADE 1 ONLY: Numbers 1-50. No addition, subtraction, multiplication, division. "
            "Use simple, child-friendly language. Names: Amma, Dadi, Raju, Meena, Bablu, Priya. "
            "DO NOT repeat the same numbers or scenarios."
        )

    # ── Class 1: Numbers 51 to 100 ──
    if _skill_tag in ("c1_count_big_identify", "c1_number_big_compare", "c1_number_big_order",
                       "c1_number_big_error", "c1_number_big_think"):
        _fmt = (directive or {}).get("format_hint", "simple_identify")
        c1_num_big = {
            "c1_count_big_identify": "Count objects or identify the number shown. Numbers 51-100 only.",
            "c1_number_big_compare": "Compare two numbers (51-100). Which is greater? Which is smaller?",
            "c1_number_big_order": "Arrange 3-4 numbers (51-100) from smallest to largest or largest to smallest.",
            "c1_number_big_error": "Find the mistake in counting or ordering numbers 51-100. Show a student who counted WRONG. Answer must be the correct count.",
            "c1_number_big_think": "Reasoning about numbers 51-100. What comes before/after? What is between two numbers?",
        }
        return (
            f"format: {_fmt}. "
            f"Topic: Numbers 51 to 100 (Class 1). skill: {_skill_tag}. "
            f"{c1_num_big.get(_skill_tag, 'About numbers 51-100.')} "
            "GRADE 1 ONLY: Numbers 51-100. No addition, subtraction, multiplication, division. "
            "Use simple, child-friendly language. Names: Amma, Dadi, Raju, Meena, Bablu, Priya. "
            "DO NOT repeat the same numbers or scenarios."
        )

    # ── Class 1: Addition up to 20 ──
    if _skill_tag in ("c1_add_basic", "c1_add_word_problem", "c1_add_missing",
                       "c1_add_error", "c1_add_think"):
        _fmt = (directive or {}).get("format_hint", "simple_identify")
        c1_add_ctx = (
            "Topic: Addition up to 20 (Class 1). "
            "Both numbers must be between 1 and 10. Sum must NEVER exceed 20. "
            "NO carrying. NO column form. Simple horizontal: 7 + 5 = ___. "
            "Use simple, child-friendly language. Names: Amma, Dadi, Raju, Meena, Bablu, Priya. "
            "DO NOT repeat the same numbers or scenarios. "
        )
        if _skill_tag == "c1_add_basic":
            return c1_add_ctx + "Present a simple addition problem. Example: What is 7 + 5? Answer: 12."
        elif _skill_tag == "c1_add_word_problem":
            return c1_add_ctx + "format: word_problem. Single-step word problem about adding small numbers. Use toys, animals, fruits, classroom objects."
        elif _skill_tag == "c1_add_missing":
            return c1_add_ctx + "format: missing_number. Fill-in-the-blank: '___ + 5 = 12' or '7 + ___ = 13'. Answer is the missing number."
        elif _skill_tag == "c1_add_error":
            return c1_add_ctx + "format: error_spot. Show a student who added two small numbers INCORRECTLY. Example: 'Bablu says 8 + 5 = 12. Is he correct?' Answer must be the CORRECT sum."
        elif _skill_tag == "c1_add_think":
            return c1_add_ctx + "format: multi_step. Reasoning about addition — e.g., 'Raju has 6 marbles. Meena gives him some more. Now he has 11. How many did Meena give?' NOT pure computation."
        return c1_add_ctx

    # ── Class 1: Subtraction within 20 ──
    if _skill_tag in ("c1_sub_basic", "c1_sub_word_problem", "c1_sub_missing",
                       "c1_sub_error", "c1_sub_think"):
        _fmt = (directive or {}).get("format_hint", "simple_identify")
        c1_sub_ctx = (
            "Topic: Subtraction within 20 (Class 1). "
            "Both numbers between 1 and 20. Result must NEVER be negative. NO borrowing. NO column form. "
            "First number must always be LARGER than the second. Simple horizontal: 15 - 7 = ___. "
            "Use simple, child-friendly language. Names: Amma, Dadi, Raju, Meena, Bablu, Priya. "
            "DO NOT repeat the same numbers or scenarios. "
        )
        if _skill_tag == "c1_sub_basic":
            return c1_sub_ctx + "Present a simple subtraction problem. Example: What is 15 - 7? Answer: 8."
        elif _skill_tag == "c1_sub_word_problem":
            return c1_sub_ctx + "format: word_problem. Single-step word problem about taking away small numbers. Use toys, animals, fruits, classroom objects."
        elif _skill_tag == "c1_sub_missing":
            return c1_sub_ctx + "format: missing_number. Fill-in-the-blank: '15 - ___ = 8' or '___ - 7 = 8'. Answer is the missing number."
        elif _skill_tag == "c1_sub_error":
            return c1_sub_ctx + "format: error_spot. Show a student who subtracted INCORRECTLY. Example: 'Priya says 14 - 6 = 9. Is she correct?' Answer must be the CORRECT difference."
        elif _skill_tag == "c1_sub_think":
            return c1_sub_ctx + "format: multi_step. Reasoning about subtraction — e.g., 'Meena had 18 flowers. She gave some to Dadi. Now she has 11. How many did she give?' NOT pure computation."
        return c1_sub_ctx

    # ── Class 1: Basic Shapes ──
    if _skill_tag in ("c1_shape_identify", "c1_shape_match", "c1_shape_count",
                       "c1_shape_error", "c1_shape_think"):
        c1_shape_ctx = (
            "Topic: Basic Shapes (Class 1). "
            "ONLY use: circle, square, triangle, rectangle. NO 3D shapes (cube, sphere, cone). "
            "Focus on shape names, counting sides and corners, real-world shape examples. "
            "NO addition, subtraction, multiplication, division. "
            "Use simple, child-friendly language. Names: Amma, Dadi, Raju, Meena, Bablu, Priya. "
            "DO NOT repeat the same shapes or scenarios. "
        )
        if _skill_tag == "c1_shape_identify":
            return c1_shape_ctx + "Identify a shape by its properties. Example: 'I have 3 sides and 3 corners. What shape am I?' Answer: Triangle."
        elif _skill_tag == "c1_shape_match":
            return c1_shape_ctx + "format: word_problem. Match a real-world object to its shape. Example: 'A wheel is shaped like a ___.' Answer: Circle."
        elif _skill_tag == "c1_shape_count":
            return c1_shape_ctx + "format: missing_number. Fill-in-the-blank about shapes. Example: 'A square has ___ sides.' Answer: 4."
        elif _skill_tag == "c1_shape_error":
            return c1_shape_ctx + "format: error_spot. Show a student who made a WRONG claim about a shape. Example: 'Raju says a circle has 2 sides. Is he correct?' Answer must be the correct fact."
        elif _skill_tag == "c1_shape_think":
            return c1_shape_ctx + "format: multi_step. Reasoning about shapes. Example: 'How many corners do 2 triangles have in total?' Answer: 6."
        return c1_shape_ctx

    # ── Class 1: Measurement ──
    if _skill_tag in ("c1_measure_compare", "c1_measure_order", "c1_measure_fill",
                       "c1_measure_error", "c1_measure_think"):
        c1_meas_ctx = (
            "Topic: Measurement (Class 1). "
            "Compare objects: longer/shorter, taller/shorter, heavier/lighter. "
            "NO standard units (no cm, m, kg, g). Use comparison words ONLY. "
            "NO addition, subtraction, multiplication, division. "
            "Use simple, child-friendly language. Names: Amma, Dadi, Raju, Meena, Bablu, Priya. "
            "DO NOT repeat the same objects or scenarios. "
        )
        if _skill_tag == "c1_measure_compare":
            return c1_meas_ctx + "Compare two objects. Example: 'Which is longer: a pencil or a crayon?' Answer: pencil."
        elif _skill_tag == "c1_measure_order":
            return c1_meas_ctx + "format: comparison_question. Arrange 3 objects from shortest to tallest, or lightest to heaviest."
        elif _skill_tag == "c1_measure_fill":
            return c1_meas_ctx + "format: missing_number. Fill-in-the-blank: 'An elephant is ___ (heavier/lighter) than a cat.' Answer: heavier."
        elif _skill_tag == "c1_measure_error":
            return c1_meas_ctx + "format: error_spot. Show a student who compared objects WRONG. Example: 'Bablu says a feather is heavier than a book. Is he correct?' Answer must state the correct comparison."
        elif _skill_tag == "c1_measure_think":
            return c1_meas_ctx + "format: multi_step. Reasoning about measurement. Example: 'Raju is taller than Meena. Meena is taller than Bablu. Who is the shortest?' Answer: Bablu."
        return c1_meas_ctx

    # ── Class 1: Time ──
    if _skill_tag in ("c1_time_identify", "c1_time_sequence", "c1_time_fill",
                       "c1_time_error", "c1_time_think"):
        c1_time_ctx = (
            "Topic: Time (Class 1). "
            "Day routines ONLY: morning, afternoon, evening, night. Days of the week. "
            "NO clock reading. NO hours or minutes. NO numbers for time. "
            "NO addition, subtraction, multiplication, division. "
            "Use simple, child-friendly language. Names: Amma, Dadi, Raju, Meena, Bablu, Priya. "
            "DO NOT repeat the same routines or scenarios. "
        )
        if _skill_tag == "c1_time_identify":
            return c1_time_ctx + "Identify the time of day for an activity. Example: 'We eat breakfast in the ___.' Answer: morning."
        elif _skill_tag == "c1_time_sequence":
            return c1_time_ctx + "format: word_problem. Put daily activities in the correct order. Example: 'What comes first — lunch or breakfast?'"
        elif _skill_tag == "c1_time_fill":
            return c1_time_ctx + "format: missing_number. Fill-in-the-blank about days or routines. Example: 'The day after Monday is ___.' Answer: Tuesday."
        elif _skill_tag == "c1_time_error":
            return c1_time_ctx + "format: error_spot. Show a student who got the order WRONG. Example: 'Meena says we brush our teeth at night before dinner. Is she correct?' Answer must state the correct routine."
        elif _skill_tag == "c1_time_think":
            return c1_time_ctx + "format: multi_step. Reasoning about time. Example: 'If today is Wednesday, what day was yesterday? What day will tomorrow be?'"
        return c1_time_ctx

    # ── Class 1: Money ──
    if _skill_tag in ("c1_money_identify", "c1_money_count", "c1_money_fill",
                       "c1_money_error", "c1_money_think"):
        c1_money_ctx = (
            "Topic: Money (Class 1). "
            "Indian coins ONLY: ₹1, ₹2, ₹5. NO notes. Total must NEVER exceed ₹20. "
            "Simple counting of coins. "
            "NO multiplication, division, fractions. "
            "Use simple, child-friendly language. Names: Amma, Dadi, Raju, Meena, Bablu, Priya. "
            "DO NOT repeat the same amounts or scenarios. "
        )
        if _skill_tag == "c1_money_identify":
            return c1_money_ctx + "Identify coins or count a small group. Example: 'How much money is 3 one-rupee coins?' Answer: ₹3."
        elif _skill_tag == "c1_money_count":
            return c1_money_ctx + "format: word_problem. Simple buying scenario with coins. Example: 'Raju has two ₹5 coins. How much money does he have?' Answer: ₹10."
        elif _skill_tag == "c1_money_fill":
            return c1_money_ctx + "format: missing_number. Fill-in-the-blank: 'Meena has ₹5 and ₹2 coins. She has ___ rupees in total.' Answer: ₹7."
        elif _skill_tag == "c1_money_error":
            return c1_money_ctx + "format: error_spot. Show a student who counted coins WRONG. Example: 'Bablu has three ₹2 coins. He says he has ₹8. Is he correct?' Answer must be the CORRECT total (₹6)."
        elif _skill_tag == "c1_money_think":
            return c1_money_ctx + "format: multi_step. Reasoning about money. Example: 'Priya has ₹10. A toffee costs ₹2. Can she buy 4 toffees? Why?' NOT pure computation."
        return c1_money_ctx

    # ── Class 2: Numbers up to 1000 ──
    if _skill_tag in ("c2_place_value_identify", "c2_number_compare", "c2_number_expansion",
                       "c2_number_ordering", "c2_place_value_error", "c2_number_thinking"):
        _fmt = (directive or {}).get("format_hint", "place_value_question")
        c2_num_instructions = {
            "c2_place_value_identify": "Identify place value (ones, tens, hundreds) in 3-digit numbers (100-999).",
            "c2_number_compare": "Compare two 3-digit numbers using > or <. Example: Which is greater: 453 or 435?",
            "c2_number_expansion": "Write a 3-digit number in expanded form. Example: 453 = 400 + 50 + 3",
            "c2_number_ordering": "Arrange 3-digit numbers in ascending or descending order.",
            "c2_place_value_error": "Find the mistake in identifying place value of a 3-digit number.",
            "c2_number_thinking": "Multi-step reasoning about 3-digit numbers. Example: What is 10 more than 453?",
        }
        return (
            f"format: {_fmt}. "
            f"Topic: Numbers up to 1000 (Class 2). skill: {_skill_tag}. "
            f"{c2_num_instructions.get(_skill_tag, 'About 3-digit numbers.')} "
            "Use numbers 100-999 ONLY. NEVER use 4-digit numbers or numbers above 999. "
            "Do NOT use addition/subtraction operations, money, time, fractions. "
            "DO NOT repeat the same numbers or scenarios. Each question must use DIFFERENT numbers and contexts."
        )

    # ── Class 2: Addition (2-digit with carry) ──
    if _skill_tag in ("c2_add_column", "c2_add_word_problem", "c2_add_missing_number",
                       "c2_add_error_spot", "c2_add_thinking"):
        _fmt = (directive or {}).get("format_hint", "column_setup")
        c2_add_instructions = {
            "c2_add_column": "Present a 2-digit addition problem in column form. Both numbers 10-99. Require carrying from ones to tens.",
            "c2_add_word_problem": "Word problem about adding two 2-digit numbers. Include a character name, context, and clear question. Require carrying.",
            "c2_add_missing_number": "Fill-in-the-blank: '___ + 27 = 54' or '38 + ___ = 65'. Answer is the missing number.",
            "c2_add_error_spot": "Show a student who added two 2-digit numbers INCORRECTLY (forgot the carry). Ask student to find and correct the mistake.",
            "c2_add_thinking": "Reasoning about 2-digit addition — e.g., 'Is 47 + 38 closer to 80 or 90? Explain.' NOT pure computation.",
        }
        return (
            f"format: {_fmt}. "
            f"Topic: Addition (2-digit with carry). skill: {_skill_tag}. "
            f"{c2_add_instructions.get(_skill_tag, 'About 2-digit addition.')} "
            "Use 2-digit numbers (10-99) ONLY. NEVER use 3-digit numbers. "
            "Numbers MUST require carrying (ones digits sum >= 10). "
            "DO NOT repeat the same numbers or scenarios."
        )

    # ── Class 2: Subtraction (2-digit with borrow) ──
    if _skill_tag in ("c2_sub_column", "c2_sub_word_problem", "c2_sub_missing_number",
                       "c2_sub_error_spot", "c2_sub_thinking"):
        _fmt = (directive or {}).get("format_hint", "column_setup")
        c2_sub_instructions = {
            "c2_sub_column": "Present a 2-digit subtraction in column form. Both numbers 10-99. Require borrowing.",
            "c2_sub_word_problem": "Word problem about subtracting two 2-digit numbers. Include a character name and context. Require borrowing.",
            "c2_sub_missing_number": "Fill-in-the-blank: '63 - ___ = 27' or '___ - 18 = 45'. Answer is the missing number.",
            "c2_sub_error_spot": "Show a student who subtracted two 2-digit numbers INCORRECTLY (forgot to borrow). Ask student to find and correct the mistake.",
            "c2_sub_thinking": "Reasoning about 2-digit subtraction — e.g., 'Is 73 - 48 more or less than 30? Explain.' NOT pure computation.",
        }
        return (
            f"format: {_fmt}. "
            f"Topic: Subtraction (2-digit with borrow). skill: {_skill_tag}. "
            f"{c2_sub_instructions.get(_skill_tag, 'About 2-digit subtraction.')} "
            "Use 2-digit numbers (10-99) ONLY. NEVER use 3-digit numbers. "
            "Numbers MUST require borrowing (ones digit of top number < ones digit of bottom number). "
            "DO NOT repeat the same numbers or scenarios."
        )

    # ── Class 2: Multiplication (tables 2-5) ──
    if _skill_tag in ("c2_mult_tables", "c2_mult_word_problem", "c2_mult_fill_blank",
                       "c2_mult_error_spot", "c2_mult_thinking"):
        c2_mult_ctx = (
            "Topic: Multiplication tables (2-5) Class 2. "
            "ONLY use tables 2, 3, 4, 5. NEVER use tables 6-10. "
            "ONLY use multiplication (x). "
            "Do NOT use addition, subtraction, carry, borrow, column form, +, -. "
            "DO NOT repeat the same numbers or scenarios. "
        )
        if _skill_tag == "c2_mult_tables":
            return c2_mult_ctx + "Ask a multiplication fact from tables 2-5 (e.g., 'What is 3 x 4?'). Answer is the product."
        elif _skill_tag == "c2_mult_word_problem":
            return c2_mult_ctx + "format: word_problem. Real-world scenario using multiplication from tables 2-5 only."
        elif _skill_tag == "c2_mult_fill_blank":
            return c2_mult_ctx + "format: fill_blank. Fill-in-the-blank: '___ x 3 = 12' or '4 x ___ = 20'. Answer is the missing number."
        elif _skill_tag == "c2_mult_error_spot":
            return c2_mult_ctx + "format: error_spot. Show a student who got a multiplication fact from tables 2-5 WRONG. Answer must be the CORRECT product."
        elif _skill_tag == "c2_mult_thinking":
            return c2_mult_ctx + "format: multi_step. Reasoning about multiplication — e.g., 'Which is greater: 3 x 5 or 4 x 4? Explain.' NOT pure computation."
        return c2_mult_ctx

    # ── Class 2: Division (sharing equally) ──
    if _skill_tag in ("c2_div_sharing", "c2_div_word_problem", "c2_div_fill_blank",
                       "c2_div_error_spot", "c2_div_thinking"):
        c2_div_ctx = (
            "Topic: Division (sharing equally) Class 2. "
            "ONLY use division by 2, 3, 4, 5. NEVER use divisors above 5. "
            "All divisions must be EXACT (no remainders). "
            "Do NOT use addition, subtraction, carry, borrow. "
            "DO NOT repeat the same numbers or scenarios. "
        )
        if _skill_tag == "c2_div_sharing":
            return c2_div_ctx + "Ask about sharing equally (e.g., '12 sweets shared among 3 children. How many each?'). Answer is the quotient."
        elif _skill_tag == "c2_div_word_problem":
            return c2_div_ctx + "format: word_problem. Real-world equal sharing problem. Dividends up to 50."
        elif _skill_tag == "c2_div_fill_blank":
            return c2_div_ctx + "format: fill_blank. Fill-in-the-blank: '___ / 4 = 5' or '20 / ___ = 4'. Answer is the missing number."
        elif _skill_tag == "c2_div_error_spot":
            return c2_div_ctx + "format: error_spot. Show a student who got a sharing/division answer WRONG. Answer must be the CORRECT quotient."
        elif _skill_tag == "c2_div_thinking":
            return c2_div_ctx + "format: multi_step. Reasoning about division — e.g., 'Aarav has 20 stickers. He shares equally among some friends and each gets 5. How many friends?' NOT pure computation."
        return c2_div_ctx

    # ── Class 2: Shapes and space (2D) ──
    if _skill_tag in ("c2_shape_identify", "c2_shape_word_problem", "c2_shape_fill_blank",
                       "c2_shape_error_spot", "c2_shape_thinking"):
        c2_shape_ctx = (
            "Topic: Shapes and space (2D) Class 2. "
            "ONLY use basic 2D shapes: circle, square, triangle, rectangle. "
            "Focus on sides, corners, shape names, real-world shape examples. "
            "Do NOT use addition, subtraction, multiplication, division. "
            "DO NOT repeat the same shapes or scenarios. "
        )
        if _skill_tag == "c2_shape_identify":
            return c2_shape_ctx + "Identify a 2D shape by its properties (e.g., 'I have 3 sides and 3 corners. What shape am I?')."
        elif _skill_tag == "c2_shape_word_problem":
            return c2_shape_ctx + "format: word_problem. Count sides or corners, or identify shapes in real-world objects."
        elif _skill_tag == "c2_shape_fill_blank":
            return c2_shape_ctx + "format: fill_blank. Fill-in-the-blank about shapes. Example: 'A rectangle has ___ sides.' or 'A triangle has ___ corners.'"
        elif _skill_tag == "c2_shape_error_spot":
            return c2_shape_ctx + "format: error_spot. Show a student who made a WRONG claim about a shape. Example: 'Priya says a triangle has 4 sides. Is she correct?' Answer must be the correct fact."
        elif _skill_tag == "c2_shape_thinking":
            return c2_shape_ctx + "format: multi_step. Reasoning about shapes — e.g., 'How many corners in total do 2 triangles and 1 square have?' NOT pure computation."
        return c2_shape_ctx

    # ── Class 2: Measurement (length, weight) ──
    if _skill_tag in ("c2_measure_identify", "c2_measure_compare", "c2_measure_fill_blank",
                       "c2_measure_error_spot", "c2_measure_thinking"):
        c2_meas_ctx = (
            "Topic: Measurement (length, weight) Class 2. "
            "Use cm, m for length and g, kg for weight. "
            "Keep numbers simple (up to 100 for cm/g, up to 10 for m/kg). "
            "Do NOT use addition, subtraction, multiplication, division as standalone. "
            "DO NOT repeat the same items or scenarios. "
        )
        if _skill_tag == "c2_measure_identify":
            return c2_meas_ctx + "Identify the correct unit for measuring an object. Example: 'Would you use cm or m to measure the length of a pencil?'"
        elif _skill_tag == "c2_measure_compare":
            return c2_meas_ctx + "format: comparison_question. Compare two measurements. Example: 'Which is longer: 50 cm or 1 m?'"
        elif _skill_tag == "c2_measure_fill_blank":
            return c2_meas_ctx + "format: fill_blank. Fill-in-the-blank: '1 m = ___ cm' or '1 kg = ___ g'."
        elif _skill_tag == "c2_measure_error_spot":
            return c2_meas_ctx + "format: error_spot. Show a student who used the WRONG unit or made a measurement comparison error. Answer must be the correct measurement."
        elif _skill_tag == "c2_measure_thinking":
            return c2_meas_ctx + "format: multi_step. Reasoning about measurement — e.g., 'Rohan is 120 cm tall. His sister is 95 cm. Who is taller and by how much?' NOT pure unit recall."
        return c2_meas_ctx

    # ── Class 2: Time (hour, half-hour) ──
    if _skill_tag in ("c2_clock_reading", "c2_time_word_problem", "c2_time_fill_blank",
                       "c2_time_error_spot", "c2_time_thinking"):
        c2_time_ctx = (
            "Topic: Time (hour, half-hour) Class 2. "
            "ONLY use o'clock and half past times. "
            "NEVER use quarter-hours, 15 minutes, or specific minutes. "
            "Do NOT use addition, subtraction, carry, regroup, base ten, place value. "
            "DO NOT repeat the same times or scenarios. "
        )
        if _skill_tag == "c2_clock_reading":
            return c2_time_ctx + "Ask about reading clocks showing o'clock or half past only. Example: 'The hour hand is on 3 and the minute hand is on 12. What time is it?'"
        elif _skill_tag == "c2_time_word_problem":
            return c2_time_ctx + "format: word_problem. Simple time scenario using o'clock or half past. Example: 'School starts at 8 o'clock. Lunch is at 12 o'clock. How many hours between?'"
        elif _skill_tag == "c2_time_fill_blank":
            return c2_time_ctx + "format: fill_blank. Fill-in-the-blank: '1 hour = ___ minutes' or 'Half past 3 is the same as 3:___'."
        elif _skill_tag == "c2_time_error_spot":
            return c2_time_ctx + "format: error_spot. Show a student who misread a clock showing o'clock or half past. Answer must be the correct time."
        elif _skill_tag == "c2_time_thinking":
            return c2_time_ctx + "format: multi_step. Reasoning about time — e.g., 'Aarav sleeps at 9 o'clock and wakes up at 6 o'clock. How many hours did he sleep?' Use only o'clock and half past."
        return c2_time_ctx

    # ── Class 2: Money (coins and notes) ──
    if _skill_tag in ("c2_money_identify", "c2_money_word_problem", "c2_money_fill_blank",
                       "c2_money_error_spot", "c2_money_thinking"):
        c2_money_ctx = (
            "Topic: Money (coins and notes) Class 2. "
            "Use coins: 1, 2, 5, 10 rupees. Notes: 10, 20, 50, 100 rupees. "
            "Keep amounts up to 100 rupees. Simple counting, no complex change. "
            "Do NOT use multiplication, division, fractions, or amounts over 100. "
            "DO NOT repeat the same amounts or scenarios. "
        )
        if _skill_tag == "c2_money_identify":
            return c2_money_ctx + "Identify coins/notes or count a small set of coins. Example: 'How much is 2 five-rupee coins and 1 two-rupee coin?'"
        elif _skill_tag == "c2_money_word_problem":
            return c2_money_ctx + "format: word_problem. Simple buying scenario with amounts up to 100 rupees."
        elif _skill_tag == "c2_money_fill_blank":
            return c2_money_ctx + "format: fill_blank. Fill-in-the-blank: '3 ten-rupee notes = Rs ___' or 'Rs 50 - Rs 20 = Rs ___'."
        elif _skill_tag == "c2_money_error_spot":
            return c2_money_ctx + "format: error_spot. Show a student who counted coins/notes INCORRECTLY. Answer must be the correct total."
        elif _skill_tag == "c2_money_thinking":
            return c2_money_ctx + "format: multi_step. Reasoning about money — e.g., 'Priya has Rs 50. She buys a toy for Rs 35. Does she have enough to also buy a pencil for Rs 20? Why?' NOT pure computation."
        return c2_money_ctx

    # ── Class 2: Data handling (pictographs) ──
    if _skill_tag in ("c2_data_read", "c2_data_word_problem", "c2_data_fill_blank",
                       "c2_data_error_spot", "c2_data_thinking"):
        c2_data_ctx = (
            "Topic: Data handling (pictographs) Class 2. "
            "Questions about reading and interpreting pictographs/picture graphs. "
            "Use simple categories (fruits, animals, colours) with symbols representing 1 item each. "
            "Do NOT use addition, subtraction, multiplication, division as standalone topics. "
            "DO NOT repeat the same data sets or scenarios. "
        )
        if _skill_tag == "c2_data_read":
            return c2_data_ctx + "Read a pictograph: describe data in words. Example: 'In a pictograph, apples have 5 symbols and bananas have 3. How many apples are shown?'"
        elif _skill_tag == "c2_data_word_problem":
            return c2_data_ctx + "format: word_problem. Ask a question that requires reading a pictograph to answer — e.g., 'Which fruit is most popular? How many more apples than bananas?'"
        elif _skill_tag == "c2_data_fill_blank":
            return c2_data_ctx + "format: fill_blank. Fill-in-the-blank from a pictograph. Example: 'Red has 4 symbols and Blue has ___. Together they have 7.'"
        elif _skill_tag == "c2_data_error_spot":
            return c2_data_ctx + "format: error_spot. Show a student who misread a pictograph. Example: 'There are 6 symbols for cats but Amit says there are 8. What is wrong?' Answer must be the correct count."
        elif _skill_tag == "c2_data_thinking":
            return c2_data_ctx + "format: multi_step. Reasoning about data — e.g., 'If each symbol stands for 1 child, and Class A has 8 symbols and Class B has 5, which class has more children and by how many?' NOT pure counting."
        return c2_data_ctx


    # ── Class 5 instruction builders ──────────────────────────

    # Numbers up to 10 lakh (Class 5)
    if _skill_tag in ("c5_lakh_identify", "c5_lakh_compare", "c5_lakh_expand",
                       "c5_lakh_error", "c5_lakh_think"):
        _fmt = (directive or {}).get("format_hint", "place_value_question")
        c5_lakh_map = {
            "c5_lakh_identify": "Identify place value in 6-7 digit numbers using Indian system (lakhs, ten-thousands, thousands). Example: 'What is the place value of 3 in 3,45,678?'",
            "c5_lakh_compare": "Compare two large numbers (6-7 digits) using > or <. Example: 'Which is greater: 4,56,789 or 4,65,789?'",
            "c5_lakh_expand": "Write a large number in expanded form using Indian system. Example: 4,56,789 = 4,00,000 + 56,000 + 789.",
            "c5_lakh_error": "A student made a WRONG place value statement about a large number. Ask student to find and correct the mistake.",
            "c5_lakh_think": "Multi-step reasoning about large numbers. Example: 'What number is 10,000 more than 4,56,789? Which digit changes?'",
        }
        return (
            f"format: {_fmt}. "
            f"Topic: Numbers up to 10 lakh (Class 5). skill: {_skill_tag}. "
            f"{c5_lakh_map.get(_skill_tag, 'About large numbers.')} "
            "Use 6-7 digit numbers in Indian system (up to 10,00,000). "
            "Do NOT use addition/subtraction operations, fractions, decimals. "
            "DO NOT repeat the same numbers or scenarios."
        )

    # Factors and multiples (Class 5)
    if _skill_tag in ("c5_factor_identify", "c5_factor_apply", "c5_factor_missing",
                       "c5_factor_error", "c5_factor_think"):
        c5_factor_ctx = (
            "Topic: Factors and multiples (Class 5). "
            "Use numbers up to 100 for factors. "
            "Do NOT use carry, borrow, decimal, percentage. "
            "DO NOT repeat the same numbers or scenarios. "
        )
        c5_factor_map = {
            "c5_factor_identify": "List all factors of a given number. Example: 'What are the factors of 24?' or 'Is 7 a factor of 42?'",
            "c5_factor_apply": "format: word_problem. Real-world scenario using factors/multiples. Example: 'Can 36 students be arranged in equal rows of 8?'",
            "c5_factor_missing": "format: fill_blank. Fill-in-the-blank. Example: 'The first 5 multiples of 6 are: 6, 12, 18, ___, ___.'",
            "c5_factor_error": "format: error_spot. A student listed factors or multiples INCORRECTLY. Ask student to find and correct the mistake.",
            "c5_factor_think": "format: multi_step. Reasoning about factors/multiples. Example: 'Is every multiple of 6 also a multiple of 3? Why?'",
        }
        return c5_factor_ctx + c5_factor_map.get(_skill_tag, "About factors and multiples.")

    # HCF and LCM (Class 5)
    if _skill_tag in ("c5_hcf_identify", "c5_hcf_apply", "c5_hcf_missing",
                       "c5_hcf_error", "c5_hcf_think"):
        c5_hcf_ctx = (
            "Topic: HCF and LCM (Class 5). "
            "Use numbers up to 100. "
            "HCF = Highest Common Factor, LCM = Least Common Multiple. "
            "Do NOT use carry, borrow, decimal, percentage. "
            "DO NOT repeat the same numbers or scenarios. "
        )
        c5_hcf_map = {
            "c5_hcf_identify": "Find the HCF or LCM of two numbers. Example: 'Find the HCF of 12 and 18.' or 'Find the LCM of 4 and 6.'",
            "c5_hcf_apply": "format: word_problem. Real-world scenario using HCF/LCM. Example: 'Two bells ring every 4 and 6 minutes. When do they ring together?'",
            "c5_hcf_missing": "format: fill_blank. Fill-in-the-blank. Example: 'HCF of 24 and 36 = ___' or 'LCM of 5 and 7 = ___.'",
            "c5_hcf_error": "format: error_spot. A student computed HCF or LCM INCORRECTLY. Ask student to find and correct the mistake.",
            "c5_hcf_think": "format: multi_step. Reasoning. Example: 'The HCF of two numbers is 6 and their LCM is 36. If one number is 12, what is the other?'",
        }
        return c5_hcf_ctx + c5_hcf_map.get(_skill_tag, "About HCF and LCM.")

    # Fractions (add and subtract) (Class 5)
    if _skill_tag in ("c5_frac_identify", "c5_frac_apply", "c5_frac_missing",
                       "c5_frac_error", "c5_frac_think"):
        c5_frac_ctx = (
            "Topic: Fractions — add and subtract (Class 5). "
            "Use like and unlike fractions. Denominators up to 20. "
            "For unlike fractions, find LCM of denominators. "
            "Do NOT use decimals or percentages. "
            "DO NOT repeat the same numbers or scenarios. "
        )
        c5_frac_map = {
            "c5_frac_identify": "Identify the operation needed. Example: 'Add 2/5 and 1/5.' or 'What is 3/4 - 1/4?'",
            "c5_frac_apply": "format: word_problem. Real-world problem. Example: 'Riya drank 1/3 litre of milk in the morning and 1/4 litre in the evening. How much in total?'",
            "c5_frac_missing": "format: fill_blank. Fill-in-the-blank. Example: '2/7 + ___ = 5/7' or '3/4 - 1/6 = ___.'",
            "c5_frac_error": "format: error_spot. A student added/subtracted fractions INCORRECTLY (common error: adding denominators). Ask student to correct.",
            "c5_frac_think": "format: multi_step. Multi-step fraction reasoning. Example: 'Aarav ate 1/3 of a cake. Priya ate 1/4. Who ate more? How much is left?'",
        }
        return c5_frac_ctx + c5_frac_map.get(_skill_tag, "About adding/subtracting fractions.")

    # Decimals (all operations) (Class 5)
    if _skill_tag in ("c5_dec_identify", "c5_dec_apply", "c5_dec_missing",
                       "c5_dec_error", "c5_dec_think"):
        c5_dec_ctx = (
            "Topic: Decimals — all operations (Class 5). "
            "Use decimals up to 2 decimal places. "
            "Cover addition, subtraction, multiplication by whole number, simple division. "
            "Do NOT use fractions or percentages. "
            "DO NOT repeat the same numbers or scenarios. "
        )
        c5_dec_map = {
            "c5_dec_identify": "Perform a decimal operation. Example: 'What is 3.45 + 2.7?' or 'What is 5.6 × 3?'",
            "c5_dec_apply": "format: word_problem. Real-world decimal problem. Example: 'A pen costs Rs 12.50 and a notebook costs Rs 35.75. What is the total cost?'",
            "c5_dec_missing": "format: fill_blank. Fill-in-the-blank. Example: '4.5 + ___ = 7.2' or '8.4 - 3.6 = ___.'",
            "c5_dec_error": "format: error_spot. A student made a decimal computation error (common: misaligned decimal point). Ask student to correct.",
            "c5_dec_think": "format: multi_step. Reasoning about decimals. Example: 'Which is greater: 3 × 1.5 or 2 × 2.3? Explain.'",
        }
        return c5_dec_ctx + c5_dec_map.get(_skill_tag, "About decimal operations.")

    # Percentage (Class 5)
    if _skill_tag in ("c5_percent_identify", "c5_percent_apply", "c5_percent_missing",
                       "c5_percent_error", "c5_percent_think"):
        c5_pct_ctx = (
            "Topic: Percentage (Class 5). "
            "Convert fractions/decimals to percentages and vice versa. "
            "Find percentage of a number. Simple discount problems. "
            "Do NOT use complex fractions or multi-step algebra. "
            "DO NOT repeat the same numbers or scenarios. "
        )
        c5_pct_map = {
            "c5_percent_identify": "Convert or compute percentage. Example: 'What is 25% of 80?' or 'Convert 3/4 to a percentage.'",
            "c5_percent_apply": "format: word_problem. Real-world percentage problem. Example: 'A shirt costs Rs 400 and there is a 20% discount. What is the sale price?'",
            "c5_percent_missing": "format: fill_blank. Fill-in-the-blank. Example: '50% of 120 = ___' or '___ % of 200 = 50.'",
            "c5_percent_error": "format: error_spot. A student computed a percentage INCORRECTLY. Example: '25% of 80 = 25' (wrong). Ask student to correct.",
            "c5_percent_think": "format: multi_step. Reasoning about percentages. Example: 'Priya scored 45 out of 60. Aarav scored 38 out of 50. Who scored a higher percentage?'",
        }
        return c5_pct_ctx + c5_pct_map.get(_skill_tag, "About percentages.")

    # Area and volume (Class 5)
    if _skill_tag in ("c5_area_identify", "c5_area_apply", "c5_area_missing",
                       "c5_area_error", "c5_area_think"):
        c5_av_ctx = (
            "Topic: Area and volume (Class 5). "
            "Area of triangle = 1/2 × base × height. Volume of cuboid = l × b × h. Volume of cube = side^3. "
            "Use whole numbers for dimensions (cm, m). "
            "Do NOT use fractions or decimals in dimensions. "
            "DO NOT repeat the same dimensions or scenarios. "
        )
        c5_av_map = {
            "c5_area_identify": "Calculate area or volume. Example: 'Find the area of a triangle with base 8 cm and height 6 cm.' or 'Find the volume of a cube with side 5 cm.'",
            "c5_area_apply": "format: word_problem. Real-world area/volume problem. Example: 'A room is 5m long, 4m wide, and 3m high. What is its volume?'",
            "c5_area_missing": "format: fill_blank. Fill-in-the-blank. Example: 'A cuboid has l=6, b=4, h=3. Volume = ___ cubic cm.' or 'Area of triangle = ___ sq cm (base=10, height=8).'",
            "c5_area_error": "format: error_spot. A student computed area or volume INCORRECTLY (forgot ½ for triangle, used wrong formula). Ask student to correct.",
            "c5_area_think": "format: multi_step. Reasoning. Example: 'Two boxes have volumes: 5×4×3 and 6×3×3. Which holds more? By how much?'",
        }
        return c5_av_ctx + c5_av_map.get(_skill_tag, "About area and volume.")

    # Geometry (circles, symmetry) (Class 5)
    if _skill_tag in ("c5_geo_identify", "c5_geo_apply", "c5_geo_missing",
                       "c5_geo_error", "c5_geo_think"):
        c5_geo_ctx = (
            "Topic: Geometry — circles and symmetry (Class 5). "
            "Circles: radius, diameter (= 2 × radius), circumference concepts. "
            "Symmetry: lines of symmetry, rotational symmetry. "
            "Do NOT use arithmetic operations, fractions, or decimals. "
            "DO NOT repeat the same shapes or scenarios. "
        )
        c5_geo_map = {
            "c5_geo_identify": "Identify circle parts or symmetry. Example: 'If the radius of a circle is 7 cm, what is its diameter?' or 'How many lines of symmetry does a square have?'",
            "c5_geo_apply": "format: word_problem. Real-world problem. Example: 'A circular garden has a diameter of 14 m. What is its radius?'",
            "c5_geo_missing": "format: fill_blank. Fill-in-the-blank. Example: 'Diameter = 2 × ___' or 'A regular hexagon has ___ lines of symmetry.'",
            "c5_geo_error": "format: error_spot. A student made a WRONG statement about circles or symmetry. Ask student to correct.",
            "c5_geo_think": "format: multi_step. Reasoning. Example: 'Which has more lines of symmetry: a circle or a square? Explain.'",
        }
        return c5_geo_ctx + c5_geo_map.get(_skill_tag, "About circles and symmetry.")

    # Data handling (pie charts) (Class 5)
    if _skill_tag in ("c5_data_identify", "c5_data_apply", "c5_data_missing",
                       "c5_data_error", "c5_data_think"):
        c5_data_ctx = (
            "Topic: Data handling — pie charts (Class 5). "
            "Questions about reading and interpreting pie charts. "
            "Use percentages or fractions of a circle (halves, quarters). "
            "Do NOT use complex calculations. "
            "DO NOT repeat the same data sets or scenarios. "
        )
        c5_data_map = {
            "c5_data_identify": "Read a pie chart. Example: 'In a pie chart, Cricket takes up 50% and Football 25%. What fraction does Cricket represent?'",
            "c5_data_apply": "format: word_problem. Question requiring pie chart interpretation. Example: 'A pie chart shows 40% students like Maths. If there are 200 students, how many like Maths?'",
            "c5_data_missing": "format: fill_blank. Fill-in-the-blank. Example: 'In a pie chart, three sectors show 30%, 25%, 20%. The fourth sector = ___ %.'",
            "c5_data_error": "format: error_spot. A student misread a pie chart. Example: 'The largest sector shows 40% but Amit says it represents less than a quarter.' Ask student to correct.",
            "c5_data_think": "format: multi_step. Reasoning. Example: 'A pie chart shows monthly expenses. Rent is 50%, Food is 25%, Transport is 15%. Is there money left for savings? How much?'",
        }
        return c5_data_ctx + c5_data_map.get(_skill_tag, "About pie charts.")

    # Speed distance time (Class 5)
    if _skill_tag in ("c5_speed_identify", "c5_speed_apply", "c5_speed_missing",
                       "c5_speed_error", "c5_speed_think"):
        c5_speed_ctx = (
            "Topic: Speed, distance, and time (Class 5). "
            "Speed = Distance ÷ Time. Distance = Speed × Time. Time = Distance ÷ Speed. "
            "Use km/hr for speed, km for distance, hours for time. "
            "Use simple whole numbers. "
            "DO NOT repeat the same numbers or scenarios. "
        )
        c5_speed_map = {
            "c5_speed_identify": "Compute speed, distance, or time. Example: 'A car travels 120 km in 2 hours. What is its speed?'",
            "c5_speed_apply": "format: word_problem. Real-world problem. Example: 'A train travels at 60 km/hr. How far will it go in 5 hours?'",
            "c5_speed_missing": "format: fill_blank. Fill-in-the-blank. Example: 'Speed = 40 km/hr, Time = 3 hours, Distance = ___ km.'",
            "c5_speed_error": "format: error_spot. A student computed speed/distance/time WRONG (common: multiplied instead of dividing). Ask student to correct.",
            "c5_speed_think": "format: multi_step. Reasoning. Example: 'Car A travels at 60 km/hr and Car B at 80 km/hr. Both start at the same time. After 3 hours, how much further has Car B gone?'",
        }
        return c5_speed_ctx + c5_speed_map.get(_skill_tag, "About speed, distance, and time.")

    # ── English Language instruction builders ──

    # ── Class 1 English instruction builders ──

    # Alphabet (Class 1)
    if _skill_tag.startswith("eng_c1_alpha_"):
        c1_alpha_ctx = (
            "Topic: Alphabet (Class 1). Capital and small letters A-Z/a-z ONLY. "
            "Use simple 3-5 letter words. NO grammar. Use Indian names: Raju, Meena, Amma. "
            "DO NOT repeat the same letters or words. "
        )
        c1_alpha_map = {
            "eng_c1_alpha_identify": "Show a letter and ask: 'Is this a capital letter or a small letter?' OR 'What letter is this?' Example: 'What letter is this: B?' → B (capital)",
            "eng_c1_alpha_match": "format: match_columns. Match capital letters to small letters. Example: Match A → a, B → b, C → c.",
            "eng_c1_alpha_fill": "format: complete_sentence. Fill in the missing letter in the alphabet. Example: 'A, B, ___, D' → C",
            "eng_c1_alpha_error": "format: error_spot_english. Show a wrong letter in a sequence and ask to correct. Example: 'A, B, D, D — which letter is wrong?' Answer: The first D should be C.",
            "eng_c1_alpha_think": "format: explain_why. Ask: 'Write 2 words that start with the letter M.' OR 'What comes after the letter P?'",
        }
        return c1_alpha_ctx + c1_alpha_map.get(_skill_tag, "About the alphabet.")

    # Phonics (Class 1)
    if _skill_tag.startswith("eng_c1_phonics_"):
        c1_phonics_ctx = (
            "Topic: Phonics (Class 1). Beginning letter sounds ONLY. "
            "Use simple 3-5 letter words (cat, bat, sun, dog). NO blends. NO grammar. "
            "Use Indian contexts. DO NOT repeat the same words or sounds. "
        )
        c1_phonics_map = {
            "eng_c1_phonics_identify": "Ask which letter sound a word starts with. Example: 'What sound does the word CAT start with?' → c",
            "eng_c1_phonics_match": "format: fill_in_blank. Fill in the first letter of a word. Example: '_at' → c (cat) or b (bat)",
            "eng_c1_phonics_fill": "format: complete_sentence. Complete the word by adding the missing first letter. Example: '_og' → d (dog)",
            "eng_c1_phonics_error": "format: error_spot_english. Show a word with the WRONG starting letter. Example: 'Does DUN start with the same sound as SUN?' → No, SUN starts with S.",
            "eng_c1_phonics_think": "format: explain_why. Ask: 'Say 2 words that start with the same sound as BIG.' OR 'Which words start with the S sound: sun, cat, sit?'",
        }
        return c1_phonics_ctx + c1_phonics_map.get(_skill_tag, "About phonics.")

    # Self and Family Vocabulary (Class 1)
    if _skill_tag.startswith("eng_c1_family_"):
        c1_family_ctx = (
            "Topic: Self and Family Vocabulary (Class 1). Family words and body parts ONLY. "
            "Use words: mother, father, sister, brother, hand, eye, nose. "
            "Use Indian names: Amma, Papa, Dadi, Nani, Raju, Meena. "
            "NO grammar. Simple 3-5 letter words. DO NOT repeat the same words. "
        )
        c1_family_map = {
            "eng_c1_family_identify": "Show a description and ask to pick the correct family word. Example: 'Who is your mother's mother?' → grandmother / Nani",
            "eng_c1_family_match": "format: fill_in_blank. Fill in with the correct family or body word. Example: 'I see with my ___.' → eyes",
            "eng_c1_family_fill": "format: complete_sentence. Complete: 'My ___ cooks food for me.' → mother / Amma",
            "eng_c1_family_error": "format: error_spot_english. Show a wrong word and ask to correct. Example: 'I hear with my nose.' → Wrong! I hear with my ears.",
            "eng_c1_family_think": "format: explain_why. Ask: 'Name 2 people in your family.' OR 'What do you use your hands for?'",
        }
        return c1_family_ctx + c1_family_map.get(_skill_tag, "About family vocabulary.")

    # Animals and Food Vocabulary (Class 1)
    if _skill_tag.startswith("eng_c1_animals_"):
        c1_animals_ctx = (
            "Topic: Animals and Food Vocabulary (Class 1). Animal and food names ONLY. "
            "Use words: cat, dog, cow, hen, apple, banana, rice, roti, milk. "
            "Use Indian contexts. NO grammar. Simple 3-5 letter words. "
            "DO NOT repeat the same animals or foods. "
        )
        c1_animals_map = {
            "eng_c1_animals_identify": "Show a description and ask to name the animal or food. Example: 'This animal says moo. What is it?' → cow",
            "eng_c1_animals_match": "format: match_columns. Match animals to their sounds or foods to their colours. Example: cow → moo, dog → bark.",
            "eng_c1_animals_fill": "format: complete_sentence. Complete: 'A ___ gives us milk.' → cow",
            "eng_c1_animals_error": "format: error_spot_english. Show a wrong animal-fact pair. Example: 'A hen says moo.' → Wrong! A hen says cluck.",
            "eng_c1_animals_think": "format: explain_why. Ask: 'Name 2 animals you see at home.' OR 'Name 2 fruits you like to eat.'",
        }
        return c1_animals_ctx + c1_animals_map.get(_skill_tag, "About animals and food.")

    # Greetings and Polite Words (Class 1)
    if _skill_tag.startswith("eng_c1_greetings_"):
        c1_greetings_ctx = (
            "Topic: Greetings and Polite Words (Class 1). "
            "Words: Hello, Good morning, Good night, Goodbye, Please, Thank you, Sorry. "
            "Use Indian contexts. NO grammar. Sentences 3-5 words max. "
            "DO NOT repeat the same greetings. "
        )
        c1_greetings_map = {
            "eng_c1_greetings_identify": "Ask when to use a greeting. Example: 'What do you say when you meet your teacher in the morning?' → Good morning",
            "eng_c1_greetings_match": "format: fill_in_blank. Fill in the correct greeting or polite word. Example: 'When someone gives you a gift, you say ___.' → Thank you",
            "eng_c1_greetings_fill": "format: complete_sentence. Complete: '___ morning, teacher!' → Good",
            "eng_c1_greetings_error": "format: error_spot_english. Show the wrong greeting for a situation. Example: 'Raju says Good night to his teacher at school.' → Wrong! He should say Good morning.",
            "eng_c1_greetings_think": "format: explain_why. Ask: 'When do we say Sorry?' OR 'Why do we say Thank you?'",
        }
        return c1_greetings_ctx + c1_greetings_map.get(_skill_tag, "About greetings and polite words.")

    # Seasons (Class 1)
    if _skill_tag.startswith("eng_c1_seasons_"):
        c1_seasons_ctx = (
            "Topic: Seasons (Class 1). Season names and weather words ONLY. "
            "Seasons: summer, winter, rainy/monsoon, spring. "
            "Words: hot, cold, rain, umbrella, sweater, fan. "
            "Use Indian contexts. NO grammar. Simple words. "
            "DO NOT repeat the same seasons or weather words. "
        )
        c1_seasons_map = {
            "eng_c1_seasons_identify": "Ask about a season from a description. Example: 'In which season do we use an umbrella?' → rainy / monsoon",
            "eng_c1_seasons_match": "format: fill_in_blank. Fill in the season or weather word. Example: 'In ___ we feel very hot.' → summer",
            "eng_c1_seasons_fill": "format: complete_sentence. Complete: 'We wear a ___ in winter.' → sweater",
            "eng_c1_seasons_error": "format: error_spot_english. Show a wrong season-fact pair. Example: 'We use a fan in winter.' → Wrong! We use a fan in summer.",
            "eng_c1_seasons_think": "format: explain_why. Ask: 'What do you wear in the rainy season? Why?' OR 'Name 2 things you do in summer.'",
        }
        return c1_seasons_ctx + c1_seasons_map.get(_skill_tag, "About seasons.")

    # Simple Sentences (Class 1)
    if _skill_tag.startswith("eng_c1_simple_"):
        c1_simple_ctx = (
            "Topic: Simple Sentences (Class 1). 3-5 word sentences ONLY. "
            "Example sentences: 'I see a cat.', 'Raju has a ball.', 'Amma is kind.' "
            "Use Indian names: Raju, Meena, Amma, Papa. NO grammar terms. "
            "All words must be 3-5 letters max. DO NOT repeat sentence patterns. "
        )
        c1_simple_map = {
            "eng_c1_simple_identify": "Show a group of words and ask if it is a sentence. Example: 'Is this a sentence? → The cat sat.' → Yes",
            "eng_c1_simple_rewrite": "format: rewrite_sentence. Put words in order to make a sentence. Example: 'ball / a / I / have' → 'I have a ball.'",
            "eng_c1_simple_fill": "format: complete_sentence. Complete a simple sentence. Example: 'Meena has a ___.' (cat / pen / bag)",
            "eng_c1_simple_error": "format: error_spot_english. Show a sentence with a wrong word order. Example: 'Cat the is big.' → Wrong! The cat is big.",
            "eng_c1_simple_think": "format: creative_writing. Ask: 'Say a sentence about your pet.' OR 'Make a sentence using the word Amma.'",
        }
        return c1_simple_ctx + c1_simple_map.get(_skill_tag, "About simple sentences.")

    # ── Class 2+ English instruction builders ──

    # Nouns
    if _skill_tag.startswith("eng_noun_"):
        eng_noun_ctx = (
            "Topic: Nouns (naming words). "
            "Use simple, age-appropriate sentences about school, family, animals, places. "
            "Use Indian names and contexts. "
            "DO NOT repeat the same nouns or sentences. "
        )
        eng_noun_map = {
            "eng_noun_identify": "Pick out the noun(s) in a given sentence. Example: 'The dog sat on the mat.' → dog, mat",
            "eng_noun_use": "format: fill_in_blank. Fill in the blank with a suitable noun. Example: 'The ___ flew over the tree.'",
            "eng_noun_complete": "format: complete_sentence. Complete the sentence by adding a noun in the blank. Example: 'Aarav went to the ___.'",
            "eng_noun_error": "format: error_spot_english. Show a sentence where a noun is used INCORRECTLY (wrong word or wrong form). Ask student to find and correct the mistake.",
            "eng_noun_thinking": "format: explain_why. Ask student to explain or classify nouns. Example: 'Write 3 naming words for things you see in a classroom.'",
        }
        return eng_noun_ctx + eng_noun_map.get(_skill_tag, "About nouns.")

    # Verbs
    if _skill_tag.startswith("eng_verb_"):
        eng_verb_ctx = (
            "Topic: Verbs (action words). "
            "Use simple, age-appropriate sentences. Use Indian names and contexts. "
            "DO NOT repeat the same verbs or sentences. "
        )
        eng_verb_map = {
            "eng_verb_identify": "Pick out the verb(s) in a given sentence. Example: 'The cat jumped over the wall.' → jumped",
            "eng_verb_use": "format: fill_in_blank. Fill in the blank with a suitable verb. Example: 'The children ___ in the garden.'",
            "eng_verb_complete": "format: complete_sentence. Complete the sentence with the correct verb form. Example: 'Priya ___ (run) to school every day.'",
            "eng_verb_error": "format: error_spot_english. Show a sentence with an INCORRECT verb form. Ask student to find and fix it. Example: 'She go to school yesterday.'",
            "eng_verb_thinking": "format: explain_why. Ask student to think about verbs. Example: 'Write 3 action words for things you do in the morning.'",
        }
        return eng_verb_ctx + eng_verb_map.get(_skill_tag, "About verbs.")

    # Pronouns
    if _skill_tag.startswith("eng_pronoun_"):
        eng_pron_ctx = (
            "Topic: Pronouns (he, she, it, they, we, I, you). "
            "Use simple sentences. Use Indian names and contexts. "
            "DO NOT repeat the same pronouns or sentences. "
        )
        eng_pron_map = {
            "eng_pronoun_identify": "Pick out the pronoun(s) in a given sentence. Example: 'She likes to read books.' → She",
            "eng_pronoun_use": "format: fill_in_blank. Replace the underlined noun with the correct pronoun. Example: 'Aarav is tall. ___ plays basketball.'",
            "eng_pronoun_complete": "format: complete_sentence. Complete with the correct pronoun. Example: '___ went to the park. (Meera)'",
            "eng_pronoun_error": "format: error_spot_english. Show a sentence with the WRONG pronoun. Example: 'Meera is kind. He helps everyone.' Ask student to correct.",
            "eng_pronoun_thinking": "format: explain_why. Ask student to explain pronoun usage. Example: 'Why do we use pronouns instead of repeating names?'",
        }
        return eng_pron_ctx + eng_pron_map.get(_skill_tag, "About pronouns.")

    # Sentences
    if _skill_tag.startswith("eng_sentence_") and not _skill_tag.startswith("eng_sentence_type_"):
        eng_sent_ctx = (
            "Topic: Sentences (forming correct sentences). "
            "Use simple sentence structures. Use Indian names and contexts. "
            "DO NOT repeat the same sentence patterns. "
        )
        eng_sent_map = {
            "eng_sentence_identify": "Identify whether a group of words is a complete sentence or not. Example: 'The big brown' → Not a sentence. 'The dog is sleeping.' → Sentence.",
            "eng_sentence_rewrite": "format: rewrite_sentence. Rewrite jumbled words into a correct sentence. Example: 'school / to / goes / Aarav' → 'Aarav goes to school.'",
            "eng_sentence_rearrange": "format: rearrange_words. Put the given words in the correct order to form a sentence.",
            "eng_sentence_error": "format: error_spot_english. Show a sentence with a grammatical error. Example: 'the cat is sitting on mat.' Ask student to correct.",
            "eng_sentence_thinking": "format: creative_writing. Ask student to create their own sentence. Example: 'Write a sentence about your best friend.'",
        }
        return eng_sent_ctx + eng_sent_map.get(_skill_tag, "About sentences.")

    # Rhyming Words
    if _skill_tag.startswith("eng_rhyme_"):
        eng_rhyme_ctx = (
            "Topic: Rhyming Words (words that sound the same at the end). "
            "Use simple, common English words. "
            "DO NOT repeat the same rhyming pairs. "
        )
        eng_rhyme_map = {
            "eng_rhyme_identify": "Identify which words rhyme from a given set. Example: 'Which word rhymes with cat: dog, bat, pen?' → bat",
            "eng_rhyme_match": "format: match_columns. Match rhyming pairs. Example: cat-bat, tree-free, sun-fun.",
            "eng_rhyme_complete": "format: complete_sentence. Complete a rhyme: 'I see a ___ sitting on a log.' (Answer: frog)",
            "eng_rhyme_error": "format: error_spot_english. Show an incorrect rhyming pair and ask student to fix it. Example: 'Does cat rhyme with pen? Find the correct rhyming word.'",
            "eng_rhyme_thinking": "format: creative_writing. Ask student to write a short rhyming couplet. Example: 'Write two lines that end with rhyming words.'",
        }
        return eng_rhyme_ctx + eng_rhyme_map.get(_skill_tag, "About rhyming words.")

    # Punctuation
    if _skill_tag.startswith("eng_punctuation_"):
        eng_punct_ctx = (
            "Topic: Punctuation (full stop, question mark, exclamation mark, comma, apostrophe). "
            "Use simple sentences. Use Indian names and contexts. "
            "DO NOT repeat the same punctuation patterns. "
        )
        eng_punct_map = {
            "eng_punctuation_identify": "Identify the punctuation mark used and explain why. Example: 'What punctuation mark ends this sentence: How are you?'",
            "eng_punctuation_use": "format: correct_sentence. Add the correct punctuation to a sentence. Example: 'Where is the library' → 'Where is the library?'",
            "eng_punctuation_complete": "format: complete_sentence. Add missing punctuation marks to complete the sentence correctly.",
            "eng_punctuation_error": "format: error_spot_english. Show a sentence with WRONG punctuation. Example: 'What is your name.' Ask student to correct the punctuation.",
            "eng_punctuation_thinking": "format: explain_why. Ask student to explain why specific punctuation is used. Example: 'Why do we use a question mark at the end of some sentences?'",
        }
        return eng_punct_ctx + eng_punct_map.get(_skill_tag, "About punctuation.")

    # Adjectives
    if _skill_tag.startswith("eng_adjective_"):
        eng_adj_ctx = (
            "Topic: Adjectives (describing words). "
            "Use simple, descriptive sentences. Use Indian names and contexts. "
            "DO NOT repeat the same adjectives or sentences. "
        )
        eng_adj_map = {
            "eng_adjective_identify": "Pick out the adjective(s) in a sentence. Example: 'The tall boy ran fast.' → tall",
            "eng_adjective_use": "format: fill_in_blank. Fill in the blank with a suitable adjective. Example: 'The ___ mango was very sweet.'",
            "eng_adjective_complete": "format: complete_sentence. Complete the sentence with an adjective. Example: 'Diya wore a ___ dress to the party.'",
            "eng_adjective_error": "format: error_spot_english. Show a sentence with an incorrect degree of comparison. Example: 'This building is more taller than that one.' Ask student to correct.",
            "eng_adjective_thinking": "format: creative_writing. Ask student to describe something using adjectives. Example: 'Describe your classroom using 3 adjectives.'",
        }
        return eng_adj_ctx + eng_adj_map.get(_skill_tag, "About adjectives.")

    # Tenses
    if _skill_tag.startswith("eng_tense_"):
        eng_tense_ctx = (
            "Topic: Tenses (past, present, future). "
            "Use simple, clear sentences. Use Indian names and contexts. "
            "DO NOT repeat the same verb or tense pattern. "
        )
        eng_tense_map = {
            "eng_tense_identify": "Identify the tense of a given sentence. Example: 'Aarav played cricket yesterday.' → Simple past tense",
            "eng_tense_change": "format: rewrite_sentence. Change the sentence to a different tense. Example: 'She reads a book.' → Past tense: 'She read a book.'",
            "eng_tense_complete": "format: change_form. Fill in the correct tense form of the verb. Example: 'Yesterday, Priya ___ (walk) to school.'",
            "eng_tense_error": "format: error_spot_english. Show a sentence with the WRONG tense form. Example: 'Yesterday I am going to the park.' Ask student to correct.",
            "eng_tense_thinking": "format: explain_why. Ask student to explain tense usage. Example: 'Why do we say \"she ran\" instead of \"she runned\"?'",
        }
        return eng_tense_ctx + eng_tense_map.get(_skill_tag, "About tenses.")

    # Vocabulary
    if _skill_tag.startswith("eng_vocabulary_"):
        eng_vocab_ctx = (
            "Topic: Vocabulary (word meanings, synonyms, antonyms). "
            "Use age-appropriate words. Use Indian contexts. "
            "DO NOT repeat the same words or meanings. "
        )
        eng_vocab_map = {
            "eng_vocabulary_identify": "Choose the correct meaning of a word from options. Example: 'What does \"enormous\" mean? (a) tiny (b) huge (c) fast'",
            "eng_vocabulary_use": "format: use_in_sentence. Use a given word in a sentence. Example: 'Use the word \"brave\" in a sentence.'",
            "eng_vocabulary_match": "format: match_columns. Match words with their meanings or synonyms/antonyms.",
            "eng_vocabulary_complete": "format: complete_sentence. Complete the sentence with the correct vocabulary word. Example: 'The opposite of happy is ___.'",
            "eng_vocabulary_error": "format: error_spot_english. Show a sentence where a word is used with the WRONG meaning. Example: 'The tiny elephant...' Ask student to fix it.",
            "eng_vocabulary_thinking": "format: explain_why. Ask student to explain word meanings or relationships. Example: 'How are the words \"happy\" and \"glad\" related?'",
        }
        return eng_vocab_ctx + eng_vocab_map.get(_skill_tag, "About vocabulary.")

    # Reading Comprehension
    if _skill_tag.startswith("eng_comprehension_"):
        eng_comp_ctx = (
            "Topic: Reading Comprehension. "
            "Include a SHORT passage (3-5 sentences) in the question_text, then ask a question about it. "
            "Use Indian names, places, and situations. "
            "DO NOT repeat the same passage theme. "
        )
        eng_comp_map = {
            "eng_comprehension_identify": "Read the passage and pick the correct answer from options. Include the passage and a factual question.",
            "eng_comprehension_answer": "format: word_problem_english. Read the passage and answer a question in your own words. Include the passage.",
            "eng_comprehension_complete": "format: paragraph_cloze. Passage with blanks to fill in from context. Include the passage with 2-3 blanks.",
            "eng_comprehension_error": "format: error_spot_english. Show a passage with a factual or grammatical error. Ask student to find and correct it.",
            "eng_comprehension_thinking": "format: explain_why. After reading a passage, ask an inferential or opinion question. Example: 'Why do you think the character did that?'",
        }
        return eng_comp_ctx + eng_comp_map.get(_skill_tag, "About reading comprehension.")

    # Conjunctions
    if _skill_tag.startswith("eng_conjunction_"):
        eng_conj_ctx = (
            "Topic: Conjunctions (and, but, or, so, because, although, while, when). "
            "Use simple sentences. Use Indian names and contexts. "
            "DO NOT repeat the same conjunction or sentence pattern. "
        )
        eng_conj_map = {
            "eng_conjunction_identify": "Identify the conjunction in a sentence. Example: 'I like tea but she likes coffee.' → but",
            "eng_conjunction_use": "format: fill_in_blank. Fill in with the correct conjunction. Example: 'Aarav was tired ___ he kept playing.' (but/so)",
            "eng_conjunction_complete": "format: complete_sentence. Join two sentences using a conjunction. Example: 'It was raining. We went out.' → 'It was raining but we went out.'",
            "eng_conjunction_error": "format: error_spot_english. Show a sentence with the WRONG conjunction. Example: 'I was hungry but I ate food.' (should be 'so'). Ask student to correct.",
            "eng_conjunction_thinking": "format: explain_why. Ask student to explain conjunction choice. Example: 'Why is \"because\" better than \"and\" in this sentence?'",
        }
        return eng_conj_ctx + eng_conj_map.get(_skill_tag, "About conjunctions.")

    # Prepositions
    if _skill_tag.startswith("eng_preposition_"):
        eng_prep_ctx = (
            "Topic: Prepositions (in, on, at, under, over, between, behind, beside, through). "
            "Use simple sentences about places, directions, positions. Use Indian contexts. "
            "DO NOT repeat the same preposition or sentence pattern. "
        )
        eng_prep_map = {
            "eng_preposition_identify": "Identify the preposition in a sentence. Example: 'The book is on the table.' → on",
            "eng_preposition_use": "format: fill_in_blank. Fill in with the correct preposition. Example: 'The cat is hiding ___ the bed.' (under)",
            "eng_preposition_complete": "format: complete_sentence. Complete with a preposition. Example: 'Diya walked ___ the bridge to reach school.'",
            "eng_preposition_error": "format: error_spot_english. Show a sentence with the WRONG preposition. Example: 'The bird is sitting in the tree.' (should be 'on'). Ask student to correct.",
            "eng_preposition_thinking": "format: explain_why. Ask student to explain preposition usage. Example: 'What is the difference between \"in\" and \"on\"?'",
        }
        return eng_prep_ctx + eng_prep_map.get(_skill_tag, "About prepositions.")

    # Adverbs
    if _skill_tag.startswith("eng_adverb_"):
        eng_adv_ctx = (
            "Topic: Adverbs (words that tell how, when, where — quickly, slowly, always, here). "
            "Use simple sentences. Use Indian names and contexts. "
            "DO NOT repeat the same adverb or sentence pattern. "
        )
        eng_adv_map = {
            "eng_adverb_identify": "Identify the adverb in a sentence. Example: 'She sings beautifully.' → beautifully",
            "eng_adverb_use": "format: fill_in_blank. Fill in with a suitable adverb. Example: 'The tortoise walked ___.' (slowly)",
            "eng_adverb_complete": "format: complete_sentence. Complete with the adverb form. Example: 'Priya speaks ___ (soft → softly).'",
            "eng_adverb_error": "format: error_spot_english. Show a sentence where an adjective is used instead of an adverb. Example: 'He runs quick.' (should be 'quickly'). Ask student to correct.",
            "eng_adverb_thinking": "format: explain_why. Ask student to form adverbs or explain usage. Example: 'How do you change \"careful\" into an adverb?'",
        }
        return eng_adv_ctx + eng_adv_map.get(_skill_tag, "About adverbs.")

    # Prefixes and Suffixes
    if _skill_tag.startswith("eng_prefix_") or _skill_tag.startswith("eng_suffix_") or _skill_tag.startswith("eng_affix_"):
        eng_affix_ctx = (
            "Topic: Prefixes (un-, re-, dis-, pre-) and Suffixes (-ful, -less, -ness, -ly, -ment). "
            "Use age-appropriate words. Use Indian contexts. "
            "DO NOT repeat the same prefix/suffix or root word. "
        )
        eng_affix_map = {
            "eng_prefix_identify": "Identify the prefix and root word. Example: 'What is the prefix in \"unhappy\"?' → un- (root: happy)",
            "eng_suffix_identify": "Identify the suffix and root word. Example: 'What is the suffix in \"careful\"?' → -ful (root: care)",
            "eng_affix_use": "format: fill_in_blank. Add the correct prefix or suffix. Example: 'Add a prefix to \"kind\" to make its opposite.' → unkind",
            "eng_affix_change": "format: change_form. Change the word by adding a prefix or suffix. Example: 'Make a new word from \"play\" using a suffix.' → playful",
            "eng_affix_error": "format: error_spot_english. Show a word with the WRONG prefix/suffix. Example: 'The opposite of happy is dishappy.' (should be 'unhappy'). Ask student to correct.",
            "eng_affix_thinking": "format: explain_why. Ask student to explain how a prefix/suffix changes meaning. Example: 'How does adding \"un-\" change the meaning of a word?'",
        }
        return eng_affix_ctx + eng_affix_map.get(_skill_tag, "About prefixes and suffixes.")

    # Sentence Types (Class 4)
    if _skill_tag.startswith("eng_sentence_type_"):
        eng_stype_ctx = (
            "Topic: Sentence Types (declarative, interrogative, exclamatory, imperative). "
            "Use clear examples of each type. Use Indian names and contexts. "
            "DO NOT repeat the same sentence type or pattern. "
        )
        eng_stype_map = {
            "eng_sentence_type_identify": "Identify the type of sentence. Example: 'Close the door!' → Imperative. 'It is raining.' → Declarative.",
            "eng_sentence_type_rewrite": "format: rewrite_sentence. Change a sentence from one type to another. Example: 'It is cold.' → Question: 'Is it cold?'",
            "eng_sentence_type_rearrange": "format: rearrange_words. Rearrange words to form a specific type of sentence (question, command, statement).",
            "eng_sentence_type_error": "format: error_spot_english. Show a sentence with wrong punctuation for its type. Example: 'What is your name.' (should be ?). Ask student to correct.",
            "eng_sentence_type_thinking": "format: creative_writing. Ask student to write one sentence of each type about a given topic.",
        }
        return eng_stype_ctx + eng_stype_map.get(_skill_tag, "About sentence types.")

    # ── Class 5 English instruction builders ──

    # Active and Passive Voice (Class 5)
    if _skill_tag.startswith("eng_c5_voice_"):
        eng_voice_ctx = (
            "Topic: Active and Passive Voice (Class 5). "
            "Use simple present, past, and future tense sentences only. "
            "Use Indian names (Ravi, Meena, Priya, Arjun) and contexts. "
            "DO NOT repeat the same sentence pattern or subject. "
        )
        eng_voice_map = {
            "eng_c5_voice_identify": "Identify whether the sentence is in active or passive voice. Example: 'The ball was kicked by Ravi.' → Passive voice.",
            "eng_c5_voice_convert": "format: rewrite_sentence. Convert the sentence from active to passive voice or vice versa. Example: 'Meena wrote a letter.' → 'A letter was written by Meena.'",
            "eng_c5_voice_complete": "format: change_form. Change the form of the sentence to the other voice. Fill in the blank. Example: 'The cake was baked by Amma.' → Active: 'Amma ___ the cake.' (baked)",
            "eng_c5_voice_error": "format: error_spot_english. Show a sentence with an INCORRECT voice conversion. Example: 'The book was read by she.' (should be 'her'). Ask student to find and correct the error.",
            "eng_c5_voice_thinking": "format: explain_why. Ask why a particular voice is more suitable. Example: 'Why is \"The Taj Mahal was built by Shah Jahan\" better in passive voice for a history book?'",
        }
        return eng_voice_ctx + eng_voice_map.get(_skill_tag, "About active and passive voice.")

    # Direct and Indirect Speech (Class 5)
    if _skill_tag.startswith("eng_c5_speech_"):
        eng_speech_ctx = (
            "Topic: Direct and Indirect Speech (Class 5). "
            "Use said/told/asked as reporting verbs. Change pronouns and tenses correctly. "
            "Use Indian names and contexts. "
            "DO NOT repeat the same reporting verb or sentence structure. "
        )
        eng_speech_map = {
            "eng_c5_speech_identify": "Identify whether the sentence uses direct or indirect speech. Example: 'Amma said, \"Eat your vegetables.\"' → Direct speech.",
            "eng_c5_speech_convert": "format: rewrite_sentence. Convert direct speech to indirect or vice versa. Example: 'Ravi said, \"I am going to school.\"' → 'Ravi said that he was going to school.'",
            "eng_c5_speech_complete": "format: change_form. Complete the indirect speech conversion by filling in blanks. Example: 'Priya said, \"I like mangoes.\"' → 'Priya said that ___ ___ mangoes.' (she liked)",
            "eng_c5_speech_error": "format: error_spot_english. Show incorrect speech conversion. Example: 'Meena said that I am happy.' (should be 'she was happy'). Ask student to correct.",
            "eng_c5_speech_thinking": "format: explain_why. Ask about rules of speech conversion. Example: 'Why does \"am\" change to \"was\" when we convert direct speech to indirect speech?'",
        }
        return eng_speech_ctx + eng_speech_map.get(_skill_tag, "About direct and indirect speech.")

    # Complex Sentences (Class 5)
    if _skill_tag.startswith("eng_c5_complex_"):
        eng_complex_ctx = (
            "Topic: Complex Sentences (Class 5). "
            "Use subordinating conjunctions: because, although, when, while, if, since, before, after, until, unless. "
            "Use Indian names and contexts. "
            "DO NOT repeat the same conjunction or sentence pattern. "
        )
        eng_complex_map = {
            "eng_c5_complex_identify": "Identify the subordinating conjunction or the main/subordinate clause. Example: 'Ravi stayed home because it was raining.' → Conjunction: because.",
            "eng_c5_complex_rewrite": "format: rewrite_sentence. Join two simple sentences into a complex sentence. Example: 'It was hot. We went swimming.' → 'Since it was hot, we went swimming.'",
            "eng_c5_complex_complete": "format: complete_sentence. Complete with a suitable subordinate clause. Example: 'Meena could not play ___ (because/although)...' → 'because she had a fever.'",
            "eng_c5_complex_error": "format: error_spot_english. Show a sentence with the WRONG conjunction. Example: 'Although it was sunny, we took an umbrella.' (should be 'Because'). Ask student to correct.",
            "eng_c5_complex_thinking": "format: creative_writing. Ask student to write 2-3 complex sentences about a given topic using different conjunctions.",
        }
        return eng_complex_ctx + eng_complex_map.get(_skill_tag, "About complex sentences.")

    # Summary Writing (Class 5)
    if _skill_tag.startswith("eng_c5_summary_"):
        eng_summary_ctx = (
            "Topic: Summary Writing (Class 5). "
            "Include a short passage (50-80 words) with Indian contexts. "
            "Focus on identifying main idea, key points, and writing concise summaries. "
            "DO NOT repeat the same passage topic or structure. "
        )
        eng_summary_map = {
            "eng_c5_summary_identify": "Read a short passage and pick the best summary or main idea from options. Include the passage and 3-4 options.",
            "eng_c5_summary_write": "format: word_problem_english. Read a short passage and write a 2-3 sentence summary in your own words. Include the passage.",
            "eng_c5_summary_complete": "format: paragraph_cloze. Complete a summary of a passage by filling in key words. Include the passage and the summary with blanks.",
            "eng_c5_summary_error": "format: error_spot_english. Show a passage and a WRONG summary (with incorrect facts or missing key points). Ask student to find the error.",
            "eng_c5_summary_thinking": "format: explain_why. Ask student to explain why certain details should or should not be included in a summary. Example: 'Why is the date not important in a summary of this story?'",
        }
        return eng_summary_ctx + eng_summary_map.get(_skill_tag, "About summary writing.")

    # Comprehension (Class 5)
    if _skill_tag.startswith("eng_c5_comprehension_"):
        eng_c5comp_ctx = (
            "Topic: Comprehension (Class 5). "
            "Include a passage (60-100 words) with Indian contexts. "
            "Ask factual, inferential, and evaluative questions. "
            "DO NOT repeat the same passage topic. "
        )
        eng_c5comp_map = {
            "eng_c5_comprehension_identify": "Read the passage and pick the correct answer from options. Include the passage and a factual question with 3-4 options.",
            "eng_c5_comprehension_answer": "format: word_problem_english. Read the passage and answer a question in your own words. Include the passage.",
            "eng_c5_comprehension_complete": "format: paragraph_cloze. Passage with blanks to fill in from context. Include the passage with 2-3 blanks.",
            "eng_c5_comprehension_error": "format: error_spot_english. Show a passage with a factual or grammatical error. Ask student to find and correct it.",
            "eng_c5_comprehension_thinking": "format: explain_why. After reading a passage, ask an inferential or opinion question. Example: 'What lesson can we learn from this story?'",
        }
        return eng_c5comp_ctx + eng_c5comp_map.get(_skill_tag, "About comprehension.")

    # Synonyms and Antonyms (Class 5)
    if _skill_tag.startswith("eng_c5_synonym_"):
        eng_synonym_ctx = (
            "Topic: Synonyms and Antonyms (Class 5). "
            "Use Class 5 level vocabulary. Include words from CBSE English textbooks. "
            "Use Indian contexts where possible. "
            "DO NOT repeat the same word or word pair. "
        )
        eng_synonym_map = {
            "eng_c5_synonym_identify": "Pick the synonym or antonym of a given word from options. Example: 'Choose the synonym of \"brave\": (a) coward (b) fearless (c) timid (d) weak' → fearless",
            "eng_c5_synonym_match": "format: match_columns. Match words with their synonyms or antonyms. Example: Match: happy → glad, big → large, fast → quick.",
            "eng_c5_synonym_use": "format: fill_in_blank. Replace the underlined word with a synonym or antonym. Example: 'The king was very angry (synonym: _____).' → furious",
            "eng_c5_synonym_error": "format: error_spot_english. Show a sentence where a word is used with the WRONG synonym/antonym. Example: 'The antonym of \"kind\" is \"gentle\".' (should be 'cruel'). Ask student to correct.",
            "eng_c5_synonym_thinking": "format: explain_why. Ask student to explain meaning differences. Example: 'How are \"big\" and \"enormous\" different? When would you use each?'",
        }
        return eng_synonym_ctx + eng_synonym_map.get(_skill_tag, "About synonyms and antonyms.")

    # Formal Letter Writing (Class 5)
    if _skill_tag.startswith("eng_c5_letter_"):
        eng_letter_ctx = (
            "Topic: Formal Letter Writing (Class 5). "
            "Cover format: sender's address, date, receiver's address, subject, salutation, body, closing. "
            "Use school and community topics. Use Indian contexts. "
            "DO NOT repeat the same letter topic or format element. "
        )
        eng_letter_map = {
            "eng_c5_letter_identify": "Identify the correct part of a formal letter from options. Example: 'Which part comes first: Subject line or Salutation?' → Subject line.",
            "eng_c5_letter_write": "format: word_problem_english. Write a formal letter on a given topic. Example: 'Write a letter to your principal requesting a holiday for a school function.'",
            "eng_c5_letter_complete": "format: paragraph_cloze. Complete a formal letter by filling in missing parts (salutation, subject, closing). Include the letter template with blanks.",
            "eng_c5_letter_error": "format: error_spot_english. Show a formal letter with format errors (wrong order, missing parts, informal language). Ask student to find and correct.",
            "eng_c5_letter_thinking": "format: creative_writing. Write a formal letter on a given topic using correct format. Example: 'Write to the editor of a newspaper about traffic problems near your school.'",
        }
        return eng_letter_ctx + eng_letter_map.get(_skill_tag, "About formal letter writing.")

    # Creative Writing (Class 5)
    if _skill_tag.startswith("eng_c5_creative_"):
        eng_creative_ctx = (
            "Topic: Creative Writing (Class 5). "
            "Encourage descriptive language, vivid vocabulary, similes, and varied sentence structures. "
            "Use topics relatable to Indian Class 5 students. "
            "DO NOT repeat the same writing prompt or style. "
        )
        eng_creative_map = {
            "eng_c5_creative_identify": "Read a short passage and identify the literary device or writing technique. Example: 'The sun smiled down at us.' → Personification.",
            "eng_c5_creative_use": "format: use_in_sentence. Use the given word or literary device in a creative sentence. Example: 'Use a simile to describe the moon.'",
            "eng_c5_creative_expand": "format: expand_sentence. Expand the given sentence by adding descriptive details. Example: 'The boy ran.' → 'The little boy ran quickly through the dusty village road.'",
            "eng_c5_creative_error": "format: error_spot_english. Show a paragraph with a dull/incorrect description and ask to improve. Example: 'The flower was nice.' → needs more vivid language.",
            "eng_c5_creative_thinking": "format: creative_writing. Write a short paragraph or story on a given topic. Example: 'Describe a rainy day at your school in 5-6 sentences using vivid language.'",
        }
        return eng_creative_ctx + eng_creative_map.get(_skill_tag, "About creative writing.")

    # Clauses (Class 5)
    if _skill_tag.startswith("eng_c5_clause_"):
        eng_clause_ctx = (
            "Topic: Clauses (Class 5). "
            "Cover main (independent) and subordinate (dependent) clauses — noun, adjective, and adverb clauses. "
            "Use Indian names and contexts. "
            "DO NOT repeat the same clause type or sentence pattern. "
        )
        eng_clause_map = {
            "eng_c5_clause_identify": "Identify the main clause and subordinate clause. Example: 'The boy who won the race is my friend.' → Main: 'The boy is my friend.' Subordinate: 'who won the race'.",
            "eng_c5_clause_rewrite": "format: rewrite_sentence. Combine two sentences using a relative pronoun or conjunction to form a sentence with a clause. Example: 'Priya is my friend. She lives in Delhi.' → 'Priya, who lives in Delhi, is my friend.'",
            "eng_c5_clause_complete": "format: complete_sentence. Complete the sentence with a suitable clause. Example: 'The teacher praised the student who ___.' → 'who scored the highest marks.'",
            "eng_c5_clause_error": "format: error_spot_english. Show a sentence with the WRONG relative pronoun or clause structure. Example: 'The book which I met yesterday was interesting.' (should be 'that I read'). Ask student to correct.",
            "eng_c5_clause_thinking": "format: explain_why. Ask student to explain clause types. Example: 'In the sentence \"I know that she is honest,\" what kind of clause is \"that she is honest\"? Why?'",
        }
        return eng_clause_ctx + eng_clause_map.get(_skill_tag, "About clauses.")

    # ── Science Class 3 instruction builders ──

    # Plants
    if _skill_tag.startswith("sci_plants_"):
        sci_plants_ctx = (
            "Topic: Plants (Class 3 Science, CBSE). "
            "Cover parts of a plant (root, stem, leaf, flower, fruit, seed), how plants grow, "
            "types of plants (herbs, shrubs, trees, climbers, creepers), photosynthesis in simple terms. "
            "Use Indian plants: neem, tulsi, mango, banyan, lotus, coconut, bamboo. "
            "DO NOT repeat the same plant or concept. "
        )
        sci_plants_map = {
            "sci_plants_identify": "Identify a part of a plant or type of plant. Example: 'Which part of the plant makes food? (a) Root (b) Leaf (c) Stem (d) Flower' → Leaf",
            "sci_plants_apply": "format: explain_why_science. Explain a concept about plants. Example: 'Why do plants need sunlight?'",
            "sci_plants_represent": "format: sequence_steps. Arrange steps of a process in order. Example: 'Arrange the steps of how a seed grows into a plant.'",
            "sci_plants_error": "format: error_spot_science. Present a WRONG fact about plants. Example: 'Roots make food for the plant.' Ask: 'Find the mistake and correct it.'",
            "sci_plants_thinking": "format: thinking_science. Ask a reasoning question. Example: 'A plant is kept in a dark room for a week. What do you think will happen? Why?'",
        }
        return sci_plants_ctx + sci_plants_map.get(_skill_tag, "About plants.")

    # Animals
    if _skill_tag.startswith("sci_animals_"):
        sci_animals_ctx = (
            "Topic: Animals (Class 3 Science, CBSE). "
            "Cover types of animals (wild, domestic, pet), habitats (forest, water, desert, grassland), "
            "body coverings (fur, feathers, scales, shell), food habits (herbivore, carnivore, omnivore), movement. "
            "Use Indian animals: peacock, cow, elephant, camel, parrot, cobra, tiger, monkey. "
            "DO NOT repeat the same animal or concept. "
        )
        sci_animals_map = {
            "sci_animals_identify": "Classify or identify an animal. Example: 'Which of these is a herbivore? (a) Lion (b) Cow (c) Eagle (d) Frog' → Cow",
            "sci_animals_apply": "format: compare_two. Compare two animals. Example: 'How are a fish and a frog different in how they breathe?'",
            "sci_animals_represent": "format: cause_effect. Show cause and effect. Example: 'Birds have wings → they can ___.'",
            "sci_animals_error": "format: error_spot_science. Present a WRONG fact about animals. Example: 'A snake is covered with fur.' Ask: 'Find the mistake and correct it.'",
            "sci_animals_thinking": "format: thinking_science. Ask a reasoning question. Example: 'Why do you think camels can survive in the desert? Give two reasons.'",
        }
        return sci_animals_ctx + sci_animals_map.get(_skill_tag, "About animals.")

    # Food and Nutrition
    if _skill_tag.startswith("sci_food_"):
        sci_food_ctx = (
            "Topic: Food and Nutrition (Class 3 Science, CBSE). "
            "Cover food groups (energy-giving: rice, roti, ghee; body-building: dal, paneer, eggs; "
            "protective: fruits, vegetables), balanced diet, sources of food (plants, animals), "
            "cooking methods, food preservation. "
            "Use Indian foods: dal, roti, rice, sabzi, curd, paneer, jaggery, ghee. "
            "DO NOT repeat the same food item or concept. "
        )
        sci_food_map = {
            "sci_food_identify": "Identify food group or source. Example: 'Which food gives us energy? (a) Spinach (b) Rice (c) Curd (d) Water' → Rice",
            "sci_food_apply": "format: give_example. Ask for examples. Example: 'Give two examples of body-building foods.'",
            "sci_food_represent": "format: fill_diagram. Classify foods into groups. Example: 'Write each food in the correct group: rice, dal, apple, ghee → Energy-giving / Body-building / Protective'",
            "sci_food_error": "format: error_spot_science. Present a WRONG fact. Example: 'Ghee is a protective food that gives us vitamins.' Ask: 'Find the mistake and correct it.'",
            "sci_food_thinking": "format: thinking_science. Ask a reasoning question. Example: 'Why should we eat different types of food every day instead of just our favourite food?'",
        }
        return sci_food_ctx + sci_food_map.get(_skill_tag, "About food and nutrition.")

    # Shelter
    if _skill_tag.startswith("sci_shelter_"):
        sci_shelter_ctx = (
            "Topic: Shelter (Class 3 Science, CBSE). "
            "Cover why living things need shelter, types of human houses (kutcha, pucca, tent, houseboat, stilt house), "
            "animal shelters (nest, burrow, den, hive, web), materials used for building. "
            "Use Indian contexts: village houses, city flats, houseboats in Kashmir, stilt houses in Assam. "
            "DO NOT repeat the same shelter type or concept. "
        )
        sci_shelter_map = {
            "sci_shelter_identify": "Identify or match shelter. Example: 'Where does a rabbit live? (a) Nest (b) Burrow (c) Den (d) Hive' → Burrow",
            "sci_shelter_apply": "format: compare_two. Compare shelters. Example: 'How is a kutcha house different from a pucca house?'",
            "sci_shelter_represent": "format: cause_effect. Show cause and effect. Example: 'In Assam, it rains a lot → people build ___ houses.'",
            "sci_shelter_error": "format: error_spot_science. Present a WRONG fact. Example: 'A beehive is built by birds.' Ask: 'Find the mistake and correct it.'",
            "sci_shelter_thinking": "format: thinking_science. Ask a reasoning question. Example: 'Why do people in Rajasthan build houses with thick walls?'",
        }
        return sci_shelter_ctx + sci_shelter_map.get(_skill_tag, "About shelter.")

    # Water
    if _skill_tag.startswith("sci_water_"):
        sci_water_ctx = (
            "Topic: Water (Class 3 Science, CBSE). "
            "Cover sources of water (rain, river, well, tap, borewell), uses of water (drinking, cooking, "
            "washing, farming), water cycle (evaporation, condensation, precipitation), saving water, "
            "clean vs dirty water, water purification. "
            "Use Indian contexts: monsoon, Ganga, hand pumps, water tankers, rainwater harvesting. "
            "DO NOT repeat the same concept or context. "
        )
        sci_water_map = {
            "sci_water_identify": "Identify facts about water. Example: 'True or False: We get most of our water from the ocean.' → False",
            "sci_water_apply": "format: what_happens_if. Ask cause-effect. Example: 'What happens if we leave a glass of water in the sun for a long time?'",
            "sci_water_represent": "format: sequence_steps. Arrange steps. Example: 'Arrange the steps of the water cycle: Rain falls → Water in rivers → Sun heats water → Clouds form'",
            "sci_water_error": "format: error_spot_science. Present a WRONG fact. Example: 'Sea water is safe to drink directly.' Ask: 'Find the mistake and correct it.'",
            "sci_water_thinking": "format: multi_step_science. Ask multi-step reasoning. Example: 'Your village has no rain for 3 months. List two ways to save water and explain why each works.'",
        }
        return sci_water_ctx + sci_water_map.get(_skill_tag, "About water.")

    # Air
    if _skill_tag.startswith("sci_air_"):
        sci_air_ctx = (
            "Topic: Air (Class 3 Science, CBSE). "
            "Cover air is everywhere, properties of air (takes up space, has weight, moves), "
            "composition (oxygen, carbon dioxide, nitrogen), uses of air (breathing, burning, drying), "
            "air pollution (vehicle smoke, factory smoke, burning waste), wind energy. "
            "Use Indian contexts: kite flying on Sankranti, windmills, Diwali fireworks, vehicle pollution. "
            "DO NOT repeat the same concept or context. "
        )
        sci_air_map = {
            "sci_air_identify": "Identify facts about air. Example: 'True or False: Air has weight.' → True",
            "sci_air_apply": "format: explain_why_science. Explain a concept. Example: 'Why do we see bubbles when we blow air into water?'",
            "sci_air_represent": "format: cause_effect. Show cause and effect. Example: 'Burning crackers on Diwali → ___ happens to the air.'",
            "sci_air_error": "format: error_spot_science. Present a WRONG fact. Example: 'Air is made up of only oxygen.' Ask: 'Find the mistake and correct it.'",
            "sci_air_thinking": "format: thinking_science. Ask reasoning. Example: 'Why should we plant more trees to keep the air clean?'",
        }
        return sci_air_ctx + sci_air_map.get(_skill_tag, "About air.")

    # Our Body
    if _skill_tag.startswith("sci_body_"):
        sci_body_ctx = (
            "Topic: Our Body (Class 3 Science, CBSE). "
            "Cover major body parts and organs (heart, lungs, brain, stomach, bones, muscles), "
            "sense organs (eyes, ears, nose, tongue, skin), hygiene (handwashing, bathing, brushing), "
            "healthy habits (exercise, balanced diet, sleep), keeping the body safe. "
            "Use Indian contexts: yoga, PT class, school nurse, morning assembly. "
            "DO NOT repeat the same body part or concept. "
        )
        sci_body_map = {
            "sci_body_identify": "Identify a body part or its function. Example: 'Which organ pumps blood? (a) Brain (b) Heart (c) Lungs (d) Stomach' → Heart",
            "sci_body_apply": "format: explain_why_science. Explain a concept. Example: 'Why should we wash our hands before eating?'",
            "sci_body_represent": "format: fill_diagram. Match organs to functions. Example: 'Match: Eyes → ___. Ears → ___. Nose → ___.'",
            "sci_body_error": "format: error_spot_science. Present a WRONG fact. Example: 'We breathe with our stomach.' Ask: 'Find the mistake and correct it.'",
            "sci_body_thinking": "format: multi_step_science. Ask reasoning. Example: 'Why is it important to do yoga or exercise every day? Give two reasons.'",
        }
        return sci_body_ctx + sci_body_map.get(_skill_tag, "About the human body.")

    # ── EVS Class 1: My Family ──
    if _skill_tag.startswith("sci_c1_family_"):
        ctx = (
            "Topic: My Family (Class 1 EVS, CBSE). "
            "Cover family members: mother (Amma), father (Appa/Papa), brother, sister, "
            "grandmother (Dadi/Nani), grandfather (Dada/Nana). "
            "Use Indian names: Raju, Meena, Amma, Appa, Dadi, Nani. "
            "Keep vocabulary VERY simple — Class 1 level. "
            "DO NOT repeat the same family member or scenario. "
        )
        tag_map = {
            "sci_c1_family_identify": "Identify a family member. Example: 'Who cooks food at home? (a) Teacher (b) Amma (c) Doctor (d) Policeman' -> Amma",
            "sci_c1_family_apply": "format: give_example. Ask for examples about family. Example: 'Name two people in your family who take care of you.'",
            "sci_c1_family_represent": "format: fill_diagram. Match family members. Example: 'Match: Dadi -> ___. Appa -> ___. (father / grandmother)'",
            "sci_c1_family_error": "format: error_spot_science. Present a WRONG fact about family. Example: 'Dadi is my younger sister.' Ask: 'Find the mistake and correct it.'",
            "sci_c1_family_thinking": "format: thinking_science. Ask a simple reasoning question. Example: 'Why do we love our family? Tell one reason.'",
        }
        return ctx + tag_map.get(_skill_tag, "About family.")

    # ── EVS Class 1: My Body ──
    if _skill_tag.startswith("sci_c1_body_"):
        ctx = (
            "Topic: My Body (Class 1 EVS, CBSE). "
            "Cover basic body parts: head, eyes, ears, nose, mouth, hands, legs, feet. "
            "Simple functions: eyes help us see, ears help us hear. "
            "Use Indian contexts: clapping hands, running in the playground. "
            "Keep vocabulary VERY simple — Class 1 level. NO internal organs. "
            "DO NOT repeat the same body part. "
        )
        tag_map = {
            "sci_c1_body_identify": "Identify a body part. Example: 'Which part helps us see? (a) Ears (b) Eyes (c) Nose (d) Mouth' -> Eyes",
            "sci_c1_body_apply": "format: explain_why_science. Simple explanation. Example: 'Why do we need legs?'",
            "sci_c1_body_represent": "format: fill_diagram. Match parts to use. Example: 'Match: Eyes -> ___. Ears -> ___. (hear / see)'",
            "sci_c1_body_error": "format: error_spot_science. Present a WRONG fact. Example: 'We smell with our eyes.' Ask: 'Find the mistake and correct it.'",
            "sci_c1_body_thinking": "format: thinking_science. Simple reasoning. Example: 'What would happen if we could not hear? Tell one thing.'",
        }
        return ctx + tag_map.get(_skill_tag, "About body parts.")

    # ── EVS Class 1: Plants Around Us ──
    if _skill_tag.startswith("sci_c1_plants_"):
        ctx = (
            "Topic: Plants Around Us (Class 1 EVS, CBSE). "
            "Cover common plants: neem, tulsi, mango, banyan, marigold, sunflower. "
            "Simple parts: leaf, flower, stem. Plants need water and sun. "
            "Use Indian contexts: tulsi at home, mango tree in garden. "
            "Keep vocabulary VERY simple — Class 1 level. NO photosynthesis. "
            "DO NOT repeat the same plant. "
        )
        tag_map = {
            "sci_c1_plants_identify": "Identify a plant or part. Example: 'Which part of the plant is green and flat? (a) Root (b) Leaf (c) Flower (d) Fruit' -> Leaf",
            "sci_c1_plants_apply": "format: give_example. Ask for examples. Example: 'Name two trees you see near your house.'",
            "sci_c1_plants_represent": "format: sequence_steps. Simple order. Example: 'What comes first? (a) Big tree (b) Tiny plant (c) Seed in soil' -> Put in order.",
            "sci_c1_plants_error": "format: error_spot_science. Present a WRONG fact. Example: 'Plants do not need water to grow.' Ask: 'Find the mistake and correct it.'",
            "sci_c1_plants_thinking": "format: thinking_science. Simple reasoning. Example: 'Why should we water plants every day?'",
        }
        return ctx + tag_map.get(_skill_tag, "About plants.")

    # ── EVS Class 1: Animals Around Us ──
    if _skill_tag.startswith("sci_c1_animals_"):
        ctx = (
            "Topic: Animals Around Us (Class 1 EVS, CBSE). "
            "Cover common animals: cow, dog, cat, hen, parrot, fish, elephant, monkey, squirrel. "
            "Simple groups: pets, farm animals, wild animals. Where they live, what they eat. "
            "Use Indian animals: peacock, cow, parrot, monkey. "
            "Keep vocabulary VERY simple — Class 1 level. "
            "DO NOT repeat the same animal. "
        )
        tag_map = {
            "sci_c1_animals_identify": "Identify or classify an animal. Example: 'Which animal gives us milk? (a) Dog (b) Cat (c) Cow (d) Parrot' -> Cow",
            "sci_c1_animals_apply": "format: compare_two. Simple comparison. Example: 'How is a fish different from a bird?'",
            "sci_c1_animals_represent": "format: cause_effect. Simple cause-effect. Example: 'A bird has wings -> it can ___.'",
            "sci_c1_animals_error": "format: error_spot_science. Present a WRONG fact. Example: 'A fish lives on land.' Ask: 'Find the mistake and correct it.'",
            "sci_c1_animals_thinking": "format: thinking_science. Simple reasoning. Example: 'Why does a dog wag its tail?'",
        }
        return ctx + tag_map.get(_skill_tag, "About animals.")

    # ── EVS Class 1: Food We Eat ──
    if _skill_tag.startswith("sci_c1_food_"):
        ctx = (
            "Topic: Food We Eat (Class 1 EVS, CBSE). "
            "Cover basic foods: roti, rice, dal, milk, banana, mango, curd, idli, sabzi. "
            "Food comes from plants or animals. We eat food to stay strong. "
            "Use Indian foods and contexts: tiffin at school, Amma cooking. "
            "Keep vocabulary VERY simple — Class 1 level. NO nutrition science. "
            "DO NOT repeat the same food item. "
        )
        tag_map = {
            "sci_c1_food_identify": "Identify a food. Example: 'Which food comes from a cow? (a) Rice (b) Milk (c) Mango (d) Roti' -> Milk",
            "sci_c1_food_apply": "format: give_example. Ask for examples. Example: 'Name two fruits you like to eat.'",
            "sci_c1_food_represent": "format: fill_diagram. Classify foods. Example: 'Which comes from plants? Which from animals? Rice, Milk, Banana, Egg'",
            "sci_c1_food_error": "format: error_spot_science. Present a WRONG fact. Example: 'We get rice from a cow.' Ask: 'Find the mistake and correct it.'",
            "sci_c1_food_thinking": "format: thinking_science. Simple reasoning. Example: 'Why should we eat fruits and vegetables every day?'",
        }
        return ctx + tag_map.get(_skill_tag, "About food.")

    # ── EVS Class 1: Seasons and Weather ──
    if _skill_tag.startswith("sci_c1_seasons_"):
        ctx = (
            "Topic: Seasons and Weather (Class 1 EVS, CBSE). "
            "Cover three seasons: summer (hot), rainy/monsoon (wet), winter (cold). "
            "Weather words: hot, cold, rainy, windy, sunny, cloudy. "
            "Clothes for each season: cotton in summer, raincoat in rain, sweater in winter. "
            "Use Indian contexts: monsoon, Sankranti kites, Diwali in autumn. "
            "Keep vocabulary VERY simple — Class 1 level. "
            "DO NOT repeat the same season or scenario. "
        )
        tag_map = {
            "sci_c1_seasons_identify": "Identify a season or weather. Example: 'In which season do we wear sweaters? (a) Summer (b) Rainy (c) Winter' -> Winter",
            "sci_c1_seasons_apply": "format: what_happens_if. Simple cause. Example: 'What happens when it rains a lot?'",
            "sci_c1_seasons_represent": "format: cause_effect. Match season to activity. Example: 'Summer is hot -> we drink more ___.'",
            "sci_c1_seasons_error": "format: error_spot_science. Present a WRONG fact. Example: 'We wear sweaters in summer because it is hot.' Ask: 'Find the mistake and correct it.'",
            "sci_c1_seasons_thinking": "format: thinking_science. Simple reasoning. Example: 'Why do we carry an umbrella in the rainy season?'",
        }
        return ctx + tag_map.get(_skill_tag, "About seasons and weather.")

    # ── EVS Class 2: Plants ──
    if _skill_tag.startswith("sci_c2_plants_"):
        ctx = (
            "Topic: Plants (Class 2 EVS, CBSE). "
            "Cover parts of a plant (root, stem, leaf, flower, fruit, seed), how a seed grows, "
            "plants give us food, shade, and fresh air. "
            "Use Indian plants: neem, tulsi, mango, banyan, lotus, coconut, marigold. "
            "Keep sentences simple — Class 2 level. NO photosynthesis detail. "
            "DO NOT repeat the same plant or concept. "
        )
        tag_map = {
            "sci_c2_plants_identify": "Identify a plant part or type. Example: 'Which part of the plant takes in water from the soil? (a) Leaf (b) Root (c) Flower (d) Fruit' -> Root",
            "sci_c2_plants_apply": "format: explain_why_science. Explain a concept. Example: 'Why do plants need sunlight?'",
            "sci_c2_plants_represent": "format: sequence_steps. Arrange steps. Example: 'Put in order: A seed is planted -> It gets water -> A tiny plant comes out -> The plant grows big.'",
            "sci_c2_plants_error": "format: error_spot_science. Present a WRONG fact. Example: 'Roots of a plant make flowers.' Ask: 'Find the mistake and correct it.'",
            "sci_c2_plants_thinking": "format: thinking_science. Reasoning question. Example: 'What would happen if a plant does not get water for many days?'",
        }
        return ctx + tag_map.get(_skill_tag, "About plants.")

    # ── EVS Class 2: Animals and Habitats ──
    if _skill_tag.startswith("sci_c2_animals_"):
        ctx = (
            "Topic: Animals and Habitats (Class 2 EVS, CBSE). "
            "Cover pet, farm, and wild animals. Where animals live (forest, water, desert, home). "
            "What they eat, how they move (fly, swim, walk, crawl). "
            "Use Indian animals: peacock, cow, camel, elephant, parrot, cobra, monkey. "
            "Keep sentences simple — Class 2 level. NO scientific classification. "
            "DO NOT repeat the same animal or concept. "
        )
        tag_map = {
            "sci_c2_animals_identify": "Classify or identify an animal. Example: 'Which animal lives in water? (a) Cow (b) Fish (c) Dog (d) Parrot' -> Fish",
            "sci_c2_animals_apply": "format: compare_two. Compare animals. Example: 'How is a camel different from a fish?'",
            "sci_c2_animals_represent": "format: cause_effect. Cause and effect. Example: 'A frog lives near water -> it can ___.'",
            "sci_c2_animals_error": "format: error_spot_science. Present a WRONG fact. Example: 'A parrot lives in water.' Ask: 'Find the mistake and correct it.'",
            "sci_c2_animals_thinking": "format: thinking_science. Reasoning. Example: 'Why do you think birds have wings but cows do not?'",
        }
        return ctx + tag_map.get(_skill_tag, "About animals and habitats.")

    # ── EVS Class 2: Food and Nutrition ──
    if _skill_tag.startswith("sci_c2_food_"):
        ctx = (
            "Topic: Food and Nutrition (Class 2 EVS, CBSE). "
            "Cover food groups: fruits, vegetables, grains, dairy. Sources: plants or animals. "
            "Eating different foods keeps us healthy. "
            "Use Indian foods: dal, roti, rice, curd, paneer, sabzi, jaggery, idli. "
            "Keep sentences simple — Class 2 level. NO calorie or vitamin details. "
            "DO NOT repeat the same food item or concept. "
        )
        tag_map = {
            "sci_c2_food_identify": "Identify food source or type. Example: 'Which food is a fruit? (a) Roti (b) Mango (c) Paneer (d) Rice' -> Mango",
            "sci_c2_food_apply": "format: give_example. Ask for examples. Example: 'Name two vegetables you eat at home.'",
            "sci_c2_food_represent": "format: fill_diagram. Classify foods. Example: 'Sort into groups — Fruits / Vegetables / Grains: apple, carrot, rice, banana, potato, wheat'",
            "sci_c2_food_error": "format: error_spot_science. Present a WRONG fact. Example: 'Rice is a fruit that grows on trees.' Ask: 'Find the mistake and correct it.'",
            "sci_c2_food_thinking": "format: thinking_science. Reasoning. Example: 'Why should we not eat only sweets every day?'",
        }
        return ctx + tag_map.get(_skill_tag, "About food and nutrition.")

    # ── EVS Class 2: Water ──
    if _skill_tag.startswith("sci_c2_water_"):
        ctx = (
            "Topic: Water (Class 2 EVS, CBSE). "
            "Cover sources of water (rain, river, well, tap), uses (drinking, cooking, washing, farming), "
            "why we should save water, clean vs dirty water. "
            "Use Indian contexts: hand pump, monsoon, village well, water tanker. "
            "Keep sentences simple — Class 2 level. NO water cycle detail. "
            "DO NOT repeat the same concept or context. "
        )
        tag_map = {
            "sci_c2_water_identify": "Identify facts about water. Example: 'True or False: We use water for cooking.' -> True",
            "sci_c2_water_apply": "format: what_happens_if. Cause-effect. Example: 'What happens if we drink dirty water?'",
            "sci_c2_water_represent": "format: sequence_steps. Simple order. Example: 'Put in order: Turn on the tap -> Fill the glass -> Drink the water -> Close the tap.'",
            "sci_c2_water_error": "format: error_spot_science. Present a WRONG fact. Example: 'We should waste water because there is a lot of it.' Ask: 'Find the mistake and correct it.'",
            "sci_c2_water_thinking": "format: thinking_science. Reasoning. Example: 'Name two ways you can save water at home.'",
        }
        return ctx + tag_map.get(_skill_tag, "About water.")

    # ── EVS Class 2: Shelter ──
    if _skill_tag.startswith("sci_c2_shelter_"):
        ctx = (
            "Topic: Shelter (Class 2 EVS, CBSE). "
            "Cover why living things need shelter, types of houses (kutcha, pucca, tent, houseboat, flat), "
            "animal homes (nest, burrow, den, hive, web). "
            "Use Indian contexts: village house, city flat, houseboat in Kashmir, stilt house in Assam. "
            "Keep sentences simple — Class 2 level. "
            "DO NOT repeat the same shelter type. "
        )
        tag_map = {
            "sci_c2_shelter_identify": "Identify a shelter. Example: 'Where does a bird live? (a) Den (b) Nest (c) Burrow (d) Hive' -> Nest",
            "sci_c2_shelter_apply": "format: compare_two. Compare shelters. Example: 'How is a kutcha house different from a pucca house?'",
            "sci_c2_shelter_represent": "format: cause_effect. Cause and effect. Example: 'It rains a lot in Assam -> people build ___ houses.'",
            "sci_c2_shelter_error": "format: error_spot_science. Present a WRONG fact. Example: 'Bees live in a burrow.' Ask: 'Find the mistake and correct it.'",
            "sci_c2_shelter_thinking": "format: thinking_science. Reasoning. Example: 'Why do animals need homes just like people do?'",
        }
        return ctx + tag_map.get(_skill_tag, "About shelter.")

    # ── EVS Class 2: Our Senses ──
    if _skill_tag.startswith("sci_c2_senses_"):
        ctx = (
            "Topic: Our Senses (Class 2 EVS, CBSE). "
            "Cover five senses: eyes (see), ears (hear), nose (smell), tongue (taste), skin (touch/feel). "
            "Match senses to body parts and everyday experiences. "
            "Use Indian contexts: smelling flowers, tasting jalebi, hearing temple bells. "
            "Keep sentences simple — Class 2 level. NO nervous system. "
            "DO NOT repeat the same sense or scenario. "
        )
        tag_map = {
            "sci_c2_senses_identify": "Identify a sense organ. Example: 'Which body part helps us taste food? (a) Eyes (b) Ears (c) Tongue (d) Nose' -> Tongue",
            "sci_c2_senses_apply": "format: give_example. Ask for examples. Example: 'Name two things you can smell.'",
            "sci_c2_senses_represent": "format: fill_diagram. Match senses. Example: 'Match: Eyes -> ___. Nose -> ___. Tongue -> ___. (taste / see / smell)'",
            "sci_c2_senses_error": "format: error_spot_science. Present a WRONG fact. Example: 'We hear with our nose.' Ask: 'Find the mistake and correct it.'",
            "sci_c2_senses_thinking": "format: thinking_science. Reasoning. Example: 'Why are all five senses important to us? Give one reason.'",
        }
        return ctx + tag_map.get(_skill_tag, "About senses.")

    # ── Science Class 4: Living Things ──
    if _skill_tag.startswith("sci_c4_living_"):
        ctx = (
            "Topic: Living Things (Class 4 Science, CBSE). "
            "Cover classification of living vs non-living things, characteristics of living things "
            "(growth, respiration, reproduction, response to stimuli), basic plant and animal cell features. "
            "Use Indian examples: neem tree, cow, river stone, bicycle. "
            "DO NOT repeat the same example or concept. "
        )
        tag_map = {
            "sci_c4_living_identify": "Classify an object as living or non-living. Example: 'Which of these is a living thing? (a) Stone (b) Chair (c) Mushroom (d) Water' -> Mushroom",
            "sci_c4_living_apply": "format: compare_two. Compare features of two things. Example: 'How is a plant different from a rock? Give two reasons.'",
            "sci_c4_living_represent": "format: fill_diagram. Label or classify. Example: 'Put each item in the correct group — Living / Non-living: cow, table, tulsi, pencil.'",
            "sci_c4_living_error": "format: error_spot_science. Present a WRONG fact. Example: 'A car is a living thing because it moves.' Ask: 'Find the mistake and correct it.'",
            "sci_c4_living_thinking": "format: thinking_science. Ask reasoning. Example: 'A seed is kept in soil and watered. After a week it sprouts. Is the seed living or non-living? Explain your answer.'",
        }
        return ctx + tag_map.get(_skill_tag, "About living things.")

    # ── Science Class 4: Human Body ──
    if _skill_tag.startswith("sci_c4_humanbody_"):
        ctx = (
            "Topic: Human Body (Class 4 Science, CBSE). "
            "Cover the digestive system (mouth, food pipe, stomach, small intestine, large intestine), "
            "skeletal system (skull, ribcage, backbone, joints — hinge, ball-and-socket). "
            "Use Indian contexts: eating roti, chewing sugarcane, playing kabaddi, doing yoga. "
            "DO NOT repeat the same organ or concept. "
        )
        tag_map = {
            "sci_c4_humanbody_identify": "Identify a body part or organ. Example: 'Which organ breaks down food in our body? (a) Heart (b) Lungs (c) Stomach (d) Brain' -> Stomach",
            "sci_c4_humanbody_apply": "format: explain_why_science. Explain function. Example: 'Why do we need to chew food properly before swallowing?'",
            "sci_c4_humanbody_represent": "format: fill_diagram. Label parts. Example: 'Fill in the order: Mouth → ___ → Stomach → ___ → Large Intestine. (Food pipe / Small intestine)'",
            "sci_c4_humanbody_error": "format: error_spot_science. Present a WRONG fact. Example: 'The skull protects our stomach.' Ask: 'Find the mistake and correct it.'",
            "sci_c4_humanbody_thinking": "format: multi_step_science. Multi-step reasoning. Example: 'Ravi ate a roti. Describe the journey of that roti through his body in 3 steps.'",
        }
        return ctx + tag_map.get(_skill_tag, "About the human body.")

    # ── Science Class 4: States of Matter ──
    if _skill_tag.startswith("sci_c4_matter_"):
        ctx = (
            "Topic: States of Matter (Class 4 Science, CBSE). "
            "Cover three states of matter (solid, liquid, gas), properties of each (shape, volume, compressibility), "
            "changes of state (melting, freezing, evaporation, condensation, boiling). "
            "Use Indian contexts: making ice gola, boiling chai, drying clothes, morning dew. "
            "DO NOT repeat the same example or concept. "
        )
        tag_map = {
            "sci_c4_matter_identify": "Identify the state of matter. Example: 'What state of matter is steam? (a) Solid (b) Liquid (c) Gas (d) None' -> Gas",
            "sci_c4_matter_apply": "format: what_happens_if. Ask about changes. Example: 'What happens if you keep an ice cube on a plate in the sun?'",
            "sci_c4_matter_represent": "format: cause_effect. Show cause and effect. Example: 'Water is heated strongly → it turns into ___.'",
            "sci_c4_matter_error": "format: error_spot_science. Present a WRONG fact. Example: 'Gases have a fixed shape and volume.' Ask: 'Find the mistake and correct it.'",
            "sci_c4_matter_thinking": "format: thinking_science. Ask reasoning. Example: 'Why do wet clothes dry faster on a hot, windy day than on a cold day?'",
        }
        return ctx + tag_map.get(_skill_tag, "About states of matter.")

    # ── Science Class 4: Force and Motion ──
    if _skill_tag.startswith("sci_c4_force_"):
        ctx = (
            "Topic: Force and Motion (Class 4 Science, CBSE). "
            "Cover push and pull as forces, types of force (muscular, frictional, gravitational, magnetic), "
            "friction (rough vs smooth surfaces), gravity pulls things downward. "
            "Use Indian contexts: playing cricket, riding a bicycle, pulling a bullock cart, sliding on a playground slide. "
            "DO NOT repeat the same scenario or concept. "
        )
        tag_map = {
            "sci_c4_force_identify": "Identify type of force. Example: 'True or False: Friction helps us walk without slipping.' -> True",
            "sci_c4_force_apply": "format: explain_why_science. Explain a concept. Example: 'Why is it easier to slide on a polished floor than on a rough road?'",
            "sci_c4_force_represent": "format: cause_effect. Show cause and effect. Example: 'A ball is thrown upwards → ___ pulls it back down.'",
            "sci_c4_force_error": "format: error_spot_science. Present a WRONG fact. Example: 'Objects fall down because of friction.' Ask: 'Find the mistake and correct it.'",
            "sci_c4_force_thinking": "format: thinking_science. Ask reasoning. Example: 'Why do we put oil on a squeaky door hinge? What force are we reducing?'",
        }
        return ctx + tag_map.get(_skill_tag, "About force and motion.")

    # ── Science Class 4: Simple Machines ──
    if _skill_tag.startswith("sci_c4_machines_"):
        ctx = (
            "Topic: Simple Machines (Class 4 Science, CBSE). "
            "Cover six simple machines: lever, pulley, wheel and axle, inclined plane, wedge, screw. "
            "How they make work easier by changing force direction or reducing effort. "
            "Use Indian contexts: see-saw, well pulley, ramp at station, scissors, wheelbarrow. "
            "DO NOT repeat the same machine type or example. "
        )
        tag_map = {
            "sci_c4_machines_identify": "Match machine to function. Example: 'Which simple machine is used to draw water from a well? (a) Lever (b) Pulley (c) Wedge (d) Screw' -> Pulley",
            "sci_c4_machines_apply": "format: give_example. Ask for examples. Example: 'Give two examples of levers that you use at home or school.'",
            "sci_c4_machines_represent": "format: fill_diagram. Classify machines. Example: 'Write each item in the correct group — Lever / Pulley / Inclined Plane: see-saw, flag pole, ramp.'",
            "sci_c4_machines_error": "format: error_spot_science. Present a WRONG fact. Example: 'A see-saw is an example of a pulley.' Ask: 'Find the mistake and correct it.'",
            "sci_c4_machines_thinking": "format: multi_step_science. Multi-step reasoning. Example: 'A heavy box needs to be loaded onto a truck. Which two simple machines could help? Explain how each works.'",
        }
        return ctx + tag_map.get(_skill_tag, "About simple machines.")

    # ── Science Class 4: Photosynthesis ──
    if _skill_tag.startswith("sci_c4_photosyn_"):
        ctx = (
            "Topic: Photosynthesis (Class 4 Science, CBSE). "
            "Cover how plants make food: sunlight + water + carbon dioxide → food (glucose) + oxygen. "
            "Role of leaves (chlorophyll, stomata), roots absorb water, leaves absorb CO₂. "
            "Use Indian plants: neem, mango, tulsi, banyan, rice paddy. "
            "DO NOT repeat the same plant or concept. "
        )
        tag_map = {
            "sci_c4_photosyn_identify": "Identify a fact about photosynthesis. Example: 'What gas do plants take in during photosynthesis? (a) Oxygen (b) Nitrogen (c) Carbon dioxide (d) Hydrogen' -> Carbon dioxide",
            "sci_c4_photosyn_apply": "format: explain_why_science. Explain a concept. Example: 'Why are leaves green in colour?'",
            "sci_c4_photosyn_represent": "format: sequence_steps. Arrange steps. Example: 'Arrange the steps of photosynthesis in order: Plant makes food → Roots absorb water → Sunlight falls on leaves → Leaves take in CO₂.'",
            "sci_c4_photosyn_error": "format: error_spot_science. Present a WRONG fact. Example: 'Plants take in oxygen and give out carbon dioxide during photosynthesis.' Ask: 'Find the mistake and correct it.'",
            "sci_c4_photosyn_thinking": "format: thinking_science. Ask reasoning. Example: 'Why do you think plants kept in a dark cupboard for many days turn yellow and weak?'",
        }
        return ctx + tag_map.get(_skill_tag, "About photosynthesis.")

    # ── Science Class 4: Animal Adaptation ──
    if _skill_tag.startswith("sci_c4_adapt_"):
        ctx = (
            "Topic: Animal Adaptation (Class 4 Science, CBSE). "
            "Cover how animals adapt to survive: desert (camel — hump, long eyelashes), "
            "aquatic (fish — gills, streamlined body), polar (polar bear — thick fur, fat layer), "
            "forest (monkey — long arms, camouflage). Body features for food, movement, protection. "
            "Use Indian animals: camel, fish, frog, eagle, chameleon, yak. "
            "DO NOT repeat the same animal or adaptation. "
        )
        tag_map = {
            "sci_c4_adapt_identify": "Classify an adaptation. Example: 'Which animal is adapted to live in the desert? (a) Penguin (b) Camel (c) Whale (d) Frog' -> Camel",
            "sci_c4_adapt_apply": "format: compare_two. Compare adaptations. Example: 'How is a fish adapted to live in water differently from a frog?'",
            "sci_c4_adapt_represent": "format: cause_effect. Show cause and effect. Example: 'A polar bear has thick fur → it can survive in ___.'",
            "sci_c4_adapt_error": "format: error_spot_science. Present a WRONG fact. Example: 'Fish breathe using lungs.' Ask: 'Find the mistake and correct it.'",
            "sci_c4_adapt_thinking": "format: thinking_science. Ask reasoning. Example: 'Why do you think a chameleon changes its colour? How does this help it survive?'",
        }
        return ctx + tag_map.get(_skill_tag, "About animal adaptation.")

    # ── Science Class 5: Circulatory System ──
    if _skill_tag.startswith("sci_c5_circulatory_"):
        ctx = (
            "Topic: Circulatory System (Class 5 Science, CBSE). "
            "Cover the heart (4 chambers), blood vessels (arteries, veins, capillaries), "
            "blood flow path (heart → arteries → body → veins → heart), blood carries oxygen and nutrients. "
            "Use Indian contexts: feeling pulse after running, doctor's stethoscope, blood donation camp. "
            "DO NOT repeat the same organ or concept. "
        )
        tag_map = {
            "sci_c5_circulatory_identify": "Identify a part of the circulatory system. Example: 'Which blood vessels carry blood away from the heart? (a) Veins (b) Arteries (c) Capillaries (d) Nerves' -> Arteries",
            "sci_c5_circulatory_apply": "format: explain_why_science. Explain function. Example: 'Why does your heart beat faster when you run?'",
            "sci_c5_circulatory_represent": "format: sequence_steps. Arrange blood flow steps. Example: 'Arrange: Blood reaches lungs → Heart pumps blood → Blood picks up oxygen → Blood returns to heart.'",
            "sci_c5_circulatory_error": "format: error_spot_science. Present a WRONG fact. Example: 'Veins carry blood away from the heart.' Ask: 'Find the mistake and correct it.'",
            "sci_c5_circulatory_thinking": "format: multi_step_science. Multi-step reasoning. Example: 'Anita ran for 5 minutes. Her pulse went from 72 to 110. Why did this happen? What is her body doing?'",
        }
        return ctx + tag_map.get(_skill_tag, "About the circulatory system.")

    # ── Science Class 5: Respiratory and Nervous System ──
    if _skill_tag.startswith("sci_c5_respnerv_"):
        ctx = (
            "Topic: Respiratory and Nervous System (Class 5 Science, CBSE). "
            "Cover breathing (nose → windpipe → lungs → oxygen in, CO₂ out), "
            "nervous system (brain, spinal cord, nerves), reflex actions, five senses connected to brain. "
            "Use Indian contexts: pranayam, sneezing in dust, stepping on a thorn, smelling biryani. "
            "DO NOT repeat the same organ or concept. "
        )
        tag_map = {
            "sci_c5_respnerv_identify": "Identify a body part. Example: 'Which organ controls all our actions and thoughts? (a) Heart (b) Lungs (c) Brain (d) Stomach' -> Brain",
            "sci_c5_respnerv_apply": "format: explain_why_science. Explain function. Example: 'Why do we sneeze when dust enters our nose?'",
            "sci_c5_respnerv_represent": "format: fill_diagram. Label parts. Example: 'Fill in the breathing path: Nose → ___ → Lungs. (Windpipe / Stomach)'",
            "sci_c5_respnerv_error": "format: error_spot_science. Present a WRONG fact. Example: 'We breathe in carbon dioxide and breathe out oxygen.' Ask: 'Find the mistake and correct it.'",
            "sci_c5_respnerv_thinking": "format: thinking_science. Ask reasoning. Example: 'When you touch a hot tawa, your hand pulls back instantly. Why does this happen without you thinking about it?'",
        }
        return ctx + tag_map.get(_skill_tag, "About respiratory and nervous systems.")

    # ── Science Class 5: Reproduction in Plants and Animals ──
    if _skill_tag.startswith("sci_c5_reprod_"):
        ctx = (
            "Topic: Reproduction in Plants and Animals (Class 5 Science, CBSE). "
            "Cover plant reproduction: parts of a flower (petals, stamens, pistil), pollination (insects, wind), "
            "seed formation, seed dispersal. Animal reproduction: egg-laying (birds, reptiles, fish), live birth (mammals). "
            "Use Indian contexts: mango flowering, bees on marigold, hen and eggs, puppies born. "
            "DO NOT repeat the same example or concept. "
        )
        tag_map = {
            "sci_c5_reprod_identify": "Identify a fact about reproduction. Example: 'Which part of a flower develops into a fruit? (a) Petal (b) Sepal (c) Pistil (d) Stamen' -> Pistil",
            "sci_c5_reprod_apply": "format: compare_two. Compare methods. Example: 'How is egg-laying in a hen different from live birth in a cow?'",
            "sci_c5_reprod_represent": "format: sequence_steps. Arrange steps. Example: 'Arrange: Seed grows into a plant → Flower produces seeds → Pollination occurs → Flower blooms.'",
            "sci_c5_reprod_error": "format: error_spot_science. Present a WRONG fact. Example: 'Seeds are formed inside the stamen of a flower.' Ask: 'Find the mistake and correct it.'",
            "sci_c5_reprod_thinking": "format: thinking_science. Ask reasoning. Example: 'Why do you think some fruits are sweet and colourful? How does this help the plant?'",
        }
        return ctx + tag_map.get(_skill_tag, "About reproduction.")

    # ── Science Class 5: Physical and Chemical Changes ──
    if _skill_tag.startswith("sci_c5_changes_"):
        ctx = (
            "Topic: Physical and Chemical Changes (Class 5 Science, CBSE). "
            "Cover physical changes (reversible — melting ice, folding paper, dissolving sugar), "
            "chemical changes (irreversible — burning, rusting, cooking, curdling milk). "
            "Use Indian contexts: making paneer, rusting iron gate, burning wood on Lohri, making curd. "
            "DO NOT repeat the same example or change type. "
        )
        tag_map = {
            "sci_c5_changes_identify": "Classify a change. Example: 'Is melting of ice a physical or chemical change? (a) Physical (b) Chemical' -> Physical",
            "sci_c5_changes_apply": "format: what_happens_if. Ask about changes. Example: 'What happens if you leave an iron nail in water for a week?'",
            "sci_c5_changes_represent": "format: cause_effect. Show cause and effect. Example: 'Lemon juice is added to hot milk → ___ is formed.'",
            "sci_c5_changes_error": "format: error_spot_science. Present a WRONG fact. Example: 'Burning a piece of paper is a reversible change.' Ask: 'Find the mistake and correct it.'",
            "sci_c5_changes_thinking": "format: thinking_science. Ask reasoning. Example: 'You can melt ice back into water, but you cannot un-cook an egg. Why is cooking called a chemical change?'",
        }
        return ctx + tag_map.get(_skill_tag, "About physical and chemical changes.")

    # ── Science Class 5: Forms of Energy ──
    if _skill_tag.startswith("sci_c5_energy_"):
        ctx = (
            "Topic: Forms of Energy (Class 5 Science, CBSE). "
            "Cover different forms: heat, light, sound, electrical, kinetic, potential. "
            "Energy conversion examples: bulb (electrical → light + heat), drum (kinetic → sound). "
            "Use Indian contexts: solar panel, Diwali diyas, tabla, windmill in Rajasthan, pressure cooker. "
            "DO NOT repeat the same energy form or example. "
        )
        tag_map = {
            "sci_c5_energy_identify": "Identify a form of energy. Example: 'What form of energy does a burning candle give? (a) Sound (b) Light and heat (c) Electrical (d) Magnetic' -> Light and heat",
            "sci_c5_energy_apply": "format: give_example. Ask for examples. Example: 'Give two examples of objects that convert electrical energy into sound energy.'",
            "sci_c5_energy_represent": "format: cause_effect. Show energy conversion. Example: 'Pressing a switch → electrical energy → light bulb glows. The electrical energy changes into ___ and ___.'",
            "sci_c5_energy_error": "format: error_spot_science. Present a WRONG fact. Example: 'A solar panel converts sound energy into light energy.' Ask: 'Find the mistake and correct it.'",
            "sci_c5_energy_thinking": "format: multi_step_science. Multi-step reasoning. Example: 'Ravi claps his hands and makes a sound. Describe the energy changes that happen from start to finish.'",
        }
        return ctx + tag_map.get(_skill_tag, "About forms of energy.")

    # ── Science Class 5: Solar System and Earth ──
    if _skill_tag.startswith("sci_c5_solar_"):
        ctx = (
            "Topic: Solar System and Earth (Class 5 Science, CBSE). "
            "Cover the sun, 8 planets in order (Mercury to Neptune), Earth's rotation (day/night), "
            "Earth's revolution (seasons), moon phases, basic facts about each planet. "
            "Use Indian contexts: Chandrayaan mission, sunrise times, seasons in India, planetarium visits. "
            "DO NOT repeat the same planet or concept. "
        )
        tag_map = {
            "sci_c5_solar_identify": "Identify a fact about the solar system. Example: 'True or False: Mars is the largest planet in the solar system.' -> False",
            "sci_c5_solar_apply": "format: explain_why_science. Explain a concept. Example: 'Why do we have day and night on Earth?'",
            "sci_c5_solar_represent": "format: sequence_steps. Arrange planets. Example: 'Arrange these planets from closest to farthest from the Sun: Earth, Mars, Mercury, Venus.'",
            "sci_c5_solar_error": "format: error_spot_science. Present a WRONG fact. Example: 'The moon produces its own light.' Ask: 'Find the mistake and correct it.'",
            "sci_c5_solar_thinking": "format: thinking_science. Ask reasoning. Example: 'India has very hot summers and cold winters. What causes this change in seasons? Explain.'",
        }
        return ctx + tag_map.get(_skill_tag, "About the solar system.")

    # ── Science Class 5: Ecosystem and Food Chains ──
    if _skill_tag.startswith("sci_c5_ecosystem_"):
        ctx = (
            "Topic: Ecosystem and Food Chains (Class 5 Science, CBSE). "
            "Cover producers (plants), consumers (herbivores, carnivores, omnivores), decomposers (fungi, bacteria), "
            "food chains (grass → deer → tiger), food webs, interdependence of living things. "
            "Use Indian contexts: Ranthambore, rice paddy ecosystem, village pond, forest near a hill station. "
            "DO NOT repeat the same food chain or organism. "
        )
        tag_map = {
            "sci_c5_ecosystem_identify": "Classify an organism. Example: 'In a food chain, what is a deer? (a) Producer (b) Herbivore (c) Carnivore (d) Decomposer' -> Herbivore",
            "sci_c5_ecosystem_apply": "format: explain_why_science. Explain a concept. Example: 'Why are plants called producers in a food chain?'",
            "sci_c5_ecosystem_represent": "format: sequence_steps. Build a food chain. Example: 'Arrange into a food chain: Tiger, Grass, Deer → ___ → ___ → ___.'",
            "sci_c5_ecosystem_error": "format: error_spot_science. Present a WRONG fact. Example: 'A tiger is a producer in the food chain.' Ask: 'Find the mistake and correct it.'",
            "sci_c5_ecosystem_thinking": "format: thinking_science. Ask reasoning. Example: 'If all the frogs in a paddy field disappeared, what would happen to the insects and snakes? Explain.'",
        }
        return ctx + tag_map.get(_skill_tag, "About ecosystems and food chains.")

    # ── Hindi Varnamala (Class 3) ──
    if _skill_tag.startswith("hin_varna_"):
        hin_varna_ctx = (
            "Topic: Varnamala (Class 3 Hindi, CBSE). "
            "Cover Hindi alphabet: swar (अ, आ, इ, ई, उ, ऊ, ए, ऐ, ओ, औ, अं, अः) and "
            "vyanjan (क, ख, ग, घ... to ज्ञ). Letter recognition, sounds, and usage in words. "
            "MUST use Devanagari script for all questions and answers. "
            "DO NOT repeat the same letter or word. "
        )
        hin_varna_map = {
            "hin_varna_identify": "format: identify_letter. Identify a Hindi letter or its type. Example: 'इनमें से कौन सा स्वर है? (क) क (ख) आ (ग) ग (घ) म' → आ",
            "hin_varna_use": "format: fill_matra. Use a letter to complete a word. Example: 'रिक्त स्थान भरो: ___मल (क/ख/ग/घ)' → कमल",
            "hin_varna_complete": "format: complete_word. Complete a word with the missing letter. Example: 'शब्द पूरा करो: प___ल' → पहल",
            "hin_varna_error": "format: error_spot_hindi. Present a WRONG letter usage. Example: 'गलती ढूँढो: \"सेब\" में \"स\" एक स्वर है।' Ask: 'गलती ढूँढो और सही करो।'",
            "hin_varna_thinking": "format: explain_meaning. Ask reasoning about letters. Example: 'स्वर और व्यंजन में क्या अंतर है? अपने शब्दों में समझाओ।'",
        }
        return hin_varna_ctx + hin_varna_map.get(_skill_tag, "About Hindi Varnamala.")

    # ── Hindi Matras (Class 3) ──
    if _skill_tag.startswith("hin_matra_"):
        hin_matra_ctx = (
            "Topic: Matras (Class 3 Hindi, CBSE). "
            "Cover vowel signs (matras): aa (ा), i (ि), ee (ी), u (ु), oo (ू), "
            "e (े), ai (ै), o (ो), au (ौ), anusvaar (ं), visarg (ः). "
            "Forming and reading words with matras. "
            "MUST use Devanagari script for all questions and answers. "
            "DO NOT repeat the same matra or word. "
        )
        hin_matra_map = {
            "hin_matra_identify": "format: identify_matra. Identify the matra in a word. Example: 'शब्द \"काम\" में कौन सी मात्रा है? (क) इ की मात्रा (ख) आ की मात्रा (ग) उ की मात्रा (घ) ए की मात्रा' → आ की मात्रा",
            "hin_matra_fill": "format: fill_matra. Fill in the correct matra. Example: 'सही मात्रा लगाकर शब्द बनाओ: क___ला (ा / ि / ी / ु)' → केला",
            "hin_matra_complete": "format: complete_word. Complete the word with correct matra. Example: 'शब्द पूरा करो: ग___ला' → गुलाब → गाला",
            "hin_matra_error": "format: error_spot_hindi. Present a word with WRONG matra. Example: 'गलती ढूँढो: \"किताब\" को \"कीताब\" लिखा गया है।' Ask: 'गलती सही करो।'",
            "hin_matra_thinking": "format: explain_meaning. Ask about matra usage. Example: '\"कल\" और \"काल\" में क्या अंतर है? समझाओ।'",
        }
        return hin_matra_ctx + hin_matra_map.get(_skill_tag, "About Hindi Matras.")

    # ── Hindi Shabd Rachna (Class 3) ──
    if _skill_tag.startswith("hin_shabd_"):
        hin_shabd_ctx = (
            "Topic: Shabd Rachna (Class 3 Hindi, CBSE). "
            "Cover word formation: prefix (upsarg), suffix (pratyay), compound words (samas/sanyukt shabd), "
            "synonyms (paryayvachi), antonyms (vilom shabd), word building from syllables. "
            "MUST use Devanagari script for all questions and answers. "
            "DO NOT repeat the same word or word pair. "
        )
        hin_shabd_map = {
            "hin_shabd_identify": "format: identify_word_type. Identify word type. Example: '\"सुंदर\" का विलोम शब्द कौन सा है? (क) अच्छा (ख) कुरूप (ग) बड़ा (घ) छोटा' → कुरूप",
            "hin_shabd_make": "format: make_word. Form a new word. Example: 'इन अक्षरों से शब्द बनाओ: म, क, ा, न' → मकान",
            "hin_shabd_complete": "format: word_formation. Complete word formation. Example: '\"अन\" उपसर्ग लगाकर नया शब्द बनाओ: ___ + पढ़ = ___' → अनपढ़",
            "hin_shabd_error": "format: error_spot_hindi. Present a WRONG word formation. Example: 'गलती ढूँढो: \"बड़ा\" का विलोम शब्द \"लम्बा\" है।' Ask: 'गलती सही करो।'",
            "hin_shabd_thinking": "format: explain_meaning. Ask about word meaning. Example: '\"विद्यालय\" शब्द किन दो शब्दों से मिलकर बना है? समझाओ।'",
        }
        return hin_shabd_ctx + hin_shabd_map.get(_skill_tag, "About Hindi Shabd Rachna.")

    # ── Hindi Vakya Rachna (Class 3) ──
    if _skill_tag.startswith("hin_vakya_"):
        hin_vakya_ctx = (
            "Topic: Vakya Rachna (Class 3 Hindi, CBSE). "
            "Cover sentence formation: simple Hindi sentences, word order (subject-object-verb), "
            "punctuation (poorn viram, prashn chinh), sentence types (statement, question, exclamation). "
            "MUST use Devanagari script for all questions and answers. "
            "DO NOT repeat the same sentence or structure. "
        )
        hin_vakya_map = {
            "hin_vakya_identify": "format: pick_correct_hindi. Identify sentence type. Example: 'कौन सा वाक्य सही है? (क) गया बाज़ार राम (ख) राम बाज़ार गया (ग) बाज़ार गया राम (घ) राम गया बाज़ार' → राम बाज़ार गया",
            "hin_vakya_make": "format: make_sentence_hindi. Make a sentence. Example: 'इन शब्दों से वाक्य बनाओ: खेलते / बच्चे / हैं / मैदान में' → बच्चे मैदान में खेलते हैं।",
            "hin_vakya_rearrange": "format: rearrange_letters. Rearrange words. Example: 'शब्दों को सही क्रम में लगाओ: है / मीठा / आम / बहुत' → आम बहुत मीठा है।",
            "hin_vakya_error": "format: error_spot_hindi. Present a sentence with WRONG word order or punctuation. Example: 'गलती ढूँढो: \"सीता ने खाना खाया\"' Ask: 'विराम चिह्न लगाओ।'",
            "hin_vakya_thinking": "format: creative_writing_hindi. Creative writing. Example: 'अपने विद्यालय के बारे में तीन वाक्य लिखो।'",
        }
        return hin_vakya_ctx + hin_vakya_map.get(_skill_tag, "About Hindi Vakya Rachna.")

    # ── Hindi Kahani Lekhan (Class 3) ──
    if _skill_tag.startswith("hin_kahani_"):
        hin_kahani_ctx = (
            "Topic: Kahani Lekhan (Class 3 Hindi, CBSE). "
            "Cover story/passage comprehension: reading short Hindi passages, answering questions, "
            "writing short paragraphs, moral of the story, story sequencing. "
            "Use Indian stories: Panchatantra, Birbal, folk tales, festival stories. "
            "MUST use Devanagari script for all questions and answers. "
            "DO NOT repeat the same story or passage theme. "
        )
        hin_kahani_map = {
            "hin_kahani_identify": "format: pick_correct_hindi. Comprehension question. Example: Provide a short passage (2-3 lines) then ask: 'इस कहानी का मुख्य पात्र कौन है? (क) लोमड़ी (ख) शेर (ग) खरगोश (घ) हाथी' → लोमड़ी",
            "hin_kahani_answer": "format: word_problem_hindi. Answer from passage. Example: Provide a short passage then ask: 'लोमड़ी ने क्या किया? अपने शब्दों में लिखो।'",
            "hin_kahani_complete": "format: complete_sentence_hindi. Complete from passage. Example: 'कहानी पूरी करो: एक दिन एक चिड़िया ___ पर बैठी थी।'",
            "hin_kahani_error": "format: error_spot_hindi. Present a WRONG fact from a story. Example: 'गलती ढूँढो: पंचतंत्र की कहानी में खरगोश ने कछुए से दौड़ में हार मानी।' Ask: 'गलती सही करो।'",
            "hin_kahani_thinking": "format: creative_writing_hindi. Creative writing. Example: 'अगर तुम जंगल में होते तो क्या करते? कल्पना करो और लिखो।'",
        }
        return hin_kahani_ctx + hin_kahani_map.get(_skill_tag, "About Hindi Kahani Lekhan.")

    # ── Computer Science: Parts of Computer (Class 1) ──
    if _skill_tag.startswith("comp_c1_parts_"):
        comp_parts_ctx = (
            "Topic: Parts of Computer (Class 1 Computer, CBSE). "
            "Cover the 5 main parts: Monitor (screen), Keyboard (typing), Mouse (pointing/clicking), "
            "CPU (brain of the computer), Speaker (sound). "
            "Use Indian school contexts: computer lab, IT period. "
            "Keep vocabulary VERY simple — Class 1 level. NO technical specs. "
            "DO NOT repeat the same computer part or scenario. "
        )
        comp_parts_map = {
            "comp_c1_parts_identify": "format: pick_correct_science. Identify a computer part. Example: 'Which part of the computer do you use to type letters? (a) Mouse (b) Monitor (c) Keyboard (d) Speaker' -> Keyboard",
            "comp_c1_parts_apply": "format: explain_why_science. Simple explanation. Example: 'Why do we need a monitor? Tell one reason.'",
            "comp_c1_parts_represent": "format: fill_diagram. Match parts to functions. Example: 'Match: Mouse -> ___. Speaker -> ___. (pointing / sound)'",
            "comp_c1_parts_error": "format: error_spot_science. Present a WRONG fact. Example: 'We use the speaker to type letters.' Ask: 'Find the mistake and correct it.'",
            "comp_c1_parts_thinking": "format: thinking_science. Simple reasoning. Example: 'What would happen if a computer had no monitor? Tell one thing.'",
        }
        return comp_parts_ctx + comp_parts_map.get(_skill_tag, "About parts of a computer.")

    # ── Computer Science: Using Mouse and Keyboard (Class 1) ──
    if _skill_tag.startswith("comp_c1_mouse_"):
        comp_mouse_ctx = (
            "Topic: Using Mouse and Keyboard (Class 1 Computer, CBSE). "
            "Cover mouse actions: left click, right click, double click, drag. "
            "Cover keyboard basics: typing letters, space bar, enter key. "
            "Use Indian school contexts: IT class, computer lab. "
            "Keep vocabulary VERY simple — Class 1 level. "
            "DO NOT repeat the same action or scenario. "
        )
        comp_mouse_map = {
            "comp_c1_mouse_identify": "format: true_false. True/false about mouse or keyboard. Example: 'True or False: We use the left button of the mouse to click on things.' -> True",
            "comp_c1_mouse_apply": "format: give_example. Ask for examples. Example: 'Name two things you can do with a mouse.'",
            "comp_c1_mouse_represent": "format: sequence_steps. Order the steps. Example: 'Put in order: (a) Move the mouse pointer to the icon (b) Double-click (c) The program opens'",
            "comp_c1_mouse_error": "format: error_spot_science. Present a WRONG fact. Example: 'To open a program, you right-click on it once.' Ask: 'Find the mistake and correct it.'",
            "comp_c1_mouse_thinking": "format: thinking_science. Simple reasoning. Example: 'Why do you think we need both a mouse and a keyboard? Can we use only one?'",
        }
        return comp_mouse_ctx + comp_mouse_map.get(_skill_tag, "About using mouse and keyboard.")

    # ── Computer Science: Desktop and Icons (Class 2) ──
    if _skill_tag.startswith("comp_c2_desktop_"):
        comp_desktop_ctx = (
            "Topic: Desktop and Icons (Class 2 Computer, CBSE). "
            "Cover desktop elements: icons, taskbar, start menu, wallpaper, Recycle Bin. "
            "Explain how to open programs, find applications. "
            "Use Indian school contexts: school computer lab, IT period. "
            "Keep vocabulary simple — Class 2 level. "
            "DO NOT repeat the same desktop element or scenario. "
        )
        comp_desktop_map = {
            "comp_c2_desktop_identify": "format: pick_correct_science. Identify desktop elements. Example: 'Where do you click to find all programs on the computer? (a) Recycle Bin (b) Taskbar (c) Start Menu (d) Wallpaper' -> Start Menu",
            "comp_c2_desktop_apply": "format: explain_why_science. Explain purpose. Example: 'Why do we have a Recycle Bin on the desktop?'",
            "comp_c2_desktop_represent": "format: fill_diagram. Match elements to functions. Example: 'Match: Start Menu -> ___. Recycle Bin -> ___. (find programs / deleted files)'",
            "comp_c2_desktop_error": "format: error_spot_science. Present a WRONG fact. Example: 'The Recycle Bin is used to open new programs.' Ask: 'Find the mistake and correct it.'",
            "comp_c2_desktop_thinking": "format: thinking_science. Reasoning question. Example: 'Why do you think icons have different pictures on them?'",
        }
        return comp_desktop_ctx + comp_desktop_map.get(_skill_tag, "About desktop and icons.")

    # ── Computer Science: Basic Typing (Class 2) ──
    if _skill_tag.startswith("comp_c2_typing_"):
        comp_typing_ctx = (
            "Topic: Basic Typing (Class 2 Computer, CBSE). "
            "Cover home row keys (A, S, D, F, J, K, L), correct posture, "
            "proper finger placement, typing simple words and sentences. "
            "Use Indian school contexts: IT class, typing practice. "
            "Keep vocabulary simple — Class 2 level. "
            "DO NOT repeat the same typing concept. "
        )
        comp_typing_map = {
            "comp_c2_typing_identify": "format: true_false. True/false about typing. Example: 'True or False: The home row keys are A, S, D, F, J, K, L.' -> True",
            "comp_c2_typing_apply": "format: give_example. Ask about typing practice. Example: 'Name the four keys your left hand rests on in the home row.'",
            "comp_c2_typing_represent": "format: sequence_steps. Order typing steps. Example: 'Put in order: (a) Place fingers on home row (b) Sit straight (c) Look at the screen and type'",
            "comp_c2_typing_error": "format: error_spot_science. Present a WRONG fact. Example: 'For correct typing posture, you should slouch in your chair.' Ask: 'Find the mistake and correct it.'",
            "comp_c2_typing_thinking": "format: thinking_science. Reasoning question. Example: 'Why is it important to sit straight while typing? Give one reason.'",
        }
        return comp_typing_ctx + comp_typing_map.get(_skill_tag, "About basic typing.")

    # ── Computer Science: Special Keys (Class 2) ──
    if _skill_tag.startswith("comp_c2_special_"):
        comp_special_ctx = (
            "Topic: Special Keys (Class 2 Computer, CBSE). "
            "Cover special keys: Enter (new line/confirm), Space (gap between words), "
            "Backspace (erase left), Shift (capital letters), Caps Lock (all capitals), "
            "Tab (indent), Delete (erase right), Escape (cancel). "
            "Use Indian school contexts: typing class, IT lab. "
            "Keep vocabulary simple — Class 2 level. "
            "DO NOT repeat the same key. "
        )
        comp_special_map = {
            "comp_c2_special_identify": "format: pick_correct_science. Identify special keys. Example: 'Which key do you press to erase the letter on the left? (a) Enter (b) Backspace (c) Space (d) Shift' -> Backspace",
            "comp_c2_special_apply": "format: explain_why_science. Explain purpose. Example: 'Why do we press the Space bar while typing a sentence?'",
            "comp_c2_special_represent": "format: fill_diagram. Match keys to functions. Example: 'Match: Enter -> ___. Caps Lock -> ___. (new line / all capitals)'",
            "comp_c2_special_error": "format: error_spot_science. Present a WRONG fact. Example: 'Pressing Caps Lock makes all letters small.' Ask: 'Find the mistake and correct it.'",
            "comp_c2_special_thinking": "format: thinking_science. Reasoning question. Example: 'What is the difference between Backspace and Delete? Explain in your own words.'",
        }
        return comp_special_ctx + comp_special_map.get(_skill_tag, "About special keys.")

    # ── Computer Science: MS Paint Basics (Class 3) ──
    if _skill_tag.startswith("comp_c3_paint_"):
        comp_paint_ctx = (
            "Topic: MS Paint Basics (Class 3 Computer, CBSE). "
            "Cover tools: pencil, brush, fill (colour bucket), eraser, text tool, "
            "shape tools (rectangle, circle, line), colour palette, save/open. "
            "Use Indian contexts: drawing Indian flag, rangoli, Diwali card. "
            "Keep vocabulary appropriate — Class 3 level. "
            "DO NOT repeat the same tool or scenario. "
        )
        comp_paint_map = {
            "comp_c3_paint_identify": "format: pick_correct_science. Identify Paint tools. Example: 'Which tool fills a closed shape with colour in MS Paint? (a) Pencil (b) Eraser (c) Fill with colour (d) Brush' -> Fill with colour",
            "comp_c3_paint_apply": "format: give_example. Ask about using tools. Example: 'Name two shapes you can draw using the Shapes tool in MS Paint.'",
            "comp_c3_paint_represent": "format: sequence_steps. Order drawing steps. Example: 'Put in order to draw and colour a circle: (a) Select the circle shape (b) Choose a colour (c) Draw the circle (d) Use fill tool to colour it'",
            "comp_c3_paint_error": "format: error_spot_science. Present a WRONG fact. Example: 'The eraser tool is used to add colour to a shape.' Ask: 'Find the mistake and correct it.'",
            "comp_c3_paint_thinking": "format: thinking_science. Reasoning question. Example: 'Why should you save your drawing before closing MS Paint? What could happen if you don't?'",
        }
        return comp_paint_ctx + comp_paint_map.get(_skill_tag, "About MS Paint basics.")

    # ── Computer Science: Keyboard Shortcuts (Class 3) ──
    if _skill_tag.startswith("comp_c3_shortcuts_"):
        comp_shortcuts_ctx = (
            "Topic: Keyboard Shortcuts (Class 3 Computer, CBSE). "
            "Cover shortcuts: Ctrl+C (copy), Ctrl+V (paste), Ctrl+X (cut), "
            "Ctrl+Z (undo), Ctrl+S (save), Ctrl+A (select all), Ctrl+P (print), "
            "Alt+Tab (switch windows), Ctrl+B (bold). "
            "Use Indian school contexts: school projects, IT class. "
            "Keep vocabulary appropriate — Class 3 level. "
            "DO NOT repeat the same shortcut. "
        )
        comp_shortcuts_map = {
            "comp_c3_shortcuts_identify": "format: pick_correct_science. Identify shortcuts. Example: 'Which keyboard shortcut is used to copy text? (a) Ctrl+V (b) Ctrl+C (c) Ctrl+Z (d) Ctrl+S' -> Ctrl+C",
            "comp_c3_shortcuts_apply": "format: explain_why_science. Explain usage. Example: 'Why is Ctrl+Z a useful shortcut? When would you use it?'",
            "comp_c3_shortcuts_represent": "format: fill_diagram. Match shortcuts to actions. Example: 'Match: Ctrl+C -> ___. Ctrl+V -> ___. (copy / paste)'",
            "comp_c3_shortcuts_error": "format: error_spot_science. Present a WRONG fact. Example: 'Ctrl+S is the shortcut to paste text.' Ask: 'Find the mistake and correct it.'",
            "comp_c3_shortcuts_thinking": "format: thinking_science. Reasoning question. Example: 'Why are keyboard shortcuts faster than using the mouse to do the same thing? Give an example.'",
        }
        return comp_shortcuts_ctx + comp_shortcuts_map.get(_skill_tag, "About keyboard shortcuts.")

    # ── Computer Science: Files and Folders (Class 3) ──
    if _skill_tag.startswith("comp_c3_files_"):
        comp_files_ctx = (
            "Topic: Files and Folders (Class 3 Computer, CBSE). "
            "Cover: creating folders, renaming files, deleting files, moving files, "
            "file extensions (.txt, .png, .docx), organising into subject folders. "
            "Use Indian school contexts: saving school projects, organising homework. "
            "Keep vocabulary appropriate — Class 3 level. "
            "DO NOT repeat the same file operation. "
        )
        comp_files_map = {
            "comp_c3_files_identify": "format: true_false. True/false about files. Example: 'True or False: A folder can contain other folders inside it.' -> True",
            "comp_c3_files_apply": "format: give_example. Ask about file management. Example: 'Name two types of files you can save on a computer (like documents and pictures).'",
            "comp_c3_files_represent": "format: sequence_steps. Order steps for file operations. Example: 'Put in order to create a new folder: (a) Right-click on desktop (b) Click New (c) Click Folder (d) Type the folder name'",
            "comp_c3_files_error": "format: error_spot_science. Present a WRONG fact. Example: 'To rename a file, you should delete it and create a new one.' Ask: 'Find the mistake and correct it.'",
            "comp_c3_files_thinking": "format: thinking_science. Reasoning question. Example: 'Why is it a good idea to organise your files into folders? What could happen if you don't?'",
        }
        return comp_files_ctx + comp_files_map.get(_skill_tag, "About files and folders.")

    # ── Computer Science: MS Word Basics (Class 4) ──
    if _skill_tag.startswith("comp_c4_word_"):
        comp_word_ctx = (
            "Topic: MS Word Basics (Class 4 Computer, CBSE). "
            "Cover: typing text, formatting (bold/italic/underline), font size, font colour, "
            "alignment (left/centre/right), save/open/print, inserting tables and page borders. "
            "Use Indian school contexts: writing essays, school projects, letters. "
            "Keep vocabulary appropriate — Class 4 level. "
            "DO NOT repeat the same formatting feature. "
        )
        comp_word_map = {
            "comp_c4_word_identify": "format: pick_correct_science. Identify Word features. Example: 'Which button do you click to make text bold in MS Word? (a) I (b) B (c) U (d) A' -> B",
            "comp_c4_word_apply": "format: explain_why_science. Explain usage. Example: 'Why would you change the font size of a heading in your essay? Give one reason.'",
            "comp_c4_word_represent": "format: sequence_steps. Order steps. Example: 'Put in order to save a document: (a) Click File (b) Click Save As (c) Type file name (d) Click Save'",
            "comp_c4_word_error": "format: error_spot_science. Present a WRONG fact. Example: 'To underline text in MS Word, press Ctrl+B.' Ask: 'Find the mistake and correct it.'",
            "comp_c4_word_thinking": "format: thinking_science. Reasoning question. Example: 'Why is it important to save your document regularly while working on it?'",
        }
        return comp_word_ctx + comp_word_map.get(_skill_tag, "About MS Word basics.")

    # ── Computer Science: Introduction to Scratch (Class 4) ──
    if _skill_tag.startswith("comp_c4_scratch_"):
        comp_scratch4_ctx = (
            "Topic: Introduction to Scratch (Class 4 Computer, CBSE). "
            "Cover: Scratch interface (stage, sprite, script area), motion blocks (move, turn, glide), "
            "looks blocks (say, think, change costume), events (green flag, when clicked), "
            "simple loops (repeat), basic animation. "
            "Use Indian contexts: making a sprite say Namaste, cricket game sprite. "
            "Keep vocabulary appropriate — Class 4 level. "
            "DO NOT repeat the same block type or scenario. "
        )
        comp_scratch4_map = {
            "comp_c4_scratch_identify": "format: pick_correct_science. Identify Scratch elements. Example: 'What is the character in Scratch called? (a) Actor (b) Sprite (c) Avatar (d) Player' -> Sprite",
            "comp_c4_scratch_apply": "format: give_example. Ask about Scratch usage. Example: 'Name two things a sprite can do using Motion blocks.'",
            "comp_c4_scratch_represent": "format: sequence_steps. Order steps to create animation. Example: 'Put in order: (a) Add a sprite (b) Drag motion blocks (c) Click green flag to run (d) Add a backdrop'",
            "comp_c4_scratch_error": "format: error_spot_science. Present a WRONG fact. Example: 'In Scratch, the Stage is where you write your code blocks.' Ask: 'Find the mistake and correct it.'",
            "comp_c4_scratch_thinking": "format: thinking_science. Reasoning question. Example: 'Why do we use a loop (repeat) block instead of writing the same command many times?'",
        }
        return comp_scratch4_ctx + comp_scratch4_map.get(_skill_tag, "About Introduction to Scratch.")

    # ── Computer Science: Internet Safety (Class 4) ──
    if _skill_tag.startswith("comp_c4_safety_"):
        comp_safety_ctx = (
            "Topic: Internet Safety (Class 4 Computer, CBSE). "
            "Cover: strong passwords, personal information (name, address, phone), "
            "safe browsing, not clicking unknown links, cyberbullying (recognising, reporting), "
            "talking to a trusted adult about online problems. "
            "Use Indian school contexts: school email accounts, kids' websites. "
            "Keep vocabulary appropriate — Class 4 level. "
            "DO NOT repeat the same safety rule. "
        )
        comp_safety_map = {
            "comp_c4_safety_identify": "format: true_false. True/false about internet safety. Example: 'True or False: You should share your password with your best friend.' -> False",
            "comp_c4_safety_apply": "format: explain_why_science. Explain safety rules. Example: 'Why should you never share your home address with someone you meet online?'",
            "comp_c4_safety_represent": "format: sequence_steps. Order safety steps. Example: 'Put in order if you see a mean message online: (a) Don't reply (b) Take a screenshot (c) Tell your teacher or parent (d) Block the person'",
            "comp_c4_safety_error": "format: error_spot_science. Present a WRONG fact. Example: 'A strong password should be your birthday so you can remember it easily.' Ask: 'Find the mistake and correct it.'",
            "comp_c4_safety_thinking": "format: thinking_science. Reasoning question. Example: 'Why is a password like \"abc123\" not a good password? What makes a password strong?'",
        }
        return comp_safety_ctx + comp_safety_map.get(_skill_tag, "About internet safety.")

    # ── Computer Science: Scratch Programming (Class 5) ──
    if _skill_tag.startswith("comp_c5_scratch_"):
        comp_scratch5_ctx = (
            "Topic: Scratch Programming (Class 5 Computer, CBSE). "
            "Cover: variables (score, lives), conditionals (if-then, if-then-else), "
            "loops (repeat, forever, repeat until), broadcasting (messages between sprites), "
            "events, cloning, game creation, debugging. "
            "Use Indian contexts: cricket score game, mango catching game. "
            "Keep vocabulary appropriate — Class 5 level. "
            "DO NOT repeat the same programming concept. "
        )
        comp_scratch5_map = {
            "comp_c5_scratch_identify": "format: pick_correct_science. Identify programming concepts. Example: 'Which block in Scratch is used to store a score? (a) Motion (b) Variable (c) Looks (d) Sound' -> Variable",
            "comp_c5_scratch_apply": "format: explain_why_science. Explain programming concepts. Example: 'Why do we use an if-then block in Scratch? Give an example of when you would use it.'",
            "comp_c5_scratch_represent": "format: sequence_steps. Order steps to build a game. Example: 'Put in order to make a catching game: (a) Create a falling object (b) Add score variable (c) Use if-touching to increase score (d) Add forever loop'",
            "comp_c5_scratch_error": "format: error_spot_science. Present a WRONG fact. Example: 'A forever loop in Scratch runs the code inside it exactly 10 times.' Ask: 'Find the mistake and correct it.'",
            "comp_c5_scratch_thinking": "format: thinking_science. Reasoning question. Example: 'How would you make a game more difficult as the player scores more points? Describe your idea.'",
        }
        return comp_scratch5_ctx + comp_scratch5_map.get(_skill_tag, "About Scratch programming.")

    # ── Computer Science: Internet Basics (Class 5) ──
    if _skill_tag.startswith("comp_c5_internet_"):
        comp_internet_ctx = (
            "Topic: Internet Basics (Class 5 Computer, CBSE). "
            "Cover: web browser (Chrome, Edge), URL/address bar, search engines (Google), "
            "email basics (compose, send, reply, attach), downloading files, bookmarks, tabs. "
            "Use Indian school contexts: searching for school projects, emailing teachers. "
            "Keep vocabulary appropriate — Class 5 level. "
            "DO NOT repeat the same internet concept. "
        )
        comp_internet_map = {
            "comp_c5_internet_identify": "format: pick_correct_science. Identify internet concepts. Example: 'What do you type in the address bar of a browser? (a) Password (b) Email (c) URL/web address (d) File name' -> URL/web address",
            "comp_c5_internet_apply": "format: give_example. Ask about internet usage. Example: 'Name two things you need to include when composing an email.'",
            "comp_c5_internet_represent": "format: sequence_steps. Order steps. Example: 'Put in order to send an email: (a) Type the message (b) Click Compose (c) Enter the email address (d) Click Send'",
            "comp_c5_internet_error": "format: error_spot_science. Present a WRONG fact. Example: 'A search engine is a program that saves your files on the computer.' Ask: 'Find the mistake and correct it.'",
            "comp_c5_internet_thinking": "format: thinking_science. Reasoning question. Example: 'Why should you check if a website is trustworthy before using information from it for a school project?'",
        }
        return comp_internet_ctx + comp_internet_map.get(_skill_tag, "About internet basics.")

    # ── Computer Science: MS PowerPoint Basics (Class 5) ──
    if _skill_tag.startswith("comp_c5_ppt_"):
        comp_ppt_ctx = (
            "Topic: MS PowerPoint Basics (Class 5 Computer, CBSE). "
            "Cover: creating slides, adding text and images, slide layouts, "
            "transitions (fade, wipe), basic animations, slideshow mode, presenting. "
            "Use Indian school contexts: school presentations, science fair projects. "
            "Keep vocabulary appropriate — Class 5 level. "
            "DO NOT repeat the same PowerPoint feature. "
        )
        comp_ppt_map = {
            "comp_c5_ppt_identify": "format: pick_correct_science. Identify PPT features. Example: 'What is a single page in a PowerPoint presentation called? (a) Document (b) Sheet (c) Slide (d) Frame' -> Slide",
            "comp_c5_ppt_apply": "format: explain_why_science. Explain usage. Example: 'Why do we add transitions between slides in a presentation?'",
            "comp_c5_ppt_represent": "format: sequence_steps. Order steps. Example: 'Put in order to create a presentation: (a) Open PowerPoint (b) Add a title slide (c) Add content slides (d) Add transitions (e) Start slideshow'",
            "comp_c5_ppt_error": "format: error_spot_science. Present a WRONG fact. Example: 'A transition in PowerPoint changes the font of the text on a slide.' Ask: 'Find the mistake and correct it.'",
            "comp_c5_ppt_thinking": "format: thinking_science. Reasoning question. Example: 'Why should you not put too much text on one slide? How does it affect your audience?'",
        }
        return comp_ppt_ctx + comp_ppt_map.get(_skill_tag, "About MS PowerPoint basics.")

    # ── Computer Science: Digital Citizenship (Class 5) ──
    if _skill_tag.startswith("comp_c5_digital_"):
        comp_digital_ctx = (
            "Topic: Digital Citizenship (Class 5 Computer, CBSE). "
            "Cover: online etiquette (respectful comments), digital footprint (what you post stays), "
            "copyright (not copying others' work), responsible use of technology, "
            "privacy settings, reporting inappropriate content. "
            "Use Indian school contexts: school projects, class WhatsApp groups. "
            "Keep vocabulary appropriate — Class 5 level. "
            "DO NOT repeat the same digital citizenship concept. "
        )
        comp_digital_map = {
            "comp_c5_digital_identify": "format: true_false. True/false about digital citizenship. Example: 'True or False: Everything you post online can be seen by others even after you delete it.' -> True",
            "comp_c5_digital_apply": "format: explain_why_science. Explain digital citizenship. Example: 'Why should you always ask permission before using someone else's photo or artwork for your project?'",
            "comp_c5_digital_represent": "format: sequence_steps. Order steps. Example: 'Put in order if you find copied content in a classmate's project: (a) Tell the classmate politely (b) Explain why copying is wrong (c) Help them find original sources (d) Inform the teacher if needed'",
            "comp_c5_digital_error": "format: error_spot_science. Present a WRONG fact. Example: 'It is okay to copy pictures from the internet for your school project without giving credit.' Ask: 'Find the mistake and correct it.'",
            "comp_c5_digital_thinking": "format: thinking_science. Reasoning question. Example: 'What does \"digital footprint\" mean? Why should you be careful about what you post online?'",
        }
        return comp_digital_ctx + comp_digital_map.get(_skill_tag, "About digital citizenship.")

    # ── General Knowledge: Famous Landmarks (Class 3) ──
    if _skill_tag.startswith("gk_c3_landmarks_"):
        gk_landmarks_ctx = (
            "Topic: Famous Landmarks (Class 3 GK, CBSE). "
            "Cover: Taj Mahal, Great Wall of China, Eiffel Tower, Qutub Minar, India Gate, Red Fort, "
            "Gateway of India, Hawa Mahal, Statue of Unity, and other famous monuments. "
            "Use Indian school contexts. Keep vocabulary appropriate — Class 3 level. "
            "DO NOT repeat the same landmark. "
        )
        gk_landmarks_map = {
            "gk_c3_landmarks_identify": "format: pick_correct_science. Multiple choice about landmarks. Example: 'Which monument is located in Agra? (a) Red Fort (b) Taj Mahal (c) Qutub Minar (d) India Gate' -> (b) Taj Mahal",
            "gk_c3_landmarks_apply": "format: explain_why_science. Explain about a landmark. Example: 'Why is the Taj Mahal considered one of the wonders of the world?'",
            "gk_c3_landmarks_represent": "format: sequence_steps. Match or order landmarks. Example: 'Match the following landmarks with their cities: (a) Taj Mahal — Delhi (b) Red Fort — Agra (c) Hawa Mahal — Jaipur. Write the correct pairs.'",
            "gk_c3_landmarks_error": "format: error_spot_science. Present a WRONG fact. Example: 'The Eiffel Tower is located in London.' Ask: 'Find the mistake and correct it.'",
            "gk_c3_landmarks_thinking": "format: thinking_science. Reasoning question. Example: 'Why do you think it is important to protect old monuments and landmarks?'",
        }
        return gk_landmarks_ctx + gk_landmarks_map.get(_skill_tag, "About famous landmarks.")

    # ── General Knowledge: National Symbols (Class 3) ──
    if _skill_tag.startswith("gk_c3_symbols_"):
        gk_symbols_ctx = (
            "Topic: National Symbols (Class 3 GK, CBSE). "
            "Cover: Indian flag (tiranga — saffron, white, green, Ashoka Chakra), national emblem, "
            "national anthem (Jana Gana Mana), national animal (Bengal tiger), national bird (peacock), "
            "national flower (lotus), national fruit (mango). "
            "Use Indian school contexts. Keep vocabulary appropriate — Class 3 level. "
            "DO NOT repeat the same symbol. "
        )
        gk_symbols_map = {
            "gk_c3_symbols_identify": "format: pick_correct_science. Multiple choice about national symbols. Example: 'What is the national bird of India? (a) Sparrow (b) Parrot (c) Peacock (d) Crow' -> (c) Peacock",
            "gk_c3_symbols_apply": "format: give_example. Give examples related to national symbols. Example: 'Name the three colours of the Indian flag from top to bottom.'",
            "gk_c3_symbols_represent": "format: fill_diagram. Fill in information. Example: 'Complete: The national anthem of India is _____ and it was written by _____.'",
            "gk_c3_symbols_error": "format: error_spot_science. Present a WRONG fact. Example: 'The national animal of India is the lion.' Ask: 'Find the mistake and correct it.'",
            "gk_c3_symbols_thinking": "format: thinking_science. Reasoning question. Example: 'Why do you think the peacock was chosen as the national bird of India?'",
        }
        return gk_symbols_ctx + gk_symbols_map.get(_skill_tag, "About national symbols.")

    # ── General Knowledge: Solar System Basics (Class 3) ──
    if _skill_tag.startswith("gk_c3_solar_"):
        gk_solar_ctx = (
            "Topic: Solar System Basics (Class 3 GK, CBSE). "
            "Cover: Sun as a star, 8 planets in order (Mercury, Venus, Earth, Mars, Jupiter, Saturn, Uranus, Neptune), "
            "Moon, day and night, stars vs planets, satellites. "
            "Use Indian school contexts. Keep vocabulary appropriate — Class 3 level. "
            "DO NOT repeat the same planet or concept. "
        )
        gk_solar_map = {
            "gk_c3_solar_identify": "format: pick_correct_science. Multiple choice about the solar system. Example: 'Which planet is closest to the Sun? (a) Earth (b) Mars (c) Mercury (d) Venus' -> (c) Mercury",
            "gk_c3_solar_apply": "format: explain_why_science. Explain a solar system concept. Example: 'Why do we have day and night on Earth?'",
            "gk_c3_solar_represent": "format: sequence_steps. Order planets. Example: 'Arrange the planets in order from the Sun: Earth, Mercury, Venus, Mars.'",
            "gk_c3_solar_error": "format: error_spot_science. Present a WRONG fact. Example: 'The Sun is a planet that gives us light and heat.' Ask: 'Find the mistake and correct it.'",
            "gk_c3_solar_thinking": "format: thinking_science. Reasoning question. Example: 'Why do you think life exists on Earth but not on other planets in our solar system?'",
        }
        return gk_solar_ctx + gk_solar_map.get(_skill_tag, "About the solar system.")

    # ── General Knowledge: Current Awareness (Class 3) ──
    if _skill_tag.startswith("gk_c3_current_"):
        gk_current_ctx = (
            "Topic: Current Awareness (Class 3 GK, CBSE). "
            "Cover: Indian festivals (Diwali, Holi, Eid, Christmas, Pongal), seasons of India, "
            "important days (Republic Day 26 Jan, Independence Day 15 Aug, Children's Day 14 Nov, Teachers' Day 5 Sep). "
            "Use Indian school contexts. Keep vocabulary appropriate — Class 3 level. "
            "DO NOT repeat the same festival or day. "
        )
        gk_current_map = {
            "gk_c3_current_identify": "format: true_false. True/false about festivals or important days. Example: 'True or False: Republic Day is celebrated on 26th January.' -> True",
            "gk_c3_current_apply": "format: give_example. Give examples. Example: 'Name two festivals celebrated in the month of October or November in India.'",
            "gk_c3_current_represent": "format: fill_diagram. Fill in information. Example: 'Complete: Independence Day is celebrated on _____ August every year to remember India's freedom from _____.'",
            "gk_c3_current_error": "format: error_spot_science. Present a WRONG fact. Example: 'Children's Day is celebrated on 5th September in India.' Ask: 'Find the mistake and correct it.'",
            "gk_c3_current_thinking": "format: thinking_science. Reasoning question. Example: 'Why do you think we celebrate Republic Day and Independence Day as national holidays?'",
        }
        return gk_current_ctx + gk_current_map.get(_skill_tag, "About current awareness.")

    # ── General Knowledge: Continents and Oceans (Class 4) ──
    if _skill_tag.startswith("gk_c4_continents_"):
        gk_continents_ctx = (
            "Topic: Continents and Oceans (Class 4 GK, CBSE). "
            "Cover: 7 continents (Asia, Africa, North America, South America, Antarctica, Europe, Australia/Oceania), "
            "5 oceans (Pacific, Atlantic, Indian, Southern, Arctic), major countries. "
            "Use Indian school contexts. Keep vocabulary appropriate — Class 4 level. "
            "DO NOT repeat the same continent or ocean. "
        )
        gk_continents_map = {
            "gk_c4_continents_identify": "format: pick_correct_science. Multiple choice about continents/oceans. Example: 'Which is the largest continent? (a) Africa (b) Asia (c) Europe (d) Australia' -> (b) Asia",
            "gk_c4_continents_apply": "format: explain_why_science. Explain a geography fact. Example: 'Why is Antarctica the coldest continent on Earth?'",
            "gk_c4_continents_represent": "format: fill_diagram. Fill in information. Example: 'Complete: India is located in the continent of _____ and is surrounded by the _____ Ocean.'",
            "gk_c4_continents_error": "format: error_spot_science. Present a WRONG fact. Example: 'The Atlantic Ocean is the largest ocean in the world.' Ask: 'Find the mistake and correct it.'",
            "gk_c4_continents_thinking": "format: thinking_science. Reasoning question. Example: 'Why do you think Asia is the most populated continent in the world?'",
        }
        return gk_continents_ctx + gk_continents_map.get(_skill_tag, "About continents and oceans.")

    # ── General Knowledge: Famous Scientists (Class 4) ──
    if _skill_tag.startswith("gk_c4_scientists_"):
        gk_scientists_ctx = (
            "Topic: Famous Scientists (Class 4 GK, CBSE). "
            "Cover: Newton (gravity), Edison (light bulb), APJ Abdul Kalam (missiles/President), "
            "C.V. Raman (Nobel Prize), Marie Curie (radioactivity), Homi Bhabha, Vikram Sarabhai, Ramanujan. "
            "Use Indian school contexts. Keep vocabulary appropriate — Class 4 level. "
            "DO NOT repeat the same scientist. "
        )
        gk_scientists_map = {
            "gk_c4_scientists_identify": "format: pick_correct_science. Multiple choice about scientists. Example: 'Who is known as the Missile Man of India? (a) C.V. Raman (b) Homi Bhabha (c) APJ Abdul Kalam (d) Vikram Sarabhai' -> (c) APJ Abdul Kalam",
            "gk_c4_scientists_apply": "format: give_example. Give examples. Example: 'Name the scientist who discovered gravity and describe how the discovery was made.'",
            "gk_c4_scientists_represent": "format: cause_effect. Match scientists with discoveries. Example: 'Match: (a) Newton — Light bulb (b) Edison — Gravity (c) C.V. Raman — Raman Effect. Write the correct pairs.'",
            "gk_c4_scientists_error": "format: error_spot_science. Present a WRONG fact. Example: 'Thomas Edison is famous for discovering gravity when an apple fell on his head.' Ask: 'Find the mistake and correct it.'",
            "gk_c4_scientists_thinking": "format: thinking_science. Reasoning question. Example: 'Why do you think scientists are important for the progress of a country?'",
        }
        return gk_scientists_ctx + gk_scientists_map.get(_skill_tag, "About famous scientists.")

    # ── General Knowledge: Festivals of India (Class 4) ──
    if _skill_tag.startswith("gk_c4_festivals_"):
        gk_festivals_ctx = (
            "Topic: Festivals of India (Class 4 GK, CBSE). "
            "Cover: Diwali, Holi, Eid-ul-Fitr, Christmas, Pongal, Baisakhi, Onam, Navratri, "
            "Durga Puja, Guru Nanak Jayanti, and other regional festivals. "
            "Use Indian school contexts. Keep vocabulary appropriate — Class 4 level. "
            "DO NOT repeat the same festival. "
        )
        gk_festivals_map = {
            "gk_c4_festivals_identify": "format: true_false. True/false about festivals. Example: 'True or False: Pongal is a harvest festival celebrated mainly in Tamil Nadu.' -> True",
            "gk_c4_festivals_apply": "format: give_example. Give examples. Example: 'Name the festival known as the \"festival of lights\" and describe how it is celebrated.'",
            "gk_c4_festivals_represent": "format: fill_diagram. Fill in information. Example: 'Complete: Baisakhi is celebrated in the state of _____ to mark the _____.'",
            "gk_c4_festivals_error": "format: error_spot_science. Present a WRONG fact. Example: 'Onam is a festival celebrated in Gujarat with boat races.' Ask: 'Find the mistake and correct it.'",
            "gk_c4_festivals_thinking": "format: thinking_science. Reasoning question. Example: 'Why do you think India celebrates so many different festivals from different religions?'",
        }
        return gk_festivals_ctx + gk_festivals_map.get(_skill_tag, "About festivals of India.")

    # ── General Knowledge: Sports and Games (Class 4) ──
    if _skill_tag.startswith("gk_c4_sports_"):
        gk_sports_ctx = (
            "Topic: Sports and Games (Class 4 GK, CBSE). "
            "Cover: cricket, hockey (national game), football, Olympics, Sachin Tendulkar, PV Sindhu, "
            "Neeraj Chopra, Mary Kom, kabaddi, and other sports facts. "
            "Use Indian school contexts. Keep vocabulary appropriate — Class 4 level. "
            "DO NOT repeat the same sport or sportsperson. "
        )
        gk_sports_map = {
            "gk_c4_sports_identify": "format: pick_correct_science. Multiple choice about sports. Example: 'Which sport did Neeraj Chopra win a gold medal in at the Olympics? (a) Cricket (b) Javelin throw (c) Boxing (d) Badminton' -> (b) Javelin throw",
            "gk_c4_sports_apply": "format: explain_why_science. Explain a sports fact. Example: 'Why is hockey considered the national game of India? Name one famous Indian hockey player.'",
            "gk_c4_sports_represent": "format: cause_effect. Match sportspersons with sports. Example: 'Match: (a) Sachin Tendulkar — Boxing (b) Mary Kom — Cricket (c) PV Sindhu — Badminton. Write the correct pairs.'",
            "gk_c4_sports_error": "format: error_spot_science. Present a WRONG fact. Example: 'Sachin Tendulkar is famous for his achievements in football.' Ask: 'Find the mistake and correct it.'",
            "gk_c4_sports_thinking": "format: thinking_science. Reasoning question. Example: 'Why do you think playing sports is important for children? Give two reasons.'",
        }
        return gk_sports_ctx + gk_sports_map.get(_skill_tag, "About sports and games.")

    # ── General Knowledge: Indian Constitution (Class 5) ──
    if _skill_tag.startswith("gk_c5_constitution_"):
        gk_constitution_ctx = (
            "Topic: Indian Constitution (Class 5 GK, CBSE). "
            "Cover: fundamental rights (right to equality, right to education), fundamental duties, "
            "the Preamble, Dr B.R. Ambedkar (father of the Constitution), republic, Parliament, President. "
            "Use Indian school contexts. Keep vocabulary appropriate — Class 5 level. "
            "DO NOT repeat the same constitutional concept. "
        )
        gk_constitution_map = {
            "gk_c5_constitution_identify": "format: true_false. True/false about the Constitution. Example: 'True or False: Dr B.R. Ambedkar is known as the Father of the Indian Constitution.' -> True",
            "gk_c5_constitution_apply": "format: explain_why_science. Explain a constitutional concept. Example: 'What does the Right to Education mean? Why is it important for all children?'",
            "gk_c5_constitution_represent": "format: cause_effect. Connect concepts. Example: 'Match the following fundamental rights with their meanings: (a) Right to Equality (b) Right to Freedom (c) Right to Education.'",
            "gk_c5_constitution_error": "format: error_spot_science. Present a WRONG fact. Example: 'The Indian Constitution was written by Mahatma Gandhi in 1947.' Ask: 'Find the mistake and correct it.'",
            "gk_c5_constitution_thinking": "format: thinking_science. Reasoning question. Example: 'Why do you think having a Constitution is important for a country like India?'",
        }
        return gk_constitution_ctx + gk_constitution_map.get(_skill_tag, "About the Indian Constitution.")

    # ── General Knowledge: World Heritage Sites (Class 5) ──
    if _skill_tag.startswith("gk_c5_heritage_"):
        gk_heritage_ctx = (
            "Topic: World Heritage Sites (Class 5 GK, CBSE). "
            "Cover: UNESCO sites in India (Ajanta-Ellora caves, Sun Temple Konark, Hampi, Kaziranga, Sundarbans), "
            "global sites (Machu Picchu, Great Barrier Reef, Pyramids of Giza). "
            "Use Indian school contexts. Keep vocabulary appropriate — Class 5 level. "
            "DO NOT repeat the same heritage site. "
        )
        gk_heritage_map = {
            "gk_c5_heritage_identify": "format: pick_correct_science. Multiple choice about heritage sites. Example: 'Which of these is a UNESCO World Heritage Site in India? (a) Taj Mahal (b) Eiffel Tower (c) Statue of Liberty (d) Big Ben' -> (a) Taj Mahal",
            "gk_c5_heritage_apply": "format: give_example. Give examples. Example: 'Name two UNESCO World Heritage Sites in India and explain why they are important.'",
            "gk_c5_heritage_represent": "format: fill_diagram. Fill in information. Example: 'Complete: The Ajanta and Ellora caves are located in the state of _____ and are famous for their _____.'",
            "gk_c5_heritage_error": "format: error_spot_science. Present a WRONG fact. Example: 'The Sun Temple at Konark is located in Rajasthan.' Ask: 'Find the mistake and correct it.'",
            "gk_c5_heritage_thinking": "format: thinking_science. Reasoning question. Example: 'Why is it important to protect World Heritage Sites? What can students do to help?'",
        }
        return gk_heritage_ctx + gk_heritage_map.get(_skill_tag, "About world heritage sites.")

    # ── General Knowledge: Space Missions (Class 5) ──
    if _skill_tag.startswith("gk_c5_space_"):
        gk_space_ctx = (
            "Topic: Space Missions (Class 5 GK, CBSE). "
            "Cover: ISRO (Indian Space Research Organisation), Chandrayaan (Moon mission), "
            "Mangalyaan (Mars mission), NASA, satellites, Rakesh Sharma (first Indian in space), "
            "International Space Station. "
            "Use Indian school contexts. Keep vocabulary appropriate — Class 5 level. "
            "DO NOT repeat the same space mission or concept. "
        )
        gk_space_map = {
            "gk_c5_space_identify": "format: pick_correct_science. Multiple choice about space. Example: 'Which organisation launched Chandrayaan-3? (a) NASA (b) ISRO (c) ESA (d) JAXA' -> (b) ISRO",
            "gk_c5_space_apply": "format: explain_why_science. Explain a space concept. Example: 'What was the purpose of India's Mangalyaan mission? Why was it considered a great achievement?'",
            "gk_c5_space_represent": "format: sequence_steps. Order events. Example: 'Arrange India's space achievements in order: (a) Mangalyaan (b) Chandrayaan-1 (c) Aryabhata satellite (d) Chandrayaan-3.'",
            "gk_c5_space_error": "format: error_spot_science. Present a WRONG fact. Example: 'Rakesh Sharma was the first Indian to walk on the Moon.' Ask: 'Find the mistake and correct it.'",
            "gk_c5_space_thinking": "format: thinking_science. Reasoning question. Example: 'Why do you think space exploration is important for India and the world?'",
        }
        return gk_space_ctx + gk_space_map.get(_skill_tag, "About space missions.")

    # ── General Knowledge: Environmental Awareness (Class 5) ──
    if _skill_tag.startswith("gk_c5_environment_"):
        gk_env_ctx = (
            "Topic: Environmental Awareness (Class 5 GK, CBSE). "
            "Cover: air/water/soil pollution, conservation, recycling, climate change, global warming, "
            "renewable energy (solar, wind), deforestation, waste management. "
            "Use Indian school contexts. Keep vocabulary appropriate — Class 5 level. "
            "DO NOT repeat the same environmental concept. "
        )
        gk_env_map = {
            "gk_c5_environment_identify": "format: true_false. True/false about the environment. Example: 'True or False: Burning fossil fuels is one of the main causes of air pollution.' -> True",
            "gk_c5_environment_apply": "format: explain_why_science. Explain an environmental concept. Example: 'Why is it important to recycle paper and plastic? How does it help the environment?'",
            "gk_c5_environment_represent": "format: cause_effect. Connect causes and effects. Example: 'Match the cause with its effect: (a) Cutting trees — Water pollution (b) Factory waste in rivers — Flooding (c) Burning plastic — Air pollution. Write the correct pairs.'",
            "gk_c5_environment_error": "format: error_spot_science. Present a WRONG fact. Example: 'Solar energy is a non-renewable source of energy.' Ask: 'Find the mistake and correct it.'",
            "gk_c5_environment_thinking": "format: thinking_science. Reasoning question. Example: 'What are three things you can do at home and school to help protect the environment?'",
        }
        return gk_env_ctx + gk_env_map.get(_skill_tag, "About environmental awareness.")

    # ── Moral Science: Sharing (Class 1) ──
    if _skill_tag.startswith("moral_c1_sharing_"):
        moral_sharing_ctx = (
            "Topic: Sharing (Class 1 Moral Science, CBSE). "
            "Cover: sharing toys, food, books with friends and family; being generous; "
            "how sharing makes others happy; taking turns. "
            "Use very simple language — Class 1 level (age 6). Use Indian names and contexts. "
            "DO NOT repeat the same sharing scenario. "
        )
        moral_sharing_map = {
            "moral_c1_sharing_identify": "format: pick_correct_science. Multiple choice about sharing. Example: 'Riya has 4 chocolates. She gives 2 to her friend. What is Riya doing? (a) Fighting (b) Sharing (c) Hiding (d) Running' -> (b) Sharing",
            "moral_c1_sharing_apply": "format: give_example. Give an example. Example: 'Give one example of how you can share something with your friend at school.'",
            "moral_c1_sharing_represent": "format: sequence_steps. Order actions. Example: 'Put in order: (a) Aman sees his friend has no pencil (b) Aman gives his extra pencil (c) His friend says thank you (d) They both smile.'",
            "moral_c1_sharing_error": "format: error_spot_science. Present a WRONG behaviour. Example: 'Sneha had many toys but she never let anyone play with them. She said \"These are all mine!\" Is this good behaviour? What should she do instead?'",
            "moral_c1_sharing_thinking": "format: thinking_science. Reasoning question. Example: 'Why do you think sharing makes you and your friends feel happy?'",
        }
        return moral_sharing_ctx + moral_sharing_map.get(_skill_tag, "About sharing.")

    # ── Moral Science: Honesty (Class 1) ──
    if _skill_tag.startswith("moral_c1_honesty_"):
        moral_honesty_ctx = (
            "Topic: Honesty (Class 1 Moral Science, CBSE). "
            "Cover: telling the truth, being fair, returning things that belong to others, "
            "admitting mistakes, not cheating. "
            "Use very simple language — Class 1 level (age 6). Use Indian names and contexts. "
            "DO NOT repeat the same honesty scenario. "
        )
        moral_honesty_map = {
            "moral_c1_honesty_identify": "format: true_false. True/false about honesty. Example: 'True or False: It is always better to tell the truth even if it is hard.' -> True",
            "moral_c1_honesty_apply": "format: give_example. Give an example. Example: 'Give one example of being honest at school.'",
            "moral_c1_honesty_represent": "format: sequence_steps. Order actions. Example: 'Put in order: (a) Aman accidentally breaks a toy (b) He feels scared (c) He tells his mother the truth (d) His mother is proud of him.'",
            "moral_c1_honesty_error": "format: error_spot_science. Present a WRONG behaviour. Example: 'Kiran found a pencil box on the ground. He put it in his bag and did not tell anyone. Is this right? What should he do?'",
            "moral_c1_honesty_thinking": "format: thinking_science. Reasoning question. Example: 'Why is it important to always tell the truth?'",
        }
        return moral_honesty_ctx + moral_honesty_map.get(_skill_tag, "About honesty.")

    # ── Moral Science: Kindness (Class 2) ──
    if _skill_tag.startswith("moral_c2_kindness_"):
        moral_kindness_ctx = (
            "Topic: Kindness (Class 2 Moral Science, CBSE). "
            "Cover: being kind to people and animals, helping others, saying kind words, "
            "making others feel better, small acts of kindness. "
            "Use Indian names and school contexts. Keep vocabulary appropriate — Class 2 level. "
            "DO NOT repeat the same kindness scenario. "
        )
        moral_kindness_map = {
            "moral_c2_kindness_identify": "format: pick_correct_science. Multiple choice about kindness. Example: 'Which of these is an act of kindness? (a) Pushing someone (b) Helping a friend carry books (c) Laughing at someone (d) Ignoring a new student' -> (b) Helping a friend carry books",
            "moral_c2_kindness_apply": "format: give_example. Give an example. Example: 'Give two examples of how you can be kind to animals.'",
            "moral_c2_kindness_represent": "format: sequence_steps. Order kind actions. Example: 'Put in order: (a) Riya sees a classmate crying (b) She asks what happened (c) She comforts her friend (d) They go to the teacher together.'",
            "moral_c2_kindness_error": "format: error_spot_science. Present unkind behaviour. Example: 'A new student joined the class. Nobody talked to him all day. Everyone ignored him. Is this kind behaviour? What should the children do?'",
            "moral_c2_kindness_thinking": "format: thinking_science. Reasoning question. Example: 'How does being kind to others help make your school a better place?'",
        }
        return moral_kindness_ctx + moral_kindness_map.get(_skill_tag, "About kindness.")

    # ── Moral Science: Respecting Elders (Class 2) ──
    if _skill_tag.startswith("moral_c2_respect_"):
        moral_respect_ctx = (
            "Topic: Respecting Elders (Class 2 Moral Science, CBSE). "
            "Cover: good manners, greeting elders, listening when elders speak, "
            "saying please and thank you, following instructions. "
            "Use Indian names and school contexts. Keep vocabulary appropriate — Class 2 level. "
            "DO NOT repeat the same respect scenario. "
        )
        moral_respect_map = {
            "moral_c2_respect_identify": "format: true_false. True/false about respect. Example: 'True or False: We should stand up when our teacher enters the classroom.' -> True",
            "moral_c2_respect_apply": "format: give_example. Give an example. Example: 'Give two ways you can show respect to your grandparents.'",
            "moral_c2_respect_represent": "format: sequence_steps. Order respectful actions. Example: 'Put in order: (a) The teacher enters the class (b) Students stand up and say 'Good morning' (c) The teacher smiles and asks them to sit (d) The lesson begins.'",
            "moral_c2_respect_error": "format: error_spot_science. Present disrespectful behaviour. Example: 'Aman was talking loudly while his grandmother was telling a story. He did not listen at all. Is this respectful? What should he do?'",
            "moral_c2_respect_thinking": "format: thinking_science. Reasoning question. Example: 'Why is it important to listen carefully when elders are speaking?'",
        }
        return moral_respect_ctx + moral_respect_map.get(_skill_tag, "About respecting elders.")

    # ── Moral Science: Teamwork (Class 3) ──
    if _skill_tag.startswith("moral_c3_teamwork_"):
        moral_teamwork_ctx = (
            "Topic: Teamwork (Class 3 Moral Science, CBSE). "
            "Cover: working together, cooperation, different roles in a team, "
            "supporting team members, group activities, sharing responsibilities. "
            "Use Indian names and school contexts. Keep vocabulary appropriate — Class 3 level. "
            "DO NOT repeat the same teamwork scenario. "
        )
        moral_teamwork_map = {
            "moral_c3_teamwork_identify": "format: pick_correct_science. Multiple choice about teamwork. Example: 'Which of these is a good example of teamwork? (a) Doing everything alone (b) Working together to clean the class (c) Not helping others (d) Arguing with teammates' -> (b) Working together to clean the class",
            "moral_c3_teamwork_apply": "format: explain_why_science. Explain about teamwork. Example: 'Why is it important for everyone in a team to do their part? Give an example from school.'",
            "moral_c3_teamwork_represent": "format: sequence_steps. Order steps. Example: 'Put in order for a group project: (a) Divide tasks among members (b) Decide the topic together (c) Each person does their part (d) Combine and present the project.'",
            "moral_c3_teamwork_error": "format: error_spot_science. Present poor teamwork. Example: 'In a group project, Sneha did all the work herself and did not let others help. She said she could do it better alone. Is this good teamwork? Why or why not?'",
            "moral_c3_teamwork_thinking": "format: thinking_science. Reasoning question. Example: 'How is a cricket team an example of good teamwork? What happens if one person does not cooperate?'",
        }
        return moral_teamwork_ctx + moral_teamwork_map.get(_skill_tag, "About teamwork.")

    # ── Moral Science: Empathy (Class 3) ──
    if _skill_tag.startswith("moral_c3_empathy_"):
        moral_empathy_ctx = (
            "Topic: Empathy (Class 3 Moral Science, CBSE). "
            "Cover: understanding others' feelings, being supportive, putting yourself in someone else's shoes, "
            "caring for others, noticing when someone is sad or left out. "
            "Use Indian names and school contexts. Keep vocabulary appropriate — Class 3 level. "
            "DO NOT repeat the same empathy scenario. "
        )
        moral_empathy_map = {
            "moral_c3_empathy_identify": "format: true_false. True/false about empathy. Example: 'True or False: Empathy means understanding how another person feels.' -> True",
            "moral_c3_empathy_apply": "format: give_example. Give an example. Example: 'Your friend is crying because she lost her favourite book. How would you show empathy?'",
            "moral_c3_empathy_represent": "format: cause_effect. Connect situations and feelings. Example: 'Match the situation with how the person might feel: (a) A new student with no friends — Happy (b) A child who won a prize — Lonely (c) A boy who lost his pet — Sad. Write the correct pairs.'",
            "moral_c3_empathy_error": "format: error_spot_science. Present a lack of empathy. Example: 'Kiran saw his classmate sitting alone at lunch, looking sad. He walked past without saying anything. Is this showing empathy? What should he have done?'",
            "moral_c3_empathy_thinking": "format: thinking_science. Reasoning question. Example: 'Why is it important to try to understand how others feel, even if you have not experienced the same thing?'",
        }
        return moral_empathy_ctx + moral_empathy_map.get(_skill_tag, "About empathy.")

    # ── Moral Science: Environmental Care (Class 3) ──
    if _skill_tag.startswith("moral_c3_envcare_"):
        moral_envcare_ctx = (
            "Topic: Environmental Care (Class 3 Moral Science, CBSE). "
            "Cover: protecting nature, reduce-reuse-recycle, saving water and electricity, "
            "planting trees, not littering, keeping surroundings clean. "
            "Use Indian names and school contexts. Keep vocabulary appropriate — Class 3 level. "
            "DO NOT repeat the same environmental care scenario. "
        )
        moral_envcare_map = {
            "moral_c3_envcare_identify": "format: pick_correct_science. Multiple choice about environmental care. Example: 'Which of these helps the environment? (a) Throwing wrappers on the road (b) Using a cloth bag instead of plastic (c) Wasting water (d) Burning leaves' -> (b) Using a cloth bag instead of plastic",
            "moral_c3_envcare_apply": "format: explain_why_science. Explain environmental care. Example: 'Why should we plant more trees? Give two reasons.'",
            "moral_c3_envcare_represent": "format: cause_effect. Connect actions and results. Example: 'Match: (a) Turning off lights — Saves paper (b) Using both sides of paper — Saves electricity (c) Closing the tap — Saves water. Write the correct pairs.'",
            "moral_c3_envcare_error": "format: error_spot_science. Present harmful behaviour. Example: 'Aman threw his empty chips packet out of the car window. He said it was just one small packet. Is this right? What should he do?'",
            "moral_c3_envcare_thinking": "format: thinking_science. Reasoning question. Example: 'What are three things you can do every day to take care of the environment?'",
        }
        return moral_envcare_ctx + moral_envcare_map.get(_skill_tag, "About environmental care.")

    # ── Moral Science: Leadership (Class 4) ──
    if _skill_tag.startswith("moral_c4_leadership_"):
        moral_leadership_ctx = (
            "Topic: Leadership (Class 4 Moral Science, CBSE). "
            "Cover: qualities of good leaders (honesty, responsibility, fairness), "
            "decision-making, inspiring others, taking responsibility, being helpful. "
            "Use Indian names and school contexts. Keep vocabulary appropriate — Class 4 level. "
            "DO NOT repeat the same leadership scenario. "
        )
        moral_leadership_map = {
            "moral_c4_leadership_identify": "format: pick_correct_science. Multiple choice about leadership. Example: 'Which of these is a quality of a good leader? (a) Always bossing others (b) Listening to everyone's ideas (c) Doing only what they want (d) Blaming others for mistakes' -> (b) Listening to everyone's ideas",
            "moral_c4_leadership_apply": "format: explain_why_science. Explain about leadership. Example: 'Why is it important for a class monitor to be fair to everyone?'",
            "moral_c4_leadership_represent": "format: sequence_steps. Order steps. Example: 'Put in order for solving a problem as a leader: (a) Listen to everyone's ideas (b) Understand the problem (c) Choose the best solution (d) Take action and check results.'",
            "moral_c4_leadership_error": "format: error_spot_science. Present poor leadership. Example: 'The class monitor always chose only his friends for every activity and ignored other students. Is this good leadership? What should he do differently?'",
            "moral_c4_leadership_thinking": "format: thinking_science. Reasoning question. Example: 'Think of a leader you admire (from history or your life). What qualities make them a good leader?'",
        }
        return moral_leadership_ctx + moral_leadership_map.get(_skill_tag, "About leadership.")

    # ── Moral Science: Global Citizenship (Class 5) ──
    if _skill_tag.startswith("moral_c5_global_"):
        moral_global_ctx = (
            "Topic: Global Citizenship (Class 5 Moral Science, CBSE). "
            "Cover: cultural diversity, world peace, human rights basics, respecting all cultures, "
            "global cooperation, United Nations, equality and fairness for all. "
            "Use Indian school contexts. Keep vocabulary appropriate — Class 5 level. "
            "DO NOT repeat the same global citizenship concept. "
        )
        moral_global_map = {
            "moral_c5_global_identify": "format: true_false. True/false about global citizenship. Example: 'True or False: Every child in the world has the right to education, food, and shelter.' -> True",
            "moral_c5_global_apply": "format: explain_why_science. Explain a global citizenship concept. Example: 'Why is it important to respect people from different cultures and religions?'",
            "moral_c5_global_represent": "format: cause_effect. Connect concepts. Example: 'Match: (a) Cultural diversity — Helping people in need (b) Human rights — Many cultures living together (c) Charity — Rights that every person has. Write the correct pairs.'",
            "moral_c5_global_error": "format: error_spot_science. Present incorrect thinking. Example: 'Only people who speak the same language as us deserve our respect and friendship. Is this correct? What is wrong with this thinking?'",
            "moral_c5_global_thinking": "format: thinking_science. Reasoning question. Example: 'How can you be a good global citizen even as a student? Give two examples.'",
        }
        return moral_global_ctx + moral_global_map.get(_skill_tag, "About global citizenship.")

    # ── Moral Science: Digital Ethics (Class 5) ──
    if _skill_tag.startswith("moral_c5_digital_"):
        moral_digital_ctx = (
            "Topic: Digital Ethics (Class 5 Moral Science, CBSE). "
            "Cover: responsible online behaviour, privacy (not sharing personal info), "
            "digital footprint, cyberbullying, safe internet use, screen time limits, copyright. "
            "Use Indian school contexts. Keep vocabulary appropriate — Class 5 level. "
            "DO NOT repeat the same digital ethics concept. "
        )
        moral_digital_map = {
            "moral_c5_digital_identify": "format: true_false. True/false about digital ethics. Example: 'True or False: You should never share your password with anyone, even your best friend.' -> True",
            "moral_c5_digital_apply": "format: explain_why_science. Explain a digital ethics concept. Example: 'Why should you not copy homework or images from the internet and pretend they are yours?'",
            "moral_c5_digital_represent": "format: sequence_steps. Order steps. Example: 'Put in order if someone is bullying you online: (a) Do not reply to the bully (b) Tell a trusted adult (c) Block the person (d) Save the messages as proof.'",
            "moral_c5_digital_error": "format: error_spot_science. Present wrong digital behaviour. Example: 'Riya shared her home address and phone number on a public website to win a contest. Is this safe? What should she do instead?'",
            "moral_c5_digital_thinking": "format: thinking_science. Reasoning question. Example: 'What does \"digital footprint\" mean? Why should you be careful about what you post online?'",
        }
        return moral_digital_ctx + moral_digital_map.get(_skill_tag, "About digital ethics.")

    # ── Health & PE: Personal Hygiene (Class 1) ──
    if _skill_tag.startswith("health_c1_hygiene_"):
        health_hygiene_ctx = (
            "Topic: Personal Hygiene (Class 1 Health & PE, CBSE). "
            "Cover: handwashing, brushing teeth, bathing, wearing clean clothes, trimming nails. "
            "Use very simple language — Class 1 level (age 6). Use Indian names and contexts. "
            "DO NOT repeat the same hygiene scenario. "
        )
        health_hygiene_map = {
            "health_c1_hygiene_identify": "format: pick_correct_science. Multiple choice about hygiene. Example: 'When should you wash your hands? (a) Only at night (b) Before eating food (c) Never (d) Only on Sundays' -> (b) Before eating food",
            "health_c1_hygiene_apply": "format: explain_why_science. Explain a hygiene habit. Example: 'Why should you brush your teeth every morning and night?'",
            "health_c1_hygiene_represent": "format: sequence_steps. Order steps. Example: 'Put in order for washing hands: (a) Dry with a clean towel (b) Wet your hands with water (c) Rub soap on your hands for 20 seconds (d) Rinse off the soap.'",
            "health_c1_hygiene_error": "format: error_spot_science. Present bad hygiene. Example: 'Aman never washes his hands before eating. He says germs cannot hurt him. Is this correct? What should he do?'",
            "health_c1_hygiene_thinking": "format: thinking_science. Reasoning question. Example: 'Why do you think washing hands with soap is better than washing with just water?'",
        }
        return health_hygiene_ctx + health_hygiene_map.get(_skill_tag, "About personal hygiene.")

    # ── Health & PE: Good Posture (Class 1) ──
    if _skill_tag.startswith("health_c1_posture_"):
        health_posture_ctx = (
            "Topic: Good Posture (Class 1 Health & PE, CBSE). "
            "Cover: sitting straight, standing tall, carrying school bags on both shoulders, "
            "not slouching while reading or writing. "
            "Use very simple language — Class 1 level (age 6). Use Indian names and contexts. "
            "DO NOT repeat the same posture scenario. "
        )
        health_posture_map = {
            "health_c1_posture_identify": "format: true_false. True/false about posture. Example: 'True or False: You should carry your school bag on both shoulders, not just one.' -> True",
            "health_c1_posture_apply": "format: give_example. Give an example. Example: 'Give one example of good posture when you are sitting in class.'",
            "health_c1_posture_represent": "format: sequence_steps. Order steps. Example: 'Put in order for sitting correctly: (a) Keep your feet flat on the floor (b) Sit on the chair (c) Keep your back straight (d) Place your hands on the desk.'",
            "health_c1_posture_error": "format: error_spot_science. Present bad posture. Example: 'Riya always leans to one side while writing and carries her bag on one shoulder. Is this good for her body? What should she do?'",
            "health_c1_posture_thinking": "format: thinking_science. Reasoning question. Example: 'Why do you think sitting straight while studying is important for your body?'",
        }
        return health_posture_ctx + health_posture_map.get(_skill_tag, "About good posture.")

    # ── Health & PE: Basic Physical Activities (Class 1) ──
    if _skill_tag.startswith("health_c1_physical_"):
        health_physical_ctx = (
            "Topic: Basic Physical Activities (Class 1 Health & PE, CBSE). "
            "Cover: running, jumping, throwing, catching, hopping, skipping, balancing. "
            "Use very simple language — Class 1 level (age 6). Use Indian names and contexts. "
            "DO NOT repeat the same activity scenario. "
        )
        health_physical_map = {
            "health_c1_physical_identify": "format: pick_correct_science. Multiple choice about activities. Example: 'Which of these is a physical activity? (a) Sleeping (b) Running (c) Watching TV (d) Sitting' -> (b) Running",
            "health_c1_physical_apply": "format: give_example. Give an example. Example: 'Name two physical activities you can do during recess at school.'",
            "health_c1_physical_represent": "format: sequence_steps. Order steps. Example: 'Put in order for a relay race: (a) Run to the finish line (b) Stand at the starting line (c) Pass the baton to your friend (d) Wait for the whistle.'",
            "health_c1_physical_error": "format: error_spot_science. Present wrong idea. Example: 'Kiran says playing video games all day is the same as playing outside. Is this correct? Why or why not?'",
            "health_c1_physical_thinking": "format: thinking_science. Reasoning question. Example: 'Why do you think playing outside is good for your body?'",
        }
        return health_physical_ctx + health_physical_map.get(_skill_tag, "About physical activities.")

    # ── Health & PE: Healthy Eating Habits (Class 2) ──
    if _skill_tag.startswith("health_c2_eating_"):
        health_eating_ctx = (
            "Topic: Healthy Eating Habits (Class 2 Health & PE, CBSE). "
            "Cover: eating fruits and vegetables, drinking water, avoiding junk food, "
            "choosing healthy snacks, balanced meals. "
            "Use Indian names and school contexts. Keep vocabulary appropriate — Class 2 level. "
            "DO NOT repeat the same eating scenario. "
        )
        health_eating_map = {
            "health_c2_eating_identify": "format: pick_correct_science. Multiple choice about eating. Example: 'Which is a healthy snack? (a) Chips (b) Apple (c) Chocolate (d) Soft drink' -> (b) Apple",
            "health_c2_eating_apply": "format: explain_why_science. Explain a healthy habit. Example: 'Why should you eat fruits and vegetables every day?'",
            "health_c2_eating_represent": "format: sequence_steps. Order steps. Example: 'Put in order for a healthy morning: (a) Eat a healthy breakfast (b) Wake up early (c) Wash hands before eating (d) Drink a glass of water.'",
            "health_c2_eating_error": "format: error_spot_science. Present unhealthy habit. Example: 'Sneha eats chips and cola for lunch every day. She says it gives her energy. Is this correct? What should she eat instead?'",
            "health_c2_eating_thinking": "format: thinking_science. Reasoning question. Example: 'Why do you think drinking water is better than drinking soft drinks?'",
        }
        return health_eating_ctx + health_eating_map.get(_skill_tag, "About healthy eating.")

    # ── Health & PE: Outdoor Play (Class 2) ──
    if _skill_tag.startswith("health_c2_outdoor_"):
        health_outdoor_ctx = (
            "Topic: Outdoor Play (Class 2 Health & PE, CBSE). "
            "Cover: benefits of playing outside, types of outdoor games (kho-kho, hopscotch, "
            "cycling, running), why outdoor play is important. "
            "Use Indian names and school contexts. Keep vocabulary appropriate — Class 2 level. "
            "DO NOT repeat the same outdoor play scenario. "
        )
        health_outdoor_map = {
            "health_c2_outdoor_identify": "format: true_false. True/false about outdoor play. Example: 'True or False: Playing outside helps make your bones and muscles strong.' -> True",
            "health_c2_outdoor_apply": "format: give_example. Give an example. Example: 'Name three outdoor games you can play with your friends.'",
            "health_c2_outdoor_represent": "format: sequence_steps. Order steps. Example: 'Put in order before going to play outside: (a) Put on your shoes (b) Drink water (c) Ask permission from your parents (d) Do your homework first.'",
            "health_c2_outdoor_error": "format: error_spot_science. Present wrong idea. Example: 'Aman says sitting inside and watching cartoons all day is just as good as playing outside. Is this correct? Why or why not?'",
            "health_c2_outdoor_thinking": "format: thinking_science. Reasoning question. Example: 'How does playing outside with friends help your body and your mind?'",
        }
        return health_outdoor_ctx + health_outdoor_map.get(_skill_tag, "About outdoor play.")

    # ── Health & PE: Basic Stretching (Class 2) ──
    if _skill_tag.startswith("health_c2_stretching_"):
        health_stretching_ctx = (
            "Topic: Basic Stretching (Class 2 Health & PE, CBSE). "
            "Cover: simple stretches (arm stretch, toe touch, neck roll, side bend), "
            "warming up before exercise, why stretching is important. "
            "Use Indian names and school contexts. Keep vocabulary appropriate — Class 2 level. "
            "DO NOT repeat the same stretching scenario. "
        )
        health_stretching_map = {
            "health_c2_stretching_identify": "format: pick_correct_science. Multiple choice about stretching. Example: 'When should you stretch? (a) Only before sleeping (b) Before playing or exercising (c) Never (d) Only on holidays' -> (b) Before playing or exercising",
            "health_c2_stretching_apply": "format: give_example. Give an example. Example: 'Name two stretches you can do before running in the playground.'",
            "health_c2_stretching_represent": "format: sequence_steps. Order steps. Example: 'Put in order for warming up: (a) Do gentle arm circles (b) Stand in a line on the ground (c) Touch your toes slowly (d) Do jumping jacks.'",
            "health_c2_stretching_error": "format: error_spot_science. Present wrong idea. Example: 'Kiran started running very fast without warming up first. He says stretching is a waste of time. Is this correct? What could happen?'",
            "health_c2_stretching_thinking": "format: thinking_science. Reasoning question. Example: 'Why do you think it is important to warm up your body before playing a sport?'",
        }
        return health_stretching_ctx + health_stretching_map.get(_skill_tag, "About stretching.")

    # ── Health & PE: Balanced Diet (Class 3) ──
    if _skill_tag.startswith("health_c3_diet_"):
        health_diet_ctx = (
            "Topic: Balanced Diet (Class 3 Health & PE, CBSE). "
            "Cover: five food groups (carbohydrates, proteins, fats, vitamins, minerals), "
            "nutrients, Indian thali concept, healthy meals. "
            "Use Indian names and school contexts. Keep vocabulary appropriate — Class 3 level. "
            "DO NOT repeat the same diet scenario. "
        )
        health_diet_map = {
            "health_c3_diet_identify": "format: pick_correct_science. Multiple choice about diet. Example: 'Which food group gives us energy? (a) Vitamins (b) Carbohydrates (c) Water (d) Minerals' -> (b) Carbohydrates",
            "health_c3_diet_apply": "format: explain_why_science. Explain about balanced diet. Example: 'Why should an Indian thali have dal, roti, sabzi, and curd together?'",
            "health_c3_diet_represent": "format: cause_effect. Connect food and benefit. Example: 'Match: (a) Milk — Energy (b) Rice — Strong bones (c) Spinach — Iron for blood. Write the correct pairs.'",
            "health_c3_diet_error": "format: error_spot_science. Present wrong diet idea. Example: 'Arjun eats only biscuits and noodles every day. He says he is eating enough food. Is this a balanced diet? What is missing?'",
            "health_c3_diet_thinking": "format: thinking_science. Reasoning question. Example: 'Design a balanced lunch plate for a Class 3 student. Explain why you chose each food.'",
        }
        return health_diet_ctx + health_diet_map.get(_skill_tag, "About balanced diet.")

    # ── Health & PE: Team Sports Rules (Class 3) ──
    if _skill_tag.startswith("health_c3_sports_"):
        health_sports_ctx = (
            "Topic: Team Sports Rules (Class 3 Health & PE, CBSE). "
            "Cover: basic rules of cricket, football, kabaddi, kho-kho; fair play; "
            "sportsmanship; different positions and roles in team sports. "
            "Use Indian names and school contexts. Keep vocabulary appropriate — Class 3 level. "
            "DO NOT repeat the same sport or rule. "
        )
        health_sports_map = {
            "health_c3_sports_identify": "format: true_false. True/false about sports rules. Example: 'True or False: In cricket, each team gets a chance to bat and bowl.' -> True",
            "health_c3_sports_apply": "format: explain_why_science. Explain about sports. Example: 'Why is it important to follow the rules during a game of kabaddi?'",
            "health_c3_sports_represent": "format: sequence_steps. Order steps. Example: 'Put in order for starting a cricket match: (a) The captain wins the toss (b) The teams warm up (c) The batting team sends two players (d) The bowler bowls the first ball.'",
            "health_c3_sports_error": "format: error_spot_science. Present poor sportsmanship. Example: 'Sneha's team lost the football match. She refused to shake hands with the other team and said the game was unfair. Is this good sportsmanship? What should she do?'",
            "health_c3_sports_thinking": "format: thinking_science. Reasoning question. Example: 'Why do you think team sports teach us important life skills? Give two examples.'",
        }
        return health_sports_ctx + health_sports_map.get(_skill_tag, "About team sports rules.")

    # ── Health & PE: Safety at Play (Class 3) ──
    if _skill_tag.startswith("health_c3_safety_"):
        health_safety_ctx = (
            "Topic: Safety at Play (Class 3 Health & PE, CBSE). "
            "Cover: playground safety rules, avoiding injuries, first aid kit awareness, "
            "safe and unsafe behaviours during play, wearing proper shoes. "
            "Use Indian names and school contexts. Keep vocabulary appropriate — Class 3 level. "
            "DO NOT repeat the same safety scenario. "
        )
        health_safety_map = {
            "health_c3_safety_identify": "format: pick_correct_science. Multiple choice about safety. Example: 'What should you do before using a swing? (a) Push someone off it (b) Check if it is broken (c) Jump on it quickly (d) Run away' -> (b) Check if it is broken",
            "health_c3_safety_apply": "format: explain_why_science. Explain about safety. Example: 'Why should you wear proper shoes while playing on the ground?'",
            "health_c3_safety_represent": "format: sequence_steps. Order steps. Example: 'Put in order if a friend falls and scrapes her knee: (a) Help her sit down (b) Tell the teacher (c) Stay calm (d) Get the first aid kit.'",
            "health_c3_safety_error": "format: error_spot_science. Present unsafe behaviour. Example: 'Riya was running near the swimming pool and pushing other children. She says it is just fun. Is this safe? What could happen?'",
            "health_c3_safety_thinking": "format: thinking_science. Reasoning question. Example: 'What are three safety rules everyone should follow on a playground?'",
        }
        return health_safety_ctx + health_safety_map.get(_skill_tag, "About safety at play.")

    # ── Health & PE: First Aid Basics (Class 4) ──
    if _skill_tag.startswith("health_c4_firstaid_"):
        health_firstaid_ctx = (
            "Topic: First Aid Basics (Class 4 Health & PE, CBSE). "
            "Cover: treating minor cuts and burns, bandaging, when to call an adult, "
            "contents of a first aid kit, basic wound care. "
            "Use Indian names and school contexts. Keep vocabulary appropriate — Class 4 level. "
            "DO NOT repeat the same first aid scenario. "
        )
        health_firstaid_map = {
            "health_c4_firstaid_identify": "format: pick_correct_science. Multiple choice about first aid. Example: 'What should you do first if you get a small burn? (a) Put ice directly on it (b) Run cold water over it (c) Ignore it (d) Put toothpaste on it' -> (b) Run cold water over it",
            "health_c4_firstaid_apply": "format: explain_why_science. Explain first aid. Example: 'Why should you clean a cut with water before putting a bandage on it?'",
            "health_c4_firstaid_represent": "format: sequence_steps. Order steps. Example: 'Put in order for treating a small cut: (a) Apply an antiseptic cream (b) Wash the cut with clean water (c) Press with a clean cloth if bleeding (d) Cover with a plaster.'",
            "health_c4_firstaid_error": "format: error_spot_science. Present wrong first aid. Example: 'Aman put butter on his burn and said his grandmother told him to do this. Is this the correct first aid for a burn? What should he do instead?'",
            "health_c4_firstaid_thinking": "format: thinking_science. Reasoning question. Example: 'Why is it important for every school to have a first aid kit? What should be in it?'",
        }
        return health_firstaid_ctx + health_firstaid_map.get(_skill_tag, "About first aid.")

    # ── Health & PE: Yoga Introduction (Class 4) ──
    if _skill_tag.startswith("health_c4_yoga_"):
        health_yoga_ctx = (
            "Topic: Yoga Introduction (Class 4 Health & PE, CBSE). "
            "Cover: basic asanas (Tadasana, Vrikshasana, Balasana, Bhujangasana, Shavasana), "
            "breathing exercises (pranayama), benefits of yoga for body and mind. "
            "Use Indian names and school contexts. Keep vocabulary appropriate — Class 4 level. "
            "DO NOT repeat the same yoga asana or concept. "
        )
        health_yoga_map = {
            "health_c4_yoga_identify": "format: true_false. True/false about yoga. Example: 'True or False: Tadasana (Mountain Pose) helps improve balance and posture.' -> True",
            "health_c4_yoga_apply": "format: give_example. Give an example. Example: 'Name two yoga asanas and describe how they help your body.'",
            "health_c4_yoga_represent": "format: sequence_steps. Order steps. Example: 'Put in order for doing Surya Namaskar: (a) Stand straight in Tadasana (b) Raise arms overhead (c) Bend forward and touch toes (d) Take a deep breath in.'",
            "health_c4_yoga_error": "format: error_spot_science. Present wrong yoga practice. Example: 'Sneha does yoga very fast without proper breathing. She says speed is more important. Is this correct? What should she focus on?'",
            "health_c4_yoga_thinking": "format: thinking_science. Reasoning question. Example: 'Why do you think India celebrates International Yoga Day on 21 June? How does yoga help both body and mind?'",
        }
        return health_yoga_ctx + health_yoga_map.get(_skill_tag, "About yoga.")

    # ── Health & PE: Importance of Sleep (Class 4) ──
    if _skill_tag.startswith("health_c4_sleep_"):
        health_sleep_ctx = (
            "Topic: Importance of Sleep (Class 4 Health & PE, CBSE). "
            "Cover: how many hours children need (9-11 hours), effects of screen time before bed, "
            "good sleep habits, bedtime routines, why sleep matters for learning and growth. "
            "Use Indian names and school contexts. Keep vocabulary appropriate — Class 4 level. "
            "DO NOT repeat the same sleep concept. "
        )
        health_sleep_map = {
            "health_c4_sleep_identify": "format: true_false. True/false about sleep. Example: 'True or False: Children aged 9-10 should sleep for at least 9 hours every night.' -> True",
            "health_c4_sleep_apply": "format: explain_why_science. Explain about sleep. Example: 'Why should you avoid watching TV or using a phone just before going to bed?'",
            "health_c4_sleep_represent": "format: cause_effect. Connect actions and effects. Example: 'Match: (a) Sleeping late — Fresh and alert in class (b) Getting 10 hours of sleep — Feeling tired at school (c) No screen before bed — Falling asleep faster. Write the correct pairs.'",
            "health_c4_sleep_error": "format: error_spot_science. Present bad sleep habit. Example: 'Kiran watches cartoons on a tablet until midnight every day. He says he can sleep in class if he is tired. Is this correct? What should he do?'",
            "health_c4_sleep_thinking": "format: thinking_science. Reasoning question. Example: 'Why do you think getting enough sleep helps you do better at school?'",
        }
        return health_sleep_ctx + health_sleep_map.get(_skill_tag, "About importance of sleep.")

    # ── Health & PE: Fitness and Stamina (Class 5) ──
    if _skill_tag.startswith("health_c5_fitness_"):
        health_fitness_ctx = (
            "Topic: Fitness and Stamina (Class 5 Health & PE, CBSE). "
            "Cover: exercises for strength and endurance, measuring fitness, "
            "running, push-ups, skipping rope, heart health, stamina building. "
            "Use Indian names and school contexts. Keep vocabulary appropriate — Class 5 level. "
            "DO NOT repeat the same fitness concept. "
        )
        health_fitness_map = {
            "health_c5_fitness_identify": "format: pick_correct_science. Multiple choice about fitness. Example: 'Which activity helps build stamina? (a) Watching TV (b) Running laps (c) Sleeping (d) Playing video games' -> (b) Running laps",
            "health_c5_fitness_apply": "format: explain_why_science. Explain about fitness. Example: 'Why is it important to exercise regularly to keep your heart healthy?'",
            "health_c5_fitness_represent": "format: sequence_steps. Order steps. Example: 'Put in order for a fitness routine: (a) Cool down with stretching (b) Warm up with light jogging (c) Do the main exercise (running, push-ups) (d) Drink water and rest.'",
            "health_c5_fitness_error": "format: error_spot_science. Present wrong fitness idea. Example: 'Arjun says exercising once a month is enough to stay fit. He only plays cricket during the annual sports day. Is this correct? How often should he exercise?'",
            "health_c5_fitness_thinking": "format: thinking_science. Reasoning question. Example: 'Design a one-week fitness plan for a Class 5 student. What activities would you include and why?'",
        }
        return health_fitness_ctx + health_fitness_map.get(_skill_tag, "About fitness and stamina.")

    # ── Health & PE: Nutrition Labels Reading (Class 5) ──
    if _skill_tag.startswith("health_c5_nutrition_"):
        health_nutrition_ctx = (
            "Topic: Nutrition Labels Reading (Class 5 Health & PE, CBSE). "
            "Cover: reading food labels, understanding calories, protein, fat, sugar, "
            "expiry dates, ingredients list, making healthier food choices. "
            "Use Indian names and school contexts. Keep vocabulary appropriate — Class 5 level. "
            "DO NOT repeat the same nutrition label concept. "
        )
        health_nutrition_map = {
            "health_c5_nutrition_identify": "format: true_false. True/false about labels. Example: 'True or False: The expiry date on a food packet tells you the last date by which you should eat the food.' -> True",
            "health_c5_nutrition_apply": "format: explain_why_science. Explain about labels. Example: 'Why should you check the sugar content on a juice box before buying it?'",
            "health_c5_nutrition_represent": "format: cause_effect. Connect labels and choices. Example: 'Match: (a) High sugar — May cause weight gain (b) High protein — Good for muscles (c) High trans fat — Bad for heart health. Write the correct pairs.'",
            "health_c5_nutrition_error": "format: error_spot_science. Present wrong label reading. Example: 'Riya says a food packet with \"0% fat\" printed in big letters must be completely healthy. She did not check the sugar or sodium content. Is she correct? What else should she check?'",
            "health_c5_nutrition_thinking": "format: thinking_science. Reasoning question. Example: 'Compare the nutrition labels of a packet of chips and a packet of roasted chana. Which is healthier and why?'",
        }
        return health_nutrition_ctx + health_nutrition_map.get(_skill_tag, "About nutrition labels.")

    # ── Health & PE: Mental Health Awareness (Class 5) ──
    if _skill_tag.startswith("health_c5_mental_"):
        health_mental_ctx = (
            "Topic: Mental Health Awareness (Class 5 Health & PE, CBSE). "
            "Cover: managing stress, talking about feelings, mindfulness, "
            "coping with difficult emotions, seeking help, self-care, being kind to yourself. "
            "Use Indian names and school contexts. Keep vocabulary appropriate — Class 5 level. "
            "DO NOT repeat the same mental health concept. "
        )
        health_mental_map = {
            "health_c5_mental_identify": "format: pick_correct_science. Multiple choice about mental health. Example: 'What is a good way to manage stress before an exam? (a) Skip the exam (b) Take deep breaths and study a little at a time (c) Stay awake all night (d) Argue with your parents' -> (b) Take deep breaths and study a little at a time",
            "health_c5_mental_apply": "format: explain_why_science. Explain about mental health. Example: 'Why is it important to talk to a trusted adult when you feel very sad or worried?'",
            "health_c5_mental_represent": "format: cause_effect. Connect actions and feelings. Example: 'Match: (a) Talking to a friend — Feeling calm (b) Deep breathing — Feeling less lonely (c) Writing in a journal — Understanding your feelings better. Write the correct pairs.'",
            "health_c5_mental_error": "format: error_spot_science. Present wrong mental health idea. Example: 'Aman says real boys never cry or feel sad. He tells his friend to stop being weak. Is this correct? Why or why not?'",
            "health_c5_mental_thinking": "format: thinking_science. Reasoning question. Example: 'What are three things you can do every day to take care of your mental health?'",
        }
        return health_mental_ctx + health_mental_map.get(_skill_tag, "About mental health awareness.")

    # Check if this is a non-arithmetic topic by looking at skill_tag
    _NON_ARITHMETIC_TAGS = {
        "multiplication_tables", "multiplication_word_problem", "multiplication_fill_blank",
        "multiplication_error_spot", "multiplication_thinking",
        "division_basics", "division_word_problem", "division_fill_blank",
        "division_error_spot", "division_thinking",
        "place_value_identify", "number_comparison", "number_sequence",
        "number_expansion", "number_ordering", "place_value_error", "number_thinking",
        "fraction_identify_half", "fraction_identify_quarter",
        "fraction_word_problem", "fraction_of_shape_shaded",
        "fraction_compare", "fraction_fill_blank",
        "fraction_error_spot", "fraction_thinking",
        "clock_reading", "time_word_problem", "calendar_reading",
        "time_fill_blank", "time_error_spot", "time_thinking",
        "symmetry_identify", "symmetry_draw", "symmetry_fill_blank",
        "symmetry_error_spot", "symmetry_thinking",
        "money_recognition", "money_word_problem", "money_change",
        "money_fill_blank", "money_error_spot", "money_thinking",
        "number_pattern", "shape_pattern", "pattern_fill_blank",
        "pattern_error_spot", "pattern_thinking",
    }
    # Include all c2_, c4_, and eng_ prefixed tags as non-arithmetic
    _NON_ARITHMETIC_TAGS.update(
        tag for tag in _SKILL_TAG_TO_SLOT if tag.startswith("c2_") or tag.startswith("c4_") or tag.startswith("c5_") or tag.startswith("eng_") or tag.startswith("sci_") or tag.startswith("hin_") or tag.startswith("comp_") or tag.startswith("gk_") or tag.startswith("moral_") or tag.startswith("health_")
    )
    _is_generic_arithmetic = _skill_tag not in _NON_ARITHMETIC_TAGS

    base = ""

    if slot_type == "recognition":
        # If variant has a deterministic carry pair, use it directly
        if chosen_variant and chosen_variant.get("carry_pair"):
            a, b = chosen_variant["carry_pair"]
            op = chosen_variant.get("operation", "addition")
            sym = "+" if op == "addition" else "-"
            base = (
                f"format: column_setup. "
                f'Write EXACTLY: "Write {a} {sym} {b} in column form." '
                f"Answer: {a} {sym} {b}"
            )
        elif _is_generic_arithmetic:
            base = (
                "format: column_setup OR place_value. "
                "Direct recall or single-step. Easy.\n"
                'Examples: "Write 345 + 278 in column form." / '
                '"What is the hundreds digit in 507?"'
            )
        else:
            base = f"format: standard. Direct recall or identification about the topic. skill: {_skill_tag}."

    elif slot_type == "application":
        if not chosen_variant:
            base = "format: word_problem. Use a real-world scenario. Exact numerical answer required."
        else:
            name = chosen_variant.get("name", "Aarav")
            ctx = chosen_variant.get("context", {})
            if chosen_variant.get("carry_pair"):
                a, b = chosen_variant["carry_pair"]
                op = chosen_variant.get("operation", "addition")
                sym = "+" if op == "addition" else "-"
                base = (
                    f"format: word_problem. "
                    f"MUST use this context: {name} is {ctx.get('scenario', 'at school')}. "
                    f"Item: {ctx.get('item', 'things')}. "
                    f"MUST use EXACTLY these numbers: {a} {sym} {b}. "
                    f"Exact numerical answer required."
                )
            elif _is_generic_arithmetic:
                base = (
                    f"format: word_problem. "
                    f"MUST use this context: {name} is {ctx.get('scenario', 'at school')}. "
                    f"Item: {ctx.get('item', 'things')}. "
                    f"Numbers must require carrying. Exact numerical answer required."
                )
            else:
                base = (
                    f"format: word_problem. "
                    f"MUST use this context: {name} is {ctx.get('scenario', 'at school')}. "
                    f"Item: {ctx.get('item', 'things')}. "
                    f"Exact numerical answer required."
                )
    elif slot_type == "representation":
        if _is_generic_arithmetic:
            base = (
                "format: missing_number OR estimation OR place_value. "
                'NEVER "visualize" or "draw" or "use array/number line".\n'
                'Examples: "___ + 178 = 502" / '
                '"Estimate 478 + 256 to the nearest hundred." / '
                '"Show 345 as 3 hundreds + ___ tens + 5 ones."'
            )
        else:
            base = f"format: fill_blank OR standard. Represent or complete a pattern. skill: {_skill_tag}."

    elif slot_type == "error_detection":
        if not chosen_variant:
            base = "format: error_spot. Show a wrong answer for the student to find and correct. The question MUST be about the CURRENT TOPIC (not addition/subtraction unless that IS the topic)."
        else:
            err = chosen_variant.get("error", {})
            if err and "a" in err and "wrong" in err:
                base = (
                    f"format: error_spot. "
                    f"MUST use EXACTLY these numbers: "
                    f"A student added {err['a']} + {err['b']} and got {err['wrong']}. "
                    f"The correct answer is {err['correct']}. "
                    f"The student's mistake: {err['hint']}. "
                    f"Write a question asking the student to find the mistake and give the correct answer."
                )
            else:
                base = "format: error_spot. Show a wrong answer for the student to find and correct. The question MUST be about the CURRENT TOPIC (not addition/subtraction unless that IS the topic)."

    elif slot_type == "thinking":
        if not chosen_variant:
            base = "format: thinking. Reasoning question, not pure computation."
        else:
            style = chosen_variant.get("style", {})
            base = (
                f"format: thinking. "
                f"Style: {style['style']}. "
                f"{style['instruction']} "
                f"Use 3-digit numbers that require carrying."
            )

    # ── Directive augmentation ──
    if directive:
        extras = []
        if directive.get("carry_required"):
            extras.append(
                "Numbers MUST require carrying (digit sum >= 10 in ones or tens) "
                "for addition, or borrowing for subtraction."
            )
        ops = directive.get("allow_operations")
        if ops and len(ops) == 1:
            extras.append(f"Use {ops[0]} only.")
        if directive.get("estimation_rule"):
            extras.append(
                "Round each number to the nearest hundred before estimating."
            )
        if extras:
            base += "\n" + " ".join(extras)

    # ── Indian Context Bank injection (Gold-G3) ──
    # Append Indian context guidance for application (word_problem) slots.
    # This covers all paths that set `base` (i.e., did not early-return).
    if slot_type == "application" and topic:
        _ctx_bank = get_context_bank(topic)
        if _ctx_bank:
            base += (
                f"\nChoose ONE context from this list for the word problem: {_ctx_bank}. "
                "Use Indian names: Priya, Arjun, Meera, Ravi, Kavya, Dadi, Chacha, Aarav, Ananya, Rohan. "
                "Make the problem feel real to an Indian child. "
                "DO NOT use generic 'Ram and Shyam' or generic fruit/animal problems. "
                "DO NOT reuse a context already used in this worksheet."
            )

    return base


# ════════════════════════════════════════════════════════════
# G) Token-Efficient Prompts
# ════════════════════════════════════════════════════════════

META_SYSTEM = (
    "Expert primary-school curriculum designer. "
    "Output JSON only. No markdown. No extra keys."
)

META_USER_TEMPLATE = (
    'Grade {grade} {subject} | Topic: "{topic}" | Region: {region} | Difficulty: {difficulty}\n'
    "Generate worksheet metadata.\n"
    'micro_skill must be narrow and specific (NOT "addition" - instead '
    '"3-digit addition with carrying in tens and hundreds").\n'
    "common_mistakes: 2-5 specific errors students make on this micro_skill.\n"
    "parent_tip: <=2 sentences of actionable guidance.\n"
    "teaching_script: 1 sentence.\n"
    '{{"micro_skill":"","skill_focus":"","learning_objective":"",'
    '"difficulty":"","parent_tip":"","teaching_script":"","common_mistakes":[]}}'
)

QUESTION_SYSTEM = (
    "Expert question writer for primary-school worksheets. "
    "Output JSON only. No markdown. No extra keys.\n"
    "Rules:\n"
    "- Grade-appropriate language only.\n"
    "- NEVER reference visuals, arrays, number lines, or diagrams in "
    "question_text. Students see only printed text.\n"
    "- Every answer must be mathematically correct and verifiable.\n"
    "- pictorial_elements must be empty list [].\n"
    "\n"
    "CRITICAL DEDUPLICATION RULES:\n"
    "- DO NOT use the same numbers in consecutive questions\n"
    "- DO NOT repeat the same scenario or context\n"
    "- DO NOT use the same shape/object in consecutive questions\n"
    "- Each question must be UNIQUE in both numbers AND context\n"
    "- Track previous questions and ensure variety\n"
    "\n"
    "Example violations to avoid:\n"
    '- Q1: "half of 8" and Q2: "half of 16" (same operation) → Use different operations\n'
    '- Q4: "pizza cut into 4" and Q5: "cake cut into 4" (same context) → Use different food or different divisions\n'
    '- Q6: "56 ÷ 8" and Q7: "56 ÷ 8" (same numbers) → Use different numbers'
)

QUESTION_SYSTEM_ENGLISH = (
    "Expert question writer for primary-school English language worksheets. "
    "Output JSON only. No markdown. No extra keys.\n"
    "Rules:\n"
    "- Grade-appropriate vocabulary and sentence complexity.\n"
    "- NEVER reference visuals, pictures, or diagrams in question_text.\n"
    "- Every answer must be grammatically correct and unambiguous.\n"
    "- pictorial_elements must be empty list [].\n"
    "- Use Indian English spelling and conventions (colour, favourite, etc.).\n"
    "- Use age-appropriate Indian contexts (school, family, festivals, cricket).\n"
    "\n"
    "CRITICAL DEDUPLICATION RULES:\n"
    "- DO NOT reuse the same word, sentence, or passage across questions\n"
    "- DO NOT repeat the same grammar concept in consecutive questions\n"
    "- Each question must test a UNIQUE aspect of the topic\n"
    "- Vary sentence structures and vocabulary\n"
)

QUESTION_SYSTEM_SCIENCE = (
    "Expert question writer for primary-school Science worksheets (CBSE curriculum). "
    "Output JSON only. No markdown. No extra keys.\n"
    "Rules:\n"
    "- Grade-appropriate scientific vocabulary.\n"
    "- NEVER reference visuals, pictures, or diagrams in question_text.\n"
    "- Every answer must be scientifically accurate and age-appropriate.\n"
    "- pictorial_elements must be empty list [].\n"
    "- Use Indian contexts: local plants (neem, tulsi, mango), Indian animals, "
    "Indian food (dal, roti, rice), monsoon, Indian seasons.\n"
    "- NEVER generate arithmetic or maths questions.\n"
    "\n"
    "CRITICAL DEDUPLICATION RULES:\n"
    "- DO NOT reuse the same fact, organism, or concept across questions\n"
    "- DO NOT repeat the same question pattern in consecutive questions\n"
    "- Each question must test a UNIQUE aspect of the topic\n"
    "- Vary contexts, examples, and question styles\n"
)

QUESTION_SYSTEM_HINDI = (
    "Expert question writer for primary-school Hindi language worksheets (CBSE curriculum). "
    "Output JSON only. No markdown. No extra keys.\n"
    "Rules:\n"
    "- Use Devanagari script for question_text and answer.\n"
    "- Grade-appropriate Hindi vocabulary.\n"
    "- CBSE curriculum aligned (Rimjhim textbook topics).\n"
    "- NEVER reference visuals, pictures, or diagrams in question_text.\n"
    "- Every answer must be grammatically correct Hindi in Devanagari.\n"
    "- pictorial_elements must be empty list [].\n"
    "- Use Indian cultural contexts: festivals (Diwali, Holi, Raksha Bandhan), "
    "food (roti, dal, sabzi), family (dadi, nani, chacha), school life, "
    "Indian animals (mor, hathi, bandar), Indian places.\n"
    "- NEVER generate arithmetic, maths, or English grammar questions.\n"
    "\n"
    "CRITICAL DEDUPLICATION RULES:\n"
    "- DO NOT reuse the same word, letter, or sentence across questions\n"
    "- DO NOT repeat the same concept in consecutive questions\n"
    "- Each question must test a UNIQUE aspect of the topic\n"
    "- Vary vocabulary and sentence structures\n"
)

QUESTION_USER_TEMPLATE = (
    "Grade {grade} {subject} | Micro-skill: {micro_skill} | "
    "Slot: {slot_type} | Difficulty: {difficulty}\n"
    "{topic_constraint}"
    "Avoid reusing: {avoid}\n"
    "{slot_instruction}\n"
    "{language_instruction}"
    '{{"format":"","question_text":"","pictorial_elements":[],"answer":""}}'
)

# Topic-specific constraints injected into the LLM prompt
_TOPIC_CONSTRAINTS: dict[str, str] = {
    "Symmetry": (
        "CRITICAL: ALL questions MUST be about Symmetry ONLY — lines of symmetry, "
        "folding shapes, mirror images. NEVER generate addition/subtraction/arithmetic questions.\n"
    ),
    "Money (bills and change)": (
        "CRITICAL: ALL questions MUST be about Money ONLY — rupees, paise, bills, coins, "
        "making change. NEVER generate plain addition/subtraction questions.\n"
    ),
    "Time (reading clock, calendar)": (
        "CRITICAL: ALL questions MUST be about Time ONLY — clocks, hours, minutes, "
        "calendar, days, months. NEVER generate plain addition/subtraction questions.\n"
    ),
    "Patterns and sequences": (
        "CRITICAL: ALL questions MUST be about Patterns ONLY — number sequences, "
        "shape patterns, repeating patterns. NEVER generate plain arithmetic questions.\n"
    ),
    "Fractions": (
        "CRITICAL: ALL questions MUST be about Fractions ONLY — halves, quarters, "
        "parts of whole. NEVER generate addition/subtraction/carry questions.\n"
    ),
    "Fractions (halves, quarters)": (
        "CRITICAL: ALL questions MUST be about Fractions (halves/quarters) ONLY. "
        "NEVER generate addition/subtraction/carry questions.\n"
    ),
    "Numbers up to 10000": (
        "CRITICAL: ALL questions MUST be about Numbers/Place Value ONLY — place value, "
        "expanded form, comparison, ordering. NEVER generate addition/subtraction questions.\n"
    ),
    "Multiplication (tables 2-10)": (
        "CRITICAL: ALL questions MUST be about Multiplication tables (2-10) ONLY. "
        "NEVER generate addition/subtraction/carry questions.\n"
    ),
    "Division basics": (
        "CRITICAL: ALL questions MUST be about Division ONLY — equal sharing, grouping, "
        "division facts. NEVER generate addition/subtraction questions.\n"
    ),
    # ── Class 1 topic constraints ──
    "Numbers 1 to 50 (Class 1)": (
        "CRITICAL: Numbers 1-50 ONLY. NEVER use numbers above 50. "
        "NEVER generate addition, subtraction, multiplication, or division questions. "
        "Focus on counting, number names, before/after, comparison (greater/smaller), ordering.\n"
    ),
    "Numbers 51 to 100 (Class 1)": (
        "CRITICAL: Numbers 51-100 ONLY. NEVER use numbers above 100. "
        "NEVER generate addition, subtraction, multiplication, or division questions. "
        "Focus on counting, number names, before/after, comparison (greater/smaller), ordering.\n"
    ),
    "Addition up to 20 (Class 1)": (
        "CRITICAL: Addition ONLY. Both numbers must be between 1 and 10. "
        "Sum must NEVER exceed 20. NO carrying EVER. NO column form. "
        "NO subtraction, multiplication, or division. "
        "Use simple horizontal format: 7 + 5 = ___\n"
    ),
    "Subtraction within 20 (Class 1)": (
        "CRITICAL: Subtraction ONLY. Both numbers between 1 and 20. "
        "Result must NEVER be negative or zero. NO borrowing EVER. NO column form. "
        "The first number must always be larger than the second. "
        "NO addition, multiplication, or division. "
        "Use simple horizontal format: 15 - 7 = ___\n"
    ),
    "Basic Shapes (Class 1)": (
        "CRITICAL: ALL questions MUST be about basic 2D shapes ONLY — circle, square, triangle, rectangle. "
        "NO 3D shapes (cube, sphere, cone). Focus on shape names, sides, corners, real-world examples. "
        "NEVER generate arithmetic questions (no addition, subtraction, multiplication, division).\n"
    ),
    "Measurement (Class 1)": (
        "CRITICAL: ALL questions MUST be about comparing objects ONLY — longer/shorter, taller/shorter, "
        "heavier/lighter. NO standard units (no cm, m, kg, g). Use comparison words ONLY. "
        "NEVER generate arithmetic questions.\n"
    ),
    "Time (Class 1)": (
        "CRITICAL: ALL questions MUST be about daily routines and days of the week ONLY — "
        "morning, afternoon, evening, night. Days: Monday to Sunday. "
        "NO clock reading. NO hours or minutes. NO numbers for time. "
        "NEVER generate arithmetic questions.\n"
    ),
    "Money (Class 1)": (
        "CRITICAL: ALL questions MUST be about Indian coins ONLY — ₹1, ₹2, ₹5 coins. "
        "NO notes (no ₹10, ₹20, ₹50, ₹100). Total must NEVER exceed ₹20. "
        "Simple counting of coins only. NEVER generate arithmetic beyond simple coin counting.\n"
    ),
    "Addition (2-digit with carry)": (
        "CRITICAL: ALL questions MUST be about 2-digit Addition with carrying ONLY. "
        "Both numbers must be 2-digit (10-99). Sums must NOT exceed 198. "
        "Numbers MUST require carrying (ones digits sum >= 10). NEVER use 3-digit numbers. "
        "NEVER generate subtraction, multiplication, or division questions.\n"
    ),
    "Subtraction (2-digit with borrow)": (
        "CRITICAL: ALL questions MUST be about 2-digit Subtraction with borrowing ONLY. "
        "Both numbers must be 2-digit (10-99). "
        "Numbers MUST require borrowing (ones digit of top < ones digit of bottom). "
        "NEVER use 3-digit numbers. "
        "NEVER generate addition, multiplication, or division questions.\n"
    ),
    # ── Class 2 non-arithmetic topic constraints ──
    "Numbers up to 1000 (Class 2)": (
        "CRITICAL: ALL questions MUST be about Numbers/Place Value up to 1000 ONLY — "
        "hundreds, tens, ones, expanded form, comparison, ordering. "
        "Numbers must be 3-digit (100-999). NEVER use numbers above 999. "
        "NEVER generate addition/subtraction questions.\n"
    ),
    "Shapes and space (2D)": (
        "CRITICAL: ALL questions MUST be about 2D shapes ONLY — circle, square, triangle, "
        "rectangle, sides, corners. NEVER generate arithmetic questions.\n"
    ),
    "Measurement (length, weight)": (
        "CRITICAL: ALL questions MUST be about Measurement ONLY — length (cm, m), "
        "weight (g, kg). Compare, estimate, convert simple units. "
        "NEVER generate plain arithmetic questions.\n"
    ),
    "Time (hour, half-hour)": (
        "CRITICAL: ALL questions MUST be about Time ONLY — hours and half-hours on clocks. "
        "ONLY use o'clock and half past times. NEVER use quarter-hours or minutes. "
        "NEVER generate addition/subtraction questions.\n"
    ),
    "Money (coins and notes)": (
        "CRITICAL: ALL questions MUST be about Money ONLY — coins (1, 2, 5, 10 rupees), "
        "notes (10, 20, 50, 100 rupees). Simple buying, counting coins. "
        "NEVER generate plain arithmetic questions.\n"
    ),
    "Data handling (pictographs)": (
        "CRITICAL: ALL questions MUST be about reading and interpreting pictographs ONLY — "
        "picture graphs, counting symbols, comparing categories. "
        "NEVER generate plain arithmetic questions.\n"
    ),
    "Multiplication (tables 2-5)": (
        "CRITICAL: ALL questions MUST be about Multiplication tables 2, 3, 4, 5 ONLY. "
        "NEVER use tables above 5. NEVER generate addition/subtraction/carry questions.\n"
    ),
    "Division (sharing equally)": (
        "CRITICAL: ALL questions MUST be about equal sharing/division by 2, 3, 4, 5 ONLY. "
        "All division must be exact (no remainders). NEVER use divisors above 5. "
        "NEVER generate addition/subtraction questions.\n"
    ),
    # ── Class 4 topic constraints ──
    "Addition and subtraction (5-digit)": (
        "CRITICAL: ALL questions MUST be about 5-digit addition and subtraction ONLY. "
        "Use numbers in range 10000-99999. Require carrying for addition and borrowing for subtraction. "
        "NEVER generate fraction, decimal, or plain 2/3-digit arithmetic questions.\n"
    ),
    "Large numbers (up to 1,00,000)": (
        "CRITICAL: ALL questions MUST be about large numbers (5-digit, up to 99999) ONLY — "
        "Indian system place value (ten-thousands, thousands, hundreds, tens, ones), "
        "expanded form, comparison, ordering. NEVER generate addition/subtraction operation questions.\n"
    ),
    "Multiplication (3-digit × 2-digit)": (
        "CRITICAL: ALL questions MUST be about multi-digit multiplication ONLY — "
        "3-digit × 1-digit or 3-digit × 2-digit. NEVER generate addition/subtraction/carry questions.\n"
    ),
    "Division (long division)": (
        "CRITICAL: ALL questions MUST be about long division ONLY — "
        "3-digit ÷ 1-digit with or without remainder. Show steps of long division. "
        "NEVER generate addition/subtraction questions.\n"
    ),
    "Fractions (equivalent, comparison)": (
        "CRITICAL: ALL questions MUST be about Fractions ONLY — equivalent fractions, "
        "comparing fractions, simplifying fractions, fractions on number line. "
        "NEVER generate addition/subtraction/decimal questions.\n"
    ),
    "Decimals (tenths, hundredths)": (
        "CRITICAL: ALL questions MUST be about Decimals ONLY — tenths (0.1), hundredths (0.01), "
        "decimal place value, converting fractions to decimals, comparing decimals. "
        "NEVER generate addition/subtraction/carry questions.\n"
    ),
    "Geometry (angles, lines)": (
        "CRITICAL: ALL questions MUST be about Geometry ONLY — types of angles (acute, right, obtuse, straight), "
        "types of lines (parallel, perpendicular, intersecting). "
        "NEVER generate arithmetic, fraction, or decimal questions.\n"
    ),
    "Perimeter and area": (
        "CRITICAL: ALL questions MUST be about Perimeter and Area ONLY — "
        "perimeter of rectangles/squares, area of rectangles/squares. "
        "Use formulas: Perimeter = 2 × (length + width), Area = length × width. "
        "NEVER generate plain arithmetic questions.\n"
    ),
    "Time (minutes, 24-hour clock)": (
        "CRITICAL: ALL questions MUST be about Time ONLY — reading 24-hour clocks, "
        "converting between 12-hour and 24-hour format, calculating duration in hours and minutes. "
        "NEVER generate plain addition/subtraction questions.\n"
    ),
    "Money (bills, profit/loss)": (
        "CRITICAL: ALL questions MUST be about Money ONLY — bills, budgets, "
        "cost price, selling price, profit and loss. "
        "Use rupees (₹). NEVER generate plain arithmetic questions.\n"
    ),
    # ── Class 5 topic constraints ──
    "Numbers up to 10 lakh (Class 5)": (
        "CRITICAL: ALL questions MUST be about large numbers (up to 10,00,000) ONLY — "
        "Indian place value system (lakhs, ten-thousands, thousands, hundreds, tens, ones), "
        "expanded form, comparison, ordering. Numbers must be 6-7 digits. "
        "NEVER generate addition/subtraction operation questions.\n"
    ),
    "Factors and multiples (Class 5)": (
        "CRITICAL: ALL questions MUST be about Factors and Multiples ONLY — "
        "finding factors, listing multiples, prime/composite numbers, divisibility rules. "
        "Use numbers up to 100 for factors. "
        "NEVER generate addition/subtraction/carry questions.\n"
    ),
    "HCF and LCM (Class 5)": (
        "CRITICAL: ALL questions MUST be about HCF and LCM ONLY — "
        "Highest Common Factor, Least Common Multiple, prime factorisation. "
        "Use numbers up to 100. "
        "NEVER generate plain arithmetic or fraction questions.\n"
    ),
    "Fractions (add and subtract) (Class 5)": (
        "CRITICAL: ALL questions MUST be about Adding and Subtracting Fractions ONLY — "
        "like fractions, unlike fractions (find LCM of denominators), mixed numbers. "
        "Denominators up to 20. NEVER generate decimal or percentage questions.\n"
    ),
    "Decimals (all operations) (Class 5)": (
        "CRITICAL: ALL questions MUST be about Decimal Operations ONLY — "
        "addition, subtraction, multiplication, and division of decimals. "
        "Up to 2 decimal places. NEVER generate fraction or percentage questions.\n"
    ),
    "Percentage (Class 5)": (
        "CRITICAL: ALL questions MUST be about Percentage ONLY — "
        "converting fractions/decimals to percentage, finding percentage of a number, "
        "simple discount and increase problems. "
        "NEVER generate plain fraction or decimal arithmetic questions.\n"
    ),
    "Area and volume (Class 5)": (
        "CRITICAL: ALL questions MUST be about Area and Volume ONLY — "
        "area of triangles (½ × base × height), area of composite shapes, "
        "volume of cubes (side³) and cuboids (l × b × h). "
        "Use whole numbers for dimensions. "
        "NEVER generate plain arithmetic or fraction questions.\n"
    ),
    "Geometry (circles, symmetry) (Class 5)": (
        "CRITICAL: ALL questions MUST be about Circles and Symmetry ONLY — "
        "radius, diameter, circumference (basic), lines of symmetry, rotational symmetry. "
        "NEVER generate arithmetic, fraction, or decimal questions.\n"
    ),
    "Data handling (pie charts) (Class 5)": (
        "CRITICAL: ALL questions MUST be about Pie Charts and Data Handling ONLY — "
        "reading pie charts, comparing sectors, calculating simple percentages from pie charts. "
        "NEVER generate plain arithmetic questions.\n"
    ),
    "Speed distance time (Class 5)": (
        "CRITICAL: ALL questions MUST be about Speed, Distance, and Time ONLY — "
        "Speed = Distance ÷ Time, Distance = Speed × Time, Time = Distance ÷ Speed. "
        "Use km/hr and simple numbers. "
        "NEVER generate plain arithmetic or fraction questions.\n"
    ),
    # ── English Language topic constraints ──
    # ── Class 1 English constraints ──
    "Alphabet (Class 1)": (
        "CRITICAL: Only capital and small letter recognition. NO grammar. NO sentences longer than 3 words. "
        "Only A-Z and a-z. Use words with 3-5 letters maximum. "
        "NEVER generate arithmetic or maths questions.\n"
    ),
    "Phonics (Class 1)": (
        "CRITICAL: Only beginning letter sounds (e.g., 'b' for bat). NO blends, NO digraphs, NO grammar rules. "
        "Use only simple 3-5 letter words. NO long sentences. "
        "NEVER generate arithmetic or maths questions.\n"
    ),
    "Self and Family Vocabulary (Class 1)": (
        "CRITICAL: Only words for family members (mother, father, sister, brother, grandmother, grandfather) "
        "and body parts (hand, eye, nose, ear, leg). NO grammar terminology. NO complex sentences. "
        "Use names like Amma, Papa, Dadi, Nani, Raju, Meena. Words must be 3-5 letters max. "
        "NEVER generate arithmetic or maths questions.\n"
    ),
    "Animals and Food Vocabulary (Class 1)": (
        "CRITICAL: Only common animal names (cat, dog, cow, hen, fish, bird) and food names "
        "(apple, banana, rice, roti, milk, egg). NO grammar. NO complex sentences. "
        "Words must be 3-5 letters max. Use Indian contexts. "
        "NEVER generate arithmetic or maths questions.\n"
    ),
    "Greetings and Polite Words (Class 1)": (
        "CRITICAL: Only greetings (Hello, Good morning, Good night, Goodbye) and polite words "
        "(Please, Thank you, Sorry, Excuse me). NO grammar rules. NO complex sentences. "
        "Sentences must be 3-5 words max. Use Indian contexts (Namaste is OK). "
        "NEVER generate arithmetic or maths questions.\n"
    ),
    "Seasons (Class 1)": (
        "CRITICAL: Only season names (summer, winter, rainy/monsoon, spring) and simple associated words "
        "(hot, cold, rain, umbrella, sweater, fan). NO grammar. NO complex sentences. "
        "Words must be 3-5 letters max. Use Indian seasons and contexts. "
        "NEVER generate arithmetic or maths questions.\n"
    ),
    "Simple Sentences (Class 1)": (
        "CRITICAL: Only simple 3-5 word sentences (e.g., 'I see a cat.', 'Raju has a ball.'). "
        "NO grammar terminology. NO tenses. NO complex structures. "
        "Use Indian names: Raju, Meena, Amma, Papa. All words must be 3-5 letters max. "
        "NEVER generate arithmetic or maths questions.\n"
    ),
    # ── Class 2 English constraints ──
    "Nouns (Class 2)": (
        "CRITICAL: ALL questions MUST be about Nouns ONLY — naming words for people, places, animals, things. "
        "Use simple Class 2 level vocabulary. NEVER generate arithmetic or maths questions.\n"
    ),
    "Verbs (Class 2)": (
        "CRITICAL: ALL questions MUST be about Verbs (action words) ONLY — running, jumping, eating, etc. "
        "Use simple Class 2 level vocabulary. NEVER generate arithmetic or maths questions.\n"
    ),
    "Pronouns (Class 2)": (
        "CRITICAL: ALL questions MUST be about Pronouns ONLY — he, she, it, they, we, I, you. "
        "Use simple Class 2 level sentences. NEVER generate arithmetic or maths questions.\n"
    ),
    "Sentences (Class 2)": (
        "CRITICAL: ALL questions MUST be about Sentences ONLY — forming sentences, "
        "capital letters at start, full stop at end, simple sentence structure. "
        "Use Class 2 level vocabulary. NEVER generate arithmetic or maths questions.\n"
    ),
    "Rhyming Words (Class 2)": (
        "CRITICAL: ALL questions MUST be about Rhyming Words ONLY — words that sound alike "
        "(cat/bat, tree/free, etc.). Use simple Class 2 level words. "
        "NEVER generate arithmetic or maths questions.\n"
    ),
    "Punctuation (Class 2)": (
        "CRITICAL: ALL questions MUST be about Punctuation ONLY — full stop (.), "
        "question mark (?), capital letters. Simple Class 2 level. "
        "NEVER generate arithmetic or maths questions.\n"
    ),
    "Nouns (Class 3)": (
        "CRITICAL: ALL questions MUST be about Nouns ONLY — common nouns, proper nouns, "
        "collective nouns, singular/plural. NEVER generate arithmetic or maths questions.\n"
    ),
    "Verbs (Class 3)": (
        "CRITICAL: ALL questions MUST be about Verbs ONLY — action verbs, helping verbs, "
        "verb forms. NEVER generate arithmetic or maths questions.\n"
    ),
    "Adjectives (Class 3)": (
        "CRITICAL: ALL questions MUST be about Adjectives ONLY — describing words, "
        "degrees of comparison (big/bigger/biggest). NEVER generate arithmetic or maths questions.\n"
    ),
    "Pronouns (Class 3)": (
        "CRITICAL: ALL questions MUST be about Pronouns ONLY — personal pronouns (I, you, he, she, it, we, they), "
        "possessive pronouns (my, your, his, her, its). NEVER generate arithmetic or maths questions.\n"
    ),
    "Tenses (Class 3)": (
        "CRITICAL: ALL questions MUST be about Tenses ONLY — simple present, simple past, "
        "simple future. NEVER generate arithmetic or maths questions.\n"
    ),
    "Punctuation (Class 3)": (
        "CRITICAL: ALL questions MUST be about Punctuation ONLY — full stop, question mark, "
        "exclamation mark, comma, apostrophe. NEVER generate arithmetic or maths questions.\n"
    ),
    "Vocabulary (Class 3)": (
        "CRITICAL: ALL questions MUST be about Vocabulary ONLY — word meanings, synonyms, "
        "antonyms, word usage. Use Class 3 level words. NEVER generate arithmetic or maths questions.\n"
    ),
    "Reading Comprehension (Class 3)": (
        "CRITICAL: ALL questions MUST be about Reading Comprehension ONLY — read a short passage "
        "and answer questions about it. Include the passage in question_text. "
        "NEVER generate arithmetic or maths questions.\n"
    ),
    "Tenses (Class 4)": (
        "CRITICAL: ALL questions MUST be about Tenses ONLY — simple, continuous, and perfect tenses "
        "(past, present, future). NEVER generate arithmetic or maths questions.\n"
    ),
    "Sentence Types (Class 4)": (
        "CRITICAL: ALL questions MUST be about Sentence Types ONLY — declarative, interrogative, "
        "exclamatory, imperative sentences. NEVER generate arithmetic or maths questions.\n"
    ),
    "Conjunctions (Class 4)": (
        "CRITICAL: ALL questions MUST be about Conjunctions ONLY — and, but, or, so, because, "
        "although, while, when. NEVER generate arithmetic or maths questions.\n"
    ),
    "Prepositions (Class 4)": (
        "CRITICAL: ALL questions MUST be about Prepositions ONLY — in, on, at, under, over, "
        "between, behind, beside, through. NEVER generate arithmetic or maths questions.\n"
    ),
    "Adverbs (Class 4)": (
        "CRITICAL: ALL questions MUST be about Adverbs ONLY — words that describe how, when, where "
        "(quickly, slowly, always, here, there). NEVER generate arithmetic or maths questions.\n"
    ),
    "Prefixes and Suffixes (Class 4)": (
        "CRITICAL: ALL questions MUST be about Prefixes and Suffixes ONLY — un-, re-, dis-, pre-, "
        "-ful, -less, -ness, -ly, -ment. NEVER generate arithmetic or maths questions.\n"
    ),
    "Vocabulary (Class 4)": (
        "CRITICAL: ALL questions MUST be about Vocabulary ONLY — word meanings, synonyms, antonyms, "
        "homophones, homonyms, idioms. Use Class 4 level words. NEVER generate arithmetic or maths questions.\n"
    ),
    "Reading Comprehension (Class 4)": (
        "CRITICAL: ALL questions MUST be about Reading Comprehension ONLY — read a passage "
        "and answer questions. Include the passage in question_text. Use Class 4 level text. "
        "NEVER generate arithmetic or maths questions.\n"
    ),
    # ── Class 5 English constraints ──
    "Active and Passive Voice (Class 5)": (
        "SCOPE: Active and passive voice for Class 5. ONLY use simple present, past, and future tense sentences. "
        "NEVER use complex tenses (perfect continuous, past perfect). "
        "Use age-appropriate vocabulary and Indian contexts. "
        "NEVER include maths content or arithmetic questions.\n"
    ),
    "Direct and Indirect Speech (Class 5)": (
        "SCOPE: Direct and indirect (reported) speech for Class 5. "
        "Cover said/told/asked reporting verbs. Change pronouns and tenses correctly. "
        "Use simple and continuous tenses only. NEVER use perfect tenses in reported speech. "
        "Use Indian names and contexts. NEVER include maths content.\n"
    ),
    "Complex Sentences (Class 5)": (
        "SCOPE: Complex sentences with subordinating conjunctions for Class 5. "
        "Use: because, although, when, while, if, since, before, after, until, unless. "
        "NEVER use advanced grammar terms like 'subjunctive' or 'conditional perfect'. "
        "Use age-appropriate vocabulary. NEVER include maths content.\n"
    ),
    "Summary Writing (Class 5)": (
        "SCOPE: Summary writing skills for Class 5. "
        "Include a short passage (50-80 words) and ask to identify main idea or write a summary. "
        "Passages must be age-appropriate with Indian contexts. "
        "NEVER include maths content or arithmetic questions.\n"
    ),
    "Comprehension (Class 5)": (
        "CRITICAL: ALL questions MUST be about Reading Comprehension ONLY — read a passage "
        "and answer factual, inferential, or evaluative questions. "
        "Include the passage in question_text. Use Class 5 level text with Indian contexts. "
        "NEVER generate arithmetic or maths questions.\n"
    ),
    "Synonyms and Antonyms (Class 5)": (
        "SCOPE: Synonyms and antonyms for Class 5. "
        "Use age-appropriate vocabulary (Class 5 level). "
        "Include words commonly found in CBSE Class 5 English textbooks. "
        "NEVER include maths content or arithmetic questions.\n"
    ),
    "Formal Letter Writing (Class 5)": (
        "SCOPE: Formal letter writing for Class 5. "
        "Cover format: sender's address, date, receiver's address, subject line, salutation, body, closing. "
        "Use polite and formal language. Topics should be school or community related. "
        "Use Indian contexts. NEVER include maths content.\n"
    ),
    "Creative Writing (Class 5)": (
        "SCOPE: Creative writing for Class 5 — descriptive paragraphs, short stories, diary entries. "
        "Encourage vivid language, similes, and interesting vocabulary. "
        "Topics should be relatable to Indian Class 5 students. "
        "NEVER include maths content or arithmetic questions.\n"
    ),
    "Clauses (Class 5)": (
        "SCOPE: Main (independent) and subordinate (dependent) clauses for Class 5. "
        "Cover noun clauses, adjective clauses (relative clauses with who/which/that), and adverb clauses. "
        "Use age-appropriate sentences. NEVER use advanced grammar terminology. "
        "Use Indian names and contexts. NEVER include maths content.\n"
    ),
    # ── Science Class 3 constraints ──
    "Plants (Class 3)": (
        "CRITICAL: ALL questions MUST be about Plants ONLY — parts of a plant (root, stem, leaf, flower, fruit), "
        "how plants grow, types of plants, photosynthesis in simple terms. "
        "Use Indian plants: neem, tulsi, mango, banyan, lotus, coconut. "
        "NEVER generate arithmetic, maths, or English grammar questions.\n"
    ),
    "Animals (Class 3)": (
        "CRITICAL: ALL questions MUST be about Animals ONLY — types of animals, habitats, "
        "body coverings (fur, feathers, scales), food habits (herbivore, carnivore, omnivore), movement. "
        "Use Indian animals: peacock, cow, elephant, camel, parrot, cobra. "
        "NEVER generate arithmetic, maths, or English grammar questions.\n"
    ),
    "Food and Nutrition (Class 3)": (
        "CRITICAL: ALL questions MUST be about Food and Nutrition ONLY — food groups "
        "(energy-giving, body-building, protective), balanced diet, sources of food, cooking, preservation. "
        "Use Indian foods: dal, roti, rice, paneer, curd, sabzi, ghee, jaggery. "
        "NEVER generate arithmetic, maths, or English grammar questions.\n"
    ),
    "Shelter (Class 3)": (
        "CRITICAL: ALL questions MUST be about Shelter ONLY — why living things need shelter, "
        "types of houses (kutcha, pucca, tent, houseboat, stilt house), animal shelters (nest, burrow, den, web). "
        "Use Indian contexts: village homes, city flats, houseboats in Kashmir, stilt houses in Assam. "
        "NEVER generate arithmetic, maths, or English grammar questions.\n"
    ),
    "Water (Class 3)": (
        "CRITICAL: ALL questions MUST be about Water ONLY — sources of water (river, well, rain, tap), "
        "uses of water, water cycle (evaporation, condensation, rain), saving water, clean vs dirty water. "
        "Use Indian contexts: monsoon, Ganga, hand pumps, water tankers. "
        "NEVER generate arithmetic, maths, or English grammar questions.\n"
    ),
    "Air (Class 3)": (
        "CRITICAL: ALL questions MUST be about Air ONLY — air is everywhere, properties of air "
        "(takes up space, has weight), composition (oxygen, carbon dioxide, nitrogen), "
        "air pollution, wind and its uses. "
        "Use Indian contexts: kite flying on Sankranti, windmills, factory smoke, vehicle pollution. "
        "NEVER generate arithmetic, maths, or English grammar questions.\n"
    ),
    "Our Body (Class 3)": (
        "CRITICAL: ALL questions MUST be about the Human Body ONLY — major body parts and organs, "
        "sense organs (eyes, ears, nose, tongue, skin), hygiene, healthy habits, food for a healthy body. "
        "Use Indian contexts: yoga, PT period, school nurse, morning assembly exercises. "
        "NEVER generate arithmetic, maths, or English grammar questions.\n"
    ),
    # ── EVS Class 1 topic constraints ──
    "My Family (Class 1)": (
        "SCOPE: Family members for Class 1 EVS. Use mother, father, brother, sister, grandparents. "
        "Keep vocabulary very simple (3-4 letter words preferred). "
        "Use Indian names: Amma, Appa, Dadi, Nani, Raju, Meena. "
        "NEVER use complex family tree terms (uncle, cousin, nephew). "
        "NEVER include maths content, arithmetic, or English grammar questions.\n"
    ),
    "My Body (Class 1)": (
        "SCOPE: Basic body parts for Class 1 EVS — head, eyes, ears, nose, mouth, hands, legs, feet. "
        "Focus on naming parts and simple functions (eyes help us see). "
        "Keep vocabulary very simple. NO internal organs (heart, lungs, brain). "
        "Use Indian contexts: clapping during a rhyme, running in the playground. "
        "NEVER include maths content, arithmetic, or English grammar questions.\n"
    ),
    "Plants Around Us (Class 1)": (
        "SCOPE: Simple plants for Class 1 EVS. Name common plants and trees (neem, tulsi, mango, banyan). "
        "Simple parts only: leaf, flower, stem. NO photosynthesis, NO scientific terms. "
        "Plants need water and sunlight to grow — that is all. "
        "Keep vocabulary very simple. "
        "NEVER include maths content, arithmetic, or English grammar questions.\n"
    ),
    "Animals Around Us (Class 1)": (
        "SCOPE: Common animals for Class 1 EVS — cow, dog, cat, parrot, hen, fish, elephant. "
        "Simple classification: pet, farm, wild animals. Where they live (land, water, sky). "
        "What they eat (grass, grain, fish). NO scientific terms, NO habitat ecology. "
        "Use Indian animals: peacock, cow, parrot, monkey, squirrel. "
        "NEVER include maths content, arithmetic, or English grammar questions.\n"
    ),
    "Food We Eat (Class 1)": (
        "SCOPE: Basic foods for Class 1 EVS — roti, rice, dal, milk, fruits, vegetables. "
        "Food comes from plants or animals. We need food to grow strong. "
        "NO food groups, NO nutrition science, NO calories. Keep it very simple. "
        "Use Indian foods: roti, dal, rice, curd, banana, mango, idli. "
        "NEVER include maths content, arithmetic, or English grammar questions.\n"
    ),
    "Seasons and Weather (Class 1)": (
        "SCOPE: Three main seasons for Class 1 EVS — summer (hot), rainy/monsoon (wet), winter (cold). "
        "Simple weather words: hot, cold, rainy, windy, sunny, cloudy. "
        "Clothes we wear in each season. NO temperature numbers, NO climate science. "
        "Use Indian contexts: monsoon rains, Sankranti kite flying, wearing sweaters in winter. "
        "NEVER include maths content, arithmetic, or English grammar questions.\n"
    ),
    # ── EVS Class 2 topic constraints ──
    "Plants (Class 2)": (
        "CRITICAL: ALL questions MUST be about Plants for Class 2 EVS ONLY — parts of a plant "
        "(root, stem, leaf, flower, fruit, seed), how a seed grows, plants give us food/shade/air. "
        "Use Indian plants: neem, tulsi, mango, banyan, lotus, coconut, marigold. "
        "NO photosynthesis detail, NO scientific terminology. Keep sentences simple. "
        "NEVER generate arithmetic, maths, or English grammar questions.\n"
    ),
    "Animals and Habitats (Class 2)": (
        "CRITICAL: ALL questions MUST be about Animals and their Habitats for Class 2 EVS ONLY — "
        "pet/farm/wild animals, where animals live (forest, water, desert), what they eat, how they move. "
        "Use Indian animals: peacock, cow, camel, elephant, parrot, cobra, monkey. "
        "NO scientific classification, NO food chains. Keep sentences simple. "
        "NEVER generate arithmetic, maths, or English grammar questions.\n"
    ),
    "Food and Nutrition (Class 2)": (
        "CRITICAL: ALL questions MUST be about Food for Class 2 EVS ONLY — "
        "food groups (fruits, vegetables, grains, dairy), plant vs animal food sources, "
        "eating different foods keeps us healthy. "
        "Use Indian foods: dal, roti, rice, curd, paneer, sabzi, jaggery. "
        "NO calorie counting, NO vitamins by name. Keep sentences simple. "
        "NEVER generate arithmetic, maths, or English grammar questions.\n"
    ),
    "Water (Class 2)": (
        "CRITICAL: ALL questions MUST be about Water for Class 2 EVS ONLY — "
        "sources of water (rain, river, well, tap), uses (drinking, cooking, washing, farming), "
        "why we should save water, clean vs dirty water. "
        "Use Indian contexts: hand pump, monsoon, Ganga, water tanker. "
        "NO water cycle detail, NO chemical formulas. Keep sentences simple. "
        "NEVER generate arithmetic, maths, or English grammar questions.\n"
    ),
    "Shelter (Class 2)": (
        "CRITICAL: ALL questions MUST be about Shelter for Class 2 EVS ONLY — "
        "why living things need shelter, types of houses (kutcha, pucca, tent, houseboat), "
        "animal homes (nest, burrow, den, hive, web). "
        "Use Indian contexts: village house, city flat, houseboat in Kashmir, stilt house in Assam. "
        "NO architecture, NO building materials science. Keep sentences simple. "
        "NEVER generate arithmetic, maths, or English grammar questions.\n"
    ),
    "Our Senses (Class 2)": (
        "CRITICAL: ALL questions MUST be about the Five Senses for Class 2 EVS ONLY — "
        "eyes (see), ears (hear), nose (smell), tongue (taste), skin (touch). "
        "Match senses to body parts and everyday experiences. "
        "Use Indian contexts: smelling flowers, tasting jalebi, hearing temple bells. "
        "NO nervous system, NO brain science. Keep sentences simple. "
        "NEVER generate arithmetic, maths, or English grammar questions.\n"
    ),
    # ── Science Class 4 topic constraints ──
    "Living Things (Class 4)": (
        "CRITICAL: ALL questions MUST be about Living Things ONLY — classification of living vs non-living, "
        "characteristics of living things (growth, respiration, reproduction, response to stimuli), "
        "basic intro to plant and animal cells. "
        "Use Indian examples: neem tree, cow, mushroom, stone, bicycle. "
        "Keep answers factual and age-appropriate for Class 4. "
        "NEVER generate maths computation, English grammar, or unrelated science questions.\n"
    ),
    "Human Body (Class 4)": (
        "CRITICAL: ALL questions MUST be about the Human Body for Class 4 ONLY — "
        "digestive system (mouth, food pipe, stomach, small intestine, large intestine), "
        "skeletal system (skull, ribcage, backbone, joints — hinge, ball-and-socket). "
        "Use Indian contexts: eating roti, doing yoga, playing kabaddi. "
        "NO circulatory system, NO nervous system (those are Class 5). "
        "NEVER generate maths computation, English grammar, or unrelated science questions.\n"
    ),
    "States of Matter (Class 4)": (
        "CRITICAL: ALL questions MUST be about States of Matter ONLY — solid, liquid, gas. "
        "Properties (shape, volume), changes of state (melting, freezing, evaporation, condensation, boiling). "
        "Use Indian contexts: ice gola, boiling chai, drying clothes, morning dew. "
        "Keep answers factual and age-appropriate for Class 4. "
        "NEVER generate maths computation, English grammar, or unrelated science questions.\n"
    ),
    "Force and Motion (Class 4)": (
        "CRITICAL: ALL questions MUST be about Force and Motion ONLY — push/pull forces, "
        "types of force (muscular, frictional, gravitational, magnetic), friction on surfaces, gravity. "
        "Use Indian contexts: cricket, bicycle, bullock cart, playground slide. "
        "Keep answers factual and age-appropriate for Class 4. "
        "NEVER generate maths computation, English grammar, or unrelated science questions.\n"
    ),
    "Simple Machines (Class 4)": (
        "CRITICAL: ALL questions MUST be about Simple Machines ONLY — lever, pulley, wheel and axle, "
        "inclined plane, wedge, screw. How they make work easier. "
        "Use Indian contexts: see-saw, well pulley, ramp at railway station, scissors, wheelbarrow. "
        "Keep answers factual and age-appropriate for Class 4. "
        "NEVER generate maths computation, English grammar, or unrelated science questions.\n"
    ),
    "Photosynthesis (Class 4)": (
        "CRITICAL: ALL questions MUST be about Photosynthesis ONLY — how plants make food "
        "using sunlight, water, and carbon dioxide. Role of leaves, chlorophyll, stomata. "
        "Use Indian plants: neem, mango, tulsi, banyan, rice paddy. "
        "Keep explanations simple for Class 4. NO chemical equations, NO complex biochemistry. "
        "NEVER generate maths computation, English grammar, or unrelated science questions.\n"
    ),
    "Animal Adaptation (Class 4)": (
        "CRITICAL: ALL questions MUST be about Animal Adaptation ONLY — how animals adapt "
        "to desert, aquatic, polar, and forest habitats. Body features for survival. "
        "Use Indian animals: camel, fish, frog, eagle, chameleon, yak, cobra. "
        "Keep answers factual and age-appropriate for Class 4. "
        "NEVER generate maths computation, English grammar, or unrelated science questions.\n"
    ),
    # ── Science Class 5 topic constraints ──
    "Circulatory System (Class 5)": (
        "CRITICAL: ALL questions MUST be about the Circulatory System ONLY — "
        "heart (4 chambers), blood vessels (arteries, veins, capillaries), blood flow, "
        "blood carries oxygen and nutrients. "
        "Use Indian contexts: checking pulse, doctor visits, blood donation camp. "
        "Keep answers factual and age-appropriate for Class 5. "
        "NEVER generate maths computation, English grammar, or unrelated science questions.\n"
    ),
    "Respiratory and Nervous System (Class 5)": (
        "CRITICAL: ALL questions MUST be about the Respiratory and Nervous System ONLY — "
        "breathing (nose, windpipe, lungs, oxygen in, CO₂ out), nervous system (brain, spinal cord, nerves), "
        "reflex actions. "
        "Use Indian contexts: pranayam, yoga, sneezing, reflex when touching hot tawa. "
        "Keep answers factual and age-appropriate for Class 5. "
        "NEVER generate maths computation, English grammar, or unrelated science questions.\n"
    ),
    "Reproduction in Plants and Animals (Class 5)": (
        "CRITICAL: ALL questions MUST be about Reproduction ONLY — "
        "parts of a flower (petals, stamens, pistil), pollination (insect, wind), "
        "seed formation, seed dispersal, egg-laying vs live birth in animals. "
        "Use Indian contexts: mango flowering, bees on marigold, hen and eggs. "
        "Keep content age-appropriate for Class 5. NO human reproduction. "
        "NEVER generate maths computation, English grammar, or unrelated science questions.\n"
    ),
    "Physical and Chemical Changes (Class 5)": (
        "CRITICAL: ALL questions MUST be about Physical and Chemical Changes ONLY — "
        "physical (reversible — melting, freezing, dissolving), chemical (irreversible — burning, rusting, cooking). "
        "Use Indian contexts: making paneer, rusting gate, burning wood on Lohri, making curd. "
        "Keep answers factual and age-appropriate for Class 5. "
        "NEVER generate maths computation, English grammar, or unrelated science questions.\n"
    ),
    "Forms of Energy (Class 5)": (
        "CRITICAL: ALL questions MUST be about Forms of Energy ONLY — "
        "heat, light, sound, electrical energy. Energy conversions (electrical to light, kinetic to sound). "
        "Use Indian contexts: solar panel, Diwali diyas, tabla, windmill, pressure cooker. "
        "Keep answers factual and age-appropriate for Class 5. "
        "NEVER generate maths computation, English grammar, or unrelated science questions.\n"
    ),
    "Solar System and Earth (Class 5)": (
        "CRITICAL: ALL questions MUST be about the Solar System and Earth ONLY — "
        "Sun, 8 planets in order, Earth's rotation (day/night), revolution (seasons), moon phases. "
        "Use Indian contexts: Chandrayaan mission, sunrise, Indian seasons, planetarium. "
        "Keep answers factual and age-appropriate for Class 5. "
        "NEVER generate maths computation, English grammar, or unrelated science questions.\n"
    ),
    "Ecosystem and Food Chains (Class 5)": (
        "CRITICAL: ALL questions MUST be about Ecosystems and Food Chains ONLY — "
        "producers, consumers (herbivore, carnivore, omnivore), decomposers, "
        "food chains, food webs, interdependence. "
        "Use Indian contexts: Ranthambore, rice paddy, village pond, forest ecosystem. "
        "Keep answers factual and age-appropriate for Class 5. "
        "NEVER generate maths computation, English grammar, or unrelated science questions.\n"
    ),
    # ── Hindi Class 3 topic constraints ──
    "Varnamala (Class 3)": (
        "CRITICAL: ALL questions MUST be about Hindi Varnamala (alphabet) ONLY — "
        "swar (vowels: अ, आ, इ, ई, उ, ऊ, ए, ऐ, ओ, औ, अं, अः), "
        "vyanjan (consonants: क to ज्ञ), letter recognition, letter sounds. "
        "MUST use Devanagari script. "
        "NEVER generate arithmetic or English grammar questions.\n"
    ),
    "Matras (Class 3)": (
        "CRITICAL: ALL questions MUST be about Hindi Matras (vowel signs) ONLY — "
        "aa ki matra (ा), ee ki matra (ि, ी), oo ki matra (ु, ू), "
        "e ki matra (े), ai ki matra (ै), o ki matra (ो), au ki matra (ौ), "
        "anusvaar (ं), visarg (ः). Forming words with matras. "
        "MUST use Devanagari script. "
        "NEVER generate arithmetic or English grammar questions.\n"
    ),
    "Shabd Rachna (Class 3)": (
        "CRITICAL: ALL questions MUST be about Hindi Shabd Rachna (word formation) ONLY — "
        "prefix (upsarg), suffix (pratyay), compound words (samas), "
        "synonyms (paryayvachi), antonyms (vilom shabd), word building from letters/syllables. "
        "MUST use Devanagari script. "
        "NEVER generate arithmetic or English grammar questions.\n"
    ),
    "Vakya Rachna (Class 3)": (
        "CRITICAL: ALL questions MUST be about Hindi Vakya Rachna (sentence formation) ONLY — "
        "simple sentences, word order in Hindi (subject-object-verb), "
        "punctuation (poorn viram, prashn chinh, vistar chinh), "
        "types of sentences (vidhaan vakya, nishedh vakya, prashn vakya). "
        "MUST use Devanagari script. "
        "NEVER generate arithmetic or English grammar questions.\n"
    ),
    "Kahani Lekhan (Class 3)": (
        "CRITICAL: ALL questions MUST be about Hindi Kahani/Gadyansh (story/passage) ONLY — "
        "reading comprehension of short Hindi passages, answering questions from a passage, "
        "writing short paragraphs or stories, moral of a story, story sequencing. "
        "Use Indian stories: Panchatantra, Birbal, folk tales. "
        "MUST use Devanagari script. "
        "NEVER generate arithmetic or English grammar questions.\n"
    ),
    # ── Computer Science topic constraints ──
    "Parts of Computer (Class 1)": (
        "CRITICAL: ALL questions MUST be about Parts of a Computer ONLY — "
        "monitor, keyboard, mouse, CPU, speaker. Their names and basic functions. "
        "Keep language VERY simple for Class 1. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "Using Mouse and Keyboard (Class 1)": (
        "CRITICAL: ALL questions MUST be about Using Mouse and Keyboard ONLY — "
        "left click, right click, double click, drag, typing letters, space bar, enter key. "
        "Keep language VERY simple for Class 1. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "Desktop and Icons (Class 2)": (
        "CRITICAL: ALL questions MUST be about Desktop and Icons ONLY — "
        "desktop layout, icons, taskbar, start menu, wallpaper, Recycle Bin, opening programs. "
        "Keep language simple for Class 2. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "Basic Typing (Class 2)": (
        "CRITICAL: ALL questions MUST be about Basic Typing ONLY — "
        "home row keys (ASDF JKL), correct posture, finger placement, typing words/sentences. "
        "Keep language simple for Class 2. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "Special Keys (Class 2)": (
        "CRITICAL: ALL questions MUST be about Special Keys ONLY — "
        "Enter, Space, Backspace, Shift, Caps Lock, Tab, Delete, Escape and their functions. "
        "Keep language simple for Class 2. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "MS Paint Basics (Class 3)": (
        "CRITICAL: ALL questions MUST be about MS Paint ONLY — "
        "drawing tools (pencil, brush, fill, eraser), shapes, colour palette, text tool, "
        "save/open drawings. "
        "Keep language appropriate for Class 3. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "Keyboard Shortcuts (Class 3)": (
        "CRITICAL: ALL questions MUST be about Keyboard Shortcuts ONLY — "
        "Ctrl+C (copy), Ctrl+V (paste), Ctrl+X (cut), Ctrl+Z (undo), Ctrl+S (save), "
        "Ctrl+A (select all), Ctrl+P (print), Alt+Tab (switch windows). "
        "Keep language appropriate for Class 3. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "Files and Folders (Class 3)": (
        "CRITICAL: ALL questions MUST be about Files and Folders ONLY — "
        "creating, renaming, deleting, moving files/folders, file extensions, organising files. "
        "Keep language appropriate for Class 3. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "MS Word Basics (Class 4)": (
        "CRITICAL: ALL questions MUST be about MS Word ONLY — "
        "typing text, formatting (bold, italic, underline), font size/colour, alignment, "
        "save/open/print, inserting tables and borders. "
        "Keep language appropriate for Class 4. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "Introduction to Scratch (Class 4)": (
        "CRITICAL: ALL questions MUST be about Scratch programming ONLY — "
        "sprites, stage, script area, motion blocks, looks blocks, events (green flag), "
        "simple loops (repeat), basic animation. "
        "Keep language appropriate for Class 4. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "Internet Safety (Class 4)": (
        "CRITICAL: ALL questions MUST be about Internet Safety ONLY — "
        "strong passwords, personal information protection, safe browsing, "
        "not clicking unknown links, cyberbullying awareness, reporting to trusted adults. "
        "Keep language appropriate for Class 4. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "Scratch Programming (Class 5)": (
        "CRITICAL: ALL questions MUST be about Scratch Programming ONLY — "
        "variables, conditionals (if-then-else), loops (repeat, forever, repeat-until), "
        "broadcasting, cloning, events, game creation, debugging. "
        "Keep language appropriate for Class 5. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "Internet Basics (Class 5)": (
        "CRITICAL: ALL questions MUST be about Internet Basics ONLY — "
        "web browsers, URLs, search engines, email (compose, send, reply, attach), "
        "downloading, bookmarks, tabs. "
        "Keep language appropriate for Class 5. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "MS PowerPoint Basics (Class 5)": (
        "CRITICAL: ALL questions MUST be about MS PowerPoint ONLY — "
        "slides, adding text/images, slide layouts, transitions, basic animations, "
        "slideshow mode, presenting to an audience. "
        "Keep language appropriate for Class 5. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "Digital Citizenship (Class 5)": (
        "CRITICAL: ALL questions MUST be about Digital Citizenship ONLY — "
        "online etiquette, digital footprint, copyright, responsible use of technology, "
        "privacy settings, reporting inappropriate content. "
        "Keep language appropriate for Class 5. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    # ── General Knowledge constraints ──────────────────────────
    "Famous Landmarks (Class 3)": (
        "CRITICAL: ALL questions MUST be about Famous Landmarks ONLY — "
        "Taj Mahal, Great Wall of China, Eiffel Tower, Qutub Minar, India Gate, Red Fort, "
        "Gateway of India, Hawa Mahal, Statue of Unity, and other famous monuments. "
        "Keep language appropriate for Class 3. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "National Symbols (Class 3)": (
        "CRITICAL: ALL questions MUST be about National Symbols of India ONLY — "
        "the Indian flag (tiranga), national emblem (Ashoka pillar), national anthem (Jana Gana Mana), "
        "national animal (Bengal tiger), national bird (peacock), national flower (lotus), national fruit (mango). "
        "Keep language appropriate for Class 3. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "Solar System Basics (Class 3)": (
        "CRITICAL: ALL questions MUST be about the Solar System ONLY — "
        "the Sun, 8 planets in order, Earth, Moon, stars vs planets, day and night, satellites. "
        "Keep language appropriate for Class 3. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "Current Awareness (Class 3)": (
        "CRITICAL: ALL questions MUST be about Current Awareness ONLY — "
        "Indian festivals (Diwali, Holi, Eid, Christmas), seasons of India, "
        "important national days (Republic Day, Independence Day, Children's Day, Teachers' Day). "
        "Keep language appropriate for Class 3. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "Continents and Oceans (Class 4)": (
        "CRITICAL: ALL questions MUST be about Continents and Oceans ONLY — "
        "7 continents (Asia, Africa, North America, South America, Antarctica, Europe, Australia), "
        "5 oceans (Pacific, Atlantic, Indian, Southern, Arctic), major countries. "
        "Keep language appropriate for Class 4. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "Famous Scientists (Class 4)": (
        "CRITICAL: ALL questions MUST be about Famous Scientists ONLY — "
        "Newton (gravity), Edison (light bulb), APJ Abdul Kalam (missiles), C.V. Raman (Raman effect), "
        "Marie Curie (radioactivity), Homi Bhabha, Vikram Sarabhai, Srinivasa Ramanujan. "
        "Keep language appropriate for Class 4. "
        "NEVER generate arithmetic, grammar, or unrelated science questions.\n"
    ),
    "Festivals of India (Class 4)": (
        "CRITICAL: ALL questions MUST be about Indian Festivals ONLY — "
        "Diwali, Holi, Eid, Christmas, Pongal, Baisakhi, Onam, Navratri, Durga Puja, "
        "Guru Nanak Jayanti, and other regional festivals. "
        "Keep language appropriate for Class 4. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "Sports and Games (Class 4)": (
        "CRITICAL: ALL questions MUST be about Sports and Games ONLY — "
        "cricket, hockey, football, Olympics, Sachin Tendulkar, PV Sindhu, Neeraj Chopra, "
        "Mary Kom, kabaddi, and other sports facts. "
        "Keep language appropriate for Class 4. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "Indian Constitution (Class 5)": (
        "CRITICAL: ALL questions MUST be about the Indian Constitution ONLY — "
        "fundamental rights, fundamental duties, the Preamble, Dr B.R. Ambedkar, "
        "republic, Parliament, President, Right to Education. "
        "Keep language appropriate for Class 5. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "World Heritage Sites (Class 5)": (
        "CRITICAL: ALL questions MUST be about World Heritage Sites ONLY — "
        "UNESCO sites in India (Ajanta-Ellora, Konark, Hampi, Kaziranga, Sundarbans), "
        "global heritage sites (Machu Picchu, Great Barrier Reef, Pyramids). "
        "Keep language appropriate for Class 5. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "Space Missions (Class 5)": (
        "CRITICAL: ALL questions MUST be about Space Missions ONLY — "
        "ISRO, Chandrayaan, Mangalyaan, NASA, satellites, Rakesh Sharma, "
        "International Space Station, space exploration achievements. "
        "Keep language appropriate for Class 5. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "Environmental Awareness (Class 5)": (
        "CRITICAL: ALL questions MUST be about Environmental Awareness ONLY — "
        "air/water/soil pollution, conservation, recycling, climate change, "
        "renewable energy, deforestation, waste management. "
        "Keep language appropriate for Class 5. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    # ── Moral Science constraints ──────────────────────────
    "Sharing (Class 1)": (
        "CRITICAL: ALL questions MUST be about Sharing ONLY — "
        "sharing toys, food, books; being generous; how sharing makes others happy. "
        "Use very simple language appropriate for Class 1 (age 6). "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "Honesty (Class 1)": (
        "CRITICAL: ALL questions MUST be about Honesty ONLY — "
        "telling the truth, being fair, returning things that belong to others, "
        "admitting mistakes. Use very simple language appropriate for Class 1 (age 6). "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "Kindness (Class 2)": (
        "CRITICAL: ALL questions MUST be about Kindness ONLY — "
        "being kind to people and animals, helping others, saying kind words, "
        "making others feel better. Keep language appropriate for Class 2. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "Respecting Elders (Class 2)": (
        "CRITICAL: ALL questions MUST be about Respecting Elders ONLY — "
        "good manners, greeting elders, listening when elders speak, "
        "saying please/thank you, following instructions. "
        "Keep language appropriate for Class 2. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "Teamwork (Class 3)": (
        "CRITICAL: ALL questions MUST be about Teamwork ONLY — "
        "working together, cooperation, different roles in a team, "
        "supporting team members, group activities. "
        "Keep language appropriate for Class 3. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "Empathy (Class 3)": (
        "CRITICAL: ALL questions MUST be about Empathy ONLY — "
        "understanding others' feelings, being supportive, putting yourself in "
        "someone else's shoes, caring for others. "
        "Keep language appropriate for Class 3. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "Environmental Care (Class 3)": (
        "CRITICAL: ALL questions MUST be about Environmental Care ONLY — "
        "protecting nature, reduce-reuse-recycle, saving water and electricity, "
        "planting trees, keeping surroundings clean. "
        "Keep language appropriate for Class 3. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "Leadership (Class 4)": (
        "CRITICAL: ALL questions MUST be about Leadership ONLY — "
        "qualities of good leaders, responsibility, decision-making, "
        "inspiring others, being fair and helpful. "
        "Keep language appropriate for Class 4. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "Global Citizenship (Class 5)": (
        "CRITICAL: ALL questions MUST be about Global Citizenship ONLY — "
        "cultural diversity, world peace, human rights, respecting all cultures, "
        "global cooperation, United Nations basics. "
        "Keep language appropriate for Class 5. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "Digital Ethics (Class 5)": (
        "CRITICAL: ALL questions MUST be about Digital Ethics ONLY — "
        "responsible online behaviour, privacy, digital footprint, "
        "cyberbullying, safe internet use, screen time, copyright. "
        "Keep language appropriate for Class 5. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    # ── Health & Physical Education constraints ──────────────────────────
    "Personal Hygiene (Class 1)": (
        "CRITICAL: ALL questions MUST be about Personal Hygiene ONLY — "
        "handwashing, brushing teeth, bathing, wearing clean clothes, trimming nails. "
        "Use very simple language appropriate for Class 1 (age 6). "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "Good Posture (Class 1)": (
        "CRITICAL: ALL questions MUST be about Good Posture ONLY — "
        "sitting straight, standing tall, carrying school bags correctly, "
        "not slouching while reading or writing. "
        "Use very simple language appropriate for Class 1 (age 6). "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "Basic Physical Activities (Class 1)": (
        "CRITICAL: ALL questions MUST be about Basic Physical Activities ONLY — "
        "running, jumping, throwing, catching, hopping, skipping, balancing. "
        "Use very simple language appropriate for Class 1 (age 6). "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "Healthy Eating Habits (Class 2)": (
        "CRITICAL: ALL questions MUST be about Healthy Eating Habits ONLY — "
        "eating fruits and vegetables, drinking water, avoiding junk food, "
        "choosing healthy snacks. Keep language appropriate for Class 2. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "Outdoor Play (Class 2)": (
        "CRITICAL: ALL questions MUST be about Outdoor Play ONLY — "
        "benefits of playing outside, types of outdoor games, "
        "running, cycling, kho-kho, hopscotch. Keep language appropriate for Class 2. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "Basic Stretching (Class 2)": (
        "CRITICAL: ALL questions MUST be about Basic Stretching ONLY — "
        "simple stretches, warming up before exercise, arm stretches, "
        "toe touches, neck rolls, side bends. Keep language appropriate for Class 2. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "Balanced Diet (Class 3)": (
        "CRITICAL: ALL questions MUST be about Balanced Diet ONLY — "
        "food groups (carbohydrates, proteins, fats, vitamins, minerals), "
        "nutrients, Indian thali concept, healthy meals. "
        "Keep language appropriate for Class 3. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "Team Sports Rules (Class 3)": (
        "CRITICAL: ALL questions MUST be about Team Sports Rules ONLY — "
        "rules of cricket, football, kabaddi, kho-kho, fair play, "
        "sportsmanship, different positions and roles. "
        "Keep language appropriate for Class 3. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "Safety at Play (Class 3)": (
        "CRITICAL: ALL questions MUST be about Safety at Play ONLY — "
        "playground safety rules, avoiding injuries, first aid kit awareness, "
        "safe and unsafe behaviours during play. "
        "Keep language appropriate for Class 3. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "First Aid Basics (Class 4)": (
        "CRITICAL: ALL questions MUST be about First Aid Basics ONLY — "
        "treating cuts and burns, bandaging, when to call an adult, "
        "contents of a first aid kit, basic wound care. "
        "Keep language appropriate for Class 4. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "Yoga Introduction (Class 4)": (
        "CRITICAL: ALL questions MUST be about Yoga ONLY — "
        "basic asanas (Tadasana, Vrikshasana, Balasana, Bhujangasana), "
        "breathing exercises (pranayama), benefits of yoga. "
        "Keep language appropriate for Class 4. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "Importance of Sleep (Class 4)": (
        "CRITICAL: ALL questions MUST be about Importance of Sleep ONLY — "
        "how many hours children need, effects of screen time before bed, "
        "good sleep habits, bedtime routines, why sleep matters. "
        "Keep language appropriate for Class 4. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "Fitness and Stamina (Class 5)": (
        "CRITICAL: ALL questions MUST be about Fitness and Stamina ONLY — "
        "exercises for strength and endurance, measuring fitness, "
        "running, push-ups, stamina building, heart health. "
        "Keep language appropriate for Class 5. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "Nutrition Labels Reading (Class 5)": (
        "CRITICAL: ALL questions MUST be about Reading Nutrition Labels ONLY — "
        "reading food labels, understanding calories, protein, fat, sugar, "
        "expiry dates, ingredients, making healthier food choices. "
        "Keep language appropriate for Class 5. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
    "Mental Health Awareness (Class 5)": (
        "CRITICAL: ALL questions MUST be about Mental Health Awareness ONLY — "
        "managing stress, talking about feelings, mindfulness, "
        "coping with difficult emotions, seeking help, self-care. "
        "Keep language appropriate for Class 5. "
        "NEVER generate arithmetic, grammar, or science questions.\n"
    ),
}

REGION_CONTEXT: dict[str, dict[str, str]] = {
    "India": {"currency": "rupees"},
    "UAE": {"currency": "AED"},
}


# ════════════════════════════════════════════════════════════
# H) Validators
# ════════════════════════════════════════════════════════════

_FORBIDDEN_VISUAL_PHRASES = re.compile(
    r"(use the (visual|array|number line|diagram|grid|picture)"
    r"|look at the (array|number line|diagram|grid|picture)"
    r"|shown in the (array|number line|diagram|picture)"
    r"|the (array|number line|diagram) (shows|below)"
    r"|draw an? (array|number line|diagram)"
    r"|using the (array|number line|diagram)"
    r"|observe the (array|number line|diagram|figure)"
    r"|see the (array|number line|diagram))",
    re.IGNORECASE,
)

_ERROR_LANGUAGE = re.compile(
    r"(mistake|error|wrong|incorrect|correct it|find.*(wrong|mistake)"
    r"|is.*(correct|right)\?|spot the|what is wrong)",
    re.IGNORECASE,
)

_REASONING_LANGUAGE = re.compile(
    r"(explain|why|which.*(greater|more|better|easier|faster|closer)"
    r"|compare|create|without calculating|estimate|round"
    r"|how do you know|in your own words|what would happen"
    r"|reasonable|closer to|above or below|bound|upper|lower"
    r"|more than|less than|between|nearest)",
    re.IGNORECASE,
)

_BLANK_MARKER = re.compile(r"(_{2,}|\?{1,}|□|▢|\[ *\])")

# English-specific validation patterns
_GRAMMAR_ERROR_LANGUAGE = re.compile(
    r"(mistake|error|wrong|incorrect|correct\s+(the|it|this)|find.*(wrong|mistake|error)"
    r"|spot the|what is wrong|rewrite.*correct|fix the)",
    re.IGNORECASE,
)

_ENGLISH_REASONING_LANGUAGE = re.compile(
    r"(explain|why|which.*(better|correct|appropriate|suitable)"
    r"|how do you know|in your own words|what would happen"
    r"|give a reason|think about|what if|create|write your own"
    r"|make up|compose|describe|imagine)",
    re.IGNORECASE,
)

_WRONG_ANSWER_RE = re.compile(
    r"(?:\bgot\s+|answer\s+is\s+|=\s*|found.*?(?:sum|answer|total).*?(?:to be|is|as)\s+)(\d{2,})",
    re.IGNORECASE,
)

# Hindi-specific validation patterns
_HINDI_ERROR_LANGUAGE = re.compile(
    r"(गलती|गलत|त्रुटि|सही करो|सही कीजिए|ठीक करो|mistake|error|wrong|incorrect"
    r"|correct\s+(the|it|this)|find.*(wrong|mistake|error)|spot the|what is wrong"
    r"|शुद्ध करो|अशुद्ध)",
    re.IGNORECASE,
)

_HINDI_REASONING_LANGUAGE = re.compile(
    r"(क्यों|कैसे|समझाओ|बताओ|सोचो|कल्पना करो|लिखो|रचना करो|वर्णन करो"
    r"|explain|why|how|think|imagine|write|describe|create|compose"
    r"|अपने शब्दों में|कहानी लिखो|अनुच्छेद लिखो)",
    re.IGNORECASE,
)


def validate_question(q: dict, slot_type: str, subject: str = "Mathematics") -> list[str]:
    """Validate a single generated question against slot constraints."""
    issues: list[str] = []
    fmt = q.get("format", "")
    text = q.get("question_text", "")
    answer = q.get("answer")
    is_english = subject and subject.lower() == "english"
    is_science = subject and subject.lower() in ("science", "computer", "gk", "moral science", "health")
    is_hindi = subject and subject.lower() == "hindi"

    allowed = get_valid_formats(subject).get(slot_type, set())
    if fmt not in allowed:
        issues.append(f"format '{fmt}' not allowed for {slot_type}; expected one of {sorted(allowed)}")

    if not is_english and not is_science and not is_hindi and _FORBIDDEN_VISUAL_PHRASES.search(text):
        issues.append("question_text references visuals/arrays/diagrams that aren't rendered")

    if answer is None or (isinstance(answer, str) and not answer.strip()):
        issues.append("answer is empty")

    if not text or len(text.strip()) < 10:
        issues.append("question_text is too short or missing")

    # ── Science-specific validation ──
    if is_science:
        if slot_type == "error_detection":
            _SCI_ERROR_LANG = re.compile(
                r"(wrong|incorrect|mistake|error|not true|false statement|"
                r"find the (?:error|mistake)|correct the|what is wrong)",
                re.IGNORECASE,
            )
            if not _SCI_ERROR_LANG.search(text):
                issues.append("Science error_detection must present a factual error for student to find/correct")

        if slot_type == "thinking":
            _SCI_REASONING_LANG = re.compile(
                r"(why|how|explain|reason|what would happen|think|predict|"
                r"what if|describe|compare|suggest)",
                re.IGNORECASE,
            )
            if not _SCI_REASONING_LANG.search(text):
                issues.append("Science thinking slot should involve reasoning or explanation")

        if q.get("pictorial_elements"):
            issues.append("pictorial_elements must be empty (no renderer available)")

        return issues

    # ── Hindi-specific validation ──
    if is_hindi:
        if slot_type == "error_detection":
            if not _HINDI_ERROR_LANGUAGE.search(text):
                issues.append("Hindi error_detection must present a spelling/grammar error for student to find/correct")

        if slot_type == "thinking":
            if not _HINDI_REASONING_LANGUAGE.search(text):
                issues.append("Hindi thinking slot should involve reasoning, creativity, or explanation")

        if q.get("pictorial_elements"):
            issues.append("pictorial_elements must be empty (no renderer available)")

        return issues

    # ── English-specific validation ──
    if is_english:
        if slot_type == "error_detection":
            if not _GRAMMAR_ERROR_LANGUAGE.search(text):
                issues.append("English error_detection must present a grammar/spelling error for student to find/correct")

        if slot_type == "thinking":
            if not _ENGLISH_REASONING_LANGUAGE.search(text):
                issues.append("English thinking slot should involve reasoning, creativity, or explanation")

        if slot_type == "representation" and fmt == "complete_sentence":
            if not _BLANK_MARKER.search(text):
                issues.append("complete_sentence format should contain a blank (___, ?, [])")

        if q.get("pictorial_elements"):
            issues.append("pictorial_elements must be empty (no renderer available)")

        return issues

    # ── Maths-specific validation below ──
    if slot_type == "error_detection":
        if not _ERROR_LANGUAGE.search(text):
            issues.append("error_detection must present a wrong answer for student to find/correct")
        # Topic-specific error_detection validation
        _skill = q.get("skill_tag", "")
        _TIME_ERROR_LANG = re.compile(r"(o'clock|:\d{2}|hour|minute|half past|quarter|clock|time|duration|a\.m\.|p\.m\.)", re.IGNORECASE)
        if _skill == "time_error_spot" and not _TIME_ERROR_LANG.search(text):
            issues.append("time error_detection must reference clock/time concepts")

    # Clock reading validation: verify minute hand × 5 = minutes in answer
    _skill = q.get("skill_tag", "")
    if _skill == "clock_reading":
        _MINUTE_HAND_RE = re.compile(r"minute\s+hand\s+(?:is\s+)?(?:on|at|points?\s+(?:to|at))\s+(\d{1,2})", re.IGNORECASE)
        mh_match = _MINUTE_HAND_RE.search(text)
        if mh_match:
            hand_pos = int(mh_match.group(1))
            expected_min = 0 if hand_pos == 12 else hand_pos * 5
            answer_str = str(answer).strip() if answer else ""
            _ANS_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})")
            ans_match = _ANS_TIME_RE.search(answer_str)
            if ans_match:
                ans_min = int(ans_match.group(2))
                if ans_min != expected_min:
                    issues.append(
                        f"clock answer minutes={ans_min} but minute hand on {hand_pos} "
                        f"should give :{expected_min:02d} (hand_pos × 5)"
                    )

    if slot_type == "representation" and fmt == "missing_number":
        if not _BLANK_MARKER.search(text):
            issues.append("missing_number format should contain a blank (___, ?, [])")

    if slot_type == "thinking":
        if not _REASONING_LANGUAGE.search(text):
            issues.append("thinking slot should involve reasoning, not pure computation")

    if q.get("pictorial_elements"):
        issues.append("pictorial_elements must be empty (no renderer available)")

    return issues


def violates_topic_purity(q: dict, profile: dict) -> list[str]:
    """Check if a question violates topic purity constraints."""
    reasons: list[str] = []
    text = (q.get("question_text") or "").lower()

    # Visual disallow
    vt = (q.get("visual_spec") or {}).get("model_id", "").lower()
    for dv in profile.get("disallowed_visual_types", []):
        if vt and vt == dv.lower():
            reasons.append(f"disallowed_visual:{vt}")
            break

    # Keyword disallow
    for kw in profile.get("disallowed_keywords", []):
        if kw.lower() in text:
            reasons.append(f"disallowed_kw:{kw}")
            break

    # Skill tag must exist and be in allowed set
    st = (q.get("skill_tag") or "").strip()
    if not st:
        reasons.append("empty_skill_tag")
    else:
        allowed = set(profile.get("allowed_skill_tags", []))
        if allowed and st not in allowed:
            reasons.append(f"skill_tag_not_allowed:{st}")

    return reasons


def normalize_q_text(q: dict) -> str:
    """Collapse whitespace for duplicate detection."""
    s = (q.get("question_text") or "").strip().lower()
    return " ".join(s.split())


# ════════════════════════════════════════════════════════════
# H-bis) Visual Hydration & Verification
# ════════════════════════════════════════════════════════════

_HYDRATE_ESTIMATION = re.compile(r"closer\s+to|estimat", re.IGNORECASE)
_HYDRATE_ADD_KW = re.compile(
    r"\+|\badd\b|\bsum\b|\btotal\b|\baltogether\b|\bin all\b|\bmore\b|\breceived\b|\bgot\b",
    re.IGNORECASE,
)
_HYDRATE_SUB_KW = re.compile(
    r"\d\s*-\s*\d|\bsubtract|\bleft\b|\bremain|\bdifference\b",
    re.IGNORECASE,
)
_HYDRATE_MISSING = re.compile(r"_{2,}|\?{2,}|□")
_HYDRATE_NUMS_2TO4 = re.compile(r"\b(\d{2,4})\b")


def hydrate_visuals(questions: list[dict], visuals_only: bool = False) -> list[dict]:
    """Deterministic visual hydration: infer representation + visual_spec + visual_model_ref.

    Rules (always active, checked in order):
      C) Blank marker + two integers → NUMBER_LINE (highlight=missing)
      D) 'closer to' / 'estimate' + two integers → NUMBER_LINE (highlight=computed sum)
      A) Two 2-4 digit integers + add/sub keywords → BASE_TEN_REGROUPING
    Fallback: TEXT_ONLY, or deterministic template when visuals_only.
    """
    for q_index, q in enumerate(questions):
        rep = q.get("representation")
        if rep == "TEXT_ONLY" and not visuals_only:
            continue
        spec_id = (q.get("visual_spec") or {}).get("model_id")
        ref = q.get("visual_model_ref")
        if rep == "PICTORIAL_MODEL" and spec_id and ref:
            continue  # already hydrated

        text = q.get("question_text") or q.get("text") or ""
        text_lower = text.lower()
        nums_2to4 = [int(n) for n in _HYDRATE_NUMS_2TO4.findall(text) if 10 <= int(n) <= 9999]

        # Skip all arithmetic visuals for non-arithmetic topics
        _q_skill = q.get("skill_tag", "")
        _is_time_skill = _q_skill in ("clock_reading", "time_word_problem", "calendar_reading", "time_fill_blank", "time_error_spot", "time_thinking")
        if _is_time_skill:
            q["representation"] = "TEXT_ONLY"
            continue

        # ── Gold-G4: Format-based visual hydration for new visual types ──
        _q_format = q.get("format", "")

        # Fractions → PIE_FRACTION
        if _q_format in ("fraction_number",):
            _frac_match = re.search(r"(\d+)\s*/\s*(\d+)", text)
            if _frac_match:
                _num, _den = int(_frac_match.group(1)), int(_frac_match.group(2))
                if 1 <= _den <= 12:
                    q["representation"] = "PICTORIAL_MODEL"
                    q["visual_spec"] = {
                        "model_id": "PIE_FRACTION",
                        "numerator": _num,
                        "denominator": _den,
                    }
                    q["visual_model_ref"] = "PIE_FRACTION"
                    continue

        # Symmetry → GRID_SYMMETRY
        if _q_format in ("symmetry_question", "symmetry_complete"):
            q["representation"] = "PICTORIAL_MODEL"
            q["visual_spec"] = {
                "model_id": "GRID_SYMMETRY",
                "grid_size": 6,
                "filled_cells": [[1, 1], [1, 2], [2, 1], [2, 2], [3, 1]],
                "fold_axis": "vertical",
            }
            q["visual_model_ref"] = "GRID_SYMMETRY"
            continue

        # Money → MONEY_COINS
        if _q_format in ("money_question",):
            _coin_matches = re.findall(r"(?:Rs\.?|₹)\s*(\d+)", text)
            if _coin_matches:
                _coins = [{"value": int(v), "count": 1} for v in _coin_matches[:5]]
                q["representation"] = "PICTORIAL_MODEL"
                q["visual_spec"] = {
                    "model_id": "MONEY_COINS",
                    "coins": _coins,
                }
                q["visual_model_ref"] = "MONEY_COINS"
                continue

        # Pattern → PATTERN_TILES
        if _q_format in ("shape_pattern", "pattern_question", "growing_pattern"):
            q["representation"] = "PICTORIAL_MODEL"
            q["visual_spec"] = {
                "model_id": "PATTERN_TILES",
                "tiles": ["A", "B", "A", "B", "A", "?"],
                "blank_position": 5,
            }
            q["visual_model_ref"] = "PATTERN_TILES"
            continue

        # Place value → ABACUS (only for non-arithmetic place value questions)
        if _q_format in ("place_value", "place_value_question"):
            if len(nums_2to4) >= 1:
                _pv_num = nums_2to4[0]
                q["representation"] = "PICTORIAL_MODEL"
                q["visual_spec"] = {
                    "model_id": "ABACUS",
                    "hundreds": (_pv_num // 100) % 10,
                    "tens": (_pv_num // 10) % 10,
                    "ones": _pv_num % 10,
                }
                q["visual_model_ref"] = "ABACUS"
                continue

        # Rule C: missing number (blank marker + two known values) → NUMBER_LINE
        if _HYDRATE_MISSING.search(text) and len(nums_2to4) >= 2:
            vals = sorted(nums_2to4)
            min_val, max_val = vals[0], vals[-1]
            missing = max_val - min_val if max_val > min_val else min_val
            lo = min(min_val, missing)
            hi = max(max_val, missing)
            q["representation"] = "PICTORIAL_MODEL"
            q["visual_spec"] = {
                "model_id": "NUMBER_LINE",
                "start": max(0, (lo // 50) * 50 - 50),
                "end": (hi // 50 + 1) * 50 + 50,
                "tick_interval": 50,
                "markers": [min_val, missing, max_val],
            }
            q["visual_model_ref"] = "NUMBER_LINE"
            continue

        # Rule D: closer to / estimate → NUMBER_LINE with highlight=computed sum
        if _HYDRATE_ESTIMATION.search(text) and len(nums_2to4) >= 2:
            non_round = [n for n in nums_2to4 if n % 100 != 0]
            if len(non_round) >= 2:
                computed = non_round[0] + non_round[1]
            else:
                computed = nums_2to4[0] + nums_2to4[1]
            ref_hundreds = sorted(set(n for n in nums_2to4 if n % 100 == 0))
            if len(ref_hundreds) >= 2:
                lo_ref, hi_ref = ref_hundreds[0], ref_hundreds[-1]
            else:
                lo_ref = (computed // 100) * 100
                hi_ref = lo_ref + 100
            q["representation"] = "PICTORIAL_MODEL"
            q["visual_spec"] = {
                "model_id": "NUMBER_LINE",
                "start": max(0, lo_ref - 100),
                "end": hi_ref + 100,
                "tick_interval": 50,
                "markers": [lo_ref, computed, hi_ref],
            }
            q["visual_model_ref"] = "NUMBER_LINE"
            continue

        # Rule A/B: two integers + add/sub keywords → BASE_TEN_REGROUPING
        is_add = bool(_HYDRATE_ADD_KW.search(text))
        is_sub = bool(_HYDRATE_SUB_KW.search(text))
        if (is_add or is_sub) and len(nums_2to4) >= 2:
            a, b = nums_2to4[0], nums_2to4[1]
            op = "subtraction" if is_sub and "+" not in text else "addition"
            q["representation"] = "PICTORIAL_MODEL"
            q["visual_spec"] = {
                "model_id": "BASE_TEN_REGROUPING",
                "numbers": [a, b],
                "operation": op,
            }
            q["visual_model_ref"] = "BASE_TEN_REGROUPING"
            continue

        # Fallback
        if visuals_only:
            if len(nums_2to4) >= 2:
                a, b = nums_2to4[0], nums_2to4[1]
            else:
                a, b = CARRY_PAIRS[q_index % len(CARRY_PAIRS)]
                q["question_text"] = f"Write {a} + {b} in column form."
                q["answer"] = str(a + b)
            q["representation"] = "PICTORIAL_MODEL"
            q["visual_spec"] = {
                "model_id": "BASE_TEN_REGROUPING",
                "numbers": [a, b],
                "operation": "addition",
            }
            q["visual_model_ref"] = "BASE_TEN_REGROUPING"
        else:
            q["representation"] = "TEXT_ONLY"

    return questions


def enforce_visuals_only(questions: list[dict], min_ratio: float = 0.8) -> list[dict]:
    """Post-hydration enforcement for visuals_only mode.

    If fewer than min_ratio of questions have representation == PICTORIAL_MODEL,
    replace lowest-index TEXT_ONLY questions with deterministic column-form
    questions using CARRY_PAIRS until the ratio is met.
    """
    total = len(questions)
    if total == 0:
        return questions

    visual_count = sum(1 for q in questions if q.get("representation") == "PICTORIAL_MODEL")
    required = int(total * min_ratio)
    # Round up: if 10 * 0.8 = 8.0, we need 8
    if visual_count >= required:
        logger.info("enforce_visuals_only: %d/%d visual (%.0f%%) — meets %.0f%% threshold",
                     visual_count, total, 100 * visual_count / total, 100 * min_ratio)
        return questions

    pair_idx = 0
    for i, q in enumerate(questions):
        if visual_count >= required:
            break
        if q.get("representation") != "PICTORIAL_MODEL":
            a, b = CARRY_PAIRS[pair_idx % len(CARRY_PAIRS)]
            pair_idx += 1
            logger.warning(
                "enforce_visuals_only: replacing q%d (TEXT_ONLY) with column-form %d+%d",
                q.get("id", i + 1), a, b,
            )
            q["question_text"] = f"Write {a} + {b} in column form."
            q["answer"] = str(a + b)
            q["representation"] = "PICTORIAL_MODEL"
            q["visual_spec"] = {
                "model_id": "BASE_TEN_REGROUPING",
                "numbers": [a, b],
                "operation": "addition",
            }
            q["visual_model_ref"] = "BASE_TEN_REGROUPING"
            visual_count += 1

    logger.info("enforce_visuals_only: final %d/%d visual (%.0f%%)",
                visual_count, total, 100 * visual_count / total)
    return questions


_NUMERIC_ANSWER_RE = re.compile(r"^-?\d+$")


def normalize_estimation_answers(questions: list[dict]) -> None:
    """Recompute estimation correct_answer from question numbers.

    For 'closer to' / 'round to nearest' thinking questions, the answer must
    match a deterministic computation. Fixes LLM hallucinations.
    """
    for q in questions:
        if q.get("slot_type") != "thinking":
            continue
        text = q.get("question_text", "")
        if not _HYDRATE_ESTIMATION.search(text) and "nearest" not in text.lower() and "round" not in text.lower():
            continue

        nums = [int(n) for n in re.findall(r"\b\d{2,}\b", text)]
        non_round = [n for n in nums if n % 10 != 0]
        round_refs = sorted(set(n for n in nums if n % 10 == 0 and n not in non_round))

        if len(non_round) < 2:
            continue
        computed = non_round[0] + non_round[1]

        # "closer to X or Y" pattern
        if round_refs and len(round_refs) >= 2:
            lo, hi = round_refs[0], round_refs[-1]
            closer = lo if abs(computed - lo) <= abs(computed - hi) else hi
            # Fix answer if it's a "closer to" question
            if "closer" in text.lower():
                old = q.get("answer", "")
                q["answer"] = str(closer)
                if str(closer) not in str(old):
                    logger.info("normalize_estimation: fixed answer %r → %s (computed=%d)", old[:60], closer, computed)

        # "round to nearest 100/10" pattern
        if "nearest 100" in text.lower() or "nearest hundred" in text.lower():
            rounded_a = round(non_round[0], -2)
            rounded_b = round(non_round[1], -2)
            estimated_sum = rounded_a + rounded_b
            q["answer"] = str(estimated_sum)

        elif "nearest 10" in text.lower() or "nearest ten" in text.lower():
            rounded_a = round(non_round[0], -1)
            rounded_b = round(non_round[1], -1)
            estimated_sum = rounded_a + rounded_b
            q["answer"] = str(estimated_sum)

        # Fix visual highlight to match estimate (answer), not exact sum
        answer_str = q.get("answer", "").strip()
        spec = q.get("visual_spec")
        if spec and spec.get("model_id") == "NUMBER_LINE" and answer_str.isdigit():
            estimate = int(answer_str)
            markers = spec.get("markers", [])
            if len(markers) >= 3:
                lo, hi = markers[0], markers[-1]
                # Widen range if estimate falls outside current bounds
                if estimate < lo:
                    lo = (estimate // 100) * 100
                if estimate > hi:
                    hi = ((estimate // 100) + 1) * 100
                spec["markers"] = [lo, estimate, hi]
                spec["start"] = max(0, lo - 100)
                spec["end"] = hi + 100
                logger.info("normalize_estimation: highlight set to %d (estimate, was %d exact)",
                            estimate, computed)


def normalize_error_spot_answers(questions: list[dict]) -> None:
    """Ensure error_spot correct_answer is the numeric correct result.

    LLM often returns explanatory text in 'answer'. This extracts the numeric
    value and moves the explanation to 'explanation'.
    """
    for q in questions:
        if q.get("slot_type") != "error_detection":
            continue
        answer = str(q.get("answer", "")).strip()
        if not answer:
            continue

        # Already purely numeric — nothing to do
        if _NUMERIC_ANSWER_RE.match(answer):
            continue

        # Extract numeric correct answer from text
        nums_in_answer = re.findall(r"\b\d{2,}\b", answer)

        # Also try to compute from the question text numbers
        text = q.get("question_text", "")
        text_nums = [int(n) for n in re.findall(r"\b\d{2,}\b", text)]

        numeric_answer = None

        # If the answer text contains a number, use the last one (typically the correct answer)
        if nums_in_answer:
            numeric_answer = nums_in_answer[-1]

        # Fallback: compute from question text (first two numbers are operands,
        # third is typically the wrong answer shown after '=')
        if not numeric_answer and len(text_nums) >= 2:
            a, b = text_nums[0], text_nums[1]
            is_sub = any(kw in text.lower() for kw in ("subtract", "minus", "take away", "difference"))
            if is_sub:
                numeric_answer = str(max(a, b) - min(a, b))
            else:
                numeric_answer = str(a + b)

        if numeric_answer:
            q["explanation"] = answer  # preserve original LLM text as explanation
            q["answer"] = numeric_answer
            logger.info("normalize_error_spot: moved explanation, answer=%s", numeric_answer)
        else:
            logger.warning("normalize_error_spot: could not extract numeric answer from %r", answer[:80])


def enrich_error_spots(questions: list[dict]) -> None:
    """Add student_answer to error_spot visual specs for frontend display."""
    for q in questions:
        if q.get("slot_type") != "error_detection":
            continue

        wrong = q.get("student_wrong_answer")
        if not wrong:
            # Safety net: extract from question text
            m = _WRONG_ANSWER_RE.search(q.get("question_text", ""))
            if m:
                wrong = int(m.group(1))

        if wrong is not None:
            spec = q.get("visual_spec")
            if spec:
                spec["student_answer"] = int(wrong) if not isinstance(wrong, int) else wrong


def normalize_text_answer(answer: str) -> str:
    """Normalize a text answer: strip, lowercase, collapse whitespace, remove trailing punctuation."""
    ans = answer.strip().lower()
    ans = re.sub(r"\s+", " ", ans)
    ans = ans.rstrip(".,;:!?")
    return ans


def normalize_english_answers(questions: list[dict]) -> None:
    """Normalize English answers — clean up whitespace and ensure non-empty."""
    for q in questions:
        answer = q.get("answer")
        if isinstance(answer, str):
            cleaned = answer.strip()
            if cleaned:
                q["answer"] = cleaned
            else:
                logger.warning("normalize_english_answers: empty answer for q%s", q.get("id"))


def grade_student_answer(question: dict, student_answer: str) -> dict:
    """
    Deterministic grading:
    - materialize slots if missing
    - call contract.grade()
    - return structured feedback
    """
    import app.skills.registry as skills_registry

    contract = skills_registry.SKILL_REGISTRY.get(question.get("skill_tag"))
    if not contract:
        return {
            "is_correct": None,
            "expected": None,
            "student": None,
            "place_errors": {},
            "error_type": "no_contract",
        }

    # Ensure slots exist when relevant
    if not question.get("_slots"):
        try:
            question = contract.build_slots(question)
        except Exception as e:
            logger.warning('[slot_engine.grade_student_answer] build_slots failed for skill_tag=%s: %s', question.get('skill_tag'), e, exc_info=True)

    return contract.grade(question, student_answer)


def explain_question(question: dict) -> dict:
    """
    Deterministic explanation dispatcher.
    """
    import app.skills.registry as skills_registry

    contract = skills_registry.SKILL_REGISTRY.get(question.get("skill_tag"))
    if not contract:
        return {"steps": [], "final_answer": None}

    if not question.get("_slots"):
        try:
            question = contract.build_slots(question)
        except Exception as e:
            logger.warning('[slot_engine.explain_question] build_slots failed for skill_tag=%s: %s', question.get('skill_tag'), e, exc_info=True)

    return contract.explain(question)


def recommend_next_step(question: dict, grade_result: dict) -> dict:
    """
    Dispatch adaptive recommendation to contract.
    """
    import app.skills.registry as skills_registry

    contract = skills_registry.SKILL_REGISTRY.get(question.get("skill_tag"))
    if not contract:
        return {
            "next_skill_tag": None,
            "reason": "no_contract",
            "drill_focus": None,
        }

    return contract.recommend_next(grade_result)


def generate_isolation_drill(question: dict, student_answer: str, rng=None):
    import random
    import app.skills.registry as skills_registry

    rng = rng or random.Random()

    contract = skills_registry.SKILL_REGISTRY.get(question.get("skill_tag"))
    if not contract:
        return None

    grade = grade_student_answer(question, student_answer)
    recommendation = contract.recommend_next(grade)

    drill_focus = recommendation.get("drill_focus")
    if not drill_focus:
        return None

    return contract.generate_drill(drill_focus, rng)


def attempt_question(question: dict, student_answer: str) -> dict:
    import app.skills.registry as skills_registry

    grade = grade_student_answer(question, student_answer)
    explanation = explain_question(question)

    contract = skills_registry.SKILL_REGISTRY.get(question.get("skill_tag"))
    if not contract:
        recommendation = {"next_skill_tag": None, "reason": "no_contract", "drill_focus": None}
        return {
            "grade_result": grade,
            "explanation": explanation,
            "recommendation": recommendation,
        }

    recommendation = contract.recommend_next(grade)

    return {
        "grade_result": grade,
        "explanation": explanation,
        "recommendation": recommendation,
    }


def attempt_and_next(payload: dict) -> dict:
    """
    payload keys:
    - question, student_answer
    - mode: "single" or "chain"
    - root_question, attempts, target_streak (for chain)
    """
    import random
    import app.skills.registry as skills_registry

    question = payload.get("question") or {}
    student_answer = str(payload.get("student_answer", ""))
    mode = payload.get("mode", "single")
    target = int(payload.get("target_streak", 3))

    base = attempt_question(question, student_answer)

    # mastery tracking
    student_id = payload.get("student_id")
    mastery = None
    if student_id:
        try:
            from app.services.mastery_store import update_mastery_from_grade
            mastery = update_mastery_from_grade(
                student_id=student_id,
                skill_tag=(question.get("skill_tag") or ""),
                grade=base.get("grade_result") or {},
            ).to_dict()
        except Exception as e:
            logger.error(f"[slot_engine.attempt_and_next] mastery update failed for student={student_id}: {e}", exc_info=True)
            mastery = None

    # default next block (no chaining)
    next_block = {"action": "stop", "streak": 0, "target": target, "reason": "single_mode", "next_question": None}

    if mode == "single":
        # If recommendation has drill_focus, generate 1 drill
    
        c = skills_registry.SKILL_REGISTRY.get(question.get("skill_tag"))
        rec = base.get("recommendation") or {}
        focus = rec.get("drill_focus")
        if c and focus:
            q2 = c.generate_drill(focus, random.Random())
            next_block = {"action": "continue_drill", "streak": 0, "target": target, "reason": "single_drill", "next_question": q2}

    elif mode == "chain":
        root = payload.get("root_question") or {}
        attempts = payload.get("attempts") or []
        next_block = chain_drill_session(root, attempts, target_streak=target)

    return {
        "grade_result": base.get("grade_result") or {},
        "explanation": base.get("explanation"),
        "recommendation": base.get("recommendation") or {},
        "next": next_block,
        "mastery_state": mastery,
    }


def audit_attempt(*, student_id: str | None, worksheet_id: str | None, attempt_id: str | None,
                  grade: str | None, subject: str | None, topic: str | None,
                  question: dict, student_answer: str | None,
                  grade_result: dict | None, explanation: str | None,
                  recommendation: dict | None, drill: dict | None,
                  mastery_before: dict | None, mastery_after: dict | None) -> None:
    from app.services.audit import write_attempt_event

    spec = question.get("visual_spec") or {}
    op = spec.get("operation")

    expected = question.get("correct_answer") or question.get("answer")

    payload = {
        "student_id": student_id,
        "worksheet_id": worksheet_id,
        "attempt_id": attempt_id,
        "question_id": str(question.get("id") or ""),
        "grade": grade,
        "subject": subject,
        "topic": topic,
        "skill_tag": question.get("skill_tag"),
        "operation": op,
        "question": question,
        "student_answer": student_answer,
        "expected_answer": str(expected) if expected is not None else None,
        "is_correct": (grade_result or {}).get("is_correct"),
        "error_type": (grade_result or {}).get("error_type"),
        "place_errors": (grade_result or {}).get("place_errors") or {},
        "recommendation": recommendation,
        "drill": drill,
        "explanation": explanation,
        "mastery_before": mastery_before,
        "mastery_after": mastery_after,
    }

    write_attempt_event(payload)


def chain_drill_session(root_question: dict, attempts: list[dict], target_streak: int = 3, rng=None) -> dict:
    """
    Stateless drill chaining:
    - attempts: [{"question": dict, "student_answer": str}, ...]
    Returns action + next_question if needed.
    """
    import random
    import app.skills.registry as skills_registry

    rng = rng or random.Random()

    contract = skills_registry.SKILL_REGISTRY.get(root_question.get("skill_tag"))
    if not contract:
        return {"action": "stop", "streak": 0, "target": target_streak, "next_question": None, "reason": "no_contract"}

    # Determine drill focus from grading root (or last attempt if you prefer)
    # Use root's grade to set the drill_focus once.
    root_grade = grade_student_answer(root_question, str(root_question.get("answer") or root_question.get("correct_answer") or ""))
    # If root has no answer fields, fallback to using first attempt grading to infer focus.
    recommendation = contract.recommend_next(root_grade)
    drill_focus = recommendation.get("drill_focus")

    # If root recommendation doesn't produce drill_focus, infer from last attempt:
    if not drill_focus and attempts:
        last_q = attempts[-1].get("question") or {}
        last_contract = skills_registry.SKILL_REGISTRY.get(last_q.get("skill_tag")) or contract
        last_grade = grade_student_answer(last_q, str(attempts[-1].get("student_answer", "")))
        rec2 = last_contract.recommend_next(last_grade)
        drill_focus = rec2.get("drill_focus")

    if not drill_focus:
        return {"action": "stop", "streak": 0, "target": target_streak, "next_question": None, "reason": "no_drill_focus"}

    # Compute current consecutive correct streak on attempts
    streak = 0
    for a in reversed(attempts):
        q = a.get("question") or {}
        ans = str(a.get("student_answer", ""))
        res = grade_student_answer(q, ans)
        if res.get("is_correct") is True:
            streak += 1
        else:
            break

    # If streak complete → escalate to full problem
    if streak >= target_streak:
        nextq = contract.generate_drill("reinforce_full_problem", rng)
        return {
            "action": "escalate",
            "streak": streak,
            "target": target_streak,
            "next_question": nextq,
            "reason": "streak_complete",
        }

    # Otherwise continue isolation drill
    nextq = contract.generate_drill(drill_focus, rng)
    return {
        "action": "continue_drill",
        "streak": streak,
        "target": target_streak,
        "next_question": nextq,
        "reason": "need_more_correct",
    }


def verify_visual_contract(questions: list[dict]) -> str:
    """Return a table verifying the visual rendering contract for each question."""
    header = (
        f"{'question_id':<12} | {'representation':<18} | "
        f"{'visual_spec.model_id':<22} | {'visual_model_ref':<22} | renders?"
    )
    sep = "-" * len(header)
    lines = [sep, header, sep]
    for q in questions:
        qid = f"q{q.get('id', '?')}"
        rep = q.get("representation", "MISSING")
        model_id = (q.get("visual_spec") or {}).get("model_id", "MISSING")
        vref = q.get("visual_model_ref", "MISSING")
        renders = (
            "YES"
            if rep == "PICTORIAL_MODEL" and model_id != "MISSING" and vref != "MISSING"
            else "NO"
        )
        lines.append(f"{qid:<12} | {rep:<18} | {model_id:<22} | {vref:<22} | {renders}")
    lines.append(sep)
    return "\n".join(lines)


def enforce_slot_counts(questions: list[dict], slot_plan: list[str], subject: str = "Mathematics") -> list[dict]:
    """Deterministically trim extras / fill gaps so output matches slot_plan exactly.

    - If a slot_type has too many questions: keep only the first N (by position).
    - If a slot_type has too few: synthesize minimal fallback placeholders.
    Mutates nothing; returns a new list.
    """
    formats = get_valid_formats(subject)
    expected_counts = Counter(slot_plan)
    by_slot: dict[str, list[dict]] = {st: [] for st in SLOT_ORDER}
    for q in questions:
        st = q.get("slot_type", "")
        if st in by_slot:
            by_slot[st].append(q)

    result: list[dict] = []
    next_id = max((q.get("id", 0) for q in questions), default=0) + 1

    for st in slot_plan:
        bucket = by_slot[st]
        if bucket:
            result.append(bucket.pop(0))
        else:
            # Synthesize minimal fallback
            result.append({
                "id": next_id,
                "slot_type": st,
                "role": st,
                "skill_tag": st,
                "format": sorted(formats.get(st, {"unknown"}))[0],
                "question_text": f"[Slot fill for {st} question]",
                "pictorial_elements": [],
                "answer": "",
                "difficulty": "medium",
            })
            next_id += 1
            logger.warning("enforce_slot_counts: synthesized fallback for missing %s slot", st)

    # Re-number ids sequentially
    for i, q in enumerate(result):
        q["id"] = i + 1

    trimmed = sum(len(v) for v in by_slot.values())
    if trimmed:
        logger.info("enforce_slot_counts: trimmed %d excess question(s)", trimmed)

    return result


def validate_worksheet_slots(questions: list[dict], q_count: int, expected_plan: list[str] | None = None) -> list[str]:
    """Validate the full worksheet: slot distribution, uniqueness, diversity.

    If expected_plan is provided, validate against that (the actual plan used).
    Otherwise fall back to SLOT_PLANS / proportional computation.
    """
    issues: list[str] = []
    if expected_plan is not None:
        plan = dict(Counter(expected_plan))
    else:
        plan = SLOT_PLANS.get(q_count) or _compute_proportional_plan(q_count)
    actual_counts = Counter(q.get("slot_type", "") for q in questions)

    for slot_type in SLOT_ORDER:
        expected = plan.get(slot_type, 0)
        actual = actual_counts.get(slot_type, 0)
        if actual != expected:
            issues.append(f"slot {slot_type}: expected {expected}, got {actual}")

    if actual_counts.get("error_detection", 0) < 1:
        issues.append("missing mandatory error_detection question")
    if actual_counts.get("thinking", 0) < 1:
        issues.append("missing mandatory thinking question")

    # Track used number pairs to prevent duplicates
    _used_pairs: set[str] = set()
    for i, q in enumerate(questions):
        text = q.get("question_text", "")
        numbers = re.findall(r"\b\d{2,4}\b", text)
        if len(numbers) >= 2:
            pair = f"{numbers[0]}-{numbers[1]}"
            if pair in _used_pairs:
                issues.append(f"q{i+1}: duplicate number pair {pair}")
            _used_pairs.add(pair)
        # Also check all consecutive pairs for broader dedup
        for j in range(len(numbers) - 1):
            pair = f"{numbers[j]}-{numbers[j+1]}"
            if pair in _used_pairs and j > 0:
                issues.append(f"q{i+1}: duplicate number pair {pair}")
            _used_pairs.add(pair)

    for i, q in enumerate(questions):
        text = q.get("question_text", "")
        if _FORBIDDEN_VISUAL_PHRASES.search(text):
            issues.append(f"q{i+1}: references visuals that aren't rendered")

    # Clock/time deduplication — detect duplicate times and time-pairs across ALL questions
    _TIME_RE = re.compile(r"(\d{1,2}:\d{2}|\d{1,2}\s*o['\u2019]?clock|\d{1,2}\s*(?:thirty|fifteen|forty-five|half past|quarter (?:past|to)))", re.IGNORECASE)
    _TIME_SKILLS = ("clock_reading", "time_word_problem", "calendar_reading", "time_fill_blank", "time_error_spot", "time_thinking")
    clock_times: list[str] = []
    time_pairs: set[str] = set()  # track (start, end) pairs — order-independent
    for i, q in enumerate(questions):
        _skill = q.get("skill_tag", "")
        if _skill in _TIME_SKILLS:
            text = q.get("question_text", "")
            times_found = _TIME_RE.findall(text)
            normalized = [t.strip().lower() for t in times_found]
            for t_norm in normalized:
                if t_norm in clock_times:
                    issues.append(f"q{i+1}: duplicate time reference '{t_norm}'")
                clock_times.append(t_norm)
            # For questions with 2+ times, check (start, end) pair duplicates (order-independent)
            if len(normalized) >= 2:
                pair_sorted = tuple(sorted(normalized[:2]))
                pair_key = f"{pair_sorted[0]}|{pair_sorted[1]}"
                if pair_key in time_pairs:
                    issues.append(f"q{i+1}: duplicate time pair ({pair_sorted[0]}, {pair_sorted[1]})")
                time_pairs.add(pair_key)

    app_contexts: list[str] = []
    for q in questions:
        if q.get("slot_type") == "application":
            text_lower = q.get("question_text", "").lower()
            for ctx in CONTEXT_BANK:
                if ctx["item"] in text_lower:
                    app_contexts.append(ctx["item"])
                    break
    context_counts = Counter(app_contexts)
    for ctx_item, count in context_counts.items():
        if count > 1:
            issues.append(f"context '{ctx_item}' used {count} times in application questions")

    return issues


def validate_difficulty_sanity(micro_skill: str, difficulty: str) -> list[str]:
    """Check if difficulty matches micro_skill complexity."""
    issues: list[str] = []
    skill_lower = micro_skill.lower()
    hard_indicators = [
        "borrow" in skill_lower and "zero" in skill_lower,
        "across zero" in skill_lower,
        "multi" in skill_lower and "step" in skill_lower,
        "regroup" in skill_lower and "hundred" in skill_lower,
    ]
    if any(hard_indicators) and difficulty.lower() == "easy":
        issues.append(
            f"micro_skill '{micro_skill}' involves complex operations "
            f"- difficulty should be Medium or Hard, not Easy"
        )
    return issues


def validate_error_uses_backend_numbers(q: dict, chosen_error: dict | None) -> list[str]:
    """Verify error_detection question uses the backend-provided a, b, wrong."""
    if not chosen_error:
        return []
    issues: list[str] = []
    text = q.get("question_text", "")
    err = chosen_error.get("error", {})
    if not err:
        return []
    if str(err["wrong"]) not in text:
        issues.append(f"error_detection must include wrong answer {err['wrong']} in question_text")
    if str(err["a"]) not in text:
        issues.append(f"error_detection must include number {err['a']} in question_text")
    return issues


def validate_hard_difficulty_carry(questions: list[dict], difficulty: str, topic: str = "") -> list[str]:
    """For hard difficulty, at least one application question should involve carry in both ones and tens.
    Only applicable for Addition topic."""
    if difficulty.lower() != "hard":
        return []
    if topic and topic != "Addition (carries)":
        return []  # Skip carry validation for non-addition topics
    issues: list[str] = []
    app_qs = [q for q in questions if q.get("slot_type") == "application"]
    if not app_qs:
        return issues
    has_carry_question = False
    for q in app_qs:
        text = q.get("question_text", "")
        nums = re.findall(r"\d{3}", text)
        if len(nums) >= 2:
            a, b = int(nums[0]), int(nums[1])
            ones_carry = (a % 10) + (b % 10) >= 10
            tens_carry = ((a // 10) % 10) + ((b // 10) % 10) >= 10
            if ones_carry and tens_carry:
                has_carry_question = True
                break
    if not has_carry_question:
        issues.append("hard difficulty should have at least one addition with carry in both ones and tens")
    return issues


# ════════════════════════════════════════════════════════════
# I) Generation Pipeline
# ════════════════════════════════════════════════════════════

def _clean_json(content: str) -> str:
    """Strip markdown fences and handle common LLM JSON issues."""
    content = content.strip()
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()

    # Handle "Extra data" — LLM sometimes returns multiple JSON objects or trailing text
    # Try parsing as-is first; if that fails, extract the first valid JSON object
    try:
        json.loads(content)
        return content
    except json.JSONDecodeError:
        pass

    # Try to extract the first complete JSON object using brace matching
    start = content.find("{")
    if start == -1:
        return content
    depth = 0
    in_string = False
    escape_next = False
    for i, ch in enumerate(content[start:], start):
        if escape_next:
            escape_next = False
            continue
        if ch == "\\":
            escape_next = True
            continue
        if ch == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = content[start:i + 1]
                try:
                    json.loads(candidate)
                    return candidate
                except json.JSONDecodeError:
                    break

    return content


def generate_meta(
    client, grade: str, subject: str, topic: str, difficulty: str, region: str,
) -> dict:
    """Generate worksheet metadata via LLM."""
    user_msg = META_USER_TEMPLATE.format(
        grade=grade, subject=subject, topic=topic, region=region, difficulty=difficulty,
    )
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": META_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.5,
        max_tokens=512,
    )
    content = _clean_json(response.choices[0].message.content or "")
    meta = json.loads(content)

    for key in ("micro_skill", "skill_focus", "learning_objective",
                "parent_tip", "teaching_script"):
        meta.setdefault(key, "")
    meta.setdefault("common_mistakes", [])
    meta["difficulty"] = difficulty.capitalize()
    return meta


def generate_question(
    client,
    grade: str,
    subject: str,
    micro_skill: str,
    slot_type: str,
    difficulty: str,
    avoid_state: list[str],
    region: str,
    language: str = "English",
    slot_instruction: str = "",
    topic: str = "",
) -> dict:
    """Generate a single question via LLM."""
    avoid_str = ", ".join(avoid_state[-20:]) if avoid_state else "none"

    lang_instruction = ""
    if language != "English":
        lang_instruction = f"Write question_text in {language}.\n"

    topic_constraint = _TOPIC_CONSTRAINTS.get(topic, "")

    user_msg = QUESTION_USER_TEMPLATE.format(
        grade=grade,
        subject=subject,
        micro_skill=micro_skill,
        slot_type=slot_type,
        difficulty=difficulty,
        topic_constraint=topic_constraint,
        avoid=avoid_str,
        slot_instruction=slot_instruction,
        language_instruction=lang_instruction,
    )

    _subj_lower = (subject or "").lower()
    if _subj_lower == "english":
        sys_prompt = QUESTION_SYSTEM_ENGLISH
    elif _subj_lower in ("science", "computer", "gk", "moral science", "health"):
        sys_prompt = QUESTION_SYSTEM_SCIENCE
    elif _subj_lower == "hindi":
        sys_prompt = QUESTION_SYSTEM_HINDI
    else:
        sys_prompt = QUESTION_SYSTEM

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.8,
        max_tokens=300,
    )
    content = _clean_json(response.choices[0].message.content or "")
    q = json.loads(content)

    q.setdefault("format", "")
    q.setdefault("question_text", "")
    q.setdefault("pictorial_elements", [])
    q.setdefault("answer", "")
    q["pictorial_elements"] = []

    return q


_CONTEXT_KEYWORDS = [
    "pizza", "cake", "apple", "mango", "banana", "orange", "chocolate",
    "cookie", "pencil", "book", "marble", "toy", "flower", "sweet",
    "sticker", "balloon", "biscuit", "candy", "egg", "rupee",
    "circle", "rectangle", "square", "triangle", "star", "heart",
    "school", "park", "shop", "garden", "kitchen", "library",
]


def _extract_avoid_items(q: dict) -> list[str]:
    """Extract items to add to avoid_state from a generated question."""
    items: list[str] = []
    text = q.get("question_text", "")

    # Track number pairs (legacy)
    nums = re.findall(r"\d{2,}", text)
    if len(nums) >= 2:
        items.append(f"{nums[0]}+{nums[1]}")

    # Track individual numbers for dedup
    all_nums = re.findall(r"\d+", text)
    for n in all_nums:
        items.append(f"num:{n}")

    # Track context items from word problem contexts
    text_lower = text.lower()
    for ctx in CONTEXT_BANK:
        if ctx["item"] in text_lower:
            items.append(ctx["item"])

    # Track broader context keywords (food, shapes, places)
    for kw in _CONTEXT_KEYWORDS:
        if kw in text_lower:
            items.append(f"ctx:{kw}")

    # Track format
    fmt = q.get("format", "")
    if fmt:
        items.append(f"format:{fmt}")

    # Track operation type
    if "×" in text or "multiply" in text_lower or "times" in text_lower:
        items.append("op:multiply")
    if "÷" in text or "divide" in text_lower or "share" in text_lower:
        items.append("op:divide")
    if "half" in text_lower:
        items.append("op:half")
    if "quarter" in text_lower:
        items.append("op:quarter")

    return items


def _regen_question_for_topic(
    client, directive: dict, micro_skill: str,
    grade: str, subject: str, topic: str,
    difficulty: str, region: str, language: str,
    avoid_texts: set[str], max_attempts: int = 4,
) -> dict | None:
    """Token-efficient regen: one question at a time for topic purity."""
    profile = get_topic_profile(topic)
    for _ in range(max_attempts):
        slot_instruction = _build_slot_instruction(
            directive.get("slot_type", "application"), chosen_variant=None, directive=directive,
            topic=topic,
        )
        try:
            q = generate_question(
                client, grade, subject, micro_skill,
                directive.get("slot_type", "application"),
                directive.get("difficulty", difficulty),
                list(avoid_texts)[-20:], region, language,
                slot_instruction=slot_instruction,
                topic=topic,
            )
        except Exception as e:
            logger.warning('[slot_engine._regen_question_for_topic] generate_question failed for topic=%s, slot_type=%s: %s', topic, directive.get('slot_type', 'application'), e, exc_info=True)
            continue

        q["skill_tag"] = directive.get("skill_tag") or q.get("skill_tag") or directive.get("slot_type", "")
        q["slot_type"] = directive.get("slot_type", q.get("slot_type", ""))
        q["role"] = directive.get("role") or directive.get("slot_type", q.get("slot_type", ""))
        q["difficulty"] = directive.get("difficulty", difficulty)
        backfill_format(q, directive)

        hydrate_visuals([q])

        if profile:
            reasons = violates_topic_purity(q, profile)
            if reasons:
                continue

        nt = normalize_q_text(q)
        if nt in avoid_texts:
            continue

        return q
    return None


def backfill_format(q: dict, directive: dict | None = None, subject: str = "Mathematics") -> None:
    """Ensure q['format'] is never missing or blank. Mutates q in place.

    Resolution order:
    1. Existing q['format'] (trimmed)
    2. directive['format_hint']
    3. DEFAULT_FORMAT_BY_SLOT_TYPE[slot_type] (subject-aware)
    Raises ValueError if slot_type is unknown and format is still empty.
    """
    defaults = get_default_format_by_slot(subject)
    fmt = (q.get("format") or "").strip()
    if not fmt:
        fmt = ((directive or {}).get("format_hint") or "").strip()
    if not fmt:
        slot_type = q.get("slot_type") or (directive or {}).get("slot_type") or ""
        fmt = defaults.get(slot_type, "")
        if not fmt:
            raise ValueError(f"backfill_format: unknown slot_type '{slot_type}', cannot assign default format")
    q["format"] = fmt


def _get_mastery_for_topic(child_id: str, topic: str) -> dict | None:
    """Look up mastery state for a child + topic. Returns summary dict or None."""
    try:
        from app.services.mastery_store import get_mastery_store
        store = get_mastery_store()
        states = store.list_student(child_id)
        if not states:
            return None
        # Find the most relevant mastery state for this topic
        # Match by skill_tag prefix from topic profile's allowed_skill_tags
        profile = get_topic_profile(topic)
        if not profile:
            return None
        allowed_tags = set(profile.get("allowed_skill_tags", []))
        relevant = [s for s in states if s.skill_tag in allowed_tags]
        if not relevant:
            return None
        # Aggregate: use worst mastery_level, most recent last_error_type, average streak
        levels = [s.mastery_level for s in relevant]
        level_priority = {"unknown": 0, "learning": 1, "improving": 2, "mastered": 3}
        avg_level = sum(level_priority.get(l, 0) for l in levels) / len(levels)
        if avg_level >= 2.5:
            agg_level = "mastered"
        elif avg_level >= 1.5:
            agg_level = "improving"
        elif avg_level >= 0.5:
            agg_level = "learning"
        else:
            agg_level = "unknown"
        # Find most recent error type
        last_error = None
        for s in sorted(relevant, key=lambda x: x.updated_at, reverse=True):
            if s.last_error_type:
                last_error = s.last_error_type
                break
        avg_streak = sum(s.streak for s in relevant) / len(relevant)
        total_attempts = sum(s.total_attempts for s in relevant)
        return {
            "mastery_level": agg_level,
            "last_error_type": last_error,
            "avg_streak": avg_streak,
            "total_attempts": total_attempts,
        }
    except Exception as e:
        logger.warning("[_get_mastery_for_topic] Failed to fetch mastery: %s", e)
        return None


def adjust_slot_plan_for_mastery(
    plan_directives: list[dict],
    mastery: dict,
) -> list[dict]:
    """Adjust slot plan based on mastery state. Returns modified plan_directives.

    Rules:
    - mastered: boost thinking by 1, reduce recognition by 1
    - learning: boost recognition by 1, reduce thinking to minimum (1)
    - improving / unknown: no change (use default plan)
    """
    slot_counts: dict[str, int] = {}
    for d in plan_directives:
        st = d["slot_type"]
        slot_counts[st] = slot_counts.get(st, 0) + 1

    level = mastery.get("mastery_level", "unknown")
    changed = False

    if level == "mastered" and slot_counts.get("recognition", 0) >= 2:
        # Boost thinking, reduce recognition
        slot_counts["recognition"] -= 1
        slot_counts["thinking"] = slot_counts.get("thinking", 0) + 1
        changed = True
        logger.info("[mastery_adjust] mastered: recognition-1, thinking+1")

    elif level == "learning" and slot_counts.get("thinking", 0) >= 2:
        # Boost recognition, reduce thinking (keep minimum 1)
        slot_counts["thinking"] -= 1
        slot_counts["recognition"] = slot_counts.get("recognition", 0) + 1
        changed = True
        logger.info("[mastery_adjust] learning: thinking-1, recognition+1")

    if not changed:
        return plan_directives

    # Rebuild plan_directives with adjusted counts
    new_directives: list[dict] = []
    # Group existing directives by slot_type to preserve skill_tags and other metadata
    by_type: dict[str, list[dict]] = {}
    for d in plan_directives:
        by_type.setdefault(d["slot_type"], []).append(d)

    for slot_type in SLOT_ORDER:
        target = slot_counts.get(slot_type, 0)
        existing = by_type.get(slot_type, [])
        if target <= len(existing):
            new_directives.extend(existing[:target])
        else:
            # Need more of this type — duplicate last existing or create generic
            new_directives.extend(existing)
            template = existing[-1] if existing else {"slot_type": slot_type}
            for _ in range(target - len(existing)):
                new_directives.append(dict(template))

    return new_directives


# ── Error-type constraint messages for mastery-aware generation ──
_ERROR_TYPE_CONSTRAINTS: dict[str, str] = {
    "carry_tens": "FORCE at least 2 questions that specifically test carrying in the tens column. Use numbers where ones add to 10+.",
    "carry_ones": "FORCE at least 2 questions that specifically test carrying in the ones column.",
    "borrow_tens": "FORCE at least 2 questions that specifically test borrowing from the tens column.",
    "borrow_ones": "FORCE at least 2 questions that specifically test borrowing in the ones column.",
    "place_value_confusion": "Include questions where students must identify place value correctly. Use numbers with 0 in tens or ones.",
    "multiplication_facts": "Focus on multiplication facts the student is struggling with. Include table recall questions.",
    "division_remainder": "Include questions with remainders to test understanding of division completeness.",
    "fraction_equivalence": "Include questions comparing equivalent fractions. Test if student understands 1/2 = 2/4.",
}


def run_slot_pipeline(
    client,
    grade: str,
    subject: str,
    topic: str,
    q_count: int,
    difficulty: str,
    region: str,
    language: str = "English",
    worksheet_plan: list[dict] | None = None,
    constraints: dict | None = None,
    child_id: str | None = None,
) -> tuple[dict, list[dict]]:
    """Full slot-based generation pipeline with controlled variation.

    Returns (meta, questions) where each question dict has:
    id, slot_type, format, question_text, pictorial_elements, answer, difficulty

    Optional worksheet_plan overrides get_slot_plan() with directive-rich slots.
    Optional constraints dict carries carry_required, allow_operations, etc.
    """
    import app.skills.registry as skills_registry

    constraints = constraints or {}
    logger.info(
        "Slot pipeline v7: grade=%s topic=%s q=%d diff=%s plan=%s",
        grade, topic, q_count, difficulty,
        "custom" if worksheet_plan else "default",
    )

    # 1. Generate meta
    meta = generate_meta(client, grade, subject, topic, difficulty, region)
    micro_skill = meta.get("micro_skill", topic)
    logger.info("Meta: micro_skill=%s", micro_skill)

    # Difficulty sanity check
    diff_issues = validate_difficulty_sanity(micro_skill, difficulty)
    if diff_issues and difficulty.lower() == "easy":
        logger.warning("Bumping difficulty easy->medium: %s", diff_issues)
        difficulty = "medium"
        meta["difficulty"] = "Medium"

    # 2. Get slot plan (plan directives override simple slot_plan)
    _topic_profile = get_topic_profile(topic)
    # Normalize topic to canonical key so downstream comparisons match
    if _topic_profile:
        for _canon_key, _canon_prof in TOPIC_PROFILES.items():
            if _canon_prof is _topic_profile:
                topic = _canon_key
                break
        logger.info("Canonical topic resolved: %s", topic)
    if worksheet_plan:
        plan_directives = list(worksheet_plan)
        if _topic_profile:
            plan_directives = _apply_topic_profile(plan_directives, _topic_profile)
        slot_plan = [d["slot_type"] for d in plan_directives]
    else:
        if _topic_profile:
            plan_directives = build_worksheet_plan(q_count, topic=topic)
        else:
            plan_directives = [{"slot_type": st} for st in get_slot_plan(q_count)]
        slot_plan = [d["slot_type"] for d in plan_directives]
    logger.info("Slot plan (%d): %s", len(slot_plan), dict(Counter(slot_plan)))

    # 2b. Mastery-aware slot plan adjustment (Gold-G2)
    mastery_info = None
    mastery_constraint = None
    if child_id:
        mastery_info = _get_mastery_for_topic(child_id, topic)
        if mastery_info:
            logger.info(
                "Mastery for child=%s topic=%s: level=%s error=%s streak=%.1f attempts=%d",
                child_id, topic, mastery_info["mastery_level"],
                mastery_info.get("last_error_type"), mastery_info["avg_streak"],
                mastery_info["total_attempts"],
            )
            plan_directives = adjust_slot_plan_for_mastery(plan_directives, mastery_info)
            slot_plan = [d["slot_type"] for d in plan_directives]
            logger.info("Adjusted slot plan (%d): %s", len(slot_plan), dict(Counter(slot_plan)))

            # Build mastery constraint for instruction builder
            error_type = mastery_info.get("last_error_type")
            if error_type and error_type in _ERROR_TYPE_CONSTRAINTS:
                mastery_constraint = _ERROR_TYPE_CONSTRAINTS[error_type]
                logger.info("Mastery constraint active: %s", error_type)
        else:
            logger.info("No mastery data for child=%s topic=%s, using default plan", child_id, topic)

    # Store mastery info in meta for API response
    if mastery_info:
        meta["mastery_snapshot"] = mastery_info

    # 3. Load history and build avoid state
    history_avoid = get_avoid_state()
    history_count = len(history_avoid.get("used_contexts", []))

    # 4. Create seeded RNG for variant selection
    seed = _make_seed(grade, topic, q_count, history_count)
    rng = random.Random(seed)
    logger.info("Variation seed: %d (history_count=%d)", seed, history_count)

    # 5. Pre-pick variants for each slot occurrence
    chosen_variants: list[dict | None] = []
    used_contexts_this_ws: list[str] = []
    used_error_ids_this_ws: list[str] = []
    used_thinking_styles_this_ws: list[str] = []

    for i, slot_type in enumerate(slot_plan):
        directive = plan_directives[i]
        _skill_tag = directive.get("skill_tag", "")

        # Contract-owned variant injection (generic)
        _contract = skills_registry.SKILL_REGISTRY.get(_skill_tag)
        if _contract:
            variant = _contract.build_variant(rng, directive)
            if variant:
                chosen_variants.append(variant)
                continue

        if slot_type == "application":
            # Avoid both cross-worksheet and within-worksheet repeats
            avoid_ctx = history_avoid["used_contexts"] + used_contexts_this_ws
            ctx = pick_context(rng, avoid_ctx)
            name = pick_name(rng, region)
            used_contexts_this_ws.append(ctx["item"])
            variant = {"context": ctx, "name": name}
            if directive.get("carry_required"):
                ops = directive.get("allow_operations", ["addition", "subtraction"])
                op = rng.choice(ops)
                a, b = make_carry_pair(rng, op)
                variant["carry_pair"] = (a, b)
                variant["operation"] = op
            chosen_variants.append(variant)

        elif slot_type == "error_detection":
            # Only use addition-specific error pool for addition/subtraction topics
            _ARITHMETIC_TOPICS = {"Addition (carries)", "Subtraction (borrowing)", "Addition and subtraction (3-digit)"}
            if topic in _ARITHMETIC_TOPICS:
                avoid_err = history_avoid["used_error_ids"] + used_error_ids_this_ws
                err = pick_error(rng, avoid_err)
                used_error_ids_this_ws.append(err["id"])
                chosen_variants.append({"error": err})
            else:
                # For other topics, let LLM generate topic-specific error questions
                chosen_variants.append(None)

        elif slot_type == "thinking":
            # Only use estimation-based thinking for arithmetic topics
            _THINKING_VARIANT_TOPICS = {
                "Addition (carries)", "Subtraction (borrowing)",
                "Addition and subtraction (3-digit)",
                "Multiplication (tables 2-10)", "Division basics",
                "Numbers up to 10000",
            }
            if topic in _THINKING_VARIANT_TOPICS:
                avoid_styles = history_avoid["used_thinking_styles"] + used_thinking_styles_this_ws
                style = pick_thinking_style(rng, avoid_styles)
                used_thinking_styles_this_ws.append(style["style"])
                chosen_variants.append({"style": style})
            else:
                # For Time, Money, Symmetry, Patterns, Fractions — multi-step thinking
                chosen_variants.append({"style": {
                    "style": "multi_step",
                    "instruction": "Multi-step reasoning: solve a problem with 2-3 steps, showing your reasoning.",
                }})

        elif slot_type == "recognition" and directive.get("carry_required"):
            # Deterministic carry pair for non-addition (subtraction etc.)
            ops = directive.get("allow_operations", ["addition", "subtraction"])
            op = rng.choice(ops)
            a, b = make_carry_pair(rng, op)
            chosen_variants.append({"carry_pair": (a, b), "operation": op})

        else:
            chosen_variants.append(None)

    # 6. Generate each question with variant-driven instructions
    questions: list[dict] = []
    avoid_state: list[str] = []
    max_attempts = 3
    _question_warnings: list[str] = []

    for i, slot_type in enumerate(slot_plan):
        directive = plan_directives[i]
        q_difficulty = get_question_difficulty(slot_type, difficulty)
        variant = chosen_variants[i]
        slot_instruction = _build_slot_instruction(slot_type, variant, directive=directive, topic=topic)
        # Inject mastery constraint for targeted practice
        if mastery_constraint and slot_type in ("recognition", "application", "representation"):
            slot_instruction += f"\n\nMASTERY FOCUS: {mastery_constraint}"

        generated = False
        for attempt in range(max_attempts):
            try:
                q = generate_question(
                    client, grade, subject, micro_skill,
                    slot_type, q_difficulty, avoid_state, region, language,
                    slot_instruction=slot_instruction,
                    topic=topic,
                )

                # Backfill format BEFORE validation so validators never see ""
                backfill_format(q, {"slot_type": slot_type, **directive}, subject=subject)

                # Set skill_tag early so validators can use it
                q["skill_tag"] = directive.get("skill_tag") or q.get("skill_tag") or slot_type

                issues = validate_question(q, slot_type, subject=subject)

                # Extra check: error_detection must use backend-provided numbers (arithmetic only)
                _q_skill = q.get("skill_tag", "")
                if slot_type == "error_detection" and variant and _q_skill not in (
                    "time_error_spot", "money_error_spot", "symmetry_error_spot", "pattern_error_spot",
                ) and not (subject and subject.lower() == "english"):
                    err_issues = validate_error_uses_backend_numbers(q, variant)
                    issues.extend(err_issues)

                if issues and attempt < max_attempts - 1:
                    logger.warning(
                        "Q%d/%d attempt %d issues: %s - retrying",
                        i + 1, len(slot_plan), attempt + 1, issues,
                    )
                    avoid_state.append(f"rejected:{q.get('format','')}")
                    continue

                if issues:
                    logger.warning(
                        "Q%d/%d still has issues after %d attempts: %s - using best effort",
                        i + 1, len(slot_plan), max_attempts, issues,
                    )
                    _question_warnings.extend(f"q{i+1}: {iss}" for iss in issues)

                q["id"] = i + 1
                q["slot_type"] = slot_type
                q["role"] = directive.get("role") or slot_type
                q["difficulty"] = q_difficulty
                q["skill_tag"] = directive.get("skill_tag") or q.get("skill_tag") or slot_type

                # Preserve student_wrong_answer for error_spot enrichment
                if slot_type == "error_detection" and variant and variant.get("error"):
                    q["student_wrong_answer"] = variant["error"]["wrong"]

                questions.append(q)

                avoid_state.extend(_extract_avoid_items(q))
                generated = True
                break

            except (json.JSONDecodeError, Exception) as exc:
                logger.error("Q%d/%d attempt %d error: %s", i + 1, len(slot_plan), attempt + 1, exc)

        if not generated:
            _fallback_formats = get_valid_formats(subject)
            questions.append({
                "id": i + 1,
                "slot_type": slot_type,
                "role": directive.get("role") or slot_type,
                "skill_tag": directive.get("skill_tag") or slot_type,
                "format": sorted(_fallback_formats.get(slot_type, {"unknown"}))[0],
                "question_text": f"[Generation failed for {slot_type} question]",
                "pictorial_elements": [],
                "answer": "",
                "difficulty": q_difficulty,
            })

        logger.info(
            "Q%d/%d: %s / %s",
            i + 1, len(slot_plan), slot_type, questions[-1].get("format", "?"),
        )

    # 7. Post-generation repair pass
    questions = _repair_pass(
        client, grade, subject, micro_skill, difficulty, region, language,
        questions, slot_plan, rng, history_avoid,
        used_contexts_this_ws, used_error_ids_this_ws, used_thinking_styles_this_ws,
        topic=topic,
    )

    # 7a. Normalize answers (deterministic, no LLM)
    _is_english = subject and subject.lower() == "english"
    _is_science = subject and subject.lower() in ("science", "computer", "gk", "moral science", "health")
    _is_hindi = subject and subject.lower() == "hindi"
    _is_text_only = _is_english or _is_science or _is_hindi
    if _is_text_only:
        normalize_english_answers(questions)  # reuse text normalizer for Science too
    else:
        normalize_estimation_answers(questions)
        normalize_error_spot_answers(questions)

    # 7b. Enforce slot counts — trim extras, fill gaps
    questions = enforce_slot_counts(questions, slot_plan, subject=subject)

    # 8. Validate whole worksheet (against the actual plan, not SLOT_PLANS)
    ws_issues = validate_worksheet_slots(questions, q_count, expected_plan=slot_plan)
    if ws_issues:
        logger.warning("Worksheet-level issues: %s", ws_issues)

    carry_issues: list[str] | None = None
    if not _is_text_only:
        carry_issues = validate_hard_difficulty_carry(questions, difficulty, topic=topic)
        if carry_issues:
            logger.warning("Hard-difficulty carry issues: %s", carry_issues)

    # 8b. Hydrate visuals (deterministic, no LLM) — skip for English/Science (text-only)
    if not _is_text_only:
        questions = hydrate_visuals(questions)
    else:
        for q in questions:
            q["representation"] = "TEXT_ONLY"

    # 8d. Enrich error_spot questions with student_answer
    enrich_error_spots(questions)

    logger.info("Visual contract:\n%s", verify_visual_contract(questions))

    # DEBUG: prove hydrated fields survive to final payload (remove after verification)
    for _q in questions:
        if _q.get("representation") == "PICTORIAL_MODEL":
            logger.info(
                "VISUAL_DEBUG q%s: representation=%s model_id=%s visual_model_ref=%s",
                _q.get("id"), _q.get("representation"),
                (_q.get("visual_spec") or {}).get("model_id"),
                _q.get("visual_model_ref"),
            )

    # 8d-post. Contract slot materialization
    for i, q in enumerate(questions):
        _c = skills_registry.SKILL_REGISTRY.get(q.get("skill_tag"))
        if _c:
            q = _c.build_slots(q)
            questions[i] = q

    # 8e-pre. Skill contract validation hook (repair → revalidate → regen)

    for i, q in enumerate(questions):
        contract = skills_registry.SKILL_REGISTRY.get(q.get("skill_tag"))
        if contract:
            c_issues = contract.validate(q)
            if c_issues:
                logger.warning("Contract q%d (%s): %s — repairing", i + 1, q.get("skill_tag"), c_issues)
                q = contract.repair(q, rng)
                q = hydrate_visuals([q])[0]
                if contract.validate(q):
                    logger.warning("Contract q%d still invalid after repair — regenerating", i + 1)
                    d = plan_directives[i] if i < len(plan_directives) else {}
                    newq = _regen_question_for_topic(
                        client=client,
                        directive=d,
                        micro_skill=micro_skill,
                        grade=grade,
                        subject=subject,
                        topic=topic,
                        difficulty=difficulty,
                        region=region,
                        language=language,
                        avoid_texts=set(),
                        max_attempts=3,
                    )
                    if newq:
                        newq["id"] = i + 1
                        newq["slot_type"] = d.get("slot_type", newq.get("slot_type", ""))
                        newq["role"] = d.get("role") or d.get("slot_type", newq.get("slot_type", ""))
                        newq["skill_tag"] = d.get("skill_tag") or newq.get("skill_tag") or d.get("slot_type", "")
                        q = newq
                questions[i] = q

    # 8e. Topic purity enforcement + duplicate removal
    seen_texts: set[str] = set()
    for idx2, q in enumerate(questions):
        reasons: list[str] = []
        if _topic_profile:
            reasons.extend(violates_topic_purity(q, _topic_profile))
        nt = normalize_q_text(q)
        if nt in seen_texts:
            reasons.append("duplicate")
        if reasons:
            logger.warning("Purity/dedup q%d: %s — regenerating", idx2 + 1, reasons)
            d = plan_directives[idx2] if idx2 < len(plan_directives) else {}
            new_q = _regen_question_for_topic(
                client, d, micro_skill, grade, subject, topic,
                difficulty, region, language, seen_texts,
            )
            if new_q:
                new_q["id"] = idx2 + 1
                new_q["slot_type"] = d.get("slot_type", new_q.get("slot_type", ""))
                new_q["role"] = d.get("role") or d.get("slot_type", new_q.get("slot_type", ""))
                new_q["skill_tag"] = d.get("skill_tag") or new_q.get("skill_tag") or d.get("slot_type", "")
                questions[idx2] = new_q
                seen_texts.add(normalize_q_text(new_q))
            else:
                logger.warning("Regen failed for q%d, keeping original", idx2 + 1)
                # Ensure skill_tag is set even on failed regen
                if not q.get("skill_tag"):
                    q["skill_tag"] = d.get("skill_tag") or d.get("slot_type", "")
                seen_texts.add(nt)
        else:
            seen_texts.add(nt)

    # 9. Update history
    record = build_worksheet_record(
        grade=grade,
        topic=topic,
        questions=questions,
        used_contexts=used_contexts_this_ws,
        used_error_ids=used_error_ids_this_ws,
        used_thinking_styles=used_thinking_styles_this_ws,
    )
    update_history(record)

    meta["grade"] = grade
    meta["subject"] = subject
    meta["topic"] = topic

    # Collect all validation warnings for best-effort response
    _ws_warnings = (ws_issues or []) + (carry_issues or [])
    meta["_warnings"] = {
        "question_level": _question_warnings,
        "worksheet_level": _ws_warnings,
    }

    logger.info("Slot pipeline complete: %d questions", len(questions))
    return meta, questions


def _repair_pass(
    client, grade, subject, micro_skill, difficulty, region, language,
    questions, slot_plan, rng, history_avoid,
    used_contexts, used_error_ids, used_thinking_styles,
    topic: str = "",
) -> list[dict]:
    """Post-generation repair: fix critical constraint violations by re-generating specific questions."""
    for i, q in enumerate(questions):
        slot_type = slot_plan[i] if i < len(slot_plan) else q.get("slot_type", "")
        text = q.get("question_text", "")

        # Repair 1: error_detection must contain actual wrong number
        if slot_type == "error_detection" and "[Generation failed" not in text:
            # Find the chosen error for this slot
            err_variants = [cv for j, cv in enumerate(
                [None] * len(slot_plan)) if slot_plan[j] == "error_detection"]
            # Just check if there are numbers in the question
            nums = re.findall(r"\d{3}", text)
            if len(nums) < 2:
                logger.info("Repair: error_detection Q%d missing numbers, re-generating", i + 1)
                new_err = pick_error(rng, history_avoid["used_error_ids"] + used_error_ids)
                variant = {"error": new_err}
                instr = _build_slot_instruction("error_detection", variant)
                q_diff = get_question_difficulty("error_detection", difficulty)
                try:
                    new_q = generate_question(
                        client, grade, subject, micro_skill,
                        "error_detection", q_diff, [], region, language,
                        slot_instruction=instr,
                        topic=topic,
                    )
                    new_q["id"] = i + 1
                    new_q["slot_type"] = "error_detection"
                    new_q["difficulty"] = q_diff
                    questions[i] = new_q
                    used_error_ids.append(new_err["id"])
                except Exception as exc:
                    logger.error("Repair failed for Q%d: %s", i + 1, exc)

        # Repair 2: thinking must have reasoning language
        if slot_type == "thinking" and "[Generation failed" not in text:
            if not _REASONING_LANGUAGE.search(text):
                logger.info("Repair: thinking Q%d lacks reasoning, re-generating", i + 1)
                new_style = pick_thinking_style(rng, history_avoid["used_thinking_styles"] + used_thinking_styles)
                variant = {"style": new_style}
                instr = _build_slot_instruction("thinking", variant)
                q_diff = get_question_difficulty("thinking", difficulty)
                try:
                    new_q = generate_question(
                        client, grade, subject, micro_skill,
                        "thinking", q_diff, [], region, language,
                        slot_instruction=instr,
                        topic=topic,
                    )
                    new_q["id"] = i + 1
                    new_q["slot_type"] = "thinking"
                    new_q["difficulty"] = q_diff
                    questions[i] = new_q
                    used_thinking_styles.append(new_style["style"])
                except Exception as exc:
                    logger.error("Repair failed for Q%d: %s", i + 1, exc)

    return questions
