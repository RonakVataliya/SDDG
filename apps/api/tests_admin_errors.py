"""Admin Errors page (FR25d): errors are recorded from the API's error handler, failed jobs and failed or rate-limited
AI calls, and GET /admin/errors lists them (newest first, filter by type and severity, administrators only).

Runs against the Postgres in DATABASE_URL, which may already hold errors, so counts are checked as changes from before
the test made its own. The error text of a job and of an exception carries a secret that must never be served.
Throwaway users and projects, deleted at the end. Run: python tests_admin_errors.py
"""
import json
import os
import uuid

import psycopg
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()
os.environ['DEV_AUTH_BYPASS'] = 'true'
os.environ.setdefault('DATA_ENCRYPTION_KEY', Fernet.generate_key().decode())

from fastapi.testclient import TestClient  # noqa: E402
from core import db  # noqa: E402
from core.auth import User, get_current_user  # noqa: E402
from main import app  # noqa: E402

API = '/api/v1'
TAG = uuid.uuid4().hex[:8]
ADMIN, OTHER = f'err{TAG}-admin@example.com', f'err{TAG}-other@example.com'
ADMIN_ID, OTHER_ID = f'dev:{ADMIN}', f'dev:{OTHER}'
SECRET = f'Okapi{uuid.uuid4().hex}'  # requirement text can end up in an exception message or a job's error
BOOM = f'/_boom_{TAG}/{{item}}'


@app.get(BOOM)
def boom(item: str):
    raise RuntimeError(SECRET)


def sql(query, *args):
    with psycopg.connect(os.environ['DATABASE_URL'], prepare_threshold=None) as c:
        return c.execute(query, args).fetchall() if query.startswith('SELECT') else c.execute(query, args)


def get(client, **params):
    app.dependency_overrides[get_current_user] = lambda: User(ADMIN_ID, ADMIN, True)
    try:
        r = client.get(f'{API}/admin/errors', params=params)
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    return r


def check(client):
    db.get_user(ADMIN, ADMIN_ID)
    db.get_user(OTHER, OTHER_ID)
    nobody = {'Authorization': f'Bearer mock-token:{OTHER}'}
    assert client.get(f'{API}/admin/errors', headers=nobody).status_code == 403

    base = get(client).json()
    assert base['page'] == 1 and base['page_size'] == 25
    count = {k: get(client, **q).json()['total'] for k, q in (
        ('api', {'type': 'api'}), ('job', {'type': 'job'}), ('ai', {'type': 'ai'}), ('rate_limit', {'type': 'rate_limit'}),
        ('error', {'severity': 'error'}), ('warning', {'severity': 'warning'}))}

    # 1. A crash in a route: recorded by the API's error handler, the caller still gets a plain 500.
    crash = TestClient(app, raise_server_exceptions=False).get(f'/_boom_{TAG}/{SECRET}')
    assert crash.status_code == 500 and SECRET not in crash.text, crash.text
    # 2. A failed job, 3. a failed AI call and 4. a rate-limited one (which retried, so only a warning).
    pid = db.create_project(ADMIN_ID, 'Errors project')['id']
    job = db.create_job(pid, 'generation', 3, 'x')
    db.update_job(job['id'], status='failed', error=SECRET)
    db.add_llm_calls(job['id'], pid, [
        {'node': 'extract', 'provider': 'groq', 'duration_ms': 4000, 'attempts': 3, 'rate_limited': 2, 'status': 'ok'},
        {'node': 'render', 'provider': 'gemini', 'duration_ms': 900, 'attempts': 1, 'rate_limited': 0, 'status': 'error'},
        {'node': 'extract', 'provider': 'groq', 'duration_ms': 100, 'attempts': 1, 'rate_limited': 0, 'status': 'ok'}], False)

    r = get(client)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['total'] == base['total'] + 4, body['total']
    mine = {(e['type'], e['severity'], e['message']) for e in body['errors']}
    for want in [('api', 'error', f'RuntimeError in GET {BOOM}'),
                 ('job', 'error', 'generation job failed'),
                 ('ai', 'error', 'gemini render failed, tried 1 time(s)'),
                 ('rate_limit', 'warning', 'groq extract hit a rate limit, tried 3 time(s)')]:
        assert want in mine, (want, mine)
    assert all(set(e) == {'id', 'type', 'severity', 'message', 'project_id', 'at'} for e in body['errors'])
    assert [e['at'] for e in body['errors']] == sorted((e['at'] for e in body['errors']), reverse=True)  # newest first
    assert SECRET not in json.dumps(body) and SECRET not in json.dumps(get(client, type='job').json())
    assert sql('SELECT count(*) FROM errors WHERE message LIKE %s', f'%{SECRET}%')[0][0] == 0  # not even stored

    # Filters: by type, by severity, and both.
    for key, q in (('api', {'type': 'api'}), ('job', {'type': 'job'}), ('ai', {'type': 'ai'}), ('rate_limit', {'type': 'rate_limit'}),
                   ('error', {'severity': 'error'}), ('warning', {'severity': 'warning'})):
        f = get(client, **q).json()
        assert f['total'] == count[key] + (3 if key == 'error' else 1), (key, f['total'])
        assert all(all(e[k] == v for k, v in q.items()) for e in f['errors'])
    both = get(client, type='rate_limit', severity='error').json()
    assert both['total'] == 0 and both['errors'] == []
    # A job error row links to its project; paging past the end is empty, not an error.
    assert get(client, type='job').json()['errors'][0]['project_id'] == pid
    assert get(client, page=10_000).json()['errors'] == []
    assert get(client, type='nonsense').status_code == 422 and get(client, page=0).status_code == 422


def main():
    db.init_db()
    try:
        with TestClient(app) as client:
            check(client)
        print('admin errors test passed')
    finally:
        sql('DELETE FROM errors WHERE message LIKE %s OR project_id IN (SELECT id FROM projects WHERE owner_id = ANY(%s))',
            f'%_boom_{TAG}%', [ADMIN_ID, OTHER_ID])
        sql('DELETE FROM projects WHERE owner_id = ANY(%s)', [ADMIN_ID, OTHER_ID])
        sql('DELETE FROM users WHERE id = ANY(%s)', [ADMIN_ID, OTHER_ID])


if __name__ == '__main__':
    main()
