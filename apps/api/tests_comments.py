"""Comments and issue reports (FR32, FR27a-b). Ronak owns the project, Priya is an Editor, Karan a Viewer, Sam owns
another project. Karan (a Viewer) can comment; he can resolve his own thread but not Priya's; Priya can resolve anyone's.
A target of another project is 404, an empty or too long comment and a mention of a non-member are 422. Issue reports:
Ronak sees all of them, Priya and Karan only their own, and a plain comment is never a report. The activity log names
the target (R-001, Use Case diagram v1, Project) and never holds a comment's text.

Runs against the Postgres in DATABASE_URL (schema.sql applied, then every migration). Throwaway users, deleted at the
end. Run: python tests_comments.py
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
from core.crypto import encrypt  # noqa: E402
from main import app  # noqa: E402

API = '/api/v1'
TAG = uuid.uuid4().hex[:8]
EMAILS = {name: f'{name}.{TAG}@example.com' for name in ('ronak', 'priya', 'karan', 'sam')}
IDS = {name: f'dev:{email}' for name, email in EMAILS.items()}
SECRET = f'Okapi{uuid.uuid4().hex}'  # a comment's text must never reach the activity log


def h(name):
    return {'Authorization': f'Bearer mock-token:{EMAILS[name]}'}


def sql(query, *args):
    with psycopg.connect(os.environ['DATABASE_URL'], prepare_threshold=None) as c:
        return c.execute(query, args).fetchall() if query.lstrip().startswith('SELECT') else c.execute(query, args)


def add_diagram(pid):
    """A diagram version written directly (no Kroki or AI needed to check who can comment on it)."""
    did = f'dg_{uuid.uuid4().hex}'
    sql('INSERT INTO diagrams(id, project_id, type, title, created_at, svg, elements, statement_ids) '
        'VALUES (%s, %s, %s, %s, now(), %s, %s, %s)', did, pid, 'use_case', encrypt('Clinic'), encrypt('<svg/>'),
        encrypt('[]'), '[]')
    return did


def post(client, who, pid, target_type, target_id, body='Looks right.', **extra):
    return client.post(f'{API}/projects/{pid}/comments', headers=h(who),
                       json={'target_type': target_type, 'target_id': target_id, 'body': body, **extra})


def check_posting(client, pid, st, did, other):
    # Any member, a Viewer too, comments on a requirement, a diagram version or the project.
    r = post(client, 'karan', pid, 'statement', st['id'], f'  Should this say weekdays only? {SECRET}  ')
    assert r.status_code == 201, r.text
    c = r.json()
    assert c['body'] == f'Should this say weekdays only? {SECRET}' and c['status'] == 'open', c  # trimmed
    assert c['author'] == {'id': IDS['karan'], 'email': EMAILS['karan']} and c['target_label'] == st['ref'], c
    assert c['is_issue_report'] is False and c['resolved_by'] is None, c
    assert post(client, 'priya', pid, 'diagram', did, 'The actor is missing.').json()['target_label'] == 'Use Case diagram v1'
    assert post(client, 'ronak', pid, 'project', pid, 'Ready for the client.').json()['target_label'] == 'Project'

    # A target of another project, or no such target, is not found; so is a project you are not in.
    assert post(client, 'ronak', pid, 'statement', other['statement']).status_code == 404
    assert post(client, 'ronak', pid, 'diagram', other['diagram']).status_code == 404
    assert post(client, 'ronak', pid, 'project', other['project']).status_code == 404
    assert post(client, 'ronak', pid, 'statement', 'st_missing').status_code == 404
    assert post(client, 'sam', pid, 'project', pid).status_code == 404

    # Empty, blank, too long, a mention of someone outside the project: 422, and nothing is saved.
    before = len(client.get(f'{API}/projects/{pid}/comments', headers=h('ronak')).json())
    for bad in ('', '   ', 'x' * 2001):
        assert post(client, 'priya', pid, 'project', pid, bad).status_code == 422, bad[:5]
    r = post(client, 'priya', pid, 'project', pid, 'Ask @Sam', mentions=[IDS['sam']])
    assert r.status_code == 422 and r.json()['detail'] == 'You can only mention members of this project.', r.text
    assert len(client.get(f'{API}/projects/{pid}/comments', headers=h('ronak')).json()) == before
    assert post(client, 'priya', pid, 'project', pid, 'x' * 2000).status_code == 201  # the limit itself is fine
    r = post(client, 'priya', pid, 'project', pid, 'Over to @Karan', mentions=[IDS['karan'], IDS['karan']])
    assert r.status_code == 201, r.text  # a member, mentioned twice, is fine
    return c


def check_listing(client, pid, st, did):
    url = f'{API}/projects/{pid}/comments'
    one_req = client.get(url, headers=h('karan'), params={'target_type': 'statement', 'target_id': st['id']}).json()
    assert [c['body'] for c in one_req] == [f'Should this say weekdays only? {SECRET}'], one_req
    on_diagrams = client.get(url, headers=h('karan'), params={'target_type': 'diagram'}).json()
    assert [c['target_id'] for c in on_diagrams] == [did], on_diagrams
    every = client.get(url, headers=h('priya')).json()
    assert [c['created_at'] for c in every] == sorted(c['created_at'] for c in every)  # oldest first
    assert client.get(url, headers=h('sam')).status_code == 404


def check_resolving(client, pid, karans, did):
    priyas = post(client, 'priya', pid, 'diagram', did, 'Rename the actor.').json()
    url = f'{API}/projects/{pid}/comments/{{}}/resolve'
    # A Viewer cannot resolve someone else's thread, only their own; an outsider is told it does not exist.
    assert client.post(url.format(priyas['id']), headers=h('karan')).status_code == 403
    assert client.post(url.format(priyas['id']), headers=h('sam')).status_code == 404
    r = client.post(url.format(karans['id']), headers=h('karan'))
    assert r.status_code == 200 and r.json()['status'] == 'resolved', r.text
    assert r.json()['resolved_by'] == f'Karan.{TAG}' and r.json()['resolved_at'], r.json()
    # An Editor resolves anyone's; resolving again changes nothing (and logs nothing twice).
    first = client.post(url.format(priyas['id']), headers=h('ronak')).json()
    again = client.post(url.format(priyas['id']), headers=h('priya')).json()
    assert first['resolved_by'] == again['resolved_by'] == f'Ronak.{TAG}', (first, again)
    assert first['resolved_at'] == again['resolved_at']
    assert client.post(url.format('cm_missing'), headers=h('ronak')).status_code == 404
    return priyas


def check_reports(client, pid, other_pid):
    for who, body in (('karan', 'The export cuts the actor names.'), ('priya', 'R-001 is drawn twice.')):
        r = post(client, who, pid, 'project', pid, body, is_issue_report=True)
        assert r.status_code == 201 and r.json()['is_issue_report'] is True, r.text
    url = f'{API}/projects/{pid}/reports'
    everyone = client.get(url, headers=h('ronak')).json()
    assert sorted(c['author']['id'] for c in everyone) == sorted([IDS['karan'], IDS['priya']]), everyone
    assert all(c['is_issue_report'] for c in everyone)  # a plain comment is never a report
    assert [c['author']['id'] for c in client.get(url, headers=h('priya')).json()] == [IDS['priya']]
    assert [c['author']['id'] for c in client.get(url, headers=h('karan')).json()] == [IDS['karan']]
    assert client.get(url, headers=h('sam')).status_code == 404
    # A comment of another project cannot be resolved through this one.
    theirs = post(client, 'sam', other_pid, 'project', other_pid, 'Mine.').json()
    assert client.post(f'{API}/projects/{pid}/comments/{theirs["id"]}/resolve', headers=h('ronak')).status_code == 404


def check_log(pid, st, karans, priyas):
    rows = sql('SELECT actor_id, action, target, detail FROM activity_log WHERE project_id=%s ORDER BY created_at', pid)
    events = [(a, act, t) for a, act, t, _ in rows if act.startswith('comment.')]
    assert (IDS['karan'], 'comment.created', st['ref']) in events, events
    assert (IDS['priya'], 'comment.created', 'Use Case diagram v1') in events, events
    assert (IDS['ronak'], 'comment.created', 'Project') in events, events
    assert (IDS['karan'], 'comment.resolved', st['ref']) in events, events
    resolved = [e for e in events if e[1] == 'comment.resolved' and e[2] == 'Use Case diagram v1']
    assert resolved == [(IDS['ronak'], 'comment.resolved', 'Use Case diagram v1')], resolved  # once, not twice
    assert not any(SECRET in json.dumps(row, default=str) for row in rows), rows
    stored = sql('SELECT body FROM comments WHERE id=%s', karans['id'])[0][0]
    assert SECRET not in stored  # encrypted at rest
    assert priyas['id'] != karans['id']


def main():
    try:
        with TestClient(app) as client:
            pid = client.post(f'{API}/projects', headers=h('ronak'), json={'name': 'Clinic booking'}).json()['id']
            for name, role in (('priya', 'editor'), ('karan', 'viewer')):
                sql('INSERT INTO project_members(project_id, user_id, role) VALUES (%s, %s, %s)', pid, IDS[name], role)
            st = client.post(f'{API}/projects/{pid}/statements', headers=h('ronak'),
                             json={'text': 'Patients book visits.'}).json()
            did = add_diagram(pid)
            other_pid = client.post(f'{API}/projects', headers=h('sam'), json={'name': 'Other'}).json()['id']
            other_st = client.post(f'{API}/projects/{other_pid}/statements', headers=h('sam'),
                                   json={'text': 'Something else.'}).json()
            other = {'project': other_pid, 'statement': other_st['id'], 'diagram': add_diagram(other_pid)}

            karans = check_posting(client, pid, st, did, other)
            check_listing(client, pid, st, did)
            priyas = check_resolving(client, pid, karans, did)
            check_reports(client, pid, other_pid)
            check_log(pid, st, karans, priyas)
        print('comments test passed')
    finally:
        sql('DELETE FROM projects WHERE owner_id = ANY(%s)', list(IDS.values()))


if __name__ == '__main__':
    main()
