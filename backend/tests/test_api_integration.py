"""
Integration tests for API endpoints using FastAPI TestClient.

Tests cover:
  - Health endpoints (GET /health, GET /health/deep)
  - Children CRUD (POST/GET/PUT/DELETE /api/children)
  - Saved worksheets (POST /api/worksheets/save, GET /api/worksheets/saved/list)
  - Worksheet generation v2 (POST /api/v2/worksheets/generate)
  - Auth enforcement (missing/invalid tokens → 401)

All tests run FULLY OFFLINE using dependency overrides.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.deps import get_ai_client, get_openai_compat_client, get_supabase_client, get_user_id
from app.services.pdf import get_pdf_service

# Import conftest fixtures/helpers
from tests.conftest import TEST_USER_ID, FakeAIClient, FakeOpenAICompat, FakeSupabase

# ─────────────────────────────────────────────────────────────────────────────
# Fixture: build a fresh TestClient per test
# ─────────────────────────────────────────────────────────────────────────────


def _build_client(
    fake_db: FakeSupabase | None = None,
    user_id: str = TEST_USER_ID,
    require_auth: bool = False,
) -> TestClient:
    """Build a FastAPI TestClient with overridden dependencies.

    Args:
        fake_db: Pre-configured FakeSupabase. Uses empty default if None.
        user_id: The user_id returned by the auth override.
        require_auth: If True, does NOT override get_user_id (auth required).
    """
    from app.api.children import router as children_router
    from app.api.health import router as health_router
    from app.api.saved_worksheets import router as saved_ws_router
    from app.api.worksheets_v2 import router as ws_v2_router

    app = FastAPI()
    app.include_router(health_router)
    app.include_router(children_router)
    app.include_router(saved_ws_router)
    app.include_router(ws_v2_router)

    db = fake_db or FakeSupabase()
    app.dependency_overrides[get_supabase_client] = lambda: db

    if not require_auth:
        app.dependency_overrides[get_user_id] = lambda: user_id

    # AI client stubs
    app.dependency_overrides[get_ai_client] = lambda: FakeAIClient()
    app.dependency_overrides[get_openai_compat_client] = lambda: FakeOpenAICompat()

    # PDF service stub
    pdf_mock = MagicMock()
    pdf_mock.generate_pdf.return_value = b"%PDF-1.4 fake"
    app.dependency_overrides[get_pdf_service] = lambda: pdf_mock

    return TestClient(app, raise_server_exceptions=False)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Health Endpoints
# ─────────────────────────────────────────────────────────────────────────────


class TestHealthEndpoints:
    def test_health_returns_200(self):
        client = _build_client()
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_deep_health_returns_checks(self):
        """Deep health connects to Supabase & Gemini — will show errors with fakes,
        but should not crash (returns 200 with 'degraded' status)."""
        client = _build_client()
        resp = client.get("/health/deep")
        assert resp.status_code == 200
        body = resp.json()
        assert "status" in body
        assert "checks" in body


# ─────────────────────────────────────────────────────────────────────────────
# 2. Children CRUD
# ─────────────────────────────────────────────────────────────────────────────


class TestChildrenEndpoints:
    def _db_with_children(self) -> FakeSupabase:
        return FakeSupabase(
            table_data={
                "children": [
                    {
                        "id": "child-1",
                        "user_id": TEST_USER_ID,
                        "name": "Aryan",
                        "grade": "Class 3",
                        "board": "CBSE",
                        "notes": None,
                        "created_at": "2026-01-01T00:00:00Z",
                        "updated_at": "2026-01-01T00:00:00Z",
                    },
                ],
            },
            user_id=TEST_USER_ID,
        )

    def test_list_children_returns_200(self):
        client = _build_client(self._db_with_children())
        resp = client.get("/api/children/")
        assert resp.status_code == 200
        body = resp.json()
        assert "children" in body
        assert len(body["children"]) == 1
        assert body["children"][0]["name"] == "Aryan"

    def test_get_child_returns_200(self):
        client = _build_client(self._db_with_children())
        resp = client.get("/api/children/child-1")
        assert resp.status_code == 200

    def test_create_child_returns_200(self):
        db = FakeSupabase(
            table_data={
                "children": [{"id": "new-child", "user_id": TEST_USER_ID, "name": "Diya", "grade": "Class 2", "board": "CBSE", "notes": None, "created_at": "2026-01-01", "updated_at": "2026-01-01"}],
            },
        )
        client = _build_client(db)
        resp = client.post(
            "/api/children/",
            json={"name": "Diya", "grade": "Class 2", "board": "CBSE"},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_create_child_empty_name_fails(self):
        """Pydantic validation: name is required."""
        client = _build_client()
        resp = client.post(
            "/api/children/",
            json={"grade": "Class 3"},
        )
        assert resp.status_code == 422  # Validation error


# ─────────────────────────────────────────────────────────────────────────────
# 3. Saved Worksheets
# ─────────────────────────────────────────────────────────────────────────────


class TestSavedWorksheetEndpoints:
    def _db_with_worksheets(self) -> FakeSupabase:
        return FakeSupabase(
            table_data={
                "worksheets": [
                    {
                        "id": "ws-1",
                        "user_id": TEST_USER_ID,
                        "title": "Addition Worksheet",
                        "board": "CBSE",
                        "grade": "Class 3",
                        "subject": "Maths",
                        "topic": "Addition",
                        "difficulty": "easy",
                        "language": "English",
                        "questions": [],
                        "created_at": "2026-01-15T10:00:00Z",
                        "children": None,
                        "teacher_classes": None,
                    },
                ],
            },
        )

    def test_save_worksheet_returns_200(self):
        db = FakeSupabase(
            table_data={
                "worksheets": [{"id": "ws-new", "user_id": TEST_USER_ID}],
            },
        )
        client = _build_client(db)
        resp = client.post(
            "/api/worksheets/save",
            json={
                "worksheet": {
                    "title": "Test Worksheet",
                    "grade": "Class 3",
                    "subject": "Maths",
                    "topic": "Addition",
                    "difficulty": "easy",
                    "language": "English",
                    "questions": [
                        {"id": "q1", "type": "mcq", "text": "What is 2+3?", "options": ["3", "4", "5", "6"], "correct_answer": "5"},
                    ],
                },
                "board": "CBSE",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True

    def test_list_saved_worksheets_returns_200(self):
        client = _build_client(self._db_with_worksheets())
        resp = client.get("/api/worksheets/saved/list")
        assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# 4. Worksheet Generation v2
# ─────────────────────────────────────────────────────────────────────────────


class TestWorksheetGenerationV2:
    def _make_generate_request(self) -> dict:
        return {
            "board": "CBSE",
            "grade_level": "Class 3",
            "subject": "Maths",
            "topic": "Addition (carries)",
            "difficulty": "easy",
            "num_questions": 5,
            "language": "English",
            "problem_style": "standard",
        }

    def test_generate_with_mocked_llm(self):
        """Full integration: mock the LLM, verify the endpoint returns a worksheet."""
        from tests.test_worksheet_pipeline_async import _make_raw_response

        db = FakeSupabase(
            rpc_data={
                "increment_worksheet_usage": {"allowed": True, "tier": "free", "remaining": 9, "message": ""},
            },
        )

        mock_openai = MagicMock()
        raw = _make_raw_response(5, "Addition (carries)")
        mock_openai.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=raw))]
        )

        from app.api.health import router as health_router
        from app.api.worksheets_v2 import router as ws_v2_router

        app = FastAPI()
        app.include_router(health_router)
        app.include_router(ws_v2_router)

        app.dependency_overrides[get_supabase_client] = lambda: db
        app.dependency_overrides[get_user_id] = lambda: TEST_USER_ID
        app.dependency_overrides[get_ai_client] = lambda: FakeAIClient()
        app.dependency_overrides[get_openai_compat_client] = lambda: mock_openai

        client = TestClient(app, raise_server_exceptions=False)

        # Mock quality scorer to return a passing score for mock data
        mock_qs = MagicMock(total_score=85.0, export_allowed=True, gold_standard_eligible=False)
        with patch("app.services.curriculum.get_curriculum_context", return_value=None), \
             patch("app.services.quality_scorer.score_worksheet", return_value=mock_qs):
            resp = client.post(
                "/api/v2/worksheets/generate",
                json=self._make_generate_request(),
            )

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        body = resp.json()
        assert "worksheet" in body
        assert body["worksheet"]["subject"] == "Maths"
        assert len(body["worksheet"]["questions"]) == 5

    def test_subscription_denied_returns_402(self):
        """If the subscription check returns allowed=False, expect 402."""
        db = FakeSupabase(
            rpc_data={
                "increment_worksheet_usage": {
                    "allowed": False,
                    "tier": "free",
                    "remaining": 0,
                    "message": "Free tier limit reached",
                },
            },
        )

        from app.api.worksheets_v2 import router as ws_v2_router

        app = FastAPI()
        app.include_router(ws_v2_router)

        app.dependency_overrides[get_supabase_client] = lambda: db
        app.dependency_overrides[get_user_id] = lambda: TEST_USER_ID
        app.dependency_overrides[get_ai_client] = lambda: FakeAIClient()
        app.dependency_overrides[get_openai_compat_client] = lambda: FakeOpenAICompat()

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/v2/worksheets/generate",
            json=self._make_generate_request(),
        )
        assert resp.status_code == 402

    def test_invalid_grade_returns_422(self):
        """Pydantic validation: invalid grade should fail."""
        client = _build_client()
        req = self._make_generate_request()
        req["grade_level"] = "Grade INVALID"
        resp = client.post("/api/v2/worksheets/generate", json=req)
        assert resp.status_code == 422

    def test_invalid_subject_returns_422(self):
        """Pydantic validation: invalid subject should fail."""
        client = _build_client()
        req = self._make_generate_request()
        req["subject"] = "Alchemy"
        resp = client.post("/api/v2/worksheets/generate", json=req)
        assert resp.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# 5. Auth Enforcement
# ─────────────────────────────────────────────────────────────────────────────


class TestAuthEnforcement:
    """Test that endpoints requiring auth actually fail without it."""

    def test_children_list_without_auth_returns_422(self):
        """When get_user_id is NOT overridden, missing Authorization header → 422."""
        client = _build_client(require_auth=True)
        resp = client.get("/api/children/")
        # FastAPI returns 422 when a required Header() is missing
        assert resp.status_code == 422

    def test_worksheets_save_without_auth_returns_422(self):
        client = _build_client(require_auth=True)
        resp = client.post(
            "/api/worksheets/save",
            json={
                "worksheet": {
                    "title": "Test",
                    "grade": "Class 3",
                    "subject": "Maths",
                    "topic": "Addition",
                    "questions": [],
                },
            },
        )
        assert resp.status_code == 422

    def test_health_does_not_require_auth(self):
        """Health endpoint should work without auth."""
        client = _build_client(require_auth=True)
        resp = client.get("/health")
        assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# 6. Subscription Check Service (unit test)
# ─────────────────────────────────────────────────────────────────────────────


class TestSubscriptionCheck:
    def test_check_and_increment_allowed(self):
        import asyncio

        from app.services.subscription_check import check_and_increment_usage

        db = FakeSupabase(
            rpc_data={
                "increment_worksheet_usage": [{"allowed": True, "tier": "free", "remaining": 8, "message": ""}],
            },
        )
        result = asyncio.run(check_and_increment_usage("user-123", db))
        assert result["allowed"] is True
        assert result["tier"] == "free"

    def test_check_and_increment_denied(self):
        import asyncio

        from app.services.subscription_check import check_and_increment_usage

        db = FakeSupabase(
            rpc_data={
                "increment_worksheet_usage": [{"allowed": False, "tier": "free", "remaining": 0, "message": "Limit reached"}],
            },
        )
        result = asyncio.run(check_and_increment_usage("user-123", db))
        assert result["allowed"] is False

    def test_db_failure_fails_closed(self):
        import asyncio

        from app.services.subscription_check import check_and_increment_usage

        # A client that raises on rpc()
        db = MagicMock()
        db.rpc.side_effect = Exception("DB down")
        result = asyncio.run(check_and_increment_usage("user-123", db))
        assert result["allowed"] is False
        assert result["tier"] == "unknown"
