"""Admin console API (FR23): user list, search, paging, deactivate and reactivate, and that non-admins are refused.

Runs against the Postgres in DATABASE_URL. The admin is faked with a dependency override (the dev mock tokens never
make an administrator); the guards under test are real. Throwaway users and projects, deleted at the end.
Run: python tests_admin.py
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
from core import db  # noqa: E402
from core.auth import User, get_current_user  # noqa: E402
from main import app  # noqa: E402

API = '/api/v1'
TAG = uuid.uuid4().hex[:8]
ADMIN, OWNER, MEMBER, LONER = (f'adm{TAG}-{n}@example.com' for n in ('admin', 'owner', 'member', 'loner'))
ADMIN_ID, OWNER_ID, MEMBER_ID, LONER_ID = (f'dev:{e}' for e in (ADMIN, OWNER, MEMBER, LONER))
IDS = [ADMIN_ID, OWNER_ID, MEMBER_ID, LONER_ID]


def sql(query, *args):
    with psycopg.connect(os.environ['DATABASE_URL'], prepare_threshold=None) as c:
        return c.execute(query, args).fetchall() if query.startswith('SELECT') else c.execute(query, args)


def check(client):
    for email, uid in zip((ADMIN, OWNER, MEMBER, LONER), IDS):
        db.get_user(email, uid)

    # Not an administrator: the mock token is refused on every admin route, and /me says so.
    nobody = {'Authorization': f'Bearer mock-token:{OWNER}'}
    assert client.get(f'{API}/me', headers=nobody).json() == {'id': OWNER_ID, 'email': OWNER, 'is_admin': False}
    assert client.get(f'{API}/admin/users', headers=nobody).status_code == 403
    for action in ('deactivate', 'reactivate'):
        assert client.post(f'{API}/admin/users/{LONER_ID}/{action}', headers=nobody).status_code == 403

    app.dependency_overrides[get_current_user] = lambda: User(ADMIN_ID, ADMIN, True)
    try:
        as_admin(client)
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def as_admin(client):
    h = {}
    # Search by email (any case), '_' and '%' are not wildcards, and the row carries what the Users table shows.
    r = client.get(f'{API}/admin/users', params={'q': f'ADM{TAG}'}, headers=h).json()
    assert r['total'] == 4 and r['page'] == 1 and r['page_size'] == 25, r
    assert {u['email'] for u in r['users']} == {ADMIN, OWNER, MEMBER, LONER}
    assert client.get(f'{API}/admin/users', params={'q': f'adm{TAG}-own%'}).json()['total'] == 0
    assert client.get(f'{API}/admin/users', params={'q': f'adm{TAG}_owner'}).json()['total'] == 0
    assert client.get(f'{API}/admin/users', params={'q': f'adm{TAG}-owner'}).json()['users'][0]['projects'] == 0
    # A space matches any text, so a name as the table shows it finds the account.
    r2 = client.get(f'{API}/admin/users', params={'q': f'  ADM{TAG} owner '}).json()
    assert [u['email'] for u in r2['users']] == [OWNER], r2
    assert client.get(f'{API}/admin/users', params={'q': 'x' * 101}).status_code == 422
    assert client.get(f'{API}/admin/users', params={'page': 0}).status_code == 422
    assert client.get(f'{API}/admin/users', params={'q': f'adm{TAG}', 'page': 2}).json()['users'] == []

    # The signed-in admin is an administrator and active.
    me = next(u for u in r['users'] if u['id'] == ADMIN_ID)
    assert me['status'] == 'active' and me['last_seen_at']
    sql('UPDATE users SET is_admin = true WHERE id = %s', ADMIN_ID)
    assert client.get(f'{API}/admin/users', params={'q': ADMIN}).json()['users'][0]['is_admin'] is True

    # Guards: not yourself, unknown id, and not the only owner of a project that has other members.
    assert client.post(f'{API}/admin/users/{ADMIN_ID}/deactivate').status_code == 409
    assert client.post(f'{API}/admin/users/nope/deactivate').status_code == 404
    assert client.post(f'{API}/admin/users/nope/reactivate').status_code == 404
    pid = db.create_project(OWNER_ID, 'Admin test project')['id']
    sql("INSERT INTO project_members(project_id, user_id, role) VALUES (%s, %s, 'editor')", pid, MEMBER_ID)
    r = client.post(f'{API}/admin/users/{OWNER_ID}/deactivate')
    assert r.status_code == 409 and 'only owner of 1 project' in r.json()['detail'], r.text
    assert not sql('SELECT 1 FROM users WHERE id = %s AND deactivated_at IS NOT NULL', OWNER_ID)

    # Deactivate keeps the projects, is repeatable without a second log row, and reactivate undoes it.
    r = client.post(f'{API}/admin/users/{MEMBER_ID}/deactivate').json()
    assert r['status'] == 'deactivated' and r['projects'] == 1, r
    client.post(f'{API}/admin/users/{MEMBER_ID}/deactivate')
    assert sql("SELECT count(*) FROM activity_log WHERE actor_id = %s AND action = 'user.deactivated'", ADMIN_ID)[0][0] == 1
    assert sql('SELECT 1 FROM project_members WHERE project_id = %s AND user_id = %s', pid, MEMBER_ID)
    assert client.post(f'{API}/admin/users/{MEMBER_ID}/reactivate').json()['status'] == 'active'
    assert sql("SELECT count(*) FROM activity_log WHERE actor_id = %s AND action = 'user.reactivated'", ADMIN_ID)[0][0] == 1
    # The guard follows the roles, not who created the project. Move ownership to MEMBER: they are now the one who must
    # stay, and the creator, now only an editor, may go.
    sql("UPDATE project_members SET role = 'editor' WHERE project_id = %s AND user_id = %s", pid, OWNER_ID)
    sql("UPDATE project_members SET role = 'owner' WHERE project_id = %s AND user_id = %s", pid, MEMBER_ID)
    r = client.post(f'{API}/admin/users/{MEMBER_ID}/deactivate')
    assert r.status_code == 409 and 'only owner of 1 project' in r.json()['detail'], r.text
    assert client.post(f'{API}/admin/users/{OWNER_ID}/deactivate').json()['status'] == 'deactivated'
    assert client.post(f'{API}/admin/users/{OWNER_ID}/reactivate').json()['status'] == 'active'
    # Two Owners: either may go, but never the last active one while other people are members.
    sql("UPDATE project_members SET role = 'owner' WHERE project_id = %s AND user_id = %s", pid, OWNER_ID)
    assert client.post(f'{API}/admin/users/{MEMBER_ID}/deactivate').json()['status'] == 'deactivated'
    r = client.post(f'{API}/admin/users/{OWNER_ID}/deactivate')
    assert r.status_code == 409, r.text  # MEMBER is still a member, and OWNER is now the only active Owner
    assert client.post(f'{API}/admin/users/{MEMBER_ID}/reactivate').json()['status'] == 'active'
    # Once nobody else is in the project, the owner can go.
    sql('DELETE FROM project_members WHERE project_id = %s AND user_id = %s', pid, MEMBER_ID)
    assert client.post(f'{API}/admin/users/{OWNER_ID}/deactivate').json()['status'] == 'deactivated'


def main():
    db.init_db()
    try:
        with TestClient(app) as client:
            check(client)
        print('admin users test passed')
    finally:
        sql('DELETE FROM activity_log WHERE actor_id = ANY(%s)', IDS)
        sql('DELETE FROM projects WHERE owner_id = ANY(%s)', IDS)
        sql('DELETE FROM users WHERE id = ANY(%s)', IDS)


if __name__ == '__main__':
    main()
