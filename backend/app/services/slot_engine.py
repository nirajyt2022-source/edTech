"""
Slot-based worksheet generation engine v5.0 — Standout Factor

Backend controls structure; LLM fills content only.
Two-phase: meta generation → per-question generation with dedup + repair.

v5.0 additions:
- Variation banks (CONTEXT_BANK, ERROR_PATTERN_BANK, THINKING_STYLE_BANK)
- Deterministic seed-based rotation for diversity across worksheets
- Tightened slot definitions
- Backend-chosen context/error/style passed to prompts

Pipeline:
  1. generate_meta()       → micro_skill, common_mistakes, parent_tip, etc.
  2. get_slot_plan()       → deterministic slot sequence
  3. _pick_variations()    → seed-based bank selection
  4. generate_question()   → one LLM call per slot, validated inline
  5. validate_worksheet()  → distribution, uniqueness, diversity checks
"""

import hashlib
import json
import logging
import re
from collections import Counter
from datetime import date

logger = logging.getLogger("practicecraft.slot_engine")


# ════════════════════════════════════════════════════════════
# A) Deterministic Slot Plans — exact, no rounding drift
# ════════════════════════════════════════════════════════════

SLOT_PLANS: dict[int, dict[str, int]] = {
    5:  {"recognition": 1, "application": 1, "representation": 1, "error_detection": 1, "thinking": 1},
    10: {"recognition": 2, "application": 4, "representation": 2, "error_detection": 1, "thinking": 1},
    15: {"recognition": 3, "application": 6, "representation": 3, "error_detection": 2, "thinking": 1},
    20: {"recognition": 4, "application": 8, "representation": 4, "error_detection": 2, "thinking": 2},
}

SLOT_ORDER = ["recognition", "application", "representation", "error_detection", "thinking"]

VALID_FORMATS: dict[str, set[str]] = {
    "recognition":     {"column_setup", "place_value"},
    "application":     {"direct_compute", "word_problem"},
    "representation":  {"missing_number", "estimation", "place_value", "compare_solutions"},
    "error_detection": {"error_spot"},
    "thinking":        {"thinking"},
}

# Weights for proportional fallback (non-standard q_counts)
_DOCTRINE_WEIGHTS = {
    "recognition": 0.20, "application": 0.40, "representation": 0.20,
    "error_detection": 0.10, "thinking": 0.10,
}


# ════════════════════════════════════════════════════════════
# B) Variation Banks — backend-controlled, deterministic rotation
# ════════════════════════════════════════════════════════════

CONTEXT_BANK: list[dict[str, str]] = [
    {"item": "marbles", "scenario": "playing marbles in the park"},
    {"item": "stickers", "scenario": "collecting stickers at school"},
    {"item": "mangoes", "scenario": "buying mangoes at the market"},
    {"item": "books", "scenario": "reading books in the library"},
    {"item": "crayons", "scenario": "sharing crayons in art class"},
    {"item": "beads", "scenario": "making a bead necklace"},
    {"item": "stamps", "scenario": "collecting stamps from letters"},
    {"item": "coins", "scenario": "saving coins in a piggy bank"},
    {"item": "tickets", "scenario": "buying tickets for a school fair"},
    {"item": "flowers", "scenario": "planting flowers in the garden"},
    {"item": "biscuits", "scenario": "packing biscuits for a picnic"},
    {"item": "shells", "scenario": "picking shells at the beach"},
    {"item": "stars", "scenario": "earning stars for good work"},
    {"item": "apples", "scenario": "picking apples from the orchard"},
    {"item": "pencils", "scenario": "organising pencils in the classroom"},
    {"item": "balloons", "scenario": "decorating for a birthday party"},
    {"item": "pages", "scenario": "counting pages in notebooks"},
    {"item": "sweets", "scenario": "distributing sweets on a festival"},
]

ERROR_PATTERN_BANK: list[dict] = [
    {"a": 345, "b": 278, "wrong_sum": 513, "correct": 623, "pattern_tag": "forgot_carry_tens",
     "explanation": "The student forgot to carry 1 from the tens place."},
    {"a": 456, "b": 367, "wrong_sum": 713, "correct": 823, "pattern_tag": "forgot_carry_hundreds",
     "explanation": "The student forgot to carry 1 from the hundreds place."},
    {"a": 502, "b": 178, "wrong_sum": 334, "correct": 324, "pattern_tag": "borrow_across_zero",
     "explanation": "The student didn't borrow correctly across the zero in the tens place."},
    {"a": 600, "b": 247, "wrong_sum": 453, "correct": 353, "pattern_tag": "subtracted_smaller_from_larger",
     "explanation": "The student subtracted smaller digit from larger in each column instead of borrowing."},
    {"a": 289, "b": 145, "wrong_sum": 434, "correct": 434, "pattern_tag": "double_carry_missed",
     "explanation": "The student missed the carry from the ones to the tens."},
    {"a": 703, "b": 465, "wrong_sum": 348, "correct": 238, "pattern_tag": "borrow_chain_error",
     "explanation": "The student made an error borrowing through two consecutive places."},
    {"a": 415, "b": 268, "wrong_sum": 257, "correct": 147, "pattern_tag": "forgot_to_reduce_after_borrow",
     "explanation": "The student forgot to reduce the digit after borrowing."},
    {"a": 563, "b": 289, "wrong_sum": 742, "correct": 852, "pattern_tag": "tens_carry_dropped",
     "explanation": "The student forgot to carry 1 when adding the tens column."},
]

THINKING_STYLE_BANK: list[dict[str, str]] = [
    {"style": "estimate_nearest_100",
     "instruction": "Without calculating exactly, estimate the answer to the nearest hundred and explain your reasoning."},
    {"style": "closer_to",
     "instruction": "Without calculating, decide which of two given values the answer is closer to and explain why."},
    {"style": "threshold_check",
     "instruction": "Without calculating, decide whether the answer is above or below a given threshold and explain."},
    {"style": "compare_with_rounding",
     "instruction": "Round each number to the nearest hundred first, then compare with the actual calculation."},
    {"style": "bounds_reasoning",
     "instruction": "Find a lower bound and upper bound for the answer without calculating exactly."},
    {"style": "which_is_reasonable",
     "instruction": "Given three possible answers, pick the most reasonable one and explain why the others are wrong."},
]

NAME_BANKS: dict[str, list[str]] = {
    "India": ["Aarav", "Priya", "Rohan", "Ananya", "Meera", "Kabir", "Diya", "Arjun",
              "Ishaan", "Saanvi", "Vivaan", "Anika", "Advait", "Zara", "Reyansh", "Tara"],
    "UAE": ["Ahmed", "Fatima", "Omar", "Mariam", "Sara", "Yusuf", "Layla", "Ali",
            "Hassan", "Amira", "Khalid", "Noor", "Zain", "Hana", "Rayan", "Lina"],
}


def _make_seed(grade: str, topic: str, q_count: int) -> int:
    """Deterministic seed from (grade, topic, date, q_count). Changes daily."""
    key = f"{grade}|{topic}|{date.today().isoformat()}|{q_count}"
    return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)


def _pick_from_bank(bank: list, seed: int, index: int) -> dict:
    """Pick item from bank using seed + index for rotation."""
    pos = (seed + index) % len(bank)
    return bank[pos]


def _pick_name(region: str, seed: int, index: int) -> str:
    """Pick a name from the name bank, rotating to avoid repeats."""
    names = NAME_BANKS.get(region, NAME_BANKS["India"])
    pos = (seed + index) % len(names)
    return names[pos]


# ════════════════════════════════════════════════════════════
# C) Slot Plan Generation
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
    # Enforce mandatory minimums
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
    return worksheet_difficulty  # application, representation


# ════════════════════════════════════════════════════════════
# D) Slot Instructions — backend builds specific instructions per question
# ════════════════════════════════════════════════════════════

def _build_slot_instruction(
    slot_type: str,
    index: int,
    seed: int,
    region: str,
    slot_counter: dict[str, int],
) -> str:
    """Build backend-chosen specific instructions for a slot question.

    Returns a string injected into the prompt that tells the LLM
    exactly what context/error/style to use.
    """
    slot_idx = slot_counter.get(slot_type, 0)

    if slot_type == "application":
        ctx = _pick_from_bank(CONTEXT_BANK, seed, slot_idx)
        name = _pick_name(region, seed, index)
        return (
            f"format: direct_compute OR word_problem. "
            f"If word_problem, use this context: {name} is {ctx['scenario']}. "
            f"Item: {ctx['item']}. Exact numerical answer required."
        )

    if slot_type == "error_detection":
        err = _pick_from_bank(ERROR_PATTERN_BANK, seed, slot_idx)
        return (
            f"format: error_spot. "
            f"MUST present this SPECIFIC wrong answer for the student to find: "
            f"A student solved {err['a']} + {err['b']} (or {err['a']} - {err['b']}) "
            f"and got {err['wrong_sum']}. The correct answer is {err['correct']}. "
            f"Pattern: {err['pattern_tag']}. "
            f"Student must find the mistake and write the correct answer."
        )

    if slot_type == "thinking":
        style = _pick_from_bank(THINKING_STYLE_BANK, seed, slot_idx)
        return (
            f"format: thinking. "
            f"Style: {style['style']}. "
            f"{style['instruction']}"
        )

    if slot_type == "recognition":
        return (
            "format: column_setup OR place_value. "
            "Direct recall or single-step. Easy.\n"
            'Examples: "Write 502 - 178 in column form." / '
            '"What is the hundreds digit in 507?"'
        )

    if slot_type == "representation":
        return (
            "format: missing_number OR estimation OR place_value OR compare_solutions. "
            'NEVER "visualize" or "draw" or "use array/number line".\n'
            'Examples: "___ + 178 = 502" / '
            '"Estimate 478 + 256 to the nearest hundred." / '
            '"Show 345 as 3 hundreds + ___ tens + 5 ones."'
        )

    return ""


# ════════════════════════════════════════════════════════════
# E) Token-Efficient Prompts
# ════════════════════════════════════════════════════════════

META_SYSTEM = (
    "Expert primary-school curriculum designer. "
    "Output JSON only. No markdown. No extra keys."
)

META_USER_TEMPLATE = (
    'Grade {grade} {subject} | Topic: "{topic}" | Region: {region} | Difficulty: {difficulty}\n'
    "Generate worksheet metadata.\n"
    'micro_skill must be narrow and specific (NOT "addition" — instead '
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
    "- pictorial_elements must be empty list []."
)

QUESTION_USER_TEMPLATE = (
    "Grade {grade} {subject} | Micro-skill: {micro_skill} | "
    "Slot: {slot_type} | Difficulty: {difficulty}\n"
    "Avoid reusing: {avoid}\n"
    "{slot_instruction}\n"
    "{language_instruction}"
    '{{"format":"","question_text":"","pictorial_elements":[],"answer":""}}'
)

REGION_CONTEXT: dict[str, dict[str, str]] = {
    "India": {
        "currency": "rupees",
    },
    "UAE": {
        "currency": "AED",
    },
}


# ════════════════════════════════════════════════════════════
# F) Validators
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
    r"(explain|why|which.*(greater|more|better|easier|faster)"
    r"|compare|create|without calculating|estimate"
    r"|how do you know|in your own words|what would happen"
    r"|reasonable|closer to|above or below|round|bound|upper|lower)",
    re.IGNORECASE,
)

_BLANK_MARKER = re.compile(r"(_{2,}|\?{1,}|□|▢|\[ *\])")


def validate_question(q: dict, slot_type: str) -> list[str]:
    """Validate a single generated question against slot constraints."""
    issues: list[str] = []
    fmt = q.get("format", "")
    text = q.get("question_text", "")
    answer = q.get("answer")

    # 1. Format in allowed set
    allowed = VALID_FORMATS.get(slot_type, set())
    if fmt not in allowed:
        issues.append(
            f"format '{fmt}' not allowed for {slot_type}; "
            f"expected one of {sorted(allowed)}"
        )

    # 2. Forbidden visual phrases
    if _FORBIDDEN_VISUAL_PHRASES.search(text):
        issues.append("question_text references visuals/arrays/diagrams that aren't rendered")

    # 3. Answer present
    if answer is None or (isinstance(answer, str) and not answer.strip()):
        issues.append("answer is empty")

    # 4. Question text meaningful
    if not text or len(text.strip()) < 10:
        issues.append("question_text is too short or missing")

    # 5. Slot-specific checks
    if slot_type == "error_detection":
        if not _ERROR_LANGUAGE.search(text):
            issues.append(
                "error_detection must present a wrong answer for student to find/correct"
            )
        # Must include a wrong numerical answer
        nums_in_text = re.findall(r"\d{2,}", text)
        if len(nums_in_text) < 2:
            issues.append(
                "error_detection must include the wrong sum and the original numbers"
            )

    if slot_type == "representation" and fmt == "missing_number":
        if not _BLANK_MARKER.search(text):
            issues.append("missing_number format should contain a blank (___, ?, □)")

    if slot_type == "thinking":
        if not _REASONING_LANGUAGE.search(text):
            issues.append("thinking slot should involve reasoning, not pure computation")

    # 6. Pictorial elements empty (no renderer)
    if q.get("pictorial_elements"):
        issues.append("pictorial_elements must be empty (no renderer available)")

    return issues


def validate_worksheet_slots(questions: list[dict], q_count: int) -> list[str]:
    """Validate the full worksheet: slot distribution, uniqueness, diversity."""
    issues: list[str] = []
    plan = SLOT_PLANS.get(q_count) or _compute_proportional_plan(q_count)
    actual_counts = Counter(q.get("slot_type", "") for q in questions)

    # 1. Slot count must match plan
    for slot_type in SLOT_ORDER:
        expected = plan.get(slot_type, 0)
        actual = actual_counts.get(slot_type, 0)
        if actual != expected:
            issues.append(f"slot {slot_type}: expected {expected}, got {actual}")

    # 2. Mandatory minimums
    if actual_counts.get("error_detection", 0) < 1:
        issues.append("missing mandatory error_detection question")
    if actual_counts.get("thinking", 0) < 1:
        issues.append("missing mandatory thinking question")

    # 3. Duplicate number pairs
    number_pairs: list[str] = []
    for i, q in enumerate(questions):
        text = q.get("question_text", "")
        nums = re.findall(r"\d{2,}", text)
        if len(nums) >= 2:
            pair = f"{nums[0]}-{nums[1]}"
            if pair in number_pairs:
                issues.append(f"q{i+1}: duplicate number pair {pair}")
            number_pairs.append(pair)

    # 4. Forbidden phrases across all questions
    for i, q in enumerate(questions):
        text = q.get("question_text", "")
        if _FORBIDDEN_VISUAL_PHRASES.search(text):
            issues.append(f"q{i+1}: references visuals that aren't rendered")

    # 5. Context repetition check (application questions)
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


def validate_hard_difficulty_carry(questions: list[dict], difficulty: str) -> list[str]:
    """For hard difficulty, at least one application question should involve carry in both ones and tens."""
    if difficulty.lower() != "hard":
        return []
    issues: list[str] = []
    app_qs = [q for q in questions if q.get("slot_type") == "application"]
    if not app_qs:
        return issues
    # Check if any application question has numbers that require carries
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
# G) Generation Pipeline
# ════════════════════════════════════════════════════════════

def _clean_json(content: str) -> str:
    """Strip markdown fences."""
    content = content.strip()
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    return content.strip()


def generate_meta(
    client, grade: str, subject: str, topic: str, difficulty: str, region: str,
) -> dict:
    """Generate worksheet metadata via LLM. Returns meta dict."""
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

    # Ensure required fields
    for key in ("micro_skill", "skill_focus", "learning_objective",
                "parent_tip", "teaching_script"):
        meta.setdefault(key, "")
    meta.setdefault("common_mistakes", [])

    # Override difficulty with user's explicit choice
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
) -> dict:
    """Generate a single question via LLM. Returns question dict."""
    region_ctx = REGION_CONTEXT.get(region, REGION_CONTEXT["India"])
    avoid_str = ", ".join(avoid_state[-20:]) if avoid_state else "none"

    lang_instruction = ""
    if language != "English":
        lang_instruction = f"Write question_text in {language}.\n"

    user_msg = QUESTION_USER_TEMPLATE.format(
        grade=grade,
        subject=subject,
        micro_skill=micro_skill,
        slot_type=slot_type,
        difficulty=difficulty,
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

    # Ensure required fields
    q.setdefault("format", "")
    q.setdefault("question_text", "")
    q.setdefault("pictorial_elements", [])
    q.setdefault("answer", "")

    # Force pictorial_elements empty (no renderer)
    q["pictorial_elements"] = []

    return q


def _extract_avoid_items(q: dict) -> list[str]:
    """Extract items to add to avoid_state from a generated question."""
    items: list[str] = []
    text = q.get("question_text", "")

    # Extract number pairs
    nums = re.findall(r"\d{2,}", text)
    if len(nums) >= 2:
        items.append(f"{nums[0]}-{nums[1]}")

    # Extract context nouns from CONTEXT_BANK
    text_lower = text.lower()
    for ctx in CONTEXT_BANK:
        if ctx["item"] in text_lower:
            items.append(ctx["item"])

    # Extract format to avoid repeating same structure consecutively
    fmt = q.get("format", "")
    if fmt:
        items.append(f"format:{fmt}")

    return items


def run_slot_pipeline(
    client,
    grade: str,
    subject: str,
    topic: str,
    q_count: int,
    difficulty: str,
    region: str,
    language: str = "English",
) -> tuple[dict, list[dict]]:
    """Full slot-based generation pipeline.

    Returns (meta, questions) where each question dict has:
    id, slot_type, format, question_text, pictorial_elements, answer, difficulty
    """
    logger.info(
        "Slot pipeline v5: grade=%s topic=%s q=%d diff=%s",
        grade, topic, q_count, difficulty,
    )

    # 1. Generate meta
    meta = generate_meta(client, grade, subject, topic, difficulty, region)
    micro_skill = meta.get("micro_skill", topic)
    logger.info("Meta: micro_skill=%s", micro_skill)

    # Difficulty sanity check — auto-bump if easy is inappropriate
    diff_issues = validate_difficulty_sanity(micro_skill, difficulty)
    if diff_issues and difficulty.lower() == "easy":
        logger.warning("Bumping difficulty easy->medium: %s", diff_issues)
        difficulty = "medium"
        meta["difficulty"] = "Medium"

    # 2. Get slot plan
    slot_plan = get_slot_plan(q_count)
    logger.info("Slot plan (%d): %s", len(slot_plan), dict(Counter(slot_plan)))

    # 3. Create deterministic seed for variation banks
    seed = _make_seed(grade, topic, q_count)
    logger.info("Variation seed: %d", seed)

    # 4. Generate each question with bank-driven instructions
    questions: list[dict] = []
    avoid_state: list[str] = []
    max_attempts = 3
    slot_counter: dict[str, int] = {}  # tracks per-slot index for bank rotation

    for i, slot_type in enumerate(slot_plan):
        q_difficulty = get_question_difficulty(slot_type, difficulty)

        # Build slot-specific instruction from banks
        slot_instruction = _build_slot_instruction(
            slot_type, i, seed, region, slot_counter,
        )

        generated = False
        for attempt in range(max_attempts):
            try:
                q = generate_question(
                    client, grade, subject, micro_skill,
                    slot_type, q_difficulty, avoid_state, region, language,
                    slot_instruction=slot_instruction,
                )

                issues = validate_question(q, slot_type)

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

                # Accept question
                q["id"] = i + 1
                q["slot_type"] = slot_type
                q["difficulty"] = q_difficulty
                questions.append(q)

                # Update avoid state
                avoid_state.extend(_extract_avoid_items(q))
                generated = True

                # Increment slot counter for bank rotation
                slot_counter[slot_type] = slot_counter.get(slot_type, 0) + 1

                break

            except (json.JSONDecodeError, Exception) as exc:
                logger.error("Q%d/%d attempt %d error: %s", i + 1, len(slot_plan), attempt + 1, exc)

        if not generated:
            # Insert placeholder on total failure
            questions.append({
                "id": i + 1,
                "slot_type": slot_type,
                "format": sorted(VALID_FORMATS[slot_type])[0],
                "question_text": f"[Generation failed for {slot_type} question]",
                "pictorial_elements": [],
                "answer": "",
                "difficulty": q_difficulty,
            })
            slot_counter[slot_type] = slot_counter.get(slot_type, 0) + 1

        logger.info(
            "Q%d/%d: %s / %s",
            i + 1, len(slot_plan), slot_type, questions[-1].get("format", "?"),
        )

    # 5. Validate whole worksheet
    ws_issues = validate_worksheet_slots(questions, q_count)
    if ws_issues:
        logger.warning("Worksheet-level issues: %s", ws_issues)

    carry_issues = validate_hard_difficulty_carry(questions, difficulty)
    if carry_issues:
        logger.warning("Hard-difficulty carry issues: %s", carry_issues)

    # Attach context to meta
    meta["grade"] = grade
    meta["subject"] = subject
    meta["topic"] = topic

    logger.info("Slot pipeline complete: %d questions", len(questions))
    return meta, questions
