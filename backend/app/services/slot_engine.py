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
    if subject and subject.lower() == "science":
        return VALID_FORMATS_SCIENCE
    if subject and subject.lower() == "hindi":
        return VALID_FORMATS_HINDI
    return VALID_FORMATS


def get_default_format_by_slot(subject: str = "Mathematics") -> dict[str, str]:
    """Return the DEFAULT_FORMAT_BY_SLOT_TYPE dict for the given subject."""
    if subject and subject.lower() == "english":
        return DEFAULT_FORMAT_BY_SLOT_TYPE_ENGLISH
    if subject and subject.lower() == "science":
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
    # ── English Language skill tags ──────────────────────────
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
    # ── English Language Learning Objectives ──
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
    # ── English Language Context Banks ──
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
    # ════════════════════════════════════════════════════════════
    # English Language Topics (22 topics: 6 Class 2, 8 Class 3, 8 Class 4)
    # ════════════════════════════════════════════════════════════
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
    # ── English Language aliases ──
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

    # ── English Language instruction builders ──

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
        tag for tag in _SKILL_TAG_TO_SLOT if tag.startswith("c2_") or tag.startswith("c4_") or tag.startswith("eng_") or tag.startswith("sci_") or tag.startswith("hin_")
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
    # ── English Language topic constraints ──
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
    is_science = subject and subject.lower() == "science"
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
    elif _subj_lower == "science":
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
    _is_science = subject and subject.lower() == "science"
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
