"""Test assembler produces correct output format matching frontend expectations."""
import sys

sys.path.insert(0, ".")

from app.services.v3.assembler import assemble_worksheet, generate_maths_distractors
from app.services.v3.slot_builder import build_slots


class TestAssembler:
    def test_output_format_matches_current(self):
        """The assembled worksheet must have the exact fields the frontend expects."""
        output = build_slots("CBSE", "Class 3", "Maths", "Addition (carries)", "medium", 10, "standard", "English")

        # Simulate Gemini fill with mock data
        mock_fill = []
        for slot in output.slots:
            mock_fill.append(
                {
                    "slot": slot.slot_number,
                    "text": f"Test question {slot.slot_number} about addition",
                    "hint": "Think carefully",
                    "explanation": "Use carrying",
                    "options": None,
                    "common_mistake": "Forgetting to carry" if slot.slot_number == 1 else None,
                    "parent_tip": "Practice daily" if slot.slot_number == 1 else None,
                }
            )

        worksheet = assemble_worksheet(output, mock_fill)

        # Check top-level fields
        assert "title" in worksheet
        assert "skill_focus" in worksheet
        assert "common_mistake" in worksheet
        assert "parent_tip" in worksheet
        assert "learning_objectives" in worksheet
        assert "questions" in worksheet
        assert len(worksheet["questions"]) == 10

        # Check question fields
        q = worksheet["questions"][0]
        required_fields = [
            "id",
            "type",
            "role",
            "text",
            "options",
            "correct_answer",
            "explanation",
            "difficulty",
            "hint",
            "skill_tag",
            "image_keywords",
            "visual_type",
            "visual_data",
        ]
        for f in required_fields:
            assert f in q, f"Missing field: {f}"

    def test_maths_answers_from_python_not_gemini(self):
        """Correct answers for maths must come from slot.numbers, not Gemini."""
        output = build_slots("CBSE", "Class 3", "Maths", "Addition (carries)", "medium", 10, "standard", "English")
        mock_fill = [
            {
                "slot": s.slot_number,
                "text": f"Q{s.slot_number}",
                "hint": "",
                "explanation": "",
                "options": None,
                "common_mistake": None,
                "parent_tip": None,
            }
            for s in output.slots
        ]
        worksheet = assemble_worksheet(output, mock_fill)

        for i, q in enumerate(worksheet["questions"]):
            slot = output.slots[i]
            if slot.numbers and slot.numbers.get("answer") is not None:
                assert q["correct_answer"] == str(slot.numbers["answer"]), (
                    f"Q{i + 1}: answer should be {slot.numbers['answer']}, got {q['correct_answer']}"
                )

    def test_mcq_has_4_options(self):
        """MCQ questions must have exactly 4 options."""
        output = build_slots("CBSE", "Class 3", "Maths", "Addition (carries)", "medium", 10, "standard", "English")
        mock_fill = [
            {
                "slot": s.slot_number,
                "text": f"Q{s.slot_number}",
                "hint": "",
                "explanation": "",
                "options": None,
                "common_mistake": None,
                "parent_tip": None,
            }
            for s in output.slots
        ]
        worksheet = assemble_worksheet(output, mock_fill)

        for q in worksheet["questions"]:
            if q["type"] == "mcq":
                assert q["options"] is not None, f"{q['id']}: MCQ must have options"
                assert len(q["options"]) == 4, f"{q['id']}: MCQ must have 4 options, got {len(q['options'])}"

    def test_true_false_has_two_options(self):
        """True/false questions must have ["True", "False"] options."""
        output = build_slots("CBSE", "Class 3", "Maths", "Addition (carries)", "medium", 10, "standard", "English")
        mock_fill = [
            {
                "slot": s.slot_number,
                "text": f"Q{s.slot_number}",
                "hint": "",
                "explanation": "",
                "options": None,
                "common_mistake": None,
                "parent_tip": None,
            }
            for s in output.slots
        ]
        worksheet = assemble_worksheet(output, mock_fill)

        for q in worksheet["questions"]:
            if q["type"] == "true_false":
                assert q["options"] == ["True", "False"], f"{q['id']}: true_false should have True/False options"

    def test_worksheet_meta_from_slot_builder(self):
        """Worksheet meta should come from slot builder, overridden by Gemini slot 1."""
        output = build_slots("CBSE", "Class 3", "Maths", "Addition (carries)", "medium", 10, "standard", "English")
        mock_fill = [
            {
                "slot": 1,
                "text": "Q1",
                "hint": "",
                "explanation": "",
                "options": None,
                "common_mistake": "Students forget to carry over",
                "parent_tip": "Use manipulatives for practice",
            }
        ]
        worksheet = assemble_worksheet(output, mock_fill)

        assert worksheet["common_mistake"] == "Students forget to carry over"
        assert worksheet["parent_tip"] == "Use manipulatives for practice"
        assert len(worksheet["learning_objectives"]) >= 2

    def test_render_format_inferred(self):
        """Each question should have a 'format' field for PDF rendering."""
        output = build_slots("CBSE", "Class 3", "Maths", "Addition (carries)", "medium", 10, "standard", "English")
        mock_fill = [
            {
                "slot": s.slot_number,
                "text": f"Q{s.slot_number}",
                "hint": "",
                "explanation": "",
                "options": None,
                "common_mistake": None,
                "parent_tip": None,
            }
            for s in output.slots
        ]
        worksheet = assemble_worksheet(output, mock_fill)

        for q in worksheet["questions"]:
            assert "format" in q, f"{q['id']} missing format field"
            assert q["format"] in ("mcq_4", "mcq_3", "fill_blank", "true_false", "short_answer"), (
                f"{q['id']} has invalid format: {q['format']}"
            )


class TestMathsDistractors:
    def test_returns_3_distractors(self):
        result = generate_maths_distractors(42, "medium")
        assert len(result) == 3

    def test_correct_not_in_distractors(self):
        result = generate_maths_distractors(42, "medium")
        assert 42 not in result

    def test_all_positive(self):
        result = generate_maths_distractors(5, "easy")
        assert all(d > 0 for d in result)

    def test_digit_swap_included(self):
        result = generate_maths_distractors(42, "medium")
        assert 24 in result, "Digit swap of 42 should be 24"
