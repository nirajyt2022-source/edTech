from pydantic import BaseModel
from typing import Literal
from datetime import datetime


class Question(BaseModel):
    id: str
    type: Literal["multiple_choice", "fill_blank", "short_answer", "true_false", "matching"]
    text: str
    options: list[str] | None = None
    correct_answer: str | list[str] | None = None
    explanation: str | None = None
    difficulty: Literal["easy", "medium", "hard"]


class Worksheet(BaseModel):
    id: str
    title: str
    subject: str
    grade_level: str
    topic: str
    questions: list[Question]
    created_at: datetime
    updated_at: datetime


class WorksheetGenerationRequest(BaseModel):
    subject: str
    grade_level: str
    topic: str
    num_questions: int = 10
    question_types: list[Question.__annotations__["type"]] = ["multiple_choice"]
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    custom_instructions: str | None = None


class WorksheetGenerationResponse(BaseModel):
    worksheet: Worksheet
    generation_time_ms: int
