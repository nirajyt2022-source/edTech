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
    include_answer_key: bool = True


@router.post("/export-pdf")
async def export_worksheet_pdf(request: PDFExportRequest):
    """Export a worksheet as a PDF file."""
    try:
        # Convert Pydantic model to dict
        worksheet_dict = request.worksheet.model_dump()

        # Generate PDF
        pdf_bytes = pdf_service.generate_worksheet_pdf(
            worksheet_dict,
            include_answer_key=request.include_answer_key
        )

        # Create filename
        filename = f"{request.worksheet.title.replace(' ', '_')}.pdf"

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
    child_id: str | None = None
):
    """List user's saved worksheets."""
    user_id = get_user_id_from_token(authorization)

    try:
        # Build query with optional child_id filter
        query = supabase.table("worksheets") \
            .select("*, children(id, name)") \
            .eq("user_id", user_id)

        if child_id:
            query = query.eq("child_id", child_id)

        result = query \
            .order("created_at", desc=True) \
            .range(offset, offset + limit - 1) \
            .execute()

        worksheets = []
        for row in result.data:
            child_data = row.get("children")
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
