"""Column addition with carry — SkillContract implementation."""

from .base import SkillContract
from app.services.slot_engine import has_carry, make_carry_pair


class ColumnAdditionContract(SkillContract):
    skill_tag = "column_add_with_carry"

    def build_variant(self, rng):
        a, b = make_carry_pair(rng, "addition")
        return {"numbers": (a, b), "operation": "addition"}

    def validate(self, question: dict) -> list[str]:
        issues = []
        spec = question.get("visual_spec") or {}
        if spec.get("model_id") == "BASE_TEN_REGROUPING":
            nums = spec.get("numbers")
            if nums and len(nums) == 2:
                a, b = nums
                if not has_carry(a, b):
                    issues.append("carry_missing")
        return issues

    def repair(self, question: dict, rng):
        spec = question.get("visual_spec") or {}
        if spec.get("model_id") == "BASE_TEN_REGROUPING":
            a, b = make_carry_pair(rng, "addition")
            spec["numbers"] = [a, b]
        return question
