"""
Worksheet API models — shared between v2 endpoint and other services.
Extracted from app/api/worksheets.py.
"""
from __future__ import annotations

from pydantic import BaseModel, model_validator
from typing import Literal


class MixRecipeItem(BaseModel):
    skill_tag: str
    count: int
    visual_type: str | None = None
    require_student_answer: bool = False
    unique_contexts: bool = False


class WorksheetConstraints(BaseModel):
    carry_required: bool = False
    allow_operations: list[str] | None = None


class WorksheetGenerationRequest(BaseModel):
    board: str
    grade_level: str
    subject: str
    topic: str
    difficulty: Literal["easy", "medium", "hard"]
    num_questions: int = 10
    language: str = "English"
    custom_instructions: str | None = None
    skills: list[str] | None = None
    logic_tags: list[str] | None = None
    region: str = "India"
    problem_style: Literal["standard", "visual", "mixed"] = "standard"
    # v7.0: focused worksheet controls
    focus_skill: str | None = None
    support_skills: list[str] | None = None
    mix_recipe: list[MixRecipeItem] | None = None
    constraints: WorksheetConstraints | None = None
    visuals_only: bool = False
    min_visual_ratio: float | None = None
    child_id: str | None = None  # Gold-G2: mastery-aware slot adjustment
    # Frontend selections previously silently dropped
    problem_type: str | None = None   # "visual only" | "standard" | "mixed"
    visual_theme: str | None = None   # "color" | "black_and_white" | "minimal"

    @model_validator(mode="after")
    def _map_problem_type(self) -> "WorksheetGenerationRequest":
        if self.problem_type:
            pt = self.problem_type.lower().strip()
            if "visual" in pt and "only" in pt:
                self.visuals_only = True
                self.problem_style = "visual"
            elif "mixed" in pt:
                self.problem_style = "mixed"
        return self


class Question(BaseModel):
    id: str
    type: str
    text: str
    options: list[str] | None = None
    correct_answer: str | None = None
    explanation: str | None = None
    difficulty: str | None = None
    answer_type: str | None = None
    sample_answer: str | None = None
    grading_notes: str | None = None
    visual_type: str | None = None
    visual_data: dict | None = None
    role: str | None = None  # Phase 4: pedagogical role
    skill_tag: str | None = None  # Phase 5: skill diagnostic tag
    is_bonus: bool = False  # Phase 2: bonus challenge question flag
    is_fallback: bool = False  # True when LLM failed all generation attempts and a stub was inserted
    hint: str | None = None  # Optional hint (separate from question_text)
    images: list[dict] | None = None  # [{path, alt, category}] — cartoon images for EVS/Science
    format: str = "short_answer"  # PDF render format: fill_blank|mcq_3|mcq_4|vertical_sum|true_false|short_answer


class Worksheet(BaseModel):
    title: str
    grade: str
    subject: str
    topic: str
    difficulty: str
    language: str
    questions: list[Question]
    skill_focus: str = ""
    common_mistake: str = ""
    parent_tip: str = ""
    learning_objectives: list[str] = []
    mastery_snapshot: dict | None = None  # Gold-G2: child's mastery state at generation time


class WorksheetGenerationResponse(BaseModel):
    worksheet: Worksheet
    generation_time_ms: int
    warnings: dict | None = None
    verdict: str = "ok"
    worksheets: list[Worksheet] | None = None
    capped_q_count: int | None = None  # Set if q_count was reduced due to topic limit
