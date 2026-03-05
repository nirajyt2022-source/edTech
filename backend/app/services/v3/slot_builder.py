"""Slot Builder v3 — deterministic worksheet skeleton, zero LLM calls.

Reads topic profiles, grade profiles, scenario pools, and learning objectives
to build a complete slot skeleton. Gemini only fills in question text.
"""

from __future__ import annotations

import json
import math
import random
import re
from dataclasses import dataclass, field
from pathlib import Path

from app.data.image_registry import IMAGE_REGISTRY
from app.data.learning_objectives import LEARNING_OBJECTIVES
from app.data.topic_profiles import get_topic_profile

from .context_pools import pick_contexts, pick_names

# ---------------------------------------------------------------------------
# Data directory
# ---------------------------------------------------------------------------
_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------
@dataclass
class Slot:
    slot_number: int
    question_type: str  # "mcq" | "fill_blank" | "true_false" | "short_answer" | "word_problem" | "error_detection"
    role: str  # "recognition" | "application" | "representation" | "error_detection" | "thinking"
    difficulty: str  # "easy" | "medium" | "hard"
    skill_tag: str  # from topic profile recipe
    numbers: dict | None = None  # {"a": 345, "b": 278, "answer": 623}
    wrong_answer: int | None = None  # for error_detection slots
    visual_type: str | None = None
    visual_data: dict | None = None
    context: str = ""
    names: list[str] = field(default_factory=list)
    image_keywords: list[str] | None = None
    llm_instruction: str = ""
    max_words: int = 25
    age_range: str = "8-9"
    expected_answer: str | None = None  # Python-known answer for non-maths
    assigned_word: str | None = None  # the word assigned from a word bank
    context_object: str | None = None  # word problem object (e.g. "apples", "marbles")


@dataclass
class SlotBuilderOutput:
    slots: list[Slot]
    worksheet_meta: dict  # title, skill_focus, common_mistake, parent_tip, learning_objectives


# ---------------------------------------------------------------------------
# Grade profiles (loaded once)
# ---------------------------------------------------------------------------
_GRADE_PROFILES: dict[str, dict] = {}


def _load_grade_profiles() -> dict[str, dict]:
    global _GRADE_PROFILES
    if not _GRADE_PROFILES:
        path = _DATA_DIR / "grade_profiles.json"
        with open(path) as f:
            _GRADE_PROFILES = json.load(f)
    return _GRADE_PROFILES


# ---------------------------------------------------------------------------
# Scenario pools (loaded lazily)
# ---------------------------------------------------------------------------
_SCENARIO_POOLS: dict[str, dict] = {}


def _load_scenario_pool(pool_name: str) -> dict | None:
    if pool_name in _SCENARIO_POOLS:
        return _SCENARIO_POOLS[pool_name]
    path = _DATA_DIR / "scenario_pools" / f"{pool_name}.json"
    if path.exists():
        with open(path) as f:
            _SCENARIO_POOLS[pool_name] = json.load(f)
        return _SCENARIO_POOLS[pool_name]
    return None


# ---------------------------------------------------------------------------
# Skill tag → question type mapping
# ---------------------------------------------------------------------------
SKILL_TYPE_MAP = {
    "identify": "mcq",
    "recall": "mcq",
    "match": "mcq",
    "recognition": "mcq",
    "column": "short_answer",
    "read": "short_answer",
    "reading": "short_answer",
    "word_problem": "word_problem",
    "problem": "word_problem",
    "apply": "short_answer",
    "use": "fill_blank",
    "complete": "fill_blank",
    "fill": "fill_blank",
    "blank": "fill_blank",
    "convert": "short_answer",
    "represent": "short_answer",
    "write": "short_answer",
    "rewrite": "short_answer",
    "classify": "mcq",
    "compare": "short_answer",
    "order": "short_answer",
    "ordering": "short_answer",
    "sequence": "short_answer",
    "pattern": "fill_blank",
    "error": "error_detection",
    "error_spot": "error_detection",
    "spot": "error_detection",
    "thinking": "short_answer",
    "think": "short_answer",
}


def _skill_to_question_type(skill_tag: str) -> str:
    """Map a skill tag to a question type using keyword matching."""
    tag_lower = skill_tag.lower()
    # Try exact match first
    if tag_lower in SKILL_TYPE_MAP:
        return SKILL_TYPE_MAP[tag_lower]
    # Try suffix/keyword match
    for keyword, qtype in SKILL_TYPE_MAP.items():
        if keyword in tag_lower:
            return qtype
    return "short_answer"  # default


# ---------------------------------------------------------------------------
# Skill tag → role mapping
# ---------------------------------------------------------------------------
def _skill_to_role(skill_tag: str) -> str:
    """Infer the cognitive role from a skill tag."""
    tag = skill_tag.lower()
    if "error" in tag or "spot" in tag:
        return "error_detection"
    if "thinking" in tag or "think" in tag or "multi_step" in tag:
        return "thinking"
    if "word_problem" in tag or "apply" in tag or "problem" in tag:
        return "application"
    if "missing" in tag or "represent" in tag or "estimation" in tag:
        return "representation"
    return "recognition"


# ---------------------------------------------------------------------------
# Mandatory visual topics
# ---------------------------------------------------------------------------
MANDATORY_VISUAL_TOPICS = {
    "fraction": "pie_fraction",
    "fractions": "pie_fraction",
    "time": "clock",
    "telling time": "clock",
    "money": "money_coins",
    "place value": "abacus",
    "shapes": "shapes",
    "geometry": "shapes",
    "symmetry": "grid_symmetry",
    "patterns": "pattern_tiles",
    "pattern": "pattern_tiles",
}


# ---------------------------------------------------------------------------
# Difficulty distribution
# ---------------------------------------------------------------------------
DIFFICULTY_DISTRIBUTION = {
    "easy": {"recognition": 0.60, "application": 0.30, "stretch": 0.10},
    "medium": {"recognition": 0.30, "application": 0.50, "stretch": 0.20},
    "hard": {"recognition": 0.20, "application": 0.30, "stretch": 0.50},
}


# ---------------------------------------------------------------------------
# Scale recipe
# ---------------------------------------------------------------------------
def _scale_recipe(profile: dict, num_questions: int) -> list[dict]:
    """Scale a topic profile's recipe to the requested question count."""
    # Check for explicit recipe
    recipes_by_count = profile.get("recipes_by_count", {})
    if num_questions in recipes_by_count:
        return recipes_by_count[num_questions]
    if str(num_questions) in recipes_by_count:
        return recipes_by_count[str(num_questions)]

    default_recipe = profile.get("default_recipe", [])
    if not default_recipe:
        # Fallback: generic recipe
        return [{"skill_tag": "general", "count": num_questions}]

    if num_questions == 10:
        return list(default_recipe)

    if num_questions == 5:
        # Take 1 of each unique skill_tag, prioritize first occurrence
        seen_tags = []
        result = []
        for item in default_recipe:
            tag = item["skill_tag"]
            if tag not in seen_tags:
                seen_tags.append(tag)
                result.append({"skill_tag": tag, "count": 1})
            if len(result) >= 5:
                break
        # If fewer than 5 unique tags, fill with the most common tag
        while sum(r["count"] for r in result) < 5:
            result[0]["count"] += 1
        return result

    if num_questions == 15:
        # Start with default (10), add 5 more
        result = [dict(item) for item in default_recipe]
        total = sum(r["count"] for r in result)
        deficit = 15 - total
        if deficit > 0:
            # Add 2 application, 2 fill/word_problem, 1 thinking
            _add_extras(result, default_recipe, deficit)
        return result

    if num_questions == 20:
        # Double the default, then cap special types
        result = [dict(item) for item in default_recipe]
        for r in result:
            r["count"] *= 2
        # Cap error_detection at 2, thinking at 3
        for r in result:
            tag = r["skill_tag"].lower()
            if "error" in tag and r["count"] > 2:
                r["count"] = 2
            if "thinking" in tag and r["count"] > 3:
                r["count"] = 3
        total = sum(r["count"] for r in result)
        deficit = 20 - total
        if deficit > 0:
            # Fill with most common application tag
            for r in result:
                if "word_problem" in r["skill_tag"].lower() or "apply" in r["skill_tag"].lower():
                    r["count"] += deficit
                    break
            else:
                result[0]["count"] += deficit
        elif deficit < 0:
            # Trim from the largest
            result.sort(key=lambda x: -x["count"])
            for r in result:
                if r["count"] > 1 and deficit < 0:
                    trim = min(r["count"] - 1, -deficit)
                    r["count"] -= trim
                    deficit += trim
        return result

    # Non-standard count: proportional scaling
    total_default = sum(r["count"] for r in default_recipe)
    ratio = num_questions / max(total_default, 1)
    result = [dict(item) for item in default_recipe]
    for r in result:
        r["count"] = max(1, round(r["count"] * ratio))
    total = sum(r["count"] for r in result)
    while total > num_questions and total > len(result):
        result.sort(key=lambda x: -x["count"])
        result[0]["count"] -= 1
        total -= 1
    while total < num_questions:
        result[0]["count"] += 1
        total += 1
    return result


def _add_extras(result: list[dict], default_recipe: list[dict], deficit: int):
    """Add extra slots for scaling to 15."""
    added = 0
    # Try adding to word_problem/application tags first
    for r in result:
        if added >= deficit:
            break
        tag = r["skill_tag"].lower()
        if "word_problem" in tag or "apply" in tag:
            add = min(2, deficit - added)
            r["count"] += add
            added += add
    # Then fill_blank/pattern
    for r in result:
        if added >= deficit:
            break
        tag = r["skill_tag"].lower()
        if "fill" in tag or "missing" in tag or "pattern" in tag:
            add = min(2, deficit - added)
            r["count"] += add
            added += add
    # Then thinking
    for r in result:
        if added >= deficit:
            break
        tag = r["skill_tag"].lower()
        if "thinking" in tag or "think" in tag:
            add = min(1, deficit - added)
            r["count"] += add
            added += add
    # Remainder goes to first item
    if added < deficit:
        result[0]["count"] += deficit - added


# ---------------------------------------------------------------------------
# Number generation for maths
# ---------------------------------------------------------------------------
def _detect_maths_operation(topic: str, skill_tag: str) -> str | None:
    """Detect the maths operation from topic/skill_tag."""
    combined = f"{topic} {skill_tag}".lower()
    if any(kw in combined for kw in ("add", "addition", "sum", "plus")):
        if "carry" in combined or "carries" in combined:
            return "addition_with_carry"
        return "addition"
    if any(kw in combined for kw in ("subtract", "subtraction", "minus", "difference", "borrow")):
        if "borrow" in combined:
            if "without" in combined or "no" in combined:
                return "subtraction_no_borrow"
            return "subtraction_with_borrow"
        return "subtraction"
    if any(kw in combined for kw in ("multipl", "times", "product", "table")):
        return "multiplication"
    if any(kw in combined for kw in ("divid", "division", "quotient", "share")):
        return "division"
    return None


def _generate_numbers(grade_num: int, operation: str | None, skill_tag: str) -> dict | None:
    """Generate grade-appropriate numbers for maths slots."""
    if not operation:
        return None

    # Try scenario pools first
    pool = None
    if operation in ("addition", "addition_with_carry"):
        pool = _load_scenario_pool("maths_addition")
    elif operation in ("subtraction", "subtraction_with_borrow", "subtraction_no_borrow"):
        pool = _load_scenario_pool("maths_subtraction") if _load_scenario_pool("maths_subtraction") else None

    class_key = f"class_{grade_num}"
    if pool and class_key in pool:
        pairs = pool[class_key].get("pairs", [])
        if pairs:
            pair = random.choice(pairs)
            if operation in ("addition", "addition_with_carry"):
                return {"a": pair["a"], "b": pair["b"], "answer": pair.get("sum", pair["a"] + pair["b"])}
            elif operation in ("subtraction", "subtraction_with_borrow", "subtraction_no_borrow"):
                return {"a": pair["a"], "b": pair["b"], "answer": pair.get("diff", pair["a"] - pair["b"])}

    # Generate random numbers based on grade
    if operation in ("addition", "addition_with_carry"):
        return _random_addition(grade_num)
    elif operation == "subtraction_no_borrow":
        return _random_subtraction(grade_num, allow_borrow=False)
    elif operation in ("subtraction", "subtraction_with_borrow"):
        return _random_subtraction(grade_num, allow_borrow=True)
    elif operation == "multiplication":
        return _random_multiplication(grade_num)
    elif operation == "division":
        return _random_division(grade_num)
    return None


def _random_addition(grade: int) -> dict:
    if grade == 1:
        a, b = random.randint(2, 9), random.randint(2, 9)
        while a + b > 20:
            a, b = random.randint(2, 9), random.randint(2, 9)
    elif grade == 2:
        a = random.randint(10, 60)
        b = random.randint(10, 99 - a)
    elif grade == 3:
        a = random.randint(100, 600)
        b = random.randint(100, 999 - a)
    elif grade == 4:
        a = random.randint(1000, 5000)
        b = random.randint(1000, 9999 - a)
    else:
        a = random.randint(10000, 50000)
        b = random.randint(10000, 99999 - a)
    return {"a": a, "b": b, "answer": a + b}


def _random_subtraction(grade: int, allow_borrow: bool = True) -> dict:
    """Generate subtraction pair. If allow_borrow=False, ensure no borrowing needed."""
    max_attempts = 50
    for _ in range(max_attempts):
        if grade == 1:
            a = random.randint(5, 18)
            b = random.randint(2, min(9, a - 1))
        elif grade == 2:
            a = random.randint(20, 99)
            b = random.randint(10, a - 1)
        elif grade == 3:
            a = random.randint(100, 999)
            b = random.randint(100, a - 1)
        elif grade == 4:
            a = random.randint(1000, 9999)
            b = random.randint(100, a - 1)
        else:
            a = random.randint(10000, 99999)
            b = random.randint(1000, a - 1)

        # Ensure minimum pedagogical difference (avoid trivial 39-38=1)
        if a - b < 3:
            continue

        if not allow_borrow:
            # Check EVERY digit: each digit of a must be >= corresponding digit of b
            sa = str(a)
            sb = str(b).zfill(len(sa))
            needs_borrow = False
            for da, db in zip(reversed(sa), reversed(sb)):
                if int(da) < int(db):
                    needs_borrow = True
                    break
            if needs_borrow:
                continue  # retry

        return {"a": a, "b": b, "answer": a - b}

    # Fallback: construct a guaranteed no-borrow pair
    if grade <= 2:
        a_ones = random.randint(5, 9)
        b_ones = random.randint(1, a_ones)
        a_tens = random.randint(3, 9)
        b_tens = random.randint(1, a_tens)
        a = a_tens * 10 + a_ones
        b = b_tens * 10 + b_ones
    else:
        a, b = 87, 43  # safe fallback
    return {"a": a, "b": b, "answer": a - b}


def _random_multiplication(grade: int) -> dict:
    if grade <= 2:
        a = random.randint(2, 5)
        b = random.randint(2, 5)
    elif grade == 3:
        a = random.randint(2, 10)
        b = random.randint(2, 10)
    elif grade == 4:
        # NCERT Class 4: 2-digit × 1-digit, max 2-digit × 2-digit (small)
        a = random.randint(11, 50)
        b = random.randint(2, 20)
    else:
        # Class 5: 2-digit × 2-digit, some 3-digit × 1-digit
        choice = random.choice(["2d_2d", "3d_1d"])
        if choice == "2d_2d":
            a = random.randint(11, 99)
            b = random.randint(11, 50)
        else:
            a = random.randint(100, 500)
            b = random.randint(2, 9)
    return {"a": a, "b": b, "answer": a * b}


def _random_division(grade: int) -> dict:
    if grade <= 2:
        b = random.randint(2, 5)
        answer = random.randint(2, 5)
    elif grade == 3:
        b = random.randint(2, 10)
        answer = random.randint(2, 10)
    elif grade == 4:
        # NCERT Class 4: divide 2-digit by 1-digit
        b = random.randint(2, 9)
        answer = random.randint(5, 20)
    else:
        # Class 5: divide up to 3-digit by 1-2 digit
        b = random.randint(2, 20)
        answer = random.randint(10, 50)
    a = b * answer  # ensures clean division
    return {"a": a, "b": b, "answer": answer}


def _generate_wrong_answer(correct: int, operation: str | None) -> int:
    """Generate a plausible wrong answer for error detection."""
    offsets = [1, -1, 10, -10]
    if correct >= 100:
        offsets.extend([100, -100])
    wrong = correct + random.choice(offsets)
    if wrong <= 0:
        wrong = correct + abs(random.choice(offsets))
    return wrong


# ---------------------------------------------------------------------------
# Visual data computation
# ---------------------------------------------------------------------------
def _compute_visual_data(visual_type: str, numbers: dict | None, grade_num: int) -> dict | None:
    """Compute visual_data for a given visual type."""
    if visual_type == "pie_fraction":
        if numbers and "a" in numbers and "b" in numbers:
            return {"numerator": min(numbers["a"], numbers["b"]), "denominator": max(numbers["a"], numbers["b"])}
        denoms = [2, 3, 4, 6, 8]
        d = random.choice(denoms)
        n = random.randint(1, d - 1)
        return {"numerator": n, "denominator": d}

    if visual_type == "clock":
        h = random.randint(1, 12)
        m_options = [0, 15, 30, 45] if grade_num <= 2 else list(range(0, 60, 5))
        m = random.choice(m_options)
        return {"hour": h, "minute": m}

    if visual_type == "money_coins":
        coin_values = [1, 2, 5, 10]
        coins = []
        for val in random.sample(coin_values, min(3, len(coin_values))):
            coins.append({"value": val, "count": random.randint(1, 5)})
        return {"coins": coins}

    if visual_type == "abacus":
        if numbers and "a" in numbers:
            n = numbers["a"]
            return {"hundreds": (n // 100) % 10, "tens": (n // 10) % 10, "ones": n % 10}
        return {"hundreds": random.randint(1, 9), "tens": random.randint(0, 9), "ones": random.randint(0, 9)}

    if visual_type == "shapes":
        shape = random.choice(["triangle", "rectangle", "square", "circle"])
        sides = {"triangle": [3, 4, 5], "rectangle": [4, 6], "square": [5, 5], "circle": []}
        return {"shape": shape, "sides": sides.get(shape, [])}

    if visual_type == "grid_symmetry":
        size = 4
        filled = [[random.randint(0, size - 1), random.randint(0, size // 2 - 1)] for _ in range(3)]
        return {"grid_size": size, "filled_cells": filled, "fold_axis": "vertical"}

    if visual_type == "number_line":
        if numbers and "a" in numbers:
            start = max(0, numbers["a"] - 5)
            end = numbers["a"] + 10
            step = 1 if grade_num <= 2 else 5
            return {"start": start, "end": end, "step": step, "highlight": numbers["a"]}
        return {"start": 0, "end": 20, "step": 2, "highlight": None}

    if visual_type == "object_group":
        if numbers and "a" in numbers:
            op = "+" if numbers.get("answer", 0) > max(numbers["a"], numbers.get("b", 0)) else "-"
            return {
                "groups": [
                    {"count": numbers["a"], "label": "objects"},
                    {"count": numbers.get("b", 0), "label": "objects"},
                ],
                "operation": op,
            }
        return {"groups": [{"count": 3, "label": "apples"}, {"count": 4, "label": "apples"}], "operation": "+"}

    if visual_type == "pattern_tiles":
        tiles = ["A", "B", "A", "B", "A", "?"]
        return {"tiles": tiles, "blank_position": 5}

    if visual_type == "base_ten_regrouping":
        if numbers and "a" in numbers:
            op = "addition" if numbers.get("answer", 0) > numbers["a"] else "subtraction"
            return {"numbers": [numbers["a"], numbers.get("b", 0)], "operation": op}
        return {"numbers": [234, 178], "operation": "addition"}

    return None


# ---------------------------------------------------------------------------
# Image keywords for non-maths subjects
# ---------------------------------------------------------------------------
def _get_image_keywords_for_subject(subject: str) -> list[str]:
    """Get available image keywords relevant to a subject."""
    all_keywords = list(IMAGE_REGISTRY.keys())
    subject_lower = subject.lower()
    if subject_lower in ("evs", "science"):
        return [k for k in all_keywords if IMAGE_REGISTRY[k].get("category") in ("animal", "plant", "habitat", "food")]
    return all_keywords


# ── Topic → Image mapping for illustrated worksheets ──
TOPIC_IMAGE_MAP = {
    # Maths
    "addition": ["apple", "mango", "banana", "flower", "butterfly", "pencil_box"],
    "subtraction": ["apple", "mango", "bird_flock", "flower", "balloon"],
    "shapes": ["triangle_shape", "circle_shape", "rectangle_shape", "square_shape"],
    "money": ["coin_1", "coin_2", "coin_5", "note_10", "note_50"],
    "time": ["clock", "sun", "moon"],
    "measurement": ["ruler", "scale", "thermometer"],
    "numbers": ["apple", "mango", "star", "pencil_box", "book_open"],
    "multiplication": ["apple", "mango", "flower", "egg"],
    "division": ["apple", "mango", "roti", "laddoo"],
    "fractions": [],  # uses visual_type=pie_fraction instead
    "data handling": [],
    "spatial": [],
    # English
    "alphabet": ["apple", "ball", "cat", "dog", "elephant"],
    "nouns": ["dog", "cat", "book_open", "school_bag", "tree"],
    "verbs": ["cricket", "football", "bicycle", "bus"],
    "pronouns": ["family_group", "mother", "father", "baby"],
    "adjectives": ["sun", "flower", "elephant", "ant"],
    "sentences": ["school_bag", "book_open", "pencil_box"],
    "vocabulary": ["cow", "dog", "cat", "mango", "apple", "banana"],
    "phonics": ["apple", "ball", "cat", "dog", "egg", "fish"],
    "rhyming": ["cat", "bat", "star", "car"],
    "greetings": ["family_group", "school_bag"],
    "seasons": ["sunny", "rainy", "snowy", "windy", "cloudy"],
    "family": ["family_group", "grandparents", "mother", "father", "baby"],
    # EVS
    "animals": ["cow", "lion", "tiger", "elephant", "monkey", "parrot", "fish", "butterfly", "rabbit"],
    "plants": ["tree", "flower", "rose", "sunflower", "tulsi", "lotus"],
    "food": ["mango", "apple", "banana", "rice", "roti", "laddoo", "milk"],
    "body": ["human_body", "eye", "ear", "nose", "tongue", "hand"],
    "water": ["water_drop", "rain", "pond", "ocean", "tap"],
    "shelter": ["house", "nest", "kennel", "stable"],
    "senses": ["eye", "ear", "nose", "tongue", "hand"],
    "weather": ["sunny", "rainy", "cloudy", "snowy", "windy"],
    "habitats": ["forest", "pond", "desert", "ocean", "farm"],
    "nutrition": ["mango", "apple", "banana", "rice", "roti", "milk", "egg"],
    # Hindi
    "varnamala": ["apple", "mango", "elephant", "flower"],
    "family words": ["family_group", "grandparents", "mother", "father"],
    "nature": ["tree", "flower", "sun", "moon", "cloud"],
    # Science
    "digestion": ["apple", "roti", "rice", "human_body"],
    "air": ["balloon", "windy", "fan"],
    "light": ["sun", "torch", "candle"],
    "magnet": [],
    "force": ["car", "bicycle", "cricket"],
    # Computer
    "parts of computer": ["desktop_computer", "laptop", "keyboard", "mouse", "monitor"],
    "mouse": ["mouse", "desktop_computer"],
    "keyboard": ["keyboard", "desktop_computer"],
    "typing": ["keyboard", "laptop"],
    # Health
    "hygiene": ["toothbrush", "soap", "handwash", "comb", "towel"],
    "exercise": ["cricket", "football", "yoga_pose"],
    "posture": ["yoga_pose"],
    "eating": ["mango", "apple", "roti", "milk"],
}


def _get_topic_images(topic: str, subject: str, slot_num: int = 0) -> list[str] | None:
    """Get 1-2 relevant image keywords for a topic, rotating per slot."""
    topic_lower = topic.lower()

    # Find matching keywords from TOPIC_IMAGE_MAP
    matched_images: list[str] = []
    for key, images in TOPIC_IMAGE_MAP.items():
        if key in topic_lower:
            matched_images.extend(images)

    # Also check subject-level keywords
    subject_lower = subject.lower()
    for key, images in TOPIC_IMAGE_MAP.items():
        if key in subject_lower and key not in topic_lower:
            matched_images.extend(images[:3])

    if not matched_images:
        return None

    # Deduplicate while preserving order, only keep keys in IMAGE_REGISTRY
    seen: set[str] = set()
    unique: list[str] = []
    for img in matched_images:
        if img not in seen and img in IMAGE_REGISTRY:
            seen.add(img)
            unique.append(img)

    if not unique:
        return None

    # Rotate based on slot number for variety
    start = (slot_num * 2) % len(unique)
    selected = []
    for j in range(min(2, len(unique))):
        selected.append(unique[(start + j) % len(unique)])

    return selected


# ---------------------------------------------------------------------------
# Hindi grammar answer banks — Python-owned answers, same pattern as maths
# ---------------------------------------------------------------------------
HINDI_VACHAN_BANK = {
    "लड़का": "लड़के",
    "लड़की": "लड़कियाँ",
    "गाय": "गाएँ",
    "कुत्ता": "कुत्ते",
    "किताब": "किताबें",
    "पुस्तक": "पुस्तकें",
    "बच्चा": "बच्चे",
    "पक्षी": "पक्षी",
    "मछली": "मछलियाँ",
    "चिड़िया": "चिड़ियाँ",
    "दुकान": "दुकानें",
    "खिड़की": "खिड़कियाँ",
    "खिलौना": "खिलौने",
    "पटाखा": "पटाखे",
    "तारा": "तारे",
    "आँख": "आँखें",
    "कान": "कान",
    "पैर": "पैर",
    "हाथ": "हाथ",
    "दरवाज़ा": "दरवाज़े",
    "कमरा": "कमरे",
    "फूल": "फूल",
    "पत्ता": "पत्ते",
    "डिब्बा": "डिब्बे",
    "गिलास": "गिलास",
    "कप": "कप",
    "कुर्सी": "कुर्सियाँ",
    "मेज़": "मेज़ें",
    "बिल्ली": "बिल्लियाँ",
    "चूहा": "चूहे",
    "मोर": "मोर",
    "तोता": "तोते",
    "रोटी": "रोटियाँ",
    "सब्ज़ी": "सब्ज़ियाँ",
    "मिठाई": "मिठाइयाँ",
    "टोपी": "टोपियाँ",
    "नदी": "नदियाँ",
    "गुड़िया": "गुड़ियाँ",
    "पेड़": "पेड़",
    "बादल": "बादल",
    "गाड़ी": "गाड़ियाँ",
    "पौधा": "पौधे",
    "तस्वीर": "तस्वीरें",
    "गेंद": "गेंदें",
}

HINDI_VILOM_BANK = {
    "दिन": "रात",
    "गर्म": "ठंडा",
    "ऊपर": "नीचे",
    "आना": "जाना",
    "सुख": "दुख",
    "अच्छा": "बुरा",
    "बड़ा": "छोटा",
    "लंबा": "छोटा",
    "मोटा": "पतला",
    "सुंदर": "कुरूप",
    "अमीर": "गरीब",
    "राजा": "रंक",
    "जीत": "हार",
    "शुरू": "खत्म",
    "खुश": "दुखी",
    "सच": "झूठ",
}


# ---------------------------------------------------------------------------
# Topic-specific instruction templates (for tricky grammar/concept topics)
# ---------------------------------------------------------------------------
TOPIC_INSTRUCTION_TEMPLATES: dict[str, dict[str, str]] = {
    # Hindi grammar topics
    "वचन": {
        "mcq": "Ask: '{word} का बहुवचन क्या है?' Give a singular Hindi word, ask for its plural form. Example: 'लड़का → लड़के'. Options should be 4 different plural forms, only one correct.",
        "fill_blank": "Write a sentence with one blank where the student must write the correct singular or plural form. Example: 'बगीचे में कई ______ हैं। (फूल)'",
        "short_answer": "Give a singular word and ask the student to write its plural form. Example: 'पुस्तक का बहुवचन लिखो।'",
        "true_false": "Write a statement like: 'पुस्तक का बहुवचन पुस्तकें है।' correct_answer: True or False.",
        "error_detection": "Show an incorrect singular/plural conversion. Student must find the mistake.",
    },
    "विशेषण": {
        "mcq": "Give a Hindi sentence with an adjective. Ask: 'इस वाक्य में विशेषण कौन-सा शब्द है?' Options: 4 words from the sentence, only one is the adjective.",
        "fill_blank": "Write: '______ फूल बहुत सुंदर है।' where the blank needs an adjective like 'लाल' or 'बड़ा'.",
        "short_answer": "Give a sentence and ask student to identify the adjective (विशेषण) in it.",
        "true_false": "Write a statement about adjectives. Example: '\"लाल\" एक विशेषण है।' correct_answer: True.",
    },
    "संज्ञा": {
        "mcq": "Ask: 'इनमें से संज्ञा शब्द कौन-सा है?' Give 4 Hindi words, one is a noun.",
        "short_answer": "Give a sentence and ask the student to identify the noun (संज्ञा).",
    },
    "सर्वनाम": {
        "mcq": "Ask: 'इनमें से सर्वनाम कौन-सा है?' Give 4 words, one is a pronoun (मैं, तुम, वह, हम).",
        "fill_blank": "Give a sentence with a blank where a pronoun goes. Example: '______ विद्यालय जाता है।'",
    },
    "क्रिया": {
        "mcq": "Ask: 'इनमें से क्रिया शब्द कौन-सा है?' Give 4 words, one is a verb.",
        "fill_blank": "Give a sentence with a blank where a verb goes.",
    },
    "विलोम शब्द": {
        "mcq": "Ask: '{word} का विलोम शब्द क्या है?' Give a word, ask for its opposite. Options: 4 words.",
        "short_answer": "Give a word and ask for its विलोम (opposite). Example: 'दिन → रात'.",
    },
    "पर्यायवाची शब्द": {
        "mcq": "Ask: '{word} का पर्यायवाची शब्द क्या है?' Give a word, ask for its synonym. Options: 4 words.",
        "short_answer": "Give a word and ask for its पर्यायवाची (synonym).",
    },
    "मुहावरे": {
        "mcq": "Ask: '{muhavra} का अर्थ क्या है?' Give a Hindi idiom and 4 meaning options.",
        "short_answer": "Give a situation and ask which muhavra (idiom) fits.",
    },
    "Varnamala": {
        "mcq": "Ask about Hindi letter identification: 'इनमें से स्वर कौन-सा है?' or 'इस अक्षर की मात्रा पहचानो।'",
        "fill_blank": "Write a word with a missing letter (matra). Student fills in the correct matra.",
    },
    # English grammar topics
    "Nouns": {
        "mcq": "Ask: 'Which of these is a noun?' Give 4 words (1 noun, 3 non-nouns: verb, adjective, pronoun). Or: 'Identify the proper noun in this sentence.'",
        "fill_blank": "Write a sentence with a blank: 'The ______ is on the table.' Answer should be a noun.",
        "short_answer": "Give a sentence and ask the student to identify the noun(s) in it.",
    },
    "Tenses": {
        "mcq": "Give a sentence and ask: 'What tense is this sentence in?' Options: Simple Past, Simple Present, Simple Future, + 1 wrong.",
        "fill_blank": "Write: 'Yesterday, Ria ______ (go) to the park.' Answer: went.",
        "short_answer": "Give a sentence in one tense and ask: 'Change to past/present/future tense.'",
    },
    "Adjectives": {
        "mcq": "Ask: 'Which word is an adjective in this sentence?' Give 4 words from the sentence.",
        "fill_blank": "Give a sentence with a blank where an adjective goes. Example: 'The ______ cat sat on the mat.'",
    },
    "Pronouns": {
        "mcq": "Ask: 'Which word is a pronoun in this sentence?' Give 4 word options.",
        "fill_blank": "Give a sentence with a blank where a pronoun goes. Example: '______ went to school.'",
    },
    "Active and Passive Voice": {
        "mcq": "Give a sentence. Ask: 'Is this in active or passive voice?' Options: Active Voice, Passive Voice, + 2 wrong.",
        "short_answer": "Give an active voice sentence. Ask: 'Change to passive voice.'",
    },
}


# ---------------------------------------------------------------------------
# LLM instruction builder
# ---------------------------------------------------------------------------
def _build_llm_instruction(
    slot: Slot,
    topic: str,
    subject: str,
    language: str,
    grade_num: int,
) -> str:
    """Build a specific instruction string for Gemini to fill this slot."""
    parts = []

    # Check for topic-specific instruction template
    for topic_key, templates in TOPIC_INSTRUCTION_TEMPLATES.items():
        if topic_key.lower() in topic.lower() or topic.lower() in topic_key.lower():
            template = templates.get(slot.question_type) or templates.get("mcq")
            if template:
                parts.append(f"SPECIFIC INSTRUCTION: {template}")
            break

    # ── Hindi grammar word bank injection ──
    # If topic is a Hindi grammar topic with a word bank,
    # assign a specific word and answer to this slot, then RETURN EARLY.
    topic_lower = topic.lower()

    if "वचन" in topic or "vachan" in topic_lower:
        word_items = list(HINDI_VACHAN_BANK.items())
        # Deterministic index — ensures different words per slot, no shuffle
        idx = (slot.slot_number - 1) % len(word_items)
        singular, plural = word_items[idx]
        slot.assigned_word = singular
        slot.expected_answer = plural

        if slot.question_type == "mcq":
            # Rotate through different MCQ frames
            mcq_frames = [
                f"'{singular}' का बहुवचन क्या है?",
                f"इनमें से '{singular}' का सही बहुवचन चुनो।",
                f"'{singular}' शब्द का बहुवचन रूप बताओ।",
            ]
            frame = mcq_frames[slot.slot_number % len(mcq_frames)]
            other_plurals = [v for k, v in word_items if v != plural and v != singular]
            random.shuffle(other_plurals)
            wrong_opts = other_plurals[:3]
            parts.append(f"SPECIFIC TASK: Ask: {frame}")
            parts.append(f"Correct answer: {plural}")
            parts.append(f"Wrong options: {', '.join(wrong_opts)}")
            parts.append(f"Set correct_answer to exactly: {plural}")
            parts.append("Do NOT change the question. Ask ONLY about बहुवचन of this exact word.")
        elif slot.question_type == "fill_blank":
            fill_frames = [
                f"'{singular}' का बहुवचन ______ है।",
                f"एक {singular}, बहुत सारे ______।",
                f"बगीचे में कई ______ हैं। ({singular})",
            ]
            frame = fill_frames[slot.slot_number % len(fill_frames)]
            parts.append(f"SPECIFIC TASK: Write: {frame}")
            parts.append(f"Correct answer: {plural}")
            parts.append(f"Set correct_answer to exactly: {plural}")
        elif slot.question_type == "true_false":
            is_true = random.choice([True, False])
            if is_true:
                parts.append(f"SPECIFIC TASK: Write statement: '{singular} का बहुवचन {plural} है।' Answer: True")
                slot.expected_answer = "True"
            else:
                wrong = random.choice([v for k, v in word_items if v != plural])
                parts.append(f"SPECIFIC TASK: Write statement: '{singular} का बहुवचन {wrong} है।' Answer: False")
                slot.expected_answer = "False"
        elif slot.question_type == "error_detection":
            wrong = random.choice([v for k, v in word_items if v != plural])
            parts.append(f"SPECIFIC TASK: Write: 'राम ने कहा {singular} का बहुवचन {wrong} है। क्या यह सही है? गलती बताओ।'")
            parts.append(f"Correct answer: गलत है। सही बहुवचन {plural} है।")
            slot.expected_answer = f"गलत है। सही बहुवचन {plural} है।"
        else:
            sa_frames = [
                f"'{singular}' का बहुवचन लिखो।",
                f"'{singular}' शब्द को बहुवचन में बदलो।",
                f"इस शब्द का बहुवचन लिखो: '{singular}'",
            ]
            frame = sa_frames[slot.slot_number % len(sa_frames)]
            parts.append(f"SPECIFIC TASK: {frame}")
            parts.append(f"Correct answer: {plural}")
            parts.append(f"Set correct_answer to exactly: {plural}")

        parts.append("Write in pure Devanagari. No English.")
        if grade_num <= 1:
            parts.append("CRITICAL: Question text must be UNDER 15 words.")
        elif grade_num <= 2:
            parts.append("Question text must be under 20 words.")
        parts.append(f"Age range: {slot.age_range} | Difficulty: {slot.difficulty}")
        # RETURN EARLY — don't add generic instructions
        return " | ".join(parts)

    elif "विलोम" in topic or "vilom" in topic_lower:
        word_items = list(HINDI_VILOM_BANK.items())
        idx = (slot.slot_number - 1) % len(word_items)
        word, opposite = word_items[idx]
        slot.assigned_word = word
        slot.expected_answer = opposite

        if slot.question_type == "mcq":
            wrong_opts = [v for k, v in word_items if v != opposite][:3]
            parts.append(f"SPECIFIC TASK: Ask '{word} का विलोम शब्द क्या है?'")
            parts.append(f"Correct answer: {opposite}. Wrong options: {', '.join(wrong_opts)}")
            parts.append(f"Set correct_answer to exactly: {opposite}")
        elif slot.question_type == "true_false":
            is_true = random.choice([True, False])
            if is_true:
                parts.append(f"SPECIFIC TASK: Write statement: '{word} का विलोम शब्द {opposite} है।' Answer: True")
                slot.expected_answer = "True"
            else:
                wrong = random.choice([v for k, v in word_items if v != opposite])
                parts.append(f"SPECIFIC TASK: Write statement: '{word} का विलोम शब्द {wrong} है।' Answer: False")
                slot.expected_answer = "False"
        else:
            parts.append(f"SPECIFIC TASK: Use word '{word}' (विलोम: {opposite})")
            parts.append(f"Set correct_answer to exactly: {opposite}")

        parts.append("Write in pure Devanagari. No English.")
        if grade_num <= 1:
            parts.append("CRITICAL: Question text must be UNDER 15 words.")
        elif grade_num <= 2:
            parts.append("Question text must be under 20 words.")
        parts.append(f"Age range: {slot.age_range} | Difficulty: {slot.difficulty}")
        return " | ".join(parts)

    # ── Generic instruction (non-word-bank topics) ──
    # Type and topic
    parts.append(f"Question type: {slot.question_type}")
    parts.append(f"Topic: {topic}")
    parts.append(f"Age range: {slot.age_range}")

    # Question length constraint based on grade
    if grade_num <= 1:
        parts.append("CRITICAL: Question text must be UNDER 15 words. A 6-year-old must be able to read it alone.")
    elif grade_num <= 2:
        parts.append("Question text must be under 20 words. Keep sentences short and simple.")
    elif grade_num <= 3:
        parts.append("Question text should be under 30 words.")

    parts.append(f"Max words: {slot.max_words}")
    parts.append(f"Cognitive role: {slot.role}")
    parts.append(f"Difficulty: {slot.difficulty}")

    # Grade-level vocabulary constraint for Science/EVS
    if subject.lower() in ("science", "evs") and grade_num <= 5:
        if grade_num <= 2:
            parts.append("Use ONLY words a 6-7 year old knows. No scientific terms.")
        elif grade_num <= 3:
            parts.append("Use simple words. Say 'food pipe' not 'esophagus'. Say 'tummy' not 'stomach lining'.")
        elif grade_num <= 4:
            parts.append(
                "Use NCERT Class 4 vocabulary ONLY. Say 'food pipe' not 'esophagus'. Say 'breaks down food' not 'digestion enzymes'. NO words like: cellulose, ruminant, peristalsis, pancreas, enzymes, glucose, organisms, photosynthesis."
            )
        elif grade_num <= 5:
            parts.append(
                "Use NCERT Class 5 vocabulary. Avoid Class 7+ terms like: cellulose, ruminant, peristalsis, enzymes, mitochondria, cytoplasm."
            )

    # Maths with pre-computed numbers
    if slot.numbers:
        a, b, ans = slot.numbers.get("a"), slot.numbers.get("b"), slot.numbers.get("answer")
        if a is not None and b is not None and ans is not None:
            parts.append(f"Use the numbers {a} and {b}. Correct answer: {ans}.")

    # Format-specific instructions
    if slot.question_type == "word_problem":
        # Use rotating frame templates for variety
        from .context_pools import FEMALE_NAMES, WORD_PROBLEM_FRAMES

        operation = _detect_maths_operation(topic, slot.skill_tag)
        # Map operation to frame key
        frame_key = "addition"
        if operation and "subtraction" in operation:
            frame_key = "subtraction"
        elif operation and "multiplication" in operation:
            frame_key = "multiplication"
        elif operation and "fraction" in operation:
            frame_key = "fractions"
        elif operation == "addition" or (operation and "addition" in operation):
            frame_key = "addition"

        frames = WORD_PROBLEM_FRAMES.get(frame_key, WORD_PROBLEM_FRAMES["addition"])
        frame = frames[slot.slot_number % len(frames)]

        name = slot.names[0] if slot.names else "Aarav"
        name2 = slot.names[1] if len(slot.names) > 1 else "Priya"
        pronoun = "she" if name in FEMALE_NAMES else "he"
        pronoun_cap = pronoun.capitalize()
        obj = slot.context_object or "items"

        if slot.numbers:
            a, b = slot.numbers["a"], slot.numbers["b"]
            filled_frame = frame.format(
                name=name,
                name2=name2,
                pronoun=pronoun,
                pronoun_cap=pronoun_cap,
                a=a,
                b=b,
                obj=obj,
                context=slot.context or "shop",
            )
            parts.append(f"Write a word problem SIMILAR to this structure (vary the wording): {filled_frame}")
            parts.append(f"Correct answer: {slot.numbers['answer']}.")
        else:
            if slot.context:
                parts.append(f"Set in a {slot.context} context.")
            if slot.names:
                parts.append(f"Use character(s): {', '.join(slot.names)}.")
        parts.append("Make it a natural mini-story. Don't copy the frame exactly — use it as inspiration.")

    elif slot.question_type == "error_detection":
        if slot.numbers and slot.wrong_answer is not None:
            a, b = slot.numbers.get("a", 0), slot.numbers.get("b", 0)
            ans = slot.numbers.get("answer", 0)
            name = slot.names[0] if slot.names else "Aarav"
            parts.append(f"Character {name} solved {a} + {b} = {slot.wrong_answer}. Correct is {ans}.")
        parts.append("Student must find and explain the mistake.")

    elif slot.question_type == "fill_blank":
        parts.append("Must contain exactly one blank (______).")

    elif slot.question_type == "true_false":
        is_true = random.choice([True, False])
        if slot.numbers:
            # Maths true/false — use pre-computed numbers
            a, b = slot.numbers.get("a", 0), slot.numbers.get("b", 0)
            ans = slot.numbers.get("answer", 0)
            if is_true:
                parts.append(f"Write a TRUE statement using {a} and {b}.")
                parts.append(f"Example: '{a} + {b} = {ans}'")
                parts.append("correct_answer must be: True")
            else:
                wrong = ans + random.choice([-1, 1, -10, 10])
                if wrong <= 0:
                    wrong = ans + random.choice([1, 2, 10])
                parts.append(f"Write a FALSE statement: '{a} + {b} = {wrong}'")
                parts.append(f"The actual answer is {ans}.")
                parts.append("correct_answer must be: False")
        else:
            # Non-maths true/false
            parts.append(f"Write a single DECLARATIVE STATEMENT (not a question) that is {is_true}.")
            parts.append("The statement must NOT contain a question mark.")
            parts.append("BAD example: 'Which word is a noun?' — this is a question, NOT a statement.")
            parts.append("GOOD example: 'The word cake is a common noun.' — this IS a statement.")
            parts.append(f"The student must decide if this statement is True or False. Answer: {is_true}.")
            parts.append("Set correct_answer to exactly: 'True' or 'False'.")
        parts.append("CRITICAL: Write a STATEMENT, not a question. No '?' allowed.")
        parts.append("correct_answer must be exactly 'True' or 'False'.")

    elif slot.question_type == "mcq":
        is_maths_subj = subject.lower() in ("maths", "mathematics", "math")
        if is_maths_subj and slot.numbers:
            parts.append("Write the question text only. Options will be generated separately.")
        else:
            # Rotate through MCQ phrasing styles to avoid repetitive feel
            mcq_styles = [
                "Ask 'Which of these is...?' with 4 options.",
                "Give a sentence and ask to identify the correct word/concept from 4 options.",
                "Show an example and ask what category/type it belongs to. 4 options.",
                "Ask 'Which one does NOT belong?' with 4 options (3 correct, 1 wrong — answer is the odd one out).",
            ]
            style = mcq_styles[slot.slot_number % len(mcq_styles)]
            parts.append(style)
            parts.append("1 clearly correct option, 3 clearly wrong. At least 1 obviously wrong.")

    # Fraction MCQs with visuals — use fraction notation, not "Option A/B"
    if slot.visual_type == "pie_fraction" and slot.visual_data and slot.question_type == "mcq":
        n = slot.visual_data.get("numerator")
        d = slot.visual_data.get("denominator")
        if n is not None and d is not None:
            parts.append(
                f"The correct answer is the fraction {n}/{d}. Use fraction notation in options (like 1/4, 1/2, 3/4), NOT 'Option A/B/C'."
            )

    # Thinking role — require reasoning, not just harder arithmetic
    if slot.role == "thinking":
        if slot.numbers:
            thinking_maths = [
                "Ask the student to EXPLAIN WHY their answer is correct. Use 'Why?' or 'Explain your reasoning.'",
                "Ask the student to COMPARE two methods. Example: 'Ravi solves 48+37 by counting up. Priya uses column addition. Who is faster? Why?'",
                "Ask a WHAT IF question. Example: 'What happens to the sum if you increase one number by 10?'",
                "Ask the student to SPOT A PATTERN. Example: 'Add: 10+5, 20+5, 30+5. What pattern do you see?'",
                "Ask the student to PROVE or DISPROVE. Example: 'Meera says adding 0 to any number gives 0. Is she right?'",
            ]
            parts.append(f"THINKING QUESTION: {random.choice(thinking_maths)}")
        else:
            thinking_non_maths = [
                "Ask WHY or HOW — not just WHAT. Example: 'Why do we need to save water?'",
                "Ask the student to COMPARE two things. Example: 'How is a river different from a pond?'",
                "Ask the student to PREDICT. Example: 'What would happen if there was no rain for a year?'",
                "Ask the student to give their OPINION with a reason. Example: 'Which is more important — saving water or saving electricity? Why?'",
            ]
            parts.append(f"THINKING QUESTION: {random.choice(thinking_non_maths)}")
        parts.append("This must be a REASONING question, not just a harder calculation.")

    # Visual
    if slot.visual_type:
        parts.append(f"A {slot.visual_type} visual will be shown. Don't describe it in the question.")

    # Language
    if language.lower() == "hindi":
        parts.append("Write in pure Devanagari. No English except proper nouns.")

    # Context for non-word-problem types
    if slot.context and slot.question_type not in ("word_problem", "error_detection"):
        parts.append(f"Context: {slot.context}.")

    return " | ".join(parts)


# ---------------------------------------------------------------------------
# Worksheet metadata builder
# ---------------------------------------------------------------------------
_HINDI_TOPIC_ALIASES = {
    "वचन": "Vachan",
    "लिंग": "Ling",
    "विशेषण": "Visheshan",
    "संज्ञा": "Sangya",
    "सर्वनाम": "Sarvanam",
    "क्रिया": "Kriya",
    "विलोम शब्द": "Vilom Shabd",
    "पर्यायवाची शब्द": "Paryayvachi Shabd",
    "मुहावरे": "Muhavare",
    "काल": "Kaal",
    "वर्णमाला": "Varnamala",
    "मात्रा": "Matras",
    "शब्द रचना": "Shabd Rachna",
    "वाक्य रचना": "Vakya Rachna",
    "कहानी लेखन": "Kahani Lekhan",
    "पत्र लेखन": "Patra Lekhan",
    "संवाद लेखन": "Samvad Lekhan",
    "समास": "Samas",
    "अनुस्वार": "Anusvaar",
}


# Explicit overrides for topics that fuzzy-matching gets wrong
OBJECTIVES_OVERRIDES = {
    "Addition (single digit)": [
        "Add two single-digit numbers with sums up to 18",
        "Solve simple word problems involving addition",
        "Identify addition in everyday situations",
    ],
    "Addition up to 20": [
        "Add two small numbers with sums up to 20",
        "Solve word problems involving addition within 20",
    ],
    "Subtraction (2-digit without borrow)": [
        "Subtract 2-digit numbers without borrowing",
        "Solve word problems involving simple subtraction",
        "Check subtraction using addition",
    ],
    "Subtraction (2-digit with borrow)": [
        "Subtract 2-digit numbers with borrowing (regrouping)",
        "Identify when borrowing is needed in subtraction",
    ],
    "Fractions": [
        "Identify halves, thirds, and quarters of shapes and quantities",
        "Read and write simple fractions (½, ¼, ¾)",
        "Compare simple fractions using pictures",
    ],
    "Decimals": [
        "Read and write decimal numbers up to two decimal places",
        "Compare decimal numbers using place value",
        "Apply decimals to money and measurement contexts",
    ],
    "Food and Digestion": [
        "Identify different types of food and their nutrients",
        "Describe the basic process of digestion",
        "Explain the importance of a balanced diet",
    ],
    "Subtraction (no borrow)": [
        "Subtract 2-digit numbers without borrowing",
        "Solve word problems involving simple subtraction",
        "Check subtraction using addition",
    ],
    "Subtraction (without borrow)": [
        "Subtract 2-digit numbers without borrowing",
        "Solve word problems involving simple subtraction",
        "Check subtraction using addition",
    ],
    "Multiplication": [
        "Multiply numbers using repeated addition and tables",
        "Solve multiplication word problems",
        "Recall multiplication facts",
    ],
    "Multiplication (2-digit)": [
        "Multiply 2-digit numbers by 1-digit and small 2-digit numbers",
        "Solve multiplication word problems with realistic scenarios",
    ],
    "Tenses": [
        "Identify simple present, past, and future tenses",
        "Change sentences from one tense to another",
        "Use correct tense in fill-in-the-blank sentences",
    ],
    "Two Letter Words": [
        "Read and write two-letter Hindi words (दो अक्षर वाले शब्द)",
        "Form two-letter words from given letters",
        "Identify two-letter words in simple sentences",
    ],
}


def _build_worksheet_meta(topic: str, grade_level: str, subject: str) -> dict:
    """Build worksheet metadata from learning objectives with scored fuzzy matching."""
    objectives = _match_learning_objectives(topic, grade_level, subject)

    return {
        "title": f"Worksheet: {topic}",
        "skill_focus": objectives[0] if objectives else f"Practice {topic}",
        "common_mistake": "",  # Gemini will fill this
        "parent_tip": "",  # Gemini will fill this
        "learning_objectives": objectives[:3],  # Cap at 3
    }


def _match_learning_objectives(topic: str, grade_level: str, subject: str) -> list[str]:
    """Match topic to learning objectives with scored matching + grade penalty."""
    _STOP_WORDS = {"and", "the", "of", "in", "for", "with", "without", "no", "to", "a", "an"}

    # 0. Check explicit overrides first (handles common fuzzy-match failures)
    base_topic_for_override = re.sub(r"\s*\(Class\s*\d+\)\s*", "", topic, flags=re.IGNORECASE).strip()
    if base_topic_for_override in OBJECTIVES_OVERRIDES:
        return OBJECTIVES_OVERRIDES[base_topic_for_override]
    if topic in OBJECTIVES_OVERRIDES:
        return OBJECTIVES_OVERRIDES[topic]

    # 1. Exact match
    if topic in LEARNING_OBJECTIVES:
        return LEARNING_OBJECTIVES[topic]

    # 2. Strip grade suffix: "Water (Class 3)" → "Water"
    base_topic = re.sub(r"\s*\(Class\s*\d+\)\s*", "", topic, flags=re.IGNORECASE).strip()

    # 3. Try base topic exact match
    if base_topic in LEARNING_OBJECTIVES:
        return LEARNING_OBJECTIVES[base_topic]

    # 3.5. Hindi alias match: वचन → Vachan
    for hindi_name, latin_name in _HINDI_TOPIC_ALIASES.items():
        if hindi_name in topic:
            for key, val in LEARNING_OBJECTIVES.items():
                if latin_name.lower() in key.lower():
                    return val

    # 4. Scored matching across all keys
    base_lower = base_topic.lower()
    grade_num = re.search(r"\d+", str(grade_level))
    grade_str = f"class {grade_num.group()}" if grade_num else ""

    best_match = None
    best_score = 0

    for key, val in LEARNING_OBJECTIVES.items():
        key_base = re.sub(r"\s*\(Class\s*\d+\)\s*", "", key, flags=re.IGNORECASE).strip().lower()

        # Extract grade from key
        key_grade = re.search(r"class\s*(\d+)", key, re.IGNORECASE)
        key_grade_str = f"class {key_grade.group(1)}" if key_grade else ""

        # Score the match
        score = 0

        # Exact base match (after stripping grade)
        if base_lower == key_base:
            score = 100
        # Base topic starts with key base or vice versa
        elif base_lower.startswith(key_base) or key_base.startswith(base_lower):
            score = 70
        # First word matches (e.g., "Addition" matches "Addition (carries)")
        elif base_lower.split()[0] == key_base.split()[0]:
            score = 50
        # Key words overlap
        else:
            base_words = set(base_lower.split()) - _STOP_WORDS
            key_words = set(key_base.split()) - _STOP_WORDS
            if base_words and key_words:
                overlap = len(base_words & key_words) / len(base_words | key_words)
                if overlap >= 0.4:
                    score = int(overlap * 40)

        # Grade match bonus/penalty — ONLY match same grade
        if grade_str and key_grade_str:
            if grade_str == key_grade_str:
                score += 20  # same grade bonus
            else:
                score = max(0, score - 30)  # different grade penalty

        if score > best_score:
            best_score = score
            best_match = val

    # Only accept matches above threshold
    if best_match and best_score >= 40:
        return best_match

    # 5. Generate grade-appropriate fallback objectives
    return _generate_fallback_objectives(topic, grade_level, subject)


def _generate_fallback_objectives(topic: str, grade_level: str, subject: str) -> list[str]:
    """Generate specific fallback objectives when no match found."""
    base = re.sub(r"\s*\(Class\s*\d+\)\s*", "", topic, flags=re.IGNORECASE).strip()

    if subject.lower() in ("maths", "mathematics", "math"):
        return [
            f"Solve problems involving {base}",
            f"Apply {base} concepts to word problems",
            f"Identify and correct common mistakes in {base}",
        ]
    elif subject.lower() == "english":
        return [
            f"Identify and use {base} correctly in sentences",
            f"Apply knowledge of {base} in reading and writing",
        ]
    elif subject.lower() == "hindi":
        return [
            f"{base} की पहचान करना और सही उपयोग करना",
            f"{base} के नियमों को वाक्यों में लागू करना",
        ]
    elif subject.lower() in ("science", "evs"):
        return [
            f"Understand key concepts related to {base}",
            f"Apply knowledge of {base} to real-world situations",
            f"Observe and describe phenomena related to {base}",
        ]
    else:
        return [
            f"Understand and apply concepts of {base}",
            f"Demonstrate knowledge of {base} through problem-solving",
        ]


# ---------------------------------------------------------------------------
# Main entry: build_slots()
# ---------------------------------------------------------------------------
def build_slots(
    board: str,
    grade_level: str,
    subject: str,
    topic: str,
    difficulty: str,
    num_questions: int,
    problem_style: str,
    language: str,
    adaptive_config: dict | None = None,
) -> SlotBuilderOutput:
    """Build a complete slot skeleton. Zero LLM calls.

    Parameters match WorksheetGenerationRequest fields.
    Returns SlotBuilderOutput with slots and worksheet_meta.
    """
    # --- Step 1: Load grade profile ---
    grade_num = int(re.search(r"\d+", str(grade_level)).group()) if re.search(r"\d+", str(grade_level)) else 3
    grade_profiles = _load_grade_profiles()
    grade_profile = grade_profiles.get(str(grade_num), grade_profiles.get("3", {}))
    age_range = grade_profile.get("age_range", "8-9")
    max_words = grade_profile.get("answer_constraints", {}).get("max_words", 25)
    forbidden_types = grade_profile.get("forbidden_question_types", [])

    # --- Step 2: Load topic profile ---
    profile = get_topic_profile(topic, subject)
    if not profile:
        # Fallback: generic profile
        profile = {
            "allowed_skill_tags": ["general"],
            "default_recipe": [{"skill_tag": "general", "count": num_questions}],
        }

    # --- Step 3: Scale recipe ---
    recipe = _scale_recipe(profile, num_questions)

    # --- Step 4: Expand recipe into individual slots ---
    expanded_tags: list[str] = []
    for item in recipe:
        for _ in range(item["count"]):
            expanded_tags.append(item["skill_tag"])
    # Ensure exact count
    while len(expanded_tags) < num_questions:
        expanded_tags.append(expanded_tags[0] if expanded_tags else "general")
    expanded_tags = expanded_tags[:num_questions]

    # --- Step 5: Assign role + difficulty based on difficulty param ---
    # If adaptive_config is available, override the difficulty distribution
    if adaptive_config:
        mastery = adaptive_config.get("mastery_level", "unknown")
        accuracy = adaptive_config.get("accuracy", 0)

        if mastery == "mastered" and accuracy >= 85:
            # Child has mastered this — push harder regardless of selected difficulty
            dist = {"recognition": 0.10, "application": 0.40, "stretch": 0.50}
        elif mastery == "improving" and accuracy >= 65:
            # Child is improving — balanced challenge
            dist = {"recognition": 0.20, "application": 0.50, "stretch": 0.30}
        elif mastery == "learning" or accuracy < 50:
            # Child is struggling — more scaffolding
            dist = {"recognition": 0.50, "application": 0.40, "stretch": 0.10}
        else:
            dist = DIFFICULTY_DISTRIBUTION.get(difficulty, DIFFICULTY_DISTRIBUTION["medium"])
    else:
        dist = DIFFICULTY_DISTRIBUTION.get(difficulty, DIFFICULTY_DISTRIBUTION["medium"])
    n_recognition = max(1, round(num_questions * dist["recognition"]))
    n_application = max(1, round(num_questions * dist["application"]))
    n_stretch = num_questions - n_recognition - n_application

    # Build difficulty assignments
    difficulty_assignments: list[tuple[str, str]] = []  # (role, difficulty_level)
    for _ in range(n_recognition):
        difficulty_assignments.append(("recognition", "easy"))
    for _ in range(n_application):
        difficulty_assignments.append(("application", "medium"))
    for _ in range(n_stretch):
        difficulty_assignments.append(("thinking", "hard"))
    # Pad or trim
    while len(difficulty_assignments) < num_questions:
        difficulty_assignments.append(("application", "medium"))
    difficulty_assignments = difficulty_assignments[:num_questions]

    # --- Step 6: Create slots ---
    is_maths = subject.lower() in ("maths", "mathematics", "math")
    operation = _detect_maths_operation(topic, " ".join(expanded_tags)) if is_maths else None

    # Check for mandatory visuals
    mandatory_visual = None
    topic_lower = topic.lower()
    for key, vis_type in MANDATORY_VISUAL_TOPICS.items():
        if key in topic_lower:
            mandatory_visual = vis_type
            break

    # Pick contexts and objects
    contexts = pick_contexts(subject, num_questions)
    from .context_pools import pick_objects

    objects = pick_objects(grade_num, num_questions)
    used_names: list[str] = []

    # Detect error_detection forbidden
    error_det_forbidden = any("error_detection" in ft for ft in forbidden_types)

    slots: list[Slot] = []
    for i, skill_tag in enumerate(expanded_tags):
        # Determine natural role from skill tag
        natural_role = _skill_to_role(skill_tag)
        assigned_role, assigned_diff = difficulty_assignments[i]

        # Respect natural role for error_detection/thinking
        if natural_role in ("error_detection", "thinking"):
            final_role = natural_role
            # If difficulty says "easy" but role is thinking/error_detection, set medium
            final_diff = max(assigned_diff, "medium", key=lambda x: ["easy", "medium", "hard"].index(x))
        else:
            final_role = assigned_role
            final_diff = assigned_diff

        # Check forbidden types
        if error_det_forbidden and final_role == "error_detection":
            final_role = "application"

        # Question type
        q_type = _skill_to_question_type(skill_tag)

        # Check if error_detection type is forbidden
        if error_det_forbidden and q_type == "error_detection":
            q_type = "short_answer"
            final_role = "application"

        # Numbers (maths only)
        numbers = None
        wrong_answer = None
        if is_maths and operation:
            numbers = _generate_numbers(grade_num, operation, skill_tag)
        elif is_maths:
            # Try to detect from skill_tag
            skill_op = _detect_maths_operation("", skill_tag)
            if skill_op:
                numbers = _generate_numbers(grade_num, skill_op, skill_tag)

        # Wrong answer for error_detection
        if q_type == "error_detection" and numbers and numbers.get("answer") is not None:
            wrong_answer = _generate_wrong_answer(numbers["answer"], operation)

        # Visual assignment
        visual_type = None
        visual_data = None
        if mandatory_visual:
            # At least 50% get mandatory visual
            if i < math.ceil(num_questions * 0.5):
                visual_type = mandatory_visual
        elif problem_style == "visual":
            if random.random() < 0.8:
                visual_type = _pick_visual_type(topic, is_maths)
        elif problem_style == "mixed":
            if random.random() < 0.5:
                visual_type = _pick_visual_type(topic, is_maths)

        if visual_type:
            visual_data = _compute_visual_data(visual_type, numbers, grade_num)

        # Image keywords — auto-assign for Class 1-2, optional for Class 3
        image_kw = None
        auto_image_rate = 0.0
        if grade_num <= 2:
            auto_image_rate = 0.5  # 50% of questions get images
        elif grade_num == 3:
            auto_image_rate = 0.25  # 25% of questions get images

        # Override with problem_style if explicitly set
        if problem_style == "visual":
            auto_image_rate = 0.8
        elif problem_style == "mixed":
            auto_image_rate = max(auto_image_rate, 0.5)

        # Don't add images if this slot already has a visual_type (e.g., pie_fraction, clock)
        if visual_type:
            image_kw = None
        elif auto_image_rate > 0 and random.random() < auto_image_rate:
            # Find relevant images for this topic
            image_kw = _get_topic_images(topic, subject, slot_num=i)

            if not image_kw:
                # Fallback: subject-level images
                available_kw = _get_image_keywords_for_subject(subject)
                if available_kw:
                    image_kw = random.sample(available_kw, min(2, len(available_kw)))

        # Names for this slot (avoid adjacent repeats)
        slot_names = pick_names(1, exclude=used_names[-3:] if used_names else None)
        used_names.extend(slot_names)

        slot = Slot(
            slot_number=i + 1,
            question_type=q_type,
            role=final_role,
            difficulty=final_diff,
            skill_tag=skill_tag,
            numbers=numbers,
            wrong_answer=wrong_answer,
            visual_type=visual_type,
            visual_data=visual_data,
            context=contexts[i % len(contexts)] if contexts else "",
            names=slot_names,
            image_keywords=image_kw,
            max_words=max_words,
            age_range=age_range,
            context_object=objects[i % len(objects)] if objects else None,
        )

        # Build LLM instruction
        slot.llm_instruction = _build_llm_instruction(slot, topic, subject, language, grade_num)

        # If images are assigned, tell the LLM about them
        if image_kw and not slot.llm_instruction.startswith("SPECIFIC TASK"):
            image_names = [IMAGE_REGISTRY[k]["alt"] for k in image_kw if k in IMAGE_REGISTRY]
            if image_names:
                slot.llm_instruction += (
                    f" | Images shown with this question: {', '.join(image_names)}."
                    " You can reference these images in the question text"
                    " (e.g., 'Look at the picture and answer')."
                )

        slots.append(slot)

    # --- Step 6b: Deduplicate number pairs ---
    seen_pairs: set[tuple] = set()
    for slot in slots:
        if slot.numbers:
            pair_key = (slot.numbers.get("a"), slot.numbers.get("b"))
            if pair_key in seen_pairs:
                # Regenerate this slot's numbers
                for _attempt in range(10):
                    new_nums = _generate_numbers(grade_num, operation, slot.skill_tag)
                    if new_nums:
                        new_key = (new_nums.get("a"), new_nums.get("b"))
                        if new_key not in seen_pairs:
                            slot.numbers = new_nums
                            # Rebuild instruction with new numbers
                            slot.llm_instruction = _build_llm_instruction(slot, topic, subject, language, grade_num)
                            pair_key = new_key
                            break
            seen_pairs.add(pair_key)

    # --- Step 6c: Deduplicate answers (no answer 3+ times) ---
    if is_maths:
        answer_counts: dict[int, list[int]] = {}  # answer → [slot indices]
        for idx, slot in enumerate(slots):
            if slot.numbers and slot.numbers.get("answer") is not None:
                ans = slot.numbers["answer"]
                answer_counts.setdefault(ans, []).append(idx)

        for ans, indices in answer_counts.items():
            if len(indices) >= 3:
                # Keep first 2, regenerate the rest
                for regen_idx in indices[2:]:
                    for attempt in range(20):
                        new_nums = _generate_numbers(grade_num, operation, slots[regen_idx].skill_tag)
                        if new_nums and new_nums.get("answer") != ans:
                            existing_answers = {
                                s.numbers["answer"] for s in slots if s.numbers and s.numbers.get("answer") is not None
                            }
                            if new_nums["answer"] not in existing_answers or attempt > 15:
                                slots[regen_idx].numbers = new_nums
                                slots[regen_idx].llm_instruction = _build_llm_instruction(
                                    slots[regen_idx], topic, subject, language, grade_num
                                )
                                break

    # --- Step 7: Enforce type minimums ---
    _enforce_type_minimums(slots, num_questions, error_det_forbidden)

    # Rebuild LLM instructions for any slots whose type was changed
    for slot in slots:
        slot.llm_instruction = _build_llm_instruction(slot, topic, subject, language, grade_num)

    # --- Step 8: Build worksheet meta ---
    worksheet_meta = _build_worksheet_meta(topic, grade_level, subject)

    # Add adaptive info to meta if present
    if adaptive_config:
        worksheet_meta["adaptive_info"] = {
            "adapted": True,
            "mastery_level": adaptive_config.get("mastery_level"),
            "accuracy": adaptive_config.get("accuracy"),
            "total_attempts": adaptive_config.get("total_attempts"),
        }

    return SlotBuilderOutput(slots=slots, worksheet_meta=worksheet_meta)


def _pick_visual_type(topic: str, is_maths: bool) -> str | None:
    """Pick a suitable visual type for a slot."""
    topic_lower = topic.lower()
    # Check mandatory topics first
    for key, vis_type in MANDATORY_VISUAL_TOPICS.items():
        if key in topic_lower:
            return vis_type

    if is_maths:
        maths_visuals = ["object_group", "number_line", "base_ten_regrouping"]
        return random.choice(maths_visuals)
    return None


def _enforce_type_minimums(slots: list[Slot], num_questions: int, error_det_forbidden: bool):
    """Enforce minimum question type distribution."""
    type_counts = {}
    for s in slots:
        type_counts[s.question_type] = type_counts.get(s.question_type, 0) + 1

    # At least 1 true_false
    if type_counts.get("true_false", 0) == 0:
        # Convert one recognition MCQ to true_false
        for s in slots:
            if s.question_type == "mcq" and s.role == "recognition":
                s.question_type = "true_false"
                break
        else:
            # Convert any MCQ
            for s in slots:
                if s.question_type == "mcq":
                    s.question_type = "true_false"
                    break
            else:
                # Convert last short_answer
                for s in reversed(slots):
                    if s.question_type == "short_answer":
                        s.question_type = "true_false"
                        break

    # Recount
    type_counts = {}
    for s in slots:
        type_counts[s.question_type] = type_counts.get(s.question_type, 0) + 1

    # At least 30% MCQ
    min_mcq = max(1, math.ceil(num_questions * 0.3))
    mcq_count = type_counts.get("mcq", 0)
    if mcq_count < min_mcq:
        deficit = min_mcq - mcq_count
        for s in slots:
            if deficit <= 0:
                break
            if s.question_type in ("short_answer", "fill_blank") and s.role in ("recognition", "application"):
                s.question_type = "mcq"
                deficit -= 1

    # Recount
    type_counts = {}
    for s in slots:
        type_counts[s.question_type] = type_counts.get(s.question_type, 0) + 1

    # At least 1 fill_blank
    if type_counts.get("fill_blank", 0) == 0:
        for s in slots:
            if s.question_type == "short_answer" and s.role != "thinking":
                s.question_type = "fill_blank"
                break

    # Rebuild LLM instructions after type changes (skip — instructions already have context)
