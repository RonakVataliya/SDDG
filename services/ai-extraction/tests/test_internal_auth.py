"""Only a caller with the shared INTERNAL_API_KEY reaches the AI endpoints; /health stays open."""
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.internal_auth import require_internal_key
from app.main import app

URL = "/api/v1/dfd/generate"  # an invalid body gives 422 once the caller check passes


@pytest.fixture
def client(monkeypatch):
    app.dependency_overrides.pop(require_internal_key, None)  # undo conftest's skip
    monkeypatch.setattr(get_settings(), "INTERNAL_API_KEY", "s3cret")
    return TestClient(app)


def test_wrong_or_missing_key_is_rejected(client):
    assert client.post(URL, json={}).status_code == 401
    assert client.post(URL, json={}, headers={"X-Internal-Key": "guess"}).status_code == 401


def test_right_key_reaches_the_endpoint(client):
    assert client.post(URL, json={}, headers={"X-Internal-Key": "s3cret"}).status_code == 422


def test_unset_key_closes_every_endpoint(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "INTERNAL_API_KEY", "")
    assert client.post(URL, json={}, headers={"X-Internal-Key": ""}).status_code == 503


def test_health_needs_no_key(client):
    assert client.get("/api/v1/health").status_code == 200
