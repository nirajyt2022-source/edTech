"""
Ask Skolar — AI doubt solver / tutor chat.

Flow:
1. Student types a homework question
2. Gemini answers with step-by-step explanation, age-appropriate
3. Topic detection suggests Practice/Revise links
4. Multi-turn conversation supported via history
"""

import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.deps import DbClient, UserId
from app.middleware.rate_limit import limiter
from app.middleware.sanitize import INJECTION_RE as _INJECTION_RE
from app.services.subscription_check import check_ai_usage_allowed

logger = structlog.get_logger("skolar.ask_skolar")


def _sanitize_question(question: str) -> str:
    """Strip prompt injection attempts from student questions."""
    if _INJECTION_RE.search(question):
        logger.warning("prompt_injection_blocked question=%s", question[:100])
        cleaned = _INJECTION_RE.sub("", question).strip()
        if len(cleaned) < 5:
            return "Hello, can you help me with my studies?"
        return cleaned
    return question


router = APIRouter(prefix="/api/v1/ask", tags=["ask_skolar"])

# ── Pydantic models ──────────────────────────────────────────────────────


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class AskRequest(BaseModel):
    question: str = Field(..., max_length=2000)
    grade: str = ""  # Optional: "Class 4"
    subject: str = ""  # Optional: "Maths"
    language: str = "English"  # "English" or "Hindi"
    history: list[ChatMessage] = Field(default=[], max_length=20)  # Previous messages for multi-turn


class AskResponse(BaseModel):
    answer: str
    suggested_topic: str | None = None  # e.g., "Fractions"
    suggested_subject: str | None = None  # e.g., "Maths"
    suggested_grade: str | None = None  # e.g., "Class 4"


# ── Endpoints ─────────────────────────────────────────────────────────────


@router.post("/question", response_model=AskResponse)
@limiter.limit("20/minute")
async def ask_question(request: Request, body: AskRequest, user_id: UserId, db: DbClient):
    """Answer a student's homework/study question using Gemini."""

    # -- Subscription gate --
    usage = await check_ai_usage_allowed(user_id, db)
    if not usage["allowed"]:
        raise HTTPException(status_code=402, detail=usage["message"])

    # Sanitize input against prompt injection
    safe_question = _sanitize_question(body.question)

    # Sanitize user messages in history
    safe_history = []
    for msg in body.history:
        if msg.role == "user":
            safe_history.append(ChatMessage(role=msg.role, content=_sanitize_question(msg.content)))
        else:
            safe_history.append(msg)

    grade_context = (
        f"The student is in {body.grade}." if body.grade else "Determine the appropriate level from the question."
    )
    subject_context = f"This is a {body.subject} question." if body.subject else ""

    language_instruction = ""
    if body.language.lower() == "hindi":
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

    # -- RAG: Inject curriculum context if grade+subject available --
    if body.grade and body.subject:
        from app.services.curriculum import get_curriculum_context

        # Use detected topic from question or fall back to empty
        curriculum_ctx = await get_curriculum_context(body.grade, body.subject, safe_question[:50])
        if curriculum_ctx:
            system_prompt = f"{system_prompt}\n\n{curriculum_ctx}"
            logger.info("Curriculum context injected for Ask Skolar: %s/%s", body.grade, body.subject)
    # -- End RAG --

    answer_text = await _call_gemini_chat(system_prompt, safe_history, safe_question)

    # Detect topic for Practice/Revise links
    topic_detection = await _detect_topic(safe_question, body.grade)

    logger.info(f"Ask Skolar answered for user={user_id}: {safe_question[:80]}...")

    return AskResponse(
        answer=answer_text,
        suggested_topic=topic_detection.get("topic"),
        suggested_subject=topic_detection.get("subject"),
        suggested_grade=topic_detection.get("grade") or body.grade or None,
    )


# ── Internal helpers ──────────────────────────────────────────────────────


async def _call_gemini_chat(system_prompt: str, history: list[ChatMessage], question: str) -> str:
    """Call Gemini with chat history and return the answer text."""
    import asyncio

    from app.services.ai_client import get_ai_client

    # Build message history (last 10 messages for context)
    messages = []
    for msg in history[-10:]:
        messages.append(
            {
                "role": "user" if msg.role == "user" else "model",
                "content": msg.content,
            }
        )

    # Add current question
    messages.append({"role": "user", "content": question})

    try:
        ai = get_ai_client()
        return await asyncio.to_thread(
            ai.generate_chat,
            messages=messages,
            system=system_prompt,
            temperature=0.5,
            max_tokens=2048,
        )
    except Exception as e:
        logger.error(f"AI chat error: {e}")
        raise HTTPException(502, "AI tutor unavailable. Please try again.")


async def _detect_topic(question: str, grade: str) -> dict:
    """Quick detection of the most relevant Skolar topic from the question."""
    import asyncio

    from app.services.ai_client import get_ai_client

    prompt = f"""From this student question, identify the most relevant CBSE topic.

Question: {question}
Grade: {grade or "unknown"}

Return ONLY JSON (no markdown, no code fences):
{{"topic": "Fractions", "subject": "Maths", "grade": "Class 4"}}

If you can't determine, return: {{"topic": null, "subject": null, "grade": null}}"""

    try:
        ai = get_ai_client()
        return await asyncio.to_thread(ai.generate_json, prompt=prompt, temperature=0.1, max_tokens=100)
    except Exception as e:
        logger.warning(f"Topic detection failed: {e}")
        return {"topic": None, "subject": None, "grade": None}
