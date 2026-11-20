"""Admin Usage page (FR25a-c, NFR1): GET /admin/usage.

Runs against the Postgres in DATABASE_URL. The database may already hold other data, so counts are checked as changes
from before the test seeded its own rows, and the percentiles are checked against an independent Python calculation
over the same rows. Throwaway users and projects, deleted at the end. Run: python tests_admin_usage.py
"""
import json
import math
import os
import uuid

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
ADMIN, OTHER = f'use{TAG}-admin@example.com', f'use{TAG}-other@example.com'
ADMIN_ID, OTHER_ID = f'dev:{ADMIN}', f'dev:{OTHER}'
SECRET = f'Okapi{uuid.uuid4().hex}'  # a job's error text can repeat requirement text: it must never be served
SIZE = 3_000_000
RUNS = [10, 20, 30, 40, 200]  # seconds: one is slower than the 120 s target


def sql(query, *args):
    with psycopg.connect(os.environ['DATABASE_URL'], prepare_threshold=None) as c:
        return c.execute(query, args).fetchall() if query.startswith('SELECT') else c.execute(query, args)


def percentile(values, p):  # the same linear interpolation as percentile_cont
    s = sorted(values)
    k = (len(s) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def seed_jobs(pid):
    for secs in RUNS:
        job = db.create_job(pid, 'generation', 3, 'x')
        sql("UPDATE jobs SET status = 'succeeded', started_at = now() - make_interval(secs => %s), finished_at = now() "
            "WHERE id = %s", secs, job['id'])
    failed = db.create_job(pid, 'generation', 3, 'x')
    sql("UPDATE jobs SET status = 'failed', started_at = now(), finished_at = now(), error = %s WHERE id = %s", SECRET, failed['id'])
    db.add_llm_calls(failed['id'], pid, [
        {'node': 'extract', 'provider': 'groq', 'duration_ms': 4000, 'attempts': 3, 'rate_limited': 2, 'status': 'ok'},
        {'node': 'render', 'provider': 'gemini', 'duration_ms': 900, 'attempts': 1, 'rate_limited': 0, 'status': 'error'}], False)


def check(client):
    before = admin_db.usage()
    db.get_user(ADMIN, ADMIN_ID)
    nobody = {'Authorization': f'Bearer mock-token:{OTHER}'}
    assert client.get(f'{API}/admin/usage', headers=nobody).status_code == 403

    db.get_user(OTHER, OTHER_ID)
    sql('UPDATE users SET last_seen_at = now() - interval \'3 hours\' WHERE id = %s', OTHER_ID)  # an account, not active now
    pid = db.create_project(ADMIN_ID, 'Usage project')['id']
    sql('UPDATE projects SET archived_at = now() WHERE id = %s', pid)
    sql("INSERT INTO documents(id, project_id, filename, storage_path, content_type, size_bytes, page_count, status, created_at, updated_at) "
        "VALUES (%s, %s, 'x.pdf', 'p/x.pdf', 'application/pdf', %s, 2, 'processed', now(), now())", db.uid('doc'), pid, SIZE)
    seed_jobs(pid)

    app.dependency_overrides[get_current_user] = lambda: User(ADMIN_ID, ADMIN, True)
    try:
        r = client.get(f'{API}/admin/usage')
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert r.status_code == 200, r.text
    u = r.json()

    # Tiles: accounts, who was seen in the last 15 minutes, projects (archived counted too), storage.
    assert (u['window_days'], u['active_window_minutes']) == (7, 15)
    assert u['accounts'] == before['accounts'] + 2 and u['active_users'] == before['active_users'] + 1, u
    assert u['projects'] == before['projects'] + 1 and u['archived_projects'] == before['archived_projects'] + 1
    assert u['storage_bytes'] == before['storage_bytes'] + SIZE and u['storage_limit_bytes'] == 500 * 1024 * 1024
    assert u['limits'] == {'max_document_bytes': 10 * 1024 * 1024, 'max_documents_per_project': 15, 'max_pages_per_project': 100}

    # NFR1: median and 95th percentile of the finished generation runs of the last 7 days, against 60 s and 120 s.
    secs = [float(r[0]) for r in sql("SELECT extract(epoch FROM finished_at - started_at) FROM jobs WHERE kind = 'generation' "
                                     "AND status = 'succeeded' AND started_at IS NOT NULL AND finished_at > now() - interval '7 days'")]
    g = u['generation']
    assert g['runs'] == before['generation']['runs'] + len(RUNS) == len(secs), (g, len(secs))
    assert math.isclose(g['median_seconds'], percentile(secs, 0.5), abs_tol=1e-3), g
    assert math.isclose(g['p95_seconds'], percentile(secs, 0.95), abs_tol=1e-3), g
    assert (g['median_target_seconds'], g['p95_target_seconds']) == (60, 120)
    assert g['median_ok'] == (g['median_seconds'] <= 60) and g['p95_ok'] == (g['p95_seconds'] <= 120)

    # Slow runs and recent errors: kind and counts only, never a job's error text.
    texts = {(e['type'], e['description']) for e in u['events']}
    assert ('slow', 'Generation took 200 s') in texts, texts
    assert ('error', 'generation job failed') in texts, texts
    assert ('rate_limit', 'groq extract hit a rate limit, tried 3 time(s)') in texts, texts
    assert ('error', 'gemini render failed, tried 1 time(s)') in texts, texts
    assert len(u['events']) <= 10 and all(e['at'] for e in u['events'])
    assert SECRET not in json.dumps(u)

    # The storage flag turns on at 80% of the limit.
    usual = admin_db.STORAGE_LIMIT_BYTES
    try:
        admin_db.STORAGE_LIMIT_BYTES = int(u['storage_bytes'] / 0.8)
        assert admin_db.usage()['storage_warning'] is True
        admin_db.STORAGE_LIMIT_BYTES = int(u['storage_bytes'] / 0.8) + 1_000_000
        assert admin_db.usage()['storage_warning'] is False
    finally:
        admin_db.STORAGE_LIMIT_BYTES = usual


def main():
    db.init_db()
    try:
        with TestClient(app) as client:
            check(client)
        print('admin usage test passed')
    finally:
        sql('DELETE FROM projects WHERE owner_id = ANY(%s)', [ADMIN_ID, OTHER_ID])  # cascades jobs, documents, llm_calls
        sql('DELETE FROM users WHERE id = ANY(%s)', [ADMIN_ID, OTHER_ID])


if __name__ == '__main__':
    main()
