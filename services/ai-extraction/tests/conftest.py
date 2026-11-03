"""
Shared pytest fixtures.

`live_kroki` lets a test render through a real Kroki (default
http://localhost:8080, i.e. `docker compose -f infra/kroki-compose.yml up -d`)
and skips cleanly when none is reachable, so CI without Docker still passes.
"""
import pytest
import requests

from app.config import get_settings


@pytest.fixture(scope="session")
def live_kroki() -> str:
    url = get_settings().KROKI_BASE_URL
    try:
        reachable = requests.get(f"{url}/health", timeout=2).status_code == 200
    except requests.RequestException:
        reachable = False
    if not reachable:
        pytest.skip(f"Kroki is not reachable at {url}")
    return url


@pytest.fixture(autouse=True)
def _skip_internal_key():
    """Endpoint tests exercise the routes, not the caller check; tests/test_internal_auth.py covers that."""
    from app.internal_auth import require_internal_key
    from app.main import app

    app.dependency_overrides[require_internal_key] = lambda: None
    yield
    app.dependency_overrides.pop(require_internal_key, None)
