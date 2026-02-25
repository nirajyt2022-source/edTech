"""Column addition with carry — SkillContract implementation."""

import logging

from app.skills.math_utils import make_carry_pair

from .base import SkillContract

logger = logging.getLogger(__name__)


class ColumnAdditionContract(SkillContract):
    skill_tag = "column_add_with_carry"

    def build_variant(self, rng, directive: dict | None = None):
        if directive and not directive.get("carry_required"):
            return None
        a, b = make_carry_pair(rng, "addition")
        return {"numbers": (a, b), "operation": "addition"}

    def validate(self, question: dict) -> list[str]:
        issues = []

        spec = question.get("visual_spec") or {}
        if spec.get("model_id") != "BASE_TEN_REGROUPING":
            return issues

        # Ensure slots exist
        slots = question.get("_slots")
        if not slots:
            issues.append("slots_missing")
            return issues

        # Compute expected total from slots
        expected = slots["hundreds_sum"] * 100 + slots["tens_sum"] * 10 + slots["ones_sum"]

        # Validate numeric answer consistency (if present)
        answer = question.get("answer") or question.get("correct_answer")
        try:
            if answer is not None and int(answer) != expected:
                issues.append("answer_slot_mismatch")
        except Exception as e:
            logger.warning("Invalid answer format in column addition validate: %s", e)
            issues.append("invalid_answer_format")

        # Carry enforcement (if visual requires carry)
        carry = slots.get("carry_out", {})
        if any(v > 0 for v in carry.values()):
            # Carry occurred — ensure it was required for this skill
            pass  # column_add_with_carry expects carry

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

        ones_total = ones_a + ones_b
        carry_ones = ones_total // 10
        ones_sum = ones_total % 10

        tens_total = tens_a + tens_b + carry_ones
        carry_tens = tens_total // 10
        tens_sum = tens_total % 10

        hundreds_total = hundreds_a + hundreds_b + carry_tens
        carry_hundreds = hundreds_total // 10
        hundreds_sum = hundreds_total % 10

        question["_slots"] = {
            "ones_sum": ones_sum,
            "tens_sum": tens_sum,
            "hundreds_sum": hundreds_sum,
            "carry_out": {
                "ones": carry_ones,
                "tens": carry_tens,
                "hundreds": carry_hundreds,
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

        if error_type == "missed_carry":
            if place_errors.get("tens"):
                return {
                    "next_skill_tag": "column_add_with_carry",
                    "reason": "missed_carry_from_ones",
                    "drill_focus": "isolated_ones_carry",
                }

        return {
            "next_skill_tag": "column_add_with_carry",
            "reason": "reinforce_full_problem",
            "drill_focus": "full_regrouping",
        }

    def generate_drill(self, drill_focus: str, rng):
        from app.skills.math_utils import make_carry_pair

        if drill_focus == "isolated_ones_carry":
            # Force single-digit carry
            while True:
                a = rng.randint(5, 9)
                b = rng.randint(5, 9)
                if a + b >= 10:
                    return {
                        "skill_tag": "addition_isolated_ones_carry",
                        "numbers": (a, b),
                        "operation": "addition",
                    }

        if drill_focus == "reinforce_full_problem":
            a, b = make_carry_pair(rng, "addition")
            return {
                "skill_tag": "column_add_with_carry",
                "numbers": (a, b),
                "operation": "addition",
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

        ones_total = (a % 10) + (b % 10)
        carry_ones = slots["carry_out"]["ones"]
        tens_total = ((a // 10) % 10) + ((b // 10) % 10) + carry_ones
        carry_tens = slots["carry_out"]["tens"]

        steps = []

        steps.append(
            f"Ones: {a % 10} + {b % 10} = {ones_total} → write {slots['ones_sum']}"
            + (f", carry {carry_ones}" if carry_ones else "")
        )

        steps.append(
            f"Tens: {(a // 10) % 10} + {(b // 10) % 10}"
            + (f" + {carry_ones}" if carry_ones else "")
            + f" = {tens_total} → write {slots['tens_sum']}"
            + (f", carry {carry_tens}" if carry_tens else "")
        )

        steps.append(
            f"Hundreds: {(a // 100) % 10} + {(b // 100) % 10}"
            + (f" + {carry_tens}" if carry_tens else "")
            + f" = {slots['hundreds_sum']}"
        )

        final_answer = str(slots["hundreds_sum"] * 100 + slots["tens_sum"] * 10 + slots["ones_sum"])

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

        expected = slots["hundreds_sum"] * 100 + slots["tens_sum"] * 10 + slots["ones_sum"]

        try:
            student = int(student_answer)
        except Exception as e:
            logger.warning("Invalid student answer format in column addition grade: %s", e)
            result["error_type"] = "invalid_format"
            return result

        result["expected"] = expected
        result["student"] = student

        if student == expected:
            result["is_correct"] = True
            return result

        # Decompose student answer
        ones_s = student % 10
        tens_s = (student // 10) % 10
        hundreds_s = (student // 100) % 10

        result["place_errors"] = {
            "ones": ones_s != slots["ones_sum"],
            "tens": tens_s != slots["tens_sum"],
            "hundreds": hundreds_s != slots["hundreds_sum"],
        }

        # Detect missed carry from ones
        carry = slots.get("carry_out", {})
        if carry.get("ones", 0) == 1 and result["place_errors"]["tens"]:
            result["error_type"] = "missed_carry"
        else:
            result["error_type"] = "place_error"

        return result

    def repair(self, question: dict, rng):
        spec = question.get("visual_spec") or {}
        if spec.get("model_id") == "BASE_TEN_REGROUPING":
            a, b = make_carry_pair(rng, "addition")
            spec["numbers"] = [a, b]
        return question
