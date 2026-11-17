"""pytest entry point for the API test scripts (CI and local): python -m pytest -q

Each tests_*.py script keeps its own logic and still runs alone (python tests_access.py). Here each one runs in a
fresh process: the scripts patch module globals (the fake AI client, shared fixtures) and FastAPI's lifespan closes
the db pool, which cannot be reopened in the same process. The database in DATABASE_URL is migrated first.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from core.migrate import migrate, pending_files

HERE = Path(__file__).resolve().parent
SCRIPTS = sorted(p.name for p in HERE.glob("tests_*.py"))
ENV = {
    "DEV_AUTH_BYPASS": "true",
    "DATA_ENCRYPTION_KEY": os.environ.get("DATA_ENCRYPTION_KEY") or Fernet.generate_key().decode(),
    "AI_SERVICE_URL": "http://ai.invalid",
    "KROKI_URL": "http://kroki.invalid",
    "INTERNAL_API_KEY": "test-internal-key",
    "SUPABASE_URL": "",
}


@pytest.fixture(scope="session")
def database():
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set (the API tests need a Postgres database)")
    migrate(url)
    return url


@pytest.mark.parametrize("script", SCRIPTS)
def test_script(script, database):
    env = {**os.environ, **ENV, "DATABASE_URL": database}
    r = subprocess.run([sys.executable, script], cwd=HERE, env=env, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, f"{script} failed:\n{r.stdout[-4000:]}\n{r.stderr[-6000:]}"


def test_migrations_are_idempotent_and_numbered(database):
    assert migrate(database) == []  # already applied by the fixture: a second run does nothing
    numbers = [f.name[:4] for f in pending_files()]
    assert numbers == [f"{i:04d}" for i in range(1, len(numbers) + 1)], numbers  # no gaps, no duplicates
