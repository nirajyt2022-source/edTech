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
                {"skill_tag": "subtraction_word_problem", "count": 2},
                {"skill_tag": "missing_number", "count": 1},
                {"skill_tag": "addition_error_spot", "count": 1},
                {"skill_tag": "subtraction_error_spot", "count": 1},
            ],
            15: [
                {"skill_tag": "column_add_with_carry", "count": 3},
                {"skill_tag": "column_sub_with_borrow", "count": 3},
                {"skill_tag": "addition_word_problem", "count": 2},
                {"skill_tag": "subtraction_word_problem", "count": 3},
                {"skill_tag": "missing_number", "count": 2},
                {"skill_tag": "addition_error_spot", "count": 1},
                {"skill_tag": "subtraction_error_spot", "count": 1},
            ],
            20: [
                {"skill_tag": "column_add_with_carry", "count": 4},
                {"skill_tag": "column_sub_with_borrow", "count": 4},
                {"skill_tag": "addition_word_problem", "count": 2},
                {"skill_tag": "subtraction_word_problem", "count": 4},
                {"skill_tag": "missing_number", "count": 2},
                {"skill_tag": "addition_error_spot", "count": 2},
                {"skill_tag": "subtraction_error_spot", "count": 2},
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
    """Override directives with topic-specific constraints."""
    skills = profile["allowed_skill_tags"]
    allowed_skills = set(skills)
    slot_types = profile.get("allowed_slot_types", SLOT_ORDER)
    allowed_slots = set(slot_types)
    out = []
    for i, d in enumerate(directives):
        nd = dict(d)
        if nd.get("skill_tag", "") not in allowed_skills:
            nd["skill_tag"] = skills[i % len(skills)]
        if nd.get("slot_type", "") not in allowed_slots:
            nd["slot_type"] = slot_types[i % len(slot_types)]
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
    """Pick a context from CONTEXT_BANK, avoiding recently used ones."""
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

    scaled = []
    assigned = 0
    for i, item in enumerate(recipe):
        if i == len(recipe) - 1:
            count = target - assigned
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
) -> str:
    """Build backend-chosen specific instructions for a slot question.

    chosen_variant contains the picked context/error/style for this slot.
    directive (optional) carries plan-level overrides (carry_required, format_hint, etc).
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

    # Combined Addition/Subtraction - ensure proper question text length
    if _skill_tag in ("column_add_with_carry", "addition_word_problem", "addition_error_spot",
                       "column_sub_with_borrow", "subtraction_word_problem", "subtraction_error_spot"):
        _fmt = (directive or {}).get("format_hint", "column_setup")
        is_add = "add" in _skill_tag
        if is_add:
            op = "addition"
            op_symbol = "+"
            constraint = "Require carrying in ones/tens columns."
        else:
            op = "subtraction"
            op_symbol = "-"
            constraint = "Require borrowing in ones/tens columns."

        if "error_spot" in _skill_tag:
            return (
                f"format: error_spot. Topic: {op.capitalize()} (3-digit). "
                f"A student solved a 3-digit {op} problem and got the WRONG answer. "
                f"Present the problem, show the student's WRONG answer, and ask what mistake they made. "
                f"Example: 'A student computed 456 {op_symbol} 278 = XXX (wrong). What is the correct answer?' "
                f"{constraint} "
                f"IMPORTANT: Include BOTH the problem AND the student's wrong answer in the question text. "
                f"The correct_answer field must be the RIGHT answer. "
                f"Question text must be at least 50 characters. "
                f"DO NOT use number pairs that have been used before."
            )
        elif "word_problem" in _skill_tag:
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

_WRONG_ANSWER_RE = re.compile(
    r"(?:\bgot\s+|answer\s+is\s+|=\s*|found.*?(?:sum|answer|total).*?(?:to be|is|as)\s+)(\d{2,})",
    re.IGNORECASE,
)


def validate_question(q: dict, slot_type: str) -> list[str]:
    """Validate a single generated question against slot constraints."""
    issues: list[str] = []
    fmt = q.get("format", "")
    text = q.get("question_text", "")
    answer = q.get("answer")

    allowed = VALID_FORMATS.get(slot_type, set())
    if fmt not in allowed:
        issues.append(f"format '{fmt}' not allowed for {slot_type}; expected one of {sorted(allowed)}")

    if _FORBIDDEN_VISUAL_PHRASES.search(text):
        issues.append("question_text references visuals/arrays/diagrams that aren't rendered")

    if answer is None or (isinstance(answer, str) and not answer.strip()):
        issues.append("answer is empty")

    if not text or len(text.strip()) < 10:
        issues.append("question_text is too short or missing")

    if slot_type == "error_detection":
        if not _ERROR_LANGUAGE.search(text):
            issues.append("error_detection must present a wrong answer for student to find/correct")
        # Topic-specific error_detection validation
        _skill = q.get("skill_tag", "")
        _TIME_ERROR_LANG = re.compile(r"(o'clock|:\d{2}|hour|minute|half past|quarter|clock|time|duration|a\.m\.|p\.m\.)", re.IGNORECASE)
        if _skill == "time_error_spot" and not _TIME_ERROR_LANG.search(text):
            issues.append("time error_detection must reference clock/time concepts")
        # Note: Removed addition-specific validation that required "wrong sum and original numbers"
        # Different topics have different error patterns (symmetry, time, money, multiplication, etc.)

    # Clock reading validation: verify minute hand × 5 = minutes in answer
    _skill = q.get("skill_tag", "")
    if _skill == "clock_reading":
        _MINUTE_HAND_RE = re.compile(r"minute\s+hand\s+(?:is\s+)?(?:on|at|points?\s+(?:to|at))\s+(\d{1,2})", re.IGNORECASE)
        mh_match = _MINUTE_HAND_RE.search(text)
        if mh_match:
            hand_pos = int(mh_match.group(1))
            expected_min = 0 if hand_pos == 12 else hand_pos * 5
            # Check answer contains the correct minutes
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
        except Exception:
            pass

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
        except Exception:
            pass

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
        except Exception:
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


def enforce_slot_counts(questions: list[dict], slot_plan: list[str]) -> list[dict]:
    """Deterministically trim extras / fill gaps so output matches slot_plan exactly.

    - If a slot_type has too many questions: keep only the first N (by position).
    - If a slot_type has too few: synthesize minimal fallback placeholders.
    Mutates nothing; returns a new list.
    """
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
                "format": sorted(VALID_FORMATS[st])[0],
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

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": QUESTION_SYSTEM},
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

    # Track context items from CONTEXT_BANK
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
        except Exception:
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


def backfill_format(q: dict, directive: dict | None = None) -> None:
    """Ensure q['format'] is never missing or blank. Mutates q in place.

    Resolution order:
    1. Existing q['format'] (trimmed)
    2. directive['format_hint']
    3. DEFAULT_FORMAT_BY_SLOT_TYPE[slot_type]
    Raises ValueError if slot_type is unknown and format is still empty.
    """
    fmt = (q.get("format") or "").strip()
    if not fmt:
        fmt = ((directive or {}).get("format_hint") or "").strip()
    if not fmt:
        slot_type = q.get("slot_type") or (directive or {}).get("slot_type") or ""
        fmt = DEFAULT_FORMAT_BY_SLOT_TYPE.get(slot_type, "")
        if not fmt:
            raise ValueError(f"backfill_format: unknown slot_type '{slot_type}', cannot assign default format")
    q["format"] = fmt


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
            _ARITHMETIC_TOPICS = {"Addition (carries)", "Subtraction (borrowing)"}
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
        slot_instruction = _build_slot_instruction(slot_type, variant, directive=directive)

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
                backfill_format(q, {"slot_type": slot_type, **directive})

                # Set skill_tag early so validators can use it
                q["skill_tag"] = directive.get("skill_tag") or q.get("skill_tag") or slot_type

                issues = validate_question(q, slot_type)

                # Extra check: error_detection must use backend-provided numbers (arithmetic only)
                _q_skill = q.get("skill_tag", "")
                if slot_type == "error_detection" and variant and _q_skill not in (
                    "time_error_spot", "money_error_spot", "symmetry_error_spot", "pattern_error_spot",
                ):
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
            questions.append({
                "id": i + 1,
                "slot_type": slot_type,
                "role": directive.get("role") or slot_type,
                "skill_tag": directive.get("skill_tag") or slot_type,
                "format": sorted(VALID_FORMATS[slot_type])[0],
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
    normalize_estimation_answers(questions)
    normalize_error_spot_answers(questions)

    # 7b. Enforce slot counts — trim extras, fill gaps
    questions = enforce_slot_counts(questions, slot_plan)

    # 8. Validate whole worksheet (against the actual plan, not SLOT_PLANS)
    ws_issues = validate_worksheet_slots(questions, q_count, expected_plan=slot_plan)
    if ws_issues:
        logger.warning("Worksheet-level issues: %s", ws_issues)

    carry_issues = validate_hard_difficulty_carry(questions, difficulty, topic=topic)
    if carry_issues:
        logger.warning("Hard-difficulty carry issues: %s", carry_issues)

    # 8b. Hydrate visuals (deterministic, no LLM)
    questions = hydrate_visuals(questions)

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
