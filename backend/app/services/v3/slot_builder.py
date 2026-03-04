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
    "hard": {"recognition": 0.10, "application": 0.30, "stretch": 0.60},
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
    if "add" in combined or "sum" in combined:
        return "addition"
    if "sub" in combined or "borrow" in combined or "minus" in combined:
        return "subtraction"
    if "mul" in combined or "times" in combined or "table" in combined:
        return "multiplication"
    if "div" in combined or "share" in combined or "quotient" in combined:
        return "division"
    return None


def _generate_numbers(grade_num: int, operation: str | None, skill_tag: str) -> dict | None:
    """Generate grade-appropriate numbers for maths slots."""
    if not operation:
        return None

    # Try scenario pools first
    pool = None
    if operation == "addition":
        pool = _load_scenario_pool("maths_addition")
    elif operation == "subtraction":
        pool = _load_scenario_pool("maths_subtraction") if _load_scenario_pool("maths_subtraction") else None

    class_key = f"class_{grade_num}"
    if pool and class_key in pool:
        pairs = pool[class_key].get("pairs", [])
        if pairs:
            pair = random.choice(pairs)
            if operation == "addition":
                return {"a": pair["a"], "b": pair["b"], "answer": pair.get("sum", pair["a"] + pair["b"])}
            elif operation == "subtraction":
                return {"a": pair["a"], "b": pair["b"], "answer": pair.get("diff", pair["a"] - pair["b"])}

    # Generate random numbers based on grade
    if operation == "addition":
        return _random_addition(grade_num)
    elif operation == "subtraction":
        return _random_subtraction(grade_num)
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


def _random_subtraction(grade: int) -> dict:
    nums = _random_addition(grade)
    # Swap to make a > b for subtraction
    a, b = nums["answer"], nums["a"]
    return {"a": a, "b": b, "answer": a - b}


def _random_multiplication(grade: int) -> dict:
    if grade <= 2:
        a = random.randint(2, 5)
        b = random.randint(2, 5)
    elif grade == 3:
        a = random.randint(2, 10)
        b = random.randint(2, 10)
    elif grade == 4:
        a = random.randint(10, 999)
        b = random.randint(10, 99)
    else:
        a = random.randint(100, 999)
        b = random.randint(10, 99)
    return {"a": a, "b": b, "answer": a * b}


def _random_division(grade: int) -> dict:
    if grade <= 2:
        b = random.randint(2, 5)
        answer = random.randint(2, 5)
    elif grade == 3:
        b = random.randint(2, 10)
        answer = random.randint(2, 10)
    elif grade == 4:
        b = random.randint(2, 20)
        answer = random.randint(10, 50)
    else:
        b = random.randint(2, 50)
        answer = random.randint(10, 100)
    a = b * answer  # ensure clean division
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

    # Type and topic
    parts.append(f"Question type: {slot.question_type}")
    parts.append(f"Topic: {topic}")
    parts.append(f"Age range: {slot.age_range}")
    parts.append(f"Max words: {slot.max_words}")
    parts.append(f"Cognitive role: {slot.role}")
    parts.append(f"Difficulty: {slot.difficulty}")

    # Maths with pre-computed numbers
    if slot.numbers:
        a, b, ans = slot.numbers.get("a"), slot.numbers.get("b"), slot.numbers.get("answer")
        if a is not None and b is not None and ans is not None:
            parts.append(f"Use the numbers {a} and {b}. Correct answer: {ans}.")

    # Format-specific instructions
    if slot.question_type == "word_problem":
        if slot.context:
            parts.append(f"Set in a {slot.context} context.")
        if slot.names:
            parts.append(f"Use character(s): {', '.join(slot.names)}.")
        parts.append("Tell a mini-story, don't just state bare numbers.")

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
        tf_value = random.choice([True, False])
        parts.append(f"Write a statement that is {tf_value}.")

    elif slot.question_type == "mcq":
        is_maths = subject.lower() in ("maths", "mathematics", "math")
        if is_maths:
            parts.append("Write the question text only. Options will be generated separately.")
        else:
            parts.append("4 options. 1 clearly correct, 3 clearly wrong. At least 1 obviously wrong.")

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
def _build_worksheet_meta(topic: str, grade_level: str, subject: str) -> dict:
    """Build worksheet metadata from learning objectives."""
    objectives = LEARNING_OBJECTIVES.get(topic, [])
    # Try fuzzy match if exact not found
    if not objectives:
        topic_lower = topic.lower()
        for key, val in LEARNING_OBJECTIVES.items():
            if topic_lower in key.lower() or key.lower() in topic_lower:
                objectives = val
                break

    return {
        "title": f"Worksheet: {topic}",
        "skill_focus": objectives[0] if objectives else f"Practice {topic}",
        "common_mistake": "",  # Gemini will fill this
        "parent_tip": "",  # Gemini will fill this
        "learning_objectives": objectives or [f"Practice and master {topic}"],
    }


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

        # Image keywords for non-maths visual
        image_kw = None
        if not is_maths and problem_style in ("visual", "mixed") and not visual_type:
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
        )

        # Build LLM instruction
        slot.llm_instruction = _build_llm_instruction(slot, topic, subject, language, grade_num)

        slots.append(slot)

    # --- Step 7: Enforce type minimums ---
    _enforce_type_minimums(slots, num_questions, error_det_forbidden)

    # --- Step 8: Build worksheet meta ---
    worksheet_meta = _build_worksheet_meta(topic, grade_level, subject)

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
