"""
Slot-based worksheet generation engine v4.0

Backend controls structure; LLM fills content only.
Two-phase: meta generation → per-question generation with dedup + repair.

Pipeline:
  1. generate_meta()       → micro_skill, common_mistakes, parent_tip, etc.
  2. get_slot_plan()       → deterministic slot sequence
  3. generate_question()   → one LLM call per slot, validated inline
  4. validate_worksheet()  → distribution, uniqueness, forbidden phrases
"""

import json
import logging
import re
from collections import Counter

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
    "recognition":    {"column_setup", "place_value", "simple_identify"},
    "application":    {"direct_compute", "word_problem"},
    "representation": {"missing_number", "estimation", "place_value", "compare_solutions"},
    "error_detection": {"error_spot", "compare_solutions"},
    "thinking":       {"estimation", "compare_solutions", "create_example"},
}

# Weights for proportional fallback (non-standard q_counts)
_DOCTRINE_WEIGHTS = {
    "recognition": 0.20, "application": 0.40, "representation": 0.20,
    "error_detection": 0.10, "thinking": 0.10,
}


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
    """Return ordered list of slot_types for q_count questions.

    Supported: 5, 10, 15, 20 (exact plans). Other counts use proportional
    fallback with mandatory error_detection + thinking.
    Output follows cognitive progression: recognition → … → thinking.
    """
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
# D) Token-Efficient Prompts (embedded constants)
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
    'JSON: {{"micro_skill":"","skill_focus":"","learning_objective":"",'
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

SLOT_RULES: dict[str, str] = {
    "recognition": (
        "format: column_setup OR place_value OR simple_identify. "
        "Direct recall or single-step. Easy.\n"
        'Examples: "Write 502 - 178 in column form." / '
        '"What is the hundreds digit in 507?" / "Is 456 > 465?"'
    ),
    "application": (
        "format: direct_compute OR word_problem. "
        "For word_problem use regional names and real-world scenarios. "
        "Exact numerical answer required.\n"
        'Examples: "Calculate 345 + 278." / '
        '"{name} had 502 marbles and gave away 178. How many are left?"'
    ),
    "representation": (
        "format: missing_number OR estimation OR place_value OR compare_solutions. "
        'NEVER "visualize" or "draw" or "use array/number line".\n'
        'Examples: "___ + 178 = 502" / '
        '"Estimate 478 + 256 to the nearest hundred." / '
        '"Show 345 as 3 hundreds + ___ tens + 5 ones."'
    ),
    "error_detection": (
        "format: error_spot OR compare_solutions. "
        "MUST show a specific WRONG worked answer or two student claims. "
        "Student finds the mistake.\n"
        'Examples: "A student solved 502 - 178 and got 334. '
        'Find the mistake and write the correct answer." / '
        '"{name} says 400 - 168 = 242. Is he correct? If not, correct it."'
    ),
    "thinking": (
        "format: estimation OR compare_solutions OR create_example. "
        "Reasoning, not pure computation.\n"
        'Examples: "Without calculating, which is greater: 345 + 278 or '
        '400 + 200? Explain." / "Create a subtraction problem where you '
        'need to borrow from the hundreds place."'
    ),
}

REGION_CONTEXT: dict[str, dict[str, str]] = {
    "India": {
        "names": "Aarav, Priya, Rohan, Ananya, Meera, Kabir, Diya, Arjun",
        "contexts": "mangoes, cricket, Diwali, market, school, park, library, train",
        "currency": "rupees",
    },
    "UAE": {
        "names": "Ahmed, Fatima, Omar, Mariam, Sara, Yusuf, Layla, Ali",
        "contexts": "dates, football, Eid, souq, school, park, library, desert",
        "currency": "AED",
    },
}

QUESTION_USER_TEMPLATE = (
    "Grade {grade} {subject} | Micro-skill: {micro_skill} | "
    "Slot: {slot_type} | Difficulty: {difficulty}\n"
    "Avoid reusing: {avoid}\n"
    "Names: {names}. Contexts: {contexts}. Currency: {currency}.\n"
    "{slot_rules}\n"
    "{language_instruction}"
    'JSON: {{"format":"","question_text":"","pictorial_elements":[],"answer":""}}'
)


# ════════════════════════════════════════════════════════════
# E) Validators
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
    r"|how do you know|in your own words|what would happen)",
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
    """Validate the full worksheet: slot distribution, uniqueness, forbidden phrases."""
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
            f"— difficulty should be Medium or Hard, not Easy"
        )

    return issues


# ════════════════════════════════════════════════════════════
# B) Generation Pipeline
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
) -> dict:
    """Generate a single question via LLM. Returns question dict."""
    region_ctx = REGION_CONTEXT.get(region, REGION_CONTEXT["India"])
    slot_rules_text = SLOT_RULES.get(slot_type, "")

    # Inject a sample name into slot rules for application examples
    first_name = region_ctx["names"].split(",")[0].strip()
    slot_rules_text = slot_rules_text.replace("{name}", first_name)

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
        names=region_ctx["names"],
        contexts=region_ctx["contexts"],
        currency=region_ctx["currency"],
        slot_rules=slot_rules_text,
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

    # Extract context nouns
    context_words = [
        "marbles", "stickers", "mangoes", "books", "apples", "pencils",
        "balls", "sweets", "chocolates", "biscuits", "pages", "stamps",
        "dates", "dirhams", "rupees", "tickets", "flowers", "stars",
        "cricket", "football", "crayons", "beads", "coins", "shells",
    ]
    text_lower = text.lower()
    for word in context_words:
        if word in text_lower:
            items.append(word)

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
        "Slot pipeline: grade=%s topic=%s q=%d diff=%s",
        grade, topic, q_count, difficulty,
    )

    # 1. Generate meta
    meta = generate_meta(client, grade, subject, topic, difficulty, region)
    micro_skill = meta.get("micro_skill", topic)
    logger.info("Meta: micro_skill=%s", micro_skill)

    # Difficulty sanity check — auto-bump if easy is inappropriate
    diff_issues = validate_difficulty_sanity(micro_skill, difficulty)
    if diff_issues and difficulty.lower() == "easy":
        logger.warning("Bumping difficulty easy→medium: %s", diff_issues)
        difficulty = "medium"
        meta["difficulty"] = "Medium"

    # 2. Get slot plan
    slot_plan = get_slot_plan(q_count)
    logger.info("Slot plan (%d): %s", len(slot_plan), dict(Counter(slot_plan)))

    # 3. Generate each question
    questions: list[dict] = []
    avoid_state: list[str] = []
    max_attempts = 3

    for i, slot_type in enumerate(slot_plan):
        q_difficulty = get_question_difficulty(slot_type, difficulty)

        generated = False
        for attempt in range(max_attempts):
            try:
                q = generate_question(
                    client, grade, subject, micro_skill,
                    slot_type, q_difficulty, avoid_state, region, language,
                )

                issues = validate_question(q, slot_type)

                if issues and attempt < max_attempts - 1:
                    logger.warning(
                        "Q%d/%d attempt %d issues: %s — retrying",
                        i + 1, len(slot_plan), attempt + 1, issues,
                    )
                    # Add issue hints to avoid_state so next attempt varies
                    avoid_state.append(f"rejected:{q.get('format','')}")
                    continue

                if issues:
                    logger.warning(
                        "Q%d/%d still has issues after %d attempts: %s — using best effort",
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

        logger.info(
            "Q%d/%d: %s / %s",
            i + 1, len(slot_plan), slot_type, questions[-1].get("format", "?"),
        )

    # 4. Validate whole worksheet
    ws_issues = validate_worksheet_slots(questions, q_count)
    if ws_issues:
        logger.warning("Worksheet-level issues: %s", ws_issues)

    # Attach context to meta
    meta["grade"] = grade
    meta["subject"] = subject
    meta["topic"] = topic

    logger.info("Slot pipeline complete: %d questions", len(questions))
    return meta, questions
