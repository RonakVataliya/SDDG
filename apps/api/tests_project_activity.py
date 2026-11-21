"""Activity log tab (FR22): GET /projects/{id}/activity. Owners and System Administrators only; newest first; filter by
what happened (members, requirements, diagrams, comments) and by person; rows carry IDs and small values, never text.

Runs against the Postgres in DATABASE_URL, no AI calls. Throwaway users and project, deleted at the end.
Run: python tests_project_activity.py
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
from main import app  # noqa: E402

API = '/api/v1'
TAG = uuid.uuid4().hex[:8]
EMAILS = {n: f'log-{n}-{TAG}@example.com' for n in ('ronak', 'priya', 'karan', 'stranger', 'admin', 'meera')}
IDS = {n: f'dev:{e}' for n, e in EMAILS.items()}


def h(name):
    return {'Authorization': f'Bearer mock-token:{EMAILS[name]}'}


def sql(query, *args):
    with psycopg.connect(os.environ['DATABASE_URL'], prepare_threshold=None) as c:
        return c.execute(query, args).fetchall() if query.startswith('SELECT') else c.execute(query, args)


def get(client, pid, as_name='ronak', **params):
    return client.get(f'{API}/projects/{pid}/activity', headers=h(as_name), params=params)


def check(client):
    pid = db.create_project(IDS['ronak'], 'Activity tab project')['id']
    for name, role in (('priya', 'editor'), ('karan', 'viewer')):
        sql('INSERT INTO project_members(project_id, user_id, role) VALUES (%s, %s, %s)', pid, IDS[name], role)

    # Written the way the other stories write them: an invitation through the API, the rest through log_event.
    inv = client.post(f'{API}/projects/{pid}/invitations', headers=h('ronak'), json={'email': EMAILS['meera'], 'role': 'editor'})
    assert inv.status_code == 201, inv.text
    db.log_event(pid, IDS['ronak'], 'role.changed', IDS['karan'], {'from': 'viewer', 'to': 'editor'})
    db.log_event(pid, IDS['priya'], 'statement.edited', 'R-004 - rev 3')
    db.log_event(pid, IDS['priya'], 'comment.created', 'R-006')
    db.log_event(pid, IDS['ronak'], 'diagram.regenerated', 'dg_1', {'reason': 'requirement_change'})
    db.log_event(None, IDS['ronak'], 'user.deactivated', IDS['karan'])  # system-wide: never in a project's log

    # Who may read it: Owners and administrators. Editors and Viewers 403, strangers 404.
    assert get(client, pid, 'priya').status_code == 403 and get(client, pid, 'karan').status_code == 403
    assert get(client, pid, 'stranger').status_code == 404
    assert get(client, pid, 'admin').status_code == 404  # not a member and not (yet) an administrator
    sql('UPDATE users SET is_admin = true WHERE id = %s', IDS['admin'])  # an administrator counts as Owner on any project
    assert get(client, pid, 'admin').status_code == 200

    body = get(client, pid).json()
    assert body['total'] == 5 and body['page'] == 1 and body['page_size'] == 25, body
    ev = body['events']
    assert [e['action'] for e in ev] == ['diagram.regenerated', 'comment.created', 'statement.edited', 'role.changed', 'member.invited']
    assert [e['group'] for e in ev] == ['diagrams', 'comments', 'requirements', 'members', 'members']
    assert all(set(e) == {'id', 'action', 'group', 'actor_id', 'actor_email', 'subject_email', 'target', 'detail', 'at'} for e in ev)
    assert ev[0]['actor_email'] == EMAILS['ronak'] and ev[0]['detail'] == {'reason': 'requirement_change'}
    assert ev[2]['target'] == 'R-004 - rev 3' and ev[2]['actor_email'] == EMAILS['priya']
    assert ev[3]['subject_email'] == EMAILS['karan'] and ev[3]['detail'] == {'from': 'viewer', 'to': 'editor'}
    assert ev[4]['subject_email'] == EMAILS['meera'] and ev[4]['detail']['role'] == 'editor'  # found from the invitation id
    assert {a['email'] for a in body['actors']} == {EMAILS['ronak'], EMAILS['priya']}

    # Filters by what happened, and by person.
    for group, actions in (('members', {'role.changed', 'member.invited'}), ('requirements', {'statement.edited'}),
                           ('diagrams', {'diagram.regenerated'}), ('comments', {'comment.created'})):
        r = get(client, pid, group=group).json()
        assert {e['action'] for e in r['events']} == actions and r['total'] == len(r['events']), (group, r)
    assert get(client, pid, group='all').json()['total'] == 5
    by_priya = get(client, pid, actor=IDS['priya']).json()
    assert by_priya['total'] == 2 and {e['actor_id'] for e in by_priya['events']} == {IDS['priya']}
    both = get(client, pid, group='comments', actor=IDS['ronak']).json()
    assert both['total'] == 0 and both['events'] == []

    # Paging, and a bad filter.
    for i in range(25):
        db.log_event(pid, IDS['priya'], 'statement.edited', f'R-{i:03d}')
    assert len(get(client, pid).json()['events']) == 25 and get(client, pid).json()['total'] == 30
    assert len(get(client, pid, page=2).json()['events']) == 5
    assert get(client, pid, page=3).json()['events'] == []
    assert get(client, pid, group='nonsense').status_code == 422 and get(client, pid, page=0).status_code == 422
    # The log never holds requirement text: log_event refuses a long value.
    db.log_event(pid, IDS['priya'], 'statement.edited', 'R-999', {'text': 'x' * 101})
    assert get(client, pid).json()['total'] == 30
    assert 'R-999' not in json.dumps(get(client, pid, page=1).json()) and 'R-999' not in json.dumps(get(client, pid, page=2).json())


def main():
    db.init_db()
    for n in ('ronak', 'priya', 'karan', 'stranger', 'admin'):
        db.get_user(EMAILS[n], IDS[n])
    try:
        with TestClient(app) as client:
            check(client)
        print('project activity test passed')
    finally:
        sql('DELETE FROM activity_log WHERE actor_id = ANY(%s)', list(IDS.values()))
        sql('DELETE FROM projects WHERE owner_id = ANY(%s)', list(IDS.values()))
        sql('DELETE FROM users WHERE id = ANY(%s)', list(IDS.values()))


if __name__ == '__main__':
    main()
