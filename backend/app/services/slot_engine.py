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
    "recognition":     {"column_setup", "place_value"},
    "application":     {"word_problem"},
    "representation":  {"missing_number", "estimation", "place_value"},
    "error_detection": {"error_spot"},
    "thinking":        {"thinking"},
}

_DOCTRINE_WEIGHTS = {
    "recognition": 0.20, "application": 0.40, "representation": 0.20,
    "error_detection": 0.10, "thinking": 0.10,
}


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


# ════════════════════════════════════════════════════════════
# F) Slot Instructions (backend builds per-question instructions)
# ════════════════════════════════════════════════════════════

def _build_slot_instruction(
    slot_type: str,
    chosen_variant: dict | None,
) -> str:
    """Build backend-chosen specific instructions for a slot question.

    chosen_variant contains the picked context/error/style for this slot.
    """
    if slot_type == "recognition":
        return (
            "format: column_setup OR place_value. "
            "Direct recall or single-step. Easy.\n"
            'Examples: "Write 345 + 278 in column form." / '
            '"What is the hundreds digit in 507?"'
        )

    if slot_type == "application":
        if not chosen_variant:
            return "format: word_problem. Use a real-world scenario. Exact numerical answer required."
        name = chosen_variant.get("name", "Aarav")
        ctx = chosen_variant.get("context", {})
        return (
            f"format: word_problem. "
            f"MUST use this context: {name} is {ctx.get('scenario', 'at school')}. "
            f"Item: {ctx.get('item', 'things')}. "
            f"Numbers must require carrying. Exact numerical answer required."
        )

    if slot_type == "representation":
        return (
            "format: missing_number OR estimation OR place_value. "
            'NEVER "visualize" or "draw" or "use array/number line".\n'
            'Examples: "___ + 178 = 502" / '
            '"Estimate 478 + 256 to the nearest hundred." / '
            '"Show 345 as 3 hundreds + ___ tens + 5 ones."'
        )

    if slot_type == "error_detection":
        if not chosen_variant:
            return "format: error_spot. Show a wrong addition answer for the student to correct."
        err = chosen_variant.get("error", {})
        return (
            f"format: error_spot. "
            f"MUST use EXACTLY these numbers: "
            f"A student added {err['a']} + {err['b']} and got {err['wrong']}. "
            f"The correct answer is {err['correct']}. "
            f"The student's mistake: {err['hint']}. "
            f"Write a question asking the student to find the mistake and give the correct answer."
        )

    if slot_type == "thinking":
        if not chosen_variant:
            return "format: thinking. Reasoning question, not pure computation."
        style = chosen_variant.get("style", {})
        return (
            f"format: thinking. "
            f"Style: {style['style']}. "
            f"{style['instruction']} "
            f"Use 3-digit numbers that require carrying."
        )

    return ""


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
        nums_in_text = re.findall(r"\d{2,}", text)
        if len(nums_in_text) < 2:
            issues.append("error_detection must include the wrong sum and the original numbers")

    if slot_type == "representation" and fmt == "missing_number":
        if not _BLANK_MARKER.search(text):
            issues.append("missing_number format should contain a blank (___, ?, [])")

    if slot_type == "thinking":
        if not _REASONING_LANGUAGE.search(text):
            issues.append("thinking slot should involve reasoning, not pure computation")

    if q.get("pictorial_elements"):
        issues.append("pictorial_elements must be empty (no renderer available)")

    return issues


# ════════════════════════════════════════════════════════════
# H-bis) Visual Hydration & Verification
# ════════════════════════════════════════════════════════════

_HYDRATE_COLUMN = re.compile(r"column", re.IGNORECASE)
_HYDRATE_ESTIMATION = re.compile(r"closer\s+to|estimat", re.IGNORECASE)
_HYDRATE_NUMS = re.compile(r"\b(\d{3,4})\b")

# Extended hydration patterns for visuals_only mode
_HYDRATE_ADDITION = re.compile(r"\+|add|sum|total", re.IGNORECASE)
_HYDRATE_WORD_PROBLEM = re.compile(r"more|in total|together|altogether|combined|finds?\b", re.IGNORECASE)
_HYDRATE_MISSING = re.compile(r"_{2,}|\?{1,}|□")
_HYDRATE_ROUNDING = re.compile(r"round.*nearest|nearest\s+\d+|estimate.*nearest", re.IGNORECASE)
_HYDRATE_NUMS_2TO4 = re.compile(r"\b(\d{2,4})\b")


def hydrate_visuals(questions: list[dict], visuals_only: bool = False) -> list[dict]:
    """Deterministic visual hydration: infer representation + visual_spec + visual_model_ref.

    Rules (in priority order):
      A) Two 2-4 digit integers + addition keywords → BASE_TEN_REGROUPING
         (broadened from column-only; rewrites text when visuals_only)
      B) Two integers + word-problem keywords → BASE_TEN_REGROUPING
      C) Blank marker + missing-number pattern → NUMBER_LINE
      D) "round" + "nearest" → NUMBER_LINE
      E) 'closer to' / 'estimate' with 2 reference hundreds → NUMBER_LINE (existing)
      Fallback: TEXT_ONLY, or deterministic column-form when visuals_only.
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
        nums = [int(n) for n in _HYDRATE_NUMS.findall(text)]
        three_digit = [n for n in nums if 100 <= n <= 999]

        # ── Standard rules (always active) ──

        # Rule A (original): column setup + addition with two 3-digit numbers
        fmt = q.get("format") or q.get("skill_tag") or ""
        is_column = bool(_HYDRATE_COLUMN.search(text)) or fmt == "column_setup"
        is_addition = "+" in text or "add" in text_lower

        if is_column and is_addition and len(three_digit) >= 2:
            q["representation"] = "PICTORIAL_MODEL"
            q["visual_spec"] = {
                "model_id": "BASE_TEN_REGROUPING",
                "numbers": [three_digit[0], three_digit[1]],
                "operation": "addition",
            }
            q["visual_model_ref"] = "BASE_TEN_REGROUPING"
            continue

        # Rule B (original): estimation / closer-to with reference hundreds
        if _HYDRATE_ESTIMATION.search(text):
            ref_hundreds = sorted(set(n for n in nums if n % 100 == 0))
            non_round = [n for n in three_digit if n % 100 != 0]

            if len(ref_hundreds) >= 2:
                lower_ref = ref_hundreds[0]
                upper_ref = ref_hundreds[-1]

                markers = [lower_ref]
                if len(non_round) >= 2:
                    markers.append(non_round[0] + non_round[1])
                markers.append(upper_ref)

                q["representation"] = "PICTORIAL_MODEL"
                q["visual_spec"] = {
                    "model_id": "NUMBER_LINE",
                    "start": lower_ref - 100,
                    "end": upper_ref + 100,
                    "tick_interval": 50,
                    "markers": markers,
                }
                q["visual_model_ref"] = "NUMBER_LINE"
                continue

        # ── Extended rules (visuals_only mode only) ──
        if visuals_only:
            nums_2to4 = [int(n) for n in _HYDRATE_NUMS_2TO4.findall(text) if 10 <= int(n) <= 9999]

            # Rule C: two 2-4 digit integers + addition keywords → BASE_TEN_REGROUPING
            has_addition = bool(_HYDRATE_ADDITION.search(text))
            if has_addition and len(nums_2to4) >= 2:
                a, b = nums_2to4[0], nums_2to4[1]
                q["question_text"] = f"Write {a} + {b} in column form."
                q["answer"] = str(a + b)
                q["representation"] = "PICTORIAL_MODEL"
                q["visual_spec"] = {
                    "model_id": "BASE_TEN_REGROUPING",
                    "numbers": [a, b],
                    "operation": "addition",
                }
                q["visual_model_ref"] = "BASE_TEN_REGROUPING"
                continue

            # Rule D: word-problem keywords + two integers → BASE_TEN_REGROUPING
            if _HYDRATE_WORD_PROBLEM.search(text) and len(nums_2to4) >= 2:
                a, b = nums_2to4[0], nums_2to4[1]
                q["question_text"] = f"Write {a} + {b} in column form."
                q["answer"] = str(a + b)
                q["representation"] = "PICTORIAL_MODEL"
                q["visual_spec"] = {
                    "model_id": "BASE_TEN_REGROUPING",
                    "numbers": [a, b],
                    "operation": "addition",
                }
                q["visual_model_ref"] = "BASE_TEN_REGROUPING"
                continue

            # Rule E: missing number (blank marker + two known values) → NUMBER_LINE
            if _HYDRATE_MISSING.search(text) and len(nums_2to4) >= 2:
                vals = sorted(nums_2to4)
                min_val, max_val = vals[0], vals[-1]
                missing = max_val - min_val if max_val > min_val else min_val
                q["representation"] = "PICTORIAL_MODEL"
                q["visual_spec"] = {
                    "model_id": "NUMBER_LINE",
                    "start": max(0, min_val - 100),
                    "end": max_val + 100,
                    "tick_interval": 50,
                    "markers": [min_val, missing, max_val],
                }
                q["visual_model_ref"] = "NUMBER_LINE"
                continue

            # Rule F: rounding ("round" + "nearest") → NUMBER_LINE
            if _HYDRATE_ROUNDING.search(text) and nums_2to4:
                target = nums_2to4[0]
                base_match = re.search(r"nearest\s+(\d+)", text_lower)
                rounding_base = int(base_match.group(1)) if base_match else 100
                rounded_down = (target // rounding_base) * rounding_base
                rounded_up = rounded_down + rounding_base
                q["representation"] = "PICTORIAL_MODEL"
                q["visual_spec"] = {
                    "model_id": "NUMBER_LINE",
                    "start": max(0, rounded_down - rounding_base),
                    "end": rounded_up + rounding_base,
                    "tick_interval": max(1, rounding_base // 2),
                    "markers": [rounded_down, target, rounded_up],
                }
                q["visual_model_ref"] = "NUMBER_LINE"
                continue

            # Fallback (visuals_only): deterministic column-form from CARRY_PAIRS
            pair = CARRY_PAIRS[q_index % len(CARRY_PAIRS)]
            a, b = pair
            q["question_text"] = f"Write {a} + {b} in column form."
            q["answer"] = str(a + b)
            q["representation"] = "PICTORIAL_MODEL"
            q["visual_spec"] = {
                "model_id": "BASE_TEN_REGROUPING",
                "numbers": [a, b],
                "operation": "addition",
            }
            q["visual_model_ref"] = "BASE_TEN_REGROUPING"
            continue

        # Default: text-only (standard mode, no match)
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


def validate_worksheet_slots(questions: list[dict], q_count: int) -> list[str]:
    """Validate the full worksheet: slot distribution, uniqueness, diversity."""
    issues: list[str] = []
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

    number_pairs: list[str] = []
    for i, q in enumerate(questions):
        text = q.get("question_text", "")
        nums = re.findall(r"\d{2,}", text)
        if len(nums) >= 2:
            pair = f"{nums[0]}-{nums[1]}"
            if pair in number_pairs:
                issues.append(f"q{i+1}: duplicate number pair {pair}")
            number_pairs.append(pair)

    for i, q in enumerate(questions):
        text = q.get("question_text", "")
        if _FORBIDDEN_VISUAL_PHRASES.search(text):
            issues.append(f"q{i+1}: references visuals that aren't rendered")

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


def validate_hard_difficulty_carry(questions: list[dict], difficulty: str) -> list[str]:
    """For hard difficulty, at least one application question should involve carry in both ones and tens."""
    if difficulty.lower() != "hard":
        return []
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
) -> dict:
    """Generate a single question via LLM."""
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

    q.setdefault("format", "")
    q.setdefault("question_text", "")
    q.setdefault("pictorial_elements", [])
    q.setdefault("answer", "")
    q["pictorial_elements"] = []

    return q


def _extract_avoid_items(q: dict) -> list[str]:
    """Extract items to add to avoid_state from a generated question."""
    items: list[str] = []
    text = q.get("question_text", "")

    nums = re.findall(r"\d{2,}", text)
    if len(nums) >= 2:
        items.append(f"{nums[0]}+{nums[1]}")

    text_lower = text.lower()
    for ctx in CONTEXT_BANK:
        if ctx["item"] in text_lower:
            items.append(ctx["item"])

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
    """Full slot-based generation pipeline with controlled variation.

    Returns (meta, questions) where each question dict has:
    id, slot_type, format, question_text, pictorial_elements, answer, difficulty
    """
    logger.info(
        "Slot pipeline v6: grade=%s topic=%s q=%d diff=%s",
        grade, topic, q_count, difficulty,
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

    # 2. Get slot plan
    slot_plan = get_slot_plan(q_count)
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

    for slot_type in slot_plan:
        if slot_type == "application":
            # Avoid both cross-worksheet and within-worksheet repeats
            avoid_ctx = history_avoid["used_contexts"] + used_contexts_this_ws
            ctx = pick_context(rng, avoid_ctx)
            name = pick_name(rng, region)
            used_contexts_this_ws.append(ctx["item"])
            chosen_variants.append({"context": ctx, "name": name})

        elif slot_type == "error_detection":
            avoid_err = history_avoid["used_error_ids"] + used_error_ids_this_ws
            err = pick_error(rng, avoid_err)
            used_error_ids_this_ws.append(err["id"])
            chosen_variants.append({"error": err})

        elif slot_type == "thinking":
            avoid_styles = history_avoid["used_thinking_styles"] + used_thinking_styles_this_ws
            style = pick_thinking_style(rng, avoid_styles)
            used_thinking_styles_this_ws.append(style["style"])
            chosen_variants.append({"style": style})

        else:
            chosen_variants.append(None)

    # 6. Generate each question with variant-driven instructions
    questions: list[dict] = []
    avoid_state: list[str] = []
    max_attempts = 3

    for i, slot_type in enumerate(slot_plan):
        q_difficulty = get_question_difficulty(slot_type, difficulty)
        variant = chosen_variants[i]
        slot_instruction = _build_slot_instruction(slot_type, variant)

        generated = False
        for attempt in range(max_attempts):
            try:
                q = generate_question(
                    client, grade, subject, micro_skill,
                    slot_type, q_difficulty, avoid_state, region, language,
                    slot_instruction=slot_instruction,
                )

                issues = validate_question(q, slot_type)

                # Extra check: error_detection must use backend-provided numbers
                if slot_type == "error_detection" and variant:
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

                q["id"] = i + 1
                q["slot_type"] = slot_type
                q["difficulty"] = q_difficulty
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
    )

    # 8. Validate whole worksheet
    ws_issues = validate_worksheet_slots(questions, q_count)
    if ws_issues:
        logger.warning("Worksheet-level issues: %s", ws_issues)

    carry_issues = validate_hard_difficulty_carry(questions, difficulty)
    if carry_issues:
        logger.warning("Hard-difficulty carry issues: %s", carry_issues)

    # 8b. Hydrate visuals (deterministic, no LLM)
    questions = hydrate_visuals(questions)
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

    logger.info("Slot pipeline complete: %d questions", len(questions))
    return meta, questions


def _repair_pass(
    client, grade, subject, micro_skill, difficulty, region, language,
    questions, slot_plan, rng, history_avoid,
    used_contexts, used_error_ids, used_thinking_styles,
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
                    )
                    new_q["id"] = i + 1
                    new_q["slot_type"] = "thinking"
                    new_q["difficulty"] = q_diff
                    questions[i] = new_q
                    used_thinking_styles.append(new_style["style"])
                except Exception as exc:
                    logger.error("Repair failed for Q%d: %s", i + 1, exc)

    return questions
