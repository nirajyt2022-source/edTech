"""Tests for D-05: Diagnostic Context Builder — pure logic tests."""

from app.services.diagnostic_context import DiagnosticContext, build_diagnostic_context


class TestDiagnosticContextDefaults:
    def test_no_child_id_returns_normal(self):
        ctx = build_diagnostic_context(
            child_id=None,
            topic_slug="Addition (carries)",
            subject="Maths",
            grade=2,
        )
        assert ctx.mode == "normal"
        assert "anonymous" in ctx.rationale.lower() or "No child_id" in ctx.rationale

    def test_diagnostic_db_disabled_returns_normal(self, monkeypatch):
        monkeypatch.delenv("ENABLE_DIAGNOSTIC_DB", raising=False)
        ctx = build_diagnostic_context(
            child_id="some-uuid",
            topic_slug="Addition (carries)",
            subject="Maths",
            grade=2,
        )
        assert ctx.mode == "normal"
        assert "disabled" in ctx.rationale.lower()

    def test_dataclass_defaults(self):
        ctx = DiagnosticContext(mode="normal")
        assert ctx.target_skill_tags == []
        assert ctx.avoid_skill_tags == []
        assert ctx.misconceptions_to_target == []
        assert ctx.difficulty_override is None
        assert ctx.rationale == ""


class TestDiagnosticContextWithDB:
    """Tests that mock the DB services to verify mode selection logic."""

    def test_remediation_mode_with_systematic_errors(self, monkeypatch):
        """2+ systematic errors → remediation mode."""
        monkeypatch.setenv("ENABLE_DIAGNOSTIC_DB", "1")

        from app.services.error_pattern_detector import ErrorPattern

        fake_patterns = [
            ErrorPattern(
                misconception_id="ADD_NO_CARRY",
                misconception_display="Forgets carry",
                domain="addition",
                occurrences=5,
                total_attempts=10,
                error_rate=0.7,
                is_systematic=True,
                affected_skill_tags=["column_add_with_carry"],
            ),
            ErrorPattern(
                misconception_id="ADD_DIGIT_CONCAT",
                misconception_display="Concatenates digits",
                domain="addition",
                occurrences=3,
                total_attempts=10,
                error_rate=0.5,
                is_systematic=True,
                affected_skill_tags=["addition_word_problem"],
            ),
        ]

        class FakeDetector:
            def detect_patterns(self, child_id, lookback_days=30):
                return fake_patterns

        class FakeLG:
            def _get_sb(self):
                return None

            def _get_topic_mastery_row(self, sb, child_id, topic_slug):
                return {"mastery_level": "learning"}

        monkeypatch.setattr(
            "app.services.error_pattern_detector.get_error_pattern_detector",
            lambda: FakeDetector(),
        )
        monkeypatch.setattr(
            "app.services.learning_graph.get_learning_graph_service",
            lambda: FakeLG(),
        )

        ctx = build_diagnostic_context(
            child_id="test-child",
            topic_slug="Addition (carries)",
            subject="Maths",
            grade=2,
        )

        assert ctx.mode == "remediation"
        assert ctx.difficulty_override == "easy"
        assert "ADD_NO_CARRY" in ctx.misconceptions_to_target
        assert "column_add_with_carry" in ctx.target_skill_tags

    def test_reinforcement_mode_when_mastered(self, monkeypatch):
        """Mastered topic → reinforcement mode."""
        monkeypatch.setenv("ENABLE_DIAGNOSTIC_DB", "1")

        class FakeDetector:
            def detect_patterns(self, child_id, lookback_days=30):
                return []

        class FakeLG:
            def _get_sb(self):
                return None

            def _get_topic_mastery_row(self, sb, child_id, topic_slug):
                return {"mastery_level": "mastered"}

        monkeypatch.setattr(
            "app.services.error_pattern_detector.get_error_pattern_detector",
            lambda: FakeDetector(),
        )
        monkeypatch.setattr(
            "app.services.learning_graph.get_learning_graph_service",
            lambda: FakeLG(),
        )

        ctx = build_diagnostic_context(
            child_id="test-child",
            topic_slug="Addition (carries)",
            subject="Maths",
            grade=2,
        )

        assert ctx.mode == "reinforcement"
        assert ctx.difficulty_override == "hard"

    def test_normal_mode_with_one_systematic_error(self, monkeypatch):
        """Only 1 systematic error → still normal mode."""
        monkeypatch.setenv("ENABLE_DIAGNOSTIC_DB", "1")

        from app.services.error_pattern_detector import ErrorPattern

        class FakeDetector:
            def detect_patterns(self, child_id, lookback_days=30):
                return [ErrorPattern(
                    misconception_id="ADD_NO_CARRY",
                    misconception_display="Forgets carry",
                    domain="addition",
                    occurrences=3,
                    total_attempts=6,
                    error_rate=0.5,
                    is_systematic=True,
                    affected_skill_tags=["column_add_with_carry"],
                )]

        class FakeLG:
            def _get_sb(self):
                return None

            def _get_topic_mastery_row(self, sb, child_id, topic_slug):
                return {"mastery_level": "learning"}

        monkeypatch.setattr(
            "app.services.error_pattern_detector.get_error_pattern_detector",
            lambda: FakeDetector(),
        )
        monkeypatch.setattr(
            "app.services.learning_graph.get_learning_graph_service",
            lambda: FakeLG(),
        )

        ctx = build_diagnostic_context(
            child_id="test-child",
            topic_slug="Addition (carries)",
            subject="Maths",
            grade=2,
        )

        assert ctx.mode == "normal"
        assert "systematic" in ctx.rationale.lower() or "ADD_NO_CARRY" in ctx.rationale or "Forgets carry" in ctx.rationale
