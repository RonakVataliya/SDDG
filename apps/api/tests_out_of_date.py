"""Out-of-date diagrams (FR17c): editing, deleting or applying a fix to a requirement marks every diagram that draws it
as out of date; an edited version inherits the mark; a fresh generation of that type clears it; nothing is ever marked
up to date silently. Also the activity log rows this story writes (statement.added/deleted/edited, diagram.regenerated).

Runs against the Postgres in DATABASE_URL, no AI calls (the quality checker and the generation worker are faked).
Throwaway user and project, deleted at the end. Run: python tests_out_of_date.py
"""
import os
import time
import uuid

import httpx
import psycopg
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()
os.environ['DEV_AUTH_BYPASS'] = 'true'
os.environ.setdefault('DATA_ENCRYPTION_KEY', Fernet.generate_key().decode())

from fastapi.testclient import TestClient  # noqa: E402
from core import db, quality  # noqa: E402
from core.requirements import on_requirement_edited  # noqa: E402
from main import app  # noqa: E402
from routers import integrated  # noqa: E402

API = '/api/v1'
EMAIL = f'ood-{uuid.uuid4().hex[:8]}@example.com'
USER_ID = f'dev:{EMAIL}'
H = {'Authorization': f'Bearer mock-token:{EMAIL}'}


def sql(query, *args):
    with psycopg.connect(os.environ['DATABASE_URL'], prepare_threshold=None) as c:
        return c.execute(query, args).fetchall() if query.startswith('SELECT') else c.execute(query, args)


def stale(client, pid):
    """{diagram id: out_of_date} as the API's diagram list says it."""
    r = client.get(f'{API}/projects/{pid}/diagrams', headers=H)
    assert r.status_code == 200, r.text
    return {d['id']: d['out_of_date'] for d in r.json()}


def draw(pid, dtype, ids, parent=None):
    time.sleep(0.01)  # created_at and the edit time are compared: keep them apart
    return db.create_diagram(pid, dtype, f'{dtype} diagram', '<svg/>', [], ids, parent_id=parent)['id']


def log(pid):
    return [(r['action'], r['target'], r['detail']) for r in db.many(
        'SELECT action, target, detail FROM activity_log WHERE project_id = %s ORDER BY created_at', pid)]


def check(client):
    db.get_user(EMAIL, USER_ID)
    pid = db.create_project(USER_ID, 'Out of date project')['id']
    s1, s2, s3 = db.insert_statements(pid, [{'text': t, 'labels': ['functional']} for t in (
        'A member borrows a book.', 'A librarian returns a book.', 'The system sends reminders.')])
    a = draw(pid, 'use_case', [s1, s2])
    b = draw(pid, 'class', [s2])
    c = draw(pid, 'activity', [s3])
    assert stale(client, pid) == {a: False, b: False, c: False}

    # The hook: only the diagrams that draw the requirement, and nothing for an empty or unknown one.
    assert on_requirement_edited(pid, [s1], USER_ID) == [a]
    assert on_requirement_edited(pid, [], USER_ID) == [] and on_requirement_edited(pid, ['st_nope'], USER_ID) == []
    assert stale(client, pid) == {a: True, b: False, c: False}
    sql('UPDATE diagrams SET out_of_date_at = NULL WHERE project_id = %s', pid)

    # Editing the text marks every diagram that draws it; a label-only edit leaves the drawings alone.
    assert client.patch(f'{API}/projects/{pid}/statements/{s2}', headers=H, json={'text': 'A librarian takes a book back.'}).status_code == 200
    assert stale(client, pid) == {a: True, b: True, c: False}
    assert client.patch(f'{API}/projects/{pid}/statements/{s3}', headers=H, json={'label': 'constraint'}).status_code == 200
    assert stale(client, pid)[c] is False

    # An edited version of an out-of-date diagram is still out of date; of a current one, it is current.
    a2 = draw(pid, 'use_case', [s1, s2], parent=a)
    c2 = draw(pid, 'activity', [s3], parent=c)
    assert stale(client, pid) == {a: True, a2: True, b: True, c: False, c2: False}

    # Regenerating asks nothing of the edit: the log says so only for a type that was out of date.
    sql('UPDATE projects SET confirmed_at = now() WHERE id = %s', pid)
    real_worker = integrated.generation_worker

    async def no_worker(*args):  # the AI is not part of this test; the diagrams are drawn below
        pass
    integrated.generation_worker = no_worker
    try:
        r = client.post(f'{API}/projects/{pid}/generations', headers=H, json={'diagram_types': ['use_case', 'activity', 'sequence']})
    finally:
        integrated.generation_worker = real_worker
    assert r.status_code == 202, r.text
    regenerated = {t: d for a_, t, d in log(pid) if a_ == 'diagram.regenerated'}
    assert regenerated == {'Use Case diagram': {'job_id': r.json()['id'], 'reason': 'requirement_change'},
                           'Activity diagram': {'job_id': r.json()['id']}}, regenerated  # 'sequence' was never drawn

    # The new use case diagram clears the old ones of its type. Class stays out of date: it was not redrawn.
    new_a = draw(pid, 'use_case', [s1, s2])
    assert stale(client, pid) == {a: False, a2: False, new_a: False, b: True, c: False, c2: False}
    # A later edit marks the new drawing too: out of date again, not current forever.
    assert client.patch(f'{API}/projects/{pid}/statements/{s1}', headers=H, json={'text': 'A member borrows two books.'}).status_code == 200
    assert stale(client, pid)[new_a] is True and stale(client, pid)[a] is True  # a older drawing of s1 is marked too

    # Deleting marks what drew it; adding marks nothing (no diagram draws a new requirement).
    assert client.delete(f'{API}/projects/{pid}/statements/{s3}', headers=H).status_code == 204
    assert stale(client, pid)[c] is True
    before = stale(client, pid)
    r = client.post(f'{API}/projects/{pid}/statements', headers=H, json={'text': 'The system prints receipts.'})
    assert r.status_code == 201, r.text
    assert stale(client, pid) == before

    # Applying a suggested fix is an edit too.
    sql('UPDATE diagrams SET out_of_date_at = NULL WHERE project_id = %s', pid)
    db.save_flags(pid, [{'statement_id': s2, 'type': 'ambiguous', 'reason': 'Vague.', 'suggested_fix': 'A librarian returns a book within a day.'}], [s2])
    flag = client.get(f'{API}/projects/{pid}/flags', headers=H).json()[0]
    assert client.post(f'{API}/projects/{pid}/flags/{flag["id"]}/apply-fix', headers=H).status_code == 200
    assert stale(client, pid)[b] is True and stale(client, pid)[c] is False

    # The log holds the reference and revision only, never the text.
    actions = [a_ for a_, _, _ in log(pid)]
    assert actions.count('statement.edited') >= 3 and 'statement.deleted' in actions and 'statement.added' in actions
    assert not any('librarian' in str(t).lower() or 'member' in str(t).lower() for _, t, _ in log(pid))
    assert ('statement.deleted', 'R-003', None) in log(pid)


def main():
    db.init_db()
    quality.httpx.post = lambda url, json=None, timeout=None, headers=None: httpx.Response(
        200, json={'flags': []}, request=httpx.Request('POST', url))  # the checker finds nothing
    try:
        with TestClient(app) as client:
            check(client)
        print('out of date test passed')
    finally:
        sql('DELETE FROM activity_log WHERE actor_id = %s', USER_ID)
        sql('DELETE FROM projects WHERE owner_id = %s', USER_ID)
        sql('DELETE FROM users WHERE id = %s', USER_ID)


if __name__ == '__main__':
    main()
