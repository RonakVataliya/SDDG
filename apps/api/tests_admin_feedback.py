"""Admin Feedback page (FR27c): GET /admin/feedback lists the issue reports of every project, newest first, 25 per page,
optionally only open or resolved ones, and POST /admin/feedback/{report_id}/resolve closes one. Administrators only.
A plain comment (not sent as an issue report) never shows and cannot be closed here. "On" is the requirement's ref, the
diagram version or "Project export", never the requirement's text, and the activity log never holds a report's text.

Runs against the Postgres in DATABASE_URL, which may already hold reports, so counts are checked as changes from before
the test made its own. Throwaway users and projects, deleted at the end. Run: python tests_admin_feedback.py
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
from core.crypto import encrypt  # noqa: E402
from main import app  # noqa: E402

API = '/api/v1'
TAG = uuid.uuid4().hex[:8]
ADMIN, OWNER = f'fb{TAG}-admin@example.com', f'fb{TAG}-owner@example.com'
ADMIN_ID, OWNER_ID = f'dev:{ADMIN}', f'dev:{OWNER}'
SECRET = f'Okapi{uuid.uuid4().hex}'  # a report's text must never reach the activity log
owner = {'Authorization': f'Bearer mock-token:{OWNER}'}


def sql(query, *args):
    with psycopg.connect(os.environ['DATABASE_URL'], prepare_threshold=None) as c:
        return c.execute(query, args).fetchall() if query.lstrip().startswith('SELECT') else c.execute(query, args)


def as_admin(client, method, url, **kw):
    app.dependency_overrides[get_current_user] = lambda: User(ADMIN_ID, ADMIN, True)
    try:
        return client.request(method, f'{API}{url}', **kw)
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def listing(client, **params):
    r = as_admin(client, 'GET', '/admin/feedback', params=params)
    assert r.status_code == 200, r.text
    return r.json()


def comment(client, pid, target_type, target_id, body, report):
    r = client.post(f'{API}/projects/{pid}/comments', headers=owner,
                    json={'target_type': target_type, 'target_id': target_id, 'body': body, 'is_issue_report': report})
    assert r.status_code == 201, r.text
    return r.json()['id']


def check(client):
    # Not an administrator: refused, whatever the route.
    assert client.get(f'{API}/admin/feedback', headers=owner).status_code == 403
    assert client.post(f'{API}/admin/feedback/cm_x/resolve', headers=owner).status_code == 403

    before = {k: listing(client, **q)['total'] for k, q in (('all', {}), ('open', {'status': 'open'}),
                                                              ('resolved', {'status': 'resolved'}))}
    pid = client.post(f'{API}/projects', headers=owner, json={'name': 'Feedback project'}).json()['id']
    st = client.post(f'{API}/projects/{pid}/statements', headers=owner, json={'text': 'Patients book visits.'}).json()
    did = f'dg_{uuid.uuid4().hex}'
    sql('INSERT INTO diagrams(id, project_id, type, title, created_at, svg, elements, statement_ids) '
        'VALUES (%s, %s, %s, %s, now(), %s, %s, %s)', did, pid, 'use_case', encrypt('Clinic'), encrypt('<svg/>'),
        encrypt('[]'), '[]')
    plain = comment(client, pid, 'statement', st['id'], 'Just a note.', False)
    on_req = comment(client, pid, 'statement', st['id'], f'R-001 is drawn twice. {SECRET}', True)
    on_diagram = comment(client, pid, 'diagram', did, 'The actor name is cut off.', True)
    on_project = comment(client, pid, 'project', pid, 'The ZIP export is empty.', True)

    body = listing(client)
    assert body['total'] == before['all'] + 3 and body['page'] == 1 and body['page_size'] == 25, body['total']
    mine = {r['id']: r for r in body['reports'] if r['project_id'] == pid}
    assert set(mine) == {on_req, on_diagram, on_project}, mine  # the plain comment never shows
    assert mine[on_req]['on'] == st['ref'] and mine[on_diagram]['on'] == 'Use Case diagram v1', mine
    assert mine[on_project]['on'] == 'Project export', mine
    assert all(r['project_name'] == 'Feedback project' and r['from'] == OWNER and r['status'] == 'open'
               for r in mine.values()), mine
    assert mine[on_req]['report'] == f'R-001 is drawn twice. {SECRET}'  # the text the member chose to send
    assert 'Patients book visits.' not in json.dumps(body)  # never the requirement's own text
    ats = [r['at'] for r in body['reports']]
    assert ats == sorted(ats, reverse=True)  # newest first

    # Close one: it moves from open to resolved, once.
    r = as_admin(client, 'POST', f'/admin/feedback/{on_req}/resolve')
    assert r.status_code == 200 and r.json()['status'] == 'resolved', r.text
    assert r.json()['resolved_by'] == f'Fb{TAG}-admin' and r.json()['resolved_at'], r.json()
    again = as_admin(client, 'POST', f'/admin/feedback/{on_req}/resolve').json()
    assert again['resolved_at'] == r.json()['resolved_at']
    assert listing(client, status='open')['total'] == before['open'] + 2
    resolved = listing(client, status='resolved')
    assert resolved['total'] == before['resolved'] + 1 and all(x['status'] == 'resolved' for x in resolved['reports'])
    assert on_req in {x['id'] for x in resolved['reports']}

    # A plain comment or an unknown id is not a report.
    assert as_admin(client, 'POST', f'/admin/feedback/{plain}/resolve').status_code == 404
    assert as_admin(client, 'POST', '/admin/feedback/cm_missing/resolve').status_code == 404
    assert sql('SELECT status FROM comments WHERE id=%s', plain)[0][0] == 'open'

    # The project's log: one comment.resolved by the admin, by ref only.
    rows = sql('SELECT actor_id, action, target, detail FROM activity_log WHERE project_id=%s', pid)
    assert [(a, act, t) for a, act, t, _ in rows if act == 'comment.resolved'] == [(ADMIN_ID, 'comment.resolved', st['ref'])], rows
    assert not any(SECRET in json.dumps(row, default=str) for row in rows), rows

    # Paging past the end is empty; a wrong filter is refused.
    assert listing(client, page=10_000)['reports'] == []
    assert as_admin(client, 'GET', '/admin/feedback', params={'status': 'nonsense'}).status_code == 422
    assert as_admin(client, 'GET', '/admin/feedback', params={'page': 0}).status_code == 422


def main():
    try:
        with TestClient(app) as client:
            check(client)
        print('admin feedback test passed')
    finally:
        sql('DELETE FROM projects WHERE owner_id = ANY(%s)', [ADMIN_ID, OWNER_ID])
        sql('DELETE FROM users WHERE id = ANY(%s)', [ADMIN_ID, OWNER_ID])


if __name__ == '__main__':
    main()
