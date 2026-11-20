"""Stories backlog (3.4): user stories linked to requirements, with S-numbers, an assignee from the project's members
and encrypted text.

Runs against the Postgres in DATABASE_URL with no AI calls (requirements are written straight to the database). Uses
throwaway users and deletes what it creates. Run: python tests_stories.py
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
from core.crypto import PREFIX  # noqa: E402
from main import app  # noqa: E402

API = '/api/v1'
OWNER, MEMBER, STRANGER = (f'sto-{uuid.uuid4().hex[:8]}@example.com' for _ in range(3))
OWNER_ID, MEMBER_ID, STRANGER_ID = (f'dev:{e}' for e in (OWNER, MEMBER, STRANGER))
owner = {'Authorization': f'Bearer mock-token:{OWNER}'}
member = {'Authorization': f'Bearer mock-token:{MEMBER}'}
stranger = {'Authorization': f'Bearer mock-token:{STRANGER}'}
SECRET = f'Okapi{uuid.uuid4().hex}'  # must never show up in the database as plain text


def sql(query, *args):
    with psycopg.connect(os.environ['DATABASE_URL'], prepare_threshold=None) as c:
        return c.execute(query, args).fetchall() if query.startswith('SELECT') else c.execute(query, args)


def new_project(client, name):
    r = client.post(f'{API}/projects', headers=owner, json={'name': name})
    assert r.status_code == 201, r.text
    pid = r.json()['id']
    sql('INSERT INTO project_members(project_id, user_id, role) VALUES (%s, %s, %s)', pid, MEMBER_ID, 'editor')  # not an Owner
    return pid, db.insert_statements(pid, [{'text': f'The clinic handles case {i}.'} for i in range(1, 4)])


def story(sids, **extra):
    return {'role': ' receptionist ', 'goal': 'book a visit', 'reason': 'patients are seen on time',
            'statement_ids': sids, **extra}


def check(client):
    for email, user_id in ((OWNER, OWNER_ID), (MEMBER, MEMBER_ID), (STRANGER, STRANGER_ID)):
        db.get_user(email, user_id)  # what a real sign-in stores (the mock tokens skip it): the members' emails
    pid, sids = new_project(client, 'Stories project')
    other_pid, other_sids = new_project(client, 'Other stories project')
    url = f'{API}/projects/{pid}/stories'

    # Create with two requirements; defaults apply; GET lists it with the members for the assignee picker.
    r = client.post(url, headers=owner, json=story([sids[0], sids[1], sids[0]]))
    assert r.status_code == 201, r.text
    s = r.json()
    assert (s['ref'], s['role'], s['priority'], s['estimate'], s['status'], s['assignee_id'], s['assignee_email'],
            s['confirmations'], s['statement_ids']) == \
        ('S-001', 'receptionist', 'should', None, 'todo', None, None, [], sids[:2]), s
    assert s['created_at'] and s['updated_at']
    got = client.get(url, headers=member).json()
    assert got['stories'] == [s], got
    assert {(m['id'], m['email']) for m in got['members']} == {(OWNER_ID, OWNER), (MEMBER_ID, MEMBER)}, got['members']

    # Validation.
    bad = [story([]), story([other_sids[0]]), story([sids[0], other_sids[0]]), story(sids[:1], role='   '),
           story(sids[:1], goal='x' * 301), story(sids[:1], assignee_id=STRANGER_ID), story(sids[:1], priority='high'),
           story(sids[:1], status='blocked'), story(sids[:1], estimate=101), story(sids[:1], estimate=-1),
           story(sids[:1], confirmations=['ok', 'x' * 501]), story(sids[:1], confirmations=['c'] * 21)]
    for body in bad:
        r = client.post(url, headers=owner, json=body)
        assert r.status_code == 422, (body, r.text)
    r = client.post(url, headers=owner, json=story([]))
    assert r.json()['detail'] == 'A story must link to at least one requirement.', r.text
    assert len(client.get(url, headers=owner).json()['stories']) == 1  # nothing was stored

    # A non-owner member creates and edits.
    r = client.post(url, headers=member, json=story(sids[2:], priority='must', estimate=5, assignee_id=OWNER_ID,
                                                    confirmations=[' Shows free slots ', '  ', 'Sends a reminder']))
    assert r.status_code == 201, r.text
    s2 = r.json()
    assert (s2['ref'], s2['priority'], s2['estimate'], s2['assignee_email'], s2['confirmations']) == \
        ('S-002', 'must', 5, OWNER, ['Shows free slots', 'Sends a reminder']), s2
    r = client.patch(f'{url}/{s2["id"]}', headers=member,
                     json={'status': 'in_progress', 'priority': 'wont', 'assignee_id': MEMBER_ID,
                           'confirmations': ['Only one'], 'statement_ids': [sids[1], sids[2]]})
    assert r.status_code == 200, r.text
    p = r.json()
    assert (p['status'], p['priority'], p['assignee_id'], p['assignee_email'], p['confirmations'], p['statement_ids'],
            p['estimate'], p['role'], p['goal'], p['reason'], p['ref']) == \
        ('in_progress', 'wont', MEMBER_ID, MEMBER, ['Only one'], sids[1:], 5, 'receptionist', 'book a visit',
         'patients are seen on time', 'S-002'), p
    r = client.patch(f'{url}/{s2["id"]}', headers=owner, json={'assignee_id': None, 'estimate': None})
    p = r.json()
    assert (p['assignee_id'], p['assignee_email'], p['estimate'], p['status']) == (None, None, None, 'in_progress'), p
    for body in ({'statement_ids': []}, {'statement_ids': [other_sids[0]]}, {'assignee_id': STRANGER_ID},
                 {'role': ''}, {'role': None}, {'status': None}, {'estimate': 101}, {'priority': 'high'}):
        r = client.patch(f'{url}/{s2["id"]}', headers=owner, json=body)
        assert r.status_code == 422, (body, r.text)
    assert client.get(url, headers=owner).json()['stories'][1] == p  # the refused edits changed nothing

    # A story of another project, or an unknown one, is the standard 404.
    other = client.post(f'{API}/projects/{other_pid}/stories', headers=owner, json=story(other_sids[:1])).json()
    foreign = client.get(f'{API}/projects/{pid}', headers=stranger)
    for method in ('PATCH', 'DELETE'):
        for sid in (other['id'], f'us_{uuid.uuid4().hex}'):
            r = client.request(method, f'{url}/{sid}', headers=owner, json={'status': 'done'})
            assert (r.status_code, r.json()) == (404, foreign.json()), r.text
    assert other['ref'] == 'S-001'  # numbering is per project

    # An outsider gets the same 404 on all four routes.
    for method, path, body in (('GET', url, None), ('POST', url, story(sids[:1])),
                               ('PATCH', f'{url}/{s["id"]}', {'status': 'done'}), ('DELETE', f'{url}/{s["id"]}', None)):
        r = client.request(method, path, headers=stranger, json=body)
        assert (r.status_code, r.json()) == (404, foreign.json()), (method, r.text)

    # Delete S-001, create another: it is S-003, not a reused S-001.
    assert client.delete(f'{url}/{s["id"]}', headers=member).status_code == 204
    assert client.delete(f'{url}/{s["id"]}', headers=member).status_code == 404
    r = client.post(url, headers=owner, json=story(sids[:1], role=SECRET, goal=SECRET, reason=SECRET,
                                                   confirmations=[SECRET]))
    assert r.json()['ref'] == 'S-003', r.text
    assert [x['ref'] for x in client.get(url, headers=owner).json()['stories']] == ['S-002', 'S-003']

    # Deleting a linked requirement drops only that link; a story left with none stays, with no links.
    assert client.delete(f'{API}/projects/{pid}/statements/{sids[1]}', headers=owner).status_code == 204
    assert client.delete(f'{API}/projects/{pid}/statements/{sids[0]}', headers=owner).status_code == 204
    left = {x['ref']: x['statement_ids'] for x in client.get(url, headers=owner).json()['stories']}
    assert left == {'S-002': [sids[2]], 'S-003': []}, left

    # The text is stored encrypted; ids, refs and enums are plain.
    rows = sql('SELECT role_text, goal_text, reason_text, confirmations, ref, priority FROM stories WHERE project_id=%s', pid)
    for row in rows:
        for value in row[:4]:
            assert value.startswith(PREFIX) and SECRET not in value and 'receptionist' not in value, row
    assert sorted(r[4] for r in rows) == ['S-002', 'S-003']

    # Deleting the project removes its stories, their links and the counter.
    assert client.request('DELETE', f'{API}/projects/{pid}', headers=owner,
                          json={'confirm_name': 'Stories project'}).status_code == 204
    assert sql('SELECT count(*) FROM stories WHERE project_id=%s', pid)[0][0] == 0
    assert sql('SELECT count(*) FROM story_counters WHERE project_id=%s', pid)[0][0] == 0
    assert sql('SELECT count(*) FROM story_statements WHERE story_id = ANY(%s)', [s2['id']])[0][0] == 0


def main():
    try:
        with TestClient(app) as client:
            check(client)
        print('stories backlog test passed')
    finally:
        sql('DELETE FROM projects WHERE owner_id = ANY(%s)', [OWNER_ID, MEMBER_ID, STRANGER_ID])
        sql('DELETE FROM users WHERE id = ANY(%s)', [OWNER_ID, MEMBER_ID, STRANGER_ID])


if __name__ == '__main__':
    main()
