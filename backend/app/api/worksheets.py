from fastapi import APIRouter, HTTPException, Header, Response
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
from app.services.slot_engine import (
    run_slot_pipeline, hydrate_visuals, enforce_visuals_only,
    build_worksheet_plan, enrich_error_spots, grade_student_answer,
    explain_question, recommend_next_step, chain_drill_session,
    attempt_and_next, get_learning_objectives,
)
from app.services.mastery_dashboard import get_mastery, topic_summary, reset_skill
from app.api.models_practice import AttemptResponse, MasteryGetResponse, TopicSummaryResponse, ResetResponse
from app.services.telemetry import instrument

router = APIRouter(prefix="/api/worksheets", tags=["worksheets"])
pdf_service = get_pdf_service()

settings = get_settings()
client = OpenAI(api_key=settings.openai_api_key)
supabase = create_client(settings.supabase_url, settings.supabase_service_key)

logger = logging.getLogger("practicecraft.worksheets")

# ── Skill routing: UI topic strings → internal contract keys ──
UI_SKILL_TO_CONTRACTS: dict[str, list[str]] = {
    "Multiplication tables (2\u201310)": ["multiplication_table_recall"],
    "Multiplication tables (2-10)": ["multiplication_table_recall"],
    # NOTE: "Addition and subtraction (3-digit)" intentionally NOT here.
    # The combined topic uses slot_engine's TOPIC_PROFILES recipe to mix
    # add/sub questions in a single worksheet (not split into 2 bundles).
}

CONTRACT_TOPIC_LABEL: dict[str, str] = {
    "column_add_with_carry": "3-digit addition (with carry)",
    "column_sub_with_borrow": "3-digit subtraction (with borrow)",
    "multiplication_table_recall": "Multiplication tables (2\u201310)",
}


class MixRecipeItem(BaseModel):
    skill_tag: str
    count: int
    visual_type: str | None = None
    require_student_answer: bool = False
    unique_contexts: bool = False


class WorksheetConstraints(BaseModel):
    carry_required: bool = False
    allow_operations: list[str] | None = None


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
    # v7.0: focused worksheet controls
    focus_skill: str | None = None
    support_skills: list[str] | None = None
    mix_recipe: list[MixRecipeItem] | None = None
    constraints: WorksheetConstraints | None = None
    visuals_only: bool = False
    min_visual_ratio: float | None = None
    child_id: str | None = None  # Gold-G2: mastery-aware slot adjustment


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
    learning_objectives: list[str] = []
    mastery_snapshot: dict | None = None  # Gold-G2: child's mastery state at generation time


class WorksheetGenerationResponse(BaseModel):
    worksheet: Worksheet
    generation_time_ms: int
    warnings: dict | None = None
    verdict: str = "ok"
    worksheets: list[Worksheet] | None = None


class GradeRequest(BaseModel):
    question: dict
    student_answer: str


class ExplainRequest(BaseModel):
    question: dict


class RecommendRequest(BaseModel):
    question: dict
    grade_result: dict


class DrillRequest(BaseModel):
    question: dict
    student_answer: str


class ChainRequest(BaseModel):
    root_question: dict
    attempts: list[dict]
    target_streak: int = 3


class AttemptPayload(BaseModel):
    question: dict
    student_answer: str
    mode: str = "single"
    root_question: dict | None = None
    attempts: list[dict] = []
    target_streak: int = 3
    student_id: str | None = None


# ──────────────────────────────────────────────
# v3.8 System Prompt Builder
# ──────────────────────────────────────────────

# DEAD: not called from main pipeline [2026-02-17]
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

CONTENT DOCTRINE (MANDATORY — follow this cognitive taxonomy):
1. Recognition (20%) — direct recall, identify, single-step. Easy difficulty.
2. Application (40%) — word problems, use skills in real-world context. Names, scenarios, exact answers.
3. Representation (20%) — show/model with visuals, diagrams, or alternate representations.
4. Error Detection (10%) — "find the mistake", misconception spotting, true/false with common errors.
5. Thinking (10%) — reasoning, explain why, compare, pattern, multi-step.

At least ONE question must be Error Detection (misconception). This is mandatory.

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

VISUAL ALIGNMENT (STRICT — follow exactly):
1. If question text mentions "array", "rows", "columns", or "grid" → visual_type MUST be "multiplication_array".
2. If the question involves multiplication AND is visual → use multiplication_array (or object_group if factors ≤ 10 and product ≤ 20). Do NOT use number_line for multiplication visuals.
3. For addition/subtraction visuals → prefer number_line_jumps. Jumps array must be consistent: start + sum(jumps) == end. Use negative jumps for subtraction.
4. NEVER use a highlight-only number_line (just start/end/highlight with no jumps) as a visual for multi-step or multiplication problems. It provides no conceptual value.
5. multiplication_array: rows × cols MUST equal the correct_answer for total-count questions.

Drawable constraints:
- object_group counts MUST NOT exceed 20 per group. For larger numbers use number_line instead.
- object_group labels must be simple, drawable nouns (e.g. "apples", "stars", "balls"). Avoid compound phrases.
- multiplication_array: rows × cols must not exceed 20. For larger products use number_line.

Formats:
- clock: {{ "hour": 1-12, "minute": 0|5|10|...|55 }}
- number_line: {{ "start": int, "end": int, "step": int, "highlight": int }}
- number_line_jumps: {{ "start": int, "jumps": [int, int, ...], "end": int }}
  RULE: start + sum(jumps) == end. Use negative integers in jumps for subtraction.
  Example addition: {{ "start": 123, "jumps": [200, 30, 4], "end": 357 }}
  Example subtraction: {{ "start": 512, "jumps": [-200, -70, -9], "end": 233 }}
- multiplication_array: {{ "rows": int, "cols": int, "label": "dots" }}
  RULE: rows * cols must match the correct_answer. Use "cols" NOT "columns".
- object_group: {{ "groups": [{{"count": 1-20, "label": "apples"}}], "operation": "+"|"-"|"x" }}
  For multiplication ("x"), prefer multiplication_array when both factors ≤ 10 and product ≤ 20.
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
- "role": one of recognition, application, representation, error_detection, thinking
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
      "role": "recognition" | "application" | "representation" | "error_detection" | "thinking",
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


# DEAD: not called from main pipeline [2026-02-17]
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


# DEAD: not called from main pipeline [2026-02-17]
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


# DEAD: not called from main pipeline [2026-02-17]
def _fix_inconsistent_visuals(data: dict) -> None:
    """Fail-safe: null out broken visuals; migrate old schemas to current format."""
    for q in data.get("questions", []):
        vtype = q.get("visual_type")
        vdata = q.get("visual_data")

        # visual_type set but visual_data missing/not-dict → null both
        if vtype and not isinstance(vdata, dict):
            q["visual_type"] = None
            q["visual_data"] = None
            continue

        if not vtype or not isinstance(vdata, dict):
            continue

        # number_line_jumps: must have "jumps" array (migrate old schema if needed)
        if vtype == "number_line_jumps":
            if isinstance(vdata.get("jumps"), list) and len(vdata["jumps"]) > 0:
                pass  # already correct schema
            elif vdata.get("jump_size") and vdata.get("num_jumps"):
                # Migrate old {jump_size, num_jumps, result} → {jumps[], end}
                js = vdata["jump_size"]
                nj = vdata["num_jumps"]
                start = vdata.get("start", 0)
                result = vdata.get("result")
                # Determine if subtraction (result < start)
                if result is not None and result < start:
                    jumps_list = [-abs(js)] * nj
                else:
                    jumps_list = [abs(js)] * nj
                end = start + sum(jumps_list)
                q["visual_data"] = {
                    "start": start,
                    "jumps": jumps_list,
                    "end": end,
                }
            else:
                q["visual_type"] = None
                q["visual_data"] = None

        # multiplication_array: must have rows > 0 and cols > 0 (migrate "columns" → "cols")
        elif vtype == "multiplication_array":
            # Migrate "columns" → "cols" if needed
            if "columns" in vdata and "cols" not in vdata:
                vdata["cols"] = vdata.pop("columns")
            if not (vdata.get("rows") and vdata.get("cols")):
                q["visual_type"] = None
                q["visual_data"] = None

        # number_line: must have start, end, step
        elif vtype == "number_line":
            if vdata.get("end", 0) <= vdata.get("start", 0):
                q["visual_type"] = None
                q["visual_data"] = None

        # object_group: must have groups list
        elif vtype == "object_group":
            if not isinstance(vdata.get("groups"), list) or not vdata["groups"]:
                q["visual_type"] = None
                q["visual_data"] = None

        # clock: must have hour
        elif vtype == "clock":
            if not vdata.get("hour"):
                q["visual_type"] = None
                q["visual_data"] = None


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

    has_thinking = any(q.get("role") == "thinking" for q in questions)
    has_error_detection = any(q.get("role") == "error_detection" for q in questions)
    has_application = any(q.get("role") == "application" for q in questions)
    has_representation = any(
        q.get("role") == "representation" and q.get("visual_type")
        for q in questions
    )

    if not has_thinking:
        issues.append("hard difficulty requires at least one thinking (multi-step/reasoning) problem")
    if not has_error_detection:
        issues.append("hard difficulty requires at least one error_detection (misconception) problem")
    if not has_application:
        issues.append("hard difficulty requires at least one application (word problem) problem")
    if is_visual_applicable and not has_representation:
        issues.append("hard difficulty requires at least one representation with visual")

    return issues


# ──────────────────────────────────────────────
# Phase 4: Pedagogical Role Engine
# ──────────────────────────────────────────────

_DOCTRINE_TYPES = ["recognition", "application", "representation", "error_detection", "thinking"]
_DOCTRINE_WEIGHTS = {"recognition": 0.20, "application": 0.40, "representation": 0.20, "error_detection": 0.10, "thinking": 0.10}
_VALID_ROLES = set(_DOCTRINE_TYPES)

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

_ERROR_DETECTION_PATTERN = re.compile(
    r"(find the (mistake|error)|which is (wrong|incorrect)|correct the|spot the error"
    r"|true or false|is this correct|what is wrong)",
    re.IGNORECASE,
)


def _build_role_sequence(n: int) -> list[str]:
    """Build a role sequence for n questions using Content Doctrine weights.

    Uses largest-remainder proportional allocation to distribute n slots
    across the 5 doctrine types. Guarantees at least 1 error_detection
    (mandatory misconception question).

    Output order: recognition → application → representation →
    error_detection → thinking (progressive cognitive demand).
    """
    if n <= 0:
        return []

    # Compute ideal (fractional) counts, then floor
    ideal = {t: _DOCTRINE_WEIGHTS[t] * n for t in _DOCTRINE_TYPES}
    floored = {t: int(ideal[t]) for t in _DOCTRINE_TYPES}
    remainders = {t: ideal[t] - floored[t] for t in _DOCTRINE_TYPES}

    # Distribute leftover seats by largest fractional remainder
    leftover = n - sum(floored.values())
    for t in sorted(remainders, key=remainders.get, reverse=True):
        if leftover <= 0:
            break
        floored[t] += 1
        leftover -= 1

    # Enforce mandatory misconception: error_detection >= 1
    if floored["error_detection"] < 1 and n >= 1:
        # Steal one seat from the largest bucket (skip error_detection)
        donor = max(
            (t for t in _DOCTRINE_TYPES if t != "error_detection"),
            key=lambda t: floored[t],
        )
        floored[donor] -= 1
        floored["error_detection"] = 1

    # Build flat sequence in progressive-difficulty order
    seq: list[str] = []
    for t in _DOCTRINE_TYPES:
        seq.extend([t] * floored[t])

    return seq[:n]


def _assign_roles(data: dict, difficulty: str) -> None:
    """Deterministically assign Content Doctrine roles to questions in-place."""
    questions = data.get("questions", [])
    n = len(questions)
    roles = _build_role_sequence(n)

    for q, role in zip(questions, roles):
        q["role"] = role
        # Enforce difficulty alignment per doctrine type
        if role == "recognition":
            q["difficulty"] = "easy"
        elif role == "error_detection":
            if q.get("difficulty") == "easy":
                q["difficulty"] = "medium"
        elif role == "thinking":
            q["difficulty"] = "hard" if difficulty == "hard" else "medium"


def _validate_roles(data: dict, is_visual_applicable: bool) -> list[str]:
    """Validate that each question satisfies its Content Doctrine role constraints."""
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

        if role == "recognition":
            # Direct recall / single-step, must have correct_answer
            if correct is None:
                issues.append(
                    f"{qid} (recognition): must have correct_answer"
                )

        elif role == "application":
            # Real-world context or skill application, must have correct_answer
            if not _WORD_PROBLEM_PATTERN.search(text) and not _is_computational(text):
                issues.append(
                    f"{qid} (application): must include real-world context "
                    f"(names, buying, giving, etc.) or skill application"
                )
            if correct is None:
                issues.append(
                    f"{qid} (application): must have exact correct_answer"
                )

        elif role == "representation":
            # When visual mode is active, must include visual_type + visual_data
            if is_visual_applicable and not has_visual:
                issues.append(
                    f"{qid} (representation): must include visual_type + visual_data"
                )

        elif role == "error_detection":
            # Must contain error-finding / misconception language
            if not _ERROR_DETECTION_PATTERN.search(text):
                issues.append(
                    f"{qid} (error_detection): must contain error-finding language "
                    f"(find the mistake, which is wrong, true or false, etc.)"
                )

        elif role == "thinking":
            # Should not be pure arithmetic — must involve reasoning
            if _is_computational(text) and not _REASONING_PATTERN.search(text):
                issues.append(
                    f"{qid} (thinking): should not be pure arithmetic — "
                    f"use reasoning, comparison, pattern, or multi-step"
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
            cols = vdata.get("cols", 0)
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
            cols = q["visual_data"].get("cols", 0)
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
            and not isinstance(vdata.get("jumps"), list)
        ):
            issues.append(
                f"{qid}: multiplication uses number_line highlight-only "
                f"— prefer multiplication_array"
            )

        # 4. number_line_jumps: internal consistency (start + sum(jumps) == end)
        if vtype == "number_line_jumps" and isinstance(vdata, dict):
            jumps = vdata.get("jumps")
            if isinstance(jumps, list) and len(jumps) > 0:
                start = vdata.get("start", 0)
                end = vdata.get("end")
                expected_end = start + sum(jumps)
                if end is not None and end != expected_end:
                    issues.append(
                        f"{qid}: number_line_jumps start({start}) + sum({jumps})"
                        f"={expected_end} but end={end}"
                    )
            else:
                issues.append(
                    f"{qid}: number_line_jumps missing 'jumps' array"
                )

        # 5. multiplication_array: rows*cols must match correct_answer for count questions
        if vtype == "multiplication_array" and isinstance(vdata, dict):
            rows = vdata.get("rows", 0)
            cols = vdata.get("cols", 0)
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
# Slot-engine → API response mapper
# ──────────────────────────────────────────────

# Map slot-engine format → API question type
_FORMAT_TO_QTYPE: dict[str, str] = {
    "column_setup": "short_answer",
    "place_value": "fill_blank",
    "simple_identify": "fill_blank",
    "direct_compute": "fill_blank",
    "word_problem": "short_answer",
    "missing_number": "fill_blank",
    "estimation": "short_answer",
    "error_spot": "short_answer",
    "compare_solutions": "short_answer",
    "create_example": "short_answer",
    "thinking": "short_answer",
}


# Shim: map hydrated model_ids → frontend visual_type keys
_MODEL_TO_VTYPE: dict[str, str] = {
    "NUMBER_LINE": "number_line",
    "BASE_TEN_REGROUPING": "base_ten_regrouping",
    "PIE_FRACTION": "pie_fraction",
    "GRID_SYMMETRY": "grid_symmetry",
    "MONEY_COINS": "money_coins",
    "PATTERN_TILES": "pattern_tiles",
    "ABACUS": "abacus",
}


def _map_visual_fields(q: dict) -> tuple:
    """Map hydrated visual fields (representation/visual_spec) → frontend visual_type + visual_data."""
    if q.get("representation") != "PICTORIAL_MODEL":
        return None, None
    spec = q.get("visual_spec")
    if not spec or not spec.get("model_id"):
        return None, None

    model_id = spec["model_id"]
    vtype = _MODEL_TO_VTYPE.get(model_id)
    if not vtype:
        return None, None

    # Translate field names for frontend compatibility
    if model_id == "NUMBER_LINE":
        markers = spec.get("markers", [])
        return vtype, {
            "start": spec.get("start", 0),
            "end": spec.get("end", 100),
            "step": spec.get("tick_interval", 10),
            "highlight": markers[1] if len(markers) >= 2 else None,
        }

    # Default: pass through (strip model_id)
    return vtype, {k: v for k, v in spec.items() if k != "model_id"}


def _fill_role_explanations(questions: list[Question]) -> None:
    """Add short deterministic explanations for thinking and error_detection roles only."""
    for q in questions:
        if q.role not in ("thinking", "error_detection"):
            continue
        if q.explanation and q.explanation.strip():
            # Already has one (e.g. from normalize_error_spot_answers)
            q.explanation = q.explanation[:160]
            continue

        text = (q.text or "").lower()
        answer = q.correct_answer or ""

        if q.role == "thinking":
            # Estimation explanations
            if "nearest 100" in text or "nearest hundred" in text:
                q.explanation = f"Round each number to the nearest 100, then add the rounded values. The estimated answer is {answer}."
            elif "nearest 10" in text or "nearest ten" in text:
                q.explanation = f"Round each number to the nearest 10, then add the rounded values. The estimated answer is {answer}."
            elif "closer" in text:
                q.explanation = f"Add the numbers and check which reference value is nearest. The answer is {answer}."
            elif "compar" in text:
                q.explanation = "Compare both methods step by step and check which gives the correct result."
            else:
                q.explanation = f"Think through each step carefully. The answer is {answer}."

        elif q.role == "error_detection":
            if "+" in text or "add" in text:
                q.explanation = f"Re-add column by column with correct carrying. The correct answer is {answer}."
            elif "-" in text or "subtract" in text:
                q.explanation = f"Re-subtract column by column with correct borrowing. The correct answer is {answer}."
            elif "\u00d7" in text or "x " in text or "times" in text:
                q.explanation = f"Recalculate the product. The correct answer is {answer}."
            else:
                q.explanation = f"Redo the calculation carefully. The correct answer is {answer}."

        # Hard cap
        if q.explanation and len(q.explanation) > 160:
            q.explanation = q.explanation[:157] + "..."


def _slot_to_question(q: dict, idx: int) -> Question:
    """Convert a slot-engine question dict to the API Question model."""
    fmt = q.get("format", "")
    text = q.get("question_text", "")
    answer = q.get("answer")
    answer_str = str(answer).strip() if answer is not None and str(answer).strip() else None

    q_type = _FORMAT_TO_QTYPE.get(fmt, "short_answer")
    vtype, vdata = _map_visual_fields(q)

    return Question(
        id=f"q{idx + 1}",
        type=q_type,
        text=text,
        options=None,
        correct_answer=answer_str,
        explanation=q.get("explanation"),
        difficulty=q.get("difficulty"),
        answer_type="exact" if answer_str else "example",
        sample_answer=None,
        grading_notes=None,
        visual_type=vtype,
        visual_data=vdata,
        role=q.get("slot_type"),
        skill_tag=q.get("skill_tag") or fmt,
    )


# ──────────────────────────────────────────────
# Generation endpoints
# ──────────────────────────────────────────────

@router.post("/generate", response_model=WorksheetGenerationResponse)
@instrument(route="/api/worksheets/generate", version="legacy")
async def generate_worksheet(
    request: WorksheetGenerationRequest,
    authorization: str = Header(None),
):
    """Generate a new worksheet using slot-based pipeline."""
    start_time = datetime.now()

    # ── Subscription enforcement ──
    if authorization:
        try:
            user_id = get_user_id_from_token(authorization)
            from app.services.subscription_check import check_and_increment_usage
            usage = await check_and_increment_usage(user_id, supabase)
            if not usage["allowed"]:
                raise HTTPException(
                    status_code=402,
                    detail={
                        "detail": usage["message"],
                        "worksheets_remaining": 0,
                        "tier": usage["tier"],
                    },
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.warning("Subscription check failed (fail-open): %s", e)

    try:
        # ── v1.3: Multi-skill bundle ──
        # Expand UI skill labels into individual contract keys
        _expanded: list[tuple[str, str | None, str]] = []  # (topic_for_pipeline, forced_contract_key)
        if request.skills:
            for sk in request.skills:
                if not sk or not sk.strip():
                    raise HTTPException(status_code=422, detail="skill_topic must not be empty")
                contracts = UI_SKILL_TO_CONTRACTS.get(sk)
                if contracts:
                    for ck in contracts:
                        _expanded.append((CONTRACT_TOPIC_LABEL.get(ck, sk), ck, sk))
                else:
                    _expanded.append((sk, None, sk))

        if len(_expanded) >= 2:
            k = len(_expanded)
            n = request.num_questions
            base, rem = divmod(n, k)
            per_skill = [base + (1 if i < rem else 0) for i in range(k)]

            constraints_dict = request.constraints.model_dump() if request.constraints else None
            visuals_only = request.visuals_only or request.problem_style == "visual"
            min_visual_ratio = request.min_visual_ratio
            if min_visual_ratio is None and visuals_only:
                min_visual_ratio = 0.8

            bundled: list[Worksheet] = []
            all_warnings: list[str] = []

            for idx, (skill_topic, forced_contract, original_skill) in enumerate(_expanded):
                q_count = per_skill[idx]
                if q_count < 1:
                    continue

                worksheet_plan = None
                # Only trigger carry/borrow worksheet plan for 3-digit+ topics.
                # Class 1 and Class 2 topics contain "addition"/"subtraction" but must NOT
                # use the 3-digit carry plan — they have their own c1_/c2_ skill profiles.
                _is_class12_topic = any(m in skill_topic.lower() for m in ("class 1", "class 2", "up to 20", "within 20", "2-digit"))
                if request.mix_recipe or (not _is_class12_topic and any(kw in skill_topic.lower() for kw in ("3-digit", "3 digit", "addition", "subtraction"))):
                    recipe_dicts = [item.model_dump() for item in request.mix_recipe] if request.mix_recipe else None
                    worksheet_plan = build_worksheet_plan(
                        q_count=q_count,
                        mix_recipe=recipe_dicts,
                        constraints=constraints_dict,
                        topic=original_skill,
                    )

                meta, slot_questions = run_slot_pipeline(
                    client=client,
                    grade=request.grade_level,
                    subject=request.subject,
                    topic=original_skill,
                    q_count=q_count,
                    difficulty=request.difficulty,
                    region=request.region,
                    language=request.language,
                    worksheet_plan=worksheet_plan,
                    constraints=constraints_dict,
                    child_id=request.child_id,
                )

                # ── Skill purity enforcement ──
                if forced_contract:
                    import app.skills.registry as _skills_reg
                    contract = _skills_reg.SKILL_REGISTRY.get(forced_contract)
                    _rng = __import__("random").Random(idx)
                    for qi, q in enumerate(slot_questions):
                        q["skill_tag"] = forced_contract
                        # Replace off-topic questions via contract repair
                        if contract:
                            off_topic = False
                            text = q.get("question_text", "")
                            vdata = q.get("visual_spec") or {}
                            if forced_contract == "multiplication_table_recall":
                                off_topic = (
                                    vdata.get("operation") == "addition"
                                    or "+" in text
                                    or not any(c in text for c in ("\u00d7", "x", "*", "times"))
                                )
                            if off_topic:
                                q = contract.repair(q, _rng)
                                q["skill_tag"] = forced_contract
                                q["id"] = qi + 1
                                q.pop("visual_spec", None)
                                q.pop("representation", None)
                                q.pop("visual_model_ref", None)
                                slot_questions[qi] = q
                                logger.info("Purity fix q%d: replaced off-topic with %s", qi + 1, forced_contract)

                hydrate_visuals(slot_questions, visuals_only=visuals_only)
                if visuals_only:
                    enforce_visuals_only(slot_questions, min_ratio=min_visual_ratio or 0.8)

                questions = [_slot_to_question(q, i) for i, q in enumerate(slot_questions)]
                _fill_role_explanations(questions)
                common_mistakes = meta.get("common_mistakes") or []

                ws = Worksheet(
                    title=f"{meta.get('micro_skill', skill_topic)} - Practice",
                    grade=request.grade_level,
                    subject=request.subject,
                    topic=original_skill,
                    difficulty=meta.get("difficulty", request.difficulty).capitalize(),
                    language=request.language,
                    questions=questions,
                    skill_focus=meta.get("skill_focus", ""),
                    common_mistake=common_mistakes[0] if common_mistakes else "",
                    parent_tip=meta.get("parent_tip", ""),
                    learning_objectives=get_learning_objectives(skill_topic),
                    mastery_snapshot=meta.get("mastery_snapshot"),
                )
                bundled.append(ws)

                raw_warnings = meta.pop("_warnings", None) or {}
                q_warns = raw_warnings.get("question_level") or []
                ws_warns = raw_warnings.get("worksheet_level") or []
                all_warnings.extend(f"[{skill_topic}] {w}" for w in q_warns + ws_warns)

            end_time = datetime.now()
            generation_time_ms = int((end_time - start_time).total_seconds() * 1000)

            return WorksheetGenerationResponse(
                worksheet=bundled[0],
                worksheets=bundled,
                generation_time_ms=generation_time_ms,
                warnings={"bundle": all_warnings, "skills": request.skills, "counts": per_skill} if all_warnings else None,
                verdict="best_effort" if all_warnings else "ok",
            )

        # ── Single-skill path ──

        # Focus skill inference (v7.0)
        focus_skill = request.focus_skill
        if not focus_skill and request.skills:
            for s in request.skills:
                if any(kw in s.lower() for kw in ("addition", "subtraction")):
                    focus_skill = s
                    break
            if not focus_skill:
                focus_skill = request.skills[0]

        # Narrow skills when list is too broad + mixed
        effective_topic = request.topic
        if focus_skill:
            effective_topic = focus_skill
        if request.skills and len(request.skills) > 2 and request.problem_style == "mixed":
            logger.info("Narrowing %d skills to focus=%s", len(request.skills), focus_skill)

        # ── Build worksheet plan (v7.0) ──
        constraints_dict = None
        if request.constraints:
            constraints_dict = request.constraints.model_dump()

        worksheet_plan = None
        # Only trigger carry/borrow worksheet plan for 3-digit+ topics.
        # Guard against Class 1/2 topics which have their own skill profiles.
        _focus_lower = (focus_skill or "").lower()
        _is_class12_focus = any(m in _focus_lower for m in ("class 1", "class 2", "up to 20", "within 20", "2-digit"))
        use_plan = request.mix_recipe is not None or (
            focus_skill and not _is_class12_focus and any(kw in _focus_lower for kw in ("3-digit", "3 digit", "addition", "subtraction"))
        )
        if use_plan:
            recipe_dicts = None
            if request.mix_recipe:
                recipe_dicts = [item.model_dump() for item in request.mix_recipe]
            worksheet_plan = build_worksheet_plan(
                q_count=request.num_questions,
                mix_recipe=recipe_dicts,
                constraints=constraints_dict,
                topic=effective_topic,
            )
            logger.info(
                "Worksheet plan: %d slots, recipe=%s",
                len(worksheet_plan),
                "custom" if request.mix_recipe else "default",
            )

        meta, slot_questions = run_slot_pipeline(
            client=client,
            grade=request.grade_level,
            subject=request.subject,
            topic=effective_topic,
            q_count=request.num_questions,
            difficulty=request.difficulty,
            region=request.region,
            language=request.language,
            worksheet_plan=worksheet_plan,
            constraints=constraints_dict,
            child_id=request.child_id,
        )

        # Safety net: ensure visual hydration ran (idempotent if already done)
        visuals_only = request.visuals_only or request.problem_style == "visual"
        min_visual_ratio = request.min_visual_ratio
        if min_visual_ratio is None and visuals_only:
            min_visual_ratio = 0.8

        hydrate_visuals(slot_questions, visuals_only=visuals_only)
        if visuals_only:
            enforce_visuals_only(slot_questions, min_ratio=min_visual_ratio or 0.8)

        # Map slot-engine output → API Question models
        questions = [_slot_to_question(q, i) for i, q in enumerate(slot_questions)]
        _fill_role_explanations(questions)

        # Dev assertion: detect visual propagation failures
        _RE_3DIGIT = re.compile(r"\b\d{3}\b")
        for _i, _q in enumerate(questions):
            _t = _q.text or ""
            if "column" in _t.lower() and "+" in _t and len(_RE_3DIGIT.findall(_t)) >= 2 and _q.visual_type is None:
                logger.error(
                    "VISUAL_BUG q%d: column+addition with 3-digit numbers but visual_type=null | text=%.80s",
                    _i + 1, _t,
                )

        common_mistakes = meta.get("common_mistakes") or []
        worksheet = Worksheet(
            title=f"{meta.get('micro_skill', effective_topic)} - Practice",
            grade=request.grade_level,
            subject=request.subject,
            topic=effective_topic,
            difficulty=meta.get("difficulty", request.difficulty).capitalize(),
            language=request.language,
            questions=questions,
            skill_focus=meta.get("skill_focus", ""),
            common_mistake=common_mistakes[0] if common_mistakes else "",
            parent_tip=meta.get("parent_tip", ""),
            learning_objectives=get_learning_objectives(effective_topic),
            mastery_snapshot=meta.get("mastery_snapshot"),
        )

        end_time = datetime.now()
        generation_time_ms = int((end_time - start_time).total_seconds() * 1000)

        # Surface validation warnings as best-effort verdict
        raw_warnings = meta.pop("_warnings", None) or {}
        q_warns = raw_warnings.get("question_level") or []
        ws_warns = raw_warnings.get("worksheet_level") or []
        has_warnings = bool(q_warns or ws_warns)

        return WorksheetGenerationResponse(
            worksheet=worksheet,
            generation_time_ms=generation_time_ms,
            warnings={"question_level": q_warns, "worksheet_level": ws_warns} if has_warnings else None,
            verdict="best_effort" if has_warnings else "ok",
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

@router.post("/grade")
@instrument(route="/api/worksheets/grade", version="legacy")
def grade(req: GradeRequest, response: Response):
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "2026-06-01"
    response.headers["Link"] = '</api/v1/worksheets/grade>; rel="successor-version"'
    return grade_student_answer(req.question, req.student_answer)


@router.post("/explain")
@instrument(route="/api/worksheets/explain", version="legacy")
def explain(req: ExplainRequest, response: Response):
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "2026-06-01"
    response.headers["Link"] = '</api/v1/worksheets/explain>; rel="successor-version"'
    return explain_question(req.question)


@router.post("/recommend")
@instrument(route="/api/worksheets/recommend", version="legacy")
def recommend(req: RecommendRequest, response: Response):
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "2026-06-01"
    response.headers["Link"] = '</api/v1/worksheets/recommend>; rel="successor-version"'
    return recommend_next_step(req.question, req.grade_result)


@router.post("/drill")
@instrument(route="/api/worksheets/drill", version="legacy")
def drill(req: DrillRequest, response: Response):
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "2026-06-01"
    response.headers["Link"] = '</api/v1/worksheets/drill>; rel="successor-version"'
    from app.services.slot_engine import generate_isolation_drill
    return generate_isolation_drill(req.question, req.student_answer)


@router.post("/chain")
@instrument(route="/api/worksheets/chain", version="legacy")
def chain(req: ChainRequest, response: Response):
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "2026-06-01"
    response.headers["Link"] = '</api/v1/worksheets/chain>; rel="successor-version"'
    return chain_drill_session(req.root_question, req.attempts, req.target_streak)


@router.post("/attempt", response_model=AttemptResponse)
@instrument(route="/api/worksheets/attempt", version="legacy")
def attempt(req: AttemptPayload, response: Response):
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "2026-06-01"
    response.headers["Link"] = '</api/v1/worksheets/attempt>; rel="successor-version"'
    return attempt_and_next(req.model_dump())


@router.get("/mastery/get", response_model=MasteryGetResponse)
@instrument(route="/api/worksheets/mastery/get", version="legacy")
def mastery_get(student_id: str, response: Response):
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "2026-06-01"
    response.headers["Link"] = '</api/v1/worksheets/mastery/get>; rel="successor-version"'
    return {"student_id": student_id, "states": get_mastery(student_id)}


@router.get("/mastery/topic_summary", response_model=TopicSummaryResponse)
@instrument(route="/api/worksheets/mastery/topic_summary", version="legacy")
def mastery_topic_summary(student_id: str, topic: str, response: Response):
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "2026-06-01"
    response.headers["Link"] = '</api/v1/worksheets/mastery/topic_summary>; rel="successor-version"'
    return topic_summary(student_id, topic)


class MasteryResetRequest(BaseModel):
    student_id: str
    skill_tag: str


@router.post("/mastery/reset", response_model=ResetResponse)
@instrument(route="/api/worksheets/mastery/reset", version="legacy")
def mastery_reset(req: MasteryResetRequest, response: Response):
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "2026-06-01"
    response.headers["Link"] = '</api/v1/worksheets/mastery/reset>; rel="successor-version"'
    return reset_skill(req.student_id, req.skill_tag)


class PDFExportRequest(BaseModel):
    worksheet: Worksheet
    pdf_type: Literal["full", "student", "answer_key"] = "full"


@router.post("/export-pdf")
@instrument(route="/api/worksheets/export-pdf", version="legacy")
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
@instrument(route="/api/worksheets/save", version="legacy")
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
@instrument(route="/api/worksheets/saved/list", version="legacy")
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
@instrument(route="/api/worksheets/saved/{id}", version="legacy")
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
@instrument(route="/api/worksheets/saved/{id}", version="legacy")
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

from app.services.subscription_check import FREE_TIER_LIMIT  # 10 worksheets/month


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
@instrument(route="/api/worksheets/regenerate/{id}", version="legacy")
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

        # Generate new worksheet via slot pipeline
        start_time = datetime.now()

        region = original.get("region", "India")
        num_questions = len(original["questions"])
        difficulty = original["difficulty"].lower()

        meta, slot_questions = run_slot_pipeline(
            client=client,
            grade=original["grade"],
            subject=original["subject"],
            topic=original["topic"],
            q_count=num_questions,
            difficulty=difficulty,
            region=region,
            language=original.get("language", "English"),
            child_id=original.get("child_id"),
        )

        # Map slot-engine output → API Question models
        questions = [_slot_to_question(q, i) for i, q in enumerate(slot_questions)]
        _fill_role_explanations(questions)

        common_mistakes = meta.get("common_mistakes") or []
        worksheet = Worksheet(
            title=f"{meta.get('micro_skill', original['topic'])} - Practice",
            grade=original["grade"],
            subject=original["subject"],
            topic=original["topic"],
            difficulty=meta.get("difficulty", original["difficulty"]).capitalize(),
            language=original.get("language", "English"),
            questions=questions,
            skill_focus=meta.get("skill_focus", ""),
            common_mistake=common_mistakes[0] if common_mistakes else "",
            parent_tip=meta.get("parent_tip", ""),
            learning_objectives=get_learning_objectives(original["topic"]),
            mastery_snapshot=meta.get("mastery_snapshot"),
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
@instrument(route="/api/worksheets/analytics", version="legacy")
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
