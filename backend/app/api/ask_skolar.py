"""
Ask Skolar — AI doubt solver / tutor chat.

Flow:
1. Student types a homework question
2. Gemini answers with step-by-step explanation, age-appropriate
3. Topic detection suggests Practice/Revise links
4. Multi-turn conversation supported via history
"""

import json
import logging

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from supabase import create_client
from app.core.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ask", tags=["ask_skolar"])

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

class ChatMessage(BaseModel):
    role: str        # "user" or "assistant"
    content: str


class AskRequest(BaseModel):
    question: str
    grade: str = ""               # Optional: "Class 4"
    subject: str = ""             # Optional: "Maths"
    language: str = "English"     # "English" or "Hindi"
    history: list[ChatMessage] = []  # Previous messages for multi-turn


class AskResponse(BaseModel):
    answer: str
    suggested_topic: str | None = None     # e.g., "Fractions"
    suggested_subject: str | None = None   # e.g., "Maths"
    suggested_grade: str | None = None     # e.g., "Class 4"


# ── Endpoints ─────────────────────────────────────────────────────────────

@router.post("/question", response_model=AskResponse)
async def ask_question(request: AskRequest, authorization: str = Header(...)):
    """Answer a student's homework/study question using Gemini."""
    user_id = get_user_id_from_token(authorization)

    grade_context = f"The student is in {request.grade}." if request.grade else "Determine the appropriate level from the question."
    subject_context = f"This is a {request.subject} question." if request.subject else ""

    language_instruction = ""
    if request.language.lower() == "hindi":
        language_instruction = "Respond entirely in Hindi (Devanagari script). Technical terms may stay in English."

    system_prompt = f"""You are Skolar, a friendly and patient AI tutor for Indian school children (CBSE, Classes 1-5).

{grade_context}
{subject_context}
{language_instruction}

RULES:
1. ALWAYS explain step-by-step. Number your steps.
2. Use SIMPLE language appropriate for the student's class level.
   - Class 1-2: Very simple words, short sentences, use examples from daily life
   - Class 3-4: Clear explanations, introduce subject terms with definitions
   - Class 5: Can use more formal language, longer explanations
3. Use Indian context: ₹ for money, Indian names (Aarav, Priya, Rohan, Meera), Indian places, festivals, foods.
4. For Maths: show full working, one step per line, use → arrows for flow.
5. For Science/EVS: explain with real-world examples a child can relate to.
6. For English: give grammar rules with 2-3 example sentences.
7. For Hindi: respond in Devanagari, give examples with common words.
8. End with a 💡 Tip or fun fact when appropriate.
9. Be encouraging: "Great question!", "You're on the right track!", "Let's figure this out together!"
10. If the question is NOT related to school curriculum (Class 1-5 CBSE), politely redirect: "That's an interesting question! I'm best at helping with your school subjects. Try asking me about Maths, Science, English, Hindi, or EVS!"
11. Do NOT answer questions about:
    - Violence, weapons, or harmful activities
    - Adult content
    - Personal opinions on politics or religion
    - Anything outside the scope of a Class 1-5 education
    Instead say: "I'm here to help with your school studies! Ask me about any subject."
12. Keep responses concise — max 200 words for simple questions, max 400 for complex ones."""

    answer_text = await _call_gemini_chat(system_prompt, request.history, request.question)

    # Detect topic for Practice/Revise links
    topic_detection = await _detect_topic(request.question, request.grade)

    logger.info(f"Ask Skolar answered for user={user_id}: {request.question[:80]}...")

    return AskResponse(
        answer=answer_text,
        suggested_topic=topic_detection.get("topic"),
        suggested_subject=topic_detection.get("subject"),
        suggested_grade=topic_detection.get("grade") or request.grade or None,
    )


# ── Internal helpers ──────────────────────────────────────────────────────

async def _call_gemini_chat(system_prompt: str, history: list[ChatMessage], question: str) -> str:
    """Call Gemini with chat history and return the answer text."""
    from google import genai

    if not settings.gemini_api_key:
        raise HTTPException(500, "Gemini API key not configured")

    client = genai.Client(api_key=settings.gemini_api_key)

    # Build message history (last 10 messages for context)
    messages = []
    for msg in history[-10:]:
        messages.append({
            "role": "user" if msg.role == "user" else "model",
            "parts": [{"text": msg.content}],
        })

    # Add current question
    messages.append({
        "role": "user",
        "parts": [{"text": question}],
    })

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=messages,
            config={
                "temperature": 0.5,
                "max_output_tokens": 2048,
                "system_instruction": system_prompt,
            },
        )
    except Exception as e:
        logger.error(f"Gemini chat API error: {e}")
        raise HTTPException(502, "AI tutor unavailable. Please try again.")

    return response.text or "I'm sorry, I couldn't understand that. Could you rephrase your question?"


async def _detect_topic(question: str, grade: str) -> dict:
    """Quick detection of the most relevant Skolar topic from the question."""
    from google import genai

    if not settings.gemini_api_key:
        return {"topic": None, "subject": None, "grade": None}

    client = genai.Client(api_key=settings.gemini_api_key)

    prompt = f"""From this student question, identify the most relevant CBSE topic.

Question: {question}
Grade: {grade or "unknown"}

Return ONLY JSON (no markdown, no code fences):
{{"topic": "Fractions", "subject": "Maths", "grade": "Class 4"}}

If you can't determine, return: {{"topic": null, "subject": null, "grade": null}}"""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[{"parts": [{"text": prompt}]}],
            config={"temperature": 0.1, "max_output_tokens": 100},
        )
        raw = (response.text or "").strip()
        if raw.startswith("```json"):
            raw = raw[7:]
        if raw.startswith("```"):
            raw = raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        return json.loads(raw.strip())
    except Exception as e:
        logger.warning(f"Topic detection failed: {e}")
        return {"topic": None, "subject": None, "grade": None}
