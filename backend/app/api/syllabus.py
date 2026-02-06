from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
import json
import uuid
from datetime import datetime
from openai import OpenAI
from PyPDF2 import PdfReader
import io
from app.core.config import get_settings

router = APIRouter(prefix="/api/syllabus", tags=["syllabus"])

settings = get_settings()
client = OpenAI(api_key=settings.openai_api_key)


class SyllabusTopic(BaseModel):
    name: str
    subtopics: list[str] | None = None


class SyllabusChapter(BaseModel):
    name: str
    topics: list[SyllabusTopic]


class ParsedSyllabus(BaseModel):
    id: str
    name: str
    board: str | None = None
    grade: str | None = None
    subject: str | None = None
    chapters: list[SyllabusChapter]
    raw_text: str | None = None


class SyllabusParseResponse(BaseModel):
    syllabus: ParsedSyllabus
    confidence_score: float
    parsing_time_ms: int


SYSTEM_PROMPT = """You are an expert at analyzing educational syllabi from Indian schools (CBSE, ICSE, State Boards).
Your task is to extract structured information from syllabus documents.

RULES:
1. Identify the board (CBSE, ICSE, State Board) if mentioned
2. Identify the grade/class level
3. Identify the subject
4. Extract all chapters/units with their topics
5. Organize topics hierarchically when possible
6. If information is unclear, make reasonable inferences based on content
7. For partial syllabi, extract what's available

OUTPUT FORMAT (JSON only, no markdown):
{
  "name": "Syllabus name or subject name",
  "board": "CBSE/ICSE/State Board or null",
  "grade": "Class X" or null,
  "subject": "Mathematics/English/EVS/etc" or null,
  "chapters": [
    {
      "name": "Chapter 1: Chapter Name",
      "topics": [
        {
          "name": "Topic name",
          "subtopics": ["Subtopic 1", "Subtopic 2"]
        }
      ]
    }
  ],
  "confidence_score": 0.85
}

Be thorough in extracting all chapters and topics. Return confidence_score between 0-1 based on how complete and clear the syllabus content is."""


async def extract_text_from_pdf(file_content: bytes) -> str:
    """Extract text content from a PDF file."""
    try:
        pdf_reader = PdfReader(io.BytesIO(file_content))
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text.strip()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read PDF: {str(e)}")


async def extract_text_from_image(file_content: bytes, filename: str) -> str:
    """Use OpenAI Vision to extract text from an image."""
    import base64

    # Determine MIME type
    ext = filename.lower().split('.')[-1]
    mime_types = {
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        'gif': 'image/gif',
        'webp': 'image/webp'
    }
    mime_type = mime_types.get(ext, 'image/jpeg')

    base64_image = base64.b64encode(file_content).decode('utf-8')

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Extract all text from this syllabus image. Preserve the structure (chapters, topics, etc.) as much as possible. Return only the extracted text."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=4096
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process image: {str(e)}")


@router.post("/parse", response_model=SyllabusParseResponse)
async def parse_syllabus(
    file: UploadFile = File(...),
    grade_hint: str | None = Form(None),
    subject_hint: str | None = Form(None)
):
    """Parse an uploaded syllabus document (PDF, image, or text)."""
    start_time = datetime.now()

    # Read file content
    file_content = await file.read()
    filename = file.filename or "unknown"

    # Extract text based on file type
    ext = filename.lower().split('.')[-1]

    if ext == 'pdf':
        text = await extract_text_from_pdf(file_content)
    elif ext in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
        text = await extract_text_from_image(file_content, filename)
    elif ext in ['txt', 'text']:
        text = file_content.decode('utf-8')
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

    if not text or len(text.strip()) < 10:
        raise HTTPException(status_code=400, detail="Could not extract meaningful text from the file")

    # Build prompt with hints
    hints = ""
    if grade_hint:
        hints += f"\nHint: The grade level is likely {grade_hint}"
    if subject_hint:
        hints += f"\nHint: The subject is likely {subject_hint}"

    user_prompt = f"""Parse the following syllabus content and extract structured information.
{hints}

SYLLABUS CONTENT:
{text[:8000]}

Return ONLY valid JSON, no markdown."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
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

        # Parse JSON
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=500, detail=f"Failed to parse AI response: {str(e)}")

        # Build chapters
        chapters = []
        for ch in data.get("chapters", []):
            topics = []
            for t in ch.get("topics", []):
                if isinstance(t, str):
                    topics.append(SyllabusTopic(name=t))
                else:
                    topics.append(SyllabusTopic(
                        name=t.get("name", ""),
                        subtopics=t.get("subtopics")
                    ))
            chapters.append(SyllabusChapter(name=ch.get("name", ""), topics=topics))

        syllabus = ParsedSyllabus(
            id=str(uuid.uuid4()),
            name=data.get("name", "Uploaded Syllabus"),
            board=data.get("board"),
            grade=grade_hint or data.get("grade"),
            subject=subject_hint or data.get("subject"),
            chapters=chapters,
            raw_text=text[:2000]  # Store first 2000 chars for reference
        )

        end_time = datetime.now()
        parsing_time_ms = int((end_time - start_time).total_seconds() * 1000)

        return SyllabusParseResponse(
            syllabus=syllabus,
            confidence_score=data.get("confidence_score", 0.7),
            parsing_time_ms=parsing_time_ms
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse syllabus: {str(e)}")


@router.get("/{syllabus_id}")
async def get_syllabus(syllabus_id: str):
    """Get a parsed syllabus by ID."""
    # TODO: Implement retrieval from database
    return {"syllabus_id": syllabus_id, "message": "Not implemented yet - syllabus storage coming soon"}
