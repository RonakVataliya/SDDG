"""The notifications bell: notify(), list, unread count, mark read.

Runs against the Postgres in DATABASE_URL with no AI or Kroki calls. Uses throwaway users and deletes what it
creates. Needs migration 0010 (apps/api/migrations or schema.sql). Run: python tests_notifications.py
"""
import os
import uuid

import psycopg
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()
os.environ['DEV_AUTH_BYPASS'] = 'true'
os.environ.setdefault('DATA_ENCRYPTION_KEY', Fernet.generate_key().decode())

from fastapi.testclient import TestClient  # noqa: E402
from core.notifications import notify, notify_project  # noqa: E402
from main import app  # noqa: E402

API = '/api/v1'
A, B = (f'bell-{uuid.uuid4().hex[:8]}@example.com' for _ in range(2))
A_ID, B_ID = f'dev:{A}', f'dev:{B}'
a = {'Authorization': f'Bearer mock-token:{A}'}
b = {'Authorization': f'Bearer mock-token:{B}'}


def sql(query, *args):
    with psycopg.connect(os.environ['DATABASE_URL'], prepare_threshold=None) as c:
        return c.execute(query, args).fetchall() if query.startswith('SELECT') else c.execute(query, args)


def check_bell(client):
    assert client.get(f'{API}/notifications', headers=a).json() == {'unread_count': 0, 'items': []}
    assert client.get(f'{API}/notifications').status_code in (401, 403)  # login required

    first = notify(A_ID, 'mention', {'comment_id': 'cm_1'})
    second = notify(A_ID, 'mention', {'comment_id': 'cm_2'})
    notify(B_ID, 'mention', {'comment_id': 'cm_3'})
    assert first['payload'] == {'comment_id': 'cm_1'} and first['read_at'] is None

    assert client.get(f'{API}/notifications/unread-count', headers=a).json() == {'count': 2}
    body = client.get(f'{API}/notifications', headers=a).json()
    assert body['unread_count'] == 2 and [n['id'] for n in body['items']] == [second['id'], first['id']]  # newest first
    assert body['items'][0]['type'] == 'mention' and body['items'][0]['project'] is None

    # Only the owner of a notification can mark it read; anyone else is told it does not exist.
    assert client.post(f'{API}/notifications/{first["id"]}/read', headers=b).status_code == 404
    assert client.get(f'{API}/notifications/unread-count', headers=a).json() == {'count': 2}
    assert client.post(f'{API}/notifications/{first["id"]}/read', headers=a).status_code == 204
    assert client.post(f'{API}/notifications/{first["id"]}/read', headers=a).status_code == 204  # idempotent
    assert client.post(f'{API}/notifications/nt_missing/read', headers=a).status_code == 404
    assert client.get(f'{API}/notifications/unread-count', headers=a).json() == {'count': 1}

    assert client.post(f'{API}/notifications/read-all', headers=a).status_code == 204
    assert client.get(f'{API}/notifications/unread-count', headers=a).json() == {'count': 0}
    assert client.get(f'{API}/notifications/unread-count', headers=b).json() == {'count': 1}  # B is untouched
    assert len(client.get(f'{API}/notifications', headers=a).json()['items']) == 2  # read ones stay listed


def check_project_wide(client):
    """Issue #36: a generation that finishes or fails tells every member of the project, once each."""
    pid = client.post(f'{API}/projects', headers=a, json={'name': 'Bell project'}).json()['id']
    sql('INSERT INTO project_members(project_id, user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING', pid, B_ID)
    notify_project(pid, 'generation_ready', {'job_id': 'job_1', 'diagram_id': 'dg_1'})

    for headers, who in ((a, 'A'), (b, 'B')):
        items = [n for n in client.get(f'{API}/notifications', headers=headers).json()['items']
                 if n['type'] == 'generation_ready']
        assert len(items) == 1, (who, items)
        assert items[0]['payload'] == {'project_id': pid, 'job_id': 'job_1', 'diagram_id': 'dg_1'}, items[0]
        assert items[0]['project']['name'] == 'Bell project', items[0]
    # Nobody outside the project hears about it.
    c = f'bell-{uuid.uuid4().hex[:8]}@example.com'
    assert client.get(f'{API}/notifications', headers={'Authorization': f'Bearer mock-token:{c}'}).json()['items'] == []


def main():
    try:
        with TestClient(app) as client:
            check_bell(client)
            check_project_wide(client)
        print('notifications test passed')
    finally:
        sql('DELETE FROM projects WHERE owner_id = ANY(%s)', [A_ID, B_ID])
        sql('DELETE FROM notifications WHERE user_id = ANY(%s)', [A_ID, B_ID])


if __name__ == '__main__':
    main()
