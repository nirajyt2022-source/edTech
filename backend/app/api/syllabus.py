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
async def get_syllabus_by_id(syllabus_id: str):
    """Get a parsed syllabus by ID."""
    # TODO: Implement retrieval from database
    return {"syllabus_id": syllabus_id, "message": "Not implemented yet - syllabus storage coming soon"}


# ────────────────────────────────────────────────────────────
# Hardcoded CBSE syllabus — deterministic, no DB needed
# ────────────────────────────────────────────────────────────

_CBSE_SYLLABUS: dict[str, dict[str, list[dict]]] = {
    "Class 1": {
        "Mathematics": [
            {"id": "c1m1", "title": "Shapes and Space", "topics": ["Shapes around us", "Patterns"]},
            {"id": "c1m2", "title": "Numbers from One to Nine", "topics": ["Counting", "Number names 1-9"]},
            {"id": "c1m3", "title": "Addition", "topics": ["Addition up to 9", "Word problems"]},
            {"id": "c1m4", "title": "Subtraction", "topics": ["Subtraction up to 9", "Taking away"]},
            {"id": "c1m5", "title": "Numbers from Ten to Twenty", "topics": ["Place value", "Counting 10-20"]},
            {"id": "c1m6", "title": "Time", "topics": ["Before and after", "Days of the week"]},
            {"id": "c1m7", "title": "Measurement", "topics": ["Long and short", "Heavy and light"]},
            {"id": "c1m8", "title": "Numbers up to 100", "topics": ["Counting to 100", "Number names"]},
            {"id": "c1m9", "title": "Money", "topics": ["Coins", "Notes"]},
            {"id": "c1m10", "title": "How Many", "topics": ["Counting objects", "Comparing quantities"]},
        ],
        "English": [
            {"id": "c1e1", "title": "A Happy Child (Marigold)", "topics": ["Poem recitation", "Rhyming words"]},
            {"id": "c1e2", "title": "Three Little Pigs", "topics": ["Story comprehension", "Sequencing"]},
            {"id": "c1e3", "title": "After a Bath (Poem)", "topics": ["Action words", "Vocabulary"]},
            {"id": "c1e4", "title": "One Little Kitten", "topics": ["Animal words", "Counting"]},
            {"id": "c1e5", "title": "Bubbles (Poem)", "topics": ["Describing words", "Colours"]},
            {"id": "c1e6", "title": "Lalu and Peelu", "topics": ["Dialogue", "Food words"]},
            {"id": "c1e7", "title": "Alphabet", "topics": ["Capital letters", "Small letters", "Phonics"]},
            {"id": "c1e8", "title": "Basic Words", "topics": ["Three letter words", "Sight words"]},
        ],
    },
    "Class 2": {
        "Mathematics": [
            {"id": "c2m1", "title": "What is Long, What is Round?", "topics": ["3D shapes", "Rolling and sliding"]},
            {"id": "c2m2", "title": "Counting in Groups", "topics": ["Skip counting by 2, 5, 10", "Place value"]},
            {"id": "c2m3", "title": "How Much Can You Carry?", "topics": ["Weight comparison", "Heavier and lighter"]},
            {"id": "c2m4", "title": "Counting in Tens", "topics": ["Tens and ones", "Numbers up to 100"]},
            {"id": "c2m5", "title": "Patterns", "topics": ["Shape patterns", "Number patterns"]},
            {"id": "c2m6", "title": "Footprints", "topics": ["Measurement", "Non-standard units"]},
            {"id": "c2m7", "title": "Jugs and Mugs", "topics": ["Capacity", "Comparing volumes"]},
            {"id": "c2m8", "title": "Tens and Ones", "topics": ["2-digit addition", "2-digit subtraction"]},
            {"id": "c2m9", "title": "My Funday", "topics": ["Calendar", "Days and months"]},
            {"id": "c2m10", "title": "Add our Points", "topics": ["Addition with carrying", "Word problems"]},
            {"id": "c2m11", "title": "Lines and Lines", "topics": ["Straight lines", "Curved lines"]},
            {"id": "c2m12", "title": "Give and Take", "topics": ["Subtraction with borrowing", "Word problems"]},
            {"id": "c2m13", "title": "The Longest Step", "topics": ["Standard measurement", "Centimeters"]},
            {"id": "c2m14", "title": "Birds Come, Birds Go", "topics": ["Data handling", "Pictographs"]},
            {"id": "c2m15", "title": "How Many Ponytails?", "topics": ["Data collection", "Tally marks"]},
        ],
        "English": [
            {"id": "c2e1", "title": "First Day at School (Marigold)", "topics": ["Comprehension", "Feelings"]},
            {"id": "c2e2", "title": "Haldi's Adventure", "topics": ["Story elements", "Sequencing"]},
            {"id": "c2e3", "title": "I am Lucky (Poem)", "topics": ["Rhyme", "Gratitude"]},
            {"id": "c2e4", "title": "I Want (Poem)", "topics": ["Wishes", "Describing words"]},
            {"id": "c2e5", "title": "Nouns and Pronouns", "topics": ["Naming words", "He/She/It/They"]},
            {"id": "c2e6", "title": "Verbs and Tenses", "topics": ["Action words", "Is/Am/Are"]},
            {"id": "c2e7", "title": "Sentence Writing", "topics": ["Capital letters", "Full stops"]},
        ],
    },
    "Class 3": {
        "Mathematics": [
            {"id": "c3m1", "title": "Where to Look From", "topics": ["Shapes and perspectives", "Top/front/side view"]},
            {"id": "c3m2", "title": "Fun with Numbers", "topics": ["Numbers up to 1000", "Place value", "Comparison"]},
            {"id": "c3m3", "title": "Give and Take", "topics": ["Addition with carry", "Subtraction with borrow"]},
            {"id": "c3m4", "title": "Long and Short", "topics": ["Measurement", "Meters and centimeters"]},
            {"id": "c3m5", "title": "Shapes and Designs", "topics": ["Symmetry", "Patterns", "Tiling"]},
            {"id": "c3m6", "title": "Fun with Give and Take", "topics": ["Mental math", "Estimation"]},
            {"id": "c3m7", "title": "Time Goes On", "topics": ["Reading clock", "Calendar", "AM/PM"]},
            {"id": "c3m8", "title": "Who is Heavier?", "topics": ["Weight", "Kilograms and grams"]},
            {"id": "c3m9", "title": "How Many Times?", "topics": ["Multiplication tables 2-10", "Word problems"]},
            {"id": "c3m10", "title": "Play with Patterns", "topics": ["Number patterns", "Growing patterns"]},
            {"id": "c3m11", "title": "Jugs and Mugs", "topics": ["Capacity", "Liters and milliliters"]},
            {"id": "c3m12", "title": "Can We Share?", "topics": ["Division basics", "Equal sharing"]},
            {"id": "c3m13", "title": "Smart Charts", "topics": ["Data handling", "Pictographs", "Bar graphs"]},
            {"id": "c3m14", "title": "Rupees and Paise", "topics": ["Money", "Bills and change"]},
        ],
        "English": [
            {"id": "c3e1", "title": "Good Morning (Marigold)", "topics": ["Poem", "Greetings"]},
            {"id": "c3e2", "title": "The Magic Garden", "topics": ["Story comprehension", "Vocabulary"]},
            {"id": "c3e3", "title": "Bird Talk (Poem)", "topics": ["Rhyming", "Nature"]},
            {"id": "c3e4", "title": "Nina and the Baby Sparrows", "topics": ["Empathy", "Story elements"]},
            {"id": "c3e5", "title": "Grammar", "topics": ["Nouns", "Pronouns", "Verbs", "Adjectives", "Articles"]},
            {"id": "c3e6", "title": "Writing Skills", "topics": ["Paragraph writing", "Letter writing"]},
            {"id": "c3e7", "title": "Vocabulary", "topics": ["Synonyms", "Antonyms", "Homophones"]},
        ],
    },
    "Class 4": {
        "Mathematics": [
            {"id": "c4m1", "title": "Building with Bricks", "topics": ["Shapes", "Patterns", "Tiling"]},
            {"id": "c4m2", "title": "Long and Short", "topics": ["Length", "Kilometers", "Conversion"]},
            {"id": "c4m3", "title": "A Trip to Bhopal", "topics": ["Large numbers", "Tickets", "Money"]},
            {"id": "c4m4", "title": "Tick Tick Tick", "topics": ["Time", "24-hour clock", "Duration"]},
            {"id": "c4m5", "title": "The Way the World Looks", "topics": ["Maps", "Perspectives"]},
            {"id": "c4m6", "title": "The Junk Seller", "topics": ["Multiplication", "Large numbers"]},
            {"id": "c4m7", "title": "Jugs and Mugs", "topics": ["Volume", "Capacity", "Liters"]},
            {"id": "c4m8", "title": "Carts and Wheels", "topics": ["Circles", "Radius", "Diameter"]},
            {"id": "c4m9", "title": "Halves and Quarters", "topics": ["Fractions", "Equivalent fractions"]},
            {"id": "c4m10", "title": "Play with Patterns", "topics": ["Number patterns", "Magic squares"]},
            {"id": "c4m11", "title": "Tables and Shares", "topics": ["Division", "Long division"]},
            {"id": "c4m12", "title": "How Heavy? How Light?", "topics": ["Weight", "Conversion"]},
            {"id": "c4m13", "title": "Fields and Fences", "topics": ["Perimeter", "Area"]},
            {"id": "c4m14", "title": "Smart Charts", "topics": ["Data handling", "Bar graphs"]},
        ],
        "English": [
            {"id": "c4e1", "title": "Wake Up! (Marigold)", "topics": ["Poem", "Nature"]},
            {"id": "c4e2", "title": "Neha's Alarm Clock", "topics": ["Story comprehension", "Daily routine"]},
            {"id": "c4e3", "title": "Noses (Poem)", "topics": ["Senses", "Descriptive words"]},
            {"id": "c4e4", "title": "The Little Fir Tree", "topics": ["Moral story", "Wishes"]},
            {"id": "c4e5", "title": "Grammar", "topics": ["Tenses", "Conjunctions", "Prepositions", "Adverbs"]},
            {"id": "c4e6", "title": "Writing Skills", "topics": ["Essay writing", "Letter writing", "Story writing"]},
            {"id": "c4e7", "title": "Vocabulary", "topics": ["Prefixes", "Suffixes", "Idioms"]},
        ],
    },
    "Class 5": {
        "Mathematics": [
            {"id": "c5m1", "title": "The Fish Tale", "topics": ["Large numbers", "Lakhs", "Indian system"]},
            {"id": "c5m2", "title": "Shapes and Angles", "topics": ["Angles", "Types of angles", "Measuring"]},
            {"id": "c5m3", "title": "How Many Squares?", "topics": ["Area", "Perimeter", "Counting squares"]},
            {"id": "c5m4", "title": "Parts and Wholes", "topics": ["Fractions", "Equivalent fractions"]},
            {"id": "c5m5", "title": "Does it Look the Same?", "topics": ["Symmetry", "Reflection", "Rotation"]},
            {"id": "c5m6", "title": "Be My Multiple, I'll Be Your Factor", "topics": ["Factors", "Multiples", "HCF", "LCM"]},
            {"id": "c5m7", "title": "Can You See the Pattern?", "topics": ["Number patterns", "Magic squares"]},
            {"id": "c5m8", "title": "Mapping Your Way", "topics": ["Maps", "Scale", "Directions"]},
            {"id": "c5m9", "title": "Boxes and Sketches", "topics": ["3D shapes", "Nets", "Faces/edges/vertices"]},
            {"id": "c5m10", "title": "Tenths and Hundredths", "topics": ["Decimals", "Place value"]},
            {"id": "c5m11", "title": "Area and Its Boundary", "topics": ["Area", "Irregular shapes"]},
            {"id": "c5m12", "title": "Smart Charts", "topics": ["Data handling", "Pie charts", "Bar graphs"]},
            {"id": "c5m13", "title": "Ways to Multiply and Divide", "topics": ["Long multiplication", "Long division"]},
            {"id": "c5m14", "title": "How Big? How Heavy?", "topics": ["Volume", "Weight", "Conversion"]},
        ],
        "English": [
            {"id": "c5e1", "title": "Ice-cream Man (Marigold)", "topics": ["Poem", "Seasons"]},
            {"id": "c5e2", "title": "Wonderful Waste", "topics": ["Recycling", "Comprehension"]},
            {"id": "c5e3", "title": "Teamwork (Poem)", "topics": ["Cooperation", "Values"]},
            {"id": "c5e4", "title": "Flying Together", "topics": ["Story", "Unity"]},
            {"id": "c5e5", "title": "Grammar", "topics": ["Tenses", "Voice", "Direct/Indirect speech", "Clauses"]},
            {"id": "c5e6", "title": "Writing Skills", "topics": ["Essays", "Letters", "Diary entry", "Notice"]},
            {"id": "c5e7", "title": "Vocabulary", "topics": ["Word formation", "Proverbs", "Compound words"]},
        ],
    },
}

# Subject aliases for flexible lookups
_SUBJECT_ALIASES: dict[str, str] = {
    "maths": "Mathematics",
    "math": "Mathematics",
    "mathematics": "Mathematics",
    "english": "English",
}


@router.get("/cbse/{grade}/{subject}")
async def get_syllabus(grade: str, subject: str):
    """Get hardcoded CBSE syllabus for a grade and subject. No DB required."""
    # Normalize grade: "3" -> "Class 3", "Class 3" stays
    normalized_grade = grade if grade.startswith("Class") else f"Class {grade}"

    # Normalize subject
    normalized_subject = _SUBJECT_ALIASES.get(subject.lower(), subject)

    if normalized_grade not in _CBSE_SYLLABUS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported grade: {grade}. Supported: Class 1-5"
        )

    grade_data = _CBSE_SYLLABUS[normalized_grade]
    if normalized_subject not in grade_data:
        available = ", ".join(grade_data.keys())
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported subject '{subject}' for {normalized_grade}. Available: {available}"
        )

    return {
        "grade": normalized_grade,
        "subject": normalized_subject,
        "chapters": grade_data[normalized_subject],
    }
