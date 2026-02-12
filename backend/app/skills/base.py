"""Base skill contract for worksheet question generation.

Every topic-specific skill (e.g. FractionHalf, ColumnAddition) should
subclass SkillContract and override the relevant methods.
"""

import random


class SkillContract:
    skill_tag: str = ""

    def build_variant(self, rng: random.Random, directive: dict | None = None) -> dict:
        return None

    def validate(self, question: dict) -> list[str]:
        return []

    def build_slots(self, question: dict) -> dict:
        return question

    def repair(self, question: dict, rng: random.Random) -> dict:
        return question

    def explain(self, question: dict) -> dict:
        """
        Deterministic explanation builder.
        Returns structured explanation:
        {
            "steps": [str, ...],
            "final_answer": str | None
        }
        """
        return {
            "steps": [],
            "final_answer": None,
        }

    def recommend_next(self, grade_result: dict) -> dict:
        """
        Adaptive recommendation based on grading result.
        Returns:
        {
            "next_skill_tag": str | None,
            "reason": str | None,
            "drill_focus": str | None
        }
        """
        return {
            "next_skill_tag": None,
            "reason": None,
            "drill_focus": None,
        }

    def generate_drill(self, drill_focus: str, rng):
        return None

    def grade(self, question: dict, student_answer: str) -> dict:
        """
        Deterministic grading hook.
        Returns structured feedback.
        Default: no grading logic.
        """
        return {
            "is_correct": None,
            "expected": None,
            "student": None,
            "place_errors": {},
            "error_type": None,
        }
