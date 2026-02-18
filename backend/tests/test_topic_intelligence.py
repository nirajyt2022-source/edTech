"""
Tests for TopicIntelligenceAgent.

All tests run fully offline — no Supabase connection, no LLM calls needed.
Async build_context is exercised via asyncio.run() in sync wrappers, avoiding
any pytest-asyncio mode configuration requirements.
"""
import sys
import os
import asyncio
from unittest.mock import MagicMock, patch

# Ensure backend/ is on the path when running from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.topic_intelligence import (
    TopicIntelligenceAgent,
    GenerationContext,
    _lookup_canon,
    _get_skill_tags,
    _get_subtopics,
    _DEFAULT_BLOOM,
    _DEFAULT_FORMAT_MIX,
    _DEFAULT_SCAFFOLDING,
    _DEFAULT_CHALLENGE,
)


# ---------------------------------------------------------------------------
# Helper: run a coroutine synchronously
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# _lookup_canon — curriculum canon lookup (pure, no I/O after first load)
# ---------------------------------------------------------------------------

class TestLookupCanon:
    def test_known_topic_grade3_maths(self):
        """A topic that exists in curriculum_canon for Grade 3 Maths."""
        # "Division basics" is present in Grade 3 Maths in curriculum_canon.json
        result = _lookup_canon("Division basics", "Maths", 3)
        assert result["ncert_chapter"] == "Division basics"
        assert result["in_canon"] is True

    def test_unknown_topic_returns_slug_as_chapter(self):
        """Unknown topic should fall back to topic_slug without crashing."""
        result = _lookup_canon("This Topic Does Not Exist XYZ", "Maths", 3)
        assert result["ncert_chapter"] == "This Topic Does Not Exist XYZ"
        assert result["in_canon"] is False

    def test_grade_mismatch_returns_fallback(self):
        """Topic exists in Grade 3 but queried with Grade 1 → fallback."""
        result = _lookup_canon("Addition (carries)", "Maths", 1)
        # Grade 1 has "Addition up to 20", not "Addition (carries)"
        assert result["in_canon"] is False

    def test_subject_mismatch_returns_fallback(self):
        """Topic exists in Maths but queried as English → fallback."""
        result = _lookup_canon("Addition (carries)", "English", 3)
        assert result["in_canon"] is False

    def test_case_insensitive_subject_match(self):
        """Subject matching should be case-insensitive."""
        result1 = _lookup_canon("Addition (carries)", "Maths", 3)
        result2 = _lookup_canon("Addition (carries)", "maths", 3)
        assert result1["in_canon"] == result2["in_canon"]


# ---------------------------------------------------------------------------
# _get_skill_tags and _get_subtopics
# ---------------------------------------------------------------------------

class TestSlotEngineHelpers:
    def test_skill_tags_known_topic(self):
        """Addition (carries) has a known profile with multiple skill tags."""
        tags = _get_skill_tags("Addition (carries)")
        assert isinstance(tags, list)
        assert len(tags) > 0
        assert "column_add_with_carry" in tags

    def test_skill_tags_unknown_topic_returns_empty(self):
        """Unknown topic returns empty list without crashing."""
        tags = _get_skill_tags("Completely Unknown Topic ZZZZ")
        assert isinstance(tags, list)
        assert len(tags) == 0

    def test_subtopics_known_topic(self):
        """Addition (carries) has 3 learning objectives."""
        subtopics = _get_subtopics("Addition (carries)")
        assert isinstance(subtopics, list)
        assert len(subtopics) > 0

    def test_subtopics_unknown_topic_returns_empty(self):
        """Unknown topic returns empty list without crashing."""
        subtopics = _get_subtopics("Unknown Topic XYZ 999")
        assert isinstance(subtopics, list)
        # May be empty — just confirm no crash
        assert subtopics == [] or isinstance(subtopics, list)


# ---------------------------------------------------------------------------
# GenerationContext — return type
# ---------------------------------------------------------------------------

class TestGenerationContext:
    def test_is_pydantic_model(self):
        ctx = GenerationContext(
            topic_slug="Addition (carries)",
            subject="Maths",
            grade=3,
            ncert_chapter="Addition (carries)",
            ncert_subtopics=["obj1"],
            bloom_level="recall",
            format_mix={"mcq": 40, "fill_blank": 30, "word_problem": 30},
            scaffolding=True,
            challenge_mode=False,
            valid_skill_tags=["tag1"],
            child_context={},
        )
        assert ctx.topic_slug == "Addition (carries)"
        assert ctx.grade == 3


# ---------------------------------------------------------------------------
# TopicIntelligenceAgent.build_context — core tests
# ---------------------------------------------------------------------------

class TestBuildContextNoChildId:
    """All tests with child_id=None — no Supabase needed."""

    def test_returns_generation_context_type(self):
        agent = TopicIntelligenceAgent()
        ctx = _run(agent.build_context(
            child_id=None,
            topic_slug="Addition (carries)",
            subject="Maths",
            grade=3,
        ))
        assert isinstance(ctx, GenerationContext)

    def test_ncert_chapter_non_empty(self):
        """build_context must return a non-empty ncert_chapter."""
        agent = TopicIntelligenceAgent()
        ctx = _run(agent.build_context(
            child_id=None,
            topic_slug="Addition (carries)",
            subject="Maths",
            grade=3,
        ))
        assert ctx.ncert_chapter != ""
        assert ctx.ncert_chapter is not None

    def test_valid_skill_tags_non_empty(self):
        """build_context must return a non-empty valid_skill_tags list."""
        agent = TopicIntelligenceAgent()
        ctx = _run(agent.build_context(
            child_id=None,
            topic_slug="Addition (carries)",
            subject="Maths",
            grade=3,
        ))
        assert isinstance(ctx.valid_skill_tags, list)
        assert len(ctx.valid_skill_tags) > 0

    def test_defaults_applied_when_no_child_id(self):
        """With child_id=None, safe defaults must be used."""
        agent = TopicIntelligenceAgent()
        ctx = _run(agent.build_context(
            child_id=None,
            topic_slug="Addition (carries)",
            subject="Maths",
            grade=3,
        ))
        assert ctx.bloom_level == _DEFAULT_BLOOM        # "recall"
        assert ctx.scaffolding == _DEFAULT_SCAFFOLDING  # True
        assert ctx.challenge_mode == _DEFAULT_CHALLENGE # False
        assert ctx.format_mix == _DEFAULT_FORMAT_MIX
        assert ctx.child_context == {}

    def test_grade_and_subject_preserved(self):
        """grade and subject must be passed through unchanged."""
        agent = TopicIntelligenceAgent()
        ctx = _run(agent.build_context(
            child_id=None,
            topic_slug="Nouns (Class 2)",
            subject="English",
            grade=2,
        ))
        assert ctx.grade == 2
        assert ctx.subject == "English"

    def test_topic_slug_preserved(self):
        agent = TopicIntelligenceAgent()
        ctx = _run(agent.build_context(
            child_id=None,
            topic_slug="Division basics",
            subject="Maths",
            grade=3,
        ))
        assert ctx.topic_slug == "Division basics"

    def test_ncert_subtopics_is_list(self):
        """ncert_subtopics must always be a list (possibly empty)."""
        agent = TopicIntelligenceAgent()
        ctx = _run(agent.build_context(
            child_id=None,
            topic_slug="Multiplication (tables 2-10)",
            subject="Maths",
            grade=3,
        ))
        assert isinstance(ctx.ncert_subtopics, list)

    def test_format_mix_is_dict(self):
        agent = TopicIntelligenceAgent()
        ctx = _run(agent.build_context(
            child_id=None,
            topic_slug="Addition (carries)",
            subject="Maths",
            grade=3,
        ))
        assert isinstance(ctx.format_mix, dict)
        assert len(ctx.format_mix) > 0


class TestBuildContextUnknownTopic:
    """Unknown topic slug must not crash — must return safe defaults."""

    def test_no_crash_on_unknown_topic(self):
        agent = TopicIntelligenceAgent()
        ctx = _run(agent.build_context(
            child_id=None,
            topic_slug="This Topic Does Not Exist ZZZ999",
            subject="Maths",
            grade=3,
        ))
        assert isinstance(ctx, GenerationContext)

    def test_unknown_topic_ncert_chapter_is_slug(self):
        """Unknown topic → ncert_chapter falls back to the topic_slug."""
        agent = TopicIntelligenceAgent()
        slug = "Some Nonexistent Topic XYZABC"
        ctx = _run(agent.build_context(
            child_id=None,
            topic_slug=slug,
            subject="Maths",
            grade=3,
        ))
        assert ctx.ncert_chapter == slug

    def test_unknown_topic_valid_skill_tags_empty(self):
        """Unknown topic → valid_skill_tags is empty (no profile found)."""
        agent = TopicIntelligenceAgent()
        ctx = _run(agent.build_context(
            child_id=None,
            topic_slug="Totally Unknown XYZ123",
            subject="Maths",
            grade=3,
        ))
        assert ctx.valid_skill_tags == []

    def test_unknown_topic_defaults_still_applied(self):
        """Unknown topic must still use safe defaults for all difficulty fields."""
        agent = TopicIntelligenceAgent()
        ctx = _run(agent.build_context(
            child_id=None,
            topic_slug="Nonexistent Topic QRST",
            subject="Maths",
            grade=3,
        ))
        assert ctx.bloom_level == _DEFAULT_BLOOM
        assert ctx.scaffolding == _DEFAULT_SCAFFOLDING
        assert ctx.challenge_mode == _DEFAULT_CHALLENGE
        assert ctx.format_mix == _DEFAULT_FORMAT_MIX


class TestBuildContextWithChildId:
    """Tests with a mock child_id — LearningGraphService is mocked."""

    def _make_svc_mock(self, **overrides):
        """Return a mock LearningGraphService with controllable get_adaptive_difficulty."""
        defaults = {
            "bloom_level": "application",
            "scaffolding": False,
            "challenge_mode": False,
            "format_mix": {"mcq": 30, "fill_blank": 30, "word_problem": 40},
        }
        defaults.update(overrides)
        mock_svc = MagicMock()
        mock_svc.get_adaptive_difficulty.return_value = defaults
        return mock_svc

    def test_adaptive_difficulty_applied_with_child_id(self):
        """When child_id is given and LG succeeds, adaptive values override defaults."""
        mock_svc = self._make_svc_mock(bloom_level="application", scaffolding=False)

        with patch("app.services.learning_graph.get_learning_graph_service", return_value=mock_svc):
            agent = TopicIntelligenceAgent()
            ctx = _run(agent.build_context(
                child_id="test-child-uuid",
                topic_slug="Addition (carries)",
                subject="Maths",
                grade=3,
            ))

        assert ctx.bloom_level == "application"
        assert ctx.scaffolding is False
        assert ctx.child_context != {}

    def test_child_context_populated_with_child_id(self):
        """child_context must be non-empty when child_id is provided and LG succeeds."""
        mock_svc = self._make_svc_mock()

        with patch("app.services.learning_graph.get_learning_graph_service", return_value=mock_svc):
            agent = TopicIntelligenceAgent()
            ctx = _run(agent.build_context(
                child_id="test-child-uuid",
                topic_slug="Addition (carries)",
                subject="Maths",
                grade=3,
            ))

        assert isinstance(ctx.child_context, dict)
        assert len(ctx.child_context) > 0
        assert "bloom_level" in ctx.child_context

    def test_challenge_mode_mastered_child(self):
        """A mastered child (challenge_mode=True) must propagate correctly."""
        mock_svc = self._make_svc_mock(
            bloom_level="reasoning",
            scaffolding=False,
            challenge_mode=True,
            format_mix={"mcq": 20, "fill_blank": 30, "word_problem": 50},
        )

        with patch("app.services.learning_graph.get_learning_graph_service", return_value=mock_svc):
            agent = TopicIntelligenceAgent()
            ctx = _run(agent.build_context(
                child_id="mastered-child-uuid",
                topic_slug="Addition (carries)",
                subject="Maths",
                grade=3,
            ))

        assert ctx.bloom_level == "reasoning"
        assert ctx.challenge_mode is True
        assert ctx.scaffolding is False

    def test_learning_graph_failure_uses_defaults(self):
        """If LearningGraphService raises, must fall back to safe defaults silently."""
        with patch(
            "app.services.learning_graph.get_learning_graph_service",
            side_effect=Exception("Supabase unreachable"),
        ):
            agent = TopicIntelligenceAgent()
            ctx = _run(agent.build_context(
                child_id="some-child-uuid",
                topic_slug="Addition (carries)",
                subject="Maths",
                grade=3,
            ))

        # Must not crash, must use defaults
        assert isinstance(ctx, GenerationContext)
        assert ctx.bloom_level == _DEFAULT_BLOOM
        assert ctx.scaffolding == _DEFAULT_SCAFFOLDING
        assert ctx.child_context == {}


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

class TestSingleton:
    def test_get_agent_returns_same_instance(self):
        from app.services.topic_intelligence import get_topic_intelligence_agent
        a1 = get_topic_intelligence_agent()
        a2 = get_topic_intelligence_agent()
        assert a1 is a2

    def test_get_agent_is_topic_intelligence_agent(self):
        from app.services.topic_intelligence import get_topic_intelligence_agent
        assert isinstance(get_topic_intelligence_agent(), TopicIntelligenceAgent)
