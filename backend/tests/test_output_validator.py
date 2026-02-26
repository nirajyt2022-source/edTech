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
        """6/10 questions with same pattern (only names differ) should flag."""
        questions = []
        names = ["Aarav", "Priya", "Rohan", "Diya", "Kabir", "Myra"]
        # 6 near-duplicates: only the name changes
        for i, name in enumerate(names):
            questions.append({
                "id": f"Q{i+1}", "type": "word_problem",
                "text": f"{name} goes to the market and buys 5 apples for ₹10 each. How much does {name} pay?",
                "correct_answer": "₹50",
            })
        # 4 diverse questions
        questions.append({"id": "Q7", "type": "mcq", "text": "What is 2+2?", "options": ["3","4","5","6"], "correct_answer": "4"})
        questions.append({"id": "Q8", "type": "fill_blank", "text": "15 - 7 = ______", "correct_answer": "8"})
        questions.append({"id": "Q9", "type": "true_false", "text": "True or False: 5 × 3 = 15", "options": ["True","False"], "correct_answer": "True"})
        questions.append({"id": "Q10", "type": "short_answer", "text": "Name a 3-digit number", "correct_answer": "100"})

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


# ---------------------------------------------------------------------------
# Visual-topic appropriateness check
# ---------------------------------------------------------------------------

class TestVisualTopicAppropriateness:
    def _make_q(self, qid, visual_type=None, text="What is 2+2?", answer="4"):
        return {"id": qid, "type": "short_answer", "text": text,
                "correct_answer": answer, "visual_type": visual_type}

    def test_allowed_visual_passes(self, validator):
        """A visual type not in disallowed list should pass."""
        qs = [self._make_q("Q1", visual_type="number_line")]
        data = {"questions": qs, "answer_key": {}}
        _, errors = validator.validate_worksheet(
            data, subject="Maths", topic="Addition (carries)", num_questions=1
        )
        assert not any("disallowed" in e and "visual" in e for e in errors)

    def test_disallowed_visual_flagged(self, validator):
        """A disallowed visual type should produce an error."""
        # "Multiplication (tables 2-10)" disallows base_ten_regrouping
        qs = [self._make_q("Q1", visual_type="base_ten_regrouping")]
        data = {"questions": qs, "answer_key": {}}
        _, errors = validator.validate_worksheet(
            data, subject="Maths", topic="Multiplication (tables 2-10)", num_questions=1
        )
        assert any("visual type" in e and "disallowed" in e for e in errors)

    def test_no_visual_skips(self, validator):
        """Questions without visual_type should not trigger the check."""
        qs = [self._make_q("Q1")]
        data = {"questions": qs, "answer_key": {}}
        _, errors = validator.validate_worksheet(
            data, subject="Maths", topic="Multiplication (tables 2-10)", num_questions=1
        )
        assert not any("visual type" in e and "disallowed" in e for e in errors)

    def test_unknown_topic_skips(self, validator):
        """Unknown topic should not crash."""
        qs = [self._make_q("Q1", visual_type="base_ten_regrouping")]
        data = {"questions": qs, "answer_key": {}}
        _, errors = validator.validate_worksheet(
            data, subject="Maths", topic="Nonexistent Topic", num_questions=1
        )
        assert not any("visual type" in e and "disallowed" in e for e in errors)


# ---------------------------------------------------------------------------
# Opening verb diversity (L1)
# ---------------------------------------------------------------------------

class TestOpeningVerbDiversity:
    def _make_q(self, qid, text, answer="4"):
        return {"id": qid, "type": "short_answer", "text": text, "correct_answer": answer}

    def test_diverse_verbs_pass(self, validator):
        """Different opening words should pass."""
        qs = [
            self._make_q("Q1", "Find the sum of 2 and 3"),
            self._make_q("Q2", "Calculate 5 + 7"),
            self._make_q("Q3", "What is 8 - 3?"),
            self._make_q("Q4", "Add 4 and 6"),
            self._make_q("Q5", "How many apples are there?"),
        ]
        data = {"questions": qs, "answer_key": {}}
        _, errors = validator.validate_worksheet(data, num_questions=5)
        assert not any("Opening verb" in e for e in errors)

    def test_repeated_verb_fails(self, validator):
        """Same opening word 3+ times should flag."""
        qs = [
            self._make_q("Q1", "Find the sum of 2 and 3"),
            self._make_q("Q2", "Find the difference of 8 and 5"),
            self._make_q("Q3", "Find the product of 4 and 6"),
            self._make_q("Q4", "Add 7 and 9"),
            self._make_q("Q5", "What is 6 + 2?"),
        ]
        data = {"questions": qs, "answer_key": {}}
        _, errors = validator.validate_worksheet(data, num_questions=5)
        assert any("Opening verb" in e for e in errors)
        assert any("find" in e.lower() for e in errors if "Opening verb" in e)

    def test_two_repeats_ok(self, validator):
        """Exactly 2 of the same opening word is within threshold."""
        qs = [
            self._make_q("Q1", "Find the sum of 2 and 3"),
            self._make_q("Q2", "Find the difference of 8 and 5"),
            self._make_q("Q3", "Add 7 and 9"),
            self._make_q("Q4", "What is 6 + 2?"),
            self._make_q("Q5", "Calculate 4 times 5"),
        ]
        data = {"questions": qs, "answer_key": {}}
        _, errors = validator.validate_worksheet(data, num_questions=5)
        assert not any("Opening verb" in e for e in errors)

    def test_small_worksheet_skips(self, validator):
        """Fewer than 5 questions should skip the check."""
        qs = [
            self._make_q("Q1", "Find the sum of 2 and 3"),
            self._make_q("Q2", "Find the difference of 8 and 5"),
            self._make_q("Q3", "Find the product of 4 and 6"),
        ]
        data = {"questions": qs, "answer_key": {}}
        _, errors = validator.validate_worksheet(data, num_questions=3)
        assert not any("Opening verb" in e for e in errors)


# ---------------------------------------------------------------------------
# Near-duplicate threshold tightened (R3)
# ---------------------------------------------------------------------------

class TestTightenedDuplicateThreshold:
    def test_four_of_ten_same_pattern_flags(self, validator):
        """4/10 same-structure questions should now flag (was allowed at 33%, blocked at 50%)."""
        questions = []
        names = ["Aarav", "Priya", "Rohan", "Diya"]
        # 4 near-duplicates: only the name and numbers change
        for i, name in enumerate(names):
            questions.append({
                "id": f"Q{i+1}", "type": "word_problem",
                "text": f"{name} has {10+i} pencils and buys {5+i} more. How many pencils does {name} have now?",
                "correct_answer": str(15 + 2*i),
            })
        # 6 diverse questions
        questions.append({"id": "Q5", "type": "mcq", "text": "What is 2+2?", "options": ["3","4","5","6"], "correct_answer": "4"})
        questions.append({"id": "Q6", "type": "fill_blank", "text": "15 - 7 = ______", "correct_answer": "8"})
        questions.append({"id": "Q7", "type": "true_false", "text": "True or False: 5 x 3 = 15", "options": ["True","False"], "correct_answer": "True"})
        questions.append({"id": "Q8", "type": "short_answer", "text": "Name a 3-digit number", "correct_answer": "100"})
        questions.append({"id": "Q9", "type": "error_detection", "text": "Find the mistake: 25+18=42", "correct_answer": "43"})
        questions.append({"id": "Q10", "type": "short_answer", "text": "Write 45 in words", "correct_answer": "forty-five"})

        data = {"questions": questions}
        _, errors = validator.validate_worksheet(data, num_questions=10)
        # At 50% threshold, max(3, int(10*0.50)+1) = 6 → 4 < 6, so 4/10 should pass
        assert not any("Near-duplicate" in e for e in errors)

    def test_six_of_ten_same_pattern_flags(self, validator):
        """6/10 same-structure should flag at 50% threshold."""
        questions = []
        names = ["Aarav", "Priya", "Rohan", "Diya", "Kabir", "Myra"]
        for i, name in enumerate(names):
            questions.append({
                "id": f"Q{i+1}", "type": "word_problem",
                "text": f"{name} has {10+i} pencils and buys {5+i} more. How many pencils does {name} have now?",
                "correct_answer": str(15 + 2*i),
            })
        # 4 diverse
        questions.append({"id": "Q7", "type": "mcq", "text": "What is 2+2?", "options": ["3","4","5","6"], "correct_answer": "4"})
        questions.append({"id": "Q8", "type": "fill_blank", "text": "15 - 7 = ______", "correct_answer": "8"})
        questions.append({"id": "Q9", "type": "true_false", "text": "True or False: 5 x 3 = 15", "options": ["True","False"], "correct_answer": "True"})
        questions.append({"id": "Q10", "type": "short_answer", "text": "Write 45 in words", "correct_answer": "forty-five"})

        data = {"questions": questions}
        _, errors = validator.validate_worksheet(data, num_questions=10)
        # At 50% threshold, max(3, int(10*0.50)+1) = 6 → 6 >= 6, should flag
        assert any("Near-duplicate" in e for e in errors)


# ---------------------------------------------------------------------------
# Number reuse across questions (N2)
# ---------------------------------------------------------------------------

class TestNumberReuse:
    def _make_q(self, qid, text, answer="4"):
        return {"id": qid, "type": "short_answer", "text": text, "correct_answer": answer}

    def test_unique_numbers_pass(self, validator):
        """No number reused across >2 questions should pass."""
        qs = [
            self._make_q("Q1", "What is 23 + 45?"),
            self._make_q("Q2", "What is 67 - 12?"),
            self._make_q("Q3", "Find 89 + 34"),
            self._make_q("Q4", "Calculate 56 - 21"),
            self._make_q("Q5", "Add 78 and 93"),
        ]
        data = {"questions": qs, "answer_key": {}}
        _, errors = validator.validate_worksheet(data, num_questions=5)
        assert not any("Number" in e and "appears in" in e for e in errors)

    def test_number_in_three_questions_flags(self, validator):
        """Same number in 3 questions should flag."""
        qs = [
            self._make_q("Q1", "What is 25 + 13?"),
            self._make_q("Q2", "Find 25 - 8"),
            self._make_q("Q3", "Calculate 25 + 47"),
            self._make_q("Q4", "Add 67 and 89"),
            self._make_q("Q5", "What is 34 + 56?"),
        ]
        data = {"questions": qs, "answer_key": {}}
        _, errors = validator.validate_worksheet(data, num_questions=5)
        assert any("25" in e and "appears in" in e for e in errors)

    def test_trivial_numbers_excluded(self, validator):
        """Numbers 0 and 1 should not trigger the check."""
        qs = [
            self._make_q("Q1", "Is 0 even or odd?", "even"),
            self._make_q("Q2", "What is 0 + 5?", "5"),
            self._make_q("Q3", "Start from 0 and count to 10", "10"),
            self._make_q("Q4", "Add 23 and 45"),
            self._make_q("Q5", "What is 67 - 12?"),
        ]
        data = {"questions": qs, "answer_key": {}}
        _, errors = validator.validate_worksheet(data, num_questions=5)
        assert not any("Number" in e and "appears in" in e for e in errors)

    def test_small_worksheet_skips(self, validator):
        """Fewer than 5 questions should skip the check."""
        qs = [
            self._make_q("Q1", "What is 25 + 13?"),
            self._make_q("Q2", "Find 25 - 8"),
            self._make_q("Q3", "Calculate 25 + 47"),
        ]
        data = {"questions": qs, "answer_key": {}}
        _, errors = validator.validate_worksheet(data, num_questions=3)
        assert not any("Number" in e and "appears in" in e for e in errors)
