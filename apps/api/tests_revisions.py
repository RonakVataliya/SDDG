"""Revisions (base of the FR24f edit conflict check): every save of a requirement or item counts its revision up and
records who saved it; a diagram version's revision is its parent's plus one. The API returns the revision with each
requirement, item and diagram.

Runs against the Postgres in DATABASE_URL (schema.sql applied, including migrations 0005-0007) with no AI or Kroki
calls (the quality checker is unreachable and skipped). Uses a throwaway user and deletes what it creates.
Run: python tests_revisions.py
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
EMAIL = f'rev-{uuid.uuid4().hex[:8]}@example.com'
USER_ID = f'dev:{EMAIL}'
me = {'Authorization': f'Bearer mock-token:{EMAIL}'}


def sql(query, *args):
    with psycopg.connect(os.environ['DATABASE_URL'], prepare_threshold=None) as c:
        return c.execute(query, args).fetchall() if query.startswith('SELECT') else c.execute(query, args)


def check_requirement_revisions(client, pid):
    r = client.post(f'{API}/projects/{pid}/statements', headers=me, json={'text': 'A patient books an appointment.'})
    assert r.status_code == 201, r.text
    st = r.json()
    assert st['revision'] == 1, st
    for expected in (2, 3):
        r = client.patch(f'{API}/projects/{pid}/statements/{st["id"]}', headers=me,
                         json={'text': f'A patient books an appointment (edit {expected}).'})
        assert r.status_code == 200, r.text
        assert r.json()['revision'] == expected, r.json()
    listed = {s['id']: s for s in client.get(f'{API}/projects/{pid}/statements', headers=me).json()}
    assert listed[st['id']]['revision'] == 3
    [(revised_by, revised_at)] = sql('SELECT revised_by, revised_at FROM statements WHERE id=%s', st['id'])
    assert revised_by == USER_ID and revised_at is not None  # who and when, for the 409 message
    return st['id']


def check_item_revisions(client, pid, sid):
    db.add_system_items(pid, [{'id': f'it_{uuid.uuid4().hex}', 'category': 'actor', 'name': 'Patient',
                               'statement_ids': [sid]}])
    item = client.get(f'{API}/projects/{pid}/items', headers=me).json()['items'][0]
    assert item['revision'] == 1, item
    r = client.patch(f'{API}/projects/{pid}/items/{item["id"]}', headers=me, json={'name': 'Clinic patient'})
    assert r.status_code == 200, r.text
    assert r.json()['revision'] == 2 and r.json()['revised_by'] == USER_ID, r.json()


def check_diagram_revisions(client, pid, sid):
    first = db.create_diagram(pid, 'use_case', 'Booking', '<svg/>', [], [sid])
    second = db.create_diagram(pid, 'use_case', 'Booking', '<svg/>', [], [sid], parent_id=first['id'], by=USER_ID)
    third = db.create_diagram(pid, 'use_case', 'Booking', '<svg/>', [], [sid], parent_id=second['id'], by=USER_ID)
    assert (first['revision'], second['revision'], third['revision']) == (1, 2, 3)
    assert client.get(f'{API}/diagrams/{third["id"]}', headers=me).json()['revision'] == 3
    listed = {d['id']: d for d in client.get(f'{API}/projects/{pid}/diagrams', headers=me).json()}
    assert listed[second['id']]['revision'] == 2


def main():
    try:
        with TestClient(app) as client:
            r = client.post(f'{API}/projects', headers=me, json={'name': 'Revisions'})
            assert r.status_code == 201, r.text
            pid = r.json()['id']
            sid = check_requirement_revisions(client, pid)
            check_item_revisions(client, pid, sid)
            check_diagram_revisions(client, pid, sid)
        print('revisions test passed')
    finally:
        sql('DELETE FROM projects WHERE owner_id=%s', USER_ID)


if __name__ == '__main__':
    main()
