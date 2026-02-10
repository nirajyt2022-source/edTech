from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Literal
import json
import uuid
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


class Question(BaseModel):
    id: str
    type: str
    text: str
    options: list[str] | None = None
    correct_answer: str | None = None
    explanation: str | None = None


class Worksheet(BaseModel):
    title: str
    grade: str
    subject: str
    topic: str
    difficulty: str
    language: str
    questions: list[Question]


class WorksheetGenerationResponse(BaseModel):
    worksheet: Worksheet
    generation_time_ms: int


SYSTEM_PROMPT = """You are a CBSE curriculum expert and Indian primary school teacher.
You generate practice worksheets for school children.

RULES:
1. Generate age-appropriate questions for the specified grade
2. Use simple, child-friendly language
3. Questions must be directly related to the topic
4. Do NOT add concepts beyond the grade level
5. For Maths: use Indian number system and contexts (rupees, local names)
6. Instructions and question text should be in the specified language
7. Mathematical symbols, numbers, and formulas remain unchanged regardless of language
8. For regional languages (Hindi, Marathi, Tamil, Telugu, Kannada, Arabic, Urdu):
   - Use native script for that language
   - Keep vocabulary grade-appropriate
   - Use culturally relevant examples

OUTPUT FORMAT (JSON only, no markdown):
{
  "title": "Practice Worksheet: [Topic]",
  "questions": [
    {
      "id": "q1",
      "type": "multiple_choice|fill_blank|short_answer|true_false",
      "text": "Question text",
      "options": ["A", "B", "C", "D"],
      "correct_answer": "correct answer",
      "explanation": "Brief explanation"
    }
  ]
}

Mix question types appropriately. For Maths, include calculation and word problems.
For English, include grammar and vocabulary. For EVS, include factual and application questions."""


@router.post("/generate", response_model=WorksheetGenerationResponse)
async def generate_worksheet(request: WorksheetGenerationRequest):
    """Generate a new worksheet based on provided parameters."""
    start_time = datetime.now()

    user_prompt = f"""Generate a {request.difficulty} difficulty worksheet:
- Board: {request.board}
- Grade: {request.grade_level}
- Subject: {request.subject}
- Topic: {request.topic}
- Number of Questions: {request.num_questions}
- Language for instructions: {request.language}

{f"Additional instructions: {request.custom_instructions}" if request.custom_instructions else ""}

Generate exactly {request.num_questions} questions. Return ONLY valid JSON, no markdown."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=4096,
        )

        content = response.choices[0].message.content or ""

        # Clean up response - remove markdown code blocks if present
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        # Parse JSON response
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=500, detail=f"Failed to parse AI response: {str(e)}")

        # Build questions with IDs
        questions = []
        for i, q in enumerate(data.get("questions", [])):
            questions.append(Question(
                id=q.get("id", f"q{i+1}"),
                type=q.get("type", "short_answer"),
                text=q.get("text", ""),
                options=q.get("options"),
                correct_answer=q.get("correct_answer"),
                explanation=q.get("explanation"),
            ))

        worksheet = Worksheet(
            title=data.get("title", f"{request.topic} Practice Worksheet"),
            grade=request.grade_level,
            subject=request.subject,
            topic=request.topic,
            difficulty=request.difficulty.capitalize(),
            language=request.language,
            questions=questions,
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
        raise HTTPException(status_code=500, detail=f"Failed to generate worksheet: {str(e)}")


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


class SaveWorksheetRequest(BaseModel):
    worksheet: Worksheet
    board: str | None = None
    child_id: str | None = None
    class_id: str | None = None


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

        user_prompt = f"""Generate a {original['difficulty'].lower()} difficulty worksheet:
- Board: {original.get('board', 'CBSE')}
- Grade: {original['grade']}
- Subject: {original['subject']}
- Topic: {original['topic']}
- Number of Questions: {len(original['questions'])}
- Language for instructions: {original.get('language', 'English')}

Generate exactly {len(original['questions'])} NEW questions (different from before). Return ONLY valid JSON, no markdown."""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.8,  # Slightly higher for more variety
            max_tokens=4096,
        )

        content = response.choices[0].message.content or ""

        # Clean up response
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=500, detail=f"Failed to parse AI response: {str(e)}")

        # Build questions
        questions = []
        for i, q in enumerate(data.get("questions", [])):
            questions.append(Question(
                id=q.get("id", f"q{i+1}"),
                type=q.get("type", "short_answer"),
                text=q.get("text", ""),
                options=q.get("options"),
                correct_answer=q.get("correct_answer"),
                explanation=q.get("explanation"),
            ))

        worksheet = Worksheet(
            title=data.get("title", f"{original['topic']} Practice Worksheet"),
            grade=original["grade"],
            subject=original["subject"],
            topic=original["topic"],
            difficulty=original["difficulty"],
            language=original.get("language", "English"),
            questions=questions,
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
        raise HTTPException(status_code=500, detail=f"Failed to regenerate worksheet: {str(e)}")


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
