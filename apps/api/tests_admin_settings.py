"""Admin Settings page: GET /admin/settings is read-only server configuration for administrators, and never a secret.

The AI service is faked (core.admin_db.httpx.get), so no AI service has to run. Run: python tests_admin_settings.py
"""
import json
import os
import uuid

import httpx
import psycopg
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()
os.environ['DEV_AUTH_BYPASS'] = 'true'
os.environ.setdefault('DATA_ENCRYPTION_KEY', Fernet.generate_key().decode())

from fastapi.testclient import TestClient  # noqa: E402
from core import admin_db, db  # noqa: E402
from core.auth import User, get_current_user  # noqa: E402
from main import app  # noqa: E402

API = '/api/v1'
TAG = uuid.uuid4().hex[:8]
ADMIN, OTHER = f'set{TAG}-admin@example.com', f'set{TAG}-other@example.com'
ADMIN_ID, OTHER_ID = f'dev:{ADMIN}', f'dev:{OTHER}'
SECRET = f'gsk_{uuid.uuid4().hex}'  # an API key must never reach the browser, even if the AI service sent one
SETTING_ENV = ('SESSION_TIMEOUT_HOURS', 'FAILED_LOGINS_BEFORE_LOCK', 'LOGIN_LOCK_MINUTES')


class FakeResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {'failover_wait_seconds': 20, 'providers': [
            {'provider': 'groq', 'model': 'openai/gpt-oss-120b', 'available': True, 'hard_down': False, 'api_key': SECRET},
            {'provider': 'gemini', 'model': 'gemini-3.5-flash', 'available': False, 'hard_down': False}]}


def fetch(client):
    app.dependency_overrides[get_current_user] = lambda: User(ADMIN_ID, ADMIN, True)
    try:
        return client.get(f'{API}/admin/settings')
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def check(client):
    db.get_user(OTHER, OTHER_ID)
    assert client.get(f'{API}/admin/settings', headers={'Authorization': f'Bearer mock-token:{OTHER}'}).status_code == 403

    real_get = httpx.get
    try:
        # The AI service answers: providers in its order, and whether any key is set.
        admin_db.httpx.get = lambda *a, **k: FakeResponse()
        for name in SETTING_ENV:
            os.environ.pop(name, None)
        r = fetch(client)
        assert r.status_code == 200, r.text
        s = r.json()
        assert s['ai'] == {'reachable': True, 'job_deadline_seconds': 600, 'providers': [
            {'name': 'groq', 'model': 'openai/gpt-oss-120b', 'available': True},
            {'name': 'gemini', 'model': 'gemini-3.5-flash', 'available': False}]}, s['ai']
        assert s['ai_key_set'] is True
        assert s['storage_limit_bytes'] == 500 * 1024 * 1024 and s['invitation_expiry_days'] == 7
        assert (s['session_timeout_hours'], s['failed_logins_before_lock'], s['lock_minutes']) == (None, None, None)
        assert SECRET not in r.text

        # Values Supabase Auth owns show only when someone declared them.
        os.environ.update(SESSION_TIMEOUT_HOURS='24', FAILED_LOGINS_BEFORE_LOCK='5', LOGIN_LOCK_MINUTES='15')
        s = fetch(client).json()
        assert (s['session_timeout_hours'], s['failed_logins_before_lock'], s['lock_minutes']) == (24, 5, 15)
        os.environ['SESSION_TIMEOUT_HOURS'] = 'soon'  # not a number: shown as not declared, not a crash
        assert fetch(client).json()['session_timeout_hours'] is None

        # The AI service is down: everything else still shows, and the key is unknown, not "not set".
        def down(*a, **k):
            raise httpx.ConnectError('down')
        admin_db.httpx.get = down
        s = fetch(client).json()
        assert s['ai'] == {'reachable': False, 'providers': [], 'job_deadline_seconds': 600} and s['ai_key_set'] is None
        assert s['storage_limit_bytes'] == 500 * 1024 * 1024
    finally:
        admin_db.httpx.get = real_get
        for name in SETTING_ENV:
            os.environ.pop(name, None)


def main():
    db.init_db()
    try:
        with TestClient(app) as client:
            check(client)
        print('admin settings test passed')
    finally:
        with psycopg.connect(os.environ['DATABASE_URL'], prepare_threshold=None) as c:
            c.execute('DELETE FROM users WHERE id = ANY(%s)', [[ADMIN_ID, OTHER_ID]])


if __name__ == '__main__':
    main()
