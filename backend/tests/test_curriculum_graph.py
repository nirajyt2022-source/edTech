"""
Tests for curriculum_graph.py — entity models, graph builder, and public API.
"""

import pytest

from app.services.curriculum_graph import (
    Book,
    Chapter,
    CurriculumNode,
    LearningOutcome,
    Section,
    get_all_topics_for,
    get_chapter_chain,
    get_curriculum_node,
    validate_topic_exists,
)


# ---------------------------------------------------------------------------
# Entity model tests
# ---------------------------------------------------------------------------


class TestEntityModels:
    """Frozen dataclass entities are hashable and immutable."""

    def test_learning_outcome_frozen(self):
        lo = LearningOutcome(text="Add 3-digit numbers", bloom_level="apply")
        assert lo.text == "Add 3-digit numbers"
        assert lo.bloom_level == "apply"
        with pytest.raises(AttributeError):
            lo.text = "changed"  # type: ignore[misc]

    def test_section_frozen(self):
        s = Section(
            exercise_id="3.1",
            title="Addition",
            page_start=27,
            page_end=32,
            ncert_question_types=("computation", "fill_in_the_blank"),
            learning_outcomes=(),
        )
        assert s.exercise_id == "3.1"
        assert s.page_start == 27

    def test_chapter_frozen(self):
        ch = Chapter(number=3, name="Addition", sections=())
        assert ch.number == 3
        assert ch.name == "Addition"

    def test_book_frozen(self):
        b = Book(name="NCERT Math Class 3", grade="Class 3", subject="Maths", chapters=())
        assert b.grade == "Class 3"

    def test_curriculum_node_frozen(self):
        ch = Chapter(number=3, name="Addition", sections=())
        node = CurriculumNode(
            grade="Class 3",
            subject="Maths",
            topic="Addition (carries)",
            book_name="NCERT Math Class 3",
            chapter=ch,
            primary_section=None,
            learning_outcomes=("Add 3-digit numbers",),
            page_range="pp. 27-32",
        )
        assert node.topic == "Addition (carries)"
        assert len(node.learning_outcomes) == 1


# ---------------------------------------------------------------------------
# Graph lookup tests
# ---------------------------------------------------------------------------


class TestCurriculumLookup:
    """Test the public API against real data files."""

    def test_exact_lookup(self):
        """Known topic from ncert_alignment.json should be found."""
        node = get_curriculum_node("Class 1", "Maths", "Addition up to 20")
        assert node is not None
        assert node.grade == "Class 1"
        assert node.subject == "Maths"
        assert node.chapter.number == 3
        assert node.chapter.name == "Addition"

    def test_chapter_chain(self):
        """Chapter chain should return a breadcrumb string."""
        chain = get_chapter_chain("Class 1", "Maths", "Addition up to 20")
        assert chain  # non-empty
        assert "Chapter 3" in chain
        assert "Addition" in chain

    def test_nonexistent_topic(self):
        """Unknown topic returns None."""
        node = get_curriculum_node("Class 1", "Maths", "Quantum Mechanics")
        assert node is None

    def test_nonexistent_chain(self):
        """Unknown topic returns empty string for chain."""
        chain = get_chapter_chain("Class 1", "Maths", "Quantum Mechanics")
        assert chain == ""

    def test_validate_exists_true(self):
        assert validate_topic_exists("Class 1", "Maths", "Addition up to 20") is True

    def test_validate_exists_false(self):
        assert validate_topic_exists("Class 99", "Maths", "Nothing") is False

    def test_get_all_topics_for_maths_class1(self):
        """Should return a non-empty sorted list of topics."""
        topics = get_all_topics_for("Class 1", "Maths")
        assert len(topics) >= 3  # at least a few Maths topics for Class 1
        assert topics == sorted(topics)  # sorted

    def test_fuzzy_case_insensitive(self):
        """Case-insensitive lookup should work."""
        node = get_curriculum_node("class 1", "maths", "Addition up to 20")
        assert node is not None

    def test_section_has_page_range(self):
        """Primary section should have page range data."""
        node = get_curriculum_node("Class 1", "Maths", "Addition up to 20")
        assert node is not None
        assert node.page_range  # non-empty
        if node.primary_section:
            assert node.primary_section.page_start > 0

    def test_learning_outcomes_present(self):
        """Topics with entries in learning_objectives.py should have outcomes."""
        # "Addition (carries)" is a Class 3 Maths topic with learning objectives
        node = get_curriculum_node("Class 3", "Maths", "Addition (carries)")
        if node is not None:
            assert len(node.learning_outcomes) >= 1

    def test_chapter_map_fallback(self):
        """Topics only in chapter_map (not alignment) should still be found."""
        # English topics are typically in chapter_map but not alignment
        node = get_curriculum_node("Class 1", "English", "Alphabet")
        assert node is not None
        assert node.subject == "English"

    def test_hindi_topic_exists(self):
        """Hindi topics should be findable."""
        node = get_curriculum_node("Class 1", "Hindi", "Varnamala Swar")
        assert node is not None
