"""Traceability routes: the drift warning (FR17d) and naming consistency (FR17e).

Runs against the Postgres in DATABASE_URL with no AI or Kroki calls (diagrams are written straight to the
database). Uses a throwaway user and deletes what it creates. Run: python tests_traceability.py
The matching rules themselves are tested without a database in tests_traceability_logic.py.
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
OWNER, STRANGER, VIEWER = (f'trace-{uuid.uuid4().hex[:8]}@example.com' for _ in range(3))
owner = {'Authorization': f'Bearer mock-token:{OWNER}'}
stranger = {'Authorization': f'Bearer mock-token:{STRANGER}'}
viewer = {'Authorization': f'Bearer mock-token:{VIEWER}'}


def sql(query, *args):
    with psycopg.connect(os.environ['DATABASE_URL'], prepare_threshold=None) as c:
        return c.execute(query, args).fetchall() if query.startswith('SELECT') else c.execute(query, args)


def el(eid, label, kind, item=None, refs=()):
    return {'element_id': eid, 'model_item_id': item, 'kind': kind, 'label': label, 'statement_ids': list(refs),
            'is_assumption': not refs}


def seed(client):
    pid = client.post(f'{API}/projects', headers=owner, json={'name': 'Library'}).json()['id']
    s1, s2 = db.insert_statements(pid, [{'text': 'The librarian issues a book to a member.'},
                                        {'text': 'A member can return books.'}])
    spec = {'actors': [{'id': 'it_lib', 'name': 'Librarian'}, {'id': 'it_mem', 'name': 'Member'}],
            'usecases': [{'id': 'uc_issue', 'name': 'Issue book'}, {'id': 'uc_return', 'name': 'Return book'}],
            'associations': [{'actor_id': 'it_lib', 'usecase_id': 'uc_issue'},
                             {'actor_id': 'it_mem', 'usecase_id': 'uc_return'}], 'includes': [], 'extends': []}
    elements = [el('it_lib', 'Librarian', 'actor', 'it_lib', [s1]), el('uc_issue', 'Issue book', 'use_case', None, [s1]),
                el('it_mem', 'Member', 'actor', 'it_mem', [s2]), el('uc_return', 'Return book', 'use_case', None, [s2])]
    root = db.create_diagram(pid, 'use_case', 'Library · Use Case', '<svg><text>Librarian</text></svg>', elements, [s1, s2],
                             plantuml_source='@startuml\nactor "Librarian" as A\n@enduml', spec=spec)
    return pid, s1, s2, root, spec, elements


def check_drift(client, pid, s1, root, spec, elements):
    url = lambda d: f'{API}/diagrams/{d["id"]}/drift'  # noqa: E731
    assert client.get(url(root), headers=owner).json() == {'baseline_id': None, 'warnings': []}  # as generated
    assert client.get(url(root), headers=stranger).status_code == 404

    # An edit that drops "Issue book", which R-001 calls for, and links the Librarian to Return book.
    edited_spec = {**spec, 'usecases': [spec['usecases'][1]],
                   'associations': [spec['associations'][1], {'actor_id': 'it_lib', 'usecase_id': 'uc_return'}]}
    kept = [e for e in elements if e['element_id'] != 'uc_issue']
    v2 = db.create_diagram(pid, 'use_case', root['title'], root['svg'], kept, root['statement_ids'], spec=edited_spec,
                           parent_id=root['id'], instruction='Remove Issue book')
    body = client.get(url(v2), headers=owner).json()
    assert body['baseline_id'] == root['id'], body
    kinds = sorted((w['kind'], w['element_id']) for w in body['warnings'])
    assert kinds == [('element_removed', 'uc_issue'), ('relationship_added', 'it_lib-uc_return')], body
    assert next(w for w in body['warnings'] if w['kind'] == 'element_removed')['ref'] == 'R-001'

    # The requirement is changed so it no longer calls for the element: that warning goes by itself.
    db.set_statement_text(pid, s1, 'The librarian greets every member.')
    kinds = sorted(w['kind'] for w in client.get(url(v2), headers=owner).json()['warnings'])
    assert kinds == ['relationship_added'], kinds
    db.set_statement_text(pid, s1, 'The librarian issues a book to a member.')

    # Reverting the edit (a new version with everything back) clears them; so does the version it came from.
    v3 = db.create_diagram(pid, 'use_case', root['title'], root['svg'], elements, root['statement_ids'], spec=spec,
                           parent_id=v2['id'], instruction='Put Issue book back')
    assert client.get(url(v3), headers=owner).json()['warnings'] == []
    assert client.get(url(root), headers=owner).json()['warnings'] == []


def check_naming(client, pid, s1):
    base = f'{API}/projects/{pid}/traceability/naming'
    assert client.get(base, headers=owner).json() == {'issues': []}
    assert client.get(base, headers=stranger).status_code == 404
    db.create_diagram(pid, 'class', 'Library · Class', '<svg><text>Library staff</text></svg>',
                      [el('c_lib', 'Library staff', 'class', 'it_lib', [s1]), el('c_x', 'Librarian', 'class', 'it_other', [s1])],
                      [s1], plantuml_source='class "Library staff"', spec={'relations': []})
    issues = client.get(base, headers=owner).json()['issues']
    assert [i['model_item_id'] for i in issues] == ['it_lib'], issues  # it_other shares the name but is another item
    assert sorted(n['label'] for n in issues[0]['names']) == ['Librarian', 'Library staff']

    r = client.post(f'{base}/apply', headers=owner, json={'model_item_id': 'it_lib', 'name': 'Librarian'})
    assert r.status_code == 200, r.text
    updated = r.json()['updated']
    assert [u['type'] for u in updated] == ['class'], updated  # the use case already said Librarian
    assert client.get(base, headers=owner).json() == {'issues': []}
    new = db.member_diagram(updated[0]['id'], f'dev:{OWNER}')
    assert new['elements'][0]['label'] == 'Librarian' and 'Library staff' not in new['plantuml_source'], new
    assert 'Library staff' not in new['svg'] and new['parent_id'] and 'Renamed' in new['instruction']
    assert client.post(f'{base}/apply', headers=owner, json={'model_item_id': 'it_nope', 'name': 'X'}).status_code == 404
    assert client.post(f'{base}/apply', headers=owner, json={'model_item_id': 'it_lib', 'name': '  '}).status_code == 422
    assert client.post(f'{base}/apply', headers=stranger, json={'model_item_id': 'it_lib', 'name': 'X'}).status_code == 404

    # A Viewer may read the flag but not rename across diagrams, and nothing is written when they try.
    sql("INSERT INTO project_members(project_id, user_id, role) VALUES (%s, %s, 'viewer')", pid, f'dev:{VIEWER}')
    before = len(db.many('SELECT id FROM diagrams WHERE project_id=%s', pid))
    assert client.get(base, headers=viewer).status_code == 200
    r = client.post(f'{base}/apply', headers=viewer, json={'model_item_id': 'it_lib', 'name': 'Staff'})
    assert r.status_code == 403 and 'Viewer' in r.json()['detail'], r.text
    assert len(db.many('SELECT id FROM diagrams WHERE project_id=%s', pid)) == before


def main():
    try:
        with TestClient(app) as client:
            pid, s1, s2, root, spec, elements = seed(client)
            check_drift(client, pid, s1, root, spec, elements)
            check_naming(client, pid, s1)
        print('traceability test passed')
    finally:
        sql('DELETE FROM projects WHERE owner_id = ANY(%s)', [f'dev:{OWNER}'])


if __name__ == '__main__':
    main()
