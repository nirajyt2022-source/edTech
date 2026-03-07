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
    # Application suffixes (English/Hindi grammar tags like tenses_change, voice_convert)
    if any(tag.endswith(s) for s in ("_use", "_change", "_convert", "_write", "_rewrite", "_rearrange", "_answer")):
        return "application"
    # Representation suffixes (English/Hindi grammar tags like blanks_fill, sentences_complete)
    if any(tag.endswith(s) for s in ("_fill", "_complete", "_expand", "_match")):
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
    "data handling": "pictograph",
    "pictograph": "pictograph",
    "tally": "pictograph",
    "percentage": "percentage_bar",
    "percent": "percentage_bar",
    "bar graph": "bar_chart",
    "bar chart": "bar_chart",
    "pie chart": "bar_chart",
}


# ---------------------------------------------------------------------------
# Object Emoji Registry — colorful emoji objects for picture addition/subtraction
# ---------------------------------------------------------------------------
OBJECT_EMOJI_REGISTRY = {
    "fruits": [
        {"emoji": "🍎", "name": "apple", "name_hi": "सेब"},
        {"emoji": "🥭", "name": "mango", "name_hi": "आम"},
        {"emoji": "🍌", "name": "banana", "name_hi": "केला"},
        {"emoji": "🍊", "name": "orange", "name_hi": "संतरा"},
        {"emoji": "🍇", "name": "grapes", "name_hi": "अंगूर"},
    ],
    "nature": [
        {"emoji": "🌸", "name": "flower", "name_hi": "फूल"},
        {"emoji": "⭐", "name": "star", "name_hi": "तारा"},
        {"emoji": "🦋", "name": "butterfly", "name_hi": "तितली"},
        {"emoji": "🐦", "name": "bird", "name_hi": "चिड़िया"},
    ],
    "indian": [
        {"emoji": "🪁", "name": "kite", "name_hi": "पतंग"},
        {"emoji": "🪔", "name": "diya", "name_hi": "दीया"},
        {"emoji": "🏏", "name": "cricket bat", "name_hi": "बल्ला"},
    ],
    "school": [
        {"emoji": "✏️", "name": "pencil", "name_hi": "पेंसिल"},
        {"emoji": "📕", "name": "book", "name_hi": "किताब"},
        {"emoji": "🎒", "name": "school bag", "name_hi": "बस्ता"},
    ],
}


# ---------------------------------------------------------------------------
# Word-Picture Bank — for picture_word_match visual type
# ---------------------------------------------------------------------------
WORD_PICTURE_BANK = {
    "english": [
        {"emoji": "🐄", "word": "cow", "wrong": ["cat", "cup", "car"]},
        {"emoji": "🐕", "word": "dog", "wrong": ["doll", "duck", "door"]},
        {"emoji": "🏠", "word": "house", "wrong": ["horse", "hat", "hen"]},
        {"emoji": "🌳", "word": "tree", "wrong": ["train", "truck", "table"]},
        {"emoji": "☀️", "word": "sun", "wrong": ["son", "sit", "six"]},
        {"emoji": "🐟", "word": "fish", "wrong": ["fire", "five", "fan"]},
        {"emoji": "🍎", "word": "apple", "wrong": ["ant", "arm", "axe"]},
        {"emoji": "📕", "word": "book", "wrong": ["ball", "bat", "bed"]},
    ],
    "hindi": [
        {"emoji": "🐄", "word": "गाय", "wrong": ["बकरी", "भैंस", "घोड़ा"]},
        {"emoji": "🏠", "word": "घर", "wrong": ["गाँव", "गमला", "गुड़िया"]},
        {"emoji": "☀️", "word": "सूरज", "wrong": ["चाँद", "तारा", "बादल"]},
        {"emoji": "🍎", "word": "सेब", "wrong": ["आम", "केला", "अंगूर"]},
        {"emoji": "📕", "word": "किताब", "wrong": ["कलम", "कुर्सी", "कमरा"]},
        {"emoji": "🐦", "word": "चिड़िया", "wrong": ["तितली", "मछली", "बिल्ली"]},
    ],
}

# ---------------------------------------------------------------------------
# Topic-specific picture-word banks for picture_word_match visuals
# ---------------------------------------------------------------------------
PICTURE_WORD_BANKS: dict[str, list[dict]] = {
    "alphabet": [
        {"letter": "A", "word": "Apple", "emoji": "🍎", "word_hi": "सेब"},
        {"letter": "B", "word": "Ball", "emoji": "⚽", "word_hi": "गेंद"},
        {"letter": "C", "word": "Cat", "emoji": "🐱", "word_hi": "बिल्ली"},
        {"letter": "D", "word": "Dog", "emoji": "🐕", "word_hi": "कुत्ता"},
        {"letter": "E", "word": "Elephant", "emoji": "🐘", "word_hi": "हाथी"},
        {"letter": "F", "word": "Fish", "emoji": "🐟", "word_hi": "मछली"},
        {"letter": "G", "word": "Grapes", "emoji": "🍇", "word_hi": "अंगूर"},
        {"letter": "H", "word": "House", "emoji": "🏠", "word_hi": "घर"},
        {"letter": "I", "word": "Ice cream", "emoji": "🍦", "word_hi": "आइसक्रीम"},
        {"letter": "J", "word": "Jug", "emoji": "🫗", "word_hi": "जग"},
        {"letter": "K", "word": "Kite", "emoji": "🪁", "word_hi": "पतंग"},
        {"letter": "L", "word": "Lion", "emoji": "🦁", "word_hi": "शेर"},
        {"letter": "M", "word": "Mango", "emoji": "🥭", "word_hi": "आम"},
        {"letter": "N", "word": "Nest", "emoji": "🪺", "word_hi": "घोंसला"},
        {"letter": "O", "word": "Orange", "emoji": "🍊", "word_hi": "संतरा"},
        {"letter": "P", "word": "Parrot", "emoji": "🦜", "word_hi": "तोता"},
        {"letter": "Q", "word": "Queen", "emoji": "👑", "word_hi": "रानी"},
        {"letter": "R", "word": "Rabbit", "emoji": "🐰", "word_hi": "खरगोश"},
        {"letter": "S", "word": "Sun", "emoji": "☀️", "word_hi": "सूरज"},
        {"letter": "T", "word": "Tree", "emoji": "🌳", "word_hi": "पेड़"},
        {"letter": "U", "word": "Umbrella", "emoji": "☂️", "word_hi": "छाता"},
        {"letter": "V", "word": "Van", "emoji": "🚐", "word_hi": "गाड़ी"},
        {"letter": "W", "word": "Watch", "emoji": "⌚", "word_hi": "घड़ी"},
        {"letter": "X", "word": "Xylophone", "emoji": "🎵", "word_hi": "ज़ाइलोफोन"},
        {"letter": "Y", "word": "Yak", "emoji": "🐃", "word_hi": "याक"},
        {"letter": "Z", "word": "Zebra", "emoji": "🦓", "word_hi": "ज़ेबरा"},
    ],
    "phonics": [
        {"letter": "A", "word": "Apple", "emoji": "🍎", "sound": "/æ/"},
        {"letter": "B", "word": "Ball", "emoji": "⚽", "sound": "/b/"},
        {"letter": "C", "word": "Cat", "emoji": "🐱", "sound": "/k/"},
        {"letter": "M", "word": "Mango", "emoji": "🥭", "sound": "/m/"},
        {"letter": "S", "word": "Sun", "emoji": "☀️", "sound": "/s/"},
        {"letter": "T", "word": "Tree", "emoji": "🌳", "sound": "/t/"},
        {"letter": "D", "word": "Dog", "emoji": "🐕", "sound": "/d/"},
        {"letter": "F", "word": "Fish", "emoji": "🐟", "sound": "/f/"},
        {"letter": "G", "word": "Grapes", "emoji": "🍇", "sound": "/g/"},
        {"letter": "H", "word": "House", "emoji": "🏠", "sound": "/h/"},
    ],
    "animals": [
        {"word": "Cow", "emoji": "🐄", "fact": "gives milk", "word_hi": "गाय"},
        {"word": "Dog", "emoji": "🐕", "fact": "guards the house", "word_hi": "कुत्ता"},
        {"word": "Cat", "emoji": "🐱", "fact": "catches mice", "word_hi": "बिल्ली"},
        {"word": "Elephant", "emoji": "🐘", "fact": "has a trunk", "word_hi": "हाथी"},
        {"word": "Lion", "emoji": "🦁", "fact": "is king of jungle", "word_hi": "शेर"},
        {"word": "Parrot", "emoji": "🦜", "fact": "can talk", "word_hi": "तोता"},
        {"word": "Fish", "emoji": "🐟", "fact": "lives in water", "word_hi": "मछली"},
        {"word": "Butterfly", "emoji": "🦋", "fact": "has colorful wings", "word_hi": "तितली"},
        {"word": "Rabbit", "emoji": "🐰", "fact": "loves carrots", "word_hi": "खरगोश"},
        {"word": "Horse", "emoji": "🐴", "fact": "can run fast", "word_hi": "घोड़ा"},
    ],
    "fruits": [
        {"word": "Apple", "emoji": "🍎", "color": "red", "word_hi": "सेब"},
        {"word": "Mango", "emoji": "🥭", "color": "yellow", "word_hi": "आम"},
        {"word": "Banana", "emoji": "🍌", "color": "yellow", "word_hi": "केला"},
        {"word": "Orange", "emoji": "🍊", "color": "orange", "word_hi": "संतरा"},
        {"word": "Grapes", "emoji": "🍇", "color": "purple", "word_hi": "अंगूर"},
        {"word": "Watermelon", "emoji": "🍉", "color": "green", "word_hi": "तरबूज"},
    ],
    "hindi_two_letter": [
        {"word": "घर", "emoji": "🏠", "english": "house"},
        {"word": "कप", "emoji": "☕", "english": "cup"},
        {"word": "बस", "emoji": "🚌", "english": "bus"},
        {"word": "जल", "emoji": "💧", "english": "water"},
        {"word": "फल", "emoji": "🍎", "english": "fruit"},
        {"word": "वन", "emoji": "🌳", "english": "forest"},
        {"word": "रथ", "emoji": "🛞", "english": "chariot"},
        {"word": "मन", "emoji": "❤️", "english": "heart"},
    ],
    "hindi_three_letter": [
        {"word": "केला", "emoji": "🍌", "english": "banana"},
        {"word": "किताब", "emoji": "📕", "english": "book"},
        {"word": "कमल", "emoji": "🪷", "english": "lotus"},
        {"word": "नदी", "emoji": "🏞️", "english": "river"},
        {"word": "पतंग", "emoji": "🪁", "english": "kite"},
        {"word": "बादल", "emoji": "☁️", "english": "cloud"},
    ],
    "nouns": [
        {"word": "Book", "emoji": "📕", "type": "common noun", "word_hi": "किताब"},
        {"word": "Dog", "emoji": "🐕", "type": "common noun", "word_hi": "कुत्ता"},
        {"word": "School", "emoji": "🏫", "type": "common noun", "word_hi": "स्कूल"},
        {"word": "Sun", "emoji": "☀️", "type": "common noun", "word_hi": "सूरज"},
        {"word": "Chair", "emoji": "🪑", "type": "common noun", "word_hi": "कुर्सी"},
        {"word": "Flower", "emoji": "🌸", "type": "common noun", "word_hi": "फूल"},
    ],
    "seasons": [
        {"word": "Summer", "emoji": "☀️", "description": "hot, sunny", "word_hi": "गर्मी"},
        {"word": "Winter", "emoji": "❄️", "description": "cold, foggy", "word_hi": "सर्दी"},
        {"word": "Rainy", "emoji": "🌧️", "description": "wet, cloudy", "word_hi": "बारिश"},
        {"word": "Spring", "emoji": "🌸", "description": "flowers bloom", "word_hi": "बसंत"},
    ],
    "body_parts": [
        {"word": "Eye", "emoji": "👁️", "function": "see", "word_hi": "आँख"},
        {"word": "Ear", "emoji": "👂", "function": "hear", "word_hi": "कान"},
        {"word": "Nose", "emoji": "👃", "function": "smell", "word_hi": "नाक"},
        {"word": "Hand", "emoji": "✋", "function": "hold things", "word_hi": "हाथ"},
        {"word": "Foot", "emoji": "🦶", "function": "walk", "word_hi": "पैर"},
    ],
    "food": [
        {"word": "Rice", "emoji": "🍚", "group": "grain", "word_hi": "चावल"},
        {"word": "Roti", "emoji": "🫓", "group": "grain", "word_hi": "रोटी"},
        {"word": "Milk", "emoji": "🥛", "group": "dairy", "word_hi": "दूध"},
        {"word": "Carrot", "emoji": "🥕", "group": "vegetable", "word_hi": "गाजर"},
        {"word": "Egg", "emoji": "🥚", "group": "protein", "word_hi": "अंडा"},
    ],
    "family": [
        {"word": "माँ", "emoji": "👩", "english": "Mother"},
        {"word": "पापा", "emoji": "👨", "english": "Father"},
        {"word": "दादी", "emoji": "👵", "english": "Grandmother"},
        {"word": "दादा", "emoji": "👴", "english": "Grandfather"},
        {"word": "भाई", "emoji": "👦", "english": "Brother"},
        {"word": "बहन", "emoji": "👧", "english": "Sister"},
    ],
}


# ---------------------------------------------------------------------------
# Diagram Bank — for labeled_diagram visual type
# ---------------------------------------------------------------------------
DIAGRAM_BANK = {
    "plant_parts": {
        "title": "Parts of a Plant",
        "labels": ["flower", "leaf", "stem", "root"],
        "labels_hi": ["फूल", "पत्ती", "तना", "जड़"],
        "diagram_type": "vertical_labeled",
    },
    "body_parts": {
        "title": "Parts of the Body",
        "labels": ["head", "arm", "leg", "foot"],
        "labels_hi": ["सिर", "बाज़ू", "टांग", "पैर"],
        "diagram_type": "body_outline",
    },
    "computer_parts": {
        "title": "Parts of a Computer",
        "labels": ["monitor", "keyboard", "mouse", "CPU"],
        "labels_hi": ["मॉनिटर", "कीबोर्ड", "माउस", "सीपीयू"],
        "diagram_type": "horizontal_labeled",
    },
}


# ---------------------------------------------------------------------------
# Match Bank — for match_columns visual type
# ---------------------------------------------------------------------------
MATCH_BANK = {
    "animal_habitat": [
        {"left": "🐟", "left_label": "Fish", "right": "🌊", "right_label": "Water"},
        {"left": "🐦", "left_label": "Bird", "right": "🌳", "right_label": "Tree/Nest"},
        {"left": "🐫", "left_label": "Camel", "right": "🏜️", "right_label": "Desert"},
        {"left": "🐒", "left_label": "Monkey", "right": "🌳", "right_label": "Forest"},
        {"left": "🐄", "left_label": "Cow", "right": "🏡", "right_label": "Farm"},
    ],
    "animal_food": [
        {"left": "🐄", "left_label": "Cow", "right": "🌾", "right_label": "Grass"},
        {"left": "🐱", "left_label": "Cat", "right": "🐟", "right_label": "Fish"},
        {"left": "🐒", "left_label": "Monkey", "right": "🍌", "right_label": "Banana"},
        {"left": "🐰", "left_label": "Rabbit", "right": "🥕", "right_label": "Carrot"},
    ],
}


# ---------------------------------------------------------------------------
# Difficulty distribution
# ---------------------------------------------------------------------------
DIFFICULTY_DISTRIBUTION = {
    "easy": {"recognition": 0.60, "application": 0.30, "stretch": 0.10},
    "medium": {"recognition": 0.30, "application": 0.50, "stretch": 0.20},
    "hard": {"recognition": 0.20, "application": 0.40, "stretch": 0.40},
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
    # Fraction topics often contain words like "add/subtract". Detect fraction first
    # so "Fractions (add and subtract)" doesn't get misclassified as whole-number addition.
    if any(
        kw in combined for kw in ("fraction", "fractions", "halves", "quarters", "half", "quarter", "thirds", "third")
    ):
        return "fraction"
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
    if any(kw in combined for kw in ("decimal",)):
        return "decimal"
    if any(kw in combined for kw in ("place value", "numbers up to", "large number")):
        return "place_value"
    if any(kw in combined for kw in ("percent", "percentage")):
        return "percentage"
    if any(kw in combined for kw in ("geometry", "angle", "line segment")):
        return "geometry"
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
    elif operation == "fraction":
        return _random_fraction(grade_num)
    elif operation == "decimal":
        return _random_decimal(grade_num)
    elif operation == "place_value":
        return _random_place_value(grade_num)
    elif operation == "percentage":
        return _random_percentage(grade_num)
    elif operation == "geometry":
        return _random_geometry(grade_num)
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
    """Generate subtraction pair.

    If allow_borrow=True (for "with borrow" topics), GUARANTEE at least one
    digit position requires borrowing.
    If allow_borrow=False, ensure NO digit position requires borrowing.
    """
    max_attempts = 50
    for _ in range(max_attempts):
        if grade == 1:
            a = random.randint(11, 18)
            b = random.randint(3, min(9, a - 2))
        elif grade == 2:
            a = random.randint(20, 99)
            b = random.randint(10, a - 3)
        elif grade == 3:
            a = random.randint(120, 999)
            b = random.randint(100, a - 10)
        elif grade == 4:
            a = random.randint(1000, 9999)
            b = random.randint(100, a - 10)
        else:
            a = random.randint(10000, 99999)
            b = random.randint(1000, a - 10)

        # Ensure minimum pedagogical difference (avoid trivial 39-38=1)
        if a - b < 3:
            continue

        # Check if borrowing is needed
        sa = str(a).zfill(len(str(max(a, b))))
        sb = str(b).zfill(len(str(max(a, b))))
        needs_borrow = any(int(da) < int(db) for da, db in zip(reversed(sa), reversed(sb)))

        if allow_borrow and needs_borrow:
            return {"a": a, "b": b, "answer": a - b}
        elif not allow_borrow and not needs_borrow:
            return {"a": a, "b": b, "answer": a - b}

    # Fallback: guaranteed borrow pair per grade
    _BORROW_FALLBACKS = {
        1: {"a": 15, "b": 8, "answer": 7},
        2: {"a": 42, "b": 17, "answer": 25},
        3: {"a": 503, "b": 248, "answer": 255},
        4: {"a": 5032, "b": 1748, "answer": 3284},
        5: {"a": 50321, "b": 17486, "answer": 32835},
    }
    if allow_borrow:
        fb = _BORROW_FALLBACKS.get(grade, _BORROW_FALLBACKS[2])
        return dict(fb)
    if grade <= 2:
        a_ones = random.randint(5, 9)
        b_ones = random.randint(1, a_ones)
        a_tens = random.randint(3, 9)
        b_tens = random.randint(1, a_tens)
        a = a_tens * 10 + a_ones
        b = b_tens * 10 + b_ones
    else:
        a, b = 87, 43  # safe no-borrow fallback
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


def _random_fraction(grade: int) -> dict:
    """Generate a fraction question with pre-computed answer."""
    if grade <= 3:
        # Simple fractions: halves, thirds, and quarters of small numbers
        denominator = random.choice([2, 3, 4])
        if denominator == 4:
            whole = random.choice([4, 8, 12, 16, 20, 24, 28, 32])
        elif denominator == 3:
            whole = random.choice([3, 6, 9, 12, 15, 18, 21, 24])
        else:
            whole = random.choice([2, 4, 6, 8, 10, 12, 14, 16, 18, 20])
        numerator = 1  # unit fractions for Class 3
        answer = whole // denominator
    elif grade == 4:
        # Equivalent fractions, non-unit fractions
        denominator = random.choice([2, 3, 4, 5, 6, 8])
        numerator = random.randint(1, denominator - 1)
        whole = denominator * random.randint(2, 8)
        answer = (whole * numerator) // denominator
    else:
        # Class 5: fraction addition/subtraction with unlike denominators
        from math import gcd

        denoms = [2, 3, 4, 5, 6, 8]
        for _retry in range(10):
            d1 = random.choice(denoms)
            d2 = random.choice([d for d in denoms if d != d1])
            n1 = random.randint(1, d1 - 1)
            n2 = random.randint(1, d2 - 1)
            lcd = (d1 * d2) // gcd(d1, d2)

            op = random.choice(["add", "subtract"])
            if op == "add":
                result_num = n1 * (lcd // d1) + n2 * (lcd // d2)
            else:
                result_num = n1 * (lcd // d1) - n2 * (lcd // d2)
                if result_num <= 0:
                    # Flip to addition if subtraction would be zero/negative
                    result_num = n1 * (lcd // d1) + n2 * (lcd // d2)

            # Simplify the result
            g = gcd(abs(result_num), lcd)
            numerator = result_num // g
            denominator = lcd // g

            # Reject degenerate fractions (1/1, 0/n)
            if numerator > 0 and numerator != denominator:
                break
        # else: use whatever we got on last attempt (extremely rare)

        # Keep a, b for backward compat (use first operand values)
        whole = n1
        answer = f"{numerator}/{denominator}"

        return {
            "a": whole,
            "b": d1,
            "answer": answer,
            "numerator": numerator,
            "denominator": denominator,
            "fraction_str": f"{n1}/{d1}",
        }

    return {
        "a": whole,
        "b": denominator,
        "answer": answer,
        "numerator": numerator,
        "denominator": denominator,
        "fraction_str": f"{numerator}/{denominator}",
    }


def _random_decimal(grade: int) -> dict:
    """Generate decimal number pairs with pre-computed answer."""
    if grade <= 4:
        # Tenths only
        a = round(random.randint(10, 99) / 10, 1)  # 1.0 to 9.9
        b = round(random.randint(10, 99) / 10, 1)
    else:
        # Hundredths
        a = round(random.randint(100, 999) / 100, 2)  # 1.00 to 9.99
        b = round(random.randint(100, 999) / 100, 2)

    # Randomly pick operation
    op = random.choice(["add", "subtract", "compare"])
    if op == "add":
        answer = round(a + b, 2)
    elif op == "subtract":
        if a < b:
            a, b = b, a
        answer = round(a - b, 2)
    else:  # compare
        answer = a if a > b else b  # the larger one

    return {
        "a": a,
        "b": b,
        "answer": answer,
        "operation": op,
    }


def _random_place_value(grade: int) -> dict:
    """Generate place-value numbers with decomposition."""
    if grade <= 2:
        n = random.randint(100, 999)
        comparison = random.randint(100, 999)
        while comparison == n:
            comparison = random.randint(100, 999)
        return {
            "a": n,
            "b": comparison,
            "answer": n,
            "hundreds": (n // 100) % 10,
            "tens": (n // 10) % 10,
            "ones": n % 10,
        }
    elif grade <= 4:
        digits = 4 if grade == 3 else 5
        lo = 10 ** (digits - 1)
        hi = 10**digits - 1
        n = random.randint(lo, hi)
        comparison = random.randint(lo, hi)
        while comparison == n:
            comparison = random.randint(lo, hi)
        return {"a": n, "b": comparison, "answer": n}
    else:
        n = random.randint(100000, 1000000)
        comparison = random.randint(100000, 1000000)
        while comparison == n:
            comparison = random.randint(100000, 1000000)
        return {"a": n, "b": comparison, "answer": n}


def _random_percentage(grade: int) -> dict:
    """Generate percentage question with VERIFIED integer answer."""
    for _ in range(50):
        percent = random.choice([10, 20, 25, 50, 75])
        if grade <= 4:
            base = random.choice([100, 200, 400, 500, 1000])
        else:
            base = random.choice([50, 100, 200, 250, 400, 500])
        result = base * percent / 100
        if result == int(result):  # only accept clean integer answers
            return {"a": base, "b": percent, "answer": int(result), "operation": "percentage"}
    # Safe fallback
    return {"a": 100, "b": 50, "answer": 50, "operation": "percentage"}


def _random_geometry(grade: int) -> dict:
    """Generate angle problems (complementary or supplementary)."""
    angle_pool = [30, 40, 45, 50, 60, 70, 75, 80]
    kind = random.choice(["complementary", "supplementary"])
    a = random.choice(angle_pool)
    if kind == "complementary":
        b = 90 - a
    else:
        b = 180 - a
    return {"a": a, "b": b, "answer": b, "angle_type": kind}


def _generate_wrong_answer(correct: int | str, operation: str | None) -> int | str:
    """Generate a plausible wrong answer for error detection."""
    if isinstance(correct, str) and "/" in correct:
        # Fraction answer like "7/12" — tweak numerator
        from math import gcd

        parts = correct.split("/")
        num, den = int(parts[0]), int(parts[1])
        offset = random.choice([1, -1, 2, -2])
        wrong_num = num + offset
        if wrong_num <= 0:
            wrong_num = num + abs(offset)
        g = gcd(abs(wrong_num), den)
        return f"{wrong_num // g}/{den // g}"
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
def _compute_visual_data(
    visual_type: str,
    numbers: dict | None,
    grade_num: int,
    slot_number: int = 0,
    topic: str = "",
    language: str = "English",
) -> dict | None:
    """Compute visual_data for a given visual type."""
    if visual_type == "pie_fraction":
        if numbers:
            if "numerator" in numbers and "denominator" in numbers:
                return {"numerator": numbers["numerator"], "denominator": numbers["denominator"]}
            if "a" in numbers and "b" in numbers:
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
        DENOMINATIONS = [
            {"value": 1, "type": "coin", "label": "₹1", "color": "#B8860B"},
            {"value": 2, "type": "coin", "label": "₹2", "color": "#C0C0C0"},
            {"value": 5, "type": "coin", "label": "₹5", "color": "#C0C0C0"},
            {"value": 10, "type": "coin", "label": "₹10", "color": "#DAA520"},
            {"value": 10, "type": "note", "label": "₹10", "color": "#F97316"},
            {"value": 20, "type": "note", "label": "₹20", "color": "#16A34A"},
            {"value": 50, "type": "note", "label": "₹50", "color": "#2563EB"},
            {"value": 100, "type": "note", "label": "₹100", "color": "#7C3AED"},
        ]
        if numbers and numbers.get("answer"):
            target = numbers["answer"]
        else:
            target = random.choice([5, 10, 15, 20, 25, 50])
        items = []
        remaining = target
        for denom in sorted(DENOMINATIONS, key=lambda x: -x["value"]):
            while remaining >= denom["value"] and len(items) < 8:
                items.append(denom)
                remaining -= denom["value"]
            if remaining == 0:
                break
        return {
            "items": [
                {"value": d["value"], "type": d["type"], "label": d["label"], "color": d["color"]} for d in items
            ],
            "total": target,
            "currency": "INR",
        }

    if visual_type == "abacus":
        if numbers and "a" in numbers:
            n = numbers["a"]
            return {"hundreds": (n // 100) % 10, "tens": (n // 10) % 10, "ones": n % 10}
        return {"hundreds": random.randint(1, 9), "tens": random.randint(0, 9), "ones": random.randint(0, 9)}

    if visual_type == "shapes":
        SHAPE_LIBRARY = [
            {"name": "circle", "sides": 0, "color": "#EF4444"},
            {"name": "triangle", "sides": 3, "color": "#F59E0B"},
            {"name": "square", "sides": 4, "color": "#3B82F6"},
            {"name": "rectangle", "sides": 4, "color": "#10B981"},
            {"name": "pentagon", "sides": 5, "color": "#8B5CF6"},
            {"name": "hexagon", "sides": 6, "color": "#EC4899"},
        ]
        target = SHAPE_LIBRARY[(slot_number or 0) % len(SHAPE_LIBRARY)]
        others = [s for s in SHAPE_LIBRARY if s["name"] != target["name"]]
        random.shuffle(others)
        display_shapes = [target] + others[:3]
        random.shuffle(display_shapes)
        return {
            "shapes": [{"name": s["name"], "sides": s["sides"], "color": s["color"]} for s in display_shapes],
            "target": target["name"],
            "target_index": display_shapes.index(target),
        }

    if visual_type == "grid_symmetry":
        size = 4
        filled = [[random.randint(0, size - 1), random.randint(0, size // 2 - 1)] for _ in range(3)]
        return {"grid_size": size, "filled_cells": filled, "fold_axis": "vertical"}

    if visual_type == "number_line":
        if numbers and "a" in numbers:
            a = numbers["a"]
            b = numbers.get("b", 3)
            operation = numbers.get("operation", "addition")
            if "subtract" in str(operation):
                end_val = a - b
                direction = "backward"
            else:
                end_val = a + b
                direction = "forward"
            line_end = max(end_val + 3, 20)
            return {
                "start": 0,
                "end": min(line_end, 25),
                "step": 1,
                "hops_from": a,
                "hops_count": b,
                "hops_direction": direction,
                "highlight": end_val,
                "highlight_start": a,
            }
        return {"start": 0, "end": 20, "step": 2, "highlight": None}

    if visual_type == "object_group":
        # Pick a different emoji category per slot for variety
        categories = list(OBJECT_EMOJI_REGISTRY.keys())
        cat_idx = (slot_number or 0) % len(categories)
        category = categories[cat_idx]
        objects = OBJECT_EMOJI_REGISTRY[category]
        obj_idx = ((slot_number or 0) * 3) % len(objects)
        obj = objects[obj_idx]

        if numbers and "a" in numbers:
            a = numbers["a"]
            b = numbers.get("b", 0)
            ans_val = numbers.get("answer", 0)
            ans_num = ans_val if isinstance(ans_val, (int, float)) else 0
            op = "+" if ans_num > max(a, b) else "-"
            return {
                "groups": [
                    {"count": a, "type": "emoji", "emoji": obj["emoji"], "label": obj["name"]},
                    {"count": b, "type": "emoji", "emoji": obj["emoji"], "label": obj["name"]},
                ],
                "operation": op,
                "object_name": obj["name"],
                "object_name_hi": obj["name_hi"],
                "object_emoji": obj["emoji"],
            }
        count = random.randint(3, 10)
        return {
            "groups": [{"count": count, "type": "emoji", "emoji": obj["emoji"], "label": obj["name"]}],
            "operation": "count",
            "object_name": obj["name"],
            "object_emoji": obj["emoji"],
        }

    if visual_type == "picture_word_match":
        # Select topic-specific bank for richer, context-aware visuals
        topic_lower = topic.lower()
        bank_key = "animals"  # default
        if "alphabet" in topic_lower or "varnamala" in topic_lower:
            bank_key = "alphabet"
        elif "phonics" in topic_lower:
            bank_key = "phonics"
        elif "vowel" in topic_lower or "swar" in topic_lower:
            bank_key = "alphabet"
        elif "consonant" in topic_lower or "vyanjan" in topic_lower:
            bank_key = "alphabet"
        elif "animal" in topic_lower:
            bank_key = "animals"
        elif "food" in topic_lower or "nutrition" in topic_lower or "diet" in topic_lower:
            bank_key = "food"
        elif "noun" in topic_lower:
            bank_key = "nouns"
        elif "season" in topic_lower:
            bank_key = "seasons"
        elif "body" in topic_lower:
            bank_key = "body_parts"
        elif "family" in topic_lower or "parivar" in topic_lower:
            bank_key = "family"
        elif "fruit" in topic_lower or "vocabulary" in topic_lower:
            bank_key = "fruits"
        elif "two letter" in topic_lower or "do akshar" in topic_lower:
            bank_key = "hindi_two_letter"
        elif "three letter" in topic_lower or "teen akshar" in topic_lower:
            bank_key = "hindi_three_letter"
        elif language.lower() == "hindi":
            bank_key = "hindi_two_letter"

        if bank_key in PICTURE_WORD_BANKS:
            bank = PICTURE_WORD_BANKS[bank_key]
            idx = (slot_number or 0) % len(bank)
            item = bank[idx]
            return {
                "emoji": item["emoji"],
                "word": item.get("word", ""),
                "letter": item.get("letter", ""),
                "correct_word": item.get("word", ""),
                "bank_key": bank_key,
                # Pass through all extra fields for LLM context
                **{k: v for k, v in item.items() if k not in ("emoji",)},
            }

        # Fallback to legacy flat bank
        lang_key = "hindi" if language == "Hindi" else "english"
        bank = WORD_PICTURE_BANK.get(lang_key, WORD_PICTURE_BANK["english"])
        idx = (slot_number or 0) % len(bank)
        item = bank[idx]
        return {
            "emoji": item["emoji"],
            "correct_word": item["word"],
            "word": item["word"],
            "wrong_words": item["wrong"],
            "bank_key": "legacy",
        }

    if visual_type == "labeled_diagram":
        topic_lower = topic.lower()
        diagram_key = None
        if "plant" in topic_lower:
            diagram_key = "plant_parts"
        elif "body" in topic_lower:
            diagram_key = "body_parts"
        elif "computer" in topic_lower:
            diagram_key = "computer_parts"

        if diagram_key:
            diagram = DIAGRAM_BANK[diagram_key]
            blank_idx = (slot_number or 0) % len(diagram["labels"])
            return {
                "diagram_type": diagram["diagram_type"],
                "title": diagram["title"],
                "labels": diagram["labels"],
                "labels_hi": diagram["labels_hi"],
                "blank_index": blank_idx,
            }
        return None

    if visual_type == "match_columns":
        bank_key = "animal_habitat"
        if "food" in topic.lower():
            bank_key = "animal_food"

        items = MATCH_BANK.get(bank_key, MATCH_BANK["animal_habitat"])
        selected = items[:4]
        shuffled_right = selected.copy()
        random.shuffle(shuffled_right)

        return {
            "left": [{"emoji": x["left"], "label": x["left_label"]} for x in selected],
            "right": [{"emoji": x["right"], "label": x["right_label"]} for x in shuffled_right],
            "correct_matches": [selected.index(x) for x in shuffled_right],
        }

    if visual_type == "pattern_tiles":
        PATTERN_SETS = [
            ["🔴", "🔵", "🔴", "🔵", "🔴", "🔵"],
            ["⭐", "❤️", "⭐", "❤️", "⭐", "❤️"],
            ["🌸", "🍃", "🌸", "🍃", "🌸", "🍃"],
            ["🟡", "🟢", "🟡", "🟢", "🟡", "🟢"],
            ["☀️", "🌙", "☀️", "🌙", "☀️", "🌙"],
            ["🍎", "🍌", "🍎", "🍌", "🍎", "🍌"],
            ["🔴", "🔵", "🟢", "🔴", "🔵", "🟢"],
            ["⭐", "⭐", "❤️", "⭐", "⭐", "❤️"],
        ]
        pattern_idx = (slot_number or 0) % len(PATTERN_SETS)
        pattern = PATTERN_SETS[pattern_idx]
        blank_pos = len(pattern) - 1
        return {
            "tiles": pattern,
            "blank_position": blank_pos,
            "answer": pattern[blank_pos],
        }

    if visual_type == "ten_frame":
        if numbers and numbers.get("answer"):
            filled = min(numbers["answer"], 20)
        else:
            filled = random.randint(3, 10)
        ten_colors = ["#6366F1", "#EF4444", "#10B981", "#F59E0B", "#EC4899"]
        color = ten_colors[(slot_number or 0) % len(ten_colors)]
        return {
            "filled": filled,
            "total": 10 if filled <= 10 else 20,
            "color": color,
        }

    if visual_type == "pictograph":
        DATA_SETS = [
            {
                "title": "Favourite Fruits",
                "rows": [
                    {"label": "Apple", "emoji": "🍎", "count": random.randint(2, 6)},
                    {"label": "Mango", "emoji": "🥭", "count": random.randint(2, 6)},
                    {"label": "Banana", "emoji": "🍌", "count": random.randint(2, 6)},
                    {"label": "Orange", "emoji": "🍊", "count": random.randint(2, 6)},
                ],
            },
            {
                "title": "Animals in the Zoo",
                "rows": [
                    {"label": "Lion", "emoji": "🦁", "count": random.randint(1, 5)},
                    {"label": "Elephant", "emoji": "🐘", "count": random.randint(1, 5)},
                    {"label": "Monkey", "emoji": "🐒", "count": random.randint(1, 5)},
                    {"label": "Bird", "emoji": "🐦", "count": random.randint(1, 5)},
                ],
            },
            {
                "title": "Flowers in the Garden",
                "rows": [
                    {"label": "Rose", "emoji": "🌹", "count": random.randint(2, 7)},
                    {"label": "Sunflower", "emoji": "🌻", "count": random.randint(2, 7)},
                    {"label": "Lotus", "emoji": "🪷", "count": random.randint(2, 7)},
                ],
            },
        ]
        dataset = DATA_SETS[(slot_number or 0) % len(DATA_SETS)]
        return {
            "title": dataset["title"],
            "rows": dataset["rows"],
            "scale": 1,
        }

    if visual_type == "array_visual":
        if numbers:
            a = min(numbers.get("a", 3), 6)
            b = min(numbers.get("b", 4), 8)
        else:
            a = random.randint(2, 5)
            b = random.randint(2, 5)
        categories = list(OBJECT_EMOJI_REGISTRY.keys())
        cat = categories[(slot_number or 0) % len(categories)]
        objects = OBJECT_EMOJI_REGISTRY[cat]
        obj = objects[((slot_number or 0) * 7) % len(objects)]
        return {
            "rows": a,
            "cols": b,
            "emoji": obj["emoji"],
            "object_name": obj["name"],
            "answer": a * b,
        }

    if visual_type == "base_ten_regrouping":
        if numbers and "a" in numbers:
            ans_val = numbers.get("answer", 0)
            ans_num = ans_val if isinstance(ans_val, (int, float)) else 0
            op = "addition" if ans_num > numbers["a"] else "subtraction"
            return {"numbers": [numbers["a"], numbers.get("b", 0)], "operation": op}
        return {"numbers": [234, 178], "operation": "addition"}

    if visual_type == "fraction_bar":
        if numbers:
            n = numbers.get("numerator", numbers.get("a", 1))
            d = numbers.get("denominator", numbers.get("b", 4))
            if d == 0:
                d = 4
        else:
            d = random.choice([2, 3, 4, 5, 6])
            n = random.randint(1, d - 1)
        show_comparison = "compar" in topic.lower() or "equivalent" in topic.lower()
        second = None
        if show_comparison:
            d2 = random.choice([2, 3, 4, 5, 6])
            n2 = random.randint(1, d2 - 1)
            second = {"numerator": n2, "denominator": d2}
        colors = ["#6366F1", "#EF4444", "#10B981", "#F59E0B", "#EC4899"]
        color = colors[(slot_number or 0) % len(colors)]
        return {"numerator": n, "denominator": d, "color": color, "second": second, "total_parts": 12}

    if visual_type == "scenario_picture":
        SCENARIO_BANK = {
            "sharing": [
                {
                    "scene": "👧🍎🍎🍎 👦😢",
                    "description": "Priya has 3 apples. Rohan has none and looks sad.",
                    "question": "What should Priya do?",
                },
                {
                    "scene": "👦🖍️🖍️🖍️🖍️ 👧🖍️",
                    "description": "Aarav has 4 crayons. Meera has only 1.",
                    "question": "Is Aarav being kind?",
                },
            ],
            "honesty": [
                {
                    "scene": "👦⚽💔🪟",
                    "description": "Rohan's ball broke the window.",
                    "question": "Should Rohan tell the truth?",
                },
                {
                    "scene": "👧📝✅❌",
                    "description": "Ananya copied her friend's answer in the test.",
                    "question": "Was this the right thing to do?",
                },
            ],
            "kindness": [
                {
                    "scene": "👴🚌👦💺",
                    "description": "An old man is standing on the bus. Aarav has a seat.",
                    "question": "What should Aarav do?",
                },
                {
                    "scene": "👧😢📚 👦😊",
                    "description": "Meera dropped her books. Rohan is walking past.",
                    "question": "How can Rohan be kind?",
                },
            ],
            "hygiene": [
                {"scene": "👦🍽️🤲💧", "description": "Before eating food.", "question": "What should you do first?"},
                {
                    "scene": "👧🤧🤲🧼",
                    "description": "After sneezing.",
                    "question": "What should you do with your hands?",
                },
            ],
            "healthy_eating": [
                {
                    "scene": "🍎🥕🍌 vs 🍕🍬🍫",
                    "description": "Choose what to eat.",
                    "question": "Which group is healthier?",
                },
            ],
        }
        topic_lower = topic.lower()
        bank_key = "sharing"
        for key in SCENARIO_BANK:
            if key.replace("_", " ") in topic_lower or key in topic_lower:
                bank_key = key
                break
        scenarios = SCENARIO_BANK.get(bank_key, SCENARIO_BANK["sharing"])
        idx = (slot_number or 0) % len(scenarios)
        scenario = scenarios[idx]
        return {
            "scene_emoji": scenario["scene"],
            "description": scenario["description"],
            "question": scenario["question"],
        }

    if visual_type == "sequence_pictures":
        SEQUENCE_BANK = {
            "handwashing": {
                "title": "Handwashing Steps",
                "steps": ["🚰", "🧼", "🤲💧", "🧴", "🤲✨"],
                "labels": ["Turn on tap", "Take soap", "Rub hands", "Rinse", "Hands clean!"],
            },
            "plant_growth": {
                "title": "How a Plant Grows",
                "steps": ["🌱", "🌿", "🌻", "🌻🌻"],
                "labels": ["Seed sprouts", "Leaves grow", "Flower blooms", "More flowers!"],
            },
            "morning_routine": {
                "title": "Morning Routine",
                "steps": ["⏰", "🪥", "🚿", "👕", "🍳"],
                "labels": ["Wake up", "Brush teeth", "Bath", "Get dressed", "Eat breakfast"],
            },
            "tense_sequence": {
                "title": "Yesterday → Today → Tomorrow",
                "steps": ["🌅⬅️", "☀️", "🌅➡️"],
                "labels": ["Yesterday (past)", "Today (present)", "Tomorrow (future)"],
            },
        }
        topic_lower = topic.lower()
        bank_key = "morning_routine"
        if "hygiene" in topic_lower or "wash" in topic_lower:
            bank_key = "handwashing"
        elif "plant" in topic_lower or "grow" in topic_lower:
            bank_key = "plant_growth"
        elif "tense" in topic_lower or "yesterday" in topic_lower:
            bank_key = "tense_sequence"
        elif "routine" in topic_lower or "morning" in topic_lower:
            bank_key = "morning_routine"
        seq = SEQUENCE_BANK.get(bank_key, SEQUENCE_BANK["morning_routine"])
        blank_idx = (slot_number or 0) % len(seq["steps"])
        return {"title": seq["title"], "steps": seq["steps"], "labels": seq["labels"], "blank_index": blank_idx}

    if visual_type == "bar_chart":
        CHART_DATA_SETS = [
            {
                "title": "Students' Favourite Sport",
                "bars": [
                    {"label": "Cricket", "value": random.randint(5, 15), "color": "#3B82F6"},
                    {"label": "Football", "value": random.randint(3, 12), "color": "#10B981"},
                    {"label": "Badminton", "value": random.randint(2, 10), "color": "#F59E0B"},
                    {"label": "Kabaddi", "value": random.randint(2, 8), "color": "#EF4444"},
                ],
                "y_label": "Number of Students",
            },
            {
                "title": "Books Read This Month",
                "bars": [
                    {"label": "Aarav", "value": random.randint(2, 8), "color": "#6366F1"},
                    {"label": "Priya", "value": random.randint(3, 10), "color": "#EC4899"},
                    {"label": "Rohan", "value": random.randint(1, 7), "color": "#F97316"},
                    {"label": "Meera", "value": random.randint(4, 9), "color": "#14B8A6"},
                ],
                "y_label": "Books",
            },
        ]
        dataset = CHART_DATA_SETS[(slot_number or 0) % len(CHART_DATA_SETS)]
        return dataset

    if visual_type == "food_plate":
        FOOD_GROUPS = [
            {"name": "Grains", "emoji": "🍚🫓🍞", "color": "#F59E0B", "name_hi": "अनाज"},
            {"name": "Vegetables", "emoji": "🥕🥦🍅", "color": "#16A34A", "name_hi": "सब्ज़ी"},
            {"name": "Fruits", "emoji": "🍎🍌🥭", "color": "#EF4444", "name_hi": "फल"},
            {"name": "Protein", "emoji": "🥚🫘🍗", "color": "#92400E", "name_hi": "प्रोटीन"},
            {"name": "Dairy", "emoji": "🥛🧀", "color": "#3B82F6", "name_hi": "दूध"},
        ]
        blank_idx = (slot_number or 0) % len(FOOD_GROUPS)
        return {
            "groups": [
                {"name": g["name"], "emoji": g["emoji"], "color": g["color"], "name_hi": g["name_hi"]}
                for g in FOOD_GROUPS
            ],
            "blank_index": blank_idx,
        }

    if visual_type == "percentage_bar":
        if numbers:
            percent = numbers.get("b", 25)
            base = numbers.get("a", 100)
        else:
            percent = random.choice([10, 20, 25, 50, 75])
            base = 100
        return {
            "percent": percent,
            "base": base,
            "color": ["#6366F1", "#EF4444", "#10B981", "#F59E0B"][(slot_number or 0) % 4],
        }

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
    # Maths — these topics use SVG visual_types (shapes, money_coins, etc.)
    # so clipart images are skipped by _get_topic_images() for maths subjects.
    "addition": ["apple", "mango", "banana", "flower", "butterfly", "pencil_box"],
    "subtraction": ["apple", "mango", "parrot", "flower", "butterfly"],
    # shapes → removed (uses visual_type), money → removed (uses visual_type=money_coins)
    "time": ["clock", "sun", "moon"],
    "measurement": ["ruler", "thermometer"],
    "numbers": ["apple", "mango", "sun", "pencil_box", "book_open"],
    "multiplication": ["apple", "mango", "flower", "egg"],
    "division": ["apple", "mango", "roti", "egg"],
    "fractions": [],  # uses visual_type=pie_fraction instead
    "data handling": [],
    "spatial": [],
    # English
    "alphabet": ["apple", "cricket", "cat", "dog", "elephant"],
    "nouns": ["dog", "cat", "book_open", "school_bag", "tree"],
    "verbs": ["cricket", "football", "bicycle", "bus"],
    "pronouns": ["family_group", "mother", "father", "baby"],
    "adjectives": ["sun", "flower", "elephant", "ant"],
    "sentences": ["school_bag", "book_open", "pencil_box"],
    "vocabulary": ["cow", "dog", "cat", "mango", "apple", "banana"],
    "phonics": ["apple", "cricket", "cat", "dog", "egg", "fish"],
    "rhyming": ["cat", "parrot", "sun", "car"],
    "greetings": ["family_group", "school_bag"],
    "seasons": ["sunny", "rainy", "snowy", "windy", "cloudy"],
    "family": ["family_group", "grandparents", "mother", "father", "baby"],
    # EVS
    "animals": ["cow", "lion", "tiger", "elephant", "monkey", "parrot", "fish", "butterfly", "rabbit"],
    "plants": ["tree", "flower", "rose", "sunflower", "tulsi", "lotus"],
    "food": ["mango", "apple", "banana", "rice", "roti", "egg", "milk"],
    "body": ["human_body", "eye", "ear", "nose", "tongue", "hand"],
    "water": ["water_drop", "rainy", "pond", "ocean", "water_tap"],
    "shelter": ["family_group", "nest", "dog", "horse"],
    "senses": ["eye", "ear", "nose", "tongue", "hand"],
    "weather": ["sunny", "rainy", "cloudy", "snowy", "windy"],
    "habitats": ["forest", "pond", "desert", "ocean", "farm"],
    "nutrition": ["mango", "apple", "banana", "rice", "roti", "milk", "egg"],
    # Hindi
    "varnamala": ["apple", "mango", "elephant", "flower"],
    "two letter": ["apple", "mango", "book_open", "cricket"],
    "three letter": ["banana", "mango", "apple", "flower"],
    "vachan": ["cow", "cat", "dog", "book_open", "flower"],
    "ling": ["cow", "cat", "dog", "book_open", "flower"],
    "matra": ["apple", "mango", "banana", "elephant"],
    "shabd": ["book_open", "pencil_box", "school_bag", "apple"],
    "vilom": ["sun", "moon", "sunny", "rainy"],
    "family words": ["family_group", "grandparents", "mother", "father"],
    "nature": ["tree", "flower", "sun", "moon", "cloudy"],
    "rhymes": ["butterfly", "flower", "sun", "moon"],
    "kahani": ["book_open", "family_group", "tree", "sun"],
    # Science
    "human body": ["human_body", "eye", "ear", "nose", "hand"],
    "digestion": ["apple", "roti", "rice", "human_body"],
    "air": ["windy", "wind_turbine"],
    "light": ["sun", "light_bulb", "lamp"],
    "magnet": [],
    "force": ["car", "bicycle", "cricket"],
    "energy": ["sun", "light_bulb", "solar_panel"],
    "matter": ["water_drop"],
    # Computer
    "parts of computer": ["desktop_computer", "laptop", "keyboard", "mouse", "monitor"],
    "mouse": ["mouse", "desktop_computer"],
    "keyboard": ["keyboard", "desktop_computer"],
    "typing": ["keyboard", "laptop"],
    "internet": ["laptop", "tablet"],
    "storage": ["usb_drive", "laptop"],
    "output devices": ["monitor", "printer", "speaker", "headphones"],
    "input devices": ["keyboard", "mouse"],
    # Health
    "hygiene": ["toothbrush", "soap", "handwash", "comb", "towel"],
    "exercise": ["cricket", "football", "yoga_pose"],
    "posture": ["yoga_pose"],
    "eating": ["mango", "apple", "roti", "milk"],
    "safety": ["first_aid_kit", "bandage", "water_bottle"],
    "dental": ["toothbrush", "teeth"],
    "sleep": ["sleeping", "moon"],
    # GK
    "india": ["taj_mahal", "red_fort", "india_gate", "indian_flag", "ashoka_chakra"],
    "monuments": ["taj_mahal", "red_fort", "qutub_minar", "gateway_of_india", "india_gate"],
    "national symbols": [
        "indian_flag",
        "ashoka_chakra",
        "national_emblem",
        "lotus_national",
        "tiger_national",
        "peacock_national",
    ],
    "solar system": ["sun", "moon", "earth", "mars", "jupiter", "saturn", "solar_system"],
    "continents": ["globe", "world_map", "continent_asia", "continent_africa", "continent_europe"],
    "festivals": ["diwali", "holi", "eid", "christmas", "republic_day", "independence_day"],
    "musical instruments": ["tabla", "sitar", "flute", "harmonium", "drum"],
    "sports": ["cricket", "football", "badminton", "hockey", "kabaddi"],
}


def _get_topic_images(topic: str, subject: str, slot_num: int = 0) -> list[str] | None:
    """Get 1-2 relevant image keywords for a topic, rotating per slot."""
    # Maths uses SVG-based visuals (number lines, column setups, etc.),
    # not decorative clipart images. Skip image assignment entirely.
    if subject.lower() in ("maths", "math", "mathematics"):
        return None

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
                if isinstance(ans, str) and "/" in str(ans):
                    # Fraction answer — tweak for wrong statement
                    fparts = str(ans).split("/")
                    fn, fd = int(fparts[0]), int(fparts[1])
                    wrong = f"{fn + random.choice([1, -1, 2])}/{fd}"
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

    # Visual — inject specific context so LLM question matches the shown visual
    if slot.visual_type:
        parts.append(f"A {slot.visual_type} visual will be shown. Don't describe it in the question.")
        vd = slot.visual_data or {}

        if slot.visual_type == "object_group" and vd:
            obj_name = vd.get("object_name", "")
            if obj_name:
                parts.append(
                    f"The visual shows {obj_name}s. Use '{obj_name}s' (not generic 'items') in the question text."
                )

        elif slot.visual_type == "picture_word_match" and vd:
            word = vd.get("word", "")
            letter = vd.get("letter", "")
            emoji = vd.get("emoji", "")
            bank_key = vd.get("bank_key", "")
            if bank_key in ("alphabet", "phonics"):
                parts.append(f"VISUAL CONTEXT: A picture of '{word}' ({emoji}) is shown.")
                if letter:
                    parts.append(f"This word starts with letter '{letter}'.")
                parts.append(
                    f"Your question MUST be about '{word}' or the letter '{letter}'. Do NOT ask about any other word or letter."
                )
            elif bank_key in ("animals", "fruits", "food", "body_parts", "seasons"):
                fact = vd.get("fact", vd.get("description", vd.get("function", vd.get("group", ""))))
                parts.append(f"VISUAL CONTEXT: A picture of '{word}' ({emoji}) is shown.")
                if fact:
                    parts.append(f"Fact about {word}: {fact}.")
                parts.append(f"Your question MUST be about '{word}'. Do NOT ask about any other object.")
            elif bank_key == "nouns":
                parts.append(f"VISUAL CONTEXT: A picture of '{word}' ({emoji}) is shown.")
                parts.append(f"'{word}' is a {vd.get('type', 'noun')}.")
                parts.append(f"Your question MUST use '{word}' as the example. Do NOT use any other word.")
            elif bank_key in ("hindi_two_letter", "hindi_three_letter", "family"):
                english = vd.get("english", "")
                parts.append(f"VISUAL CONTEXT: A picture of '{english}' ({emoji}) is shown.")
                parts.append(f"The Hindi word is '{word}'.")
                parts.append(f"Your question MUST be about the word '{word}'. Do NOT ask about any other word.")
            elif word:
                parts.append(f"VISUAL CONTEXT: A picture ({emoji}) of '{word}' is shown.")
                parts.append(f"Your question MUST reference '{word}'. Do NOT ask about anything else.")

        elif slot.visual_type == "labeled_diagram" and vd:
            labels = vd.get("labels", [])
            blank_idx = vd.get("blank_index", -1)
            title = vd.get("title", "")
            parts.append(f"VISUAL CONTEXT: A '{title}' diagram is shown with labels: {', '.join(labels)}.")
            if 0 <= blank_idx < len(labels):
                parts.append(f"The label '{labels[blank_idx]}' is hidden. Ask the student to identify it.")

        elif slot.visual_type == "match_columns" and vd:
            left = vd.get("left", [])
            right = vd.get("right", [])
            left_items = [f"{x.get('emoji', '')} {x.get('label', '')}" for x in left]
            right_items = [f"{x.get('emoji', '')} {x.get('label', '')}" for x in right]
            parts.append("VISUAL CONTEXT: A matching exercise is shown.")
            parts.append(f"Left column: {', '.join(left_items)}")
            parts.append(f"Right column: {', '.join(right_items)}")
            parts.append("Ask the student to match them correctly.")

        elif slot.visual_type == "scenario_picture" and vd:
            scene = vd.get("scene_emoji", "")
            desc = vd.get("description", "")
            question = vd.get("question", "")
            parts.append(f"VISUAL CONTEXT: A scene is shown: {scene}")
            parts.append(f"Description: {desc}")
            parts.append(f"Ask: {question}")

        elif slot.visual_type == "sequence_pictures" and vd:
            labels = vd.get("labels", [])
            blank_idx = vd.get("blank_index", -1)
            parts.append(f"VISUAL CONTEXT: A sequence is shown: {' → '.join(labels)}")
            if 0 <= blank_idx < len(labels):
                parts.append(f"Step '{labels[blank_idx]}' is hidden. Ask what step is missing.")

        elif slot.visual_type == "food_plate" and vd:
            groups = vd.get("groups", [])
            blank_idx = vd.get("blank_index", -1)
            group_names = [g.get("name", "") for g in groups]
            parts.append(f"VISUAL CONTEXT: A balanced diet plate is shown with food groups: {', '.join(group_names)}")
            if 0 <= blank_idx < len(groups):
                parts.append(f"The '{group_names[blank_idx]}' group is hidden. Ask the student to identify it.")

        elif slot.visual_type == "bar_chart" and vd:
            bars = vd.get("bars", [])
            title = vd.get("title", "")
            bar_desc = [f"{b.get('label')}: {b.get('value')}" for b in bars]
            parts.append(f"VISUAL CONTEXT: A bar chart titled '{title}' is shown with data: {', '.join(bar_desc)}")
            parts.append("Ask a question that requires reading the chart data.")

        elif slot.visual_type == "pictograph" and vd:
            rows = vd.get("rows", [])
            title = vd.get("title", "")
            row_desc = [f"{r.get('label')}: {r.get('count')} {r.get('emoji', '')}" for r in rows]
            parts.append(f"VISUAL CONTEXT: A pictograph titled '{title}' is shown: {', '.join(row_desc)}")
            parts.append("Ask a question about this specific data (which has most, how many total, etc.)")

        elif slot.visual_type == "percentage_bar" and vd:
            percent = vd.get("percent", 25)
            parts.append(f"VISUAL CONTEXT: A percentage bar showing {percent}% is shaded.")
            parts.append(f"Use {percent}% in your question.")

        elif slot.visual_type == "fraction_bar" and vd:
            n = vd.get("numerator", 1)
            d = vd.get("denominator", 4)
            parts.append(f"VISUAL CONTEXT: A fraction bar showing {n}/{d} is shaded.")
            parts.append(f"Your question MUST reference the fraction {n}/{d}.")
            second = vd.get("second")
            if second:
                parts.append(f"A second bar shows {second['numerator']}/{second['denominator']}. Ask to compare them.")

        elif slot.visual_type == "ten_frame" and vd:
            filled = vd.get("filled", 5)
            parts.append(f"VISUAL CONTEXT: A ten frame with {filled} filled dots is shown. Ask about this count.")

        elif slot.visual_type == "shapes" and vd:
            shapes = vd.get("shapes", [])
            target = vd.get("target", "")
            shape_names = [s.get("name", "") for s in shapes]
            parts.append(
                f"VISUAL CONTEXT: These shapes are shown: {', '.join(shape_names)}. The target shape is '{target}'."
            )
            parts.append(f"Ask about '{target}' specifically.")

        elif slot.visual_type == "array_visual" and vd:
            rows_n = vd.get("rows", 3)
            cols_n = vd.get("cols", 4)
            parts.append(f"VISUAL CONTEXT: An array of {rows_n} rows × {cols_n} columns is shown.")
            parts.append(f"Ask about {rows_n} × {cols_n} = {rows_n * cols_n}.")

        elif slot.visual_type == "pie_fraction" and vd:
            n = vd.get("numerator", 1)
            d = vd.get("denominator", 4)
            parts.append(f"VISUAL CONTEXT: A pie chart showing {n}/{d} shaded is shown.")
            parts.append(f"Your question MUST reference the fraction {n}/{d}.")

        elif slot.visual_type == "clock" and vd:
            h = vd.get("hour", 3)
            m = vd.get("minute", 0)
            time_str = f"{h}:{m:02d}"
            parts.append(f"VISUAL CONTEXT: A clock showing {time_str} is displayed.")
            parts.append(f"Your question MUST ask about the time {time_str}.")

        elif slot.visual_type == "money_coins" and vd:
            total = vd.get("total", 0)
            items = vd.get("items", [])
            item_desc = [i.get("label", "") for i in items]
            parts.append(f"VISUAL CONTEXT: Coins/notes shown: {', '.join(item_desc)}. Total = ₹{total}.")
            parts.append(f"Your question MUST be about these coins/notes totalling ₹{total}.")

        elif slot.visual_type == "number_line" and vd:
            hf = vd.get("hops_from")
            hc = vd.get("hops_count")
            hl = vd.get("highlight")
            if hf is not None and hc is not None:
                parts.append(f"VISUAL CONTEXT: A number line with hops from {hf}, {hc} jumps, landing at {hl}.")
            else:
                parts.append(
                    f"VISUAL CONTEXT: A number line from {vd.get('start', 0)} to {vd.get('end', 20)} is shown."
                )

        elif slot.visual_type == "pattern_tiles" and vd:
            tiles = vd.get("tiles", [])
            blank_pos = vd.get("blank_position", -1)
            parts.append(f"VISUAL CONTEXT: A pattern is shown: {' '.join(tiles[:blank_pos])} ?")
            parts.append(f"Ask what comes next. Answer: {vd.get('answer', '')}.")

        elif slot.visual_type == "base_ten_regrouping" and vd:
            nums = vd.get("numbers", [])
            op = vd.get("operation", "addition")
            if len(nums) >= 2:
                parts.append(f"VISUAL CONTEXT: Base-ten blocks for {nums[0]} and {nums[1]} ({op}) are shown.")

        elif slot.visual_type == "abacus" and vd:
            h = vd.get("hundreds", 0)
            t = vd.get("tens", 0)
            o = vd.get("ones", 0)
            val = h * 100 + t * 10 + o
            parts.append(f"VISUAL CONTEXT: An abacus shows {h} hundreds, {t} tens, {o} ones = {val}.")
            parts.append(f"Your question MUST ask about the number {val}.")

        elif slot.visual_type == "grid_symmetry" and vd:
            parts.append("VISUAL CONTEXT: A grid with some cells filled is shown. Ask about symmetry.")

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


# Pre-written common mistakes and parent tips per topic category
TOPIC_GUIDANCE = {
    # Maths — SPECIFIC entries first (matched by longest-key-first logic below)
    "addition up to 20": {
        "common_mistake": "Children count on their fingers but start counting from the first number instead of the next. For 8+5, they count 8,9,10,11,12 (4 steps) instead of 9,10,11,12,13 (5 steps).",
        "parent_tip": "Use objects (laddoos, coins) to show adding. Practice 'counting on' — start from the bigger number and count up.",
    },
    "addition (without carry)": {
        "common_mistake": "Children count on their fingers but start counting from the first number instead of the next.",
        "parent_tip": "Use real objects (laddoos, coins) to practice addition. Start with small numbers and build up.",
    },
    "addition (carries)": {
        "common_mistake": "Children forget to carry over when the sum exceeds 9 in a column.",
        "parent_tip": "Use place value columns on paper. Write ones and tens separately. Practice carrying with small numbers first.",
    },
    "addition (2-digit with carry)": {
        "common_mistake": "Children forget to carry over when the sum of ones exceeds 9. For 28+15, they write 313 instead of 43.",
        "parent_tip": "Use place value columns on paper. Write ones and tens separately. Practice carrying with small numbers first.",
    },
    "subtraction (no borrow)": {
        "common_mistake": "Children subtract the larger digit from the smaller regardless of position (e.g., in 47-23, they do 7-3=4 correctly, but in 42-27, they do 7-2=5 instead of recognizing they need to regroup).",
        "parent_tip": "Practice with coins — removing coins from a pile makes subtraction concrete. Emphasize: always subtract bottom from top.",
    },
    "subtraction (without borrow)": {
        "common_mistake": "Children subtract the larger digit from the smaller regardless of position.",
        "parent_tip": "Practice with coins — removing coins from a pile makes subtraction concrete.",
    },
    "subtraction within 20": {
        "common_mistake": "Children count backwards incorrectly — for 13-5, they count 13,12,11,10,9 (4 steps) instead of 12,11,10,9,8 (5 steps).",
        "parent_tip": "Use a number line. Start at 13, jump back 5 times. Where do you land?",
    },
    # Generic entries (matched only if no specific entry above matched)
    "addition": {
        "common_mistake": "Children often forget to carry over when the sum exceeds 9 in a column.",
        "parent_tip": "Use real objects (laddoos, coins) to practice addition. Start with small numbers and build up.",
    },
    "subtraction": {
        "common_mistake": "Children subtract the smaller digit from the larger regardless of position (e.g., 42-17: they do 7-2=5 instead of borrowing).",
        "parent_tip": "Practice with coins — removing coins from a pile makes subtraction concrete.",
    },
    "multiplication": {
        "common_mistake": "Children confuse multiplication with addition (e.g., 3×4=7 instead of 12).",
        "parent_tip": "Use arrays — arrange objects in rows and columns to visualize multiplication.",
    },
    "division": {
        "common_mistake": "Children confuse division with subtraction or forget that division means equal sharing.",
        "parent_tip": "Practice sharing — divide laddoos equally among family members.",
    },
    "fractions": {
        "common_mistake": "Children think 1/3 is bigger than 1/2 because 3 > 2.",
        "parent_tip": "Cut a roti into halves, then quarters — let your child see and touch the parts.",
    },
    "decimals": {
        "common_mistake": "Children think 0.45 > 0.5 because 45 > 5.",
        "parent_tip": "Use money: ₹0.50 vs ₹0.45 — which can buy more? This makes decimals real.",
    },
    "time": {
        "common_mistake": "Children confuse hour and minute hands on a clock.",
        "parent_tip": "Point out the clock at home at meal times — 'It's 8 o'clock, time for dinner!'",
    },
    "money": {
        "common_mistake": "Children forget to give back correct change.",
        "parent_tip": "Let your child buy small items at a shop and count the change.",
    },
    "shapes": {
        "common_mistake": "Children confuse similar shapes like rectangle and square.",
        "parent_tip": "Point out shapes around the house — door (rectangle), clock (circle), sandwich (triangle).",
    },
    "measurement": {
        "common_mistake": "Children confuse units (cm vs m, g vs kg).",
        "parent_tip": "Measure things at home together — height of a door, weight of a bag of rice.",
    },
    "numbers": {
        "common_mistake": "Children reverse digits when writing numbers (e.g., write 31 as 13).",
        "parent_tip": "Practice number writing daily — 5 numbers before breakfast!",
    },
    "percentage": {
        "common_mistake": "Children forget that percent means 'out of 100'.",
        "parent_tip": "Use exam marks: 'You got 80 out of 100 — that's 80%!'",
    },
    "perimeter": {
        "common_mistake": "Children confuse perimeter (around) with area (inside).",
        "parent_tip": "Walk around the room — that's perimeter. The floor inside — that's area.",
    },
    "area": {
        "common_mistake": "Children confuse perimeter with area or forget to use square units.",
        "parent_tip": "Use tiles on the floor — count how many tiles cover the room.",
    },
    "geometry": {
        "common_mistake": "Children mix up angles — they think bigger-looking angles are always larger.",
        "parent_tip": "Open a book to different angles — show that angle size is about the opening, not the line length.",
    },
    "pattern": {
        "common_mistake": "Children continue patterns mechanically without understanding the rule.",
        "parent_tip": "Ask 'What's the rule?' before continuing any pattern.",
    },
    "data": {
        "common_mistake": "Children misread graph scales or count bars instead of reading values.",
        "parent_tip": "Look at graphs in newspapers together — ask 'What does this tell us?'",
    },
    # English
    "nouns": {
        "common_mistake": "Children confuse proper and common nouns.",
        "parent_tip": "Play 'spot the noun' while reading — point to every naming word in a paragraph.",
    },
    "verbs": {
        "common_mistake": "Children confuse action verbs with describing words (adjectives).",
        "parent_tip": "Act out verbs — 'Show me jump! Show me run!' Makes grammar physical.",
    },
    "tenses": {
        "common_mistake": "Children mix past and present tense in the same sentence.",
        "parent_tip": "At bedtime, ask: 'What did you do today?' (past tense practice!).",
    },
    "pronouns": {
        "common_mistake": "Children use 'me' instead of 'I' (e.g., 'Me went to school').",
        "parent_tip": "Gently correct in conversation — 'I went to school, not me went.'",
    },
    "adjectives": {
        "common_mistake": "Children place adjectives after the noun in English (influence of Hindi word order).",
        "parent_tip": "Describe things together: 'What kind of flower? A RED flower. A BIG flower.'",
    },
    # Hindi
    "\u0935\u091a\u0928": {
        "common_mistake": "\u092c\u091a\u094d\u091a\u0947 \u0905\u0928\u093f\u092f\u092e\u093f\u0924 \u092c\u0939\u0941\u0935\u091a\u0928 \u092e\u0947\u0902 \u0917\u0932\u0924\u0940 \u0915\u0930\u0924\u0947 \u0939\u0948\u0902 (\u091c\u0948\u0938\u0947 '\u0906\u0926\u092e\u0940' \u0915\u093e \u092c\u0939\u0941\u0935\u091a\u0928 '\u0906\u0926\u092e\u0940\u092f\u093e\u0901' \u0932\u093f\u0916\u0928\u093e)\u0964",
        "parent_tip": "\u0918\u0930 \u092e\u0947\u0902 \u0935\u0938\u094d\u0924\u0941\u0913\u0902 \u0915\u094b \u090f\u0915 \u0914\u0930 \u0905\u0928\u0947\u0915 \u092e\u0947\u0902 \u092c\u093e\u0901\u091f\u0915\u0930 \u0905\u092d\u094d\u092f\u093e\u0938 \u0915\u0930\u0947\u0902\u0964",
    },
    "\u0935\u093f\u0932\u094b\u092e": {
        "common_mistake": "\u092c\u091a\u094d\u091a\u0947 \u0915\u0941\u091b \u0935\u093f\u0932\u094b\u092e \u0936\u092c\u094d\u0926\u094b\u0902 \u0915\u094b \u0909\u0932\u094d\u091f\u093e \u092f\u093e\u0926 \u0915\u0930\u0924\u0947 \u0939\u0948\u0902\u0964",
        "parent_tip": "\u0935\u093f\u0932\u094b\u092e \u0936\u092c\u094d\u0926\u094b\u0902 \u0915\u093e \u0916\u0947\u0932 \u0916\u0947\u0932\u0947\u0902 \u2014 \u090f\u0915 \u0936\u092c\u094d\u0926 \u092c\u094b\u0932\u0947\u0902, \u092c\u091a\u094d\u091a\u093e \u0909\u0932\u094d\u091f\u093e \u092c\u094b\u0932\u0947\u0964",
    },
    # EVS/Science
    "animals": {
        "common_mistake": "Children classify animals only as 'pet' or 'wild' without understanding habitats.",
        "parent_tip": "Visit a park or watch nature videos together — ask 'Where does this animal live?'",
    },
    "plants": {
        "common_mistake": "Children think all plants need the same amount of water and sunlight.",
        "parent_tip": "Grow two different plants at home — one in sun, one in shade. Observe the difference.",
    },
    "food": {
        "common_mistake": "Children think all tasty food is healthy and all healthy food is boring.",
        "parent_tip": "Cook together — show how dal, roti, and sabzi each give different things to our body.",
    },
    "water": {
        "common_mistake": "Children don't connect tap water to its source (river, groundwater).",
        "parent_tip": "Ask: 'Where does our water come from before it reaches our tap?'",
    },
    "body": {
        "common_mistake": "Children confuse sense organs with the senses themselves.",
        "parent_tip": "Play a blindfold game — identify objects by touch, smell, sound.",
    },
    "digestion": {
        "common_mistake": "Children think digestion happens only in the stomach.",
        "parent_tip": "Trace the journey of a roti — mouth (chewing) → food pipe → stomach → intestines.",
    },
    "weather": {
        "common_mistake": "Children confuse weather (daily) with climate (long-term pattern).",
        "parent_tip": "Keep a weather diary for a week — draw the weather each day.",
    },
    # Computer
    "computer": {
        "common_mistake": "Children confuse hardware (things you touch) with software (programs).",
        "parent_tip": "Point to computer parts: 'Monitor is hardware. Game inside is software.'",
    },
    # Health
    "hygiene": {
        "common_mistake": "Children wash hands quickly without soap or for less than 20 seconds.",
        "parent_tip": "Sing 'Happy Birthday' twice while washing — that's 20 seconds!",
    },
    "exercise": {
        "common_mistake": "Children think exercise means only running or sports.",
        "parent_tip": "Dancing, climbing stairs, and playing are all exercise!",
    },
    "diet": {
        "common_mistake": "Children want to eat only their favourite food every day.",
        "parent_tip": "Use a plate model: half vegetables, quarter grain, quarter protein.",
    },
    # ── EVS / Science (specific) ──
    "our senses": {
        "common_mistake": "Children confuse which sense organ does what — thinking ears help us see or tongue helps us hear.",
        "parent_tip": "Play a senses game: blindfold your child and have them guess objects by touch, smell, or sound.",
    },
    "my body": {
        "common_mistake": "Children mix up internal and external body parts — they think the heart is in the head.",
        "parent_tip": "Trace your child's body on a big paper and label body parts together.",
    },
    "my family": {
        "common_mistake": "Children confuse maternal and paternal relations (nani vs dadi, mama vs chacha).",
        "parent_tip": "Draw a family tree together and label each member with their relation name.",
    },
    "food we eat": {
        "common_mistake": "Children think all cooked food is healthy and all raw food is unhealthy.",
        "parent_tip": "During meals, ask: 'Is this giving us energy, strength, or protection?' for each food item.",
    },
    "seasons and weather": {
        "common_mistake": "Children confuse seasons with weather — they think rainy season means it rains every day.",
        "parent_tip": "Keep a weekly weather chart — draw sun, clouds, or rain each day and compare at month end.",
    },
    "plants around us": {
        "common_mistake": "Children think only big trees are plants — they forget grass, herbs, and shrubs are plants too.",
        "parent_tip": "Go for a walk and count different types of plants — big trees, small bushes, climbers, grass.",
    },
    "animals around us": {
        "common_mistake": "Children forget that insects, fish, and birds are also animals.",
        "parent_tip": "List 10 animals you saw today — include ants, butterflies, sparrows, not just dogs and cats.",
    },
    "shelter": {
        "common_mistake": "Children think all animals live in the same type of home.",
        "parent_tip": "Ask: 'Where does a bird sleep? Where does a fish sleep? Where does a dog sleep?' — compare homes.",
    },
    "animals and habitats": {
        "common_mistake": "Children think desert animals need water like we do — they don't know camels store fat, not water.",
        "parent_tip": "Watch a short nature video together and ask: 'Why does this animal live HERE and not there?'",
    },
    "our body": {
        "common_mistake": "Children confuse voluntary and involuntary actions — they think breathing is voluntary.",
        "parent_tip": "Ask your child to hold their breath — 'See? Your body breathes on its own!'",
    },
    "air": {
        "common_mistake": "Children think air is nothing because they can't see it.",
        "parent_tip": "Blow up a balloon together — 'See, air takes up space! It's real even though invisible.'",
    },
    "food and nutrition": {
        "common_mistake": "Children think vitamins come only from tablets, not from food.",
        "parent_tip": "While eating, name the vitamin: 'Carrots have Vitamin A for eyes, oranges have Vitamin C for health.'",
    },
    "human body": {
        "common_mistake": "Children memorise organ names but can't explain what each organ does.",
        "parent_tip": "After a meal, trace the food journey: mouth → food pipe → stomach → small intestine → blood.",
    },
    "photosynthesis": {
        "common_mistake": "Children think plants get food from soil, not from sunlight.",
        "parent_tip": "Keep one plant in sunlight and one in a dark cupboard for a week — observe the difference.",
    },
    "force and motion": {
        "common_mistake": "Children think heavier objects always fall faster than lighter ones.",
        "parent_tip": "Drop a ball and a crumpled paper from the same height — 'See? They land at almost the same time!'",
    },
    "states of matter": {
        "common_mistake": "Children think ice is a different substance from water, not just a different state.",
        "parent_tip": "Melt ice, boil water, catch steam — show the same water in 3 forms in your kitchen.",
    },
    "animal adaptation": {
        "common_mistake": "Children think animals choose their features — 'The camel chose to have a hump.'",
        "parent_tip": "Ask: 'Why does a polar bear have thick fur but a fish doesn't?' — connect body features to habitat.",
    },
    "simple machines": {
        "common_mistake": "Children think machines are only electronic devices — they forget scissors, ramps, and seesaws.",
        "parent_tip": "Find 5 simple machines at home: scissors (lever), door handle (wheel), ramp, bottle opener.",
    },
    "living things": {
        "common_mistake": "Children think fire is alive because it moves and grows.",
        "parent_tip": "Use MRS GREN: Movement, Respiration, Sensitivity, Growth, Reproduction, Excretion, Nutrition.",
    },
    "ecosystem": {
        "common_mistake": "Children think food chains are simple and linear — they don't understand food webs.",
        "parent_tip": "Draw a food chain from your garden: grass → grasshopper → frog → snake → eagle.",
    },
    "physical and chemical": {
        "common_mistake": "Children think all changes can be reversed — they don't distinguish physical from chemical.",
        "parent_tip": "Show: ice melts back to water (physical), but a burnt paper can't become paper again (chemical).",
    },
    "forms of energy": {
        "common_mistake": "Children think energy is created when we switch on a light — they don't know it's transformed.",
        "parent_tip": "Trace energy: sun → plant → food → your body → running. Energy changes form, never created!",
    },
    "solar system": {
        "common_mistake": "Children think the sun moves around the earth because they see it 'rise' and 'set'.",
        "parent_tip": "Use a torch and ball: torch = sun, ball = earth. Spin the ball — see day and night!",
    },
    "circulatory": {
        "common_mistake": "Children think blood is only red — they don't know about oxygen-rich vs oxygen-poor blood.",
        "parent_tip": "Feel your pulse after running — 'Your heart beats faster to send more blood to muscles!'",
    },
    "respiratory": {
        "common_mistake": "Children think we breathe in only oxygen and breathe out only CO2.",
        "parent_tip": "Breathe on a mirror — 'See the fog? That's water vapor your lungs added to the air!'",
    },
    "reproduction": {
        "common_mistake": "Children think all plants grow from seeds — they forget roots, stems, and leaves can grow new plants.",
        "parent_tip": "Plant a potato eye or onion top in soil — watch a new plant grow without seeds!",
    },
    # ── English ──
    "alphabet": {
        "common_mistake": "Children confuse visually similar letters: b/d, p/q, m/w. Also mix lowercase and uppercase.",
        "parent_tip": "Practice one letter per day. Trace it, say its sound, name 3 objects starting with it.",
    },
    "phonics": {
        "common_mistake": "Children confuse letter names with letter sounds ('aitch' vs /h/, 'double-you' vs /w/).",
        "parent_tip": "Say the SOUND, not the name: 'b says /b/ as in ball', not 'b says bee'.",
    },
    "self and family": {
        "common_mistake": "Children struggle with possessives — 'me book' instead of 'my book'.",
        "parent_tip": "Practice: 'This is MY bag. This is YOUR pencil. This is HER doll.'",
    },
    "greetings": {
        "common_mistake": "Children use informal greetings in formal situations — 'Hey' to a teacher.",
        "parent_tip": "Role-play: 'How do you greet your teacher? Your friend? Your grandparent?'",
    },
    "simple sentences": {
        "common_mistake": "Children write sentence fragments or forget capital letters and full stops.",
        "parent_tip": "Every sentence needs: Capital letter + subject + verb + full stop. Practice 3 sentences daily.",
    },
    "seasons": {
        "common_mistake": "Children confuse the number of seasons in India (6 ritus vs 3-4 commonly discussed).",
        "parent_tip": "Ask: 'What clothes do we wear in summer? In winter? In rainy season?' — connect seasons to life.",
    },
    "animals and food vocabulary": {
        "common_mistake": "Children use generic words ('thing', 'stuff') instead of specific vocabulary.",
        "parent_tip": "During meals, name ingredients: 'This is dal, made from lentils. This is paneer, made from milk.'",
    },
    "nature vocabulary": {
        "common_mistake": "Children know nature words in Hindi but struggle with English equivalents.",
        "parent_tip": "Take a nature walk — name everything: cloud, leaf, puddle, stone, ant, flower.",
    },
    "sentences": {
        "common_mistake": "Children write run-on sentences without punctuation.",
        "parent_tip": "Read aloud together — pause at every full stop. This teaches sentence boundaries naturally.",
    },
    "rhyming": {
        "common_mistake": "Children think words that start the same rhyme (bat/ball) instead of words that end the same (bat/cat).",
        "parent_tip": "Play rhyme chains: 'cat → bat → hat → mat → sat' — who can think of the most?",
    },
    "punctuation": {
        "common_mistake": "Children forget question marks for questions and use full stops everywhere.",
        "parent_tip": "Read a paragraph together. Child points to every full stop, comma, and question mark.",
    },
    "reading comprehension": {
        "common_mistake": "Children answer from memory or guess instead of finding answers in the passage.",
        "parent_tip": "Teach: 'The answer is IN the passage. Underline the sentence that answers the question.'",
    },
    "vocabulary": {
        "common_mistake": "Children memorise word meanings but can't use them in sentences.",
        "parent_tip": "For every new word, make a sentence using it. One new word per day = 365 words per year!",
    },
    "prefixes": {
        "common_mistake": "Children add prefixes randomly — 'unhappy' is correct but 'unsad' is not.",
        "parent_tip": "Practice common prefixes: un- (undo), re- (redo), dis- (disagree), pre- (prepay).",
    },
    "prepositions": {
        "common_mistake": "Children confuse in/on/at — 'I am on the bus' vs 'I am in the bus' (both used in Indian English).",
        "parent_tip": "Use toys: 'Put the ball ON the table, IN the box, UNDER the chair, BESIDE the book.'",
    },
    "conjunctions": {
        "common_mistake": "Children overuse 'and' to join all sentences instead of using but, because, so, or.",
        "parent_tip": "Give two sentences, child joins with the right conjunction: 'I was hungry ___ I ate lunch.'",
    },
    "sentence types": {
        "common_mistake": "Children can't distinguish statements from questions when there's no question mark.",
        "parent_tip": "Sort sentences into types: 'The sky is blue' (statement), 'Is the sky blue?' (question).",
    },
    "formal letter": {
        "common_mistake": "Children use informal language in formal letters — 'Hey Sir' instead of 'Respected Sir'.",
        "parent_tip": "Practice the format: sender address, date, receiver, subject, body, closing. Stick it on the wall.",
    },
    "active and passive": {
        "common_mistake": "Children confuse subject and object when converting — 'The cat caught the mouse' becomes 'The mouse caught the cat'.",
        "parent_tip": "Use the trick: move the object to the start, add 'was/were', move subject to the end with 'by'.",
    },
    "direct and indirect": {
        "common_mistake": "Children forget to change pronouns and tenses when converting direct to indirect speech.",
        "parent_tip": "Practice the 3 changes: remove quotes, change pronoun (I→he/she), change tense (is→was).",
    },
    "clauses": {
        "common_mistake": "Children can't identify the main clause vs the subordinate clause.",
        "parent_tip": "Ask: 'Which part can stand alone as a sentence?' — that's the main clause.",
    },
    "complex sentences": {
        "common_mistake": "Children write compound sentences (and, but) thinking they're complex.",
        "parent_tip": "Complex = main clause + subordinate clause with words like because, although, when, if.",
    },
    "synonyms": {
        "common_mistake": "Children think synonyms mean exactly the same — they don't understand shades of meaning.",
        "parent_tip": "happy/glad/joyful/ecstatic — arrange by intensity. This builds vocabulary depth.",
    },
    "summary writing": {
        "common_mistake": "Children copy sentences from the passage instead of writing in their own words.",
        "parent_tip": "Read a paragraph, close the book, tell the main idea in 2 sentences. That's a summary!",
    },
    "creative writing": {
        "common_mistake": "Children start stories with 'Once upon a time' every time and struggle with endings.",
        "parent_tip": "Give a funny prompt: 'What if your school bag could talk?' Let imagination flow — don't correct grammar first.",
    },
    "comprehension": {
        "common_mistake": "Children answer factual questions but struggle with inference and opinion questions.",
        "parent_tip": "After reading, ask: 'How do you think the character feels? Why?' — practice reading between the lines.",
    },
    # ── Hindi ──
    "varnamala swar": {
        "common_mistake": "बच्चे अ-आ और इ-ई में अंतर भूल जाते हैं। छोटी-बड़ी मात्रा में भ्रम होता है।",
        "parent_tip": "हर दिन एक स्वर का अभ्यास करें। उस स्वर से शुरू होने वाली 5 चीज़ें ढूँढें।",
    },
    "varnamala vyanjan": {
        "common_mistake": "बच्चे क-ख, ग-घ, च-छ जैसे मिलते-जुलते व्यंजनों में भ्रम करते हैं।",
        "parent_tip": "हर दिन 5 व्यंजन लिखवाएँ और उनसे एक-एक शब्द बनवाएँ।",
    },
    "family words": {
        "common_mistake": "बच्चे माँ-पापा लिख लेते हैं पर दादा-दादी, नाना-नानी में गलती करते हैं।",
        "parent_tip": "परिवार का पेड़ बनाएँ और हर सदस्य का नाम हिंदी में लिखें।",
    },
    "simple sentences in hindi": {
        "common_mistake": "बच्चे वाक्य में क्रिया (verb) भूल जाते हैं — 'मैं स्कूल' लिखते हैं 'मैं स्कूल जाता हूँ' की जगह।",
        "parent_tip": "हर वाक्य में पूछें: कौन? क्या करता है? कहाँ? — इन तीनों का उत्तर होना चाहिए।",
    },
    "two letter words": {
        "common_mistake": "बच्चे दो अक्षर के शब्दों में मात्रा लगा देते हैं जहाँ ज़रूरत नहीं है।",
        "parent_tip": "घर की चीज़ों के दो अक्षर वाले नाम ढूँढें: कप, जग, बस, रथ, फल।",
    },
    "three letter words": {
        "common_mistake": "बच्चे तीन अक्षर के शब्दों में बीच का अक्षर भूल जाते हैं।",
        "parent_tip": "तीन अक्षर के शब्दों से चित्र बनवाएँ: कमल, नदी, पतंग।",
    },
    "matras introduction": {
        "common_mistake": "बच्चे आ की मात्रा (ा) और इ की मात्रा (ि) में भ्रम करते हैं।",
        "parent_tip": "एक मात्रा प्रतिदिन — उस मात्रा वाले 10 शब्द ढूँढें और लिखें।",
    },
    "matras": {
        "common_mistake": "बच्चे ए-ऐ और ओ-औ की मात्राओं में गलती करते हैं।",
        "parent_tip": "मात्रा चार्ट दीवार पर लगाएँ। रोज़ एक मात्रा के 5 शब्द लिखवाएँ।",
    },
    "rhymes and poems": {
        "common_mistake": "बच्चे कविता रट लेते हैं पर अर्थ नहीं समझते।",
        "parent_tip": "कविता पढ़ने के बाद पूछें: 'इसमें क्या बताया गया है?' — अर्थ समझना ज़रूरी है।",
    },
    "varnamala": {
        "common_mistake": "बच्चे अनुस्वार (ं) और विसर्ग (ः) भूल जाते हैं।",
        "parent_tip": "वर्णमाला की पूरी सूची गाकर याद करें — संगीत से याद रहता है!",
    },
    "shabd rachna": {
        "common_mistake": "बच्चे उपसर्ग और प्रत्यय में भ्रम करते हैं।",
        "parent_tip": "एक मूल शब्द दें, बच्चा उपसर्ग-प्रत्यय लगाकर नए शब्द बनाए: सुख → दुःख, सुखी, सुखद।",
    },
    "vakya rachna": {
        "common_mistake": "बच्चे वाक्य में शब्दों का क्रम गलत रखते हैं।",
        "parent_tip": "शब्दों के कार्ड बनाएँ, बच्चा सही क्रम में जमाकर वाक्य बनाए।",
    },
    "kahani lekhan": {
        "common_mistake": "बच्चे कहानी का अंत नहीं लिख पाते या बीच में रुक जाते हैं।",
        "parent_tip": "कहानी के 3 भाग सिखाएँ: शुरुआत, बीच (समस्या), अंत (समाधान)।",
    },
    "kaal": {
        "common_mistake": "बच्चे भूतकाल और भविष्यकाल में क्रिया रूप गलत लिखते हैं।",
        "parent_tip": "तीन वाक्य बनवाएँ: 'कल मैंने ___ (भूत), आज मैं ___ (वर्तमान), कल मैं ___ (भविष्य)'।",
    },
    "patra lekhan": {
        "common_mistake": "बच्चे पत्र का प्रारूप (format) भूल जाते हैं — दिनांक, संबोधन, विषय।",
        "parent_tip": "पत्र का नमूना दीवार पर लगाएँ। हर हफ़्ते दादा-दादी को एक पत्र लिखवाएँ।",
    },
    "vachan and ling": {
        "common_mistake": "बच्चे अनियमित बहुवचन में गलती करते हैं (आदमी → आदमीयाँ लिखना, सही: आदमी)।",
        "parent_tip": "घर की चीज़ों को एकवचन-बहुवचन में बदलवाएँ: एक कुर्सी → दो कुर्सियाँ।",
    },
    "anusvaar": {
        "common_mistake": "बच्चे अनुस्वार (ं) और चंद्रबिंदु (ँ) में अंतर नहीं कर पाते।",
        "parent_tip": "अंतर समझाएँ: अनुस्वार नाक से बोलो (हंस), चंद्रबिंदु नाक + मुँह से (हँसना)।",
    },
    "comprehension hindi": {
        "common_mistake": "बच्चे गद्यांश पढ़ते हैं पर उत्तर पूरे वाक्य में नहीं लिखते।",
        "parent_tip": "सिखाएँ: उत्तर हमेशा पूरे वाक्य में लिखो, सिर्फ़ एक शब्द में नहीं।",
    },
    "vilom shabd": {
        "common_mistake": "बच्चे कुछ विलोम शब्दों को उलटा याद करते हैं।",
        "parent_tip": "विलोम शब्दों का खेल खेलें — एक शब्द बोलें, बच्चा उलटा बोले।",
    },
    "muhavare": {
        "common_mistake": "बच्चे मुहावरे का शाब्दिक अर्थ समझते हैं, लाक्षणिक नहीं।",
        "parent_tip": "'आँखों का तारा' का मतलब 'आँख में तारा' नहीं बल्कि 'बहुत प्यारा' — ऐसे समझाएँ।",
    },
    "paryayvachi": {
        "common_mistake": "बच्चे पर्यायवाची और विलोम में भ्रम करते हैं।",
        "parent_tip": "पर्यायवाची = समान अर्थ (जल, पानी, नीर)। विलोम = उल्टा अर्थ (दिन/रात)।",
    },
    "samas": {
        "common_mistake": "बच्चे समास के प्रकार (तत्पुरुष, द्वंद्व, बहुव्रीहि) में भ्रम करते हैं।",
        "parent_tip": "रोज़मर्रा के शब्दों से समास पहचानें: रसोईघर = रसोई का घर (तत्पुरुष)।",
    },
    "samvad lekhan": {
        "common_mistake": "बच्चे संवाद में बोलने वाले का नाम लिखना भूल जाते हैं।",
        "parent_tip": "दो पात्रों का संवाद लिखवाएँ: 'माँ: ___ बच्चा: ___' — रोज़ एक संवाद।",
    },
    # ── Computer ──
    "parts of computer": {
        "common_mistake": "Children confuse input devices (keyboard, mouse) with output devices (monitor, printer).",
        "parent_tip": "Point to each part: 'Keyboard = you TYPE (input). Monitor = you SEE (output).'",
    },
    "mouse and keyboard": {
        "common_mistake": "Children confuse left-click (select) with right-click (menu) and double-click (open).",
        "parent_tip": "Practice: left-click to select, double-click to open, right-click to see options.",
    },
    "special keys": {
        "common_mistake": "Children don't know the difference between Backspace (delete left) and Delete (delete right).",
        "parent_tip": "Let your child type their name and practice using Enter, Space, Backspace, and Caps Lock.",
    },
    "desktop": {
        "common_mistake": "Children confuse desktop icons with files — they think deleting an icon deletes the program.",
        "parent_tip": "Show: 'This icon is a shortcut, like a door. The program is inside — the door just helps you reach it.'",
    },
    "typing": {
        "common_mistake": "Children type with two fingers (hunt and peck) instead of using home row keys.",
        "parent_tip": "Show the home row: ASDF for left hand, JKL; for right hand. Practice 5 minutes daily.",
    },
    "files and folders": {
        "common_mistake": "Children save everything on the desktop instead of organizing into folders.",
        "parent_tip": "Create folders together: 'Homework', 'Games', 'Photos' — practice saving files in the right folder.",
    },
    "keyboard shortcuts": {
        "common_mistake": "Children forget common shortcuts and use menus for everything.",
        "parent_tip": "Start with 3: Ctrl+C (copy), Ctrl+V (paste), Ctrl+Z (undo). Practice daily.",
    },
    "ms paint": {
        "common_mistake": "Children use only the pencil tool and don't explore shapes, fill, or text tools.",
        "parent_tip": "Draw a house together using shapes (rectangle for walls, triangle for roof, circle for sun).",
    },
    "ms word": {
        "common_mistake": "Children type without pressing Enter for new paragraphs — one long block of text.",
        "parent_tip": "Type a short story together: practice bold for title, Enter for paragraphs, spell-check.",
    },
    "scratch": {
        "common_mistake": "Children place too many blocks without testing — then can't find the bug.",
        "parent_tip": "Teach: 'Add 2-3 blocks, then click the green flag to test. Fix before adding more.'",
    },
    "internet safety": {
        "common_mistake": "Children share personal information (name, school, address) in online games and chats.",
        "parent_tip": "Rule: NEVER share your real name, school name, photo, or address with strangers online.",
    },
    "internet basics": {
        "common_mistake": "Children think the internet and the web browser are the same thing.",
        "parent_tip": "Explain: 'Internet is the road. Browser (Chrome) is the car. Website is the destination.'",
    },
    "powerpoint": {
        "common_mistake": "Children put too much text on one slide — they copy paragraphs instead of bullet points.",
        "parent_tip": "Rule: Maximum 5 bullet points per slide, maximum 5 words per point. Pictures > text.",
    },
    "scratch programming": {
        "common_mistake": "Children don't use loops — they repeat the same blocks 10 times instead of using 'repeat'.",
        "parent_tip": "Challenge: 'Can you make the cat walk in a square using only 4 blocks inside a repeat?'",
    },
    "digital citizenship": {
        "common_mistake": "Children think anything they find online can be copied freely — no concept of copyright.",
        "parent_tip": "Teach: 'Would you take someone's toy without asking? Online content belongs to someone too.'",
    },
    "digital ethics": {
        "common_mistake": "Children think online actions have no consequences — cyberbullying seems like 'just joking'.",
        "parent_tip": "Ask: 'Would you say this to their face? If not, don't type it.' — the grandma test.",
    },
    # ── GK ──
    "national symbols": {
        "common_mistake": "Children confuse the national bird (peacock) with the national animal (tiger).",
        "parent_tip": "Make a chart: Flag, Emblem, Bird (peacock), Animal (tiger), Flower (lotus), Fruit (mango).",
    },
    "famous landmarks": {
        "common_mistake": "Children know Taj Mahal but can't name the city or builder.",
        "parent_tip": "Pick one landmark per week: name, city, who built it, one fun fact.",
    },
    "solar system basics": {
        "common_mistake": "Children mix up planet order — they forget 'My Very Educated Mother Just Served Us Nachos'.",
        "parent_tip": "Learn the mnemonic: Mercury Venus Earth Mars Jupiter Saturn Uranus Neptune.",
    },
    "current awareness": {
        "common_mistake": "Children memorise facts without understanding context.",
        "parent_tip": "Discuss one news story per week at dinner — 'What happened? Where? Why does it matter?'",
    },
    "continents": {
        "common_mistake": "Children confuse continents with countries — they think India is a continent.",
        "parent_tip": "Use a globe or map: '7 continents, India is in Asia. Can you find the others?'",
    },
    "famous scientists": {
        "common_mistake": "Children memorise names but forget the discovery: 'Newton — something about apples.'",
        "parent_tip": "One scientist per week: name, discovery, fun story. APJ Abdul Kalam is a great start!",
    },
    "festivals": {
        "common_mistake": "Children know festival names but not why they're celebrated.",
        "parent_tip": "Before each festival, tell the story: 'Diwali celebrates Ram's return. Holi celebrates Holika.'",
    },
    "indian constitution": {
        "common_mistake": "Children think the Constitution is just a book of laws, not a living document.",
        "parent_tip": "Discuss rights: 'You have the right to education. Your friend has the right to equality.'",
    },
    "world heritage": {
        "common_mistake": "Children confuse world heritage sites with tourist spots — they don't understand 'heritage'.",
        "parent_tip": "Heritage means 'precious things from the past.' Ask: 'Why should we protect the Taj Mahal?'",
    },
    "space missions": {
        "common_mistake": "Children think only NASA sends rockets — they don't know about ISRO's achievements.",
        "parent_tip": "Learn about Chandrayaan and Mangalyaan — India sent a Mars mission cheaper than a Hollywood movie!",
    },
    "environmental awareness": {
        "common_mistake": "Children think pollution is only factory smoke — they forget plastic, water pollution, noise.",
        "parent_tip": "Do a home audit: 'How much plastic did we use today? Can we reduce it tomorrow?'",
    },
    "global citizenship": {
        "common_mistake": "Children think global problems are too big for them to help with.",
        "parent_tip": "Start small: save water, plant a tree, donate old books. Small actions matter!",
    },
    # ── Moral Science ──
    "sharing": {
        "common_mistake": "Children think sharing means giving away their things permanently.",
        "parent_tip": "Practice: 'Can you share your crayons with your friend? They'll return them after drawing.'",
    },
    "honesty": {
        "common_mistake": "Children tell small lies to avoid trouble and think it's okay because 'it's a small lie'.",
        "parent_tip": "Praise honesty: 'Thank you for telling the truth. I'm proud of you even though you made a mistake.'",
    },
    "kindness": {
        "common_mistake": "Children are kind to friends but not to strangers or younger kids.",
        "parent_tip": "Practice daily kindness: 'Did you do one kind thing today? Help someone carry their bag?'",
    },
    "respecting elders": {
        "common_mistake": "Children confuse respect with obedience — they think respect means never disagreeing.",
        "parent_tip": "Teach: 'Respect means listening politely, using kind words, and being helpful — not blind obedience.'",
    },
    "empathy": {
        "common_mistake": "Children confuse empathy (feeling what others feel) with sympathy (feeling sorry).",
        "parent_tip": "Ask: 'How would YOU feel if someone took your toy? That's empathy — understanding someone else's feelings.'",
    },
    "teamwork": {
        "common_mistake": "Children want to do everything themselves and struggle to delegate or accept others' ideas.",
        "parent_tip": "Play team games: building blocks together, cooking together. Ask: 'What was YOUR role?'",
    },
    "environmental care": {
        "common_mistake": "Children think environmental care is only about not littering.",
        "parent_tip": "Three Rs: Reduce (use less), Reuse (use again), Recycle (make new things from old).",
    },
    "leadership": {
        "common_mistake": "Children think a leader is the one who gives orders, not the one who helps the team.",
        "parent_tip": "Ask: 'What makes a good captain? Someone who shouts or someone who encourages the team?'",
    },
    # ── Health & PE ──
    "personal hygiene": {
        "common_mistake": "Children skip steps — they wash hands but forget to use soap, or brush but forget tongue.",
        "parent_tip": "Make a hygiene checklist on the bathroom wall: brush teeth, wash hands, comb hair, clean nails.",
    },
    "good posture": {
        "common_mistake": "Children slouch while studying and don't realize it affects their back and concentration.",
        "parent_tip": "The wall test: stand with back against the wall — head, shoulders, hips should touch.",
    },
    "basic physical": {
        "common_mistake": "Children think exercise has to be intense — they don't count walking and stretching.",
        "parent_tip": "Start with 10 minutes: 5 stretches, 10 jumping jacks, walk around the park. Every day!",
    },
    "healthy eating": {
        "common_mistake": "Children think 'healthy' means only salads and boring food.",
        "parent_tip": "Make healthy food fun: fruit chat with chaat masala, smoothies, veggie sandwiches with cheese.",
    },
    "outdoor play": {
        "common_mistake": "Children prefer screen time over outdoor play and don't know traditional games.",
        "parent_tip": "Teach one traditional game: kho-kho, pitthu, lagori, hopscotch. Play together on weekends.",
    },
    "basic stretching": {
        "common_mistake": "Children bounce during stretches instead of holding still — this can cause injury.",
        "parent_tip": "Hold each stretch for 10 seconds, no bouncing. Practice touching toes, arm stretches.",
    },
    "balanced diet": {
        "common_mistake": "Children think skipping meals helps them stay healthy.",
        "parent_tip": "Three meals + two snacks. Show the plate: half veggies, quarter grain, quarter protein.",
    },
    "safety at play": {
        "common_mistake": "Children ignore safety rules during excitement — no helmet while cycling, pushing on slides.",
        "parent_tip": "Before play: 'What are the 3 safety rules today?' Let them set the rules themselves.",
    },
    "team sports": {
        "common_mistake": "Children focus only on winning and get upset when they lose.",
        "parent_tip": "After every game: 'What did you learn? Did you play fair? Did you encourage your team?'",
    },
    "sports and games": {
        "common_mistake": "Children know cricket but can't name rules of other sports like kho-kho or basketball.",
        "parent_tip": "Learn one new sport per month: rules, famous players, try playing it even in a small way.",
    },
    "first aid": {
        "common_mistake": "Children panic during minor injuries instead of following basic first aid steps.",
        "parent_tip": "Teach: cuts → wash with water, press with clean cloth. Burns → run cold water. Nosebleed → pinch and lean forward.",
    },
    "yoga": {
        "common_mistake": "Children rush through yoga poses without holding them or focusing on breathing.",
        "parent_tip": "Start with 3 poses: tree pose (balance), cobra (back), butterfly (flexibility). Hold for 10 breaths.",
    },
    "importance of sleep": {
        "common_mistake": "Children think sleeping less means more time to play — they don't understand sleep helps the brain.",
        "parent_tip": "Set a bedtime: Class 1-3 need 10 hours, Class 4-5 need 9 hours. No screens 30 minutes before bed.",
    },
    "fitness": {
        "common_mistake": "Children think fitness is only for athletes or adults.",
        "parent_tip": "Track weekly activity: 'Did you play outside 5 times this week?' — make it a fun challenge.",
    },
    "nutrition labels": {
        "common_mistake": "Children don't know how to read food labels — they judge food by the brand or taste.",
        "parent_tip": "Pick a packet from your kitchen — read together: calories, sugar, fat. Compare two brands.",
    },
    "mental health": {
        "common_mistake": "Children think feeling sad or angry is wrong — they don't know these are normal emotions.",
        "parent_tip": "Teach: 'All feelings are okay. Feeling angry is normal — what matters is how we handle it.'",
    },
    # ── Maths (specific) ──
    "basic shapes": {
        "common_mistake": "Children identify shapes only in standard orientation — a rotated triangle doesn't look like a triangle to them.",
        "parent_tip": "Show shapes in different orientations and sizes — 'Is this still a triangle? Yes! Count the sides.'",
    },
    "spatial sense": {
        "common_mistake": "Children confuse left-right and above-below in written directions.",
        "parent_tip": "Play direction games: 'Put the ball ABOVE the table, BEHIND the chair, BELOW the bed.'",
    },
    "numbers 1 to 50": {
        "common_mistake": "Children reverse digits when writing teens: 12 becomes 21, 15 becomes 51.",
        "parent_tip": "Practice: say 'thirteen' → 1 then 3. The 'teen' tells you 1 comes first.",
    },
    "numbers 51 to 100": {
        "common_mistake": "Children struggle with counting across decades: ...48, 49, 50, 41? They restart instead of continuing.",
        "parent_tip": "Use a number chart (1-100). Point and read together — especially the decade transitions.",
    },
    "numbers up to 1000": {
        "common_mistake": "Children confuse place values — in 432, they think 4 means four, not four hundred.",
        "parent_tip": "Use bundles: 100 = 1 bundle, 10 = 1 stick, 1 = 1 bead. Build numbers physically.",
    },
    "numbers up to 10 lakh": {
        "common_mistake": "Children confuse Indian place values (lakhs/crores) with international system (millions).",
        "parent_tip": "Practice comma placement: Indian system has commas after 3, 5, 7 digits from right: 10,00,000.",
    },
    "multiplication (tables 2-5)": {
        "common_mistake": "Children skip-count but lose track: 4, 8, 12, 14 (wrong — should be 16).",
        "parent_tip": "Tables song: 'Two ones are two, two twos are four...' — rhythmic chanting works best.",
    },
    "area and volume": {
        "common_mistake": "Children forget to use square units (cm²) for area and cubic units (cm³) for volume.",
        "parent_tip": "Area = floor tiles (flat, cm²). Volume = how much water fits (3D, cm³ or mL).",
    },
    "speed distance": {
        "common_mistake": "Children mix up the formula — they divide when they should multiply and vice versa.",
        "parent_tip": "Use the triangle: S on top, D and T below. Cover what you want: D = S × T, S = D ÷ T.",
    },
    "factors and multiples": {
        "common_mistake": "Children confuse factors (divide into) with multiples (multiply to get).",
        "parent_tip": "Factors = what fits inside: factors of 12 = 1, 2, 3, 4, 6, 12. Multiples = keep adding: 3, 6, 9, 12...",
    },
    "hcf and lcm": {
        "common_mistake": "Children confuse HCF (biggest shared factor) with LCM (smallest shared multiple).",
        "parent_tip": "HCF = highest common FACTOR (goes INTO both). LCM = lowest common MULTIPLE (both go into IT).",
    },
    "data handling (pictographs)": {
        "common_mistake": "Children miscount symbols when each symbol represents more than 1 unit.",
        "parent_tip": "Always read the key first: 'Each 🍎 = 2 students. So 3 apples = 6 students, not 3!'",
    },
    "data handling (pie charts)": {
        "common_mistake": "Children judge pie chart sections by appearance, not by reading the percentage labels.",
        "parent_tip": "Always add up all sections — they must equal 100%. If not, something is wrong.",
    },
    "fractions (halves": {
        "common_mistake": "Children think fractions are always less than 1 — they struggle with ½ of 8 = 4.",
        "parent_tip": "Cut a roti in half — each piece is ½. Now cut 4 rotis — half of 4 rotis = 2 rotis.",
    },
    "fractions (add": {
        "common_mistake": "Children add numerators AND denominators: ½ + ⅓ = ⅖ (wrong — it's ⅚).",
        "parent_tip": "Rule: denominators MUST be same before adding. Find common denominator first, then add tops only.",
    },
    "decimals (all": {
        "common_mistake": "Children line up decimal numbers from the right like whole numbers — 2.5 + 0.35 = 2.85 (wrong alignment).",
        "parent_tip": "Golden rule: line up the decimal POINTS, then add column by column. Add zeros if needed: 2.50 + 0.35.",
    },
    "geometry (circles": {
        "common_mistake": "Children confuse radius (center to edge) with diameter (edge to edge through center).",
        "parent_tip": "Remember: diameter = 2 × radius. The diameter is the longest line through the circle.",
    },
}


def _build_worksheet_meta(topic: str, grade_level: str, subject: str) -> dict:
    """Build worksheet metadata from learning objectives with scored fuzzy matching."""
    objectives = _match_learning_objectives(topic, grade_level, subject)

    grade_num = int(re.search(r"\d+", str(grade_level)).group()) if re.search(r"\d+", str(grade_level)) else 3

    # Find matching guidance — sort by LONGEST key first so specific entries win
    topic_lower = topic.lower()
    common_mistake = ""
    parent_tip = ""
    for key in sorted(TOPIC_GUIDANCE.keys(), key=len, reverse=True):
        if key in topic_lower:
            guidance = TOPIC_GUIDANCE[key]
            common_mistake = guidance.get("common_mistake", "")
            parent_tip = guidance.get("parent_tip", "")
            break

    # Strip grade suffix for title: "Addition (carries)" → "Addition"
    base_topic = re.sub(r"\s*\(Class\s*\d+\)\s*", "", topic, flags=re.IGNORECASE).strip()
    if "(" in base_topic:
        title_topic = base_topic.split("(")[0].strip()
    else:
        title_topic = base_topic

    # Grade-appropriate title templates (8 per band for variety)
    if grade_num <= 2:
        _TITLE_TEMPLATES = [
            "Fun with {topic}",
            "Let's Learn {topic}!",
            "My {topic} Worksheet",
            "{topic} Practice",
            "{topic} — Let's Try!",
            "I Can Do {topic}!",
            "{topic} Time!",
            "Play and Learn: {topic}",
        ]
    elif grade_num <= 3:
        _TITLE_TEMPLATES = [
            "{topic} Practice",
            "{topic} Worksheet",
            "Let's Practice {topic}",
            "{topic} — Practice Questions",
            "{topic} — Test Yourself",
            "Get Better at {topic}",
            "{topic} Revision",
            "{topic} — Quick Practice",
        ]
    else:
        _TITLE_TEMPLATES = [
            "{topic} Worksheet",
            "{topic} Practice",
            "{topic} Exercise",
            "{topic} — Practice Questions",
            "{topic} — Test Your Skills",
            "{topic} Revision Sheet",
            "{topic} — Sharpen Your Skills",
            "{topic} — Practice & Apply",
        ]

    if title_topic:
        idx = hash(title_topic + grade_level) % len(_TITLE_TEMPLATES)
        title = _TITLE_TEMPLATES[idx].format(topic=title_topic)
    else:
        title = f"{subject} Practice Worksheet"

    if not common_mistake:
        common_mistake = f"Children may apply rules of {title_topic or topic} inconsistently in new examples."
    if not parent_tip:
        parent_tip = "Ask your child to explain one answer aloud after each question. Explaining improves retention."

    return {
        "title": title,
        "skill_focus": objectives[0] if objectives else f"Practice {topic}",
        "common_mistake": common_mistake,
        "parent_tip": parent_tip,
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
    profile = get_topic_profile(topic, subject, grade_level)
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

    # Detect if ALL tags are generic (no topic profile matched)
    all_generic = all(tag == "general" for tag in expanded_tags)

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
    mandatory_visual_min = 0
    topic_lower = topic.lower()
    # Special case: fraction comparison/equivalent → fraction_bar, not pie
    _special_case_visual = False
    if "fraction" in topic_lower and any(kw in topic_lower for kw in ("compar", "equivalent", "adding", "subtracting")):
        mandatory_visual = "fraction_bar"
        _special_case_visual = True
    else:
        for key, vis_type in MANDATORY_VISUAL_TOPICS.items():
            if key in topic_lower:
                mandatory_visual = vis_type
                break
    # Profile can override, but NOT when we already picked a special-case visual
    profile_mandatory = profile.get("mandatory_visuals", {}) if profile else {}
    required_types = profile_mandatory.get("required_types") or []
    if required_types and not _special_case_visual:
        mandatory_visual = required_types[0]
        mandatory_visual_min = int(profile_mandatory.get("min_count", 1))

    # Pick contexts and objects
    contexts = pick_contexts(subject, num_questions)
    from .context_pools import pick_subject_objects

    objects = pick_subject_objects(subject, topic, num_questions, grade_num)
    used_names: list[str] = []

    # Detect error_detection forbidden
    error_det_forbidden = any("error_detection" in ft for ft in forbidden_types)
    seen_number_signatures: set[tuple] = set()

    slots: list[Slot] = []
    for i, skill_tag in enumerate(expanded_tags):
        # Determine natural role from skill tag
        natural_role = _skill_to_role(skill_tag)
        assigned_role, assigned_diff = difficulty_assignments[i]

        # Respect natural role from recipe tags to preserve pedagogical intent.
        final_role = natural_role
        final_diff = assigned_diff
        if natural_role in ("error_detection", "thinking"):
            # Avoid easy error/thinking prompts.
            final_diff = max(assigned_diff, "medium", key=lambda x: ["easy", "medium", "hard"].index(x))

        # Check forbidden types
        if error_det_forbidden and final_role == "error_detection":
            final_role = "application"

        # Override role for generic tags based on position
        if all_generic:
            slot_pct = i / max(num_questions - 1, 1)
            if slot_pct < 0.3:
                final_role = "recognition"
            elif slot_pct < 0.6:
                final_role = "application"
            elif slot_pct < 0.8:
                if not error_det_forbidden:
                    final_role = "error_detection" if i % 2 == 0 else "representation"
                else:
                    final_role = "application"
            else:
                final_role = "thinking"

        # Question type
        q_type = _skill_to_question_type(skill_tag)

        # Vary question types for generic tags
        if all_generic:
            slot_pct = i / max(num_questions - 1, 1)
            if slot_pct < 0.3:
                q_type = "mcq"
            elif slot_pct < 0.5:
                q_type = "fill_blank" if i % 2 == 0 else "short_answer"
            elif slot_pct < 0.7:
                q_type = "short_answer"
            elif slot_pct < 0.8:
                q_type = "true_false"
            elif slot_pct < 0.9:
                q_type = "error_detection" if not error_det_forbidden else "short_answer"
            else:
                q_type = "short_answer"

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

        # Avoid duplicate maths pairs in the same worksheet where possible.
        if is_maths and numbers and "a" in numbers and "b" in numbers:
            op_for_retry = operation or _detect_maths_operation("", skill_tag)
            signature = (
                op_for_retry,
                numbers.get("a"),
                numbers.get("b"),
                numbers.get("numerator"),
                numbers.get("denominator"),
            )
            retries = 0
            while signature in seen_number_signatures and retries < 8 and op_for_retry:
                numbers = _generate_numbers(grade_num, op_for_retry, skill_tag) or numbers
                signature = (
                    op_for_retry,
                    numbers.get("a"),
                    numbers.get("b"),
                    numbers.get("numerator"),
                    numbers.get("denominator"),
                )
                retries += 1
            seen_number_signatures.add(signature)

        # Wrong answer for error_detection
        if q_type == "error_detection" and numbers and numbers.get("answer") is not None:
            wrong_answer = _generate_wrong_answer(numbers["answer"], operation)

        # Visual assignment
        visual_type = None
        visual_data = None
        if mandatory_visual:
            # Respect profile minimums, but never go below the 50% baseline.
            min_required = max(mandatory_visual_min, math.ceil(num_questions * 0.5))
            if i < min_required:
                visual_type = mandatory_visual
        if not visual_type:
            # Determine visual rate based on grade, subject, and problem_style
            visual_rate = 0.0
            _sl = subject.lower()

            if problem_style == "visual":
                visual_rate = {1: 1.0, 2: 0.9, 3: 0.7, 4: 0.5, 5: 0.3}.get(grade_num, 0.3)
            elif problem_style == "mixed":
                visual_rate = {1: 0.8, 2: 0.7, 3: 0.5, 4: 0.3, 5: 0.2}.get(grade_num, 0.2)
            elif is_maths and operation in (
                "addition",
                "addition_with_carry",
                "subtraction",
                "subtraction_no_borrow",
                "subtraction_with_borrow",
                "multiplication",
                "division",
            ):
                visual_rate = {1: 0.7, 2: 0.6, 3: 0.4, 4: 0.15, 5: 0.1}.get(grade_num, 0.1)
            elif is_maths:
                visual_rate = {1: 0.6, 2: 0.5, 3: 0.35, 4: 0.15, 5: 0.1}.get(grade_num, 0.1)
            elif _sl in ("health", "moral science"):
                visual_rate = {1: 0.7, 2: 0.6, 3: 0.4, 4: 0.3, 5: 0.2}.get(grade_num, 0.2)
            elif _sl in ("science", "evs"):
                visual_rate = {1: 0.7, 2: 0.5, 3: 0.35, 4: 0.2, 5: 0.1}.get(grade_num, 0.1)
            elif _sl in ("computer", "gk"):
                visual_rate = {1: 0.5, 2: 0.4, 3: 0.25, 4: 0.2, 5: 0.15}.get(grade_num, 0.15)
            else:
                visual_rate = {1: 0.5, 2: 0.4, 3: 0.25, 4: 0.1, 5: 0.05}.get(grade_num, 0.05)

            if random.random() < visual_rate:
                visual_type = _pick_visual_type(topic, is_maths, subject=subject, grade_num=grade_num, slot_number=i)
                # For early-grade arithmetic, always fall back to object_group
                if not visual_type and is_maths and grade_num <= 2:
                    visual_type = "object_group"

        if visual_type:
            visual_data = _compute_visual_data(
                visual_type, numbers, grade_num, slot_number=i, topic=topic, language=language
            )

        # Image keywords — auto-assign for Class 1-2, optional for Class 3
        image_kw = None
        auto_image_rate = 0.0
        if grade_num <= 2:
            auto_image_rate = 0.5  # 50% of questions get images
        elif grade_num == 3:
            auto_image_rate = 0.25  # 25% of questions get images

        # Boost for Science/EVS — these subjects benefit from visuals at every grade
        if subject.lower() in ("science", "evs"):
            auto_image_rate = max(auto_image_rate, 0.4)

        # Boost for other text-heavy subjects with good image coverage
        subject_lower = subject.lower()
        if subject_lower in ("english", "hindi", "health"):
            auto_image_rate = max(auto_image_rate, 0.4)
        elif subject_lower in ("computer",):
            auto_image_rate = max(auto_image_rate, 0.5)
        elif subject_lower in ("gk", "general knowledge"):
            auto_image_rate = max(auto_image_rate, 0.6)

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
                # NO fallback to random images — only show images that match the topic
                # Random images (ship for Hindi, desert for tenses) confuse children
                image_kw = None

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

        # Post-creation override: Hindi word-bank role mapping
        if slot.expected_answer and slot.assigned_word:
            type_to_role = {
                "mcq": "recognition",
                "fill_blank": "application",
                "short_answer": "application",
                "true_false": "application",
                "error_detection": "error_detection",
                "word_problem": "application",
            }
            slot.role = type_to_role.get(slot.question_type, "recognition")

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
                            # Sync visual_data groups with new numbers
                            if slot.visual_type and slot.visual_data:
                                slot.visual_data = _compute_visual_data(
                                    slot.visual_type,
                                    new_nums,
                                    grade_num,
                                    slot_number=slot.slot_number - 1,
                                    topic=topic,
                                    language=language,
                                )
                            slot.llm_instruction = _build_llm_instruction(slot, topic, subject, language, grade_num)
                            pair_key = new_key
                            break
            seen_pairs.add(pair_key)

    # --- Step 6c: Deduplicate answers ---
    # Class 1-2: max 1 repeat per answer (small number ranges)
    # Class 3+: max 2 repeats per answer
    if is_maths:
        max_repeats = 1 if grade_num <= 2 else 2
        answer_counts: dict[int, list[int]] = {}  # answer → [slot indices]
        for idx, slot in enumerate(slots):
            if slot.numbers and slot.numbers.get("answer") is not None:
                ans = slot.numbers["answer"]
                answer_counts.setdefault(ans, []).append(idx)

        for ans, indices in answer_counts.items():
            if len(indices) > max_repeats:
                for regen_idx in indices[max_repeats:]:
                    for attempt in range(30):
                        new_nums = _generate_numbers(grade_num, operation, slots[regen_idx].skill_tag)
                        if new_nums and new_nums.get("answer") != ans:
                            existing_answers = {
                                s.numbers["answer"] for s in slots if s.numbers and s.numbers.get("answer") is not None
                            }
                            if new_nums["answer"] not in existing_answers or attempt > 20:
                                slots[regen_idx].numbers = new_nums
                                # Sync visual_data groups with new numbers
                                if slots[regen_idx].visual_type and slots[regen_idx].visual_data:
                                    slots[regen_idx].visual_data = _compute_visual_data(
                                        slots[regen_idx].visual_type,
                                        new_nums,
                                        grade_num,
                                        slot_number=regen_idx,
                                        topic=topic,
                                        language=language,
                                    )
                                slots[regen_idx].llm_instruction = _build_llm_instruction(
                                    slots[regen_idx], topic, subject, language, grade_num
                                )
                                break

    # --- Step 7: Enforce type minimums ---
    _enforce_type_minimums(slots, num_questions, error_det_forbidden)

    # --- Step 7b: Sort by difficulty (scaffolding: easy → medium → hard) ---
    _DIFF_ORDER = {"easy": 0, "medium": 1, "hard": 2}
    slots.sort(key=lambda s: _DIFF_ORDER.get(s.difficulty, 1))
    for idx, slot in enumerate(slots):
        slot.slot_number = idx + 1

    # Rebuild LLM instructions for any slots whose type/order was changed
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


def _pick_visual_type(
    topic: str,
    is_maths: bool,
    subject: str = "",
    grade_num: int = 3,
    slot_number: int = 0,
) -> str | None:
    """Pick a suitable visual type for a slot."""
    topic_lower = topic.lower()
    subject_lower = subject.lower()

    # Check mandatory topics first
    for key, vis_type in MANDATORY_VISUAL_TOPICS.items():
        if key in topic_lower:
            return vis_type

    # Subject-specific visual types
    if subject_lower in ("english",) and grade_num <= 2:
        return "picture_word_match"

    if subject_lower in ("hindi",) and grade_num <= 2:
        return "picture_word_match"

    if subject_lower in ("evs",) and grade_num <= 2:
        if "animal" in topic_lower and "habitat" in topic_lower:
            return "match_columns"
        if "plant" in topic_lower or "body" in topic_lower:
            return "labeled_diagram"
        return "picture_word_match"

    if subject_lower in ("science", "evs"):
        if "food" in topic_lower or "nutrition" in topic_lower or "diet" in topic_lower:
            return "food_plate"
        if "body" in topic_lower or "human" in topic_lower or "digest" in topic_lower or "plant" in topic_lower:
            return "labeled_diagram"
        if "animal" in topic_lower:
            return random.choice(["match_columns", "picture_word_match"])
        if "water" in topic_lower or "air" in topic_lower:
            return "labeled_diagram"
        if "force" in topic_lower or "energy" in topic_lower or "matter" in topic_lower:
            return "sequence_pictures"
        return "picture_word_match"

    if subject_lower in ("computer",):
        return "labeled_diagram"

    if subject_lower in ("gk",):
        return "picture_word_match"

    # Health
    if subject_lower in ("health",):
        if "hygiene" in topic_lower or "wash" in topic_lower:
            return "sequence_pictures"
        if "diet" in topic_lower or "food" in topic_lower or "eating" in topic_lower or "nutrition" in topic_lower:
            return "food_plate"
        return "scenario_picture"

    # Moral Science
    if subject_lower in ("moral science",):
        return "scenario_picture"

    if is_maths:
        # Fraction comparison/equivalence → fraction_bar (not pie)
        if "fraction" in topic_lower and (
            "compar" in topic_lower or "equivalent" in topic_lower or "add" in topic_lower or "subtract" in topic_lower
        ):
            return "fraction_bar"
        if "percent" in topic_lower:
            return "percentage_bar"
        if "data" in topic_lower or "graph" in topic_lower or "chart" in topic_lower:
            return random.choice(["pictograph", "bar_chart"])
        if "number" in topic_lower and grade_num <= 2:
            return random.choice(["ten_frame", "number_line", "object_group"])
        if "multipl" in topic_lower and grade_num <= 3:
            return "array_visual"
        # Maths Class 4-5 topics without mandatory visuals
        if grade_num >= 4:
            if "decimal" in topic_lower:
                return "number_line"
            if "area" in topic_lower or "volume" in topic_lower or "perimeter" in topic_lower:
                return "shapes"
            if "speed" in topic_lower or "distance" in topic_lower:
                return "number_line"
            return "number_line"
        # Default maths visuals
        if grade_num <= 2:
            # For addition/subtraction topics, prefer object_group (shows two groups)
            # ten_frame is for counting single numbers, not binary operations
            if any(kw in topic_lower for kw in ("addition", "add ", "subtraction", "subtract")):
                return random.choice(["object_group", "object_group", "number_line"])
            return random.choice(["object_group", "ten_frame", "number_line"])
        return random.choice(["object_group", "number_line"])

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
