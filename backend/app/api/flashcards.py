"""
Flashcard generation via Gemini 2.5 Flash.

Flow:
1. Receive grade/subject/topic/language/count
2. Build structured prompt for CBSE-aligned flashcards
3. Call Gemini 2.5 Flash
4. Parse structured JSON response
5. Return flashcard set OR generate printable PDF
"""

import io
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from supabase import create_client
from app.core.config import get_settings
from app.services.flashcard_pdf import FlashcardPDFService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/flashcards", tags=["flashcards"])

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

class FlashcardRequest(BaseModel):
    grade: str          # e.g. "Class 3"
    subject: str        # e.g. "Maths"
    topic: str          # e.g. "Fractions"
    language: str = "English"
    count: int = 12


class Flashcard(BaseModel):
    front: str
    back: str
    category: str = "concept"  # concept / fact / formula / question


class FlashcardSet(BaseModel):
    title: str
    grade: str
    subject: str
    topic: str
    cards: list[Flashcard]


# ── Endpoints ─────────────────────────────────────────────────────────────

@router.post("/generate", response_model=FlashcardSet)
async def generate_flashcards(req: FlashcardRequest, authorization: str = Header(...)):
    """Generate a set of flashcards for a given topic using Gemini 2.5 Flash."""
    user_id = get_user_id_from_token(authorization)

    prompt = _build_flashcard_prompt(req.grade, req.subject, req.topic, req.language, req.count)
    result = await _call_gemini_for_flashcards(prompt)

    # Attach request metadata
    result["grade"] = req.grade
    result["subject"] = req.subject
    result["topic"] = req.topic

    logger.info(f"Flashcards generated for user={user_id}: {req.grade}/{req.subject}/{req.topic} ({len(result.get('cards', []))} cards)")
    return FlashcardSet(**result)


@router.post("/export-pdf")
async def export_flashcard_pdf(data: FlashcardSet, authorization: str = Header(...)):
    """Generate a printable 2-page PDF from flashcards and return as downloadable file."""
    user_id = get_user_id_from_token(authorization)

    pdf_bytes = FlashcardPDFService.generate(data.model_dump())
    logger.info(f"Flashcard PDF exported for user={user_id}: {data.topic}")

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=flashcards_{data.topic.replace(' ', '_')}.pdf"
        },
    )


# ── Internal helpers ──────────────────────────────────────────────────────

_SUBJECT_INSTRUCTIONS = {
    "Maths": "Include formulas, key calculations, number facts, and mental math tricks. Use visual representations where helpful (e.g., 'Front: 1/2 + 1/4 = ?' → 'Back: 3/4').",
    "English": "Include vocabulary words with meanings, grammar rules, sentence examples, synonyms/antonyms, and spelling tips.",
    "Hindi": "Write in Devanagari script. Include शब्द (words) with अर्थ (meanings), व्याकरण (grammar) rules, मुहावरे (idioms), and वाक्य प्रयोग (usage in sentences).",
    "Science": "Include key scientific concepts, definitions, processes, and real-world examples. Use simple 'What/Why/How' question format.",
    "EVS": "Include environmental facts, community concepts, daily life connections, and nature observations relevant to Indian context.",
    "GK": "Include trivia about India, world facts, national symbols, famous personalities, and current general knowledge appropriate for the grade.",
    "Computer": "Include basic computer terms, shortcuts, definitions, and simple concepts about hardware/software.",
    "Moral Science": "Include values, their meanings, short scenario-based questions, and moral lessons from Indian stories.",
    "Health": "Include hygiene tips, nutrition facts, exercise benefits, and health-related definitions.",
}


def _build_flashcard_prompt(grade: str, subject: str, topic: str, language: str, count: int) -> str:
    """Build a structured prompt for Gemini to generate flashcards."""

    language_instruction = ""
    if language.lower() == "hindi":
        language_instruction = (
            "IMPORTANT: Write ALL card content in Hindi using Devanagari script. "
            "Technical terms may be kept in English with Hindi transliteration in parentheses."
        )
    else:
        language_instruction = "Write all card content in clear, simple English."

    subject_hint = _SUBJECT_INSTRUCTIONS.get(subject, "Include key concepts, definitions, and examples.")

    return f"""You are an expert CBSE {subject} teacher creating study flashcards for {grade} students in India.

Topic: {topic}
Grade: {grade}
Subject: {subject}

{language_instruction}

Create exactly {count} flashcards for quick revision and recall practice.

Subject-specific guidance: {subject_hint}

Each card has a FRONT (question/prompt) and BACK (answer/explanation).
Each card has a category: "concept", "fact", "formula", or "question".

Return ONLY valid JSON with this exact structure (no markdown, no code fences):
{{
  "title": "{topic} — Flashcards",
  "cards": [
    {{
      "front": "Short question or prompt (max 15 words)",
      "back": "Clear answer or explanation (max 30 words)",
      "category": "concept"
    }}
  ]
}}

REQUIREMENTS:
- Generate exactly {count} cards
- Front text: maximum 15 words, clear and direct
- Back text: maximum 30 words, concise but complete
- Order from simple to complex (easier concepts first)
- No duplicate concepts — each card covers a unique point
- Use Indian names and context (Riya, Arjun, Priya, Rohan, etc.) in examples
- Strictly aligned with CBSE/NCERT curriculum for {grade}
- Age-appropriate vocabulary for {grade} students
- Mix of categories: include at least 2 "question" type and 1 "formula" type (if applicable)
- Category must be one of: "concept", "fact", "formula", "question"
"""


async def _call_gemini_for_flashcards(prompt: str) -> dict:
    """Call Gemini 2.5 Flash and parse the JSON response."""
    from app.services.ai_client import get_ai_client

    try:
        ai = get_ai_client()
        return ai.generate_json(prompt=prompt, temperature=0.7, max_tokens=4096)
    except ValueError as e:
        logger.error(f"AI flashcard error: {e}")
        raise HTTPException(502, "Could not parse flashcards. Please try again.")
    except Exception as e:
        logger.error(f"AI flashcard service error: {e}")
        raise HTTPException(502, "AI flashcard service unavailable. Please try again.")
