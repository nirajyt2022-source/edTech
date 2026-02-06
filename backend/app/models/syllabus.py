from pydantic import BaseModel
from datetime import datetime


class SyllabusUnit(BaseModel):
    name: str
    topics: list[str]
    estimated_weeks: int | None = None


class Syllabus(BaseModel):
    id: str
    name: str
    subject: str
    grade_level: str
    units: list[SyllabusUnit]
    created_at: datetime


class SyllabusParseRequest(BaseModel):
    file_content: str  # Base64 encoded file or raw text
    file_type: str = "pdf"  # pdf, docx, or txt


class SyllabusParseResponse(BaseModel):
    syllabus: Syllabus
    confidence_score: float
