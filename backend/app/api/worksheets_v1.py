from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from app.api.models_practice import (
    AttemptResponse,
    MasteryGetResponse,
    TopicSummaryResponse,
    ResetResponse,
)

from app.services.slot_engine import attempt_and_next
from app.services.mastery_dashboard import get_mastery, topic_summary, reset_skill

router = APIRouter(prefix="/api/v1/worksheets", tags=["worksheets-v1"])


class AttemptPayloadV1(BaseModel):
    student_id: Optional[str] = None
    question: dict
    student_answer: str
    mode: str = "single"   # keep same default
    seed: Optional[int] = None


@router.post("/attempt", response_model=AttemptResponse)
def attempt_v1(payload: AttemptPayloadV1):
    # pass through exactly; attempt_and_next already tolerates extra fields
    return attempt_and_next(payload.model_dump())


@router.get("/mastery/get", response_model=MasteryGetResponse)
def mastery_get_v1(student_id: str):
    return {"student_id": student_id, "states": get_mastery(student_id)}


@router.get("/mastery/topic_summary", response_model=TopicSummaryResponse)
def mastery_topic_summary_v1(student_id: str, topic: str):
    return topic_summary(student_id, topic)


class MasteryResetRequestV1(BaseModel):
    student_id: str
    skill_tag: str


@router.post("/mastery/reset", response_model=ResetResponse)
def mastery_reset_v1(req: MasteryResetRequestV1):
    return reset_skill(req.student_id, req.skill_tag)
