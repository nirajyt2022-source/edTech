import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from app.main import app
from app.core.config import get_settings

client = TestClient(app)

@pytest.fixture
def mock_supabase():
    mock = MagicMock()
    with patch("app.api.worksheets.supabase", mock), \
         patch("app.api.subscription.supabase", mock):
        yield mock

@pytest.fixture
def mock_openai():
    with patch("app.api.worksheets.client") as mock:
        yield mock

def test_generate_worksheet_unauthorized():
    response = client.post("/api/worksheets/generate", json={
        "board": "CBSE",
        "grade_level": "Class 3",
        "subject": "Maths",
        "topic": "Addition",
        "difficulty": "easy"
    })
    assert response.status_code == 401

def test_seed_syllabus_unauthorized():
    response = client.post("/api/cbse-syllabus/seed")
    assert response.status_code == 401

def test_upgrade_unauthorized(mock_supabase):
    # Mock valid auth
    mock_supabase.auth.get_user.return_value = MagicMock(user=MagicMock(id="user-123"))

    response = client.post("/api/subscription/upgrade", headers={"Authorization": "Bearer valid-token"})
    # It should fail because it requires admin secret when DEBUG is false (default)
    assert response.status_code == 403

def test_generate_worksheet_authorized_limit_reached(mock_supabase):
    # Mock auth
    mock_supabase.auth.get_user.return_value = MagicMock(user=MagicMock(id="user-123"))

    # Mock subscription limit reached
    mock_supabase.table().select().eq().execute.return_value = MagicMock(data=[{
        "tier": "free",
        "worksheets_generated_this_month": 3
    }])

    response = client.post(
        "/api/worksheets/generate",
        json={
            "board": "CBSE",
            "grade_level": "Class 3",
            "subject": "Maths",
            "topic": "Addition",
            "difficulty": "easy"
        },
        headers={"Authorization": "Bearer valid-token"}
    )
    assert response.status_code == 403
    assert "limit reached" in response.json()["detail"]
