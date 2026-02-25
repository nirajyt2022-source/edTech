"""
Textbook upload → AI analysis → generate worksheet/revision/flashcards.

Flow:
1. User uploads 1-3 photos of a textbook page
2. Gemini Vision extracts grade, subject, topic, key concepts, full text
3. User chooses output type (worksheet / revision / flashcards)
4. Gemini generates content based on extracted textbook text
"""

import base64
import logging

from fastapi import APIRouter, HTTPException, Header, Request, UploadFile, File

from app.middleware.rate_limit import limiter
from app.middleware.sanitize import validate_file_upload
from app.services.subscription_check import check_ai_usage_allowed
from pydantic import BaseModel, Field
from typing import Literal
from supabase import create_client
from app.core.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/textbook", tags=["textbook"])

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

class TextbookAnalysis(BaseModel):
    """What Gemini extracted from the textbook photo."""
    detected_grade: str        # "Class 4"
    detected_subject: str      # "Maths"
    detected_topic: str        # "Fractions"
    detected_chapter: str      # "Chapter 8: Fractions"
    key_concepts: list[str]    # ["Like fractions", "Unlike fractions", ...]
    content_summary: str       # 2-3 sentence summary
    language: str              # "English" or "Hindi"
    raw_text: str              # Full extracted text from the page


class TextbookGenerateRequest(BaseModel):
    """Generate content from analyzed textbook page."""
    analysis: TextbookAnalysis
    output_type: Literal["worksheet", "revision", "flashcards"] = "worksheet"
    difficulty: str = "Medium"
    question_count: int = Field(default=10, ge=1, le=30)
    language: str = "English"


# ── Endpoints ─────────────────────────────────────────────────────────────

@router.post("/analyze", response_model=TextbookAnalysis)
@limiter.limit("5/minute")
async def analyze_textbook_page(
    request: Request,
    images: list[UploadFile] = File(..., description="1-3 photos of textbook pages"),
    authorization: str = Header(...),
):
    """
    Step 1: Analyze textbook page photos using Gemini Vision.
    Extracts grade, subject, topic, key concepts, and full text content.
    """
    user_id = get_user_id_from_token(authorization)

    # -- Subscription gate --
    usage = await check_ai_usage_allowed(user_id, supabase)
    if not usage["allowed"]:
        raise HTTPException(status_code=402, detail=usage["message"])

    if len(images) < 1 or len(images) > 3:
        raise HTTPException(400, "Upload 1-3 photos")

    # Validate file types and sizes (max 10MB each)
    for img in images:
        content = await img.read()
        validate_file_upload(img.content_type or "image/jpeg", len(content), max_mb=10)
        await img.seek(0)  # Reset for re-read below

    # Read images as base64
    image_parts = []
    for img in images:
        content = await img.read()
        b64 = base64.b64encode(content).decode("utf-8")
        mime = img.content_type or "image/jpeg"
        image_parts.append({
            "inline_data": {"mime_type": mime, "data": b64}
        })

    prompt = """You are analyzing a page from an Indian school textbook (NCERT or CBSE-aligned).

Look at the uploaded photo(s) carefully and extract:

1. Grade/Class level (Class 1 through Class 5, or your best guess)
2. Subject (Maths, English, EVS/Science, Hindi, Computer, GK, etc.)
3. Topic name (e.g., "Fractions", "Animals Around Us", "Nouns and Pronouns")
4. Chapter name if visible (e.g., "Chapter 8: Fractions")
5. Key concepts covered on this page (list 3-7 specific concepts)
6. A 2-3 sentence summary of the content
7. Language the textbook is in ("English" or "Hindi")
8. The FULL text content from the page (transcribe everything readable)

Return ONLY valid JSON (no markdown, no code fences):
{
  "detected_grade": "Class 4",
  "detected_subject": "Maths",
  "detected_topic": "Fractions",
  "detected_chapter": "Chapter 8: Fractions",
  "key_concepts": ["Like fractions", "Unlike fractions", "Comparing fractions", "Addition of fractions"],
  "content_summary": "This page introduces fractions as parts of a whole. It explains numerator and denominator with visual examples using pizza slices.",
  "language": "English",
  "raw_text": "Full transcribed text from the page..."
}

If you cannot determine a field with confidence, make your best guess based on the content level and subject matter. Indian NCERT textbooks for Class 1-5 are the most likely source."""

    result = await _call_gemini_vision(image_parts, prompt)

    logger.info(
        f"Textbook analyzed for user={user_id}: "
        f"{result.get('detected_grade')}/{result.get('detected_subject')}/{result.get('detected_topic')}"
    )
    return TextbookAnalysis(**result)


@router.post("/generate")
@limiter.limit("10/minute")
async def generate_from_textbook(
    request: Request,
    body: TextbookGenerateRequest,
    authorization: str = Header(...),
):
    """
    Step 2: Generate worksheet/revision/flashcards from textbook content.
    Uses the extracted text and concepts as context for Gemini.
    """
    user_id = get_user_id_from_token(authorization)

    # -- Subscription gate --
    usage = await check_ai_usage_allowed(user_id, supabase)
    if not usage["allowed"]:
        raise HTTPException(status_code=402, detail=usage["message"])

    if body.output_type == "worksheet":
        result = await _generate_textbook_worksheet(body)
    elif body.output_type == "revision":
        result = await _generate_textbook_revision(body)
    elif body.output_type == "flashcards":
        result = await _generate_textbook_flashcards(body)
    else:
        raise HTTPException(400, f"Unknown output_type: {body.output_type}")

    logger.info(
        f"Textbook {body.output_type} generated for user={user_id}: "
        f"{body.analysis.detected_topic}"
    )
    return result


# ── Gemini helpers ────────────────────────────────────────────────────────

async def _call_gemini_vision(image_parts: list, prompt: str) -> dict:
    """Call Gemini Vision with image(s) + text prompt, return parsed JSON."""
    import asyncio
    from app.services.ai_client import get_ai_client

    try:
        ai = get_ai_client()
        return await asyncio.to_thread(
            ai.generate_with_images,
            image_parts=image_parts,
            prompt=prompt,
            temperature=0.2,
        )
    except ValueError as e:
        logger.error(f"AI textbook analysis parse error: {e}")
        raise HTTPException(502, "Could not parse textbook analysis. Please try again.")
    except Exception as e:
        logger.error(f"AI textbook analysis error: {e}")
        raise HTTPException(502, "AI textbook analysis unavailable. Please try again.")


async def _call_gemini_text(prompt: str, temperature: float = 0.7, max_tokens: int = 8192) -> dict:
    """Call Gemini text and return parsed JSON."""
    import asyncio
    from app.services.ai_client import get_ai_client

    try:
        ai = get_ai_client()
        return await asyncio.to_thread(ai.generate_json, prompt=prompt, temperature=temperature, max_tokens=max_tokens)
    except ValueError as e:
        logger.error(f"AI textbook generation parse error: {e}")
        raise HTTPException(502, "Could not parse textbook generation. Please try again.")
    except Exception as e:
        logger.error(f"AI textbook generation error: {e}")
        raise HTTPException(502, "AI generation unavailable. Please try again.")


# ── Generation functions ──────────────────────────────────────────────────

async def _generate_textbook_worksheet(request: TextbookGenerateRequest) -> dict:
    """Generate a Skolar worksheet based on textbook content."""
    analysis = request.analysis

    hindi_instruction = (
        'Generate ALL question text and options in Hindi (Devanagari script). '
        'Technical terms may stay in English.'
    ) if request.language.lower() == "hindi" else ""

    prompt = f"""Generate a {request.question_count}-question worksheet for {analysis.detected_grade} {analysis.detected_subject}.

TEXTBOOK CONTEXT (generate questions based on THIS content):
Chapter: {analysis.detected_chapter}
Topic: {analysis.detected_topic}
Key Concepts: {', '.join(analysis.key_concepts)}
Content: {analysis.raw_text[:3000]}

IMPORTANT: Generate questions that DIRECTLY test the concepts from the textbook page above.
Do NOT generate generic questions — every question should relate to specific content from this page.

{hindi_instruction}

Follow the Skolar worksheet format:
- Mix of question types: mcq_4, fill_blank, true_false, short_answer
- Three difficulty tiers: foundation (40%), application (40%), stretch (20%)
- Each question needs: id, type (one of mcq_4/fill_blank/true_false/short_answer), text, correct_answer, hint, explanation, difficulty
- For mcq_4, include "options" array with exactly 4 choices
- Use Indian names (Aarav, Priya, Rohan, Meera, Kavya, Dhruv)
- Use Indian context (₹ for money, Indian cities, festivals, foods)

Return ONLY valid JSON (no markdown, no code fences):
{{
  "title": "{analysis.detected_topic}",
  "grade": "{analysis.detected_grade}",
  "subject": "{analysis.detected_subject}",
  "topic": "{analysis.detected_topic}",
  "difficulty": "{request.difficulty}",
  "language": "{request.language}",
  "learning_objectives": ["objective 1", "objective 2", "objective 3"],
  "questions": [
    {{
      "id": "Q1",
      "type": "mcq_4",
      "text": "Question text",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "correct_answer": "Option B",
      "hint": "A helpful hint",
      "explanation": "Why the answer is correct",
      "difficulty": "foundation"
    }},
    {{
      "id": "Q2",
      "type": "fill_blank",
      "text": "The ___ is the top number of a fraction.",
      "correct_answer": "numerator",
      "hint": "Think about what 'numer' means",
      "explanation": "The numerator tells us how many parts we have",
      "difficulty": "foundation"
    }}
  ]
}}"""

    result = await _call_gemini_text(prompt, temperature=0.7, max_tokens=8192)

    # Add source metadata
    result["source"] = "textbook_upload"
    result["textbook_chapter"] = analysis.detected_chapter

    # Ensure required fields
    result.setdefault("title", analysis.detected_topic)
    result.setdefault("grade", analysis.detected_grade)
    result.setdefault("subject", analysis.detected_subject)
    result.setdefault("topic", analysis.detected_topic)
    result.setdefault("difficulty", request.difficulty)
    result.setdefault("language", request.language)

    return result


async def _generate_textbook_revision(request: TextbookGenerateRequest) -> dict:
    """Generate revision notes from textbook content.

    Returns the same shape as RevisionResponse so the frontend
    RevisionPreview component can render it directly.
    """
    analysis = request.analysis

    hindi_instruction = (
        'IMPORTANT: Write ALL content in Hindi using Devanagari script. '
        'Technical terms may be kept in English with Hindi transliteration in parentheses.'
    ) if request.language.lower() == "hindi" else "Write all content in clear, simple English."

    prompt = f"""You are an expert CBSE {analysis.detected_subject} teacher creating revision notes for {analysis.detected_grade} students.

BASE YOUR NOTES ON THIS TEXTBOOK CONTENT:
Chapter: {analysis.detected_chapter}
Topic: {analysis.detected_topic}
Key concepts: {', '.join(analysis.key_concepts)}
Content: {analysis.raw_text[:3000]}

{hindi_instruction}

Create concise revision notes that summarize THIS specific textbook page.
Use Indian names and context (Riya, Arjun, Priya, Rohan) in all examples.

Return ONLY valid JSON (no markdown, no code fences):
{{
  "grade": "{analysis.detected_grade}",
  "subject": "{analysis.detected_subject}",
  "topic": "{analysis.detected_topic}",
  "language": "{request.language}",
  "introduction": "2-3 sentence overview of this chapter content",
  "key_concepts": [
    {{
      "title": "Concept name",
      "explanation": "Clear explanation in simple language",
      "example": "A concrete example"
    }}
  ],
  "worked_examples": [
    {{
      "problem": "Problem statement",
      "step_by_step": ["Step 1: ...", "Step 2: ...", "Step 3: ..."],
      "answer": "Final answer"
    }}
  ],
  "common_mistakes": [
    {{
      "mistake": "What students commonly do wrong",
      "correction": "The correct approach",
      "tip": "A helpful tip"
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
  "memory_tips": ["A mnemonic or memory trick"]
}}

REQUIREMENTS:
- 3-5 key concepts from the textbook page
- 2-3 worked examples using content from the page
- 3-4 common mistakes
- 4-5 MCQ quiz questions with exactly 4 options each
- 3-4 memory tips
- Keep all content concise — suitable for quick revision"""

    result = await _call_gemini_text(prompt, temperature=0.5, max_tokens=4096)

    # Ensure required fields match RevisionResponse shape
    result.setdefault("grade", analysis.detected_grade)
    result.setdefault("subject", analysis.detected_subject)
    result.setdefault("topic", analysis.detected_topic)
    result.setdefault("language", request.language)

    return result


async def _generate_textbook_flashcards(request: TextbookGenerateRequest) -> dict:
    """Generate flashcards from textbook content.

    Returns the same shape as FlashcardSet so the frontend
    FlashcardPreview component can render it directly.
    """
    analysis = request.analysis

    hindi_instruction = (
        'IMPORTANT: Write ALL card content in Hindi using Devanagari script. '
        'Technical terms may be kept in English with Hindi transliteration in parentheses.'
    ) if request.language.lower() == "hindi" else "Write all card content in clear, simple English."

    prompt = f"""Generate 12 flashcards for {analysis.detected_grade} {analysis.detected_subject} based on this textbook content:

Chapter: {analysis.detected_chapter}
Topic: {analysis.detected_topic}
Key concepts: {', '.join(analysis.key_concepts)}
Content: {analysis.raw_text[:3000]}

{hindi_instruction}

Front: A term, question, or concept from the textbook (max 15 words)
Back: The answer, definition, or explanation (max 30 words)
Category: one of "concept", "fact", "formula", "question"

IMPORTANT: Every card should directly relate to the textbook content above.
Use Indian names and context. Order from simple to complex.

Return ONLY valid JSON (no markdown, no code fences):
{{
  "title": "{analysis.detected_topic} \u2014 Flashcards",
  "grade": "{analysis.detected_grade}",
  "subject": "{analysis.detected_subject}",
  "topic": "{analysis.detected_topic}",
  "cards": [
    {{"front": "Short question/term", "back": "Concise answer", "category": "concept"}}
  ]
}}"""

    result = await _call_gemini_text(prompt, temperature=0.7, max_tokens=4096)

    # Ensure required fields match FlashcardSet shape
    result.setdefault("title", f"{analysis.detected_topic} \u2014 Flashcards")
    result.setdefault("grade", analysis.detected_grade)
    result.setdefault("subject", analysis.detected_subject)
    result.setdefault("topic", analysis.detected_topic)

    return result
