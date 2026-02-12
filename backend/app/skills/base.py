"""Base skill contract for worksheet question generation.

Every topic-specific skill (e.g. FractionHalf, ColumnAddition) should
subclass SkillContract and override the relevant methods.
"""

import random


class SkillContract:
    skill_tag: str = ""

    def build_variant(self, rng: random.Random) -> dict:
        raise NotImplementedError

    def validate(self, question: dict) -> list[str]:
        return []

    def build_slots(self, question: dict) -> dict:
        return question

    def repair(self, question: dict, rng: random.Random) -> dict:
        return question
