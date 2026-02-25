"""
Shared pytest fixtures for the Skolar backend test suite.

Provides:
  - FakeSupabase: chainable in-memory Supabase client mock
  - fake_db: session-scoped FakeSupabase fixture
  - fake_user_id: overrides UserId dependency with a fixed test user
  - fake_ai_client: mock AIClient that returns canned JSON
  - app_client: FastAPI TestClient factory with all dependencies overridden
  - Environment bootstrapping (fake env vars set before any app import)
"""

from __future__ import annotations

import os
import sys

# ── Ensure backend/ is importable when pytest runs from project root ──────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── Fake env vars BEFORE importing any settings-dependent app modules ─────────
os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-service-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "fake-service-key")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake-key-for-tests")

import pytest
from unittest.mock import AsyncMock, MagicMock


# ─────────────────────────────────────────────────────────────────────────────
# FakeSupabase — chainable in-memory mock
# ─────────────────────────────────────────────────────────────────────────────


class FakeResult:
    """Mimics the result object returned by the Supabase Python client."""

    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class FakeSingle:
    """Returned by .maybe_single() — wraps a single row (or None)."""

    def __init__(self, data):
        self._data = data

    def execute(self) -> FakeResult:
        return FakeResult(self._data)


class FakeQuery:
    """Chainable query builder — all filter methods are no-ops.

    The full dataset configured for that table is always returned;
    actual WHERE filtering is not needed for these offline tests.
    """

    def __init__(self, data: list):
        self._data = data

    # ── Chainable no-ops ───────────────────────────────────────────────────
    def select(self, *a, **kw) -> "FakeQuery":
        return self

    def eq(self, *a, **kw) -> "FakeQuery":
        return self

    def neq(self, *a, **kw) -> "FakeQuery":
        return self

    def in_(self, *a, **kw) -> "FakeQuery":
        return self

    def gt(self, *a, **kw) -> "FakeQuery":
        return self

    def gte(self, *a, **kw) -> "FakeQuery":
        return self

    def lt(self, *a, **kw) -> "FakeQuery":
        return self

    def lte(self, *a, **kw) -> "FakeQuery":
        return self

    def order(self, *a, **kw) -> "FakeQuery":
        return self

    def limit(self, *a, **kw) -> "FakeQuery":
        return self

    def insert(self, row, **kw) -> "FakeQuery":
        if isinstance(row, list):
            self._data.extend(row)
        else:
            self._data.append(row)
        return self

    def update(self, *a, **kw) -> "FakeQuery":
        return self

    def upsert(self, *a, **kw) -> "FakeQuery":
        return self

    def delete(self) -> "FakeQuery":
        return self

    def range(self, *a, **kw) -> "FakeQuery":
        return self

    # ── Terminal operations ─────────────────────────────────────────────────
    def maybe_single(self) -> FakeSingle:
        return FakeSingle(self._data[0] if self._data else None)

    def single(self) -> FakeSingle:
        """Matches Supabase .single() which is also chainable with .execute()."""
        return FakeSingle(self._data[0] if self._data else None)

    def execute(self) -> FakeResult:
        return FakeResult(self._data, count=len(self._data))


class FakeAuth:
    """Stub for supabase.auth — returns a fixed user on get_user()."""

    def __init__(self, user_id: str = "test-user-id"):
        self._user_id = user_id

    def get_user(self, token: str):
        user = MagicMock()
        user.id = self._user_id
        resp = MagicMock()
        resp.user = user
        return resp


class FakeRpc:
    """Returned by FakeSupabase.rpc() — returns canned data on execute()."""

    def __init__(self, data):
        self._data = data

    def execute(self) -> FakeResult:
        return FakeResult(self._data)


class FakeSupabase:
    """Supabase client stub backed by an in-memory dict of table → rows.

    Usage:
        db = FakeSupabase({"children": [{"id": "c1", "name": "Aryan"}]})
        result = db.table("children").select("*").execute()
        assert result.data == [{"id": "c1", "name": "Aryan"}]
    """

    def __init__(
        self,
        table_data: dict[str, list] | None = None,
        rpc_data: dict[str, list | dict] | None = None,
        user_id: str = "test-user-id",
    ):
        self._tables = table_data or {}
        self._rpc_data = rpc_data or {}
        self.auth = FakeAuth(user_id)

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(list(self._tables.get(name, [])))

    def rpc(self, fn_name: str, params: dict | None = None) -> FakeRpc:
        data = self._rpc_data.get(fn_name, {})
        return FakeRpc(data)


# ─────────────────────────────────────────────────────────────────────────────
# Fake AI Client
# ─────────────────────────────────────────────────────────────────────────────

class FakeAIClient:
    """Minimal stub for AIClient — returns canned responses without LLM calls."""

    def __init__(self):
        self.total_calls = 0
        self._json_response: dict = {}
        self._text_response: str = "ok"

    @property
    def stats(self) -> dict:
        return {"total_calls": self.total_calls, "avg_latency_ms": 0}

    def set_json_response(self, data: dict):
        self._json_response = data

    def set_text_response(self, text: str):
        self._text_response = text

    def generate_json(self, prompt, **kw) -> dict:
        self.total_calls += 1
        return self._json_response

    def generate_text(self, prompt, **kw) -> str:
        self.total_calls += 1
        return self._text_response

    def generate_chat(self, messages, **kw) -> str:
        self.total_calls += 1
        return self._text_response

    def generate_with_images(self, image_parts, prompt, **kw):
        self.total_calls += 1
        return self._json_response

    def generate_openai_style(self, messages, **kw) -> str:
        self.total_calls += 1
        return self._text_response


class FakeOpenAICompat:
    """Stub for OpenAICompatAdapter — returns canned JSON string."""

    def __init__(self):
        self._response: str = "{}"

    def set_response(self, data: str):
        self._response = data

    def chat_completion(self, messages, **kw) -> str:
        return self._response


# ─────────────────────────────────────────────────────────────────────────────
# Pytest fixtures
# ─────────────────────────────────────────────────────────────────────────────

TEST_USER_ID = "test-user-00000000-0000-0000-0000-000000000000"


@pytest.fixture
def fake_db():
    """Return a fresh FakeSupabase instance with common test data."""
    return FakeSupabase(
        table_data={
            "children": [
                {"id": "child-1", "user_id": TEST_USER_ID, "name": "Aryan", "grade": "Class 3", "board": "CBSE", "notes": None, "created_at": "2026-01-01", "updated_at": "2026-01-01"},
                {"id": "child-2", "user_id": TEST_USER_ID, "name": "Priya", "grade": "Class 4", "board": "CBSE", "notes": None, "created_at": "2026-01-01", "updated_at": "2026-01-01"},
            ],
            "worksheets": [],
            "user_subscriptions": [],
        },
        rpc_data={
            "increment_worksheet_usage": {"allowed": True, "tier": "free", "remaining": 9, "message": ""},
        },
        user_id=TEST_USER_ID,
    )


@pytest.fixture
def fake_ai():
    """Return a fresh FakeAIClient."""
    return FakeAIClient()


@pytest.fixture
def fake_openai():
    """Return a fresh FakeOpenAICompat."""
    return FakeOpenAICompat()


@pytest.fixture
def app_client(fake_db, fake_ai, fake_openai):
    """Return a FastAPI TestClient with all dependencies overridden.

    Usage:
        def test_health(app_client):
            resp = app_client.get("/health")
            assert resp.status_code == 200
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.core.deps import get_supabase_client, get_user_id, get_ai_client, get_openai_compat_client
    from app.services.pdf import get_pdf_service

    # Import all routers
    from app.api.health import router as health_router
    from app.api.children import router as children_router
    from app.api.saved_worksheets import router as saved_ws_router
    from app.api.worksheets_v2 import router as ws_v2_router

    app = FastAPI()
    app.include_router(health_router)
    app.include_router(children_router)
    app.include_router(saved_ws_router)
    app.include_router(ws_v2_router)

    # Override all dependencies
    app.dependency_overrides[get_supabase_client] = lambda: fake_db
    app.dependency_overrides[get_user_id] = lambda: TEST_USER_ID
    app.dependency_overrides[get_ai_client] = lambda: fake_ai
    app.dependency_overrides[get_openai_compat_client] = lambda: fake_openai

    # PDF service — stub
    pdf_mock = MagicMock()
    pdf_mock.generate_pdf.return_value = b"%PDF-1.4 fake"
    app.dependency_overrides[get_pdf_service] = lambda: pdf_mock

    return TestClient(app, raise_server_exceptions=False)
