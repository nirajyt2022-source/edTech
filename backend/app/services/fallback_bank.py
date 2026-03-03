"""
Fallback Bank — Deterministic replacement for _needs_regen questions.

Inserted between QualityReviewer and DifficultyCalibrator in the pipeline.
When QualityReviewer flags a question with _needs_regen=True (CHECKs 3, 7,
14, 16), this module replaces it with a pre-verified deterministic question
that requires zero LLM calls.

Design:
  - Max 2 replacements per worksheet (if >2, skip — let R08 block)
  - Fail-open: exceptions keep the original question
  - Preserves original id and display_number
  - Sets is_fallback=True for traceability
"""

from __future__ import annotations

import logging
import random
from typing import Optional

logger = logging.getLogger(__name__)

# Try importing GenerationContext; fall back to duck typing if unavailable
try:
    from app.services.topic_intelligence import GenerationContext
except Exception:
    GenerationContext = None  # type: ignore[assignment,misc]

MAX_REPLACEMENTS = 2

# ---------------------------------------------------------------------------
# Fallback question banks — keyed by (subject, grade)
# Each entry: {text, answer, format, explanation}
# ---------------------------------------------------------------------------

_MATHS_BANK: dict[int, list[dict]] = {
    1: [
        {"text": "What is 3 + 5?", "answer": "8", "format": "fill_blank", "explanation": "3 + 5 = 8"},
        {"text": "What is 6 + 2?", "answer": "8", "format": "fill_blank", "explanation": "6 + 2 = 8"},
        {"text": "What is 4 + 3?", "answer": "7", "format": "fill_blank", "explanation": "4 + 3 = 7"},
        {"text": "What is 7 + 1?", "answer": "8", "format": "fill_blank", "explanation": "7 + 1 = 8"},
        {"text": "What is 2 + 6?", "answer": "8", "format": "fill_blank", "explanation": "2 + 6 = 8"},
    ],
    2: [
        {"text": "What is 14 + 23?", "answer": "37", "format": "fill_blank", "explanation": "14 + 23 = 37"},
        {"text": "What is 31 + 18?", "answer": "49", "format": "fill_blank", "explanation": "31 + 18 = 49"},
        {"text": "What is 25 + 12?", "answer": "37", "format": "fill_blank", "explanation": "25 + 12 = 37"},
        {"text": "What is 42 + 15?", "answer": "57", "format": "fill_blank", "explanation": "42 + 15 = 57"},
        {"text": "What is 33 + 24?", "answer": "57", "format": "fill_blank", "explanation": "33 + 24 = 57"},
    ],
    3: [
        {"text": "What is 123 + 245?", "answer": "368", "format": "fill_blank", "explanation": "123 + 245 = 368"},
        {"text": "What is 256 + 132?", "answer": "388", "format": "fill_blank", "explanation": "256 + 132 = 388"},
        {"text": "What is 314 + 225?", "answer": "539", "format": "fill_blank", "explanation": "314 + 225 = 539"},
        {"text": "What is 421 + 156?", "answer": "577", "format": "fill_blank", "explanation": "421 + 156 = 577"},
        {"text": "What is 512 + 234?", "answer": "746", "format": "fill_blank", "explanation": "512 + 234 = 746"},
    ],
    4: [
        {"text": "What is 1234 + 2345?", "answer": "3579", "format": "fill_blank", "explanation": "1234 + 2345 = 3579"},
        {"text": "What is 3456 + 1234?", "answer": "4690", "format": "fill_blank", "explanation": "3456 + 1234 = 4690"},
        {"text": "What is 2143 + 3521?", "answer": "5664", "format": "fill_blank", "explanation": "2143 + 3521 = 5664"},
        {"text": "What is 4512 + 1236?", "answer": "5748", "format": "fill_blank", "explanation": "4512 + 1236 = 5748"},
        {"text": "What is 1357 + 2468?", "answer": "3825", "format": "fill_blank", "explanation": "1357 + 2468 = 3825"},
    ],
    5: [
        {
            "text": "What is 12345 + 23456?",
            "answer": "35801",
            "format": "fill_blank",
            "explanation": "12345 + 23456 = 35801",
        },
        {
            "text": "What is 34567 + 12345?",
            "answer": "46912",
            "format": "fill_blank",
            "explanation": "34567 + 12345 = 46912",
        },
        {
            "text": "What is 21436 + 13524?",
            "answer": "34960",
            "format": "fill_blank",
            "explanation": "21436 + 13524 = 34960",
        },
        {
            "text": "What is 45123 + 12346?",
            "answer": "57469",
            "format": "fill_blank",
            "explanation": "45123 + 12346 = 57469",
        },
        {
            "text": "What is 13579 + 24681?",
            "answer": "38260",
            "format": "fill_blank",
            "explanation": "13579 + 24681 = 38260",
        },
    ],
}

_ENGLISH_BANK: dict[int, list[dict]] = {
    1: [
        {
            "text": "Fill in the blank: The cat is _____ the table. (on / in)",
            "answer": "on",
            "format": "fill_blank",
            "explanation": "The cat sits on the table.",
        },
        {
            "text": "Fill in the blank: I _____ to school every day. (go / goes)",
            "answer": "go",
            "format": "fill_blank",
            "explanation": "'I' takes 'go' (first person).",
        },
        {
            "text": "What is the opposite of 'big'?",
            "answer": "small",
            "format": "short_answer",
            "explanation": "The opposite of big is small.",
        },
        {
            "text": "Fill in the blank: The sun is _____. (hot / cold)",
            "answer": "hot",
            "format": "fill_blank",
            "explanation": "The sun is hot.",
        },
        {
            "text": "What is the opposite of 'happy'?",
            "answer": "sad",
            "format": "short_answer",
            "explanation": "The opposite of happy is sad.",
        },
    ],
    2: [
        {
            "text": "Fill in the blank: She _____ a book yesterday. (read / reads)",
            "answer": "read",
            "format": "fill_blank",
            "explanation": "'Yesterday' indicates past tense → 'read'.",
        },
        {
            "text": "What is the opposite of 'fast'?",
            "answer": "slow",
            "format": "short_answer",
            "explanation": "The opposite of fast is slow.",
        },
        {
            "text": "Fill in the blank: The flowers are very _____. (beautiful / beauty)",
            "answer": "beautiful",
            "format": "fill_blank",
            "explanation": "An adjective is needed: 'beautiful'.",
        },
        {
            "text": "What is the plural of 'child'?",
            "answer": "children",
            "format": "short_answer",
            "explanation": "The plural of child is children.",
        },
        {
            "text": "Fill in the blank: We _____ playing in the park. (are / is)",
            "answer": "are",
            "format": "fill_blank",
            "explanation": "'We' takes 'are'.",
        },
    ],
    3: [
        {
            "text": "Fill in the blank: The dog _____ loudly at night. (barks / bark)",
            "answer": "barks",
            "format": "fill_blank",
            "explanation": "Singular subject 'dog' takes 'barks'.",
        },
        {
            "text": "What is the opposite of 'ancient'?",
            "answer": "modern",
            "format": "short_answer",
            "explanation": "The opposite of ancient is modern.",
        },
        {
            "text": "Fill in the blank: They have _____ to the market. (gone / went)",
            "answer": "gone",
            "format": "fill_blank",
            "explanation": "'Have' + past participle → 'gone'.",
        },
        {
            "text": "What is the past tense of 'write'?",
            "answer": "wrote",
            "format": "short_answer",
            "explanation": "The past tense of write is wrote.",
        },
        {
            "text": "Fill in the blank: The birds _____ south in winter. (fly / flies)",
            "answer": "fly",
            "format": "fill_blank",
            "explanation": "Plural subject 'birds' takes 'fly'.",
        },
    ],
    4: [
        {
            "text": "Fill in the blank: Neither the boys nor the girl _____ present. (was / were)",
            "answer": "was",
            "format": "fill_blank",
            "explanation": "With neither...nor, verb agrees with nearest subject 'girl' → 'was'.",
        },
        {
            "text": "What is the opposite of 'courageous'?",
            "answer": "cowardly",
            "format": "short_answer",
            "explanation": "The opposite of courageous is cowardly.",
        },
        {
            "text": "Fill in the blank: She _____ her homework before dinner. (finished / finishing)",
            "answer": "finished",
            "format": "fill_blank",
            "explanation": "Past tense needed: 'finished'.",
        },
        {
            "text": "What is the noun form of 'happy'?",
            "answer": "happiness",
            "format": "short_answer",
            "explanation": "The noun form of happy is happiness.",
        },
        {
            "text": "Fill in the blank: The children _____ excited about the trip. (were / was)",
            "answer": "were",
            "format": "fill_blank",
            "explanation": "Plural 'children' takes 'were'.",
        },
    ],
    5: [
        {
            "text": "Fill in the blank: If I _____ a bird, I would fly. (was / were)",
            "answer": "were",
            "format": "fill_blank",
            "explanation": "Subjunctive mood: 'If I were'.",
        },
        {
            "text": "What is the opposite of 'benevolent'?",
            "answer": "malevolent",
            "format": "short_answer",
            "explanation": "The opposite of benevolent is malevolent.",
        },
        {
            "text": "Fill in the blank: The team _____ its best performance. (gave / given)",
            "answer": "gave",
            "format": "fill_blank",
            "explanation": "Simple past: 'gave'.",
        },
        {
            "text": "What is the adjective form of 'beauty'?",
            "answer": "beautiful",
            "format": "short_answer",
            "explanation": "The adjective form of beauty is beautiful.",
        },
        {
            "text": "Fill in the blank: Each of the students _____ a book. (has / have)",
            "answer": "has",
            "format": "fill_blank",
            "explanation": "'Each' is singular → 'has'.",
        },
    ],
}

_HINDI_BANK: dict[int, list[dict]] = {
    1: [
        {
            "text": "'बिल्ली' का बहुवचन लिखिए।",
            "answer": "बिल्लियाँ",
            "format": "short_answer",
            "explanation": "बिल्ली → बिल्लियाँ (ई → इयाँ)",
        },
        {
            "text": "'लड़का' का बहुवचन लिखिए।",
            "answer": "लड़के",
            "format": "short_answer",
            "explanation": "लड़का → लड़के (आ → ए)",
        },
        {"text": "'पुस्तक' का बहुवचन लिखिए।", "answer": "पुस्तकें", "format": "short_answer", "explanation": "पुस्तक → पुस्तकें"},
        {"text": "'गाय' का बहुवचन लिखिए।", "answer": "गायें", "format": "short_answer", "explanation": "गाय → गायें"},
        {
            "text": "'चिड़िया' का बहुवचन लिखिए।",
            "answer": "चिड़ियाँ",
            "format": "short_answer",
            "explanation": "चिड़िया → चिड़ियाँ",
        },
    ],
    2: [
        {
            "text": "'फूल' का बहुवचन लिखिए।",
            "answer": "फूल",
            "format": "short_answer",
            "explanation": "फूल → फूल (no change)",
        },
        {
            "text": "रिक्त स्थान भरिए: मैं रोज़ स्कूल _____ हूँ। (जाता / जाती)",
            "answer": "जाता",
            "format": "fill_blank",
            "explanation": "Masculine default: जाता",
        },
        {
            "text": "'नदी' का बहुवचन लिखिए।",
            "answer": "नदियाँ",
            "format": "short_answer",
            "explanation": "नदी → नदियाँ (ई → इयाँ)",
        },
        {
            "text": "'पत्ता' का बहुवचन लिखिए।",
            "answer": "पत्ते",
            "format": "short_answer",
            "explanation": "पत्ता → पत्ते (आ → ए)",
        },
        {
            "text": "'कमरा' का बहुवचन लिखिए।",
            "answer": "कमरे",
            "format": "short_answer",
            "explanation": "कमरा → कमरे (आ → ए)",
        },
    ],
    3: [
        {
            "text": "रिक्त स्थान भरिए: बच्चे पार्क में _____ रहे हैं। (खेल / खेला)",
            "answer": "खेल",
            "format": "fill_blank",
            "explanation": "Present continuous: खेल रहे हैं",
        },
        {
            "text": "'कहानी' का बहुवचन लिखिए।",
            "answer": "कहानियाँ",
            "format": "short_answer",
            "explanation": "कहानी → कहानियाँ (ई → इयाँ)",
        },
        {
            "text": "'आदमी' का बहुवचन लिखिए।",
            "answer": "आदमी",
            "format": "short_answer",
            "explanation": "आदमी → आदमी (no change in ई-ending masculine)",
        },
        {
            "text": "'तारा' का बहुवचन लिखिए।",
            "answer": "तारे",
            "format": "short_answer",
            "explanation": "तारा → तारे (आ → ए)",
        },
        {
            "text": "रिक्त स्थान भरिए: उसने एक _____ पढ़ी। (किताब / किताबें)",
            "answer": "किताब",
            "format": "fill_blank",
            "explanation": "Singular: एक किताब",
        },
    ],
    4: [
        {
            "text": "'लड़की' का बहुवचन लिखिए।",
            "answer": "लड़कियाँ",
            "format": "short_answer",
            "explanation": "लड़की → लड़कियाँ (ई → इयाँ)",
        },
        {
            "text": "रिक्त स्थान भरिए: हमें प्रतिदिन व्यायाम _____ चाहिए। (करना / करने)",
            "answer": "करना",
            "format": "fill_blank",
            "explanation": "चाहिए + infinitive: करना चाहिए",
        },
        {
            "text": "'मछली' का बहुवचन लिखिए।",
            "answer": "मछलियाँ",
            "format": "short_answer",
            "explanation": "मछली → मछलियाँ (ई → इयाँ)",
        },
        {
            "text": "'रास्ता' का बहुवचन लिखिए।",
            "answer": "रास्ते",
            "format": "short_answer",
            "explanation": "रास्ता → रास्ते (आ → ए)",
        },
        {
            "text": "'बेटी' का बहुवचन लिखिए।",
            "answer": "बेटियाँ",
            "format": "short_answer",
            "explanation": "बेटी → बेटियाँ (ई → इयाँ)",
        },
    ],
    5: [
        {
            "text": "'स्त्री' का बहुवचन लिखिए।",
            "answer": "स्त्रियाँ",
            "format": "short_answer",
            "explanation": "स्त्री → स्त्रियाँ (ई → इयाँ)",
        },
        {
            "text": "रिक्त स्थान भरिए: यदि वर्षा होती तो फ़सल _____ होती। (अच्छी / अच्छा)",
            "answer": "अच्छी",
            "format": "fill_blank",
            "explanation": "फ़सल is feminine: अच्छी",
        },
        {"text": "'बात' का बहुवचन लिखिए।", "answer": "बातें", "format": "short_answer", "explanation": "बात → बातें"},
        {"text": "'सड़क' का बहुवचन लिखिए।", "answer": "सड़कें", "format": "short_answer", "explanation": "सड़क → सड़कें"},
        {"text": "'चादर' का बहुवचन लिखिए।", "answer": "चादरें", "format": "short_answer", "explanation": "चादर → चादरें"},
    ],
}

_SCIENCE_BANK: dict[int, list[dict]] = {
    1: [
        {
            "text": "Name one sense organ.",
            "answer": "eyes",
            "format": "short_answer",
            "explanation": "Eyes are a sense organ used for seeing.",
        },
        {
            "text": "What do plants need to grow?",
            "answer": "water and sunlight",
            "format": "short_answer",
            "explanation": "Plants need water and sunlight to grow.",
        },
        {
            "text": "Is the sun a star? (Yes / No)",
            "answer": "Yes",
            "format": "short_answer",
            "explanation": "The sun is the closest star to Earth.",
        },
        {
            "text": "Name one part of a plant.",
            "answer": "leaf",
            "format": "short_answer",
            "explanation": "Leaves are a part of a plant.",
        },
        {
            "text": "Which animal gives us milk?",
            "answer": "cow",
            "format": "short_answer",
            "explanation": "Cows give us milk.",
        },
    ],
    2: [
        {
            "text": "What is the main source of light on Earth?",
            "answer": "the sun",
            "format": "short_answer",
            "explanation": "The sun is our main source of light.",
        },
        {
            "text": "Name one animal that lives in water.",
            "answer": "fish",
            "format": "short_answer",
            "explanation": "Fish live in water.",
        },
        {
            "text": "What are baby plants called?",
            "answer": "seedlings",
            "format": "short_answer",
            "explanation": "Baby plants are called seedlings.",
        },
        {
            "text": "Name the three states of water.",
            "answer": "solid, liquid, gas",
            "format": "short_answer",
            "explanation": "Water exists as ice (solid), water (liquid), and steam (gas).",
        },
        {
            "text": "What do we breathe in?",
            "answer": "oxygen",
            "format": "short_answer",
            "explanation": "We breathe in oxygen from the air.",
        },
    ],
    3: [
        {
            "text": "What is the process by which plants make their food called?",
            "answer": "photosynthesis",
            "format": "short_answer",
            "explanation": "Plants make food through photosynthesis.",
        },
        {
            "text": "Name the gas that plants release during photosynthesis.",
            "answer": "oxygen",
            "format": "short_answer",
            "explanation": "Plants release oxygen during photosynthesis.",
        },
        {
            "text": "What type of simple machine is a see-saw?",
            "answer": "lever",
            "format": "short_answer",
            "explanation": "A see-saw is an example of a lever.",
        },
        {
            "text": "What is the hard outer covering of an egg called?",
            "answer": "shell",
            "format": "short_answer",
            "explanation": "The hard outer covering is called the shell.",
        },
        {
            "text": "Which planet is closest to the sun?",
            "answer": "Mercury",
            "format": "short_answer",
            "explanation": "Mercury is the closest planet to the sun.",
        },
    ],
    4: [
        {
            "text": "What is the largest organ of the human body?",
            "answer": "skin",
            "format": "short_answer",
            "explanation": "The skin is the largest organ.",
        },
        {
            "text": "What is the boiling point of water in degrees Celsius?",
            "answer": "100",
            "format": "short_answer",
            "explanation": "Water boils at 100°C.",
        },
        {
            "text": "Name the process of water turning into vapour.",
            "answer": "evaporation",
            "format": "short_answer",
            "explanation": "Evaporation is when water turns to vapour.",
        },
        {
            "text": "What type of teeth are used for cutting food?",
            "answer": "incisors",
            "format": "short_answer",
            "explanation": "Incisors are used for cutting food.",
        },
        {
            "text": "What force pulls objects towards the Earth?",
            "answer": "gravity",
            "format": "short_answer",
            "explanation": "Gravity pulls objects towards the Earth.",
        },
    ],
    5: [
        {
            "text": "What is the unit of force?",
            "answer": "Newton",
            "format": "short_answer",
            "explanation": "Force is measured in Newtons.",
        },
        {
            "text": "What is the chemical formula of water?",
            "answer": "H2O",
            "format": "short_answer",
            "explanation": "Water is H2O — two hydrogen and one oxygen atom.",
        },
        {
            "text": "Name the process by which plants lose water through leaves.",
            "answer": "transpiration",
            "format": "short_answer",
            "explanation": "Transpiration is water loss through leaf pores.",
        },
        {
            "text": "What is the speed of light approximately in km/s?",
            "answer": "300000",
            "format": "short_answer",
            "explanation": "Light travels at about 3 × 10^5 km/s.",
        },
        {
            "text": "Which vitamin is produced by sunlight on our skin?",
            "answer": "Vitamin D",
            "format": "short_answer",
            "explanation": "Sunlight helps our body produce Vitamin D.",
        },
    ],
}

# Map subject names → banks (handles aliases)
_SUBJECT_BANKS: dict[str, dict[int, list[dict]]] = {
    "maths": _MATHS_BANK,
    "mathematics": _MATHS_BANK,
    "english": _ENGLISH_BANK,
    "hindi": _HINDI_BANK,
    "science": _SCIENCE_BANK,
    "evs": _SCIENCE_BANK,
}


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def _get_bank(subject: str, grade: int) -> Optional[list[dict]]:
    """Return the fallback bank for a subject + grade, or None."""
    bank = _SUBJECT_BANKS.get(subject.lower())
    if bank is None:
        return None
    # Clamp grade to 1-5
    clamped = max(1, min(5, grade))
    return bank.get(clamped)


def _build_fallback(
    original: dict,
    entry: dict,
    context: object,
) -> dict:
    """Build a replacement question dict from a bank entry, preserving identity fields."""
    q = dict(original)  # shallow copy

    # Content from bank entry
    q["question_text"] = entry["text"]
    q["text"] = entry["text"]
    q["answer"] = entry["answer"]
    q["correct_answer"] = entry["answer"]
    q["explanation"] = entry.get("explanation", "")

    # Format: prefer original if valid, else use bank entry's
    q["format"] = entry.get("format", original.get("format", "fill_blank"))
    q["type"] = q["format"]

    # Clear regen flag, mark as fallback
    q["_needs_regen"] = False
    q["is_fallback"] = True
    q["verified"] = True

    # Clear fields that don't apply to fallback
    q.pop("options", None)
    q.pop("image_keywords", None)
    q["images"] = []
    q["pictorial_elements"] = []

    # Skill tag: keep original if valid, else use first valid from context
    valid_tags = getattr(context, "valid_skill_tags", []) if context else []
    orig_tag = original.get("skill_tag", "")
    if orig_tag and (not valid_tags or orig_tag in valid_tags):
        q["skill_tag"] = orig_tag
    elif valid_tags:
        q["skill_tag"] = valid_tags[0]

    # Difficulty: keep original if present, else "medium"
    if "difficulty" not in q or not q["difficulty"]:
        q["difficulty"] = "medium"

    return q


def replace_regen_questions(
    questions: list[dict],
    context: object,
) -> tuple[list[dict], list[str]]:
    """
    Scan questions for _needs_regen=True and replace up to MAX_REPLACEMENTS
    with deterministic fallback questions.

    Returns (mutated questions list, log messages).
    Fail-open: exceptions keep original questions unchanged.
    """
    logs: list[str] = []

    try:
        # Find flagged indices
        flagged = [i for i, q in enumerate(questions) if q.get("_needs_regen")]

        if not flagged:
            return questions, logs

        if len(flagged) > MAX_REPLACEMENTS:
            logs.append(
                f"[fallback_bank] {len(flagged)} questions flagged — "
                f"exceeds max {MAX_REPLACEMENTS}, skipping (let R08 handle)"
            )
            return questions, logs

        # Resolve subject + grade from context
        subject = getattr(context, "subject", "") if context else ""
        grade = getattr(context, "grade", 3) if context else 3

        bank = _get_bank(subject, grade)
        if not bank:
            logs.append(f"[fallback_bank] No bank for subject={subject!r} grade={grade}, keeping original questions")
            return questions, logs

        # Shuffle a copy so we don't repeat entries within one worksheet
        available = list(bank)
        random.shuffle(available)
        used_idx = 0

        for idx in flagged:
            if used_idx >= len(available):
                logs.append(
                    f"[fallback_bank] Exhausted bank entries, keeping Q{questions[idx].get('id', idx + 1)} as-is"
                )
                continue

            original = questions[idx]
            entry = available[used_idx]
            used_idx += 1

            replacement = _build_fallback(original, entry, context)
            questions[idx] = replacement

            q_id = original.get("id", idx + 1)
            logs.append(
                f"[fallback_bank] Replaced Q{q_id} (was _needs_regen) "
                f"with deterministic fallback: {entry['text'][:50]}..."
            )

        logger.info(
            "[fallback_bank] Replaced %d/%d flagged questions (subject=%s, grade=%d)",
            min(used_idx, len(flagged)),
            len(flagged),
            subject,
            grade,
        )

    except Exception as exc:
        logger.warning("[fallback_bank] Exception (fail-open): %s", exc)
        logs.append(f"[fallback_bank] Exception (fail-open): {exc}")

    return questions, logs
