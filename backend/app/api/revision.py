"""
Revision notes generation via Gemini 2.5 Flash.

Flow:
1. Receive grade/subject/topic/language
2. Build structured prompt for CBSE-aligned revision notes
3. Call Gemini 2.5 Flash
4. Parse structured JSON response
5. Return revision notes OR generate PDF
"""

import io
import logging

from fastapi import APIRouter, HTTPException, Header, Request
from fastapi.responses import StreamingResponse

from app.middleware.rate_limit import limiter
from pydantic import BaseModel
from supabase import create_client
from app.core.config import get_settings
from app.services.revision_pdf import generate_revision_pdf

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/revision", tags=["revision"])

settings = get_settings()
supabase = create_client(settings.supabase_url, settings.supabase_service_key)


def get_user_id_from_token(authorization: str) -> str:
    """Extract user_id from Supabase JWT token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = authorization.replace("Bearer ", "")
    try:
        user_response = supabase.auth.get_user(token)
        if not user_response or not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user_response.user.id
    except Exception as e:
        logger.error(f"Auth error: {e}")
        raise HTTPException(status_code=401, detail="Authentication failed")


# ── Pydantic models ──────────────────────────────────────────────────────

class RevisionRequest(BaseModel):
    grade: str          # e.g. "Class 3"
    subject: str        # e.g. "Maths"
    topic: str          # e.g. "Fractions"
    language: str = "English"  # or "Hindi"


class KeyConcept(BaseModel):
    title: str
    explanation: str
    example: str


class WorkedExample(BaseModel):
    problem: str
    step_by_step: list[str]
    answer: str


class CommonMistake(BaseModel):
    mistake: str
    correction: str
    tip: str


class QuizQuestion(BaseModel):
    question: str
    options: list[str]
    correct_answer: str
    explanation: str


class RevisionResponse(BaseModel):
    grade: str
    subject: str
    topic: str
    language: str
    introduction: str
    key_concepts: list[KeyConcept]
    worked_examples: list[WorkedExample]
    common_mistakes: list[CommonMistake]
    quick_quiz: list[QuizQuestion]
    memory_tips: list[str]


# ── Endpoints ─────────────────────────────────────────────────────────────

@router.post("/generate", response_model=RevisionResponse)
@limiter.limit("10/minute")
async def generate_revision_notes(request: Request, req: RevisionRequest, authorization: str = Header(...)):
    """Generate structured revision notes for a given topic using Gemini 2.5 Flash."""
    user_id = get_user_id_from_token(authorization)

    prompt = _build_revision_prompt(req.grade, req.subject, req.topic, req.language)

    # -- RAG: Inject curriculum context --
    from app.services.curriculum import get_curriculum_context
    curriculum_ctx = await get_curriculum_context(req.grade, req.subject, req.topic)
    if curriculum_ctx:
        prompt = f"{curriculum_ctx}\n\n{prompt}"
        logger.info("Curriculum context injected for revision: %s/%s/%s", req.grade, req.subject, req.topic)
    # -- End RAG --

    result = await _call_gemini_for_revision(prompt)

    # Validate output
    from app.services.output_validator import get_validator
    is_valid, errors = get_validator().validate_revision(result)
    if not is_valid:
        logger.warning("Revision validation issues", extra={"errors": errors})

    # Attach request metadata to the response
    result["grade"] = req.grade
    result["subject"] = req.subject
    result["topic"] = req.topic
    result["language"] = req.language

    logger.info(f"Revision notes generated for user={user_id}: {req.grade}/{req.subject}/{req.topic}")
    return RevisionResponse(**result)


@router.post("/export-pdf")
@limiter.limit("10/minute")
async def export_revision_pdf(request: Request, notes: RevisionResponse, authorization: str = Header(...)):
    """Generate a PDF from revision notes and return as a downloadable file."""
    user_id = get_user_id_from_token(authorization)

    pdf_bytes = generate_revision_pdf(notes)
    logger.info(f"Revision PDF exported for user={user_id}: {notes.topic}")

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=revision_{notes.topic.replace(' ', '_')}.pdf"
        },
    )


# ── Internal helpers ──────────────────────────────────────────────────────

def _build_revision_prompt(grade: str, subject: str, topic: str, language: str) -> str:
    """Build a structured prompt for Gemini to generate revision notes."""

    language_instruction = ""
    if language.lower() == "hindi":
        language_instruction = (
            "IMPORTANT: Write ALL content in Hindi using Devanagari script. "
            "Technical terms may be kept in English with Hindi transliteration in parentheses."
        )
    else:
        language_instruction = "Write all content in clear, simple English."

    return f"""You are an expert CBSE {subject} teacher creating revision notes for {grade} students in India.

Topic: {topic}
Grade: {grade}
Subject: {subject}

{language_instruction}

Create comprehensive yet concise revision notes suitable for 1-2 pages. Use Indian names and context (Riya, Arjun, Priya, Rohan, etc.) in all examples.

The notes must be age-appropriate for {grade} students and strictly aligned with CBSE/NCERT curriculum.

Return ONLY valid JSON with this exact structure (no markdown, no code fences):
{{
  "introduction": "A brief 2-3 sentence introduction to the topic",
  "key_concepts": [
    {{
      "title": "Concept name",
      "explanation": "Clear explanation in simple language",
      "example": "A concrete example"
    }}
  ],
  "worked_examples": [
    {{
      "problem": "The problem statement",
      "step_by_step": ["Step 1: ...", "Step 2: ...", "Step 3: ..."],
      "answer": "The final answer"
    }}
  ],
  "common_mistakes": [
    {{
      "mistake": "What students commonly do wrong",
      "correction": "The correct approach",
      "tip": "A helpful tip to avoid this mistake"
    }}
  ],
  "quick_quiz": [
    {{
      "question": "A multiple choice question",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "correct_answer": "Option A",
      "explanation": "Why this is correct"
    }}
  ],
  "memory_tips": [
    "A mnemonic or memory trick to remember key facts"
  ]
}}

REQUIREMENTS:
- Generate 3-5 key concepts
- Generate 2-3 worked examples with clear step-by-step solutions
- Generate 3-4 common mistakes students make
- Generate 4-5 MCQ quiz questions with exactly 4 options each
- Generate 3-4 memory tips (mnemonics, tricks, rhymes)
- Keep all content concise — suitable for quick revision, not lengthy teaching
- Use simple vocabulary appropriate for {grade}
- Include practical, real-life examples from Indian context"""


async def _call_gemini_for_revision(prompt: str) -> dict:
    """Call Gemini 2.5 Flash and parse the JSON response."""
    from app.services.ai_client import get_ai_client

    try:
        ai = get_ai_client()
        return ai.generate_json(prompt=prompt, temperature=0.3, max_tokens=4096)
    except ValueError as e:
        logger.error(f"AI revision error: {e}")
        raise HTTPException(502, "Could not parse revision notes. Please try again.")
    except Exception as e:
        logger.error(f"AI revision service error: {e}")
        raise HTTPException(502, "AI revision service unavailable. Please try again.")
