from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Literal
import json
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
1. Warm-Up (1-2 easy questions)
2. Core Practice (majority medium difficulty)
3. Challenge (1-2 application/reasoning questions if difficulty=hard)

Ensure coverage of key sub-skills within the topic.

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
Do NOT use visual type names (number_line, object_group, clock, shapes) as the question "type".
Visuals go in "visual_type" and "visual_data" fields only.

Visual types allowed: clock, number_line, object_group, shapes.
Drawable constraints:
- object_group counts MUST NOT exceed 20 per group. For larger numbers use number_line instead.
- object_group labels must be simple, drawable nouns (e.g. "apples", "stars", "balls"). Avoid compound phrases like "boxes of chocolates".

Formats:
- clock: {{ "hour": 1-12, "minute": 0|5|10|...|55 }}
- number_line: {{ "start": int, "end": int, "step": int, "highlight": int }}
- object_group: {{ "groups": [{{"count": 1-20, "label": "apples"}}], "operation": "+"|"-"|"x" }}
  For multiplication ("x"), prefer number_line unless both factors are <= 10 and the product <= 20.
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

    # ── Answer rules + parent support + output format ──
    prompt += """

ANSWER RULES:
- Objective questions: provide exact correct_answer, set answer_type="exact", sample_answer=null, grading_notes=null.
- True/False: correct_answer must be "true" or "false" (lowercase string).
- Open-ended questions (write/explain/describe): set correct_answer=null, answer_type="example", provide sample_answer and grading_notes.

PARENT SUPPORT (include at top level of JSON):
- "skill_focus": brief statement of the core skill being practiced
- "common_mistake": typical mistake children make on this topic
- "parent_tip": short actionable guidance (1 sentence)

These must be practical and clear.

OUTPUT FORMAT (JSON only, no markdown):
{
  "title": "...",
  "skill_focus": "...",
  "common_mistake": "...",
  "parent_tip": "...",
  "questions": [
    {
      "id": "q1",
      "type": "multiple_choice" | "fill_blank" | "short_answer" | "true_false",
      "text": "...",
      "options": ["..."] | null,
      "correct_answer": "..." | null,
      "answer_type": "exact" | "example",
      "sample_answer": "..." | null,
      "grading_notes": "..." | null,
      "difficulty": "easy" | "medium" | "hard",
      "explanation": "Brief explanation",
      "visual_type": "clock" | "number_line" | "object_group" | "shapes" | null,
      "visual_data": { ... } | null
    }
  ]
}

FINAL CHECK BEFORE OUTPUT:
- Valid JSON only. No markdown.
- All required fields present.
- Exactly requested question count.
- No personal data prompts."""

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
_VISUAL_TYPE_NAMES = {"number_line", "object_group", "clock", "shapes"}


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

        # Visual field validation
        vtype = q.get("visual_type")
        vdata = q.get("visual_data")

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


def attempt_repair(
    system_prompt: str,
    original_data: dict,
    issues: list[str],
) -> dict | None:
    """Make ONE repair call to fix validation/visual issues. Returns fixed data or None."""
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
        return json.loads(content)
    except (json.JSONDecodeError, Exception):
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

        # ── Post-processing: schema fixups (before validation) ──
        _fixup_question_types(data)

        # ── Post-processing: visual enforcement ──
        if is_visual:
            data, visual_issues = enforce_visual_rules(
                data, request.problem_style, True
            )
        else:
            visual_issues = []

        # ── Validation (includes visual ratio + operation checks) ──
        validation_issues = validate_worksheet_data(
            data,
            problem_style=request.problem_style,
            is_visual_applicable=is_visual,
        )
        all_issues = validation_issues + visual_issues

        # ── Repair (one attempt) if issues found ──
        if all_issues:
            repaired = attempt_repair(system_prompt, data, all_issues)
            if repaired:
                data = repaired
                if is_visual:
                    data, _ = enforce_visual_rules(
                        data, request.problem_style, True
                    )

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

        # Schema fixups + validation + optional repair
        _fixup_question_types(data)
        validation_issues = validate_worksheet_data(data)
        if validation_issues:
            repaired = attempt_repair(system_prompt, data, validation_issues)
            if repaired:
                _fixup_question_types(repaired)
                data = repaired

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
