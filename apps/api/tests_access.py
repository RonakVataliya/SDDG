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
from core import db, styling
from core import design_db as ddb
from core import stories_db as sdb
from core import testing_db as tdb
from core.crypto import PREFIX
from core.notifications import notify
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
        sql('DELETE FROM notifications WHERE user_id = ANY(%s)', [OWNER_ID, STRANGER_ID])


def check(client):
    api = '/api/v1'
    pid = client.post(f'{api}/projects', headers=mine, json={'name': 'Secret project'}).json()['id']
    client.post(f'{api}/me/consent', headers=mine, json={'policy_version': integrated.POLICY_VERSION})
    assert client.post(f'{api}/projects/{pid}/inputs', headers=mine, json={'text': SECRET_TEXT}).status_code == 202
    statements = client.get(f'{api}/projects/{pid}/statements', headers=mine).json()
    statement = statements[0]
    assert statement['text'] == SECRET_TEXT, statement
    assert client.post(f'{api}/projects/{pid}/confirmation', headers=mine).status_code == 201
    job = db.create_job(pid, 'generation', 3, 'Queued', diagram_types=['use_case'])
    asyncio.run(integrated.generation_worker(job['id'], pid, ['use_case']))  # extracts the items, then draws
    diagram_id = db.member_job(job['id'], OWNER_ID)['diagram_ids'][0]
    item = client.get(f'{api}/projects/{pid}/items', headers=mine).json()['items'][0]
    db.save_flags(pid, [{'statement_id': statement['id'], 'type': 'ambiguous', 'reason': 'Vague.'}], [statement['id']])
    flag_id = client.get(f'{api}/projects/{pid}/flags', headers=mine).json()[0]['id']
    db.update_job(job['id'], status='failed', error=f'Kroki rejected: {SECRET_TEXT}')  # failure text can echo requirements
    client.patch(f'{api}/projects/{pid}/client', headers=mine, json={'client_name': SECRET_TEXT})
    # Tests feature rows (written directly: no AI is needed to check who can reach them).
    tdb.replace_design(pid, statement['id'], SECRET_TEXT, [{'given': SECRET_TEXT, 'when': 'w', 'then': 't'}],
                       [{'name': 'days', 'kind': 'range', 'description': SECRET_TEXT, 'min': 1, 'max': 30}],
                       [{'kind': 'basic', 'text': SECRET_TEXT}], [{'measure': SECRET_TEXT, 'limit': 2, 'unit': 's'}])
    tdb.replace_drafts(pid, statement['id'], SECRET_TEXT, [{
        'title': SECRET_TEXT, 'technique': 'EC', 'kind': 'positive', 'priority': 'high', 'outcome': 'accepted',
        'test_data': {'days': 15}, 'covers': ['EC:days:valid']}])
    case = tdb.list_cases(pid)[0]
    tdb.save_steps(pid, case['id'], [SECRET_TEXT], [SECRET_TEXT], SECRET_TEXT)
    run = tdb.create_run(pid, SECRET_TEXT, 'all', [case['id']], OWNER)
    tdb.save_result(pid, run['id'], case['id'], 'fail', SECRET_TEXT, OWNER)
    story = sdb.create_story(pid, {'role': SECRET_TEXT, 'goal': SECRET_TEXT, 'reason': SECRET_TEXT, 'priority': 'must',
                                   'estimate': None, 'status': 'todo', 'assignee_id': None,
                                   'confirmations': [SECRET_TEXT], 'statement_ids': [statement['id']]})
    ddb.save(pid, 'goals', {'goals': [{'name': 'Reliability', 'reason': SECRET_TEXT, 'statement_ids': [statement['id']]}]},
             {'groups': {}, 'conflicts': []}, 'hash')

    invitation = client.post(f'{api}/projects/{pid}/invitations', headers=mine,
                             json={'email': f'acc-{uuid.uuid4().hex[:8]}@example.com'}).json()
    note = notify(OWNER_ID, 'mention', {'project_id': pid})

    # 1. A stranger gets 404 on every route that takes a resource id, whatever the method.
    ids = {'project_id': pid, 'item_id': item['id'], 'statement_id': statement['id'], 'job_id': job['id'], 'diagram_id': diagram_id, 'flag_id': flag_id,
           'condition_id': tdb.get_conditions(pid)[0]['id'], 'criterion_id': tdb.get_criteria(pid)[0]['id'],
           'case_id': case['id'], 'run_id': run['id'], 'story_id': story['id'], 'kind': 'goals', 'document_id': 'doc_' + uuid.uuid4().hex,
           'member_id': OWNER_ID, 'invitation_id': invitation['id'], 'notification_id': note['id']}
    bodies = {'/inputs': {'text': 'Hacked.'}, '/generations': {'diagram_types': ['use_case']},
              '/items/{item_id}': {'name': 'Hacked', 'description': 'Hacked'},
              '/revisions': {'instruction': 'Hacked'}, '/answer': {'answer': 'Hacked'},
              '/layout': {'positions': {}}, '/projects/{project_id}': {'name': 'Hacked', 'confirm_name': 'Secret project'}, '/client': {'client_name': 'Hacked'},
              '/statements': {'text': 'Hacked'}, '/statements/{statement_id}': {'text': 'Hacked'},
              '/validation/accept': {'warning_id': 'Hacked'}, '/validation/fix': {'warning_id': 'Hacked'},
              # Tests feature: valid bodies, so a refusal can only come from the access check
              '/criteria-jobs': {'statement_ids': [statement['id']]}, '/step-jobs': {},
              '/conditions/{condition_id}': {'min': 0}, '/criteria/{criterion_id}': {'given': 'x', 'when': 'x', 'then': 'x'},
              '/tests/cases': {'statement_id': statement['id'], 'title': 'Hacked', 'kind': 'edge', 'priority': 'low',
                               'steps': ['x'], 'expected': 'x'},
              '/tests/cases/{case_id}': {'kept': False}, '/tests/runs': {'name': 'Hacked', 'mode': 'all'},
              '/results/{case_id}': {'status': 'pass'},
              '/stories': {'role': 'r', 'goal': 'g', 'reason': 'r', 'statement_ids': [statement['id']]},
              '/stories/{story_id}': {'status': 'done'},
              '/members/{member_id}': {'role': 'viewer'},  # the stranger tries to demote the owner
              '/design/{kind}': {'content': {'goals': [{'name': 'Reliability', 'reason': 'Hacked', 'statement_ids': []}]}},
              '/style': styling.DEFAULT_STYLE, '/preview': styling.DEFAULT_STYLE,
              # Invitations and traceability: valid bodies, so a refusal can only come from the access check
              '/invitations': {'email': 'hacked@example.com', 'role': 'owner'},
              '/naming/apply': {'model_item_id': item['id'], 'name': 'Hacked'}}
    swept = 0
    for path, methods in app.openapi()['paths'].items():
        if not any(f'{{{k}}}' in path for k in ids):
            continue
        for method in methods:
            body = next((b for suffix, b in bodies.items() if path.endswith(suffix)), None)
            r = client.request(method, path.format(**ids), headers=theirs, json=body)
            assert r.status_code == 404, (method, path, r.status_code, r.text)
            swept += 1
    assert swept == 75, swept  # a new route with a resource id must be added to this check
    # (34 + 3 style + 15 Tests + 4 documents + 4 Stories + 4 Design
    #  + 3 Members + 8 invitations/notifications/traceability)

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
    mine_cases = client.get(f'{api}/projects/{pid}/tests/cases', headers=mine).json()
    assert len(mine_cases) == 1 and mine_cases[0]['kept'] and mine_cases[0]['title'] == SECRET_TEXT
    assert len(client.get(f'{api}/projects/{pid}/tests/runs', headers=mine).json()) == 1
    assert client.get(f'{api}/projects/{pid}/stories', headers=mine).json()['stories'][0]['updated_at'] == story['updated_at'].isoformat()
    assert client.get(f'{api}/projects/{pid}/design', headers=mine).json()['sections'][0]['version'] == 1

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
    assert SECRET_TEXT in client.get(f'{api}/jobs/{job["id"]}', headers=mine).json()['error']


if __name__ == '__main__':
    main()