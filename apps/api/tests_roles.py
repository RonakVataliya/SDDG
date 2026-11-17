"""Roles (FR24e): require_role answers 404 to non-members, 403 to a member whose role is too low, and lets a System
Administrator act as owner. Also checks that the project response carries the caller's real role and that a role
change applies on the next request.

Runs against the Postgres in DATABASE_URL (schema.sql applied, including migrations 0005-0007) with no AI or Kroki
calls. Uses throwaway users and deletes what it creates. Run: python tests_roles.py
"""
import os
import uuid

import psycopg
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()
os.environ['DEV_AUTH_BYPASS'] = 'true'
os.environ.setdefault('DATA_ENCRYPTION_KEY', Fernet.generate_key().decode())

from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from core.auth import User  # noqa: E402
from routers.integrated import require_role  # noqa: E402
from main import app  # noqa: E402

API = '/api/v1'
EMAILS = {name: f'role-{name}-{uuid.uuid4().hex[:8]}@example.com'
          for name in ('owner', 'editor', 'viewer', 'admin', 'stranger')}
USERS = {name: User(f'dev:{email}', email) for name, email in EMAILS.items()}
IDS = [u.id for u in USERS.values()]


def headers(name):
    return {'Authorization': f'Bearer mock-token:{EMAILS[name]}'}


def sql(query, *args):
    with psycopg.connect(os.environ['DATABASE_URL'], prepare_threshold=None) as c:
        return c.execute(query, args).fetchall() if query.startswith('SELECT') else c.execute(query, args)


def outcome(project_id, name, min_role):
    """The caller's role if require_role lets them in, else the HTTP status it answered with."""
    try:
        return require_role(project_id, USERS[name], min_role)['role']
    except HTTPException as e:
        return e.status_code


def check_role_matrix(pid):
    expected = {  # who -> (needs viewer, needs editor, needs owner)
        'owner': ('owner', 'owner', 'owner'),
        'editor': ('editor', 'editor', 403),
        'viewer': ('viewer', 403, 403),
        'admin': ('owner', 'owner', 'owner'),  # System Administrator, not a member
        'stranger': (404, 404, 404),  # cannot tell the project exists
    }
    for name, results in expected.items():
        for min_role, want in zip(('viewer', 'editor', 'owner'), results):
            got = outcome(pid, name, min_role)
            assert got == want, f'{name} needing {min_role}: expected {want}, got {got}'
    assert outcome('pr_does_not_exist', 'owner', 'viewer') == 404
    assert outcome('pr_does_not_exist', 'admin', 'viewer') == 404
    try:
        require_role(pid, USERS['owner'], 'admin')
        raise AssertionError('an unknown role must be a programming error')
    except ValueError:
        pass


def check_role_in_responses(client, pid):
    listed = {p['id']: p for p in client.get(f'{API}/projects', headers=headers('viewer')).json()}
    assert listed[pid]['role'] == 'viewer', listed[pid]
    assert client.get(f'{API}/projects/{pid}', headers=headers('editor')).json()['role'] == 'editor'
    assert client.get(f'{API}/projects/{pid}', headers=headers('owner')).json()['role'] == 'owner'


def check_role_change_applies_next_request(client, pid):
    assert outcome(pid, 'viewer', 'editor') == 403
    sql('UPDATE project_members SET role=%s WHERE project_id=%s AND user_id=%s', 'editor', pid, USERS['viewer'].id)
    assert outcome(pid, 'viewer', 'editor') == 'editor'  # no cache: the very next check sees the new role
    assert client.get(f'{API}/projects/{pid}', headers=headers('viewer')).json()['role'] == 'editor'
    sql('DELETE FROM project_members WHERE project_id=%s AND user_id=%s', pid, USERS['viewer'].id)
    assert outcome(pid, 'viewer', 'viewer') == 404  # removed: access stops straight away


def check_new_project_creator_is_owner(client):
    r = client.post(f'{API}/projects', headers=headers('owner'), json={'name': 'Created after roles'})
    assert r.status_code == 201, r.text
    assert r.json()['role'] == 'owner'
    [(role, joined_at)] = sql('SELECT role, joined_at FROM project_members WHERE project_id=%s', r.json()['id'])
    assert role == 'owner' and joined_at is not None


def main():
    try:
        with TestClient(app) as client:
            r = client.post(f'{API}/projects', headers=headers('owner'), json={'name': 'Acme Clinic'})
            assert r.status_code == 201, r.text
            pid = r.json()['id']
            for name in ('editor', 'viewer'):
                sql('INSERT INTO project_members(project_id, user_id, role) VALUES (%s, %s, %s)',
                    pid, USERS[name].id, name)
            sql('INSERT INTO users(id, email, is_admin) VALUES (%s, %s, true)', USERS['admin'].id, EMAILS['admin'])
            check_role_matrix(pid)
            check_role_in_responses(client, pid)
            check_role_change_applies_next_request(client, pid)
            check_new_project_creator_is_owner(client)
        print('roles test passed')
    finally:
        sql('DELETE FROM projects WHERE owner_id = ANY(%s)', IDS)
        sql('DELETE FROM users WHERE id = ANY(%s)', IDS)


if __name__ == '__main__':
    main()
