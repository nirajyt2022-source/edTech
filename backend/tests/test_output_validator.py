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
