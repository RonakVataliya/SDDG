"""Members page API (FR24c): list members, change a role, remove someone, leave, and always keep an Owner.

Runs against the Postgres in DATABASE_URL (schema.sql applied, including migration 0009) with no AI or Kroki calls.
Uses throwaway users and deletes what it creates. Run: python tests_members.py
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
from main import app  # noqa: E402

API = '/api/v1'
EMAILS = {name: f'mem-{name}-{uuid.uuid4().hex[:8]}@example.com' for name in ('ronak', 'priya', 'karan', 'stranger')}
IDS = {name: f'dev:{email}' for name, email in EMAILS.items()}


def h(name):
    return {'Authorization': f'Bearer mock-token:{EMAILS[name]}'}


def sql(query, *args):
    with psycopg.connect(os.environ['DATABASE_URL'], prepare_threshold=None) as c:
        return c.execute(query, args).fetchall() if query.startswith('SELECT') else c.execute(query, args)


def add(pid, name, role):
    sql('INSERT INTO project_members(project_id, user_id, role) VALUES (%s, %s, %s)', pid, IDS[name], role)


def roles(client, pid, as_name='ronak'):
    r = client.get(f'{API}/projects/{pid}/members', headers=h(as_name))
    assert r.status_code == 200, r.text
    return {m['email']: m['role'] for m in r.json()}


def check_list(client, pid):
    members = client.get(f'{API}/projects/{pid}/members', headers=h('karan')).json()  # a Viewer can see the list
    assert [m['email'] for m in members] == [EMAILS['ronak'], EMAILS['priya'], EMAILS['karan']], members
    me = next(m for m in members if m['email'] == EMAILS['karan'])
    assert me['is_you'] and not me['is_creator'] and me['role'] == 'viewer' and me['joined_at'], me
    assert next(m for m in members if m['email'] == EMAILS['ronak'])['is_creator']
    assert client.get(f'{API}/projects/{pid}/members', headers=h('stranger')).status_code == 404


def check_change_role(client, pid):
    url = f'{API}/projects/{pid}/members/{IDS["karan"]}'
    assert client.patch(url, headers=h('priya'), json={'role': 'editor'}).status_code == 403  # Editors cannot
    assert client.patch(url, headers=h('karan'), json={'role': 'owner'}).status_code == 403  # nor promote themselves
    assert client.patch(url, headers=h('ronak'), json={'role': 'admin'}).status_code == 422
    r = client.patch(url, headers=h('ronak'), json={'role': 'editor'})
    assert r.status_code == 200, r.text
    assert {m['email']: m['role'] for m in r.json()}[EMAILS['karan']] == 'editor'
    # applies on Karan's very next request: an Editor may now edit, which needs editor
    assert client.get(f'{API}/projects/{pid}', headers=h('karan')).json()['role'] == 'editor'
    missing = client.patch(f'{API}/projects/{pid}/members/{IDS["stranger"]}', headers=h('ronak'), json={'role': 'viewer'})
    assert missing.status_code == 404


def check_last_owner(client, pid):
    me = f'{API}/projects/{pid}/members/{IDS["ronak"]}'
    r = client.patch(me, headers=h('ronak'), json={'role': 'editor'})
    assert r.status_code == 409 and 'at least one Owner' in r.json()['detail'], r.text
    r = client.delete(me, headers=h('ronak'))  # leaving as the only Owner
    assert r.status_code == 409 and 'only Owner' in r.json()['detail'], r.text
    assert roles(client, pid)[EMAILS['ronak']] == 'owner'
    # with a second Owner, the first can step down
    assert client.patch(f'{API}/projects/{pid}/members/{IDS["priya"]}', headers=h('ronak'),
                        json={'role': 'owner'}).status_code == 200
    assert client.patch(me, headers=h('ronak'), json={'role': 'editor'}).status_code == 200
    assert roles(client, pid, 'priya')[EMAILS['ronak']] == 'editor'
    assert client.patch(me, headers=h('priya'), json={'role': 'owner'}).status_code == 200  # back, for what follows


def check_remove_and_leave(client, pid):
    karan = f'{API}/projects/{pid}/members/{IDS["karan"]}'
    assert client.delete(karan, headers=h('karan')).status_code == 204  # Leave
    assert client.get(f'{API}/projects/{pid}', headers=h('karan')).status_code == 404  # gone at once
    add(pid, 'karan', 'viewer')
    assert client.delete(f'{API}/projects/{pid}/members/{IDS["priya"]}', headers=h('karan')).status_code == 403
    assert client.delete(karan, headers=h('ronak')).status_code == 204  # Remove
    assert EMAILS['karan'] not in roles(client, pid)
    assert client.delete(karan, headers=h('ronak')).status_code == 404  # already gone


def main():
    try:
        with TestClient(app) as client:
            r = client.post(f'{API}/projects', headers=h('ronak'), json={'name': 'Clinic booking'})
            assert r.status_code == 201, r.text
            pid = r.json()['id']
            add(pid, 'priya', 'editor')
            add(pid, 'karan', 'viewer')
            check_list(client, pid)
            check_change_role(client, pid)
            check_last_owner(client, pid)
            check_remove_and_leave(client, pid)
        print('members test passed')
    finally:
        sql('DELETE FROM projects WHERE owner_id = ANY(%s)', list(IDS.values()))


if __name__ == '__main__':
    main()
