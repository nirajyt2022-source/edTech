from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Literal
import json
import logging
import re
import uuid
from math import ceil
from datetime import datetime
from openai import OpenAI
from supabase import create_client
from app.core.config import get_settings
from app.services.pdf import get_pdf_service

router = APIRouter(prefix="/api/worksheets", tags=["worksheets"])
pdf_service = get_pdf_service()

settings = get_settings()
client = OpenAI(api_key=settings.openai_api_key)
supabase = create_client(settings.supabase_url, settings.supabase_service_key)

logger = logging.getLogger("practicecraft.worksheets")


class WorksheetGenerationRequest(BaseModel):
    board: str
    grade_level: str
    subject: str
    topic: str
    difficulty: Literal["easy", "medium", "hard"]
    num_questions: int = 10
    language: str = "English"
    custom_instructions: str | None = None
    skills: list[str] | None = None
    logic_tags: list[str] | None = None
    region: str = "India"
    problem_style: Literal["standard", "visual", "mixed"] = "standard"


# ──────────────────────────────────────────────
# Models (extended for v3.8 — all new fields optional for backward compat)
# ──────────────────────────────────────────────

class Question(BaseModel):
    id: str
    type: str
    text: str
    options: list[str] | None = None
    correct_answer: str | None = None
    explanation: str | None = None
    difficulty: str | None = None
    answer_type: str | None = None
    sample_answer: str | None = None
    grading_notes: str | None = None
    visual_type: str | None = None
    visual_data: dict | None = None
    role: str | None = None  # Phase 4: pedagogical role
    skill_tag: str | None = None  # Phase 5: skill diagnostic tag


class Worksheet(BaseModel):
    title: str
    grade: str
    subject: str
    topic: str
    difficulty: str
    language: str
    questions: list[Question]
    skill_focus: str = ""
    common_mistake: str = ""
    parent_tip: str = ""


class WorksheetGenerationResponse(BaseModel):
    worksheet: Worksheet
    generation_time_ms: int


# ──────────────────────────────────────────────
# v3.8 System Prompt Builder
# ──────────────────────────────────────────────

def build_system_prompt(
    region: str = "India",
    problem_style: str = "standard",
    is_visual_applicable: bool = False,
    logic_tags: list[str] | None = None,
) -> str:
    """Build the PracticeCraft v3.8 world-class system prompt."""

    prompt = """You are PracticeCraft Worksheet Engine v3.8 — an expert primary-school teacher, curriculum designer, and assessment architect.

Your job is to generate world-class, grade-appropriate worksheets that improve conceptual understanding, build structured skill progression, and maintain strict curriculum alignment.

CORE QUALITY RULES (NON-NEGOTIABLE):
1. Grade-Safe: Do NOT introduce concepts beyond the specified grade.
2. No Personal Data: Never ask for real names, addresses, phone numbers, or personal family details.
3. Clarity: Every question must be solvable with the given information.
4. No Ambiguity: Avoid vague wording.
5. Difficulty Accuracy:
   - Easy = direct recall or single-step
   - Medium = 1-2 step skill application
   - Hard = reasoning, multi-step, or scenario-based (but grade-safe)
6. Avoid repetition of identical structures.
7. Exactly the requested number of questions.

PEDAGOGICAL STRUCTURE (MANDATORY):
Follow this cognitive progression (roles will be assigned post-generation):
1. warmup — direct computation, single-step, easy. No visuals.
2. concept_visual — include visual_type + visual_data when visual mode is active.
3. word_problem — real-world scenario with names/context. Exact answer required.
4. reasoning — compare, missing number, pattern, true/false reasoning. NOT pure arithmetic.
5. challenge — multi-step (2+ operations) or advanced reasoning.

For 5 questions, use exactly this order. For more, cycle the pattern.

For Maths:
- Include at least one word problem.
- Encourage estimation or reasoning when appropriate.
- Do not rely only on raw calculations.

For Language subjects:
- Include contextual or usage-based questions.
- Include at least one comprehension or applied question."""

    # ── Regional context ──
    if region == "UAE":
        prompt += """

REGIONAL CONTEXT:
- Use AED for money problems.
- Use UAE names (Ahmed, Fatima, Omar, Mariam).
- Use UAE-relevant contexts (desert, oasis, date palms, Burj Khalifa, National Day, Eid).
- Keep examples culturally appropriate but simple."""
    else:
        prompt += """

REGIONAL CONTEXT:
- Use Rupees for money problems.
- Use culturally familiar names (Aarav, Priya, Rohan, Ananya).
- Use relatable Indian examples (mangoes, cricket, Diwali, Holi, local markets).
- Keep examples culturally appropriate but simple."""

    # ── Visual mode rules (conditional) ──
    if is_visual_applicable:
        if problem_style == "visual":
            coverage = "ALL questions MUST include visual_type and visual_data."
        else:
            coverage = "At least HALF of the questions must include visual_type and visual_data. The rest should be standard text-only."

        prompt += f"""

VISUAL MODE RULES:
{coverage}

IMPORTANT: "type" must ALWAYS be one of: multiple_choice, fill_blank, short_answer, true_false.
Do NOT use visual type names as the question "type".
Visuals go in "visual_type" and "visual_data" fields only.

Visual types allowed: multiplication_array, number_line_jumps, number_line, object_group, shapes, clock.

MULTIPLICATION RULE: Use multiplication_array for "groups of" or "times" problems.
ADDITION RULE: Prefer number_line_jumps for conceptual addition understanding.

Drawable constraints:
- object_group counts MUST NOT exceed 20 per group. For larger numbers use number_line instead.
- object_group labels must be simple, drawable nouns (e.g. "apples", "stars", "balls"). Avoid compound phrases like "boxes of chocolates".
- multiplication_array: rows × columns must not exceed 20. For larger products use number_line.

Formats:
- clock: {{ "hour": 1-12, "minute": 0|5|10|...|55 }}
- number_line: {{ "start": int, "end": int, "step": int, "highlight": int }}
- number_line_jumps: {{ "start": int, "end": int, "jump_size": int, "num_jumps": int, "result": int }}
- multiplication_array: {{ "rows": int, "columns": int, "label": "dots" }}
- object_group: {{ "groups": [{{"count": 1-20, "label": "apples"}}], "operation": "+"|"-"|"x" }}
  For multiplication ("x"), prefer multiplication_array when both factors <= 10 and product <= 20, else use number_line.
- shapes: {{ "shape": "triangle"|"circle"|"rectangle"|"square", "sides": [numbers] }}

Keep the "text" field as a readable question even for visual questions."""

    # ── Logic tag guidance ──
    if logic_tags:
        tag_map = {
            "numerical": "Include arithmetic, calculation, and number-based problems",
            "vocabulary": "Include matching, fill-in-the-blank, and word-building exercises",
            "reading_comprehension": "Include short passages with comprehension questions",
            "observation": "Include scenario-based MCQs and reasoning questions",
            "diagrammatic": "Include labeling, drawing, and diagram-based questions",
        }
        tag_lines = [f"- {tag}: {tag_map[tag]}" for tag in logic_tags if tag in tag_map]
        if tag_lines:
            prompt += "\n\nQUESTION TYPE GUIDANCE:\n" + "\n".join(tag_lines)

    # ── Difficulty engine ──
    prompt += """

DIFFICULTY ENGINE:
- If difficulty = hard:
  - Include at least one multi-step problem.
  - Include one reasoning problem.
  - Include one conceptual visual (when visual mode is active).
  - Include one word problem.
- If carrying or borrowing is required → difficulty must be >= medium (never easy).
- Easy = direct recall, single-step. Medium = 1-2 step. Hard = multi-step or reasoning."""

    # ── Answer rules + parent support + output format ──
    prompt += """

ANSWER RULES:
- Computational math questions: answer_type="exact", correct_answer must be present, sample_answer=null.
- True/False: correct_answer must be "true" or "false" (lowercase string).
- Open-ended questions (write/explain/describe): set correct_answer=null, answer_type="example", provide sample_answer and grading_notes.

PARENT SUPPORT (include at top level of JSON):
- "skill_focus": brief statement of the core skill being practiced
- "common_mistake": typical mistake children make on this topic
- "parent_tip": short actionable guidance (1 sentence)

These must be practical and clear.

Each question MUST include:
- "role": one of warmup, concept_visual, word_problem, reasoning, challenge
- "skill_tag": short skill descriptor (e.g. "2-digit addition with carry", "place value", "skip counting by 5s")

OUTPUT FORMAT (JSON only, no markdown):
{
  "title": "...",
  "skill_focus": "...",
  "common_mistake": "...",
  "parent_tip": "...",
  "questions": [
    {
      "id": "q1",
      "role": "warmup" | "concept_visual" | "word_problem" | "reasoning" | "challenge",
      "skill_tag": "...",
      "type": "multiple_choice" | "fill_blank" | "short_answer" | "true_false",
      "text": "...",
      "options": ["..."] | null,
      "correct_answer": "..." | null,
      "answer_type": "exact" | "example",
      "sample_answer": "..." | null,
      "grading_notes": "..." | null,
      "difficulty": "easy" | "medium" | "hard",
      "explanation": "Brief explanation",
      "visual_type": "multiplication_array" | "number_line_jumps" | "number_line" | "object_group" | "shapes" | "clock" | null,
      "visual_data": { ... } | null
    }
  ]
}

FINAL CHECK BEFORE OUTPUT:
- Valid JSON only. No markdown.
- All required fields present (including role and skill_tag on every question).
- Exactly requested question count.
- No personal data prompts.
- Carry/borrow questions are never marked easy."""

    return prompt


# ──────────────────────────────────────────────
# Helpers: JSON cleanup, parsing, validation
# ──────────────────────────────────────────────

def clean_json_response(content: str) -> str:
    """Strip markdown fences from model output."""
    content = content.strip()
    if content.startswith("```json"):
        content = content[7:]
    if content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    return content.strip()


_VALID_QUESTION_TYPES = {"multiple_choice", "fill_blank", "short_answer", "true_false"}
_VISUAL_TYPE_NAMES = {
    "number_line", "number_line_jumps", "object_group",
    "multiplication_array", "clock", "shapes",
}


def parse_question(q: dict, index: int, fallback_difficulty: str) -> Question:
    """Parse a question dict into a Question model with backward-compatible defaults."""
    correct_answer = q.get("correct_answer")
    answer_type = q.get("answer_type")
    if not answer_type:
        answer_type = "exact" if correct_answer is not None else "example"

    # Token efficiency: exact answers don't need sample_answer
    sample_answer = q.get("sample_answer")
    if answer_type == "exact":
        sample_answer = None

    q_type = q.get("type", "short_answer")
    visual_type = q.get("visual_type")

    # Fix #2: Remap visual type names used as question type
    if q_type in _VISUAL_TYPE_NAMES:
        visual_type = visual_type or q_type
        q_type = "fill_blank" if correct_answer is not None else "short_answer"

    # Clamp to valid enum
    if q_type not in _VALID_QUESTION_TYPES:
        q_type = "short_answer"

    return Question(
        id=q.get("id", f"q{index + 1}"),
        type=q_type,
        text=q.get("text", ""),
        options=q.get("options"),
        correct_answer=correct_answer,
        explanation=q.get("explanation"),
        difficulty=q.get("difficulty", fallback_difficulty),
        answer_type=answer_type,
        sample_answer=sample_answer,
        grading_notes=q.get("grading_notes"),
        visual_type=visual_type,
        visual_data=q.get("visual_data"),
        role=q.get("role"),
        skill_tag=q.get("skill_tag"),
    )


def _fixup_question_types(data: dict) -> None:
    """Mutate data in-place: remap visual type names used as question type."""
    for q in data.get("questions", []):
        q_type = q.get("type", "")
        if q_type in _VISUAL_TYPE_NAMES:
            q["visual_type"] = q.get("visual_type") or q_type
            q["type"] = (
                "fill_blank" if q.get("correct_answer") is not None else "short_answer"
            )
        elif q_type not in _VALID_QUESTION_TYPES:
            q["type"] = "short_answer"


# Two-part check: text has digits AND operation keywords → computational
_HAS_DIGIT = re.compile(r"\d")
_HAS_OPERATION = re.compile(
    r"(\+|-|×|÷|/|\*"
    r"|\badd\b|\bsubtract\b|\bmultiply\b|\bdivide\b"
    r"|\bsum\b|\bdifference\b|\bproduct\b|\btotal\b"
    r"|\bhow many\b|\bkitne\b|\bjod\b|\bghata\b"
    r"|\d\s*x\s*\d)",  # "3 x 4" but not "example"
    re.IGNORECASE,
)


def _is_computational(text: str) -> bool:
    """Return True if text looks like a maths computation question."""
    return bool(_HAS_DIGIT.search(text) and _HAS_OPERATION.search(text))


def _trim_to_count(data: dict, n: int, problem_style: str, is_visual: bool) -> None:
    """Trim questions to exactly N, preserving visual quota for mixed/visual modes."""
    questions = data.get("questions", [])
    if len(questions) <= n:
        return

    if is_visual and problem_style == "mixed":
        required_visual = ceil(n / 2)
        visual_qs = [q for q in questions if q.get("visual_type") and q.get("visual_data")]
        text_qs = [q for q in questions if not (q.get("visual_type") and q.get("visual_data"))]
        # Take as many visual as needed, fill rest with text
        picked = visual_qs[:required_visual]
        remaining = n - len(picked)
        picked += text_qs[:remaining]
        # If still short (not enough text-only), backfill with more visual
        if len(picked) < n:
            extra = [q for q in visual_qs[required_visual:] if q not in picked]
            picked += extra[: n - len(picked)]
        data["questions"] = picked[:n]
    elif is_visual and problem_style == "visual":
        # Keep only visual ones, trim to N
        visual_qs = [q for q in questions if q.get("visual_type") and q.get("visual_data")]
        data["questions"] = visual_qs[:n] if len(visual_qs) >= n else questions[:n]
    else:
        data["questions"] = questions[:n]

    # Re-number IDs
    for i, q in enumerate(data["questions"]):
        q["id"] = f"q{i + 1}"


def _fix_computational_answers(data: dict) -> None:
    """Force answer_type='exact' and flag missing correct_answer on computational questions."""
    for q in data.get("questions", []):
        text = q.get("text", "")
        if _is_computational(text):
            # This is arithmetic/computational — must be exact
            if q.get("correct_answer") is not None:
                q["answer_type"] = "exact"
                q["sample_answer"] = None
            # If correct_answer is null but it's clearly computational,
            # flag it — validator will catch and send to repair


def _fix_number_line_step(data: dict) -> None:
    """Ensure number_line step is sane: if range > 40, step >= 2 (prefer 5 or 10)."""
    for q in data.get("questions", []):
        if q.get("visual_type") == "number_line" and isinstance(q.get("visual_data"), dict):
            vd = q["visual_data"]
            start = vd.get("start", 0)
            end = vd.get("end", 0)
            step = vd.get("step", 1)
            span = end - start
            if span > 40 and step < 2:
                vd["step"] = 5 if span > 80 else 10 if span > 60 else 2


# ──────────────────────────────────────────────
# Carry / Borrow detection + difficulty enforcement
# ──────────────────────────────────────────────

_ADDITION_PATTERN = re.compile(r"\+|\badd\b|\bsum\b|\btotal\b|\bplus\b|\bjod\b", re.IGNORECASE)
_SUBTRACTION_PATTERN = re.compile(
    r"-|\bsubtract\b|\bminus\b|\bdifference\b|\btake\s+away\b|\bghata\b", re.IGNORECASE
)


def _needs_carry_or_borrow(text: str) -> bool:
    """Heuristic: detect if a question likely requires carrying or borrowing."""
    numbers = [int(m) for m in re.findall(r"\d+", text) if int(m) >= 10]
    if len(numbers) < 2:
        return False
    a, b = numbers[0], numbers[1]
    if _ADDITION_PATTERN.search(text):
        if (a % 10) + (b % 10) >= 10:
            return True
    if _SUBTRACTION_PATTERN.search(text):
        hi, lo = max(a, b), min(a, b)
        if (hi % 10) < (lo % 10):
            return True
    return False


def _fix_carry_borrow_difficulty(data: dict) -> None:
    """If a question requires carrying/borrowing, bump difficulty to at least medium."""
    for q in data.get("questions", []):
        text = q.get("text", "")
        if _needs_carry_or_borrow(text) and q.get("difficulty") == "easy":
            q["difficulty"] = "medium"


# ──────────────────────────────────────────────
# Hard difficulty engine validation
# ──────────────────────────────────────────────

def _validate_difficulty_engine(
    data: dict, requested_difficulty: str, is_visual_applicable: bool
) -> list[str]:
    """For hard worksheets, ensure required question types are present."""
    if requested_difficulty != "hard":
        return []

    issues: list[str] = []
    questions = data.get("questions", [])

    has_multi_step = any(q.get("role") == "challenge" for q in questions)
    has_reasoning = any(q.get("role") == "reasoning" for q in questions)
    has_word_problem = any(q.get("role") == "word_problem" for q in questions)
    has_concept_visual = any(
        q.get("role") == "concept_visual" and q.get("visual_type")
        for q in questions
    )

    if not has_multi_step:
        issues.append("hard difficulty requires at least one multi-step (challenge) problem")
    if not has_reasoning:
        issues.append("hard difficulty requires at least one reasoning problem")
    if not has_word_problem:
        issues.append("hard difficulty requires at least one word problem")
    if is_visual_applicable and not has_concept_visual:
        issues.append("hard difficulty requires at least one conceptual visual")

    return issues


# ──────────────────────────────────────────────
# Phase 4: Pedagogical Role Engine
# ──────────────────────────────────────────────

_ROLE_CYCLE = ["warmup", "concept_visual", "word_problem", "reasoning", "challenge"]
_VALID_ROLES = set(_ROLE_CYCLE)

_WORD_PROBLEM_PATTERN = re.compile(
    r"(has|have|gives?|buys?|sells?|eats?|left|remaining|costs?|pays?|earns?"
    r"|shares?|distribut|collect|picks?|plant|bake|cook|travel|walk|run"
    r"|पास|देता|खरीद|बेच|खाता|बचा|कीमत)",
    re.IGNORECASE,
)

_REASONING_PATTERN = re.compile(
    r"(\bcompare\b|\bwhich is (more|less|greater|smaller)\b"
    r"|\bmissing number\b|\bfind the (mistake|error)\b"
    r"|\btrue or false\b|\bwhat comes next\b|\bpattern\b"
    r"|\bwhat is wrong\b|\brule\b|\brelationship\b)",
    re.IGNORECASE,
)

_MULTI_OP_PATTERN = re.compile(
    r"(\d\s*[\+\-\*/×÷]\s*\d.*[\+\-\*/×÷]\s*\d"  # two operators with digits
    r"|\bthen\b.*\bthen\b"  # two "then" steps
    r"|\bfirst\b.*\bthen\b"  # first...then
    r"|\band\s+then\b)",
    re.IGNORECASE,
)


def _build_role_sequence(n: int) -> list[str]:
    """Build a role sequence for n questions by cycling through the 5-role pattern."""
    if n <= 0:
        return []
    if n <= 5:
        # For small counts, pick evenly from the pattern
        indices = [round(i * 4 / (n - 1)) if n > 1 else 0 for i in range(n)]
        return [_ROLE_CYCLE[idx] for idx in indices]
    # For larger counts, cycle the full pattern
    seq: list[str] = []
    for i in range(n):
        seq.append(_ROLE_CYCLE[i % 5])
    return seq


def _assign_roles(data: dict, difficulty: str) -> None:
    """Deterministically assign pedagogical roles to questions in-place."""
    questions = data.get("questions", [])
    n = len(questions)
    roles = _build_role_sequence(n)

    for q, role in zip(questions, roles):
        q["role"] = role
        # Enforce difficulty alignment
        if role == "warmup":
            q["difficulty"] = "easy"
        elif role == "challenge":
            q["difficulty"] = "hard" if difficulty == "hard" else "medium"


def _validate_roles(data: dict, is_visual_applicable: bool) -> list[str]:
    """Validate that each question satisfies its assigned role constraints."""
    issues: list[str] = []
    questions = data.get("questions", [])

    for q in questions:
        qid = q.get("id", "?")
        role = q.get("role")
        if not role or role not in _VALID_ROLES:
            continue  # skip validation for unrecognized roles

        text = q.get("text", "")
        correct = q.get("correct_answer")
        has_visual = bool(q.get("visual_type") and q.get("visual_data"))

        if role == "warmup":
            if not _is_computational(text) and correct is None:
                issues.append(
                    f"{qid} (warmup): should be computational with exact answer"
                )
            if has_visual:
                issues.append(f"{qid} (warmup): visual_type must be null")

        elif role == "concept_visual":
            if is_visual_applicable and not has_visual:
                issues.append(
                    f"{qid} (concept_visual): must include visual_type + visual_data"
                )

        elif role == "word_problem":
            if not _WORD_PROBLEM_PATTERN.search(text):
                issues.append(
                    f"{qid} (word_problem): must include real-world context "
                    f"(names, buying, giving, etc.)"
                )
            if correct is None:
                issues.append(
                    f"{qid} (word_problem): must have exact correct_answer"
                )

        elif role == "reasoning":
            # Should not be pure arithmetic
            if _is_computational(text) and not _REASONING_PATTERN.search(text):
                issues.append(
                    f"{qid} (reasoning): should not be pure arithmetic — "
                    f"use compare, pattern, missing number, or true/false reasoning"
                )

        elif role == "challenge":
            if not _MULTI_OP_PATTERN.search(text) and not _REASONING_PATTERN.search(text):
                issues.append(
                    f"{qid} (challenge): should be multi-step (2+ operations) "
                    f"or advanced reasoning"
                )

    return issues


_PERSONAL_DATA_PATTERNS = re.compile(
    r"("
    r"your\s+(father|mother|parent)'?s?\s+name"
    r"|my\s+(father|mother|parent)'?s?\s+name"
    r"|मेरे\s+पिता\s+का\s+नाम"
    r"|अपने\s+पिता\s+का\s+नाम"
    r"|phone\s*number"
    r"|your\s+address"
    r"|फ़ोन\s*नंबर"
    r"|पता\s+लिखि"
    r")",
    re.IGNORECASE,
)

_OPEN_ENDED_PATTERNS = re.compile(
    r"\b(write|describe|explain|लिखिए|बताइए)\b",
    re.IGNORECASE,
)


_ALLOWED_OPERATIONS = {"+", "-", "x"}


def validate_worksheet_data(
    data: dict,
    problem_style: str = "standard",
    is_visual_applicable: bool = False,
) -> list[str]:
    """Validate parsed worksheet JSON. Returns list of issue descriptions (empty = valid)."""
    issues: list[str] = []
    questions = data.get("questions", [])

    for i, q in enumerate(questions):
        qid = q.get("id", f"q{i + 1}")

        # Required keys
        if not q.get("text"):
            issues.append(f"{qid}: missing question text")

        q_type = q.get("type", "")
        correct = q.get("correct_answer")

        # Type enum correctness
        if q_type not in _VALID_QUESTION_TYPES:
            issues.append(
                f"{qid}: type '{q_type}' is invalid — must be one of "
                f"{sorted(_VALID_QUESTION_TYPES)}"
            )

        # MCQ: correct_answer must be in options
        if q_type == "multiple_choice":
            options = q.get("options") or []
            if correct is not None and correct not in options:
                issues.append(
                    f"{qid}: correct_answer '{correct}' not in options {options}"
                )

        # True/False: must be lowercase "true" or "false"
        if q_type == "true_false":
            if correct not in ("true", "false"):
                issues.append(
                    f"{qid}: true_false correct_answer must be 'true' or 'false', got '{correct}'"
                )

        # Open-ended detection
        text = q.get("text", "")
        if _OPEN_ENDED_PATTERNS.search(text):
            if correct is not None:
                issues.append(f"{qid}: open-ended question should have correct_answer=null")
            if q.get("answer_type") != "example":
                issues.append(f"{qid}: open-ended question should have answer_type='example'")

        # Personal data ban
        if _PERSONAL_DATA_PATTERNS.search(text):
            issues.append(f"{qid}: question asks for personal data — remove it")

        # Maths computational rule: must have exact answer
        if _is_computational(text) and correct is None:
            issues.append(
                f"{qid}: computational question must have correct_answer (not null)"
            )

        # Carry/borrow → difficulty >= medium
        if _needs_carry_or_borrow(text) and q.get("difficulty") == "easy":
            issues.append(
                f"{qid}: question requires carrying/borrowing, "
                f"difficulty must be >= medium"
            )

        # Visual field validation
        vtype = q.get("visual_type")
        vdata = q.get("visual_data")

        if vtype == "number_line" and isinstance(vdata, dict):
            nl_start = vdata.get("start", 0)
            nl_end = vdata.get("end", 0)
            nl_step = vdata.get("step", 1)
            if (nl_end - nl_start) > 40 and nl_step < 2:
                issues.append(
                    f"{qid}: number_line range {nl_end - nl_start} with step={nl_step} "
                    f"is too dense — step must be >= 2"
                )

        if vtype == "object_group" and isinstance(vdata, dict):
            # object_group count <= 20
            for g in vdata.get("groups", []):
                if g.get("count", 0) > 20:
                    issues.append(
                        f"{qid}: object_group count {g['count']} exceeds 20 — "
                        f"use number_line instead"
                    )
            # operation allowed values
            op = vdata.get("operation")
            if op and op not in _ALLOWED_OPERATIONS:
                issues.append(
                    f"{qid}: object_group operation '{op}' invalid — "
                    f"must be one of {sorted(_ALLOWED_OPERATIONS)}"
                )

        if vtype == "multiplication_array" and isinstance(vdata, dict):
            rows = vdata.get("rows", 0)
            cols = vdata.get("columns", 0)
            if rows * cols > 20:
                issues.append(
                    f"{qid}: multiplication_array {rows}x{cols}={rows * cols} exceeds "
                    f"20 drawable tokens — use number_line instead"
                )

    # Visual ratio checks (aggregated)
    if is_visual_applicable:
        visual_count = sum(
            1 for q in questions if q.get("visual_type") and q.get("visual_data")
        )
        total = len(questions)
        if problem_style == "visual" and visual_count < total:
            issues.append(
                f"visual mode requires ALL {total} questions to have visual fields, "
                f"but only {visual_count} do"
            )
        elif problem_style == "mixed" and total > 0 and visual_count < ceil(total / 2):
            issues.append(
                f"mixed mode requires at least {ceil(total / 2)} visual questions, "
                f"but only {visual_count} found"
            )

    return issues


def enforce_visual_rules(
    data: dict, problem_style: str, is_visual_applicable: bool
) -> tuple[dict, list[str]]:
    """Enforce visual mode constraints. Returns (modified data, list of unfixable issues)."""
    if not is_visual_applicable:
        return data, []

    questions = data.get("questions", [])
    issues: list[str] = []

    for q in questions:
        if q.get("visual_type") == "object_group" and isinstance(q.get("visual_data"), dict):
            groups = q["visual_data"].get("groups", [])
            op = q["visual_data"].get("operation", "+")

            # object_group counts > 20 → convert to number_line
            over = any(g.get("count", 0) > 20 for g in groups)

            # Multiplication with large product → prefer number_line
            mult_too_large = (
                op == "x"
                and len(groups) >= 2
                and (groups[0].get("count", 0) * groups[1].get("count", 0)) > 20
            )

            if over or mult_too_large:
                if op == "x" and len(groups) >= 2:
                    total = groups[0].get("count", 0) * groups[1].get("count", 0)
                else:
                    total = sum(g.get("count", 0) for g in groups)
                step = 1 if total <= 20 else 2 if total <= 50 else 5
                q["visual_type"] = "number_line"
                q["visual_data"] = {
                    "start": 0,
                    "end": total + step,
                    "step": step,
                    "highlight": total,
                }

        # multiplication_array: product > 20 → convert to number_line
        if q.get("visual_type") == "multiplication_array" and isinstance(
            q.get("visual_data"), dict
        ):
            rows = q["visual_data"].get("rows", 0)
            cols = q["visual_data"].get("columns", 0)
            product = rows * cols
            if product > 20:
                step = 1 if product <= 20 else 2 if product <= 50 else 5
                q["visual_type"] = "number_line"
                q["visual_data"] = {
                    "start": 0,
                    "end": product + step,
                    "step": step,
                    "highlight": product,
                }

    # Check coverage requirements
    visual_count = sum(
        1 for q in questions if q.get("visual_type") and q.get("visual_data")
    )
    total = len(questions)
    required = ceil(total / 2) if problem_style == "mixed" else total

    if problem_style == "visual" and visual_count < total:
        issues.append(
            f"visual mode requires ALL {total} questions to have visual_type+visual_data, "
            f"but only {visual_count} do"
        )
    elif problem_style == "mixed" and total > 0 and visual_count < required:
        issues.append(
            f"mixed mode requires at least {required} visual questions "
            f"(ceil({total}/2)), but only {visual_count} found"
        )

    return data, issues


# ──────────────────────────────────────────────
# Phase 5.3: Quality Moat Validators
# ──────────────────────────────────────────────

# -- Visual integrity patterns (defined before functions to prevent NameError) --
_ARRAY_TEXT_PATTERN = re.compile(
    r"\b(array|rows?\s+and\s+columns?|columns?\s+and\s+rows?|grid)\b", re.IGNORECASE
)
_NUMBER_LINE_TEXT_PATTERN = re.compile(
    r"\b(number\s+line|jump|hop)\b", re.IGNORECASE
)
_MULTIPLICATION_VISUAL_TEXT = re.compile(
    r"\b(times|groups?\s+of|multiply|×)\b|\d\s*x\s*\d", re.IGNORECASE
)

# -- Cognitive depth patterns --
_COGNITIVE_DEPTH_PATTERNS = {
    "error_analysis": re.compile(
        r"\b(find the (mistake|error)|what is wrong|correct the|spot the)\b",
        re.IGNORECASE,
    ),
    "strategy_compare": re.compile(
        r"\b(which method|compare|better way|which is (easier|faster)|two ways)\b",
        re.IGNORECASE,
    ),
    "estimate_calculate": re.compile(
        r"\b(estimate|approximately|round off|about how many|close to)\b",
        re.IGNORECASE,
    ),
    "missing_number": re.compile(
        r"\b(missing number|find the number|what number|unknown)\b|[_?□▢]{2,}",
        re.IGNORECASE,
    ),
}

# -- Multi-representation patterns --
_MULTIPLICATION_TOPIC = re.compile(
    r"\b(multipl|times\s*table|groups?\s+of|product)\b", re.IGNORECASE
)
_3DIGIT_ADDSUB_TOPIC = re.compile(
    r"\b(3[\s-]?digit|three[\s-]?digit).*(add|subtract)"
    r"|\b(add|subtract).*(3[\s-]?digit|three[\s-]?digit)",
    re.IGNORECASE,
)
_MISSING_NUMBER_PATTERN = re.compile(
    r"[_?□▢]{2,}|\b(missing|find the number|what number|blank)\b", re.IGNORECASE
)
_INVERSE_ERROR_PATTERN = re.compile(
    r"\b(check|verify|find the (mistake|error)|inverse|reverse|undo)\b", re.IGNORECASE
)
_MULT_EQUATION_PATTERN = re.compile(
    r"×|\d\s*x\s*\d|\btimes\b|\*", re.IGNORECASE
)


def validate_visual_integrity(
    data: dict,
    problem_style: str = "standard",
    is_visual_applicable: bool = False,
) -> list[str]:
    """Validate text↔visual alignment and visual data consistency.

    Visual density (ratio) is already checked in validate_worksheet_data().
    """
    issues: list[str] = []
    questions = data.get("questions", [])

    for q in questions:
        qid = q.get("id", "?")
        text = q.get("text", "")
        vtype = q.get("visual_type")
        vdata = q.get("visual_data")
        has_visual = bool(vtype and vdata)

        # 1. Text mentions array/grid → visual_type must be multiplication_array
        if _ARRAY_TEXT_PATTERN.search(text) and has_visual:
            if vtype != "multiplication_array":
                issues.append(
                    f"{qid}: text mentions array/grid but visual_type='{vtype}' "
                    f"— use 'multiplication_array'"
                )

        # 2. Text mentions number line/jump/hop → must be number_line or number_line_jumps
        if _NUMBER_LINE_TEXT_PATTERN.search(text) and has_visual:
            if vtype not in ("number_line", "number_line_jumps"):
                issues.append(
                    f"{qid}: text mentions number line/jumps but visual_type='{vtype}' "
                    f"— use 'number_line' or 'number_line_jumps'"
                )

        # 3. Multiplication text + visual: prefer multiplication_array over highlight-only
        if (
            _MULTIPLICATION_VISUAL_TEXT.search(text)
            and vtype == "number_line"
            and isinstance(vdata, dict)
            and vdata.get("highlight")
            and not vdata.get("jump_size")
        ):
            issues.append(
                f"{qid}: multiplication uses number_line highlight-only "
                f"— prefer multiplication_array"
            )

        # 4. number_line_jumps: internal consistency
        if vtype == "number_line_jumps" and isinstance(vdata, dict):
            start = vdata.get("start", 0)
            jump_size = vdata.get("jump_size", 0)
            num_jumps = vdata.get("num_jumps", 0)
            result = vdata.get("result")
            if jump_size and num_jumps and result is not None:
                expected_fwd = start + jump_size * num_jumps
                expected_bwd = start - jump_size * num_jumps
                if result != expected_fwd and result != expected_bwd:
                    issues.append(
                        f"{qid}: number_line_jumps result={result} inconsistent — "
                        f"expected {expected_fwd} or {expected_bwd}"
                    )

        # 5. multiplication_array: rows*cols must match correct_answer for count questions
        if vtype == "multiplication_array" and isinstance(vdata, dict):
            rows = vdata.get("rows", 0)
            cols = vdata.get("columns", 0)
            correct = q.get("correct_answer")
            if correct is not None and rows and cols:
                try:
                    if int(str(correct).strip()) != rows * cols:
                        issues.append(
                            f"{qid}: multiplication_array {rows}x{cols}={rows * cols} "
                            f"but correct_answer='{correct}'"
                        )
                except (ValueError, TypeError):
                    pass  # non-numeric answer, skip

    return issues


def validate_cognitive_depth(
    data: dict, requested_difficulty: str
) -> list[str]:
    """For hard worksheets, ensure at least one cognitive depth question."""
    if requested_difficulty != "hard":
        return []

    questions = data.get("questions", [])
    for q in questions:
        text = q.get("text", "")
        for pattern in _COGNITIVE_DEPTH_PATTERNS.values():
            if pattern.search(text):
                return []  # Found at least one — pass

    return [
        "hard difficulty requires at least one cognitive depth question "
        "(error analysis, strategy compare, estimate-then-calculate, "
        "or missing number reasoning)"
    ]


def validate_multi_representation(
    data: dict, topic: str, skills: list[str] | None = None
) -> list[str]:
    """Ensure topic-appropriate variety of question representations."""
    issues: list[str] = []
    questions = data.get("questions", [])
    context = f"{topic} {' '.join(skills or [])}"

    # ── Multiplication topic ──
    if _MULTIPLICATION_TOPIC.search(context):
        forms: set[str] = set()
        for q in questions:
            text = q.get("text", "")
            vtype = q.get("visual_type")
            if vtype == "multiplication_array":
                forms.add("array_visual")
            if _is_computational(text) and _MULT_EQUATION_PATTERN.search(text):
                forms.add("direct_equation")
            if _WORD_PROBLEM_PATTERN.search(text):
                forms.add("word_problem")
            if _MISSING_NUMBER_PATTERN.search(text):
                forms.add("missing_number")
        if len(forms) < 2:
            issues.append(
                f"multiplication topic needs >=2 representation forms "
                f"(array_visual, direct_equation, word_problem, missing_number) "
                f"— found: {sorted(forms) or 'none'}"
            )

    # ── 3-digit addition/subtraction topic ──
    if _3DIGIT_ADDSUB_TOPIC.search(context):
        forms_3d: set[str] = set()
        for q in questions:
            text = q.get("text", "")
            vtype = q.get("visual_type")
            if _is_computational(text):
                forms_3d.add("direct_computation")
            if _WORD_PROBLEM_PATTERN.search(text):
                forms_3d.add("word_problem")
            if vtype == "number_line_jumps":
                forms_3d.add("number_line_jumps_visual")
            if _INVERSE_ERROR_PATTERN.search(text):
                forms_3d.add("inverse_or_error")
        if len(forms_3d) < 2:
            issues.append(
                f"3-digit add/sub topic needs >=2 representation forms "
                f"(direct_computation, word_problem, number_line_jumps_visual, "
                f"inverse_or_error) — found: {sorted(forms_3d) or 'none'}"
            )

    return issues


def attempt_repair(
    system_prompt: str,
    original_data: dict,
    issues: list[str],
) -> dict | None:
    """Make ONE repair call to fix validation/visual issues. Returns fixed data or None."""
    logger.warning("Attempting repair for %d issues", len(issues))
    issue_text = "\n".join(f"- {iss}" for iss in issues)
    repair_prompt = (
        f"The following worksheet JSON has issues. Fix ONLY the listed issues and "
        f"return the complete corrected JSON. No markdown.\n\n"
        f"Issues:\n{issue_text}\n\n"
        f"Original JSON:\n{json.dumps(original_data, ensure_ascii=False)}"
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": repair_prompt},
            ],
            temperature=0.3,
            max_tokens=8192,
        )
        content = clean_json_response(response.choices[0].message.content or "")
        repaired = json.loads(content)
        logger.info("Repair succeeded, got %d questions", len(repaired.get("questions", [])))
        return repaired
    except (json.JSONDecodeError, Exception) as exc:
        logger.error("Repair failed: %s", exc)
        return None


# ──────────────────────────────────────────────
# Generation endpoints
# ──────────────────────────────────────────────

@router.post("/generate", response_model=WorksheetGenerationResponse)
async def generate_worksheet(request: WorksheetGenerationRequest):
    """Generate a new worksheet based on provided parameters."""
    start_time = datetime.now()

    # Determine visual applicability (Math, Grades 1-3)
    grade_num = 0
    try:
        grade_num = int(request.grade_level.replace("Class ", ""))
    except ValueError:
        pass
    is_visual = (
        request.problem_style in ("visual", "mixed")
        and request.subject.lower() in ("maths", "mathematics", "math")
        and 1 <= grade_num <= 3
    )

    # Build v3.8 system prompt
    system_prompt = build_system_prompt(
        region=request.region,
        problem_style=request.problem_style,
        is_visual_applicable=is_visual,
        logic_tags=request.logic_tags,
    )

    # Use skills as topic context if provided
    topic_context = request.topic
    if request.skills:
        topic_context = ", ".join(request.skills)

    # Short user prompt (all rules are in system prompt)
    user_prompt = (
        f"Grade: {request.grade_level} | Subject: {request.subject} | Board: {request.board}\n"
        f"Topic/Skills: {topic_context}\n"
        f"Difficulty: {request.difficulty} | Questions: {request.num_questions} | Language: {request.language}"
    )
    if request.custom_instructions:
        user_prompt += f"\nAdditional: {request.custom_instructions}"

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=8192,
        )

        content = clean_json_response(response.choices[0].message.content or "")

        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=500, detail=f"Failed to parse AI response: {str(e)}"
            )

        logger.info(
            "Generated %d raw questions for %s / %s",
            len(data.get("questions", [])), request.subject, request.topic,
        )

        # ── Deterministic post-processing (no LLM calls) ──
        _fixup_question_types(data)
        _trim_to_count(data, request.num_questions, request.problem_style, is_visual)
        _assign_roles(data, request.difficulty)
        _fix_computational_answers(data)
        _fix_carry_borrow_difficulty(data)
        _fix_number_line_step(data)

        if is_visual:
            data, _ = enforce_visual_rules(
                data, request.problem_style, True
            )

        # ── Validate after deterministic fixes ──
        all_issues = validate_worksheet_data(
            data,
            problem_style=request.problem_style,
            is_visual_applicable=is_visual,
        )
        all_issues += _validate_roles(data, is_visual)
        all_issues += _validate_difficulty_engine(data, request.difficulty, is_visual)
        all_issues += validate_visual_integrity(
            data, request.problem_style, is_visual
        )
        all_issues += validate_cognitive_depth(data, request.difficulty)
        all_issues += validate_multi_representation(
            data, request.topic, request.skills
        )

        logger.info("Validation complete: %d issues found", len(all_issues))

        # ── Repair (one attempt) only if validation still fails ──
        if all_issues:
            repaired = attempt_repair(system_prompt, data, all_issues)
            if repaired:
                _fixup_question_types(repaired)
                _trim_to_count(repaired, request.num_questions, request.problem_style, is_visual)
                _assign_roles(repaired, request.difficulty)
                _fix_computational_answers(repaired)
                _fix_carry_borrow_difficulty(repaired)
                _fix_number_line_step(repaired)
                if is_visual:
                    repaired, _ = enforce_visual_rules(
                        repaired, request.problem_style, True
                    )
                data = repaired
            else:
                logger.warning("Repair failed — returning best-effort worksheet")

        # ── Build response models with backward-compatible defaults ──
        questions = [
            parse_question(q, i, request.difficulty)
            for i, q in enumerate(data.get("questions", []))
        ]

        worksheet = Worksheet(
            title=data.get("title", f"{request.topic} Practice Worksheet"),
            grade=request.grade_level,
            subject=request.subject,
            topic=request.topic,
            difficulty=request.difficulty.capitalize(),
            language=request.language,
            questions=questions,
            skill_focus=data.get("skill_focus", ""),
            common_mistake=data.get("common_mistake", ""),
            parent_tip=data.get("parent_tip", ""),
        )

        end_time = datetime.now()
        generation_time_ms = int((end_time - start_time).total_seconds() * 1000)

        return WorksheetGenerationResponse(
            worksheet=worksheet,
            generation_time_ms=generation_time_ms,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to generate worksheet: {str(e)}"
        )


# ──────────────────────────────────────────────
# PDF export
# ──────────────────────────────────────────────

class PDFExportRequest(BaseModel):
    worksheet: Worksheet
    pdf_type: Literal["full", "student", "answer_key"] = "full"


@router.post("/export-pdf")
async def export_worksheet_pdf(request: PDFExportRequest):
    """Export a worksheet as a PDF file."""
    try:
        # Convert Pydantic model to dict
        worksheet_dict = request.worksheet.model_dump()

        # Generate PDF
        pdf_bytes = pdf_service.generate_worksheet_pdf(
            worksheet_dict,
            pdf_type=request.pdf_type
        )

        # Create filename with type suffix
        type_suffix = f"_{request.pdf_type}" if request.pdf_type != "full" else ""
        filename = f"{request.worksheet.title.replace(' ', '_')}{type_suffix}.pdf"

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate PDF: {str(e)}")


# ──────────────────────────────────────────────
# Save / List / Get / Delete
# ──────────────────────────────────────────────

class SaveWorksheetRequest(BaseModel):
    worksheet: Worksheet
    board: str | None = None
    child_id: str | None = None
    class_id: str | None = None
    region: str | None = None


class SavedWorksheet(BaseModel):
    id: str
    user_id: str
    title: str
    board: str | None
    grade: str
    subject: str
    topic: str
    difficulty: str
    language: str
    questions: list[Question]
    created_at: str
    regeneration_count: int = 0


def get_user_id_from_token(authorization: str) -> str:
    """Extract user_id from Supabase JWT token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    token = authorization.replace("Bearer ", "")
    try:
        # Verify the token with Supabase
        user_response = supabase.auth.get_user(token)
        if not user_response or not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user_response.user.id
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")


@router.post("/save")
async def save_worksheet(
    request: SaveWorksheetRequest,
    authorization: str = Header(None)
):
    """Save a worksheet to the database."""
    user_id = get_user_id_from_token(authorization)

    try:
        # Convert questions to JSON-serializable format
        questions_data = [q.model_dump() for q in request.worksheet.questions]

        # Insert into Supabase
        result = supabase.table("worksheets").insert({
            "user_id": user_id,
            "title": request.worksheet.title,
            "board": request.board,
            "grade": request.worksheet.grade,
            "subject": request.worksheet.subject,
            "topic": request.worksheet.topic,
            "difficulty": request.worksheet.difficulty,
            "language": request.worksheet.language,
            "questions": questions_data,
            "child_id": request.child_id,
            "class_id": request.class_id,
            "region": request.region or "India",
        }).execute()

        if result.data:
            return {"success": True, "worksheet_id": result.data[0]["id"]}
        else:
            raise HTTPException(status_code=500, detail="Failed to save worksheet")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save worksheet: {str(e)}")


@router.get("/saved/list")
async def list_saved_worksheets(
    authorization: str = Header(None),
    limit: int = 20,
    offset: int = 0,
    child_id: str | None = None,
    class_id: str | None = None
):
    """List user's saved worksheets."""
    user_id = get_user_id_from_token(authorization)

    try:
        # Build query with optional child_id/class_id filter
        query = supabase.table("worksheets") \
            .select("*, children(id, name), teacher_classes(id, name)") \
            .eq("user_id", user_id)

        if child_id:
            query = query.eq("child_id", child_id)
        if class_id:
            query = query.eq("class_id", class_id)

        result = query \
            .order("created_at", desc=True) \
            .range(offset, offset + limit - 1) \
            .execute()

        worksheets = []
        for row in result.data:
            child_data = row.get("children")
            class_data = row.get("teacher_classes")
            worksheets.append({
                "id": row["id"],
                "title": row["title"],
                "board": row.get("board"),
                "grade": row["grade"],
                "subject": row["subject"],
                "topic": row["topic"],
                "difficulty": row["difficulty"],
                "language": row.get("language", "English"),
                "question_count": len(row["questions"]),
                "created_at": row["created_at"],
                "child_id": row.get("child_id"),
                "child_name": child_data.get("name") if child_data else None,
                "class_id": row.get("class_id"),
                "class_name": class_data.get("name") if class_data else None,
                "regeneration_count": row.get("regeneration_count", 0),
            })

        return {"worksheets": worksheets, "count": len(worksheets)}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list worksheets: {str(e)}")


@router.get("/saved/{worksheet_id}")
async def get_saved_worksheet(
    worksheet_id: str,
    authorization: str = Header(None)
):
    """Get a saved worksheet by ID."""
    user_id = get_user_id_from_token(authorization)

    try:
        result = supabase.table("worksheets") \
            .select("*") \
            .eq("id", worksheet_id) \
            .eq("user_id", user_id) \
            .single() \
            .execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Worksheet not found")

        row = result.data
        questions = [Question(**q) for q in row["questions"]]

        return SavedWorksheet(
            id=row["id"],
            user_id=row["user_id"],
            title=row["title"],
            board=row.get("board"),
            grade=row["grade"],
            subject=row["subject"],
            topic=row["topic"],
            difficulty=row["difficulty"],
            language=row.get("language", "English"),
            questions=questions,
            created_at=row["created_at"],
            regeneration_count=row.get("regeneration_count", 0),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get worksheet: {str(e)}")


@router.delete("/saved/{worksheet_id}")
async def delete_saved_worksheet(
    worksheet_id: str,
    authorization: str = Header(None)
):
    """Delete a saved worksheet."""
    user_id = get_user_id_from_token(authorization)

    try:
        result = supabase.table("worksheets") \
            .delete() \
            .eq("id", worksheet_id) \
            .eq("user_id", user_id) \
            .execute()

        return {"success": True, "deleted": worksheet_id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete worksheet: {str(e)}")


# ──────────────────────────────────────────────
# Subscription helpers
# ──────────────────────────────────────────────

FREE_TIER_LIMIT = 3  # worksheets per month


def check_can_generate(user_id: str) -> tuple[bool, str, dict]:
    """Check if user can generate a worksheet. Returns (can_generate, tier, subscription_data)."""
    result = supabase.table("user_subscriptions") \
        .select("*") \
        .eq("user_id", user_id) \
        .execute()

    if not result.data:
        # Create subscription if doesn't exist
        insert_result = supabase.table("user_subscriptions") \
            .insert({"user_id": user_id, "tier": "free", "worksheets_generated_this_month": 0}) \
            .execute()
        sub = insert_result.data[0] if insert_result.data else {"tier": "free", "worksheets_generated_this_month": 0}
    else:
        sub = result.data[0]

    if sub["tier"] == "paid":
        return True, "paid", sub

    remaining = FREE_TIER_LIMIT - sub.get("worksheets_generated_this_month", 0)
    return remaining > 0, "free", sub


def increment_usage(user_id: str, sub: dict) -> None:
    """Increment usage for free tier users."""
    if sub.get("tier") == "paid":
        return

    new_count = sub.get("worksheets_generated_this_month", 0) + 1
    supabase.table("user_subscriptions") \
        .update({
            "worksheets_generated_this_month": new_count,
            "updated_at": datetime.now().isoformat()
        }) \
        .eq("user_id", user_id) \
        .execute()


# ──────────────────────────────────────────────
# Regenerate
# ──────────────────────────────────────────────

@router.post("/regenerate/{worksheet_id}", response_model=WorksheetGenerationResponse)
async def regenerate_worksheet(
    worksheet_id: str,
    authorization: str = Header(None)
):
    """
    Regenerate a worksheet with the same settings.
    First regeneration is free, subsequent ones count against quota.
    """
    user_id = get_user_id_from_token(authorization)

    # Get the original worksheet
    try:
        result = supabase.table("worksheets") \
            .select("*") \
            .eq("id", worksheet_id) \
            .eq("user_id", user_id) \
            .single() \
            .execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Worksheet not found")

        original = result.data
        regeneration_count = original.get("regeneration_count", 0)

        # Check if this regeneration counts against quota
        # First regeneration is free, subsequent ones count
        if regeneration_count > 0:
            can_generate, tier, sub = check_can_generate(user_id)
            if not can_generate:
                raise HTTPException(
                    status_code=403,
                    detail="Free tier limit reached. Upgrade to Pro for unlimited worksheets."
                )

        # Generate new worksheet with same settings
        start_time = datetime.now()

        region = original.get("region", "India")
        system_prompt = build_system_prompt(region=region)

        num_questions = len(original["questions"])
        difficulty = original["difficulty"].lower()

        user_prompt = (
            f"Grade: {original['grade']} | Subject: {original['subject']} "
            f"| Board: {original.get('board', 'CBSE')}\n"
            f"Topic: {original['topic']}\n"
            f"Difficulty: {difficulty} | Questions: {num_questions} "
            f"| Language: {original.get('language', 'English')}\n"
            f"Generate completely NEW questions (different from before)."
        )

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.8,  # Slightly higher for more variety
            max_tokens=8192,
        )

        content = clean_json_response(response.choices[0].message.content or "")

        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=500, detail=f"Failed to parse AI response: {str(e)}"
            )

        # Deterministic post-processing
        _fixup_question_types(data)
        _trim_to_count(data, num_questions, "standard", False)
        _assign_roles(data, difficulty)
        _fix_computational_answers(data)
        _fix_carry_borrow_difficulty(data)
        _fix_number_line_step(data)

        # Validate after deterministic fixes
        validation_issues = validate_worksheet_data(data)
        validation_issues += _validate_roles(data, False)
        validation_issues += _validate_difficulty_engine(data, difficulty, False)
        validation_issues += validate_visual_integrity(data)
        validation_issues += validate_cognitive_depth(data, difficulty)
        validation_issues += validate_multi_representation(data, original["topic"])

        logger.info("Regenerate validation: %d issues", len(validation_issues))

        if validation_issues:
            repaired = attempt_repair(system_prompt, data, validation_issues)
            if repaired:
                _fixup_question_types(repaired)
                _trim_to_count(repaired, num_questions, "standard", False)
                _assign_roles(repaired, difficulty)
                _fix_computational_answers(repaired)
                _fix_carry_borrow_difficulty(repaired)
                _fix_number_line_step(repaired)
                data = repaired
            else:
                logger.warning("Regenerate repair failed — returning best-effort")

        # Build questions with backward-compatible defaults
        questions = [
            parse_question(q, i, difficulty)
            for i, q in enumerate(data.get("questions", []))
        ]

        worksheet = Worksheet(
            title=data.get("title", f"{original['topic']} Practice Worksheet"),
            grade=original["grade"],
            subject=original["subject"],
            topic=original["topic"],
            difficulty=original["difficulty"],
            language=original.get("language", "English"),
            questions=questions,
            skill_focus=data.get("skill_focus", ""),
            common_mistake=data.get("common_mistake", ""),
            parent_tip=data.get("parent_tip", ""),
        )

        # Increment regeneration count on original worksheet
        supabase.table("worksheets") \
            .update({
                "regeneration_count": regeneration_count + 1,
                "updated_at": datetime.now().isoformat()
            }) \
            .eq("id", worksheet_id) \
            .execute()

        # Increment usage if this wasn't free (regeneration_count > 0)
        if regeneration_count > 0:
            _, _, sub = check_can_generate(user_id)
            increment_usage(user_id, sub)

        end_time = datetime.now()
        generation_time_ms = int((end_time - start_time).total_seconds() * 1000)

        return WorksheetGenerationResponse(
            worksheet=worksheet,
            generation_time_ms=generation_time_ms,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to regenerate worksheet: {str(e)}"
        )


# ──────────────────────────────────────────────
# Analytics
# ──────────────────────────────────────────────

@router.get("/analytics")
async def get_teacher_analytics(authorization: str = Header(None)):
    """Get light analytics for a teacher: total worksheets, topic reuse, active weeks."""
    user_id = get_user_id_from_token(authorization)

    try:
        result = supabase.table("worksheets") \
            .select("topic, subject, created_at") \
            .eq("user_id", user_id) \
            .execute()

        rows = result.data or []
        total_worksheets = len(rows)

        if total_worksheets == 0:
            return {
                "total_worksheets": 0,
                "topic_reuse_rate": 0,
                "active_weeks": 0,
                "subjects_covered": 0,
                "top_topics": [],
            }

        # Topic frequency
        topic_counts: dict[str, int] = {}
        for row in rows:
            t = row.get("topic", "Unknown")
            topic_counts[t] = topic_counts.get(t, 0) + 1

        # Topic reuse rate = worksheets on repeated topics / total
        repeated = sum(c for c in topic_counts.values() if c > 1)
        topic_reuse_rate = round(repeated / total_worksheets, 2) if total_worksheets else 0

        # Top 5 most-used topics
        top_topics = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        top_topics_list = [{"topic": t, "count": c} for t, c in top_topics]

        # Active weeks (distinct ISO weeks)
        weeks = set()
        for row in rows:
            created = row.get("created_at", "")
            try:
                dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                weeks.add(dt.isocalendar()[:2])  # (year, week)
            except (ValueError, AttributeError):
                pass

        # Distinct subjects
        subjects = set(row.get("subject", "") for row in rows)

        return {
            "total_worksheets": total_worksheets,
            "topic_reuse_rate": topic_reuse_rate,
            "active_weeks": len(weeks),
            "subjects_covered": len(subjects),
            "top_topics": top_topics_list,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get analytics: {str(e)}")
