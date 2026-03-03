"""Mapping from worksheet format/role to NCERT question type taxonomy.

The 12 NCERT question types:
  computation, word_problem, fill_in_the_blank, mcq, true_false,
  match_the_following, short_answer, activity, pattern_recognition,
  error_detection, picture_based, reasoning
"""

from __future__ import annotations

# Format (from slot engine) → NCERT question type
FORMAT_TO_NCERT_TYPE: dict[str, str] = {
    # Computation formats
    "column_setup": "computation",
    "vertical_sum": "computation",
    "vertical_sub": "computation",
    "horizontal_equation": "computation",
    # Word problem
    "word_problem": "word_problem",
    # Fill-in-the-blank formats
    "fill_blank": "fill_in_the_blank",
    "missing_number": "fill_in_the_blank",
    "place_value": "fill_in_the_blank",
    # MCQ formats
    "mcq_3": "mcq",
    "mcq_4": "mcq",
    # True/False
    "true_false": "true_false",
    # Match
    "match_columns": "match_the_following",
    # Short answer
    "short_answer": "short_answer",
    "simple_identify": "short_answer",
    # Pattern / sequence
    "sequence_question": "pattern_recognition",
    "growing_pattern": "pattern_recognition",
    # Error detection
    "error_spot": "error_detection",
    # Reasoning / thinking
    "thinking": "reasoning",
    "multi_step": "reasoning",
    # Estimation
    "estimation": "reasoning",
}

# Pedagogical role → NCERT question type (fallback when format yields generic result)
ROLE_TO_NCERT_TYPE: dict[str, str] = {
    "recognition": "short_answer",
    "application": "word_problem",
    "representation": "fill_in_the_blank",
    "error_detection": "error_detection",
    "thinking": "reasoning",
}

# Canonical set of valid NCERT question types
NCERT_QUESTION_TYPES: set[str] = {
    "computation",
    "word_problem",
    "fill_in_the_blank",
    "mcq",
    "true_false",
    "match_the_following",
    "short_answer",
    "activity",
    "pattern_recognition",
    "error_detection",
    "picture_based",
    "reasoning",
}
