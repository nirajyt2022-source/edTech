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
import random
import re
import string
import time
from typing import Any

import structlog

from app.data.image_registry import get_keywords_for_subject
from app.data.phrasing_templates import get_phrasing_samples
from app.data.topic_profiles import get_topic_profile
from app.services.prompt_builder import _BLOOM_DIRECTIVES

logger = structlog.get_logger("skolar.worksheet_generator")

# ---------------------------------------------------------------------------
# Prompt versions — bump when changing prompt content, logged with every call
# ---------------------------------------------------------------------------
SYSTEM_PROMPT_VERSION = "v2.5"
USER_PROMPT_VERSION = "v2.6"

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
6. Use Indian context: ₹ for money, Indian names, Indian scenarios (mandi, chai stall, auto-rickshaw, Diwali shopping, cricket match, rangoli, school assembly, temple). Avoid Western scenarios (supermarket, Halloween, Thanksgiving, baseball).
7. VARIETY IS CRITICAL: rotate through scenarios (home, school, market, park, farm, zoo, kitchen, playground, festival, hospital, train station), mix question styles, and vary sentence structures.
   SENTENCE STRUCTURE — Use at least 3 of these structures across the worksheet:
   (a) Direct question: "What is 5 + 3?"
   (b) Imperative: "Find the sum of 12 and 8."
   (c) Contextual/story: "Ravi has 4 apples. His sister gives him 3 more."
   (d) Error-check: "Priya says 7 + 5 = 11. Is she correct?"
   (e) Fill-in: "Complete: 9 + ___ = 15"
8. OPENING VERB ROTATION — Never start two consecutive questions the same way. Rotate through:
   Easy: What|Which|Name|Tell|Find|Show|Write|Count|Circle|Look at
   Medium: Calculate|Solve|Compare|Arrange|Explain|Complete|Fill in|How many|How much|If
   Hard: Analyze|Explain why|Prove|Is this correct|What mistake|Generalize|Predict|Justify
9. NUMBER PROGRESSION — Within each group (Foundation, Application, Stretch), start with
   smaller/simpler numbers and progress to larger ones. First question in a group uses the
   easiest numbers; last question uses the hardest.

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
- NEVER write "look at the image/picture", "In the following", "Read the passage below", or "Given below" — question text must be self-contained.
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
  "common_mistake": "<one common mistake students in THIS class level make on THIS specific topic — never reference higher-grade concepts>",
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
      "skill_tag": "<from SKILL-TAG PLAN, or null if no plan>",
      "image_keywords": null,
      "visual_type": null,
      "visual_data": null
    }
  ]
}

FEW-SHOT EXAMPLES (follow these formats exactly):

MCQ example:
{"id":"q1","type":"mcq","role":"recognition","text":"Which of these is the largest 3-digit number?","options":["999","100","909","990"],"correct_answer":"999","explanation":"The largest 3-digit number has 9 in all places: 999.","difficulty":"easy","hint":"Think about the biggest digit you can put in each place.","skill_tag":null,"image_keywords":null,"visual_type":null,"visual_data":null}

Fill-in-the-blank example:
{"id":"q2","type":"fill_blank","role":"application","text":"456 + 238 = ______","options":null,"correct_answer":"694","explanation":"Add ones: 6+8=14, write 4 carry 1. Tens: 5+3+1=9. Hundreds: 4+2=6. Answer: 694.","difficulty":"medium","hint":"Start adding from the ones place.","skill_tag":null,"image_keywords":null,"visual_type":null,"visual_data":null}

True/False example:
{"id":"q3","type":"true_false","role":"error_detection","text":"True or False: 45 × 6 = __(240)__. Is this correct?","options":["True","False"],"correct_answer":"False","explanation":"45 × 6 = 270, not 240.","difficulty":"medium","hint":"Multiply step by step: 40×6 then 5×6.","skill_tag":null,"image_keywords":null,"visual_type":null,"visual_data":null}

Word problem example:
{"id":"q4","type":"word_problem","role":"application","text":"Aarav has ₹500. He buys a notebook for ₹85 and a pen for ₹35. How much money does he have left?","options":null,"correct_answer":"₹380","explanation":"500 - 85 - 35 = 380 rupees.","difficulty":"medium","hint":"Subtract each item's cost one at a time.","skill_tag":null,"image_keywords":null,"visual_type":null,"visual_data":null}

Error detection example:
{"id":"q5","type":"error_detection","role":"thinking","text":"Priya solved: 302 - 168 = 246. Find and correct her mistake.","options":null,"correct_answer":"134","explanation":"302 - 168: ones 2-8 needs borrowing → 12-8=4. Tens: 9-6=3. Hundreds: 2-1=1. Answer: 134.","difficulty":"hard","hint":"Check each column carefully — did she borrow correctly?","skill_tag":null,"image_keywords":null,"visual_type":null,"visual_data":null}"""

_OUTPUT_FORMAT_VISUAL = """\

OUTPUT FORMAT — respond with ONLY this JSON, no other text:
{
  "title": "Worksheet: {topic}",
  "skill_focus": "<one-line skill summary>",
  "common_mistake": "<one common mistake students in THIS class level make on THIS specific topic — never reference higher-grade concepts>",
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
      "skill_tag": "<from SKILL-TAG PLAN, or null if no plan>",
      "image_keywords": ["<keyword>"] or null,
      "visual_type": "<type or null>",
      "visual_data": { ... } or null
    }
  ]
}

FEW-SHOT EXAMPLES (follow these formats exactly):

MCQ with visual:
{"id":"q1","type":"mcq","role":"application","text":"What is the total value of these coins?","options":["₹15","₹20","₹25","₹30"],"correct_answer":"₹25","explanation":"5+5+5+10 = 25 rupees.","difficulty":"medium","hint":"Add up each coin's value one by one.","skill_tag":null,"image_keywords":null,"visual_type":"money_coins","visual_data":{"coins":[{"value":5,"count":3},{"value":10,"count":1}]}}

Fill-in-the-blank:
{"id":"q2","type":"fill_blank","role":"application","text":"456 + 238 = ______","options":null,"correct_answer":"694","explanation":"Add ones: 6+8=14, write 4 carry 1. Tens: 5+3+1=9. Hundreds: 4+2=6.","difficulty":"medium","hint":"Start from the ones place.","skill_tag":null,"image_keywords":null,"visual_type":null,"visual_data":null}

True/False:
{"id":"q3","type":"true_false","role":"error_detection","text":"True or False: 45 × 6 = 240","options":["True","False"],"correct_answer":"False","explanation":"45 × 6 = 270, not 240.","difficulty":"medium","hint":"Multiply step by step.","skill_tag":null,"image_keywords":null,"visual_type":null,"visual_data":null}

Word problem:
{"id":"q4","type":"word_problem","role":"application","text":"Aarav has ₹500. He buys a notebook for ₹85 and a pen for ₹35. How much money does he have left?","options":null,"correct_answer":"₹380","explanation":"500 - 85 - 35 = 380.","difficulty":"medium","hint":"Subtract each cost one at a time.","skill_tag":null,"image_keywords":null,"visual_type":null,"visual_data":null}

Error detection:
{"id":"q5","type":"error_detection","role":"thinking","text":"Priya solved: 302 - 168 = 246. Find and correct her mistake.","options":null,"correct_answer":"134","explanation":"302 - 168: borrow to get 12-8=4, 9-6=3, 2-1=1 → 134.","difficulty":"hard","hint":"Check each column — did she borrow correctly?","skill_tag":null,"image_keywords":null,"visual_type":null,"visual_data":null}"""


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


def _build_fallback_recipe(subject: str, topic: str, num_questions: int) -> list[dict]:
    """Build a generic skill-tag recipe when no topic profile exists (P2-C).

    Returns a balanced recipe for Science, Hindi, and other subjects that lack
    curated profiles. Uses subject-aware defaults rather than leaving skill_tags
    empty (which causes downstream warnings).
    """
    subj = subject.lower()
    if subj in ("science", "evs"):
        tags = ["recall", "identify", "explain", "classify", "apply"]
    elif subj in ("hindi",):
        tags = ["recall", "identify", "fill_in", "match", "write"]
    elif subj in ("english",):
        tags = ["recall", "identify", "fill_in", "grammar_apply", "write"]
    else:
        # Generic fallback for any subject
        tags = ["recall", "identify", "apply", "explain"]

    # Build recipe: distribute num_questions across tags
    base_count = num_questions // len(tags)
    remainder = num_questions % len(tags)
    recipe = []
    for i, tag in enumerate(tags):
        count = base_count + (1 if i < remainder else 0)
        if count > 0:
            recipe.append({"skill_tag": tag, "count": count})
    return recipe


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
    lines = ["\nSCENARIO DATA (use these for variety — use smaller numbers first, larger later):"]

    # Time pool — sort by hour then minute for progression
    if "clock_read" in class_data:
        clocks = class_data["clock_read"]
        sampled_clocks = random.sample(clocks, min(3, len(clocks)))
        lines.append("  Clock times: " + ", ".join(c["answer"] for c in sampled_clocks))
    if "duration" in class_data and class_data["duration"]:
        durations = class_data["duration"]
        sampled_durations = random.sample(durations, min(2, len(durations)))
        lines.append("  Durations: " + "; ".join(f"{d['start']} to {d['end']} = {d['dur']}" for d in sampled_durations))

    # Addition pool — sort pairs by sum for number progression
    if "pairs" in class_data:
        pairs = class_data["pairs"]
        sorted_pairs = sorted(pairs, key=lambda p: p.get("sum", p.get("a", 0) + p.get("b", 0)))
        n = len(sorted_pairs)
        # Pick from bottom half (Foundation) and top half (Stretch)
        half = max(1, n // 2)
        foundation = sorted_pairs[:half]
        stretch = sorted_pairs[half:]
        f_sample = random.sample(foundation, min(2, len(foundation)))
        s_sample = random.sample(stretch, min(2, len(stretch)))
        f_sample.sort(key=lambda p: p.get("sum", 0))
        s_sample.sort(key=lambda p: p.get("sum", 0))
        if f_sample:
            lines.append("  Foundation pairs: " + ", ".join(f"{p['a']}+{p['b']}={p['sum']}" for p in f_sample))
        if s_sample:
            lines.append("  Stretch pairs: " + ", ".join(f"{p['a']}+{p['b']}={p['sum']}" for p in s_sample))

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
    diagnostic_context: object | None = None,
) -> str:
    """Build a concise user prompt that reinforces the topic constraint."""
    style_hint = {
        "visual": "visual (include visual elements in most questions)",
        "mixed": "mixed (include some visual questions)",
        "standard": "standard (text-based, no visuals)",
    }.get(problem_style, "standard")

    seed = "".join(random.choices(string.ascii_lowercase, k=6))
    names_str = ", ".join(random.sample(_INDIAN_NAMES, min(10, len(_INDIAN_NAMES))))

    prompt = (
        f"Board: {board} | Class: {grade_level} | Subject: {subject}\n"
        f"Topic: {topic} | Difficulty: {difficulty} | Questions: {num_questions}\n"
        f"Language: {language} | Style: {style_hint} | Seed: {seed}\n\n"
        f'Generate {num_questions} ORIGINAL questions strictly about "{topic}". '
        f"Use these names: {names_str}. "
        f"Vary scenarios, numbers, and distractors across questions.\n"
        f"SCENARIO VARIETY: Use DIFFERENT settings for each word problem — choose from: "
        f"mandi (vegetable market), school morning assembly, Diwali shopping, "
        f"train journey, cricket match, temple festival, chai stall, "
        f"mango orchard, rangoli making, kite flying (Makar Sankranti), "
        f"school tiffin sharing, auto-rickshaw ride, Holi celebration, "
        f"anganwadi class, railway platform, sabzi shopping, "
        f"mithai/laddoo making, school sports day, puja preparation, "
        f"family picnic to a park. NEVER repeat a scenario within one worksheet.\n"
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

    # -- MCQ option count variety (S2) --
    prompt += (
        "\nMCQ VARIETY: Not all MCQs should have exactly 4 options. "
        "Use this mix: ~70% with 4 options, ~20% with 3 options, ~10% with 5 options. "
        "This makes the worksheet feel less mechanical.\n"
    )

    # -- Word problem length variety (S3) --
    prompt += (
        "\nWORD PROBLEM LENGTH: Vary sentence count in word problems. "
        "Some should be 2 sentences (short), some 3 sentences (medium), "
        "and at least one should be 4 sentences (detailed context). "
        "Do NOT make every word problem the same length.\n"
    )

    # -- Engagement framing (P2-A, P0-A) --
    warm_count = max(2, num_questions // 5)
    prompt += (
        f"\nENGAGEMENT FRAMING (MANDATORY): Exactly {warm_count} of {num_questions} questions "
        "MUST start with one of these warm openings:\n"
        '  - "Help [name] figure out..."\n'
        '  - "Can you find/spot/solve..."\n'
        '  - "Let\'s figure out..."\n'
        '  - "Try to find..."\n'
        "Use Indian names from the list above. Apply warm framing to word_problem or fill_blank "
        "questions ONLY — keep MCQ/true_false direct.\n"
        "Example: Instead of 'Riya has 5 apples...', write 'Help Riya count: she has 5 apples...'\n"
    )

    # -- Common mistake grounding (P3-B) --
    prompt += (
        "\nCOMMON MISTAKE FIELD: The common_mistake must describe a mistake that students "
        f'in {grade_level} actually make on "{topic}". '
        "Do NOT reference concepts from higher grades. "
        "For example, Class 1 addition should mention 'counting on fingers incorrectly' "
        "not 'forgetting to regroup' (regrouping is Class 2+). "
        "Be specific to the topic and grade.\n"
    )

    # -- Word count limits (P0-B) --
    _wc_match = re.search(r"\d+", grade_level)
    _wc_grade = int(_wc_match.group()) if _wc_match else 3
    _wc_limit = 15 if _wc_grade <= 2 else 25
    prompt += (
        f"\nWORD COUNT LIMIT (HARD): Each question MUST be ≤{_wc_limit} words. "
        f"This is for {grade_level} students. Count every word carefully.\n"
        f"GOOD ({_wc_limit}-word limit):\n"
    )
    if _wc_grade <= 2:
        prompt += (
            '  ✓ "What is 5 + 3?" (5 words)\n'
            '  ✓ "Riya has 4 apples. She gets 2 more. How many?" (10 words)\n'
            '  ✗ "Riya went to the big market near her house and she bought 5 red apples" (14 words — TOO LONG)\n'
            "Keep sentences SHORT and SIMPLE. One clause only. No extra adjectives.\n"
        )
    else:
        prompt += (
            '  ✓ "A train travels 45 km in the first hour and 38 km in the second. Find the total." (17 words)\n'
            '  ✗ "During their annual school trip to the hill station, Aarav noticed that the bus covered..." (15+ words of setup before the question — TOO VERBOSE)\n'
            "Remove unnecessary scene-setting. Get to the maths quickly.\n"
        )

    # -- Explanation vocabulary gate (P2-B) --
    if _wc_grade <= 2:
        prompt += (
            "\nEXPLANATION LANGUAGE: Explanations must use ONLY words a "
            f"{grade_level} child knows. Use simple words: big/small, same/different, "
            "more/less, add/take away. Do NOT use: cuboid, vertex, vertices, "
            "equidistant, tapers, perpendicular, horizontal, parallel. "
            "If a concept needs a big word, explain it simply instead.\n"
        )
    elif _wc_grade <= 3:
        prompt += (
            "\nEXPLANATION LANGUAGE: Keep explanations in simple sentences. "
            "Avoid technical jargon unless the topic teaches that word. "
            "Use 'corner' not 'vertex', 'flat surface' not 'face'.\n"
        )

    # -- Indian currency enforcement (P3-A) --
    _money_keywords = {"money", "coin", "rupee", "price", "cost", "buy", "sell", "change", "shopping"}
    if subject.lower() in ("maths", "mathematics", "math") and any(k in topic.lower() for k in _money_keywords):
        prompt += (
            "\nINDIAN CURRENCY (MANDATORY): ALL money amounts MUST use the ₹ symbol. "
            "Write ₹50, ₹120, ₹5 — NEVER 'Rs.' or just numbers for money. "
            "Use realistic Indian prices: ₹5 for a pencil, ₹10 for a notebook, "
            "₹20 for auto fare, ₹30 for chai, ₹100 for a school bag.\n"
        )

    # -- Sentence structure variety (P3-B) --
    prompt += (
        "\nSENTENCE STARTERS (MANDATORY): Use at LEAST 3 different sentence structures:\n"
        "  1. Question words: 'What is...', 'How many...', 'Which...'\n"
        "  2. Imperatives: 'Find...', 'Solve...', 'Write...', 'Complete...'\n"
        "  3. Conditional/scenario: 'If Riya has...', 'Suppose...'\n"
        "  4. Statement: 'A box contains...', 'There are...'\n"
        "Do NOT start every question the same way. Mix at least 3 of the 4 types above.\n"
    )

    # -- NCERT terminology injection --
    _grade_match = re.search(r"\d+", grade_level)
    if _grade_match:
        from app.data.ncert_terminology import get_terminology_instructions

        term_block = get_terminology_instructions(subject, int(_grade_match.group()))
        if term_block:
            prompt += f"\n{term_block}\n"

    # -- Skill-tag recipe injection --
    profile = get_topic_profile(topic, subject)
    if profile:
        # Use recipes_by_count if available, otherwise scale default_recipe
        recipes_by_count = profile.get("recipes_by_count", {})
        if num_questions in recipes_by_count:
            recipe = recipes_by_count[num_questions]
        else:
            recipe = _scale_recipe(profile.get("default_recipe", []), num_questions)
    else:
        # Fallback: generate generic skill tags based on subject (P2-C)
        recipe = _build_fallback_recipe(subject, topic, num_questions)

        # D-05: Apply diagnostic weights to recipe if available
        if recipe and diagnostic_context and hasattr(diagnostic_context, "skill_tag_weights"):
            weights = getattr(diagnostic_context, "skill_tag_weights", {})
            if weights:
                from app.data.topic_profiles import apply_diagnostic_weights

                recipe = apply_diagnostic_weights(recipe, weights, num_questions)

        if recipe:
            lines = []
            for entry in recipe:
                tag = entry["skill_tag"]
                count = entry["count"]
                hint = _get_skill_tag_hint(tag)
                line = f"  - {count}x {tag}: {hint}"
                phrasings = get_phrasing_samples(tag, count=2)
                if phrasings:
                    examples = " | ".join(f'"{p}"' for p in phrasings)
                    line += f"\n    Phrasing ideas: {examples}"
                lines.append(line)
            prompt += (
                "\nSKILL-TAG PLAN (follow this EXACTLY — generate this many of each type):\n" + "\n".join(lines) + "\n"
                'Each question MUST include a "skill_tag" field matching one tag from the plan above.\n'
            )

        # D-05: Inject misconception-targeting instructions in remediation mode
        if diagnostic_context and hasattr(diagnostic_context, "mode"):
            diag_mode = getattr(diagnostic_context, "mode", "normal")
            misconceptions = getattr(diagnostic_context, "misconceptions_to_target", [])
            if diag_mode == "remediation" and misconceptions:
                from app.data.misconception_taxonomy import MISCONCEPTION_TAXONOMY

                misc_lines = []
                for mid in misconceptions[:3]:
                    entry = MISCONCEPTION_TAXONOMY.get(mid, {})
                    display = entry.get("display", mid)
                    misc_lines.append(f"  - {display}")
                prompt += (
                    "\nREMEDIATION MODE: This student has systematic errors. "
                    "Design questions that help diagnose and address these misconceptions:\n"
                    + "\n".join(misc_lines)
                    + "\n"
                    "Include step-by-step worked examples and scaffolded questions.\n"
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
        # T3: Hindi spoken register — child-friendly, not textbook-formal
        prompt += (
            "\nHINDI REGISTER: Use spoken, child-friendly Hindi — NOT textbook-formal. "
            "AVOID formal words like: अतः, अभिव्यक्त, निर्धारित, परिभाषित, व्याख्या, "
            "तत्पश्चात, अनुसार, प्रयुक्त, उपर्युक्त, निम्नलिखित. "
            "USE simple words like: तो, बताओ, लिखो, सोचो, गिनो, देखो, पढ़ो. "
            "Write as a friendly teacher would speak to a child, not as a textbook.\n"
        )
        # 4a: Inject Devanagari word anchors from topic profile
        try:
            _profile = get_topic_profile(topic, subject)
            _deva = (_profile or {}).get("devanagari_examples", [])
            if _deva:
                anchors = ", ".join(_deva[:12])
                prompt += f"\nHINDI EXAMPLES: Use these Devanagari words as anchors: {anchors}\n"
        except Exception as exc:
            logger.warning("[v2] Failed to load Devanagari examples for %s: %s", topic, exc)

    # ── Number progression directive ──
    if subject.lower() in ("maths", "mathematics", "math") and num_questions >= 5:
        prompt += """
NUMBER PROGRESSION RULE:
- Questions 1-3 (warm-up): Use small, friendly numbers appropriate for the grade level
- Questions 4-7 (practice): Use medium-range numbers that require more thought
- Questions 8-10 (stretch): Use larger numbers that challenge the student
This creates a natural difficulty ramp within the worksheet.
"""

    # -- Number diversity (P2-C) --
    if subject.lower() in ("maths", "mathematics", "math"):
        prompt += (
            "\nNUMBER DIVERSITY: At most 30% of numbers may be multiples of 5 or 10. "
            "Use varied numbers like 13, 27, 38, 46, 72, 84, 91 — NOT just 10, 15, 20, 25, 30, 50. "
            "Round numbers feel mechanical and reduce learning variety.\n"
        )
        # Topic-specific reinforcement for high-round-number topics
        _t = topic.lower()
        if "percent" in _t:
            prompt += (
                "\nPERCENTAGE NUMBERS: Use non-round percentages like 18%, 23%, 37%, 42%, 65%, 78%. "
                "Do NOT always use 10%, 20%, 25%, 50%, 75%. "
                "Also use non-round totals: 90 students, 150 mangoes, 250 tickets — "
                "mix with odd totals like 80, 120, 160.\n"
            )
        elif "time" in _t or "clock" in _t:
            prompt += (
                "\nTIME NUMBERS: Use varied minutes like :07, :13, :22, :38, :47, :53. "
                "Do NOT always use :00, :05, :10, :15, :30, :45. "
                "Mix durations: 17 minutes, 23 minutes, 43 minutes — not just 15, 20, 30.\n"
            )
        elif "decimal" in _t:
            prompt += (
                "\nDECIMAL NUMBERS: Use varied decimal places like 3.47, 8.63, 2.19, 14.86, 7.32. "
                "Do NOT always use .0 or .5 endings (like 2.5, 3.0, 7.5). "
                "At least 60% of decimals should have non-zero, non-five hundredths digits "
                "(e.g., 4.83 not 4.50, 12.67 not 12.00). This tests true decimal understanding.\n"
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
    num_questions: int = 10,
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

    # Scale max_tokens for larger question counts — Devanagari/Hindi text
    # uses ~250-350 tokens per question; 4096 truncates at ~12-14 questions.
    base_tokens = 4096
    if num_questions > 10:
        base_tokens = min(8192, 4096 + (num_questions - 10) * 400)

    response = client.chat.completions.create(
        model="gemini-2.5-flash",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temp,
        max_tokens=base_tokens,
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
    "addition": ["add", "sum", "plus", "carry", "total"],
    "subtraction": ["subtract", "minus", "borrow", "difference", "take away"],
    "multiplication": ["multiply", "multiplication", "times", "product", "table"],
    "division": ["divide", "division", "share", "quotient", "remainder"],
    "fraction": ["fraction", "decimal", "half", "quarter", "numerator", "denominator"],
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
    "vocabulary": [
        "word",
        "meaning",
        "synonym",
        "antonym",
        "spelling",
        "opposite",
        "rhyming",
        "prefix",
        "suffix",
        "compound",
        "syllable",
        # Hindi equivalents for vocabulary/vilom shabd questions
        "विलोम",
        "पर्यायवाची",
        "शब्द",
        "अर्थ",
        "उल्टा",
        "मतलब",
    ],
    "hindi": [
        "matra",
        "shabd",
        "vakya",
        "kaal",
        "sangya",
        "sarvanam",
        "kriya",
        "varnamala",
        "vachan",
        "ling",
        "मात्रा",
        "शब्द",
        "वाक्य",
        "काल",
        "संज्ञा",
        "सर्वनाम",
        "क्रिया",
        "वर्णमाला",
        "अक्षर",
        "व्याकरण",
        "विलोम",
        "पर्यायवाची",
        "मुहावरा",
        "लेख",
        "कहानी",
        "कविता",
        "वचन",
        "एकवचन",
        "बहुवचन",
        "लिंग",
    ],
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


# ---------------------------------------------------------------------------
# Warning severity categorization
# ---------------------------------------------------------------------------

_CRITICAL_WARNING_RE = re.compile(r"(?i)(math.*unverified|BLOCKED|_needs_regen|empty question|missing answer)")
_MODERATE_WARNING_RE = re.compile(r"(?i)(retry|format.*drift|curriculum.*unavailable|skill.*tag|validation)")


def _categorize_warnings(warnings: list[str]) -> dict:
    """Classify warnings into critical/moderate/info and compute severity score.

    Returns dict with keys: critical, moderate, info (counts),
    severity_score (int), and quality_tier ("high"/"medium"/"low").
    """
    crit = mod = info = 0
    for w in warnings:
        if _CRITICAL_WARNING_RE.search(w):
            crit += 1
        elif _MODERATE_WARNING_RE.search(w):
            mod += 1
        else:
            info += 1

    score = crit * 3 + mod * 2 + info * 1

    if crit > 0 or score >= 6:
        tier = "low"
    elif mod > 0 or score >= 3:
        tier = "medium"
    else:
        tier = "high"

    return {
        "critical": crit,
        "moderate": mod,
        "info": info,
        "severity_score": score,
        "quality_tier": tier,
    }


def _detect_topic_category(topic: str) -> str | None:
    """Return the broad topic category for a given topic string.

    Prioritises the topic's primary name (before any parenthetical qualifier)
    and uses word-boundary matching for short keywords to avoid false positives.
    """
    t_lower = topic.lower()
    # Extract primary topic name (before parentheses) for priority matching
    primary = t_lower.split("(")[0].strip() if "(" in t_lower else t_lower

    best_match: str | None = None
    best_score = 0
    for category, keywords in _TOPIC_KEYWORDS.items():
        score = 0
        for kw in keywords:
            if len(kw) <= 2:
                # Short keywords need word boundary
                if re.search(rf"\b{re.escape(kw)}\b", t_lower):
                    score += 1
            else:
                # Primary name match scores 3x (the topic IS about this)
                if kw in primary:
                    score += 3
                elif kw in t_lower:
                    score += 1
        if score > best_score:
            best_score = score
            best_match = category
    return best_match if best_score > 0 else None


def _is_question_on_topic(question_text: str, topic_category: str | None) -> bool:
    """Check if a question mentions at least one keyword from the topic category."""
    if not topic_category:
        return True  # unknown category — can't check
    keywords = _TOPIC_KEYWORDS.get(topic_category, [])
    q_lower = question_text.lower()
    return any(kw in q_lower for kw in keywords)


def _verify_maths_answer(question: dict) -> str | None:
    """For arithmetic questions, compute the answer and auto-correct if wrong.

    Delegates to the multi-step parser in quality_reviewer for a+b+c, a*b+c, etc.
    Returns the corrected answer, or None if no correction was needed/possible.
    """
    from app.services.quality_reviewer import (
        _answers_match,
        _extract_arithmetic_expression,
        _extract_word_problem_arithmetic,
    )

    text = question.get("text", "")
    answer = str(question.get("correct_answer", ""))

    extracted = _extract_arithmetic_expression(text)
    if extracted is None:
        extracted = _extract_word_problem_arithmetic(text)
        if extracted is None:
            return None

    _expr, computed = extracted
    if _answers_match(answer, computed):
        return None

    computed_str = str(int(computed)) if computed == int(computed) else str(round(computed, 2))
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
        # Try stripping markdown fences and control characters
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw_text.strip())
        cleaned = re.sub(r"\s*```$", "", cleaned)
        # Strip control characters (except \n, \r, \t) that LLMs sometimes inject
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", cleaned)
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
            warnings.append(f"[type_error] {qid}: unknown type '{q_type}', defaulted to short_answer")

        # Sync format ← type so downstream consumers (difficulty_calibrator,
        # release_gate) see the correct format instead of defaulting to "other".
        q["format"] = q["type"]

        if q_type == "mcq":
            opts = q.get("options") or []
            if len(opts) != 4:
                warnings.append(f"{qid}: MCQ should have 4 options, got {len(opts)}")
                # Auto-fix: trim to 4 (keep correct answer) or pad with "None of the above"
                correct = q.get("correct_answer", "")
                if len(opts) > 4:
                    # Keep correct answer + first 3 others
                    others = [o for o in opts if o != correct][:3]
                    q["options"] = others + [correct] if correct not in others else opts[:4]
                elif 1 <= len(opts) < 4:
                    # Pad with generic distractors
                    _fillers = [
                        "None of the above",
                        "Cannot be determined",
                        "All of the above",
                        "Not enough information",
                    ]
                    while len(opts) < 4:
                        filler = _fillers[len(opts) - 1] if len(opts) - 1 < len(_fillers) else f"Option {len(opts) + 1}"
                        if filler not in opts:
                            opts.append(filler)
                        else:
                            opts.append(f"Option {len(opts) + 1}")
                    q["options"] = opts

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
    # Only run keyword-based drift detection for Maths topics.  Non-Maths
    # subjects (English, Hindi, Science, EVS) produce rampant false positives
    # because question text rarely contains explicit grammar/science keywords.
    _drift_subjects = {"maths", "mathematics", "math"}
    if subject.lower() in _drift_subjects:
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
# 1E  Helpers + Generate — single entry-point
# ---------------------------------------------------------------------------


def _extract_repeated_templates(questions: list[dict], threshold: int = 3) -> list[str]:
    """Return template strings that appear >= *threshold* times in *questions*.

    Uses OutputValidator._make_template to normalise names/numbers/times.
    """
    from collections import Counter

    from app.services.output_validator import OutputValidator

    templates = [OutputValidator._make_template(q.get("text", "")) for q in questions]
    counts = Counter(templates)
    return [tmpl for tmpl, cnt in counts.most_common() if cnt >= threshold]


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
    diagnostic_context: object | None = None,
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
        diagnostic_context=diagnostic_context,
    )

    # -- RAG: Inject curriculum context --
    import asyncio

    curriculum_context = None
    curriculum_warnings: list[str] = []
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
        curriculum_warnings.append(
            f"[curriculum] NCERT context unavailable for {topic} — worksheet generated without curriculum grounding"
        )

    if curriculum_context:
        user_prompt = f"{curriculum_context}\n\n{user_prompt}"
        logger.info("[v2] Curriculum context injected for %s / %s", topic, grade_level)
    # -- End RAG --

    # -- Chapter name for PDF curriculum badge --
    chapter_name = None
    try:
        import concurrent.futures as _cf

        from app.services.curriculum import get_chapter_name as _get_ch

        with _cf.ThreadPoolExecutor() as _pool:
            chapter_name = _pool.submit(lambda: asyncio.run(_get_ch(grade_level, subject, topic))).result(timeout=3)
    except Exception as exc:
        logger.warning("Chapter name fetch failed (DB): %s", exc)

    # Fallback to static NCERT chapter map if DB returned nothing
    if chapter_name is None:
        try:
            from app.data.ncert_chapter_map import get_static_chapter

            chapter_name = get_static_chapter(grade_level, subject, topic)
            if chapter_name:
                logger.info("Chapter name resolved via static map: %s", chapter_name)
        except Exception as exc2:
            logger.warning("Static chapter map lookup failed: %s", exc2)

    if chapter_name is None:
        curriculum_warnings.append("[curriculum] Chapter reference unavailable — PDF badge removed")

    # P3-B: Warn when visual-dependent topics are in text-only mode
    _VISUAL_TOPICS = {"time", "clock", "shape", "pattern", "geometry", "symmetry", "graph", "chart", "pictograph"}
    if problem_style == "standard" and any(vt in topic.lower() for vt in _VISUAL_TOPICS):
        curriculum_warnings.append(
            f"[visual_recommendation] Topic '{topic}' benefits from visual elements (clock faces, "
            "shape diagrams). Consider using problem_style='visual' or 'mixed' for better pedagogy."
        )

    max_attempts = 3
    last_error: Exception | None = None
    all_warnings: list[str] = list(curriculum_warnings)

    for attempt in range(1, max_attempts + 1):
        t0 = time.perf_counter()
        try:
            system_prompt = build_system_prompt(problem_style, subject)
            raw = call_gemini(
                client, system_prompt, user_prompt, subject=subject, difficulty=difficulty, num_questions=num_questions
            )
            data, warnings = validate_response(raw, subject, topic, num_questions, difficulty)
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            all_warnings.extend(warnings)

            # ── Common mistake length cap (P2-D) ──
            _cm = data.get("common_mistake", "")
            if _cm and len(_cm.split()) > 20:
                # Keep first sentence only, or truncate to ~20 words
                _cm_sentences = [s.strip() for s in _cm.split(".") if s.strip()]
                if _cm_sentences:
                    data["common_mistake"] = _cm_sentences[0] + "."
                    logger.info(
                        "[common_mistake] Trimmed from %d to %d words",
                        len(_cm.split()),
                        len(data["common_mistake"].split()),
                    )

            # ── Question count top-up ──
            questions = data.get("questions", [])
            shortfall = num_questions - len(questions)
            if 0 < shortfall <= 3:
                try:
                    topup_prompt = (
                        f"Generate exactly {shortfall} more questions about '{topic}' "
                        f"for Class {grade_level} {subject} at {difficulty} difficulty. "
                        f"Return ONLY a JSON array of question objects with the same schema "
                        f"as before (id, type, text, correct_answer, options if MCQ)."
                    )
                    topup_raw = call_gemini(client, system_prompt, topup_prompt, subject=subject, difficulty=difficulty)
                    # Extract JSON array from response
                    topup_match = re.search(r"\[.*\]", topup_raw, re.DOTALL)
                    if topup_match:
                        topup_qs = json.loads(topup_match.group())
                        for idx, tq in enumerate(topup_qs):
                            tq["id"] = f"q{len(questions) + idx + 1}"
                            # Pad/trim MCQ options (topup skips validate_response)
                            if tq.get("type") == "mcq":
                                opts = tq.get("options") or []
                                correct = tq.get("correct_answer", "")
                                if len(opts) > 4:
                                    others = [o for o in opts if o != correct][:3]
                                    tq["options"] = others + [correct] if correct not in others else opts[:4]
                                elif 1 <= len(opts) < 4:
                                    _fillers = [
                                        "None of the above",
                                        "Cannot be determined",
                                        "All of the above",
                                        "Not enough information",
                                    ]
                                    while len(opts) < 4:
                                        filler = (
                                            _fillers[len(opts) - 1]
                                            if len(opts) - 1 < len(_fillers)
                                            else f"Option {len(opts) + 1}"
                                        )
                                        opts.append(filler if filler not in opts else f"Option {len(opts) + 1}")
                                    tq["options"] = opts
                        data["questions"] = questions + topup_qs
                        all_warnings.append(
                            f"[topup] Generated {len(topup_qs)} extra question(s) to reach {num_questions}"
                        )
                        logger.info("[topup] Generated %d extra question(s)", len(topup_qs))
                except Exception as exc:
                    logger.warning("[topup] Failed to backfill %d question(s): %s", shortfall, exc)
                    all_warnings.append(f"[topup] Backfill failed: {exc}")

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

            # ── QualityReviewer (Agent 3) ──
            try:
                from app.services.quality_reviewer import get_quality_reviewer
                from app.services.topic_intelligence import GenerationContext

                # Build minimal GenerationContext from available params
                _profile = get_topic_profile(topic, subject) or {}
                _grade_int = (
                    int(re.search(r"\d+", str(grade_level)).group()) if re.search(r"\d+", str(grade_level)) else 3
                )
                # Fix P1-B: Replace grade prefix in skill tags to match actual grade
                _raw_tags = list(_profile.get("allowed_skill_tags", []))
                _grade_fixed_tags = []
                for _tag in _raw_tags:
                    # Replace cN_ prefix with actual grade (e.g., c5_ → c2_ for Class 2)
                    _fixed = re.sub(r"^(c)\d+(_)", rf"\g<1>{_grade_int}\2", _tag)
                    _grade_fixed_tags.append(_fixed)

                _gen_ctx = GenerationContext(
                    topic_slug=topic,
                    subject=subject,
                    grade=_grade_int,
                    ncert_chapter=topic,
                    ncert_subtopics=[],
                    bloom_level="recall",
                    format_mix={"mcq": 40, "fill_blank": 30, "word_problem": 30},
                    scaffolding=False,
                    challenge_mode=False,
                    valid_skill_tags=_grade_fixed_tags,
                    child_context={},
                )

                # Map v2 field names → v1 for QualityReviewer
                _v2_questions = data.get("questions", [])
                for _q in _v2_questions:
                    if "text" in _q and "question_text" not in _q:
                        _q["question_text"] = _q["text"]
                    if "correct_answer" in _q and "answer" not in _q:
                        _q["answer"] = _q["correct_answer"]
                    if "type" in _q and "slot_type" not in _q:
                        _q["slot_type"] = _q["type"]

                _review = get_quality_reviewer().review_worksheet(_v2_questions, _gen_ctx)

                # Map v1 corrections back → v2
                for _q in _review.questions:
                    if "_answer_corrected" in _q and "answer" in _q:
                        _q["correct_answer"] = _q["answer"]
                    if "question_text" in _q:
                        _q["text"] = _q["question_text"]

                data["questions"] = _review.questions
                all_warnings.extend([f"[quality_reviewer] {c}" for c in _review.corrections])
                all_warnings.extend([f"[quality_reviewer] {w}" for w in _review.warnings])
                logger.info(
                    "[quality_reviewer] %d correction(s), %d warning(s)",
                    len(_review.corrections),
                    len(_review.warnings),
                )
            except Exception as exc:
                logger.warning("[quality_reviewer] Agent failed (non-blocking): %s", exc)
                all_warnings.append(f"[quality_reviewer] Skipped: {exc}")

            # ── Fallback Bank (replace _needs_regen questions) ──
            try:
                from app.services.fallback_bank import replace_regen_questions

                _v2_questions = data.get("questions", [])
                _v2_questions, _fb_logs = replace_regen_questions(_v2_questions, _gen_ctx)
                data["questions"] = _v2_questions
                all_warnings.extend(_fb_logs)
            except Exception as exc:
                logger.warning("[fallback_bank] Skipped (non-blocking): %s", exc)

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

            # Near-duplicate retry
            dup_errors = [e for e in validation_errors if "Near-duplicate" in e]
            if dup_errors and attempt < max_attempts:
                repeated = _extract_repeated_templates(data.get("questions", []))
                if repeated:
                    neg = "\n\nDO NOT repeat these question patterns:\n"
                    for tmpl in repeated[:3]:
                        neg += f'  - "{tmpl}"\n'
                    neg += "Each question MUST have a DIFFERENT sentence structure.\n"
                    user_prompt += neg
                    all_warnings.append(f"Retry {attempt}: near-duplicate patterns detected")
                    logger.warning("[v2] Attempt %d: near-duplicates, retrying", attempt)
                    continue

            # Unknown type retry — LLM returned types we don't support
            type_errors = [w for w in warnings if "[type_error]" in w]
            if type_errors and attempt < max_attempts:
                user_prompt += (
                    "\n\nIMPORTANT: Only use these question types: "
                    "mcq, fill_blank, true_false, short_answer, word_problem, error_detection. "
                    "Do NOT invent new question types."
                )
                all_warnings.append(f"Retry {attempt}: unknown question types detected")
                logger.warning("[v2] Attempt %d: unknown types %s, retrying", attempt, type_errors)
                continue

            # Count mismatch retry — got fewer questions than requested
            count_errors = [e for e in validation_errors if "[count_mismatch]" in e]
            if count_errors and attempt < max_attempts:
                user_prompt += (
                    f"\n\nYou MUST generate EXACTLY {num_questions} questions. Not fewer, not more. Count carefully."
                )
                all_warnings.append(f"Retry {attempt}: question count mismatch")
                logger.warning("[v2] Attempt %d: count mismatch, retrying", attempt)
                continue

            # Math unverified retry — questions where arithmetic check failed
            unverified = [q for q in data.get("questions", []) if q.get("_math_unverified")]
            if len(unverified) > 2 and attempt < max_attempts:
                user_prompt += (
                    "\n\nCRITICAL: Every arithmetic question must have a verifiably correct answer. "
                    "Show your working: state the expression and its result clearly."
                )
                all_warnings.append(f"Retry {attempt}: {len(unverified)} math answers unverifiable")
                logger.warning("[v2] Attempt %d: %d unverified math answers, retrying", attempt, len(unverified))
                continue

            # Generic validation error retry — catch math incorrect, MCQ answer
            # not in options, empty text, etc. that weren't caught by specific checks above
            serious_errors = [
                e
                for e in validation_errors
                if "[count_mismatch]" not in e  # already handled above
                and "Near-duplicate" not in e  # already handled above
                and any(kw in e for kw in ("math answer", "empty question", "MCQ answer", "MCQ needs"))
            ]
            if serious_errors and attempt < max_attempts:
                feedback = "; ".join(serious_errors[:3])
                user_prompt += (
                    f"\n\nFIX THESE ERRORS in your next attempt:\n{feedback}\n"
                    "Every MCQ answer must be one of the options. "
                    "Every question must have non-empty text. "
                    "Every math answer must be correct."
                )
                all_warnings.append(f"Retry {attempt}: {len(serious_errors)} validation error(s)")
                logger.warning(
                    "[v2] Attempt %d: %d serious validation errors, retrying: %s",
                    attempt,
                    len(serious_errors),
                    feedback,
                )
                continue

            logger.info(
                "[v2] Generated %d questions in %d ms (attempt %d)",
                len(data.get("questions", [])),
                elapsed_ms,
                attempt,
                system_prompt_version=SYSTEM_PROMPT_VERSION,
                user_prompt_version=USER_PROMPT_VERSION,
            )
            data["chapter_ref"] = chapter_name

            # ── DifficultyCalibrator (Agent 4) ──
            try:
                from app.services.difficulty_calibrator import get_difficulty_calibrator

                # Reuse _gen_ctx from QualityReviewer if available, else build fresh
                if "_gen_ctx" not in dir():
                    from app.services.topic_intelligence import GenerationContext as _GC

                    _profile = get_topic_profile(topic, subject) or {}
                    _grade_int = (
                        int(re.search(r"\d+", str(grade_level)).group()) if re.search(r"\d+", str(grade_level)) else 3
                    )
                    _gen_ctx = _GC(
                        topic_slug=topic,
                        subject=subject,
                        grade=_grade_int,
                        ncert_chapter=topic,
                        ncert_subtopics=[],
                        bloom_level="recall",
                        format_mix={"mcq": 40, "fill_blank": 30, "word_problem": 30},
                        scaffolding=False,
                        challenge_mode=False,
                        valid_skill_tags=list(_profile.get("allowed_skill_tags", [])),
                        child_context={},
                    )

                # Map v2 fields for calibrator (expects question_text)
                for _q in data.get("questions", []):
                    if "text" in _q and "question_text" not in _q:
                        _q["question_text"] = _q["text"]

                calibrated, cal_warnings = get_difficulty_calibrator().calibrate(data.get("questions", []), _gen_ctx)
                # Renumber question IDs to match final position (P2-B)
                for _i, _q in enumerate(calibrated):
                    _q["id"] = f"q{_i + 1}"
                data["questions"] = calibrated
                all_warnings.extend([f"[difficulty_calibrator] {w}" for w in cal_warnings])
                logger.info("[difficulty_calibrator] %d warning(s)", len(cal_warnings))
            except Exception as exc:
                logger.warning("[difficulty_calibrator] Agent failed (non-blocking): %s", exc)
                all_warnings.append(f"[difficulty_calibrator] Skipped: {exc}")

            # ── Release Gate (final enforcement) ──
            from app.services.release_gate import run_release_gate

            release = run_release_gate(
                questions=data.get("questions", []),
                grade_level=grade_level,
                subject=subject,
                topic=topic,
                num_questions=num_questions,
                difficulty=difficulty,
                warnings=all_warnings,
                generation_context=None,
                curriculum_available=bool(chapter_name),
            )
            data["_release_stamps"] = release.stamps
            data["_release_verdict"] = release.verdict

            if release.verdict == "blocked" and attempt < max_attempts:
                feedback = "; ".join(release.block_reasons[:3])
                user_prompt += f"\n\nQUALITY GATE REJECTED: {feedback}\nFix these issues."
                all_warnings.append(f"[release_gate] BLOCKED: {feedback}")
                continue

            if release.verdict == "blocked":
                all_warnings.extend(release.block_reasons)
                raise ValueError(f"Release gate blocked after {max_attempts} attempts: {release.block_reasons}")

            all_warnings.extend(release.degrade_reasons)

            # ── Quality Score (P2-D) ──
            try:
                from app.services.quality_scorer import score_worksheet as _score_ws

                _qs = _score_ws(data, expected_count=num_questions)
                data["_quality_score"] = _qs.total_score
                data["_quality_export_allowed"] = _qs.export_allowed
            except Exception as _qs_exc:
                logger.warning("quality_score in generator failed: %s", _qs_exc)
                data["_quality_score"] = None

            # ── Final safety-net: strip LLM-ism fillers from all questions ──
            # Quality reviewer strips these, but retries can regenerate them.
            try:
                from app.services.quality_reviewer import _strip_filler_phrases

                for _q in data.get("questions", []):
                    for _field in ("question_text", "text"):
                        _val = _q.get(_field, "")
                        if _val:
                            _cleaned = _strip_filler_phrases(_val)
                            if _cleaned != re.sub(r"\s{2,}", " ", _val).strip():
                                _q[_field] = _cleaned
            except Exception as _filler_exc:
                logger.debug("[filler_strip] Safety-net skipped: %s", _filler_exc)

            # ── Warning severity categorization ──
            data["_warning_severity"] = _categorize_warnings(all_warnings)
            data["_quality_tier"] = data["_warning_severity"].get("quality_tier", "high")

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
