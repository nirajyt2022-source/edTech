"""Column subtraction with borrow — SkillContract implementation."""

from .base import SkillContract
from app.services.slot_engine import has_borrow, make_carry_pair
import random


class ColumnSubtractionWithBorrowContract(SkillContract):
    skill_tag = "column_sub_with_borrow"

    def build_variant(self, rng: random.Random, directive: dict | None = None):
        if directive and not directive.get("carry_required"):
            return None
        a, b = make_carry_pair(rng, "subtraction")
        return {"numbers": (a, b), "operation": "subtraction"}

    def validate(self, question: dict) -> list[str]:
        issues = []

        spec = question.get("visual_spec") or {}
        if spec.get("model_id") != "BASE_TEN_REGROUPING":
            return issues

        slots = question.get("_slots")
        if not slots:
            issues.append("slots_missing")
            return issues

        expected = (
            slots["hundreds_sum"] * 100
            + slots["tens_sum"] * 10
            + slots["ones_sum"]
        )

        answer = question.get("answer") or question.get("correct_answer")
        try:
            if answer is not None and int(answer) != expected:
                issues.append("answer_slot_mismatch")
        except Exception:
            issues.append("invalid_answer_format")

        return issues

    def build_slots(self, question: dict) -> dict:
        spec = question.get("visual_spec") or {}
        if spec.get("model_id") != "BASE_TEN_REGROUPING":
            return question

        nums = spec.get("numbers", [])
        if len(nums) != 2:
            return question

        a, b = nums

        ones_a, tens_a, hundreds_a = a % 10, (a // 10) % 10, (a // 100) % 10
        ones_b, tens_b, hundreds_b = b % 10, (b // 10) % 10, (b // 100) % 10

        borrow_ones = 0
        if ones_a < ones_b:
            ones_a += 10
            borrow_ones = 1
            tens_a -= 1

        ones_sum = ones_a - ones_b

        borrow_tens = 0
        if tens_a < tens_b:
            tens_a += 10
            borrow_tens = 1
            hundreds_a -= 1

        tens_sum = tens_a - tens_b
        hundreds_sum = hundreds_a - hundreds_b

        question["_slots"] = {
            "ones_sum": ones_sum,
            "tens_sum": tens_sum,
            "hundreds_sum": hundreds_sum,
            "carry_out": {
                "ones": borrow_ones,
                "tens": borrow_tens,
                "hundreds": 0,
            },
        }

        return question

    def recommend_next(self, grade_result: dict) -> dict:
        if grade_result.get("is_correct") is True:
            return {
                "next_skill_tag": None,
                "reason": "mastered",
                "drill_focus": None,
            }

        error_type = grade_result.get("error_type")
        place_errors = grade_result.get("place_errors") or {}

        if error_type == "missed_borrow":
            if place_errors.get("tens"):
                return {
                    "next_skill_tag": "column_sub_with_borrow",
                    "reason": "missed_borrow_from_tens",
                    "drill_focus": "isolated_tens_borrow",
                }

        return {
            "next_skill_tag": "column_sub_with_borrow",
            "reason": "reinforce_full_problem",
            "drill_focus": "full_borrow",
        }

    def generate_drill(self, drill_focus: str, rng):
        from app.services.slot_engine import make_carry_pair

        if drill_focus == "isolated_tens_borrow":
            # Force borrow from ones place
            while True:
                a = rng.randint(20, 99)
                b = rng.randint(10, 89)
                if a > b and (a % 10) < (b % 10):
                    return {
                        "skill_tag": "subtraction_isolated_tens_borrow",
                        "numbers": (a, b),
                        "operation": "subtraction",
                    }

        if drill_focus == "reinforce_full_problem":
            a, b = make_carry_pair(rng, "subtraction")
            return {
                "skill_tag": "column_sub_with_borrow",
                "numbers": (a, b),
                "operation": "subtraction",
            }

        return None

    def explain(self, question: dict) -> dict:
        spec = question.get("visual_spec") or {}
        if spec.get("model_id") != "BASE_TEN_REGROUPING":
            return {"steps": [], "final_answer": None}

        slots = question.get("_slots")
        if not slots:
            question = self.build_slots(question)
            slots = question.get("_slots") or {}

        nums = spec.get("numbers", [])
        if len(nums) != 2:
            return {"steps": [], "final_answer": None}

        a, b = nums

        borrow_ones = slots["carry_out"]["ones"]
        borrow_tens = slots["carry_out"]["tens"]

        steps = []

        steps.append(
            f"Ones: {a % 10} − {b % 10}"
            + (" (borrow 1 from tens)" if borrow_ones else "")
            + f" → {slots['ones_sum']}"
        )

        steps.append(
            f"Tens: {(a // 10) % 10} − {(b // 10) % 10}"
            + (" (borrow 1 from hundreds)" if borrow_tens else "")
            + f" → {slots['tens_sum']}"
        )

        steps.append(
            f"Hundreds: {(a // 100) % 10} − {(b // 100) % 10}"
            + f" → {slots['hundreds_sum']}"
        )

        final_answer = str(
            slots["hundreds_sum"] * 100
            + slots["tens_sum"] * 10
            + slots["ones_sum"]
        )

        return {
            "steps": steps,
            "final_answer": final_answer,
        }

    def grade(self, question: dict, student_answer: str) -> dict:
        slots = question.get("_slots") or {}
        result = {
            "is_correct": False,
            "expected": None,
            "student": None,
            "place_errors": {},
            "error_type": None,
        }

        if not slots:
            return result

        expected = (
            slots["hundreds_sum"] * 100
            + slots["tens_sum"] * 10
            + slots["ones_sum"]
        )

        try:
            student = int(student_answer)
        except Exception:
            result["error_type"] = "invalid_format"
            return result

        result["expected"] = expected
        result["student"] = student

        if student == expected:
            result["is_correct"] = True
            return result

        ones_s = student % 10
        tens_s = (student // 10) % 10
        hundreds_s = (student // 100) % 10

        result["place_errors"] = {
            "ones": ones_s != slots["ones_sum"],
            "tens": tens_s != slots["tens_sum"],
            "hundreds": hundreds_s != slots["hundreds_sum"],
        }

        borrow = slots.get("carry_out", {})
        if borrow.get("ones", 0) == 1 and result["place_errors"]["tens"]:
            result["error_type"] = "missed_borrow"
        else:
            result["error_type"] = "place_error"

        return result

    def repair(self, question: dict, rng: random.Random):
        spec = question.get("visual_spec") or {}
        if spec.get("model_id") == "BASE_TEN_REGROUPING":
            a, b = make_carry_pair(rng, "subtraction")
            spec["numbers"] = [a, b]
        return question
