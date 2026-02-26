"""
Tests for NCERT preferred terminology mapping.

All tests run fully offline — no Supabase or LLM calls required.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.data.ncert_terminology import NCERT_TERMINOLOGY, get_terminology_instructions


class TestNCERTTerminology:
    def test_maths_grade3_has_regrouping(self):
        result = get_terminology_instructions("Maths", 3)
        assert "regrouping" in result
        assert "carrying" in result  # the informal term being replaced

    def test_no_terms_for_unknown_subject(self):
        result = get_terminology_instructions("Art", 3)
        assert result == ""

    def test_grade_filtering_take_away(self):
        """'take away' → 'subtract' only applies for grade 3+."""
        result_grade2 = get_terminology_instructions("Maths", 2)
        result_grade3 = get_terminology_instructions("Maths", 3)
        assert "subtract" not in result_grade2
        assert "subtract" in result_grade3

    def test_all_subjects_have_entries(self):
        """Every subject in the mapping should produce output for at least one grade."""
        for subject in NCERT_TERMINOLOGY:
            found = False
            for grade in range(1, 6):
                if get_terminology_instructions(subject, grade):
                    found = True
                    break
            assert found, f"No terminology found for subject '{subject}'"

    def test_english_grade2(self):
        result = get_terminology_instructions("English", 2)
        assert "language patterns" in result

    def test_science_grade1(self):
        result = get_terminology_instructions("Science", 1)
        assert "activity" in result

    def test_maths_grade5_has_simplify(self):
        result = get_terminology_instructions("Maths", 5)
        assert "simplify" in result

    def test_maths_grade2_no_simplify(self):
        """'reduce' → 'simplify' only applies for grade 4+."""
        result = get_terminology_instructions("Maths", 2)
        assert "simplify" not in result
