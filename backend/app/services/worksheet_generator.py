"""
Worksheet Generator v2 — simplified prompt-to-Gemini pipeline.

Replaces the 18,000-line slot_engine.py for generation.  Everything else
(PDF export, mastery tracking, auth, subscription, save/load) is untouched.

Architecture:
    build_prompt(params) -> system + user prompt
        -> call_gemini(prompt) -> Gemini 2.5 Flash, temp=0.3, JSON mode
            -> validate(response) -> schema + maths verification + topic drift
                -> return WorksheetGenerationResponse (same shape as v1)
"""

from __future__ import annotations

import json
import math
import random
import re
import string
import time
from typing import Any

import structlog

from app.data.image_registry import get_keywords_for_subject
from app.data.topic_profiles import get_topic_profile
from app.services.prompt_builder import _BLOOM_DIRECTIVES

logger = structlog.get_logger("skolar.worksheet_generator")

# ---------------------------------------------------------------------------
# Prompt versions — bump when changing prompt content, logged with every call
# ---------------------------------------------------------------------------
SYSTEM_PROMPT_VERSION = "v2.3"
USER_PROMPT_VERSION = "v2.3"

# ---------------------------------------------------------------------------
# 1A  System Prompt — composable blocks
# ---------------------------------------------------------------------------

_CORE_RULES = """\
You are an expert CBSE school teacher creating worksheets for Indian primary school students.

RULES:
1. Generate questions ONLY about the given topic — never about other topics.
2. All questions must be age-appropriate for the given class level.
3. Follow NCERT/CBSE curriculum standards for the given class and subject.
4. Every question must have a correct answer. For maths, compute the answer precisely.
5. Never repeat the same question pattern. Vary formats, angles, and phrasings.
6. Use Indian context (₹ for money, Indian names, Indian festivals, Indian cities, etc.)
7. VARIETY IS CRITICAL: rotate through scenarios (home, school, market, park, farm, zoo, kitchen, playground, festival, hospital, train station), mix question styles, and vary sentence structures.

DIFFICULTY LEVELS & ROLE DISTRIBUTION:
- Easy: 60% Foundation (★ recognition/representation), 30% Application (★★), 10% Stretch (★★★ error_detection/thinking)
- Medium: 30% Foundation, 50% Application, 20% Stretch
- Hard: 10% Foundation, 30% Application, 60% Stretch

Group questions: all Foundation first, then Application, then Stretch.
Each question MUST have a "role" field.

Examples:
- Easy: "What time does this clock show?" (direct recall)
- Medium: "School starts at 8:30 AM. If Priya takes 45 minutes to get ready, what time should she wake up?"
- Hard: "Rahul says 90 minutes equals 1 hour 20 minutes. Is he correct? Explain why."

QUESTION TYPES — required distribution:
- mcq (≥30%): MUST have "options" array with EXACTLY 4 strings. Include "options": ["True", "False"] for true_false.
- fill_blank (≥20%): question text MUST contain "______".
- true_false (≥1): "options": ["True", "False"]. correct_answer must be "True" or "False".
- short_answer / word_problem / error_detection: "options": null.

Every question MUST have a "hint" field that guides without revealing the answer."""

_VISUAL_BLOCK = """\

VISUAL TYPES — use ONLY these exact type names and data structures:

1. "clock" — visual_data: { "hour": <1-12>, "minute": <0-59> }
2. "object_group" — visual_data: { "groups": [{"count": <n>, "label": "<object>"}], "operation": "+"|"-" }
   Labels: mango/apple/orange/banana/fruit, bird/parrot/sparrow, star/sticker, coin/rupee, marble/ball/bead, balloon, candy/sweet/toffee/chocolate, flower/rose, pencil/pen/crayon, book/notebook
3. "shapes" — visual_data: { "shape": "triangle"|"rectangle"|"square"|"circle", "sides": [<numbers>] }
4. "number_line" — visual_data: { "start": <n>, "end": <n>, "step": <n>, "highlight": <n or null> }
5. "base_ten_regrouping" — visual_data: { "numbers": [<n1>, <n2>], "operation": "addition"|"subtraction" }
6. "pie_fraction" — visual_data: { "numerator": <n>, "denominator": <n> }
7. "grid_symmetry" — visual_data: { "grid_size": <n>, "filled_cells": [[row,col], ...], "fold_axis": "vertical"|"horizontal" }
8. "money_coins" — visual_data: { "coins": [{"value": <n>, "count": <n>}, ...] }
9. "pattern_tiles" — visual_data: { "tiles": ["A","B","A","B","A","?"], "blank_position": 5 }
10. "abacus" — visual_data: { "hundreds": <0-9>, "tens": <0-9>, "ones": <0-9> }

VISUAL RULES:
- Use ONLY the 10 types above. Do NOT use "clock_face", "fraction_bar", "bar_chart", or "tally_chart".
- visual_data must EXACTLY match the schema — no extra or missing fields.
- For "standard" problem_style: visual_type=null, visual_data=null for ALL questions.
- For "visual": EVERY question MUST have a visual. For "mixed": ~50% should have visuals.
- NEVER write "look at the image/picture" — question text must be self-contained.
- Visual must directly help answer the question. No visual is better than a misleading one."""

_IMAGE_BLOCK_TEMPLATE = """\

IMAGES: Attach cartoon images using "image_keywords" from this list ONLY: {keywords}

IMAGE RULES:
- Use 1 keyword per question (2 only for comparison questions).
- For EVS/Science with visual/mixed style: images on ≥60% of questions.
- For Maths: prefer SVG visual_type over image_keywords.
- image_keywords and visual_type can coexist."""

_OUTPUT_FORMAT_STANDARD = """\

OUTPUT FORMAT — respond with ONLY this JSON, no other text:
{
  "title": "Worksheet: {topic}",
  "skill_focus": "<one-line skill summary>",
  "common_mistake": "<one common mistake>",
  "parent_tip": "<one tip for parents>",
  "learning_objectives": ["<obj 1>", "<obj 2>", "<obj 3>"],
  "questions": [
    {
      "id": "q1",
      "type": "<mcq|fill_blank|true_false|short_answer|word_problem|error_detection>",
      "role": "<recognition|representation|application|error_detection|thinking>",
      "text": "<question text>",
      "options": ["<A>", "<B>", "<C>", "<D>"] or null,
      "correct_answer": "<accurate answer>",
      "explanation": "<brief explanation>",
      "difficulty": "<easy|medium|hard>",
      "hint": "<helpful hint>",
      "image_keywords": null,
      "visual_type": null,
      "visual_data": null
    }
  ]
}

FEW-SHOT EXAMPLES (follow these formats exactly):

MCQ example:
{"id":"q1","type":"mcq","role":"recognition","text":"Which of these is the largest 3-digit number?","options":["999","100","909","990"],"correct_answer":"999","explanation":"The largest 3-digit number has 9 in all places: 999.","difficulty":"easy","hint":"Think about the biggest digit you can put in each place.","image_keywords":null,"visual_type":null,"visual_data":null}

Fill-in-the-blank example:
{"id":"q2","type":"fill_blank","role":"application","text":"456 + 238 = ______","options":null,"correct_answer":"694","explanation":"Add ones: 6+8=14, write 4 carry 1. Tens: 5+3+1=9. Hundreds: 4+2=6. Answer: 694.","difficulty":"medium","hint":"Start adding from the ones place.","image_keywords":null,"visual_type":null,"visual_data":null}

True/False example:
{"id":"q3","type":"true_false","role":"error_detection","text":"True or False: 45 × 6 = __(240)__. Is this correct?","options":["True","False"],"correct_answer":"False","explanation":"45 × 6 = 270, not 240.","difficulty":"medium","hint":"Multiply step by step: 40×6 then 5×6.","image_keywords":null,"visual_type":null,"visual_data":null}

Word problem example:
{"id":"q4","type":"word_problem","role":"application","text":"Aarav has ₹500. He buys a notebook for ₹85 and a pen for ₹35. How much money does he have left?","options":null,"correct_answer":"₹380","explanation":"500 - 85 - 35 = 380 rupees.","difficulty":"medium","hint":"Subtract each item's cost one at a time.","image_keywords":null,"visual_type":null,"visual_data":null}

Error detection example:
{"id":"q5","type":"error_detection","role":"thinking","text":"Priya solved: 302 - 168 = 246. Find and correct her mistake.","options":null,"correct_answer":"134","explanation":"302 - 168: ones 2-8 needs borrowing → 12-8=4. Tens: 9-6=3. Hundreds: 2-1=1. Answer: 134.","difficulty":"hard","hint":"Check each column carefully — did she borrow correctly?","image_keywords":null,"visual_type":null,"visual_data":null}"""

_OUTPUT_FORMAT_VISUAL = """\

OUTPUT FORMAT — respond with ONLY this JSON, no other text:
{
  "title": "Worksheet: {topic}",
  "skill_focus": "<one-line skill summary>",
  "common_mistake": "<one common mistake>",
  "parent_tip": "<one tip for parents>",
  "learning_objectives": ["<obj 1>", "<obj 2>", "<obj 3>"],
  "questions": [
    {
      "id": "q1",
      "type": "<mcq|fill_blank|true_false|short_answer|word_problem|error_detection>",
      "role": "<recognition|representation|application|error_detection|thinking>",
      "text": "<question text>",
      "options": ["<A>", "<B>", "<C>", "<D>"] or null,
      "correct_answer": "<accurate answer>",
      "explanation": "<brief explanation>",
      "difficulty": "<easy|medium|hard>",
      "hint": "<helpful hint>",
      "image_keywords": ["<keyword>"] or null,
      "visual_type": "<type or null>",
      "visual_data": { ... } or null
    }
  ]
}

FEW-SHOT EXAMPLES (follow these formats exactly):

MCQ with visual:
{"id":"q1","type":"mcq","role":"application","text":"What is the total value of these coins?","options":["₹15","₹20","₹25","₹30"],"correct_answer":"₹25","explanation":"5+5+5+10 = 25 rupees.","difficulty":"medium","hint":"Add up each coin's value one by one.","image_keywords":null,"visual_type":"money_coins","visual_data":{"coins":[{"value":5,"count":3},{"value":10,"count":1}]}}

Fill-in-the-blank:
{"id":"q2","type":"fill_blank","role":"application","text":"456 + 238 = ______","options":null,"correct_answer":"694","explanation":"Add ones: 6+8=14, write 4 carry 1. Tens: 5+3+1=9. Hundreds: 4+2=6.","difficulty":"medium","hint":"Start from the ones place.","image_keywords":null,"visual_type":null,"visual_data":null}

True/False:
{"id":"q3","type":"true_false","role":"error_detection","text":"True or False: 45 × 6 = 240","options":["True","False"],"correct_answer":"False","explanation":"45 × 6 = 270, not 240.","difficulty":"medium","hint":"Multiply step by step.","image_keywords":null,"visual_type":null,"visual_data":null}

Word problem:
{"id":"q4","type":"word_problem","role":"application","text":"Aarav has ₹500. He buys a notebook for ₹85 and a pen for ₹35. How much money does he have left?","options":null,"correct_answer":"₹380","explanation":"500 - 85 - 35 = 380.","difficulty":"medium","hint":"Subtract each cost one at a time.","image_keywords":null,"visual_type":null,"visual_data":null}

Error detection:
{"id":"q5","type":"error_detection","role":"thinking","text":"Priya solved: 302 - 168 = 246. Find and correct her mistake.","options":null,"correct_answer":"134","explanation":"302 - 168: borrow to get 12-8=4, 9-6=3, 2-1=1 → 134.","difficulty":"hard","hint":"Check each column — did she borrow correctly?","image_keywords":null,"visual_type":null,"visual_data":null}"""


def build_system_prompt(problem_style: str, subject: str) -> str:
    """Build a token-efficient system prompt based on problem style and subject.

    Standard mode omits ~1,500 tokens of visual/image rules.
    Subject filtering reduces image keywords to only relevant ones.
    """
    parts = [_CORE_RULES]

    # Visual block: only for visual/mixed modes
    if problem_style in ("visual", "mixed"):
        parts.append(_VISUAL_BLOCK)

    # Image block: only for non-standard modes AND non-Maths subjects
    if problem_style != "standard":
        keywords = get_keywords_for_subject(subject)
        if keywords:
            parts.append(_IMAGE_BLOCK_TEMPLATE.replace("{keywords}", ", ".join(keywords)))

    # Output format: standard variant omits visual_type/visual_data example
    if problem_style == "standard":
        parts.append(_OUTPUT_FORMAT_STANDARD)
    else:
        parts.append(_OUTPUT_FORMAT_VISUAL)

    return "".join(parts)


# Legacy constant for backward compatibility (tests, etc.)
SYSTEM_PROMPT = build_system_prompt("visual", "EVS")

# ---------------------------------------------------------------------------
# 1B  User Prompt Builder
# ---------------------------------------------------------------------------


_INDIAN_NAMES = [
    "Aarav",
    "Ananya",
    "Vihaan",
    "Diya",
    "Reyansh",
    "Saanvi",
    "Arjun",
    "Isha",
    "Kabir",
    "Myra",
    "Aditya",
    "Kiara",
    "Rohan",
    "Priya",
    "Vivaan",
    "Anika",
    "Krishna",
    "Zara",
    "Rudra",
    "Pari",
    "Atharv",
    "Navya",
    "Shaurya",
    "Aadhya",
    "Dhruv",
    "Riya",
    "Arnav",
    "Sara",
    "Dev",
    "Anvi",
    "Ishan",
    "Tara",
    "Kian",
    "Meera",
    "Yash",
    "Nisha",
    "Aryan",
    "Siya",
    "Neil",
    "Pooja",
    "Rahul",
    "Sneha",
    "Manav",
    "Kavya",
    "Sameer",
    "Tanvi",
    "Kunal",
    "Ritika",
]


# ---------------------------------------------------------------------------
# Skill-tag recipe helpers
# ---------------------------------------------------------------------------

# Suffix-based hints so we don't need 959 entries — just common suffixes
_SKILL_TAG_HINTS: dict[str, str] = {
    # Exact tags
    "clock_reading": "Show a clock face; student reads the time shown",
    "calendar_reading": "Read dates, days, or months from a calendar",
    "column_add_with_carry": "Column addition with carrying/regrouping",
    "column_sub_with_borrow": "Column subtraction with borrowing/regrouping",
    "missing_number": "Fill in the missing number in an equation",
    "estimation": "Estimate the answer before calculating",
    "thinking": "Multi-step reasoning or explain-your-thinking question",
}

# Suffix fallbacks — matched if no exact key found
_SKILL_TAG_SUFFIX_HINTS: dict[str, str] = {
    "_word_problem": "Word problem with a real-life scenario",
    "_fill_blank": "Fill-in-the-blank about the topic",
    "_error_spot": "Show a worked solution with a mistake; student finds the error",
    "_thinking": "Multi-step reasoning or explain-your-thinking question",
    "_reading": "Read and interpret information presented visually",
    "_match": "Match items from two columns",
    "_identify": "Identify or classify the given item",
    "_compare": "Compare two quantities or items",
    "_sequence": "Put items in the correct order or find the pattern",
}


def _get_skill_tag_hint(tag: str) -> str:
    """Return a 1-line description for a skill tag using exact match or suffix fallback."""
    if tag in _SKILL_TAG_HINTS:
        return _SKILL_TAG_HINTS[tag]
    for suffix, hint in _SKILL_TAG_SUFFIX_HINTS.items():
        if tag.endswith(suffix):
            return hint
    # Generic fallback: humanize the tag name
    return tag.replace("_", " ").capitalize()


def _scale_recipe(recipe: list[dict], target: int) -> list[dict]:
    """Scale a 10-question recipe to any target count, preserving proportions.

    Guarantees min-1-per-tag and exact sum == target.
    """
    total = sum(entry["count"] for entry in recipe)
    if total == target:
        return [dict(entry) for entry in recipe]

    # Start with min-1 per tag
    scaled = []
    for entry in recipe:
        scaled.append({"skill_tag": entry["skill_tag"], "count": 1})

    remaining = target - len(scaled)
    if remaining <= 0:
        # More tags than target — truncate to target, keeping first N
        return scaled[:target]

    # Distribute remaining proportionally
    weights = [entry["count"] / total for entry in recipe]
    extra = [int(w * remaining) for w in weights]

    # Distribute rounding remainder to largest tags first
    leftover = remaining - sum(extra)
    indices = sorted(range(len(weights)), key=lambda i: weights[i], reverse=True)
    for i in range(leftover):
        extra[indices[i % len(indices)]] += 1

    for i, entry in enumerate(scaled):
        entry["count"] += extra[i]

    return scaled


# Topic-to-scenario-pool mapping
_TOPIC_POOL_MAP: dict[str, str] = {
    "time": "maths_time.json",
    "clock": "maths_time.json",
    "calendar": "maths_time.json",
    "addition": "maths_addition.json",
    "add": "maths_addition.json",
    "carry": "maths_addition.json",
}


def _build_scenario_block(topic: str, grade_level: str) -> str | None:
    """Load scenario pool for the topic and return a prompt block with sampled data."""
    import json
    from pathlib import Path

    t_lower = topic.lower()
    pool_file = None
    for keyword, filename in _TOPIC_POOL_MAP.items():
        if keyword in t_lower:
            pool_file = filename
            break
    if not pool_file:
        return None

    pools_dir = Path(__file__).resolve().parent.parent / "data" / "scenario_pools"
    pool_path = pools_dir / pool_file
    if not pool_path.exists():
        return None

    pool_data = json.loads(pool_path.read_text())

    # Extract class number from grade_level (e.g. "Class 3" -> "class_3")
    class_key = None
    import re as _re

    m = _re.search(r"\d+", grade_level)
    if m:
        class_key = f"class_{m.group()}"
    if not class_key or class_key not in pool_data:
        return None

    class_data = pool_data[class_key]
    lines = ["\nSCENARIO DATA (use these for variety — sample from these values):"]

    # Time pool
    if "clock_read" in class_data:
        clocks = class_data["clock_read"]
        sampled_clocks = random.sample(clocks, min(3, len(clocks)))
        lines.append("  Clock times: " + ", ".join(c["answer"] for c in sampled_clocks))
    if "duration" in class_data and class_data["duration"]:
        durations = class_data["duration"]
        sampled_durations = random.sample(durations, min(2, len(durations)))
        lines.append("  Durations: " + "; ".join(f"{d['start']} to {d['end']} = {d['dur']}" for d in sampled_durations))

    # Addition pool
    if "pairs" in class_data:
        pairs = class_data["pairs"]
        sampled_pairs = random.sample(pairs, min(3, len(pairs)))
        lines.append("  Number pairs: " + ", ".join(f"{p['a']}+{p['b']}={p['sum']}" for p in sampled_pairs))

    # Common fields
    if "contexts" in class_data:
        contexts = class_data["contexts"]
        sampled_contexts = random.sample(contexts, min(4, len(contexts)))
        lines.append("  Contexts: " + ", ".join(sampled_contexts))

    if len(lines) <= 1:
        return None

    return "\n".join(lines) + "\n"


def build_user_prompt(
    board: str,
    grade_level: str,
    subject: str,
    topic: str,
    difficulty: str,
    num_questions: int,
    language: str,
    problem_style: str = "standard",
    custom_instructions: str | None = None,
) -> str:
    """Build a concise user prompt that reinforces the topic constraint."""
    style_hint = {
        "visual": "visual (include visual elements in most questions)",
        "mixed": "mixed (include some visual questions)",
        "standard": "standard (text-based, no visuals)",
    }.get(problem_style, "standard")

    seed = "".join(random.choices(string.ascii_lowercase, k=6))
    names_str = ", ".join(random.sample(_INDIAN_NAMES, 6))

    prompt = (
        f"Board: {board} | Class: {grade_level} | Subject: {subject}\n"
        f"Topic: {topic} | Difficulty: {difficulty} | Questions: {num_questions}\n"
        f"Language: {language} | Style: {style_hint} | Seed: {seed}\n\n"
        f'Generate {num_questions} ORIGINAL questions strictly about "{topic}". '
        f"Use these names: {names_str}. "
        f"Vary scenarios (market, school, park, zoo, kitchen, festival, playground, train station), "
        f"numbers, and distractors across questions.\n"
    )

    # Problem-style specific image instructions
    if problem_style == "standard":
        prompt += (
            "\nIMPORTANT: Do NOT use image_keywords for any question. "
            "Set image_keywords to null for ALL questions. "
            "Standard mode means text-only worksheets with no cartoon images.\n"
        )
    elif problem_style == "visual":
        prompt += "\nIMPORTANT: EVERY question MUST have at least one image_keyword from the provided list.\n"

    # -- Bloom's taxonomy directive (from prompt_builder.py) --
    bloom_map = {"easy": "recall", "medium": "application", "hard": "reasoning"}
    bloom_key = bloom_map.get(difficulty.lower(), "application")
    bloom_directive = _BLOOM_DIRECTIVES.get(bloom_key)
    if bloom_directive:
        prompt += f"\nCOGNITIVE LEVEL: {bloom_directive}\n"

    # -- Skill-tag recipe injection --
    profile = get_topic_profile(topic, subject)
    if profile:
        # Use recipes_by_count if available, otherwise scale default_recipe
        recipes_by_count = profile.get("recipes_by_count", {})
        if num_questions in recipes_by_count:
            recipe = recipes_by_count[num_questions]
        else:
            recipe = _scale_recipe(profile.get("default_recipe", []), num_questions)

        if recipe:
            lines = []
            for entry in recipe:
                tag = entry["skill_tag"]
                count = entry["count"]
                hint = _get_skill_tag_hint(tag)
                lines.append(f"  - {count}x {tag}: {hint}")
            prompt += (
                "\nSKILL-TAG PLAN (follow this EXACTLY — generate this many of each type):\n" + "\n".join(lines) + "\n"
            )

    # -- Scenario pool injection --
    try:
        scenario_block = _build_scenario_block(topic, grade_level)
        if scenario_block:
            prompt += scenario_block
    except Exception as exc:
        logger.debug("Scenario pool injection skipped: %s", exc)

    # -- Fractions constraint --
    if "fraction" in topic.lower():
        prompt += (
            "\nFRACTIONS CONSTRAINT: Every question MUST contain a fraction "
            "(e.g. 1/2, 3/4, 5/8). No whole-number arithmetic.\n"
        )

    # -- Hindi Devanagari anchor --
    if language.lower() == "hindi" or subject.lower() == "hindi":
        prompt += (
            "\nHINDI SCRIPT: Generate ALL question content in Devanagari script. "
            "NEVER use transliterated Hindi (Roman script for Hindi words). "
            "All Hindi words must use proper Devanagari Unicode characters.\n"
        )

    if custom_instructions:
        prompt += f"\nAdditional teacher instructions: {custom_instructions}"

    return prompt


# ---------------------------------------------------------------------------
# 1C  Gemini Caller
# ---------------------------------------------------------------------------


def call_gemini(
    client,
    system_prompt: str,
    user_prompt: str,
    subject: str = "",
    difficulty: str = "medium",
) -> str:
    """Call the LLM via the existing adapter and return raw text."""
    # Lower temperature for Maths to maintain accuracy, higher for creative subjects
    is_maths = subject.lower() in ("maths", "math", "mathematics")
    temp = 0.5 if is_maths else 0.8

    # Enable chain-of-thought for Maths medium/hard (reduces auto-corrections)
    thinking_budget = 1024 if is_maths and difficulty.lower() in ("medium", "hard") else 0

    # When thinking is enabled, add explicit CoT directive so the model
    # verifies arithmetic before committing to an answer
    if thinking_budget > 0:
        user_prompt = (
            user_prompt + "\n\nCHAIN-OF-THOUGHT: Before writing each answer, mentally compute "
            "the arithmetic step by step. Verify your answer is correct before "
            "writing it. For subtraction with borrowing, check each column."
        )

    response = client.chat.completions.create(
        model="gemini-2.5-flash",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temp,
        max_tokens=4096,
        thinking_budget=thinking_budget,
    )
    return response.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# 1D  Validator
# ---------------------------------------------------------------------------

# Broad topic keywords — NOT 198 profiles, just ~20 categories
_TOPIC_KEYWORDS: dict[str, list[str]] = {
    "time": [
        "time",
        "clock",
        "hour",
        "minute",
        "o'clock",
        "half past",
        "quarter",
        "am",
        "pm",
        "calendar",
        "month",
        "day",
        "week",
    ],
    "addition": ["add", "sum", "plus", "carry", "total", "+"],
    "subtraction": ["subtract", "minus", "borrow", "difference", "take away", "-"],
    "multiplication": ["multiply", "times", "product", "table", "×"],
    "division": ["divide", "share", "quotient", "remainder", "÷"],
    "fraction": ["fraction", "half", "quarter", "numerator", "denominator", "/"],
    "money": ["money", "coin", "rupee", "₹", "price", "cost", "change", "buy", "sell"],
    "shape": ["shape", "triangle", "circle", "square", "rectangle", "side", "corner", "edge"],
    "measurement": ["measure", "length", "weight", "height", "cm", "metre", "kg", "gram", "litre"],
    "pattern": ["pattern", "sequence", "next", "rule", "repeat"],
    "number": ["number", "count", "digit", "place value", "ones", "tens", "hundreds"],
    "data": ["data", "graph", "chart", "tally", "pictograph", "table"],
    "symmetry": ["symmetry", "symmetric", "line of symmetry", "mirror"],
    "spatial": ["in", "out", "near", "far", "above", "below", "left", "right", "position"],
    "grammar": ["noun", "verb", "pronoun", "adjective", "adverb", "tense", "sentence", "punctuation"],
    "comprehension": ["passage", "read", "comprehension", "paragraph", "story"],
    "vocabulary": ["word", "meaning", "synonym", "antonym", "spelling"],
    "hindi": ["matra", "shabd", "vakya", "kaal", "sangya", "sarvanam", "kriya", "varnamala"],
    "science": [
        "plant",
        "animal",
        "body",
        "water",
        "air",
        "food",
        "weather",
        "environment",
        "habitat",
        "material",
        "force",
        "energy",
    ],
    "evs": ["environment", "family", "community", "shelter", "transport", "safety", "festival", "food", "water"],
}


def _detect_topic_category(topic: str) -> str | None:
    """Return the broad topic category for a given topic string."""
    t_lower = topic.lower()
    for category, keywords in _TOPIC_KEYWORDS.items():
        if any(kw in t_lower for kw in keywords):
            return category
    return None


def _is_question_on_topic(question_text: str, topic_category: str | None) -> bool:
    """Check if a question mentions at least one keyword from the topic category."""
    if not topic_category:
        return True  # unknown category — can't check
    keywords = _TOPIC_KEYWORDS.get(topic_category, [])
    q_lower = question_text.lower()
    return any(kw in q_lower for kw in keywords)


def _verify_maths_answer(question: dict) -> str | None:
    """For simple arithmetic questions, compute the answer and auto-correct if wrong.

    Returns the corrected answer, or None if no correction was needed/possible.
    """
    text = question.get("text", "")
    answer = str(question.get("correct_answer", ""))

    # Try to find a simple arithmetic expression in the question
    # Match patterns like "234 + 567", "45 × 8", "100 - 37", "84 ÷ 4"
    pattern = r"(\d+(?:\.\d+)?)\s*([+\-×÷*/])\s*(\d+(?:\.\d+)?)"
    match = re.search(pattern, text)
    if not match:
        return None

    a_str, op, b_str = match.groups()
    try:
        a, b = float(a_str), float(b_str)
    except ValueError:
        return None

    op_map = {"+": a + b, "-": a - b, "×": a * b, "*": a * b}
    if op in ("÷", "/") and b != 0:
        op_map[op] = a / b

    computed = op_map.get(op)
    if computed is None:
        return None

    # Format: prefer integer if whole number
    if computed == int(computed):
        computed_str = str(int(computed))
    else:
        computed_str = str(round(computed, 2))

    # Check if the LLM answer matches
    try:
        llm_val = float(answer.replace(",", "").strip())
        if math.isclose(llm_val, computed, rel_tol=1e-6):
            return None  # correct — no fix needed
    except (ValueError, TypeError):
        pass

    logger.warning(
        "Maths auto-correct: Q '%s' — LLM said '%s', computed '%s'",
        text[:60],
        answer,
        computed_str,
    )
    return computed_str


# ---------------------------------------------------------------------------
# Visual type post-processing
# ---------------------------------------------------------------------------

VISUAL_TYPE_ALIASES: dict[str, str | None] = {
    "clock_face": "clock",
    "clock_analog": "clock",
    "analog_clock": "clock",
    "fraction_bar": "pie_fraction",
    "fraction_circle": "pie_fraction",
    "fraction_pie": "pie_fraction",
    "shape_grid": "shapes",
    "shape": "shapes",
    "base_ten_blocks": "base_ten_regrouping",
    "bar_chart": None,
    "tally_chart": None,
    "diagram_label": None,
    "food_chain": None,
    "lifecycle": None,
    "sentence_diagram": None,
    "word_web": None,
}

SUPPORTED_VISUAL_TYPES = {
    "clock",
    "object_group",
    "shapes",
    "number_line",
    "base_ten_regrouping",
    "pie_fraction",
    "grid_symmetry",
    "money_coins",
    "pattern_tiles",
    "abacus",
}

REQUIRED_VISUAL_FIELDS: dict[str, list[str]] = {
    "clock": ["hour", "minute"],
    "object_group": ["groups", "operation"],
    "shapes": ["shape"],
    "number_line": ["start", "end", "step"],
    "base_ten_regrouping": ["numbers", "operation"],
    "pie_fraction": ["numerator", "denominator"],
    "grid_symmetry": ["grid_size", "filled_cells", "fold_axis"],
    "money_coins": ["coins"],
    "pattern_tiles": ["tiles", "blank_position"],
    "abacus": ["hundreds", "tens", "ones"],
}


VALID_ROLES = {"recognition", "representation", "application", "error_detection", "thinking"}

TIER_ORDER = {"recognition": 0, "representation": 0, "application": 1, "error_detection": 2, "thinking": 2}


def ensure_roles(questions: list[dict], difficulty: str) -> list[dict]:
    """Assign roles if missing, then re-order by tier."""
    for i, q in enumerate(questions):
        if q.get("role") not in VALID_ROLES:
            n = len(questions)
            pct = i / max(n, 1)
            if pct < 0.4:
                q["role"] = "recognition"
            elif pct < 0.8:
                q["role"] = "application"
            else:
                q["role"] = "thinking"
    # Re-order: foundation → application → stretch
    questions.sort(key=lambda q: TIER_ORDER.get(q.get("role", ""), 1))
    return questions


def fix_true_false_options(questions: list[dict]) -> list[dict]:
    """Ensure true_false questions always have options and correct_answer is True/False."""
    for q in questions:
        if q.get("type") == "true_false":
            if not q.get("options"):
                q["options"] = ["True", "False"]
            # Ensure correct_answer is exactly "True" or "False"
            ans = str(q.get("correct_answer", "")).strip().lower()
            if ans not in ("true", "false"):
                # Try to infer: if the answer looks affirmative, set True
                if ans in ("yes", "correct", "right"):
                    q["correct_answer"] = "True"
                else:
                    q["correct_answer"] = "False"
            else:
                q["correct_answer"] = "True" if ans == "true" else "False"
    return questions


def fix_mcq_options(questions: list[dict]) -> list[dict]:
    """Ensure MCQ questions have options, downgrade to short_answer if not."""
    MCQ_PHRASES = ["which of these", "which one of", "which of the following", "which animal", "which option"]

    for q in questions:
        q_type = q.get("type", "")
        options = q.get("options")
        text_lower = q.get("text", "").lower()

        # Case 1: Typed as MCQ but no options → downgrade
        if q_type == "mcq" and (not options or not isinstance(options, list) or len(options) < 2):
            q["type"] = "short_answer"
            q["options"] = None
            logger.warning("MCQ '%s' has no options — downgraded", q.get("id"))

        # Case 2: Typed as MCQ — ensure correct_answer is in options
        elif q_type == "mcq" and options:
            correct = q.get("correct_answer", "")
            if correct and correct not in options:
                for opt in options:
                    if correct.lower().strip() == opt.lower().strip():
                        q["correct_answer"] = opt
                        break

        # Case 3: Text says "which of these" but type is NOT mcq and no options — log it
        elif q_type != "mcq" and any(phrase in text_lower for phrase in MCQ_PHRASES) and not options:
            logger.info("Question '%s' looks like MCQ but typed as '%s' — leaving as-is", q.get("id"), q_type)

    return questions


def detect_true_false(questions: list[dict]) -> list[dict]:
    """Detect questions that are really True/False but typed differently."""
    TF_INDICATORS = [
        "true or false",
        "is this true",
        "is this correct",
        "is this statement true",
        "is this statement correct",
    ]

    for q in questions:
        if q.get("type") == "true_false":
            continue  # Already typed correctly

        text_lower = q.get("text", "").lower().strip()
        correct_lower = (q.get("correct_answer") or "").lower().strip()

        if correct_lower in ("true", "false"):
            if any(indicator in text_lower for indicator in TF_INDICATORS) or not text_lower.endswith("?"):
                q["type"] = "true_false"
                if not q.get("options"):
                    q["options"] = ["True", "False"]

    return questions


PHANTOM_IMAGE_PATTERNS = [
    r"[Ll]ook at the (?:image|picture|animal|figure|shape|object|diagram)(?:\s+(?:below|above|shown))?\.\s*",
    r"[Ss]ee the (?:image|picture|animal|figure)(?:\s+(?:below|above))?\.\s*",
    r"[Tt]he (?:animal|object|image|picture|figure) (?:shown |displayed )?(?:below|above)[.,]?\s*",
    r"[Ii]n the (?:image|picture) (?:below|above)[.,]?\s*",
    r"[Oo]bserve the (?:image|picture|figure)(?:\s+(?:below|above))?\.\s*",
]


def strip_phantom_image_refs(questions: list[dict]) -> list[dict]:
    """Remove 'look at the image' text when no visual or image is provided."""
    for q in questions:
        if q.get("visual_type") is not None or q.get("images"):
            continue  # Has a visual or images — references are fine
        text = q.get("text", "")
        for pattern in PHANTOM_IMAGE_PATTERNS:
            text = re.sub(pattern, "", text)
        text = re.sub(r"\s{2,}", " ", text).strip()
        if text and text[0].islower():
            text = text[0].upper() + text[1:]
        q["text"] = text
    return questions


def resolve_question_images(questions: list[dict]) -> list[dict]:
    """Resolve image_keywords to actual image paths."""
    from app.data.image_registry import resolve_keywords

    _PICTURE_PHRASES = ["look at the picture", "see the image", "shown below", "in the picture"]

    for q in questions:
        keywords = q.pop("image_keywords", None) or []
        # Skip image resolution when an SVG visual already exists (avoids duplicate visuals)
        if keywords and not q.get("visual_type"):
            images = resolve_keywords(keywords)
            if images:
                q["images"] = images  # [{path, alt, category}, ...]
            # If question says "look at the picture" but no valid images, rewrite text
            text = q.get("text", "")
            if not images and any(phrase in text.lower() for phrase in _PICTURE_PHRASES):
                for phrase in [
                    "Look at the picture below. ",
                    "See the image below. ",
                    "Look at the picture. ",
                    "See the image. ",
                ]:
                    text = text.replace(phrase, "")
                q["text"] = text
    return questions


def fix_visual_types(questions: list[dict]) -> list[dict]:
    """Remap known visual type aliases and strip unsupported types."""
    for q in questions:
        vt = q.get("visual_type")
        if vt is None:
            continue
        if vt in VISUAL_TYPE_ALIASES:
            mapped = VISUAL_TYPE_ALIASES[vt]
            if mapped is None:
                q["visual_type"] = None
                q["visual_data"] = None
            else:
                q["visual_type"] = mapped
        elif vt not in SUPPORTED_VISUAL_TYPES:
            q["visual_type"] = None
            q["visual_data"] = None
    return questions


def validate_visual_data(questions: list[dict]) -> list[dict]:
    """Strip visuals whose visual_data is missing required fields."""
    for q in questions:
        vt = q.get("visual_type")
        vd = q.get("visual_data")
        if vt and vd:
            required = REQUIRED_VISUAL_FIELDS.get(vt, [])
            if not all(field in vd for field in required):
                q["visual_type"] = None
                q["visual_data"] = None
        elif vt and not vd:
            q["visual_type"] = None
    return questions


def validate_response(
    raw_text: str,
    subject: str,
    topic: str,
    num_questions: int,
    difficulty: str = "medium",
) -> tuple[dict[str, Any], list[str]]:
    """Validate and repair the LLM response.

    Returns (validated_dict, warnings).
    Raises ValueError if the response is completely unusable.
    """
    warnings: list[str] = []

    # --- JSON parse ---
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        # Try stripping markdown fences
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw_text.strip())
        cleaned = re.sub(r"\s*```$", "", cleaned)
        data = json.loads(cleaned)  # let it raise if still bad

    questions = data.get("questions", [])
    if not questions:
        raise ValueError("LLM returned no questions")

    # --- Schema check ---
    valid_types = {"mcq", "fill_blank", "true_false", "short_answer", "word_problem", "error_detection"}
    for i, q in enumerate(questions):
        qid = q.get("id") or f"q{i + 1}"
        q["id"] = qid

        if "text" not in q or not q["text"]:
            warnings.append(f"{qid}: missing question text")

        if "correct_answer" not in q or q["correct_answer"] is None:
            warnings.append(f"{qid}: missing correct_answer")

        q_type = q.get("type", "short_answer")
        if q_type not in valid_types:
            q["type"] = "short_answer"
            warnings.append(f"{qid}: unknown type '{q_type}', defaulted to short_answer")

        if q_type == "mcq":
            opts = q.get("options") or []
            if len(opts) != 4:
                warnings.append(f"{qid}: MCQ should have 4 options, got {len(opts)}")

    # --- Count check ---
    count_diff = abs(len(questions) - num_questions)
    if count_diff > 1:
        warnings.append(f"Requested {num_questions} questions, got {len(questions)}")

    # --- Maths answer verification ---
    if subject.lower() in ("maths", "mathematics", "math"):
        for q in questions:
            correction = _verify_maths_answer(q)
            if correction is not None:
                q["correct_answer"] = correction
                warnings.append(f"{q['id']}: answer auto-corrected to {correction}")

    # --- Topic drift check ---
    topic_cat = _detect_topic_category(topic)
    if topic_cat:
        off_topic_count = sum(1 for q in questions if not _is_question_on_topic(q.get("text", ""), topic_cat))
        drift_ratio = off_topic_count / max(len(questions), 1)
        if drift_ratio > 0.3:
            warnings.append(
                f"Topic drift: {off_topic_count}/{len(questions)} questions "
                f"appear off-topic for '{topic}' (category: {topic_cat})"
            )

    # --- Visual type fix-up ---
    questions = fix_visual_types(questions)
    questions = validate_visual_data(questions)

    # --- Image keyword resolution ---
    questions = resolve_question_images(questions)

    # --- Question type fixes ---
    questions = detect_true_false(questions)
    questions = fix_true_false_options(questions)
    questions = fix_mcq_options(questions)

    # --- Strip phantom image references ---
    questions = strip_phantom_image_refs(questions)

    # --- Role assignment + tier ordering ---
    questions = ensure_roles(questions, difficulty)

    data["questions"] = questions
    return data, warnings


# ---------------------------------------------------------------------------
# 1E  Generate — single entry-point
# ---------------------------------------------------------------------------


def generate_worksheet(
    client,
    board: str,
    grade_level: str,
    subject: str,
    topic: str,
    difficulty: str,
    num_questions: int = 10,
    language: str = "English",
    problem_style: str = "standard",
    custom_instructions: str | None = None,
) -> tuple[dict[str, Any], int, list[str]]:
    """Generate a validated worksheet via Gemini.

    Returns (worksheet_dict, elapsed_ms, warnings).
    Raises ValueError if generation fails after retries.
    """
    user_prompt = build_user_prompt(
        board=board,
        grade_level=grade_level,
        subject=subject,
        topic=topic,
        difficulty=difficulty,
        num_questions=num_questions,
        language=language,
        problem_style=problem_style,
        custom_instructions=custom_instructions,
    )

    # -- RAG: Inject curriculum context --
    import asyncio

    try:
        from app.services.curriculum import get_curriculum_context

        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                curriculum_context = pool.submit(
                    lambda: asyncio.run(get_curriculum_context(grade_level, subject, topic))
                ).result(timeout=5)
        else:
            curriculum_context = asyncio.run(get_curriculum_context(grade_level, subject, topic))
    except Exception as e:
        logger.warning("Failed to fetch curriculum context for %s/%s: %s", topic, grade_level, e)
        curriculum_context = None

    if curriculum_context:
        user_prompt = f"{curriculum_context}\n\n{user_prompt}"
        logger.info("[v2] Curriculum context injected for %s / %s", topic, grade_level)
    # -- End RAG --

    max_attempts = 2
    last_error: Exception | None = None
    all_warnings: list[str] = []

    for attempt in range(1, max_attempts + 1):
        t0 = time.perf_counter()
        try:
            system_prompt = build_system_prompt(problem_style, subject)
            raw = call_gemini(client, system_prompt, user_prompt, subject=subject, difficulty=difficulty)
            data, warnings = validate_response(raw, subject, topic, num_questions, difficulty)
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            all_warnings.extend(warnings)

            # ── Output validation ──
            from app.services.output_validator import get_validator

            validator = get_validator()
            is_valid, validation_errors = validator.validate_worksheet(
                data, grade=grade_level, subject=subject, topic=topic, num_questions=num_questions
            )
            if not is_valid:
                all_warnings.extend([f"[validation] {e}" for e in validation_errors])
                logger.warning(
                    "Worksheet validation issues",
                    extra={"errors": validation_errors, "topic": topic, "grade": grade_level},
                )

            # Safety net: strip all images in standard mode
            if problem_style == "standard":
                for q in data.get("questions", []):
                    q["images"] = []
                    q.pop("image_keywords", None)

            # Check if retry is needed for topic drift
            drift_warnings = [w for w in warnings if "Topic drift" in w]
            if drift_warnings and attempt < max_attempts:
                logger.warning("[v2] Attempt %d: topic drift detected, retrying", attempt)
                # Strengthen the prompt for retry
                user_prompt += (
                    f"\n\nI REPEAT: only generate questions about {topic}. "
                    f"Do NOT include any questions about other topics."
                )
                all_warnings.append(f"Retry {attempt}: topic drift detected")
                continue

            logger.info(
                "[v2] Generated %d questions in %d ms (attempt %d)",
                len(data.get("questions", [])),
                elapsed_ms,
                attempt,
                system_prompt_version=SYSTEM_PROMPT_VERSION,
                user_prompt_version=USER_PROMPT_VERSION,
            )
            return data, elapsed_ms, all_warnings

        except (json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            logger.warning("[v2] Attempt %d failed (%s): %s", attempt, type(exc).__name__, exc)
            all_warnings.append(f"Attempt {attempt} failed: {exc}")
            if attempt < max_attempts:
                user_prompt += "\n\nIMPORTANT: Respond with ONLY valid JSON. No markdown, no extra text."
                continue

    raise ValueError(f"Worksheet generation failed after {max_attempts} attempts. Last error: {last_error}")
