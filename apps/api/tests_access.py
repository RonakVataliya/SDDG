"""Checks that only project members can reach a project's data, that stored content is encrypted, and that logs
hold no user content. Runs against the Postgres in DATABASE_URL with the AI/Kroki calls faked, as in
tests_integration.py. Uses throwaway users and deletes what it creates. Run: python tests_access.py
"""
import asyncio
import io
import logging
import os
import uuid

import psycopg
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault('DATA_ENCRYPTION_KEY', Fernet.generate_key().decode())

from fastapi.testclient import TestClient
import routers.integrated as integrated
import tests_integration
from core import db
from core.crypto import PREFIX
from main import app

SECRET_TEXT = f'Zebra{uuid.uuid4().hex} logs in.'  # must never show up in the database or the logs
OWNER, STRANGER = (f'acc-{uuid.uuid4().hex[:8]}@example.com' for _ in range(2))
OWNER_ID, STRANGER_ID = f'dev:{OWNER}', f'dev:{STRANGER}'
mine = {'Authorization': f'Bearer mock-token:{OWNER}'}
theirs = {'Authorization': f'Bearer mock-token:{STRANGER}'}


def sql(query, *args):
    with psycopg.connect(os.environ['DATABASE_URL'], prepare_threshold=None) as c:
        return c.execute(query, args).fetchall() if query.startswith('SELECT') else c.execute(query, args)


def main():
    log = io.StringIO()
    logging.getLogger().addHandler(logging.StreamHandler(log))
    logging.getLogger().setLevel(logging.INFO)
    requirement = tests_integration.EXTRACTION['requirements'][0]
    requirement.update(text=SECRET_TEXT, source_location={'line_start': 1, 'line_end': 1, 'excerpt': SECRET_TEXT})
    original = integrated.httpx.AsyncClient
    integrated.httpx.AsyncClient = tests_integration.FakeAIClient
    try:
        with TestClient(app) as client:
            check(client)
        assert SECRET_TEXT not in log.getvalue(), 'user content found in the logs'
        print('access control, encryption and log test passed')
    finally:
        integrated.httpx.AsyncClient = original
        sql('DELETE FROM projects WHERE owner_id = ANY(%s)', [OWNER_ID, STRANGER_ID])
        sql('DELETE FROM consents WHERE user_id = ANY(%s)', [OWNER_ID, STRANGER_ID])


def check(client):
    api = '/api/v1'
    pid = client.post(f'{api}/projects', headers=mine, json={'name': 'Secret project'}).json()['id']
    client.post(f'{api}/me/consent', headers=mine, json={'policy_version': integrated.POLICY_VERSION})
    assert client.post(f'{api}/projects/{pid}/inputs', headers=mine, json={'text': SECRET_TEXT}).status_code == 202
    statements = client.get(f'{api}/projects/{pid}/statements', headers=mine).json()
    statement = statements[0]
    assert statement['text'] == SECRET_TEXT, statement
    item = client.get(f'{api}/projects/{pid}/items', headers=mine).json()['items'][0]
    assert client.post(f'{api}/projects/{pid}/confirmation', headers=mine).status_code == 201
    job = db.create_job(pid, 'generation', 3, 'Queued', diagram_types=['use_case'])
    asyncio.run(integrated.generation_worker(job['id'], pid, ['use_case']))
    diagram_id = db.member_job(job['id'], OWNER_ID)['diagram_ids'][0]
    db.save_flags(pid, [{'statement_id': statement['id'], 'type': 'ambiguous', 'reason': 'Vague.'}], [statement['id']])
    flag_id = client.get(f'{api}/projects/{pid}/flags', headers=mine).json()[0]['id']

    # 1. A stranger gets 404 on every route that takes a resource id, whatever the method.
    ids = {'project_id': pid, 'item_id': item['id'], 'job_id': job['id'], 'diagram_id': diagram_id, 'flag_id': flag_id}
    bodies = {'/inputs': {'text': 'Hacked.'}, '/generations': {'diagram_types': ['use_case']},
              '/items/{item_id}': {'name': 'Hacked', 'description': 'Hacked'},
              '/revisions': {'instruction': 'Hacked'}, '/answer': {'answer': 'Hacked'}}
    swept = 0
    for path, methods in app.openapi()['paths'].items():
        if not any(f'{{{k}}}' in path for k in ids):
            continue
        for method in methods:
            body = next((b for suffix, b in bodies.items() if path.endswith(suffix)), None)
            r = client.request(method, path.format(**ids), headers=theirs, json=body)
            assert r.status_code == 404, (method, path, r.status_code, r.text)
            swept += 1
    assert swept == 18, swept  # a new route with a resource id must be added to this check

    # 2. A guessed id gets exactly the answer a real but foreign id gets, so nothing reveals what exists.
    foreign = client.get(f'{api}/projects/{pid}', headers=theirs)
    for url in (f'projects/pr_{uuid.uuid4().hex}', f'diagrams/dg_{uuid.uuid4().hex}', f'jobs/job_{uuid.uuid4().hex}'):
        guess = client.get(f'{api}/{url}', headers=theirs)
        assert (guess.status_code, guess.json()) == (404, foreign.json()), guess.text
    assert client.get(f'{api}/projects', headers=theirs).json() == []

    # 3. The stranger's attempted writes changed nothing.
    assert client.get(f'{api}/projects/{pid}/statements', headers=mine).json() == statements
    assert client.get(f'{api}/projects/{pid}/items', headers=mine).json()['items'][0] == item
    assert len(client.get(f'{api}/projects/{pid}/diagrams', headers=mine).json()) == 1

    # 4. Access follows the project_members table: adding a member opens the project, removing one closes it.
    sql('INSERT INTO project_members(project_id, user_id) VALUES (%s, %s)', pid, STRANGER_ID)
    assert client.get(f'{api}/projects/{pid}', headers=theirs).status_code == 200
    assert client.get(f'{api}/diagrams/{diagram_id}', headers=theirs).status_code == 200
    sql('DELETE FROM project_members WHERE project_id=%s AND user_id=%s', pid, STRANGER_ID)
    assert client.get(f'{api}/projects/{pid}', headers=theirs).status_code == 404

    # 5. Everything the database holds for this project is encrypted, while the API still returns plain text.
    for table, columns in db.SECRET.items():
        for col in columns:
            where = 'id' if table == 'projects' else 'project_id'
            for (value,) in sql(f'SELECT {col} FROM {table} WHERE {where}=%s AND {col} IS NOT NULL', pid):
                assert value.startswith(PREFIX) and SECRET_TEXT not in value, (table, col)
    assert client.get(f'{api}/diagrams/{diagram_id}', headers=mine).json()['svg'].startswith('<svg')


if __name__ == '__main__':
    main()
