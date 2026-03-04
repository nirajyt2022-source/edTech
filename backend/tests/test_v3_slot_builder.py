"""Test slot builder produces correct slot structures."""
import sys

sys.path.insert(0, ".")

from app.services.v3.slot_builder import Slot, SlotBuilderOutput, build_slots


class TestBuildSlots:
    def test_returns_correct_count_10(self):
        output = build_slots("CBSE", "Class 3", "Maths", "Addition (carries)", "medium", 10, "standard", "English")
        assert len(output.slots) == 10

    def test_returns_correct_count_5(self):
        output = build_slots("CBSE", "Class 3", "Maths", "Addition (carries)", "medium", 5, "standard", "English")
        assert len(output.slots) == 5

    def test_returns_correct_count_15(self):
        output = build_slots("CBSE", "Class 3", "Maths", "Addition (carries)", "medium", 15, "standard", "English")
        assert len(output.slots) == 15

    def test_returns_correct_count_20(self):
        output = build_slots("CBSE", "Class 3", "Maths", "Addition (carries)", "medium", 20, "standard", "English")
        assert len(output.slots) == 20

    def test_maths_slots_have_numbers(self):
        output = build_slots("CBSE", "Class 3", "Maths", "Addition (carries)", "medium", 10, "standard", "English")
        maths_slots_with_numbers = [s for s in output.slots if s.numbers is not None]
        assert len(maths_slots_with_numbers) >= 5  # at least half should have pre-computed numbers

    def test_maths_answers_are_correct(self):
        output = build_slots("CBSE", "Class 3", "Maths", "Addition (carries)", "medium", 10, "standard", "English")
        for slot in output.slots:
            if slot.numbers and "answer" in slot.numbers:
                a, b = slot.numbers["a"], slot.numbers["b"]
                assert slot.numbers["answer"] == a + b, f"Wrong answer: {a} + {b} != {slot.numbers['answer']}"

    def test_class1_no_error_detection(self):
        output = build_slots(
            "CBSE", "Class 1", "Maths", "Addition up to 20 (Class 1)", "easy", 10, "standard", "English"
        )
        for slot in output.slots:
            assert slot.role != "error_detection", f"Slot {slot.slot_number} has error_detection for Class 1"

    def test_easy_difficulty_distribution(self):
        output = build_slots("CBSE", "Class 3", "Maths", "Addition (carries)", "easy", 10, "standard", "English")
        easy_count = sum(1 for s in output.slots if s.difficulty == "easy")
        assert easy_count >= 5, f"Easy difficulty should have 5+ easy slots, got {easy_count}"

    def test_hard_difficulty_distribution(self):
        output = build_slots("CBSE", "Class 3", "Maths", "Addition (carries)", "hard", 10, "standard", "English")
        hard_count = sum(1 for s in output.slots if s.difficulty == "hard")
        assert hard_count >= 4, f"Hard difficulty should have 4+ hard slots, got {hard_count}"

    def test_non_maths_topic(self):
        output = build_slots("CBSE", "Class 3", "EVS", "Water (Class 3)", "medium", 10, "standard", "English")
        assert len(output.slots) == 10
        assert all(s.llm_instruction for s in output.slots), "Every slot must have llm_instruction"

    def test_english_topic(self):
        output = build_slots("CBSE", "Class 2", "English", "Nouns (Class 2)", "medium", 10, "standard", "English")
        assert len(output.slots) == 10

    def test_hindi_topic(self):
        output = build_slots("CBSE", "Class 1", "Hindi", "Varnamala Swar (Class 1)", "easy", 10, "standard", "Hindi")
        assert len(output.slots) == 10

    def test_visual_style_has_visuals(self):
        output = build_slots(
            "CBSE", "Class 3", "Maths", "Fractions (halves, quarters)", "medium", 10, "visual", "English"
        )
        visual_count = sum(1 for s in output.slots if s.visual_type is not None)
        assert visual_count >= 5, f"Visual style should have 5+ visuals, got {visual_count}"

    def test_fraction_has_mandatory_visuals(self):
        output = build_slots(
            "CBSE", "Class 3", "Maths", "Fractions (halves, quarters)", "medium", 10, "standard", "English"
        )
        pie_count = sum(1 for s in output.slots if s.visual_type == "pie_fraction")
        assert pie_count >= 3, f"Fractions should have 3+ pie_fraction visuals, got {pie_count}"

    def test_has_true_false(self):
        output = build_slots("CBSE", "Class 3", "Maths", "Addition (carries)", "medium", 10, "standard", "English")
        tf_count = sum(1 for s in output.slots if s.question_type == "true_false")
        assert tf_count >= 1, "Must have at least 1 true_false question"

    def test_has_minimum_mcq(self):
        output = build_slots("CBSE", "Class 3", "Maths", "Addition (carries)", "medium", 10, "standard", "English")
        mcq_count = sum(1 for s in output.slots if s.question_type == "mcq")
        assert mcq_count >= 3, f"Must have at least 3 MCQs, got {mcq_count}"

    def test_worksheet_meta_has_objectives(self):
        output = build_slots("CBSE", "Class 3", "Maths", "Addition (carries)", "medium", 10, "standard", "English")
        assert output.worksheet_meta.get("learning_objectives"), "Must have learning objectives"
        assert len(output.worksheet_meta["learning_objectives"]) >= 2

    def test_every_slot_has_instruction(self):
        output = build_slots("CBSE", "Class 3", "Maths", "Addition (carries)", "medium", 10, "standard", "English")
        for slot in output.slots:
            assert len(slot.llm_instruction) > 20, f"Slot {slot.slot_number} has too short instruction"

    def test_no_duplicate_names_in_adjacent_slots(self):
        output = build_slots("CBSE", "Class 3", "Maths", "Addition (carries)", "medium", 10, "standard", "English")
        for i in range(len(output.slots) - 1):
            names_a = set(output.slots[i].names)
            names_b = set(output.slots[i + 1].names)
            assert not (names_a & names_b), f"Slots {i + 1} and {i + 2} share names"

    def test_no_duplicate_contexts(self):
        output = build_slots("CBSE", "Class 3", "Maths", "Addition (carries)", "medium", 10, "standard", "English")
        contexts = [s.context for s in output.slots if s.context]
        # Allow some repeats for 10 questions, but not all same
        unique = set(contexts)
        assert len(unique) >= min(5, len(contexts)), (
            f"Need variety: {len(unique)} unique contexts out of {len(contexts)}"
        )
