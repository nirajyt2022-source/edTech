"""
Answer sheet photo grading via Gemini Vision.

Flow:
1. Receive worksheet data + uploaded images
2. Build a structured prompt with all questions + correct answers
3. Send images + prompt to Gemini Vision
4. Parse structured JSON response
5. Return grading results
"""

import base64
import json
import logging

from fastapi import APIRouter, Request, UploadFile, File, Form, HTTPException, Header

from app.middleware.rate_limit import limiter
from app.middleware.sanitize import validate_file_upload
from app.services.subscription_check import check_ai_usage_allowed
from typing import Optional
from supabase import create_client
from app.core.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/grading", tags=["grading"])

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


@router.post("/grade-photo")
@limiter.limit("5/minute")
async def grade_from_photo(
    request: Request,
    images: list[UploadFile] = File(..., description="1-5 photos of filled worksheet"),
    worksheet_json: str = Form(..., description="JSON string of worksheet data including questions"),
    child_id: Optional[str] = Form(None),
    authorization: str = Header(...),
):
    """Grade a student's handwritten answers from photos."""

    user_id = get_user_id_from_token(authorization)

    # -- Subscription gate --
    usage = await check_ai_usage_allowed(user_id, supabase)
    if not usage["allowed"]:
        raise HTTPException(status_code=402, detail=usage["message"])

    # 1. Parse worksheet data
    try:
        worksheet = json.loads(worksheet_json)
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid worksheet JSON")

    questions = worksheet.get("questions", [])
    grade_level = worksheet.get("grade", "")
    subject = worksheet.get("subject", "")

    if not questions:
        raise HTTPException(400, "No questions found in worksheet")

    if len(images) < 1 or len(images) > 5:
        raise HTTPException(400, "Upload 1-5 photos")

    # 2. Read images as base64
    image_data = []
    for img in images:
        content = await img.read()
        validate_file_upload(img.content_type or "image/jpeg", len(content), max_mb=10)
        b64 = base64.b64encode(content).decode("utf-8")
        mime = img.content_type or "image/jpeg"
        image_data.append({"base64": b64, "mime_type": mime})

    # 3. Build the grading prompt
    prompt = build_grading_prompt(questions, grade_level, subject)

    # 4. Call Gemini Vision
    results = await call_gemini_vision_for_grading(image_data, prompt, len(questions))

    # Validate grading output
    from app.services.output_validator import get_validator
    is_valid, val_errors = get_validator().validate_grading(results, total_questions=len(questions))
    if not is_valid:
        logger.warning("Grading validation issues", extra={"errors": val_errors})

    # Invalidate dashboard cache so fresh stats are shown
    if child_id:
        from app.services.cache import invalidate_dashboard
        invalidate_dashboard(child_id)

    logger.info(f"Grading complete for user={user_id}: {results['score']}/{results['total']}")

    return results


def build_grading_prompt(questions: list, grade: str, subject: str) -> str:
    """Build structured prompt for Gemini Vision grading."""

    qa_list = []
    for i, q in enumerate(questions, 1):
        q_text = q.get("text", q.get("question_text", ""))
        q_format = q.get("format", "short_answer")
        correct = q.get("correct_answer", "")
        options = q.get("options", [])

        entry = f"Q{i} [{q_format}]: {q_text}"
        if options:
            for j, opt in enumerate(options):
                letter = chr(65 + j)  # A, B, C, D
                entry += f"\n  {letter}) {opt}"
        entry += f"\nCorrect Answer: {correct}"
        qa_list.append(entry)

    questions_text = "\n\n".join(qa_list)

    # Determine spelling leniency based on class
    grade_num = 0
    try:
        grade_num = int("".join(filter(str.isdigit, str(grade))) or "0")
    except ValueError:
        pass

    if grade_num <= 2:
        spelling_rule = "Be VERY lenient with spelling. Accept phonetic approximations (e.g., 'nset' for 'nest', 'loin' for 'lion'). These are young children."
    elif grade_num <= 4:
        spelling_rule = "Be moderately lenient. Accept common misspellings but not completely wrong words."
    else:
        spelling_rule = "Expect correct spelling. Minor typos are OK but the word should be recognizably correct."

    return f"""You are grading a {grade} {subject} worksheet filled by a student.

QUESTIONS AND CORRECT ANSWERS:
{questions_text}

INSTRUCTIONS:
Look at the uploaded photo(s) of the student's filled-in worksheet.
For each question (Q1 through Q{len(questions)}), find the student's written/marked answer.

GRADING RULES:
- MCQ (mcq_3, mcq_4): Check which option letter (A/B/C/D) is circled, ticked, underlined, or written. Match against correct answer.
- True/False (true_false): Check if student selected A (True) or B (False). Match against correct answer.
- Fill-in-the-blank (fill_blank): Read the handwritten text. {spelling_rule}
- Short answer (short_answer, word_problem): Read the answer but mark as "needs_review" = true. Do NOT auto-grade these — a parent will review.
- Error detection (error_spot): Read the student's explanation. Mark as "needs_review" = true.

READING RULES:
- If handwriting is unclear, set confidence below 0.5 and needs_review = true
- If a question appears unanswered (blank), mark student_answer as "BLANK" and is_correct as false
- Read carefully — children's handwriting can be messy but often correct
- Look for tick marks, circles, underlines on MCQ options, not just written letters

FEEDBACK RULES:
- Be encouraging and age-appropriate
- For correct answers: brief praise ("Great job!", "Correct!", "Well done!")
- For wrong answers: explain what the right answer is and WHY, gently
- Keep feedback to 1-2 sentences max

Return ONLY valid JSON, no markdown backticks:
{{
  "results": [
    {{
      "question_number": 1,
      "question_format": "mcq_4",
      "student_answer": "B) Lion",
      "correct_answer": "B) Lion",
      "is_correct": true,
      "confidence": 0.95,
      "needs_review": false,
      "feedback": "Correct! Lions are known for their majestic manes."
    }}
  ],
  "score": 0,
  "total": {len(questions)},
  "needs_review_questions": [],
  "summary": "Brief 1-2 sentence overall performance summary"
}}"""


async def call_gemini_vision_for_grading(image_data: list[dict], prompt: str, expected_total: int) -> dict:
    """Call Gemini Vision API with images and grading prompt."""
    from app.services.ai_client import get_ai_client

    image_parts = [
        {"inline_data": {"mime_type": img["mime_type"], "data": img["base64"]}}
        for img in image_data
    ]

    try:
        import asyncio
        ai = get_ai_client()
        results = await asyncio.to_thread(
            ai.generate_with_images,
            image_parts=image_parts,
            prompt=prompt,
            temperature=0.1,
        )
    except ValueError as e:
        logger.error(f"AI grading error: {e}")
        raise HTTPException(502, "Could not parse grading results. Please try again with a clearer photo.")
    except Exception as e:
        logger.error(f"AI grading service error: {e}")
        raise HTTPException(502, "AI grading service unavailable. Please try again.")

    # Validate and compute score
    question_results = results.get("results", [])
    score = sum(1 for r in question_results if r.get("is_correct", False))
    needs_review = [r["question_number"] for r in question_results if r.get("needs_review", False)]

    return {
        "results": question_results,
        "score": score,
        "total": expected_total,
        "needs_review_questions": needs_review,
        "summary": results.get("summary", ""),
    }
