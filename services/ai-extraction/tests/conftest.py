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
