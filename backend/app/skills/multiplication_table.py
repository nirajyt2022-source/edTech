"""Multiplication table recall — SkillContract implementation."""

from .base import SkillContract
import random
import re


class MultiplicationTableRecallContract(SkillContract):
    skill_tag = "multiplication_table_recall"

    def build_variant(self, rng: random.Random, directive: dict | None = None):
        a = rng.randint(2, 10)
        b = rng.randint(2, 10)
        return {"a": a, "b": b}

    def validate(self, question: dict) -> list[str]:
        issues = []
        text = (question.get("question_text") or "").lower()

        # Extract multiplication pattern like "7 x 8" or "7 × 8"
        match = re.search(r"(\d+)\s*[x×*]\s*(\d+)", text)
        if not match:
            issues.append("no_multiplication_pattern")
            return issues

        a, b = int(match.group(1)), int(match.group(2))
        expected = a * b

        answer = question.get("answer")
        try:
            if int(answer) != expected:
                issues.append("incorrect_product")
        except Exception:
            issues.append("invalid_answer_format")

        return issues

    def repair(self, question: dict, rng: random.Random):
        # Deterministic repair via new variant
        variant = self.build_variant(rng)
        a, b = variant["a"], variant["b"]
        question["question_text"] = f"What is {a} × {b}?"
        question["answer"] = str(a * b)
        return question
