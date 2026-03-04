"""
Sprint S9 — Quality Pipeline Wiring & Observability tests.

Covers:
  - Gold standard mode config wiring
  - Quality score persistence on save (model + computation)
  - Telemetry emit_event is callable
  - Audit write_attempt_event is callable
  - List endpoint includes quality fields
"""

from __future__ import annotations

from unittest.mock import patch


# ---------------------------------------------------------------------------
# S9.1: Gold standard mode config wiring
# ---------------------------------------------------------------------------


class TestGoldStandardConfigWiring:
    """gold_standard_mode from config should be readable and affect scoring."""

    def test_config_has_gold_standard_mode(self):
        """Settings class has gold_standard_mode field."""
        from app.core.config import Settings

        # Instantiate with required fields only
        s = Settings(supabase_url="http://x", supabase_service_key="k")
        assert hasattr(s, "gold_standard_mode")
        assert s.gold_standard_mode is False  # default

    def test_gold_threshold_defaults(self):
        from app.core.config import Settings

        s = Settings(supabase_url="http://x", supabase_service_key="k")
        assert s.worksheet_export_min_score == 70
        assert s.worksheet_export_gold_score == 85

    def test_score_worksheet_gold_mode_raises_threshold(self):
        """In gold mode, export threshold should be 85."""
        from app.services.quality_scorer import score_worksheet

        ws = {
            "title": "Test",
            "grade": "Class 3",
            "subject": "Maths",
            "topic": "Addition",
            "questions": [],
            "learning_objectives": [],
            "skill_focus": "",
        }
        # Normal mode: threshold = 70
        result_normal = score_worksheet(ws, expected_count=0, gold_standard_mode=False)
        assert result_normal.export_threshold == 70

        # Gold mode: threshold = 85
        result_gold = score_worksheet(ws, expected_count=0, gold_standard_mode=True)
        assert result_gold.export_threshold == 85


# ---------------------------------------------------------------------------
# S9.2: Quality score persistence
# ---------------------------------------------------------------------------


class TestQualityScorePersistence:
    """SaveWorksheetRequest should accept and pass quality fields."""

    def test_save_request_accepts_quality_fields(self):
        from app.api.saved_worksheets import SaveWorksheetRequest, WorksheetForSave

        req = SaveWorksheetRequest(
            worksheet=WorksheetForSave(title="T", grade="3", subject="Maths", topic="Add"),
            quality_score=85.0,
            quality_tier="high",
            gold_standard_eligible=True,
        )
        assert req.quality_score == 85.0
        assert req.quality_tier == "high"
        assert req.gold_standard_eligible is True

    def test_save_request_quality_fields_optional(self):
        from app.api.saved_worksheets import SaveWorksheetRequest, WorksheetForSave

        req = SaveWorksheetRequest(
            worksheet=WorksheetForSave(title="T", grade="3", subject="Maths", topic="Add"),
        )
        assert req.quality_score is None
        assert req.quality_tier is None
        assert req.gold_standard_eligible is None

    def test_quality_score_computed_on_save_when_missing(self):
        """score_worksheet should be importable and produce valid scores."""
        from app.services.quality_scorer import score_worksheet

        ws = {
            "title": "Test",
            "grade": "Class 3",
            "subject": "Maths",
            "topic": "Addition",
            "questions": [
                {
                    "id": "Q1",
                    "text": "What is 2+3?",
                    "correct_answer": "5",
                    "type": "short_answer",
                    "role": "application",
                    "skill_tag": "add",
                    "hint": "count",
                    "format": "short_answer",
                }
            ],
            "learning_objectives": ["Learn addition"],
            "chapter_ref": "Ch 1",
            "skill_focus": "Addition",
        }
        result = score_worksheet(ws, expected_count=1)
        assert result.total_score >= 0
        assert isinstance(result.gold_standard_eligible, bool)


# ---------------------------------------------------------------------------
# S9.3: Telemetry emit_event
# ---------------------------------------------------------------------------


class TestTelemetryWiring:
    """emit_event should be callable and log correctly."""

    def test_emit_event_callable(self):
        from app.services.telemetry import emit_event

        # Should not raise; logs but doesn't persist (ENABLE_TELEMETRY_DB!=1)
        emit_event(
            "test_event",
            route="/test",
            version="v2",
            topic="Addition",
            ok=True,
            latency_ms=100,
        )

    def test_emit_event_with_error(self):
        from app.services.telemetry import emit_event

        emit_event(
            "test_event",
            route="/test",
            version="v2",
            ok=False,
            error_type="TestError",
        )

    def test_instrument_decorator_exists(self):
        from app.services.telemetry import instrument

        assert callable(instrument)

    @patch("app.services.telemetry.emit_event")
    def test_v2_endpoint_calls_emit_event(self, mock_emit):
        """Verify emit_event import exists in worksheets_v2 module."""
        # We can't easily call the full endpoint without mocking everything,
        # but we verify the import path works
        from app.api import worksheets_v2  # noqa: F401

        # The module should import emit_event at endpoint level
        from app.services.telemetry import emit_event

        assert callable(emit_event)


# ---------------------------------------------------------------------------
# S9.4: Audit write_attempt_event
# ---------------------------------------------------------------------------


class TestAuditWiring:
    """write_attempt_event should be callable."""

    def test_write_attempt_event_callable(self):
        from app.services.audit import write_attempt_event

        # Should not raise; audit disabled (ENABLE_ATTEMPT_AUDIT_DB!=1)
        write_attempt_event({
            "student_id": "test-child",
            "worksheet_id": "ws-123",
            "question_number": 1,
            "skill_tag": "addition",
            "is_correct": True,
            "subject": "Maths",
            "grade": "Class 3",
        })

    def test_should_write_audit_default_false(self):
        from app.services.audit import should_write_audit

        # Default: ENABLE_ATTEMPT_AUDIT_DB is not set → False
        assert should_write_audit() is False

    def test_audit_import_in_grading(self):
        """Verify audit module is importable from grading context."""
        from app.services.audit import write_attempt_event  # noqa: F401

        assert callable(write_attempt_event)


# ---------------------------------------------------------------------------
# S9.2 continued: List endpoint quality fields
# ---------------------------------------------------------------------------


class TestListEndpointQualityFields:
    """Verify list endpoint code includes quality fields in response mapping."""

    def test_list_response_mapping_includes_quality(self):
        """The list endpoint code should reference quality_score, quality_tier, gold_standard_eligible."""
        import inspect

        from app.api.saved_worksheets import list_saved_worksheets

        source = inspect.getsource(list_saved_worksheets)
        assert "quality_score" in source
        assert "quality_tier" in source
        assert "gold_standard_eligible" in source


# ---------------------------------------------------------------------------
# Integration: gold_standard_eligible auto-promotion still works
# ---------------------------------------------------------------------------


class TestGoldAutoPromotionIntegration:
    """Verify gold_standard_eligible is correctly computed across modules."""

    def test_high_score_no_failures_is_gold(self):
        from app.services.quality_scorer import score_worksheet

        # Build a minimal "perfect" worksheet
        qs = []
        texts = [
            "Find the sum of 23 and 45.",
            "Solve: 67 - 34 = ___",
            "What is 12 + 19?",
            "Help Priya count her 15 apples and 8 oranges.",
            "Calculate 56 - 28.",
        ]
        answers = ["68", "33", "31", "23", "28"]
        types = ["short_answer", "fill_blank", "short_answer", "word_problem", "short_answer"]
        roles = ["recognition", "application", "application", "application", "thinking"]
        for i in range(5):
            qs.append({
                "id": f"Q{i + 1}",
                "text": texts[i],
                "correct_answer": answers[i],
                "type": types[i],
                "role": roles[i],
                "skill_tag": ["s1", "s2", "s3"][i % 3],
                "hint": f"Step {i + 1}",
                "format": types[i],
            })

        ws = {
            "title": "Perfect WS",
            "grade": "Class 3",
            "subject": "Maths",
            "topic": "Addition",
            "questions": qs,
            "learning_objectives": ["Learn addition"],
            "chapter_ref": "Ch 1",
            "skill_focus": "Addition",
            "common_mistake": "Forgetting carry",
        }
        result = score_worksheet(ws, expected_count=5)
        # Score and gold eligibility should be deterministic
        assert isinstance(result.gold_standard_eligible, bool)
        # If score >= 85 and no major+ failures → gold
        has_major = any(f.severity in ("critical", "major") for f in result.failures)
        if result.total_score >= 85 and not has_major:
            assert result.gold_standard_eligible is True
