"""Visual Strategy Selector — enriches every question with the best visual strategy.

Rules engine (no LLM call) that decides emoji, card_color, question_style
per question based on subject, topic, question type, and visual_type.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# ── Emoji rotation pools per subject ──────────────────────────────────────

MATHS_EMOJI = ["🍎", "🍊", "🍌", "🫐", "🍇", "🥭", "🌟", "⭐", "💎", "🔵"]

HINDI_TOPIC_EMOJI: dict[str, str] = {
    "swar": "🔤",
    "vyanjan": "🔤",
    "varnamala": "🔤",
    "matra": "📝",
    "shabd": "✏️",
    "vakya": "📖",
    "comprehension": "📚",
    "poem": "🎵",
    "kavita": "🎵",
    "kahani": "📖",
    "story": "📖",
    "letter": "✉️",
    "patra": "✉️",
    "anuched": "📝",
    "nibandh": "📝",
}

ENGLISH_TOPIC_EMOJI: dict[str, str] = {
    "noun": "📦",
    "verb": "🏃",
    "adjective": "🌈",
    "pronoun": "👤",
    "preposition": "📍",
    "conjunction": "🔗",
    "tense": "⏰",
    "article": "📄",
    "sentence": "✏️",
    "punctuation": "❗",
    "vocabulary": "📚",
    "spelling": "🔤",
    "comprehension": "📖",
    "creative": "🎨",
    "writing": "✍️",
    "grammar": "📝",
    "alphabet": "🔠",
    "phonics": "🗣️",
    "rhyming": "🎵",
}

EVS_EMOJI: dict[str, list[str]] = {
    "animal": ["🐶", "🐱", "🐦", "🐟", "🦁", "🐘", "🐒", "🦋", "🐢", "🐍"],
    "plant": ["🌱", "🌳", "🌻", "🌿", "🍀", "🌾", "🌺", "🪴", "🌹", "🌼"],
    "season": ["🌞", "☀️", "🌧️", "⛈️", "❄️", "☃️", "🍂", "🌊"],
    "food": ["🍎", "🥕", "🍌", "🥛", "🍳", "🥦", "🍞", "🥜", "🧀", "🍗"],
    "body": ["👁️", "👃", "👂", "✋", "🦵", "🧠", "💪", "🦷"],
    "water": ["💧", "🌊", "🚰", "🏊", "☁️", "🌧️"],
    "transport": ["🚗", "🚌", "🚲", "🛺", "🚂", "✈️", "🚢", "🏍️"],
    "festival": ["🪔", "🎆", "🎨", "🏮", "🎋"],
    "family": ["👨‍👩‍👧‍👦", "👴", "👵", "👶", "🏠"],
    "clothes": ["👕", "👗", "🧥", "🧣", "👒"],
    "school": ["📚", "✏️", "🎒", "🏫", "📐", "🖍️"],
    "hygiene": ["🧼", "🪥", "🚿", "🧴", "🫧"],
    "air": ["💨", "🌬️", "🎈", "🪁"],
    "light": ["💡", "🔦", "🕯️", "☀️"],
    "shelter": ["🏠", "🏡", "🏢", "⛺"],
    "soil": ["🪨", "🌍", "🏔️"],
    "energy": ["⚡", "🔋", "☀️", "💡"],
}

SCIENCE_EMOJI = EVS_EMOJI  # Science shares EVS emoji pools

GK_EMOJI: dict[str, list[str]] = {
    "india": ["🇮🇳", "🏛️", "🕌", "🗺️"],
    "monument": ["🏛️", "🕌", "🗼"],
    "national": ["🇮🇳", "🦚", "🐅", "🪷"],
    "solar": ["☀️", "🌙", "🌍", "🪐", "⭐"],
    "continent": ["🌍", "🗺️"],
    "festival": ["🪔", "🎆", "🎨", "🏮"],
    "sport": ["🏏", "⚽", "🏸", "🏑"],
    "musical": ["🎵", "🥁", "🎶"],
    "famous": ["👤", "🏛️"],
    "currency": ["💰", "🪙"],
    "flag": ["🏳️", "🇮🇳"],
}

COMPUTER_EMOJI = ["💻", "🖥️", "⌨️", "🖱️", "📱", "🖨️", "💾", "📡"]
HEALTH_EMOJI = ["🏃‍♂️", "🧘‍♀️", "🤸‍♂️", "🫀", "🦷", "🥗", "💪", "🏊"]
MORAL_EMOJI = ["🤝", "❤️", "🌟", "🙏", "📖", "🕊️", "🌈", "👫"]


# ── Question style inference ──────────────────────────────────────────────


def _infer_question_style(q: dict, subject: str, topic: str) -> str:
    """Infer the rendering style for a question."""
    q_type = q.get("type", "short_answer")
    topic_lower = topic.lower()

    # MCQ → mcq_grid
    if q_type == "mcq":
        return "mcq_grid"

    # True/False
    if q_type == "true_false":
        return "true_false"

    # Hindi tracing
    if subject.lower() == "hindi" and any(kw in topic_lower for kw in ("varnamala", "swar", "vyanjan", "alphabet")):
        role = q.get("role", "")
        if role == "recognition" or q.get("difficulty") == "easy":
            return "tracing"

    # Fill blank
    if q_type == "fill_blank":
        return "fill_blank"

    # Match columns (visual_type-based)
    if q.get("visual_type") == "match_columns":
        return "match_columns"

    # Word problem detection
    text = q.get("text", "").lower()
    if any(kw in text for kw in ("how many", "kitne", "total", "remaining", "left", "bought", "sold")):
        return "word_problem"

    # Default: writing lines for long answers, short_answer otherwise
    if len(q.get("correct_answer", "")) > 50:
        return "writing_lines"

    return "fill_blank" if q_type == "fill_blank" else "word_problem" if "?" in q.get("text", "") else "fill_blank"


# ── Emoji assignment ──────────────────────────────────────────────────────


def _get_topic_emoji_pool(subject: str, topic: str) -> list[str]:
    """Get the best emoji pool for a subject+topic combination."""
    subject_lower = subject.lower()
    topic_lower = topic.lower()

    if subject_lower in ("maths", "math", "mathematics"):
        return MATHS_EMOJI

    if subject_lower == "hindi":
        for kw, emoji in HINDI_TOPIC_EMOJI.items():
            if kw in topic_lower:
                return [emoji]
        return ["📝"]

    if subject_lower == "english":
        for kw, emoji in ENGLISH_TOPIC_EMOJI.items():
            if kw in topic_lower:
                return [emoji]
        return ["📚"]

    if subject_lower in ("evs", "environmental studies"):
        return _match_evs_pool(topic_lower)

    if subject_lower == "science":
        return _match_evs_pool(topic_lower)  # shares pool

    if subject_lower in ("gk", "general knowledge"):
        for kw, pool in GK_EMOJI.items():
            if kw in topic_lower:
                return pool
        return ["🌍", "🏛️", "📚"]

    if subject_lower in ("computer", "computer science"):
        return COMPUTER_EMOJI

    if subject_lower in ("health", "health & pe", "health and physical education"):
        return HEALTH_EMOJI

    if subject_lower in ("moral science", "moral education", "value education"):
        return MORAL_EMOJI

    # Fallback
    return ["📝", "✏️", "📖"]


def _match_evs_pool(topic_lower: str) -> list[str]:
    """Match EVS/Science topic to emoji pool."""
    for kw, pool in EVS_EMOJI.items():
        if kw in topic_lower:
            return pool
    # Broader keyword matching
    if any(w in topic_lower for w in ("pet", "wild", "domestic", "bird", "insect", "fish")):
        return EVS_EMOJI["animal"]
    if any(w in topic_lower for w in ("tree", "flower", "leaf", "seed", "garden")):
        return EVS_EMOJI["plant"]
    if any(w in topic_lower for w in ("rain", "summer", "winter", "spring", "weather")):
        return EVS_EMOJI["season"]
    if any(w in topic_lower for w in ("eat", "fruit", "vegetable", "nutrition", "diet")):
        return EVS_EMOJI["food"]
    if any(w in topic_lower for w in ("hand", "eye", "ear", "nose", "organ", "sense")):
        return EVS_EMOJI["body"]
    if any(w in topic_lower for w in ("river", "pond", "ocean", "rain", "drink")):
        return EVS_EMOJI["water"]
    if any(w in topic_lower for w in ("car", "bus", "train", "vehicle", "road")):
        return EVS_EMOJI["transport"]
    if any(w in topic_lower for w in ("diwali", "holi", "eid", "christmas", "celebrate")):
        return EVS_EMOJI["festival"]
    if any(w in topic_lower for w in ("mother", "father", "sister", "brother", "home")):
        return EVS_EMOJI["family"]
    if any(w in topic_lower for w in ("clean", "wash", "bath", "teeth", "germ")):
        return EVS_EMOJI["hygiene"]
    return ["🌿", "🌍", "📚"]


def _generate_emoji_visual_for_maths(q: dict, emoji_pool: list[str], q_index: int) -> str | None:
    """Generate emoji visual string for maths questions."""
    visual_type = q.get("visual_type")
    visual_data = q.get("visual_data") or {}

    # object_group: build from groups data
    if visual_type == "object_group" and visual_data.get("groups"):
        groups = visual_data["groups"]
        op = visual_data.get("operation", "+")
        parts = []
        for g in groups:
            count = g.get("count", 0)
            e = g.get("emoji") or emoji_pool[q_index % len(emoji_pool)]
            parts.append(e * min(count, 15))  # cap at 15 for display
        op_char = "➕" if op == "+" else "➖" if op == "-" else "✖️" if op in ("*", "×") else "➗"
        return f"  {op_char}  ".join(parts) + "  🟰  ❓"

    # No visual_type but has numbers → generate from numbers
    numbers = q.get("numbers") or {}
    if numbers and not visual_type:
        a = numbers.get("a")
        b = numbers.get("b")
        if a is not None and b is not None and a <= 15 and b <= 15:
            e = emoji_pool[q_index % len(emoji_pool)]
            return f"{e * a}  ➕  {e * b}  🟰  ❓"

    return None


# ── Main entry point ──────────────────────────────────────────────────────


def enrich_visuals(worksheet: dict) -> dict:
    """Enrich every question in the worksheet with the best visual strategy.

    For each question, decides:
    - emoji_visual: str | None — emoji string to display
    - emoji_label: str | None — label below the emoji
    - visual_type: str | None — SVG component type (kept if valid, else cleared)
    - visual_data: dict | None — data for SVG component
    - card_color: int — 1-10, rotates per question for pastel variety
    - question_style: str — rendering hint for the template

    Returns the worksheet dict with enriched questions.
    """
    subject = worksheet.get("subject", "")
    topic = worksheet.get("topic", "")
    questions = worksheet.get("questions", [])

    emoji_pool = _get_topic_emoji_pool(subject, topic)

    # Valid SVG visual types that the template can render
    valid_svg_types = {
        "clock",
        "number_line",
        "pie_fraction",
        "shapes",
        "base_ten_regrouping",
        "object_group",
        "money_coins",
        "pattern_tiles",
        "ten_frame",
        "abacus",
        "grid_symmetry",
        "bar_chart",
        "pictograph",
        "array_visual",
        "fraction_bar",
        "percentage_bar",
        "match_columns",
    }

    # Group questions by tier for card_color rotation
    tiers = {"foundation": [], "application": [], "stretch": []}
    for i, q in enumerate(questions):
        role = q.get("role", "recognition")
        if role in ("recognition", "representation"):
            tiers["foundation"].append(i)
        elif role == "application":
            tiers["application"].append(i)
        else:  # error_detection, thinking
            tiers["stretch"].append(i)

    # Assign card colors: each tier restarts from its offset
    card_colors: dict[int, int] = {}
    color_counter = 1
    for tier_name in ("foundation", "application", "stretch"):
        for idx in tiers[tier_name]:
            card_colors[idx] = ((color_counter - 1) % 10) + 1
            color_counter += 1

    is_maths = subject.lower() in ("maths", "math", "mathematics")
    is_hindi = subject.lower() == "hindi"

    for i, q in enumerate(questions):
        # 1. Card color
        q["card_color"] = card_colors.get(i, (i % 10) + 1)

        # 2. Question style
        q["question_style"] = _infer_question_style(q, subject, topic)

        # 3. Visual type validation
        vt = q.get("visual_type")
        if vt and vt not in valid_svg_types:
            q["visual_type"] = None
            q["visual_data"] = None

        # 4. Emoji visual — Priority: Gemini per-question > visual_data > topic pool > none
        if q.get("emoji") and q["emoji"] != "null":
            # Priority 1: Gemini chose a per-question emoji
            q["emoji_visual"] = q["emoji"]
            q["emoji_label"] = None
        elif is_maths:
            emoji_vis = _generate_emoji_visual_for_maths(q, emoji_pool, i)
            if emoji_vis:
                q["emoji_visual"] = emoji_vis
                vd = q.get("visual_data") or {}
                q["emoji_label"] = vd.get("object_name", "")
            elif not q.get("visual_type"):
                # Non-visual maths question — add subject emoji
                q["emoji_visual"] = emoji_pool[i % len(emoji_pool)]
                q["emoji_label"] = None
        else:
            # Non-maths fallback: assign topic-relevant emoji
            if not q.get("emoji_visual"):
                q["emoji_visual"] = emoji_pool[i % len(emoji_pool)]
                q["emoji_label"] = None

        # Hindi Varnamala: enhance tracing style (overrides emoji for tracing)
        if is_hindi and q.get("question_style") == "tracing":
            text = q.get("text", "")
            devanagari_chars = re.findall(r"[\u0900-\u097F]", text)
            if devanagari_chars:
                q["emoji_visual"] = devanagari_chars[0]
                q["emoji_label"] = f"({text[:30]})" if len(text) > 2 else None

    logger.info(
        "[visual_strategy] Enriched %d questions for %s / %s",
        len(questions),
        subject,
        topic,
    )

    return worksheet


# ── Self-test ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Visual Strategy — Self Tests")
    print("=" * 60)

    # Test 1: Maths Addition with object_group
    ws1 = {
        "subject": "Maths",
        "topic": "Addition up to 20",
        "questions": [
            {
                "id": "q1",
                "type": "mcq",
                "role": "recognition",
                "text": "Count and add.",
                "difficulty": "easy",
                "visual_type": "object_group",
                "visual_data": {
                    "groups": [{"count": 5, "emoji": "🍎"}, {"count": 3, "emoji": "🍎"}],
                    "operation": "+",
                    "object_name": "apple",
                    "object_emoji": "🍎",
                },
                "correct_answer": "8",
                "hint": "Count both groups",
            },
            {
                "id": "q2",
                "type": "fill_blank",
                "role": "application",
                "text": "7 + ___ = 12",
                "difficulty": "medium",
                "visual_type": None,
                "visual_data": None,
                "correct_answer": "5",
                "hint": "Think backwards",
            },
        ],
    }
    result = enrich_visuals(ws1)
    q1, q2 = result["questions"]
    assert q1.get("emoji_visual"), "Q1 should have emoji_visual"
    assert "🍎" in q1["emoji_visual"], "Q1 emoji should contain apples"
    assert q1["question_style"] == "mcq_grid", f"Q1 style should be mcq_grid, got {q1['question_style']}"
    assert q1["card_color"] >= 1, "Q1 should have card_color"
    assert q2["question_style"] == "fill_blank", f"Q2 style should be fill_blank, got {q2['question_style']}"
    print("✓ Test 1: Maths Addition — PASS")

    # Test 2: Hindi Varnamala
    ws2 = {
        "subject": "Hindi",
        "topic": "Varnamala — Swar",
        "questions": [
            {
                "id": "q1",
                "type": "short_answer",
                "role": "recognition",
                "text": "इस अक्षर को पहचानो: अ",
                "difficulty": "easy",
                "visual_type": None,
                "visual_data": None,
                "correct_answer": "अ",
                "hint": "अनार का अ",
            },
        ],
    }
    result2 = enrich_visuals(ws2)
    hq1 = result2["questions"][0]
    assert hq1["question_style"] == "tracing", f"Hindi Q1 should be tracing, got {hq1['question_style']}"
    assert hq1.get("emoji_visual"), "Hindi Q1 should have emoji_visual"
    print("✓ Test 2: Hindi Varnamala — PASS")

    # Test 3: EVS Animals
    ws3 = {
        "subject": "EVS",
        "topic": "Animals around us",
        "questions": [
            {
                "id": "q1",
                "type": "mcq",
                "role": "recognition",
                "text": "Which animal gives us milk?",
                "difficulty": "easy",
                "visual_type": None,
                "visual_data": None,
                "correct_answer": "Cow",
                "options": ["Cow", "Dog", "Cat", "Fish"],
                "hint": "Think of the farm",
            },
        ],
    }
    result3 = enrich_visuals(ws3)
    eq1 = result3["questions"][0]
    assert eq1.get("emoji_visual"), "EVS Q1 should have emoji_visual"
    assert eq1["question_style"] == "mcq_grid", f"EVS Q1 should be mcq_grid, got {eq1['question_style']}"
    print("✓ Test 3: EVS Animals — PASS")

    # Test 4: English Grammar
    ws4 = {
        "subject": "English",
        "topic": "Nouns",
        "questions": [
            {
                "id": "q1",
                "type": "fill_blank",
                "role": "application",
                "text": "The ___ is playing in the park.",
                "difficulty": "medium",
                "visual_type": None,
                "visual_data": None,
                "correct_answer": "boy",
                "hint": "Think of a person",
            },
        ],
    }
    result4 = enrich_visuals(ws4)
    en_q1 = result4["questions"][0]
    assert en_q1.get("emoji_visual"), "English Q1 should have emoji_visual"
    assert en_q1["question_style"] == "fill_blank"
    print("✓ Test 4: English Grammar — PASS")

    # Test 5: Edge case — unknown subject, no visual
    ws5 = {
        "subject": "Art",
        "topic": "Drawing",
        "questions": [
            {
                "id": "q1",
                "type": "short_answer",
                "role": "application",
                "text": "Draw a house.",
                "difficulty": "easy",
                "visual_type": "INVALID_TYPE",
                "visual_data": {"foo": "bar"},
                "correct_answer": "A house drawing",
            },
        ],
    }
    result5 = enrich_visuals(ws5)
    art_q1 = result5["questions"][0]
    assert art_q1["visual_type"] is None, "Invalid visual_type should be cleared"
    assert art_q1["visual_data"] is None, "Invalid visual_data should be cleared"
    assert art_q1.get("emoji_visual"), "Should still get fallback emoji"
    assert art_q1["card_color"] >= 1, "Should have card_color"
    print("✓ Test 5: Edge case — PASS")

    print()
    print("=" * 60)
    print("ALL 5 TESTS PASSED")
    print("=" * 60)
