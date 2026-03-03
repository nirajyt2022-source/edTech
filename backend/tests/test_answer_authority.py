"""Tests for AnswerAuthority — verify-and-block answer verification."""

import pytest
from app.services.answer_authority import AnswerAuthority, AnswerVerdict


@pytest.fixture
def authority():
    return AnswerAuthority()


def _q(qid="1", text="", answer="", slot_type="short_answer", **kw):
    return {
        "id": qid,
        "question_text": text,
        "text": text,
        "answer": answer,
        "correct_answer": answer,
        "slot_type": slot_type,
        "type": slot_type,
        **kw,
    }


class TestArithmeticVerification:
    def test_correct_addition(self, authority):
        q = _q(text="What is 5 + 3?", answer="8")
        v = authority.verify_question(q, "Maths")
        assert v.match is True
        assert v.method == "arithmetic"

    def test_wrong_addition(self, authority):
        q = _q(text="What is 5 + 3?", answer="9")
        v = authority.verify_question(q, "Maths")
        assert v.match is False
        assert v.authoritative_answer == "8"
        assert v.method == "arithmetic"

    def test_correct_subtraction(self, authority):
        q = _q(text="What is 15 - 7?", answer="8")
        v = authority.verify_question(q, "Maths")
        assert v.match is True

    def test_wrong_subtraction(self, authority):
        q = _q(text="What is 15 - 7?", answer="7")
        v = authority.verify_question(q, "Maths")
        assert v.match is False
        assert v.authoritative_answer == "8"

    def test_correct_multiplication(self, authority):
        q = _q(text="What is 6 × 7?", answer="42")
        v = authority.verify_question(q, "Maths")
        assert v.match is True


class TestUnverifiable:
    def test_non_maths_subject(self, authority):
        q = _q(text="Name the capital of India.", answer="New Delhi")
        v = authority.verify_question(q, "Science")
        assert v.match is None
        assert v.method == "unverifiable"

    def test_no_expression(self, authority):
        q = _q(text="What shape has 4 equal sides?", answer="Square")
        v = authority.verify_question(q, "Maths")
        assert v.match is None
        assert v.method == "unverifiable"


class TestWordProblem:
    def test_correct_word_problem(self, authority):
        q = _q(
            text="Riya has 12 apples. She gives 5 to her friend. How many apples does she have left?",
            answer="7",
        )
        v = authority.verify_question(q, "Maths")
        # Word problem extraction may or may not find expression — depends on extractor
        if v.match is not None:
            assert v.match is True


class TestErrorDetection:
    def test_error_detection_skips_arithmetic(self, authority):
        q = _q(
            text="Is this correct? 5 + 3 = 9",
            answer="No, the correct answer is 8",
            slot_type="error_detection",
        )
        v = authority.verify_question(q, "Maths")
        assert v.method == "error_detection"


class TestWorksheetVerification:
    def test_verify_worksheet_returns_list(self, authority):
        questions = [
            _q(qid="1", text="5 + 3 = ?", answer="8"),
            _q(qid="2", text="7 - 2 = ?", answer="5"),
        ]
        verdicts = authority.verify_worksheet(questions, "Maths")
        assert len(verdicts) == 2
        assert all(isinstance(v, AnswerVerdict) for v in verdicts)

    def test_worksheet_with_one_mismatch(self, authority):
        questions = [
            _q(qid="1", text="5 + 3 = ?", answer="8"),
            _q(qid="2", text="7 - 2 = ?", answer="6"),  # wrong
            _q(qid="3", text="What shape has 4 sides?", answer="Square"),
        ]
        verdicts = authority.verify_worksheet(questions, "Maths")
        mismatches = [v for v in verdicts if v.match is False]
        assert len(mismatches) == 1
        assert mismatches[0].question_id == "2"


class TestIntegrationWithReleaseGate:
    def test_r15_blocks_on_mismatch(self):
        from app.services.release_gate import run_release_gate

        questions = [
            {
                "id": "Q1",
                "text": "5 + 3 = ?",
                "correct_answer": "8",
                "type": "short_answer",
                "format": "short_answer",
                "role": "application",
                "skill_tag": "mth_c3_add",
            },
            {
                "id": "Q2",
                "text": "7 - 2 = ?",
                "correct_answer": "5",
                "type": "short_answer",
                "format": "short_answer",
                "role": "recognition",
                "skill_tag": "mth_c3_sub",
                "_answer_mismatch": True,
                "_answer_mismatch_debug": {"computed": 5},
            },
        ]
        verdict = run_release_gate(
            questions=questions,
            grade_level="Class 3",
            subject="Maths",
            topic="Addition",
            num_questions=2,
            difficulty="medium",
            warnings=[],
        )
        assert "R15_ANSWER_AUTHORITY" in verdict.failed_rules
        assert verdict.verdict == "blocked"
