from pydantic import BaseModel
from typing import Any, Optional


class GradeResult(BaseModel):
    is_correct: Optional[bool] = None
    expected: Optional[Any] = None
    student: Optional[Any] = None
    place_errors: dict[str, bool] = {}
    error_type: Optional[str] = None


class ExplainResult(BaseModel):
    steps: list[str] = []
    final_answer: Optional[str] = None


class RecommendResult(BaseModel):
    next_skill_tag: Optional[str] = None
    reason: Optional[str] = None
    drill_focus: Optional[str] = None


class NextBlock(BaseModel):
    action: str = "stop"
    streak: int = 0
    target: int = 3
    reason: Optional[str] = None
    next_question: Optional[dict] = None


class MasteryStateDTO(BaseModel):
    student_id: str
    skill_tag: str
    streak: int = 0
    total_attempts: int = 0
    correct_attempts: int = 0
    last_error_type: Optional[str] = None
    mastery_level: str = "unknown"
    updated_at: Optional[float] = None
    topic: Optional[str] = None


class AttemptResponse(BaseModel):
    grade_result: GradeResult
    explanation: Any  # keep flexible: could be list[str] or dict, depending on your contract
    recommendation: dict
    next: NextBlock
    mastery_state: Optional[dict] = None


class MasteryGetResponse(BaseModel):
    student_id: str
    states: list[dict]


class TopicSummaryResponse(BaseModel):
    student_id: str
    topic: str
    skills_total: int
    mastered: int
    improving: int
    learning: int
    skills: list[dict]


class ResetResponse(BaseModel):
    ok: bool = True


# ──────────────────────────────────────────────
# Endpoint-level response schemas
# ──────────────────────────────────────────────

class GenerateResponse(BaseModel):
    worksheet: dict
    generation_time_ms: int


class GradeResponse(BaseModel):
    is_correct: Optional[bool] = None
    expected: Optional[Any] = None
    student: Optional[Any] = None
    place_errors: dict[str, bool] = {}
    error_type: Optional[str] = None


class ExplainResponse(BaseModel):
    steps: list[str] = []
    final_answer: Optional[str] = None


class RecommendResponse(BaseModel):
    next_skill_tag: Optional[str] = None
    reason: Optional[str] = None
    drill_focus: Optional[str] = None


class DrillResponse(BaseModel):
    skill_tag: Optional[str] = None
    numbers: Optional[Any] = None
    operation: Optional[str] = None
