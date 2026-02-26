"""Tests for AI output validation."""
import pytest

from app.services.output_validator import OutputValidator


@pytest.fixture
def validator():
    return OutputValidator()

class TestWorksheetValidation:
    def test_valid_worksheet(self, validator):
        data = {
            "questions": [
                {"id": "Q1", "type": "mcq", "text": "What is 2+2?", "options": ["3","4","5","6"], "correct_answer": "4"},
                {"id": "Q2", "type": "fill_blank", "text": "5+3 = ?", "correct_answer": "8"},
            ],
            "answer_key": {"Q1": "4", "Q2": "8"},
        }
        is_valid, errors = validator.validate_worksheet(data, num_questions=2)
        assert is_valid
        assert len(errors) == 0

    def test_too_few_questions(self, validator):
        data = {"questions": [{"id": "Q1", "type": "mcq", "text": "test", "options": ["a","b","c"], "correct_answer": "a"}]}
        is_valid, errors = validator.validate_worksheet(data, num_questions=10)
        assert not is_valid
        assert any("Too few" in e for e in errors)

    def test_missing_answer(self, validator):
        data = {"questions": [{"id": "Q1", "type": "mcq", "text": "test", "options": ["a","b","c"]}]}
        is_valid, errors = validator.validate_worksheet(data, num_questions=1)
        assert not is_valid
        assert any("missing correct_answer" in e for e in errors)

    def test_duplicate_questions(self, validator):
        data = {"questions": [
            {"id": "Q1", "type": "fill_blank", "text": "What is 2+2?", "correct_answer": "4"},
            {"id": "Q2", "type": "fill_blank", "text": "What is 2+2?", "correct_answer": "4"},
        ]}
        is_valid, errors = validator.validate_worksheet(data, num_questions=2)
        assert not is_valid
        assert any("Duplicate" in e for e in errors)

    def test_true_false_invalid_answer(self, validator):
        data = {"questions": [{"id": "Q1", "type": "true_false", "text": "Sky is blue", "correct_answer": "yes"}]}
        is_valid, errors = validator.validate_worksheet(data, num_questions=1)
        assert not is_valid
        assert any("true_false" in e for e in errors)

    def test_math_verification_correct(self, validator):
        result = validator._verify_math_answer({"text": "What is 25 + 17?", "correct_answer": "42", "type": "fill_blank"})
        assert result is True

    def test_math_verification_wrong(self, validator):
        result = validator._verify_math_answer({"text": "What is 25 + 17?", "correct_answer": "43", "type": "fill_blank"})
        assert result is False

    def test_grade_complexity_check(self, validator):
        data = {"questions": [
            {"id": "Q1", "type": "short_answer", "text": "Determine and evaluate the hypothesis of this consequently illustrated phenomenon", "correct_answer": "test"}
        ]}
        is_valid, errors = validator.validate_worksheet(data, grade="Class 1", num_questions=1)
        assert not is_valid
        assert any("complex vocabulary" in e for e in errors)

    def test_mcq_answer_not_in_options(self, validator):
        data = {"questions": [
            {"id": "Q1", "type": "mcq", "text": "Pick one", "options": ["A", "B", "C", "D"], "correct_answer": "Z"}
        ]}
        is_valid, errors = validator.validate_worksheet(data, num_questions=1)
        assert not is_valid
        assert any("not in options" in e for e in errors)

    def test_empty_text(self, validator):
        data = {"questions": [
            {"id": "Q1", "type": "short_answer", "text": "", "correct_answer": "test"}
        ]}
        is_valid, errors = validator.validate_worksheet(data, num_questions=1)
        assert not is_valid
        assert any("empty question text" in e for e in errors)


    def test_near_duplicate_detection_flags(self, validator):
        """5/10 questions with same pattern (only names differ) should flag."""
        questions = []
        names = ["Aarav", "Priya", "Rohan", "Diya", "Kabir"]
        # 5 near-duplicates: only the name changes
        for i, name in enumerate(names):
            questions.append({
                "id": f"Q{i+1}", "type": "word_problem",
                "text": f"{name} goes to the market and buys 5 apples for ₹10 each. How much does {name} pay?",
                "correct_answer": "₹50",
            })
        # 5 diverse questions
        questions.append({"id": "Q6", "type": "mcq", "text": "What is 2+2?", "options": ["3","4","5","6"], "correct_answer": "4"})
        questions.append({"id": "Q7", "type": "fill_blank", "text": "15 - 7 = ______", "correct_answer": "8"})
        questions.append({"id": "Q8", "type": "true_false", "text": "True or False: 5 × 3 = 15", "options": ["True","False"], "correct_answer": "True"})
        questions.append({"id": "Q9", "type": "short_answer", "text": "Name a 3-digit number", "correct_answer": "100"})
        questions.append({"id": "Q10", "type": "error_detection", "text": "Find the mistake: 25+18=42", "correct_answer": "43"})

        data = {"questions": questions}
        is_valid, errors = validator.validate_worksheet(data, num_questions=10)
        assert any("Near-duplicate" in e for e in errors)

    def test_near_duplicate_detection_passes_diverse(self, validator):
        """4 diverse questions should pass near-duplicate check."""
        data = {"questions": [
            {"id": "Q1", "type": "mcq", "text": "What time does the clock show?", "options": ["3:00","4:00","5:00","6:00"], "correct_answer": "3:00"},
            {"id": "Q2", "type": "word_problem", "text": "Aarav starts homework at 4:30 PM and finishes at 5:15 PM. How long did it take?", "correct_answer": "45 minutes"},
            {"id": "Q3", "type": "fill_blank", "text": "1 hour = ______ minutes", "correct_answer": "60"},
            {"id": "Q4", "type": "true_false", "text": "True or False: 90 minutes = 1 hour 30 minutes", "options": ["True","False"], "correct_answer": "True"},
        ]}
        is_valid, errors = validator.validate_worksheet(data, num_questions=4)
        assert not any("Near-duplicate" in e for e in errors)

    def test_make_template(self, validator):
        """_make_template should normalize names, numbers, and times."""
        text1 = "Aarav goes to school at 8:30 AM and comes back at 3:15 PM"
        text2 = "Priya goes to school at 9:00 AM and comes back at 2:45 PM"
        assert validator._make_template(text1) == validator._make_template(text2)


class TestVisualAnswerCoherence:
    def test_clock_match(self, validator):
        q = {
            "id": "Q1", "type": "mcq", "text": "What time does the clock show?",
            "options": ["3:30", "4:00", "3:00", "4:30"],
            "correct_answer": "3:30",
            "visual_type": "clock",
            "visual_data": {"hour": 3, "minute": 30},
        }
        result = validator._verify_clock_answer(q)
        assert result is True

    def test_clock_mismatch(self, validator):
        q = {
            "id": "Q1", "type": "mcq", "text": "What time does the clock show?",
            "options": ["3:30", "4:00", "3:00", "4:30"],
            "correct_answer": "3:30",
            "visual_type": "clock",
            "visual_data": {"hour": 4, "minute": 0},
        }
        result = validator._verify_clock_answer(q)
        assert result is False

    def test_clock_mismatch_in_worksheet(self, validator):
        """Clock mismatch should produce an error in validate_worksheet."""
        data = {"questions": [{
            "id": "Q1", "type": "mcq", "text": "What time?",
            "options": ["3:30", "4:00"], "correct_answer": "3:30",
            "visual_type": "clock",
            "visual_data": {"hour": 4, "minute": 0},
        }]}
        is_valid, errors = validator.validate_worksheet(data, num_questions=1)
        assert not is_valid
        assert any("visual data does not match" in e for e in errors)

    def test_object_group_match(self, validator):
        q = {
            "id": "Q1", "type": "short_answer",
            "text": "Count the total objects.",
            "correct_answer": "8",
            "visual_type": "object_group",
            "visual_data": {"groups": [{"count": 5}, {"count": 3}], "operation": "+"},
        }
        result = validator._verify_object_group_answer(q)
        assert result is True

    def test_object_group_mismatch(self, validator):
        q = {
            "id": "Q1", "type": "short_answer",
            "text": "Count the total objects.",
            "correct_answer": "7",
            "visual_type": "object_group",
            "visual_data": {"groups": [{"count": 5}, {"count": 3}], "operation": "+"},
        }
        result = validator._verify_object_group_answer(q)
        assert result is False

    def test_object_group_subtraction(self, validator):
        q = {
            "id": "Q1", "type": "short_answer",
            "text": "How many are left?",
            "correct_answer": "2",
            "visual_type": "object_group",
            "visual_data": {"groups": [{"count": 5}, {"count": 3}], "operation": "-"},
        }
        result = validator._verify_object_group_answer(q)
        assert result is True

    def test_no_visual_skipped(self, validator):
        """Questions without visual_type should return None (no error)."""
        q = {
            "id": "Q1", "type": "fill_blank",
            "text": "5 + 3 = ______",
            "correct_answer": "8",
        }
        result = validator._verify_visual_answer_coherence(q)
        assert result is None

    def test_unknown_visual_type_skipped(self, validator):
        """Unknown visual types should return None (no error)."""
        q = {
            "id": "Q1", "type": "short_answer",
            "text": "Look at the bar chart.",
            "correct_answer": "5",
            "visual_type": "bar_chart",
            "visual_data": {"bars": [5, 3, 7]},
        }
        result = validator._verify_visual_answer_coherence(q)
        assert result is None

    def test_currency_answer_object_group(self, validator):
        """Object group with ₹ prefix in answer should still match."""
        q = {
            "id": "Q1", "type": "short_answer",
            "text": "Total coins?",
            "correct_answer": "₹15",
            "visual_type": "object_group",
            "visual_data": {"groups": [{"count": 10}, {"count": 5}], "operation": "+"},
        }
        result = validator._verify_object_group_answer(q)
        assert result is True


class TestFlashcardValidation:
    def test_valid_flashcards(self, validator):
        data = {"cards": [{"front": f"Q{i}", "back": f"A{i}"} for i in range(12)]}
        is_valid, errors = validator.validate_flashcards(data)
        assert is_valid

    def test_too_few_cards(self, validator):
        data = {"cards": [{"front": "Q1", "back": "A1"}]}
        is_valid, errors = validator.validate_flashcards(data)
        assert not is_valid

    def test_empty_front(self, validator):
        data = {"cards": [{"front": "", "back": "answer"} for _ in range(12)]}
        is_valid, errors = validator.validate_flashcards(data)
        assert not is_valid

    def test_duplicate_fronts(self, validator):
        data = {"cards": [{"front": "Same Q", "back": f"A{i}"} for i in range(12)]}
        is_valid, errors = validator.validate_flashcards(data)
        assert not is_valid
        assert any("Duplicate" in e for e in errors)


class TestRevisionValidation:
    def test_valid_revision(self, validator):
        data = {
            "introduction": "This topic covers fractions",
            "key_concepts": [
                {"title": "Numerator", "explanation": "Top number"},
                {"title": "Denominator", "explanation": "Bottom number"},
            ],
            "worked_examples": [{"problem": "1/2 + 1/2", "step_by_step": ["Add"], "answer": "1"}],
            "quick_quiz": [
                {"question": "What is 1/4?", "answer": "One quarter"},
                {"question": "Add 1/3 + 1/3", "answer": "2/3"},
            ],
        }
        is_valid, errors = validator.validate_revision(data)
        assert is_valid

    def test_missing_introduction(self, validator):
        data = {
            "key_concepts": [{"title": "a", "explanation": "b"}] * 3,
            "worked_examples": [{"problem": "q"}],
            "quick_quiz": [{"question": "q"}] * 3,
        }
        is_valid, errors = validator.validate_revision(data)
        assert not is_valid
        assert any("introduction" in e.lower() for e in errors)

    def test_too_few_concepts(self, validator):
        data = {
            "introduction": "Intro",
            "key_concepts": [{"title": "a", "explanation": "b"}],
            "worked_examples": [{"problem": "q"}],
            "quick_quiz": [{"question": "q"}] * 3,
        }
        is_valid, errors = validator.validate_revision(data)
        assert not is_valid
        assert any("Too few key concepts" in e for e in errors)


class TestGradingValidation:
    def test_valid_grading(self, validator):
        data = {
            "results": [
                {"question_number": 1, "is_correct": True, "student_answer": "4"},
                {"question_number": 2, "is_correct": False, "student_answer": "3"},
            ],
            "score": 1,
            "total": 2,
        }
        is_valid, errors = validator.validate_grading(data, total_questions=2)
        assert is_valid

    def test_score_exceeds_total(self, validator):
        data = {"results": [{"is_correct": True}], "score": 5, "total": 2}
        is_valid, errors = validator.validate_grading(data)
        assert not is_valid
        assert any("exceeds" in e for e in errors)

    def test_no_results(self, validator):
        data = {"results": [], "score": 0, "total": 0}
        is_valid, errors = validator.validate_grading(data)
        assert not is_valid
        assert any("No grading results" in e for e in errors)


# ---------------------------------------------------------------------------
# Type diversity check
# ---------------------------------------------------------------------------

class TestTypeDiversity:
    def _make_q(self, qid, qtype, text="What is 2+2?", answer="4"):
        return {"id": qid, "type": qtype, "text": text, "correct_answer": answer}

    def test_diverse_types_pass(self, validator):
        """Mixed types under 40% each should pass."""
        qs = [
            self._make_q("Q1", "mcq"),
            self._make_q("Q2", "fill_blank"),
            self._make_q("Q3", "word_problem"),
            self._make_q("Q4", "short_answer"),
            self._make_q("Q5", "true_false", answer="True"),
        ]
        qs[0]["options"] = ["3", "4", "5", "6"]
        qs[4]["options"] = ["True", "False"]
        data = {"questions": qs, "answer_key": {}}
        _, errors = validator.validate_worksheet(data, num_questions=5)
        assert not any("Type diversity" in e for e in errors)

    def test_all_same_type_fails(self, validator):
        """5 MCQs = 100% > 40% → should flag."""
        qs = [
            {"id": f"Q{i}", "type": "mcq", "text": f"Q {i}?",
             "options": ["A", "B", "C", "D"], "correct_answer": "A"}
            for i in range(1, 6)
        ]
        data = {"questions": qs, "answer_key": {}}
        _, errors = validator.validate_worksheet(data, num_questions=5)
        assert any("Type diversity" in e for e in errors)

    def test_small_worksheet_skips_check(self, validator):
        """Fewer than 5 questions should skip the diversity check."""
        qs = [
            {"id": f"Q{i}", "type": "mcq", "text": f"Q {i}?",
             "options": ["A", "B", "C", "D"], "correct_answer": "A"}
            for i in range(1, 4)
        ]
        data = {"questions": qs, "answer_key": {}}
        _, errors = validator.validate_worksheet(data, num_questions=3)
        assert not any("Type diversity" in e for e in errors)


# ---------------------------------------------------------------------------
# Disallowed keyword check
# ---------------------------------------------------------------------------

class TestDisallowedKeywords:
    def _make_q(self, qid, text="What is 2+2?", answer="4"):
        return {"id": qid, "type": "short_answer", "text": text, "correct_answer": answer}

    def test_clean_topic_passes(self, validator):
        """Questions without disallowed keywords should pass."""
        qs = [self._make_q("Q1", text="What is 23 + 45?")]
        data = {"questions": qs, "answer_key": {}}
        _, errors = validator.validate_worksheet(
            data, subject="Maths", topic="Addition (carries)", num_questions=1
        )
        assert not any("disallowed keyword" in e for e in errors)

    def test_disallowed_keyword_flagged(self, validator):
        """A question containing a disallowed keyword should be flagged."""
        # "Multiplication (tables 2-10)" disallows "carry", "borrow", "add", etc.
        qs = [self._make_q("Q1", text="Use the carry method to solve 6 x 7")]
        data = {"questions": qs, "answer_key": {}}
        _, errors = validator.validate_worksheet(
            data, subject="Maths", topic="Multiplication (tables 2-10)", num_questions=1
        )
        assert any("disallowed keyword" in e for e in errors)

    def test_unknown_topic_skips(self, validator):
        """Unknown topic should not crash — fail-open."""
        qs = [self._make_q("Q1", text="carry the one")]
        data = {"questions": qs, "answer_key": {}}
        _, errors = validator.validate_worksheet(
            data, subject="Maths", topic="Nonexistent Topic XYZ", num_questions=1
        )
        assert not any("disallowed keyword" in e for e in errors)
