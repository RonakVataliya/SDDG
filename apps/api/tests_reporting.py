"""Stream 5, project side: rename, delete and archive (Owner only).

Runs against the Postgres in DATABASE_URL with no AI or Kroki calls (the fixture is written straight to the
database). Uses throwaway users and deletes what it creates. Run: python tests_reporting.py
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
from main import app  # noqa: E402

API = '/api/v1'
OWNER, MEMBER = (f'rep-{uuid.uuid4().hex[:8]}@example.com' for _ in range(2))
OWNER_ID, MEMBER_ID = f'dev:{OWNER}', f'dev:{MEMBER}'
owner = {'Authorization': f'Bearer mock-token:{OWNER}'}
member = {'Authorization': f'Bearer mock-token:{MEMBER}'}


def sql(query, *args):
    with psycopg.connect(os.environ['DATABASE_URL'], prepare_threshold=None) as c:
        return c.execute(query, args).fetchall() if query.startswith('SELECT') else c.execute(query, args)


def new_project(client, name):
    r = client.post(f'{API}/projects', headers=owner, json={'name': name})
    assert r.status_code == 201, r.text
    pid = r.json()['id']
    sql('INSERT INTO project_members(project_id, user_id) VALUES (%s, %s)', pid, MEMBER_ID)  # a non-owner member
    return pid


def check_rename(client):
    pid = new_project(client, 'Acme Clinic booking')
    new_project(client, 'Other project')
    r = client.patch(f'{API}/projects/{pid}', headers=owner, json={'name': '  Acme booking v2 '})
    assert r.status_code == 200 and r.json()['name'] == 'Acme booking v2', r.text
    assert r.json()['is_owner'] is True
    assert client.patch(f'{API}/projects/{pid}', headers=owner, json={'name': 'acme BOOKING v2'}).status_code == 200  # its own name
    assert client.patch(f'{API}/projects/{pid}', headers=owner, json={'name': 'OTHER project'}).status_code == 409
    assert client.patch(f'{API}/projects/{pid}', headers=owner, json={'name': '   '}).status_code == 422
    assert client.patch(f'{API}/projects/{pid}', headers=owner, json={'name': ''}).status_code == 422
    # A member who is not the owner sees the project but cannot rename it, and is told nothing more than an outsider.
    assert client.get(f'{API}/projects/{pid}', headers=member).json()['is_owner'] is False
    r = client.patch(f'{API}/projects/{pid}', headers=member, json={'name': 'Hacked'})
    assert r.status_code == 404, r.text
    assert client.get(f'{API}/projects/{pid}', headers=owner).json()['name'] == 'acme BOOKING v2'


def check_delete(client):
    pid = new_project(client, 'To delete')
    sid = db.insert_statements(pid, [{'text': 'The clinic books visits.'}])[0]
    db.create_diagram(pid, 'use_case', 'To delete · Use Case', '<svg/>', [], [sid])
    db.save_flags(pid, [{'statement_id': sid, 'type': 'ambiguous', 'reason': 'Vague.'}], [sid])
    r = client.request('DELETE', f'{API}/projects/{pid}', headers=owner, json={'confirm_name': 'to delete'})
    assert r.status_code == 422 and r.json()['detail'] == 'Type the project name to confirm.', r.text
    assert client.get(f'{API}/projects/{pid}', headers=owner).status_code == 200  # nothing deleted
    assert client.request('DELETE', f'{API}/projects/{pid}', headers=member, json={'confirm_name': 'To delete'}).status_code == 404
    assert client.request('DELETE', f'{API}/projects/{pid}', headers=owner, json={'confirm_name': 'To delete'}).status_code == 204
    assert client.get(f'{API}/projects/{pid}', headers=owner).status_code == 404
    for table in ('statements', 'diagrams', 'flags', 'project_members'):
        assert sql(f'SELECT count(*) FROM {table} WHERE project_id=%s', pid)[0][0] == 0, table


def check_archive(client):
    pid = new_project(client, 'To archive')
    assert client.post(f'{API}/projects/{pid}/archive', headers=member).status_code == 404
    r = client.post(f'{API}/projects/{pid}/archive', headers=owner)
    assert r.status_code == 200 and r.json()['archived_at'] and r.json()['archived_by'] == OWNER, r.text
    first = r.json()['archived_at']
    assert client.post(f'{API}/projects/{pid}/archive', headers=owner).json()['archived_at'] == first  # idempotent
    # Reads and exports keep working; the web app shows the project read-only.
    assert client.get(f'{API}/projects/{pid}/statements', headers=member).status_code == 200
    assert client.delete(f'{API}/projects/{pid}/archive', headers=member).status_code == 404
    assert client.delete(f'{API}/projects/{pid}/archive', headers=owner).json()['archived_at'] is None


def main():
    try:
        with TestClient(app) as client:
            check_rename(client)
            check_delete(client)
            check_archive(client)
        print('stream 5 reporting test passed')
    finally:
        sql('DELETE FROM projects WHERE owner_id = ANY(%s)', [OWNER_ID, MEMBER_ID])


if __name__ == '__main__':
    main()
