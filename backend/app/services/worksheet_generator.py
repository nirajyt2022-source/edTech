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
import logging
import math
import random
import re
import string
import time
from typing import Any

from app.data.image_registry import get_available_keywords

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 1A  System Prompt — universal, works for all topics
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an expert CBSE school teacher creating worksheets for Indian primary school students.

RULES:
1. Generate questions ONLY about the given topic. If the topic is "Telling Time", every question must be about time — never about addition, subtraction, or any other topic.
2. All questions must be age-appropriate for the given class level.
3. Follow NCERT/CBSE curriculum standards for the given class and subject.
4. Every question must have a correct answer. For maths, compute the answer precisely.
5. Never repeat the same question pattern. Vary the question formats.
6. Use Indian context (₹ for money, Indian names, Indian festivals, Indian cities, etc.)
7. VARIETY IS CRITICAL: Every worksheet you generate must be DIFFERENT from the last one.
   - Use different question angles and phrasings each time
   - Rotate through different real-world scenarios (home, school, market, park, farm, zoo, kitchen, playground, festival, hospital, train station)
   - For the same topic, explore different subtopics and aspects each time
   - Avoid formulaic patterns like always starting with "Which of these..."
   - Mix up question styles: direct questions, scenario-based, riddles, compare-contrast, classify, odd-one-out, complete-the-pattern, true/false statements, fill-in-the-blanks with context
   - Use varied sentence structures: "Name...", "How many...", "What happens when...", "Which one does NOT...", "Arrange in order...", "Complete the sentence..."

VARIETY ANCHORS BY SUBJECT:
- EVS: Rotate through different animals, plants, seasons, family scenarios, festivals, food items each generation
- Science: Use different experiments, phenomena, body parts, materials each time
- Maths: Change numbers, contexts (shopping, cooking, travel, sports), and units each time
- English: Use different example sentences, vocabulary themes, and passage topics
- GK: Cover different landmarks, symbols, facts, personalities each time
- Hindi: Vary the words, poems, story themes, and sentence contexts

DIFFICULTY LEVELS:
- Easy: Single-step, direct recall, recognition. Example for Class 3 Maths Time: "What time does this clock show?" (with a described clock face)
- Medium: Two-step, application, requires some reasoning. Example: "School starts at 8:30 AM. If Priya takes 45 minutes to get ready, what time should she wake up?"
- Hard: Multi-step, word problems, error detection, reasoning. Example: "Rahul says 90 minutes is the same as 1 hour 20 minutes. Is he correct? Explain why."

QUESTION ROLES — assign a "role" to EVERY question:

Distribute questions across three tiers:
- "recognition" or "representation" → Foundation tier (★) — recall, identify, basic understanding
- "application" → Application tier (★★) — use knowledge to solve, apply in context
- "error_detection" or "thinking" → Stretch tier (★★★) — reason, find mistakes, explain why

DISTRIBUTION RULES based on selected difficulty:
- Easy: 60% foundation, 30% application, 10% stretch
- Medium: 30% foundation, 50% application, 20% stretch
- Hard: 10% foundation, 30% application, 60% stretch

Group questions in this order in your output: all foundation first, then application, then stretch.
Each question MUST have a "role" field.

QUESTION TYPES — you MUST use this distribution for every worksheet:
- mcq: Multiple choice with 4 options → AT LEAST 30% of questions (e.g., 3 out of 10)
- fill_blank: Fill in the blank → AT LEAST 20% of questions (e.g., 2 out of 10)
- true_false: True or False → AT LEAST 1 question per worksheet
- short_answer / word_problem / error_detection: Remaining questions

EXAMPLE for 10 questions: 3 mcq + 2 fill_blank + 1 true_false + 2 short_answer + 1 word_problem + 1 error_detection

CRITICAL RULES FOR QUESTION TYPES:
- EVERY mcq question MUST have an "options" array with EXACTLY 4 strings. This is NON-NEGOTIABLE.
  Example: "options": ["Dog", "Cat", "Fish", "Lion"]
  If you cannot think of 4 options, change the question type to short_answer instead.
- For "true_false" type: You MUST include "options": ["True", "False"]. Never set options to null.
- For "fill_blank" type: The question text MUST contain a blank indicated by "______" or "_________".
- For "short_answer" and "word_problem" type: Set "options" to null.
- For "error_detection" type: Present a statement with a mistake. Set "options" to null.

Every question MUST have a "hint" field. The hint should:
- Guide the student toward the answer WITHOUT revealing it
- Be age-appropriate and encouraging
- Never contain the answer itself

IMPORTANT: Even within a single difficulty level, create a GRADIENT:
- If user selects "Easy": make ~60% warm-up, ~30% at easy level, ~10% slightly harder
- If user selects "Medium": make ~30% slightly easier (warm-up), ~50% at medium level, ~20% slightly harder (stretch)
- If user selects "Hard": make ~10% warm-up, ~30% at hard level, ~60% challenging
- This gradient naturally maps to the Foundation/Application/Stretch tiers
- Foundation questions should be the easiest, Stretch should be the hardest

VISUAL TYPES — use ONLY these exact type names and data structures:

1. "clock" — analog clock face
   visual_data: { "hour": <1-12>, "minute": <0-59> }
   Use for: Time topics. Example: Show 3:30 → {"hour": 3, "minute": 30}

2. "object_group" — groups of countable objects (fruits, birds, stars, coins, etc.)
   visual_data: { "groups": [{"count": <number>, "label": "<object name>"}], "operation": "+"|"-" }
   Use for: Addition, subtraction, counting. Example: 4 mangoes + 3 mangoes → {"groups": [{"count": 4, "label": "mangoes"}, {"count": 3, "label": "mangoes"}], "operation": "+"}
   Supported labels for icons: mango/apple/orange/banana/fruit, bird/parrot/sparrow, star/sticker, coin/rupee, marble/ball/bead, balloon, candy/sweet/toffee/chocolate, flower/rose, pencil/pen/crayon, book/notebook

3. "shapes" — geometric shape with optional side measurements
   visual_data: { "shape": "triangle"|"rectangle"|"square"|"circle", "sides": [<numbers>] }
   Use for: Geometry topics. Example: triangle with sides 3,4,5 → {"shape": "triangle", "sides": [3, 4, 5]}

4. "number_line" — number line with tick marks and optional highlight
   visual_data: { "start": <number>, "end": <number>, "step": <number>, "highlight": <number or null> }
   Use for: Number sense, counting, skip counting. Example: 0 to 20 by 2s highlighting 14 → {"start": 0, "end": 20, "step": 2, "highlight": 14}

5. "base_ten_regrouping" — column addition/subtraction with H/T/O columns
   visual_data: { "numbers": [<first_number>, <second_number>], "operation": "addition"|"subtraction" }
   Use for: Multi-digit arithmetic ONLY. Example: 345 + 278 → {"numbers": [345, 278], "operation": "addition"}

6. "pie_fraction" — circular pie chart showing a fraction
   visual_data: { "numerator": <number>, "denominator": <number> }
   Use for: Fractions. Example: 3/4 → {"numerator": 3, "denominator": 4}

7. "grid_symmetry" — dot grid with filled cells and a fold line
   visual_data: { "grid_size": <number>, "filled_cells": [[row,col], ...], "fold_axis": "vertical"|"horizontal" }
   Use for: Symmetry topics.

8. "money_coins" — Indian coins and notes
   visual_data: { "coins": [{"value": <number>, "count": <number>}, ...] }
   Use for: Money topics. Values ≤10 render as coins, >10 as notes. Example: 3 five-rupee coins and 1 ten-rupee note → {"coins": [{"value": 5, "count": 3}, {"value": 10, "count": 1}]}

9. "pattern_tiles" — sequence of tiles with one blank
   visual_data: { "tiles": ["A", "B", "A", "B", "A", "?"], "blank_position": 5 }
   Use for: Pattern recognition topics.

10. "abacus" — 3-rod abacus (hundreds, tens, ones)
    visual_data: { "hundreds": <0-9>, "tens": <0-9>, "ones": <0-9> }
    Use for: Place value topics.

CRITICAL RULES FOR VISUALS:
- Use ONLY the 10 visual types listed above. Any other type name will NOT render.
- The visual_data structure must EXACTLY match what's shown above — no extra or missing fields.
- For "standard" problem_style: set visual_type to null and visual_data to null for ALL questions.
- For "visual" problem_style: EVERY question MUST have a visual_type and visual_data.
- For "mixed" problem_style: approximately half the questions should have visuals.
- NEVER write "look at the image", "look at the picture", "see the animal below", "the animal shown below", or ANY phrase that implies a visual is embedded in the question. Images are shown as supplementary context — the question text must be fully self-contained and answerable even without the image.
  BAD: "Look at the image. Which of these animals is a wild animal?"
  GOOD: "Which of these animals is a wild animal? (a) Hen (b) Lion (c) Cat (d) Dog"
  BAD: "The animal shown below gives us milk."
  GOOD: "Which farm animal gives us milk?"
- You CAN still use image_keywords to show a relevant cartoon alongside the question. But the question text must make sense on its own.
- Do NOT use visual_type "clock_face" — use "clock". Do NOT use "fraction_bar" — use "pie_fraction". Do NOT use "bar_chart" or "tally_chart" — these are NOT supported.
- Match the visual to the topic: clock for Time, shapes for Geometry, object_group for counting/arithmetic, money_coins for Money, etc.

VISUAL RELEVANCE RULE: The visual must directly help answer the question.
- Do NOT show a money_coins visual for a shapes question
- Do NOT show an object_group visual if the question doesn't involve counting objects
- If no visual genuinely helps the question, set visual_type and visual_data to null
- It's better to have no visual than a misleading one

IMAGES: You can attach cartoon images to questions using "image_keywords".
Only use keywords from this list: {available_image_keywords}

IMAGE USAGE BY SUBJECT:
- EVS: animals, plants, habitats, food, weather, family, transport, objects
- Science: body, science, space, animals, plants
- GK: landmarks, symbols, geography, space, festivals, sports, instruments
- Computer: computer
- Health: health, sports, food
- Moral Science: family, festivals (minimal images needed)
- Maths: Use SVG visual_type (clock, shapes, etc.) — NOT image_keywords
- English: Minimal images — mostly text-based subject
- Hindi: Minimal images — mostly text-based subject

RULES FOR IMAGES:
- Only use keywords from the available list. Unknown keywords will be silently ignored.
- Use ONLY 1 image_keyword per question. Pick the MOST relevant one.
  BAD: "image_keywords": ["hen", "duck", "egg"] — too many, wastes space
  GOOD: "image_keywords": ["hen"] — one clear image for an egg-laying question
- Exception: Use 2 keywords only when the question is ABOUT comparing two things.
  Example: "How is a bird different from a fish?" → ["parrot", "fish"] (comparison)
- Use images when they ADD value: identifying animals, showing objects, visual context.
- For EVS/Science subjects with "visual" or "mixed" problem_style: use images on at least 60% of questions.
- For Maths: prefer SVG visual_type (clock, shapes, etc.) over image_keywords.
- image_keywords and visual_type can coexist on the same question.

OUTPUT FORMAT — respond with ONLY this JSON, no other text:
{
  "title": "Worksheet: {topic}",
  "skill_focus": "<one-line summary of the skill being tested>",
  "common_mistake": "<one common mistake students make on this topic>",
  "parent_tip": "<one tip for parents to help their child with this topic>",
  "learning_objectives": ["<objective 1>", "<objective 2>", "<objective 3>"],
  "questions": [
    {
      "id": "q1",
      "type": "<mcq|fill_blank|true_false|short_answer|word_problem|error_detection>",
      "role": "<recognition|representation|application|error_detection|thinking>",
      "text": "<question text>",
      "options": ["<option A>", "<option B>", "<option C>", "<option D>"] or null,
      "correct_answer": "<the correct answer — MUST be accurate>",
      "explanation": "<brief explanation of how to solve it>",
      "difficulty": "<easy|medium|hard>",
      "hint": "<a helpful hint that does NOT reveal the answer>",
      "image_keywords": ["<keyword1>", "<keyword2>"] or null,
      "visual_type": "<type or null>",
      "visual_data": null
    }
  ]
}
"""

# Inject dynamic keyword list from registry
SYSTEM_PROMPT = SYSTEM_PROMPT.replace(
    "{available_image_keywords}",
    ", ".join(get_available_keywords()),
)

# ---------------------------------------------------------------------------
# 1B  User Prompt Builder
# ---------------------------------------------------------------------------


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
        "standard": "standard (text-based, minimize visuals)",
    }.get(problem_style, "standard")

    # Random seed to force variety across generations
    seed = ''.join(random.choices(string.ascii_lowercase, k=6))

    # Random Indian names to use in word problems (different each time)
    all_names = [
        "Aarav", "Ananya", "Vihaan", "Diya", "Reyansh", "Saanvi", "Arjun", "Isha",
        "Kabir", "Myra", "Aditya", "Kiara", "Rohan", "Priya", "Vivaan", "Anika",
        "Krishna", "Zara", "Rudra", "Pari", "Atharv", "Navya", "Shaurya", "Aadhya",
        "Dhruv", "Riya", "Arnav", "Sara", "Dev", "Anvi", "Ishan", "Tara",
        "Kian", "Meera", "Yash", "Nisha", "Aryan", "Siya", "Neil", "Pooja",
        "Rahul", "Sneha", "Manav", "Kavya", "Sameer", "Tanvi", "Kunal", "Ritika",
    ]
    names_for_this_worksheet = random.sample(all_names, min(6, len(all_names)))
    names_str = ", ".join(names_for_this_worksheet)

    prompt = (
        f"Board: {board}\n"
        f"Class: {grade_level}\n"
        f"Subject: {subject}\n"
        f"Topic: {topic}\n"
        f"Difficulty: {difficulty}\n"
        f"Number of questions: {num_questions}\n"
        f"Language: {language}\n"
        f"Problem style: {style_hint}\n"
        f"Variation seed: {seed}\n\n"
        f"Generate a FRESH and CREATIVE worksheet following the system instructions. "
        f'Every single question must be strictly about "{topic}" and nothing else.\n\n'
        f"IMPORTANT — UNIQUENESS RULES:\n"
        f"- Create ORIGINAL questions you have NOT generated before. Be creative.\n"
        f"- Use different SCENARIOS for word problems each time (market, school, park, zoo, kitchen, garden, playground, train station, bus stop, festival, birthday party, sports day).\n"
        f"- Use these Indian names in your questions: {names_str}\n"
        f"- For Maths: vary the NUMBERS each time. Don't always use the same examples.\n"
        f"- For EVS/Science: ask about DIFFERENT animals, plants, or phenomena each time.\n"
        f"- For MCQs: vary the DISTRACTORS (wrong options). Don't always use the same set.\n"
        f"- Each worksheet should feel completely new and different from any previous one.\n"
    )

    # Problem-style specific image instructions
    if problem_style == "standard":
        prompt += (
            "\nIMPORTANT: Do NOT use image_keywords for any question. "
            "Set image_keywords to null for ALL questions. "
            "Standard mode means text-only worksheets with no cartoon images.\n"
        )
    elif problem_style == "visual":
        prompt += (
            "\nIMPORTANT: EVERY question MUST have at least one image_keyword "
            "from the provided list.\n"
        )

    if custom_instructions:
        prompt += f"\nAdditional teacher instructions: {custom_instructions}"

    return prompt


# ---------------------------------------------------------------------------
# 1C  Gemini Caller
# ---------------------------------------------------------------------------


def call_gemini(client, system_prompt: str, user_prompt: str, subject: str = "") -> str:
    """Call the LLM via the existing adapter and return raw text."""
    # Lower temperature for Maths to maintain accuracy, higher for creative subjects
    temp = 0.5 if subject.lower() in ("maths", "math", "mathematics") else 0.8
    response = client.chat.completions.create(
        model="gemini-2.5-flash",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temp,
        max_tokens=4096,
    )
    return response.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# 1D  Validator
# ---------------------------------------------------------------------------

# Broad topic keywords — NOT 198 profiles, just ~20 categories
_TOPIC_KEYWORDS: dict[str, list[str]] = {
    "time": ["time", "clock", "hour", "minute", "o'clock", "half past", "quarter", "am", "pm", "calendar", "month", "day", "week"],
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
    "science": ["plant", "animal", "body", "water", "air", "food", "weather", "environment", "habitat", "material", "force", "energy"],
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
        text[:60], answer, computed_str,
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
    "clock", "object_group", "shapes", "number_line",
    "base_ten_regrouping", "pie_fraction", "grid_symmetry",
    "money_coins", "pattern_tiles", "abacus",
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
        if keywords:
            images = resolve_keywords(keywords)
            if images:
                q["images"] = images  # [{path, alt, category}, ...]
            # If question says "look at the picture" but no valid images, rewrite text
            text = q.get("text", "")
            if not images and any(phrase in text.lower() for phrase in _PICTURE_PHRASES):
                for phrase in ["Look at the picture below. ", "See the image below. ",
                               "Look at the picture. ", "See the image. "]:
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
        warnings.append(
            f"Requested {num_questions} questions, got {len(questions)}"
        )

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
        off_topic_count = sum(
            1 for q in questions
            if not _is_question_on_topic(q.get("text", ""), topic_cat)
        )
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

    max_attempts = 2
    last_error: Exception | None = None
    all_warnings: list[str] = []

    for attempt in range(1, max_attempts + 1):
        t0 = time.perf_counter()
        try:
            raw = call_gemini(client, SYSTEM_PROMPT, user_prompt, subject=subject)
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
                len(data.get("questions", [])), elapsed_ms, attempt,
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

    raise ValueError(
        f"Worksheet generation failed after {max_attempts} attempts. "
        f"Last error: {last_error}"
    )
