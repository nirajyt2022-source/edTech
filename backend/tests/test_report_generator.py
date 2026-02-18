"""Tests for ClassReportGenerator and GET /api/reports/{token}.

All tests run FULLY OFFLINE — no Supabase connection, no LLM calls.

Coverage:
  1. generate_class_report returns a report with the correct child count
  2. report_text for each child contains no underscores or slug-style words
  3. token is unique (two back-to-back calls must produce different tokens)
  4. GET /api/reports/{expired_token} returns HTTP 410
"""

import re
import sys
import os

# ── Ensure backend/ is importable when pytest runs from project root ──────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── Fake env vars BEFORE importing any settings-dependent app modules ─────────
os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-service-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "fake-service-key")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake-key-for-tests")

import pytest
from datetime import datetime, timezone, timedelta

from app.services.report_generator import ClassReportGenerator


# ─────────────────────────────────────────────────────────────────────────────
# Offline Supabase mock
# ─────────────────────────────────────────────────────────────────────────────

class _FakeResult:
    """Mimics the result object returned by the Supabase Python client."""

    def __init__(self, data):
        self.data = data


class _FakeSingle:
    """Returned by .maybe_single() — wraps a single row (or None)."""

    def __init__(self, data):
        self._data = data

    def execute(self) -> _FakeResult:
        return _FakeResult(self._data)


class _FakeQuery:
    """Chainable query builder — all filter methods are no-ops.

    The full dataset configured for that table is always returned; actual
    WHERE filtering is not needed for these offline tests.
    """

    def __init__(self, data: list):
        self._data = data

    # ── chainable no-ops ──────────────────────────────────────────────────
    def select(self, *a, **kw) -> "_FakeQuery":  return self
    def eq(self, *a, **kw) -> "_FakeQuery":       return self
    def in_(self, *a, **kw) -> "_FakeQuery":      return self
    def insert(self, *a, **kw) -> "_FakeQuery":   return self
    def update(self, *a, **kw) -> "_FakeQuery":   return self
    def upsert(self, *a, **kw) -> "_FakeQuery":   return self

    # ── terminal operations ───────────────────────────────────────────────
    def maybe_single(self) -> _FakeSingle:
        return _FakeSingle(self._data[0] if self._data else None)

    def execute(self) -> _FakeResult:
        return _FakeResult(self._data)


class _FakeSupabase:
    """Supabase client stub backed by an in-memory dict of table → rows."""

    def __init__(self, table_data: dict[str, list]):
        self._tables = table_data

    def table(self, name: str) -> _FakeQuery:
        return _FakeQuery(list(self._tables.get(name, [])))

    # The reports.py router accesses supabase.auth — we only stub what we need
    @property
    def auth(self):
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_sb(extra_mastery: list | None = None) -> _FakeSupabase:
    """Return a mock Supabase with two students in class 'cls-1'.

    - child_learning_summary is empty  →  get_child_summary() returns empty dicts
    - topic_mastery is empty by default →  no recommendations
    """
    return _FakeSupabase(
        {
            "teacher_classes": [
                {
                    "id": "cls-1",
                    "name": "Class 3A",
                    "grade": "3",
                    "subject": "Maths",
                    "user_id": "teacher-1",
                }
            ],
            "worksheets": [
                {"child_id": "child-1"},
                {"child_id": "child-2"},
            ],
            "children": [
                {"id": "child-1", "name": "Aryan"},
                {"id": "child-2", "name": "Priya"},
            ],
            "child_learning_summary": [],  # → empty summary → "just getting started"
            "topic_mastery": extra_mastery or [],
            "class_reports": [],           # receives inserts (no-op in mock)
        }
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 1 — generate_class_report returns correct child count
# ─────────────────────────────────────────────────────────────────────────────

class TestCorrectChildCount:
    def test_total_students_is_two(self):
        gen = ClassReportGenerator(supabase_client=_make_sb())
        result = gen.generate_class_report("cls-1", "teacher-1")
        assert result["report_data"]["total_students"] == 2

    def test_children_list_length_matches_total_students(self):
        gen = ClassReportGenerator(supabase_client=_make_sb())
        result = gen.generate_class_report("cls-1", "teacher-1")
        data = result["report_data"]
        assert len(data["children"]) == data["total_students"]

    def test_child_names_are_present(self):
        gen = ClassReportGenerator(supabase_client=_make_sb())
        result = gen.generate_class_report("cls-1", "teacher-1")
        names = {c["name"] for c in result["report_data"]["children"]}
        assert names == {"Aryan", "Priya"}

    def test_class_name_is_correct(self):
        gen = ClassReportGenerator(supabase_client=_make_sb())
        result = gen.generate_class_report("cls-1", "teacher-1")
        assert result["report_data"]["class_name"] == "Class 3A"

    def test_empty_class_returns_zero_students(self):
        """A class whose worksheets have no child_id should yield 0 students."""
        sb = _FakeSupabase(
            {
                "teacher_classes": [
                    {"id": "cls-2", "name": "Empty Class", "grade": "1", "subject": "English", "user_id": "t-x"}
                ],
                "worksheets": [],
                "children": [],
                "child_learning_summary": [],
                "topic_mastery": [],
                "class_reports": [],
            }
        )
        gen = ClassReportGenerator(supabase_client=sb)
        result = gen.generate_class_report("cls-2", "t-x")
        assert result["report_data"]["total_students"] == 0
        assert result["report_data"]["children"] == []


# ─────────────────────────────────────────────────────────────────────────────
# Test 2 — report_text contains no underscores or slug-style words
# ─────────────────────────────────────────────────────────────────────────────

_SLUG_RE = re.compile(r"\b\w+_\w+\b")  # e.g. "mth_c1_addition"


class TestReportTextQuality:
    def test_no_underscores_in_any_report_text(self):
        gen = ClassReportGenerator(supabase_client=_make_sb())
        result = gen.generate_class_report("cls-1", "teacher-1")
        for child in result["report_data"]["children"]:
            text = child["report_text"]
            assert "_" not in text, (
                f"Underscore found in report_text for {child['name']!r}: {text!r}"
            )

    def test_no_slug_patterns_in_report_text(self):
        gen = ClassReportGenerator(supabase_client=_make_sb())
        result = gen.generate_class_report("cls-1", "teacher-1")
        for child in result["report_data"]["children"]:
            text = child["report_text"]
            assert not _SLUG_RE.search(text), (
                f"Slug-style word found in report_text for {child['name']!r}: {text!r}"
            )

    def test_child_name_appears_in_report_text(self):
        gen = ClassReportGenerator(supabase_client=_make_sb())
        result = gen.generate_class_report("cls-1", "teacher-1")
        for child in result["report_data"]["children"]:
            assert child["name"] in child["report_text"], (
                f"Name {child['name']!r} missing from report_text: {child['report_text']!r}"
            )

    def test_report_text_is_nonempty_string(self):
        gen = ClassReportGenerator(supabase_client=_make_sb())
        result = gen.generate_class_report("cls-1", "teacher-1")
        for child in result["report_data"]["children"]:
            assert isinstance(child["report_text"], str)
            assert len(child["report_text"]) > 0

    def test_no_class_suffix_in_report_text(self):
        """Even when mastered topics carry '(Class N)' suffixes, they must be stripped."""
        sb_with_mastery = _make_sb(
            extra_mastery=[
                {
                    "child_id": "child-1",
                    "topic_slug": "Numbers 1 to 50 (Class 1)",
                    "mastery_level": "mastered",
                    "streak": 5,
                    "sessions_total": 10,
                    "last_practiced_at": None,
                }
            ]
        )
        # Patch child_learning_summary so child-1 has mastered topics
        sb_with_mastery._tables["child_learning_summary"] = [
            {
                "child_id": "child-1",
                "mastered_topics": ["Numbers 1 to 50 (Class 1)"],
                "improving_topics": [],
                "needs_attention": [],
                "strongest_subject": "Maths",
                "weakest_subject": None,
                "total_sessions": 10,
                "total_questions": 100,
                "overall_accuracy": 90,
                "learning_velocity": "fast",
                "last_updated_at": None,
            }
        ]
        gen = ClassReportGenerator(supabase_client=sb_with_mastery)
        result = gen.generate_class_report("cls-1", "teacher-1")
        aryan = next(c for c in result["report_data"]["children"] if c["name"] == "Aryan")
        assert "(Class 1)" not in aryan["report_text"], (
            f"Class suffix not stripped: {aryan['report_text']!r}"
        )
        assert "_" not in aryan["report_text"]


# ─────────────────────────────────────────────────────────────────────────────
# Test 3 — tokens are unique
# ─────────────────────────────────────────────────────────────────────────────

class TestUniqueTokens:
    def test_two_calls_produce_different_tokens(self):
        gen = ClassReportGenerator(supabase_client=_make_sb())
        r1 = gen.generate_class_report("cls-1", "teacher-1")
        r2 = gen.generate_class_report("cls-1", "teacher-1")
        assert r1["token"] != r2["token"], (
            f"Tokens must differ; both were {r1['token']!r}"
        )

    def test_token_is_non_empty_url_safe_string(self):
        gen = ClassReportGenerator(supabase_client=_make_sb())
        result = gen.generate_class_report("cls-1", "teacher-1")
        token = result["token"]
        assert isinstance(token, str)
        assert len(token) >= 16
        # secrets.token_urlsafe uses base64url — only [A-Za-z0-9_-]
        assert re.fullmatch(r"[A-Za-z0-9_\-]+", token), (
            f"Token contains non-URL-safe characters: {token!r}"
        )

    def test_ten_tokens_are_all_unique(self):
        gen = ClassReportGenerator(supabase_client=_make_sb())
        tokens = [gen.generate_class_report("cls-1", "teacher-1")["token"] for _ in range(10)]
        assert len(set(tokens)) == 10, "Expected all 10 tokens to be unique"


# ─────────────────────────────────────────────────────────────────────────────
# Test 4 — GET /api/reports/{expired_token} returns 410
# ─────────────────────────────────────────────────────────────────────────────

class TestExpiredTokenEndpoint:
    """Uses FastAPI TestClient and monkeypatches the module-level supabase client."""

    def _make_reports_client(self, monkeypatch, table_rows: list):
        """Build a TestClient for the reports router with a mocked supabase."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api import reports as reports_mod

        mock_sb = _FakeSupabase({"class_reports": table_rows})
        monkeypatch.setattr(reports_mod, "supabase", mock_sb)

        app = FastAPI()
        app.include_router(reports_mod.router)
        return TestClient(app, raise_server_exceptions=False)

    def test_expired_token_returns_410(self, monkeypatch):
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        expired_row = {
            "report_data": {"class_name": "Test", "children": []},
            "expires_at": past,
            "view_count": 0,
        }
        client = self._make_reports_client(monkeypatch, [expired_row])
        resp = client.get("/api/reports/some-expired-token")
        assert resp.status_code == 410, (
            f"Expected 410 Gone for expired token, got {resp.status_code}: {resp.text}"
        )

    def test_missing_token_returns_404(self, monkeypatch):
        client = self._make_reports_client(monkeypatch, [])  # empty table
        resp = client.get("/api/reports/nonexistent-token")
        assert resp.status_code == 404

    def test_valid_unexpired_token_returns_200(self, monkeypatch):
        future = (datetime.now(timezone.utc) + timedelta(days=6)).isoformat()
        valid_row = {
            "report_data": {"class_name": "Live Class", "children": []},
            "expires_at": future,
            "view_count": 0,
        }
        client = self._make_reports_client(monkeypatch, [valid_row])
        resp = client.get("/api/reports/valid-token-abc")
        assert resp.status_code == 200
        body = resp.json()
        assert body["class_name"] == "Live Class"

    def test_expiry_boundary_one_second_past_is_410(self, monkeypatch):
        just_past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        expired_row = {
            "report_data": {"class_name": "Edge", "children": []},
            "expires_at": just_past,
            "view_count": 0,
        }
        client = self._make_reports_client(monkeypatch, [expired_row])
        resp = client.get("/api/reports/edge-token")
        assert resp.status_code == 410
