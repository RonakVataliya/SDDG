"""Integration test for System Design (Feature 4) group 1: the design sections and 4.1 design goals, run against the
Postgres in DATABASE_URL.

The AI draft (POST /design/goals) is faked; POST /design/derive is answered with the AI
service's real plain-code modules, as tests_testing.py does for the black-box engine. Uses a throwaway user and deletes
everything it created. Run: python tests_design.py
"""
import importlib.util
import json
import os
import uuid
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv()
os.environ['DEV_AUTH_BYPASS'] = 'true'

from fastapi.testclient import TestClient  # noqa: E402
import routers.integrated as integrated  # noqa: E402
import tests_integration  # noqa: E402
from core import db  # noqa: E402
from core.crypto import PREFIX  # noqa: E402
from main import app  # noqa: E402
from routers import design  # noqa: E402

EMAIL = f'dz-{uuid.uuid4().hex[:8]}@example.com'
OTHER = f'dz-{uuid.uuid4().hex[:8]}@example.com'
H = {'Authorization': f'Bearer mock-token:{EMAIL}'}
THEIRS = {'Authorization': f'Bearer mock-token:{OTHER}'}
SECRET = f'Okapi{uuid.uuid4().hex}'
API = '/api/v1'

_spec = importlib.util.spec_from_file_location(
    'services_design_goals', Path(__file__).resolve().parents[2] / 'services/ai-extraction/app/design/goals.py')
GOALS = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(GOALS)

DERIVE = {'goals': lambda content, model: GOALS.derive_goals(content)}
AI = {'goals': 0, 'derive': 0, 'down': False}


def unavailable(url):
    return integrated.httpx.Response(503, json={'detail': 'AI service is not available.'},
                                     request=integrated.httpx.Request('POST', url))


class FakeDesignAI(tests_integration.FakeAIClient):
    async def post(self, url, **kwargs):
        body = kwargs.get('json') or {}
        if AI['down']:
            return unavailable(url)
        if url.endswith('/design/goals'):
            AI['goals'] += 1
            ids = [r['id'] for r in body['requirements']]
            return tests_integration.FakeResponse({'goals': [
                {'name': 'Reliability', 'reason': f'{SECRET} bookings must not be lost.', 'statement_ids': ids[:1]},
                {'name': 'Efficiency', 'reason': 'Pages answer in 2 s.', 'statement_ids': ids[1:2]},
                {'name': 'Portability', 'reason': 'Runs on phones and desktops.', 'statement_ids': ids[:1]},
            ], 'errors': [], 'metadata': {}})
        if url.endswith('/design/derive'):
            AI['derive'] += 1
            return tests_integration.FakeResponse(DERIVE[body['kind']](body['content'], body.get('model')))
        return await super().post(url, **kwargs)




def sql(query, *args):
    with psycopg.connect(os.environ['DATABASE_URL'], prepare_threshold=None) as c:
        return c.execute(query, args).fetchall() if query.lstrip().startswith('SELECT') else c.execute(query, args)


def goals_section(c, pid, headers=H):
    r = c.get(f'{API}/projects/{pid}/design', headers=headers)
    assert r.status_code == 200, r.text
    return r.json()['sections'][0]


def check(c):
    assert design.GOAL_NAMES == tuple(GOALS.VOCABULARY)  # the API's copy of the vocabulary matches the AI service's
    pid = c.post(f'{API}/projects', headers=H, json={'name': 'Design feature'}).json()['id']
    d = f'{API}/projects/{pid}/design'
    r1, r2 = db.insert_statements(pid, [{'text': 'Patients book appointments online.'},
                                        {'text': 'The booking page answers within 2 seconds.'}])

    # A fresh project: the goals section is empty and open; an unknown kind is the standard 404.
    fresh = goals_section(c, pid)
    assert fresh == {'kind': 'goals', 'title': 'Design goals', 'status': 'empty', 'version': 0, 'content': None,
                     'derived': None, 'stale': False, 'locked': False, 'job': None, 'updated_at': None}, fresh
    for method, path in (('POST', '/nope/draft-jobs'), ('PUT', '/nope'), ('POST', '/nope/confirm')):
        r = c.request(method, f'{d}{path}', headers=H, json={'content': {}})
        assert (r.status_code, r.json()['detail']) == (404, integrated.NOT_FOUND), (path, r.text)

    # The AI draft needs consent and confirmed requirements.
    assert c.post(f'{d}/goals/draft-jobs', headers=H).status_code == 403
    c.post(f'{API}/me/consent', headers=H, json={'policy_version': integrated.POLICY_VERSION})
    refused = c.post(f'{d}/goals/draft-jobs', headers=H)
    assert (refused.status_code, refused.json()) == (409, {'detail': 'Confirm the requirements first.'}), refused.text
    assert AI['goals'] == 0
    assert c.post(f'{API}/projects/{pid}/confirmation', headers=H).status_code == 201

    # The draft job stores a draft with its derived values, version 1.
    job = c.post(f'{d}/goals/draft-jobs', headers=H)
    assert job.status_code == 202 and job.json()['kind'] == 'design_goals', job.text
    assert c.get(f'{API}/jobs/{job.json()["id"]}', headers=H).json()['status'] == 'succeeded'
    drafted = goals_section(c, pid)
    assert (drafted['status'], drafted['version'], drafted['stale']) == ('draft', 1, False), drafted
    assert [g['name'] for g in drafted['content']['goals']] == ['Reliability', 'Efficiency', 'Portability']
    assert drafted['derived']['groups']['end_user'] == ['Reliability', 'Efficiency']
    assert drafted['derived']['conflicts'] == [
        {'a': 'Efficiency', 'b': 'Portability', 'pair': 'Efficiency vs. Portability (or Modifiability)'}]
    assert drafted['job']['id'] == job.json()['id'] and drafted['job']['status'] == 'succeeded'
    assert (AI['goals'], AI['derive']) == (1, 1), AI

    # PUT validation: one readable string per refusal, nothing stored.
    other = c.post(f'{API}/projects', headers=THEIRS, json={'name': 'Other'}).json()['id']
    (foreign,) = db.insert_statements(other, [{'text': 'Someone else.'}])

    def goal(name='Reliability', reason='', sids=()):
        return {'name': name, 'reason': reason, 'statement_ids': list(sids)}

    bad = {
        'unknown goal': ([goal('Speed')], 'Unknown design goal: Speed.'),
        'duplicate goal': ([goal(), goal()], 'Each design goal can be chosen only once: Reliability.'),
        'foreign statement': ([goal(sids=[foreign])], 'A design goal can only cite requirements of this project.'),
        'too many': ([goal(n) for n in GOALS.VOCABULARY] + [goal('Reliability')], 'Choose 1 to 28 design goals.'),
        'none': ([], 'Choose 1 to 28 design goals.'),
        'reason too long': ([goal(reason='x' * 301)], 'A reason can be at most 300 characters.'),
    }
    for label, (goals, message) in bad.items():
        r = c.put(f'{d}/goals', headers=H, json={'content': {'goals': goals}})
        assert (r.status_code, r.json()) == (422, {'detail': message}), (label, r.text)
    shape = c.put(f'{d}/goals', headers=H, json={'content': {'goals': 'Reliability'}})
    assert shape.status_code == 422 and isinstance(shape.json()['detail'], str), shape.text
    assert goals_section(c, pid)['version'] == 1

    # PUT stores (reason trimmed, citations de-duplicated) and bumps the version; derived comes back with it.
    content = {'goals': [goal('Reliability', '  Bookings must not be lost.  ', [r1, r1]),
                         goal('Maintainability', 'Small team.', [])]}
    saved = c.put(f'{d}/goals', headers=H, json={'content': content})
    assert saved.status_code == 200, saved.text
    saved = saved.json()
    assert (saved['status'], saved['version']) == ('draft', 2)
    assert saved['content']['goals'][0] == goal('Reliability', 'Bookings must not be lost.', [r1])
    assert saved['derived']['groups']['other'] == ['Maintainability'] and saved['derived']['conflicts'] == []

    # Confirm is refused while a goal cites nothing, then succeeds.
    r = c.post(f'{d}/goals/confirm', headers=H)
    assert (r.status_code, r.json()) == (422, {'detail': 'Every design goal must cite at least one requirement: '
                                                          'Maintainability.'}), r.text
    content['goals'][1]['statement_ids'] = [r2]
    c.put(f'{d}/goals', headers=H, json={'content': content})
    confirmed = c.post(f'{d}/goals/confirm', headers=H)
    assert confirmed.status_code == 200 and confirmed.json()['status'] == 'confirmed', confirmed.text
    assert confirmed.json()['version'] == 3
    print('GET /projects/{id}/design (confirmed goals):')
    print(json.dumps(c.get(d, headers=H).json(), indent=2))

    # Editing a cited requirement makes the section stale; confirm is refused while stale; saving again clears it.
    c.patch(f'{API}/projects/{pid}/statements/{r2}', headers=H, json={'text': 'The booking page answers within 1 s.'})
    stale = goals_section(c, pid)
    assert stale['stale'] and stale['status'] == 'confirmed', stale
    r = c.post(f'{d}/goals/confirm', headers=H)
    assert (r.status_code, r.json()) == (422, {'detail': 'A requirement this section cites has changed. Review the '
                                                          'section and save it again.'}), r.text
    again = c.put(f'{d}/goals', headers=H, json={'content': content}).json()
    assert not again['stale'] and again['status'] == 'draft'
    # Deleting a cited requirement makes it stale too.
    assert c.delete(f'{API}/projects/{pid}/statements/{r2}', headers=H).status_code == 204
    assert goals_section(c, pid)['stale']

    # Confirm on an empty section.
    pid2 = c.post(f'{API}/projects', headers=H, json={'name': 'Empty design'}).json()['id']
    r = c.post(f'{API}/projects/{pid2}/design/goals/confirm', headers=H)
    assert (r.status_code, r.json()) == (422, {'detail': 'Write or draft the design goals first.'}), r.text

    # A second draft job while one is running is refused.
    db.insert_statements(pid2, [{'text': 'Clerks print invoices.'}])
    c.post(f'{API}/projects/{pid2}/confirmation', headers=H)
    running = db.create_job(pid2, 'design_goals', 3, 'Queued')
    r = c.post(f'{API}/projects/{pid2}/design/goals/draft-jobs', headers=H)
    assert (r.status_code, r.json()) == (409, {'detail': 'A draft of this section is already running.'}), r.text
    assert goals_section(c, pid2)['job']['id'] == running['id']
    db.update_job(running['id'], status='failed')

    # AI service down: the PUT gives the readable 503 and stores nothing; a draft job fails with the reason.
    AI['down'] = True
    before = goals_section(c, pid2)
    r = c.put(f'{API}/projects/{pid2}/design/goals', headers=H, json={'content': {'goals': [goal()]}})
    assert (r.status_code, r.json()) == (503, {'detail': "Couldn't save the design goals: AI service is not "
                                                          "available."}), r.text
    failed = c.post(f'{API}/projects/{pid2}/design/goals/draft-jobs', headers=H).json()
    failed = c.get(f'{API}/jobs/{failed["id"]}', headers=H).json()
    assert failed['status'] == 'failed' and failed['error'] == 'Drafting failed: AI service is not available.', failed
    after = goals_section(c, pid2)
    assert (after['status'], after['version'], after['content']) == (before['status'], 0, None)
    AI['down'] = False

    # Access: an outsider gets the standard 404 on all four routes; a member who is not the owner may use them.
    routes = (('GET', d), ('POST', f'{d}/goals/draft-jobs'), ('PUT', f'{d}/goals'), ('POST', f'{d}/goals/confirm'))
    for method, url in routes:
        r = c.request(method, url, headers=THEIRS, json={'content': content})
        assert (r.status_code, r.json()['detail']) == (404, integrated.NOT_FOUND), (method, url, r.text)
    sql('INSERT INTO project_members(project_id, user_id) VALUES (%s, %s)', pid, f'dev:{OTHER}')
    assert goals_section(c, pid, THEIRS)['version'] == 4
    content['goals'][1]['statement_ids'] = [r1]
    assert c.put(f'{d}/goals', headers=THEIRS, json={'content': content}).json()['version'] == 5
    assert c.post(f'{d}/goals/confirm', headers=THEIRS).json()['status'] == 'confirmed'

    # The stored content is encrypted.
    stored = sql('SELECT section_content FROM design_sections WHERE project_id=%s', pid)
    assert stored and all(v.startswith(PREFIX) and 'Reliability' not in v for (v,) in stored)
    first = sql('SELECT section_content FROM design_sections WHERE project_id=%s', pid2)
    assert first == []




def main():
    original = integrated.httpx.AsyncClient
    integrated.httpx.AsyncClient = FakeDesignAI
    try:
        with TestClient(app) as client:
            check(client)
        print('design sections integration test passed')
    finally:
        integrated.httpx.AsyncClient = original
        with psycopg.connect(os.environ['DATABASE_URL'], prepare_threshold=None) as c:
            for e in (EMAIL, OTHER):
                c.execute('DELETE FROM projects WHERE owner_id=%s', (f'dev:{e}',))
                c.execute('DELETE FROM consents WHERE user_id=%s', (f'dev:{e}',))


if __name__ == '__main__':
    main()
