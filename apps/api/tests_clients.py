"""Stream 5, client side: the project's client name and contact email.

Runs against the Postgres in DATABASE_URL with no AI or Kroki calls (diagrams are written straight to the
database). Uses throwaway users and deletes what it creates. Run: python tests_clients.py
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
OWNER, MEMBER, STRANGER = (f'cli-{uuid.uuid4().hex[:8]}@example.com' for _ in range(3))
IDS = [f'dev:{e}' for e in (OWNER, MEMBER, STRANGER)]
owner, member, stranger = ({'Authorization': f'Bearer mock-token:{e}'} for e in (OWNER, MEMBER, STRANGER))


def sql(query, *args):
    with psycopg.connect(os.environ['DATABASE_URL'], prepare_threshold=None) as c:
        return c.execute(query, args).fetchall() if query.startswith('SELECT') else c.execute(query, args)


def new_project(client, name, **extra):
    r = client.post(f'{API}/projects', headers=owner, json={'name': name, **extra})
    assert r.status_code == 201, r.text
    sql('INSERT INTO project_members(project_id, user_id) VALUES (%s, %s)', r.json()['id'], IDS[1])
    return r.json()


def check_client_details(client):
    p = new_project(client, 'Acme Clinic booking', client_name=' Acme Clinic ', contact_email='Mira@AcmeClinic.example')
    assert (p['client_name'], p['contact_email']) == ('Acme Clinic', 'mira@acmeclinic.example'), p
    assert new_project(client, 'No client yet')['client_name'] is None
    bad = client.post(f'{API}/projects', headers=owner, json={'name': 'Bad email', 'contact_email': 'not-an-email'})
    assert bad.status_code == 422, bad.text

    url = f'{API}/projects/{p["id"]}/client'
    r = client.patch(url, headers=owner, json={'client_name': 'Acme Health', 'contact_email': 'ops@acme.example'})
    assert r.status_code == 200 and r.json()['client_name'] == 'Acme Health', r.text
    assert client.patch(url, headers=member, json={'client_name': 'Hacked'}).status_code == 404
    assert client.patch(url, headers=stranger, json={'client_name': 'Hacked'}).status_code == 404
    assert client.patch(url, headers=owner, json={'contact_email': 'x@'}).status_code == 422
    # Home groups by the client name it gets from the project list.
    names = {q['name']: q['client_name'] for q in client.get(f'{API}/projects', headers=member).json()}
    assert names == {'Acme Clinic booking': 'Acme Health', 'No client yet': None}, names
    # Clearing removes the association; there is no client record left behind.
    r = client.patch(url, headers=owner, json={'client_name': ' ', 'contact_email': ''})
    assert (r.json()['client_name'], r.json()['contact_email']) == (None, None), r.text
    stored = sql('SELECT client_name FROM projects WHERE id=%s', p['id'])[0][0]
    assert stored is None
    client.patch(url, headers=owner, json={'client_name': 'Acme Health'})
    assert sql('SELECT client_name FROM projects WHERE id=%s', p['id'])[0][0].startswith('enc:')  # stored encrypted


def main():
    try:
        with TestClient(app) as client:
            check_client_details(client)
        print('stream 5 clients test passed')
    finally:
        sql('DELETE FROM projects WHERE owner_id = ANY(%s)', IDS)


if __name__ == '__main__':
    main()
