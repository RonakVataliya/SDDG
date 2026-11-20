"""Invitations (FR24a) and the bell: invite, list, revoke, accept from the bell and by link, expiry, administrators.

Runs against the Postgres in DATABASE_URL with no AI or Kroki calls. Uses throwaway users and deletes what it
creates. Needs migrations 0010 and 0011 (or schema.sql). Run: python tests_invitations.py
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
OWNER, VIEWER, INVITEE, OUTSIDER, ADMIN, CO_OWNER = (f'inv-{uuid.uuid4().hex[:8]}@example.com' for _ in range(6))
EMAILS = [OWNER, VIEWER, INVITEE, OUTSIDER, ADMIN, CO_OWNER]
IDS = [f'dev:{e}' for e in EMAILS]
owner, viewer, invitee, outsider, admin, co_owner = ({'Authorization': f'Bearer mock-token:{e}'} for e in EMAILS)


def sql(query, *args):
    with psycopg.connect(os.environ['DATABASE_URL'], prepare_threshold=None) as c:
        return c.execute(query, args).fetchall() if query.startswith('SELECT') else c.execute(query, args)


def setup(client):
    for email, uid in zip(EMAILS, IDS):  # the throwaway users need a row so their email can be looked up
        sql('INSERT INTO users(id, email) VALUES (%s, %s) ON CONFLICT DO NOTHING', uid, email)
    sql('UPDATE users SET is_admin=true WHERE id=%s', IDS[4])
    r = client.post(f'{API}/projects', headers=owner, json={'name': 'Acme Clinic'})
    assert r.status_code == 201, r.text
    pid = r.json()['id']
    sql("INSERT INTO project_members(project_id, user_id, role) VALUES (%s, %s, 'viewer')", pid, IDS[1])
    sql("INSERT INTO project_members(project_id, user_id, role) VALUES (%s, %s, 'owner')", pid, IDS[5])
    return pid


def check_invite_rules(client, pid):
    url = f'{API}/projects/{pid}/invitations'
    assert client.post(url, headers=outsider, json={'email': INVITEE}).status_code == 404  # cannot tell it exists
    assert client.get(url, headers=outsider).status_code == 404
    r = client.post(url, headers=viewer, json={'email': INVITEE})
    assert r.status_code == 403, r.text  # a member who is not an Owner
    assert client.post(url, headers=owner, json={'email': 'not-an-email'}).status_code == 422
    assert client.post(url, headers=owner, json={'email': INVITEE, 'role': 'boss'}).status_code == 422
    assert client.post(url, headers=owner, json={'email': VIEWER}).status_code == 409  # already a member

    r = client.post(url, headers=owner, json={'email': f'  {INVITEE.upper()} '})
    assert r.status_code == 201, r.text
    inv = r.json()
    assert inv['email'] == INVITEE and inv['role'] == 'viewer' and inv['token'], inv  # lowercased, default Viewer
    assert inv['invited_by']['email'] == OWNER
    days = (sql('SELECT expires_at - created_at FROM invitations WHERE id=%s', inv['id'])[0][0]).days
    assert days == 7, days
    assert client.post(url, headers=owner, json={'email': INVITEE}).status_code == 409  # one open invitation each

    listed = client.get(url, headers=owner).json()
    assert [i['id'] for i in listed] == [inv['id']] and listed[0]['token'] == inv['token']
    assert client.get(url, headers=viewer).json()[0]['token'] is None  # only Owners get the link
    return inv


def check_accept_from_bell(client, pid, inv):
    bell = client.get(f'{API}/notifications', headers=invitee).json()
    assert bell['unread_count'] == 1, bell
    n = bell['items'][0]
    assert n['type'] == 'invitation' and n['project'] == {'id': pid, 'name': 'Acme Clinic'}, n
    assert n['invitation']['role'] == 'viewer' and n['invitation']['status'] == 'open' and n['from_user']['email'] == OWNER
    assert n['payload'].keys() == {'invitation_id', 'project_id', 'from_user_id'}  # IDs only
    assert client.get(f'{API}/notifications', headers=invitee).json()['unread_count'] == 1  # not added twice
    assert client.get(f'{API}/projects/{pid}', headers=invitee).status_code == 404  # not a member yet

    assert client.post(f'{API}/invitations/{inv["id"]}/accept', headers=outsider).status_code == 404  # not theirs
    r = client.post(f'{API}/invitations/{inv["id"]}/accept', headers=invitee)
    assert r.status_code == 200, r.text
    assert r.json()['id'] == pid and r.json()['role'] == 'viewer'
    assert sql('SELECT role FROM project_members WHERE project_id=%s AND user_id=%s', pid, IDS[2])[0][0] == 'viewer'
    mine = client.get(f'{API}/projects', headers=invitee).json()
    assert [p['id'] for p in mine] == [pid]  # the project is in their list straight away
    # owner_email / joined_at and the project's role come from C2's Members work (#59), not from here.
    bell = client.get(f'{API}/notifications', headers=invitee).json()
    assert bell['unread_count'] == 0 and bell['items'][0]['invitation']['status'] == 'accepted'
    assert client.post(f'{API}/invitations/{inv["id"]}/accept', headers=invitee).status_code == 200  # twice is fine
    assert client.get(f'{API}/projects/{pid}/invitations', headers=owner).json() == []  # no longer open


def check_revoke_expiry_and_link(client, pid):
    url = f'{API}/projects/{pid}/invitations'
    inv = client.post(url, headers=owner, json={'email': OUTSIDER, 'role': 'editor'}).json()
    assert client.delete(f'{url}/{inv["id"]}', headers=viewer).status_code == 403
    assert client.delete(f'{url}/{inv["id"]}', headers=owner).status_code == 204
    assert client.delete(f'{url}/{inv["id"]}', headers=owner).status_code == 404  # already revoked
    r = client.post(f'{API}/invitations/{inv["id"]}/accept', headers=outsider)
    assert r.status_code == 410 and 'withdrawn' in r.json()['detail'], r.text
    assert client.get(f'{API}/notifications', headers=outsider).json()['unread_count'] == 0  # revoked: not shown

    inv = client.post(url, headers=owner, json={'email': OUTSIDER, 'role': 'editor'}).json()  # can be sent again
    sql("UPDATE invitations SET expires_at = now() - interval '1 minute' WHERE id=%s", inv['id'])
    assert client.get(url, headers=owner).json() == []  # expired ones are not open
    r = client.post(f'{API}/invitations/{inv["id"]}/accept', headers=outsider)
    assert r.status_code == 410 and 'expired' in r.json()['detail'], r.text

    inv = client.post(url, headers=owner, json={'email': OUTSIDER, 'role': 'editor'}).json()  # a new one after expiry
    assert client.post(f'{API}/invitations/accept', headers=invitee, json={'token': inv['token']}).status_code == 404
    r = client.post(f'{API}/invitations/accept', headers=outsider, json={'token': inv['token']})  # the copied link
    assert r.status_code == 200 and r.json()['role'] == 'editor', r.text
    assert client.post(f'{API}/invitations/accept', headers=outsider, json={'token': 'nope'}).status_code == 404


def check_admin_invite(client, pid):
    url = f'{API}/projects/{pid}/invitations'
    stranger = f'inv-{uuid.uuid4().hex[:8]}@example.com'
    r = client.post(url, headers=admin, json={'email': stranger, 'role': 'owner'})
    assert r.status_code == 201, r.text  # an administrator may invite without being a member
    assert client.get(url, headers=admin).status_code == 200
    for headers, who in ((owner, OWNER), (co_owner, CO_OWNER)):  # every Owner is told
        items = client.get(f'{API}/notifications', headers=headers).json()['items']
        hit = [n for n in items if n['type'] == 'admin_invited']
        assert len(hit) == 1, (who, items)
        assert hit[0]['invitation']['email'] == stranger and hit[0]['from_user']['email'] == ADMIN
    r = client.post(url, headers=owner, json={'email': f'inv-{uuid.uuid4().hex[:8]}@example.com'})
    assert r.status_code == 201
    assert not [n for n in client.get(f'{API}/notifications', headers=co_owner).json()['items']
                if n['type'] == 'admin_invited' and n['invitation']['email'] != stranger]  # an Owner's invite: no notice


def main():
    try:
        with TestClient(app) as client:
            pid = setup(client)
            inv = check_invite_rules(client, pid)
            check_accept_from_bell(client, pid, inv)
            check_revoke_expiry_and_link(client, pid)
            check_admin_invite(client, pid)
        print('invitations test passed')
    finally:
        sql('DELETE FROM projects WHERE owner_id = ANY(%s)', IDS)
        sql('DELETE FROM notifications WHERE user_id = ANY(%s)', IDS)
        sql('DELETE FROM users WHERE id = ANY(%s)', IDS)


if __name__ == '__main__':
    main()
