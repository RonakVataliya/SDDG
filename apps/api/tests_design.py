"""Integration test for System Design (Feature 4) group 1: the design sections, 4.1 design goals and 4.2 subsystem
decomposition (with its stored package diagram), run against the Postgres in DATABASE_URL.

The AI drafts (POST /design/goals, /design/decompose) and Kroki are faked; POST /design/derive is answered with the AI
service's real plain-code modules, as tests_testing.py does for the black-box engine. Uses a throwaway user and deletes
everything it created. Run: python tests_design.py
"""
import importlib.util
import io
import json
import os
import sys
import uuid
import zipfile
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
sys.path.append(str(Path(__file__).resolve().parents[2] / 'services/ai-extraction'))  # decomposition uses its escaping
from app.design.decomposition import derive_decomposition  # noqa: E402

DERIVE = {'goals': lambda content, model: GOALS.derive_goals(content), 'decomposition': derive_decomposition}
AI = {'goals': 0, 'derive': 0, 'down': False, 'decompose': [], 'kroki_down': False}


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
        if url.endswith('/design/decompose'):
            AI['decompose'].append(body)
            ids = [r['id'] for r in body['requirements']]
            return tests_integration.FakeResponse({'architecture': 'closed', 'subsystems': [
                subsystem('web-ui', 'Web interface', 1, depends_on=['booking'], sids=ids[:1]),
                subsystem('booking', 'Booking', 2, ['Patient', 'Appointment'], sids=ids[:2],
                          description=f'{SECRET} books appointments.'),
            ], 'errors': [], 'metadata': {}})
        if '/plantuml/' in url and AI['kroki_down']:
            raise integrated.httpx.ConnectError('Kroki is down', request=integrated.httpx.Request('POST', url))
        return await super().post(url, **kwargs)


def subsystem(sid, name, layer, classes=(), depends_on=(), sids=(), description=''):
    return {'id': sid, 'name': name, 'description': description, 'layer': layer,
            'services': [{'name': f'{name} services', 'operations': ['open']}], 'classes': list(classes),
            'depends_on': list(depends_on), 'statement_ids': list(sids)}


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


def section(c, pid, kind):
    r = c.get(f'{API}/projects/{pid}/design', headers=H)
    assert r.status_code == 200, r.text
    return next(s for s in r.json()['sections'] if s['kind'] == kind)


def package_diagrams(c, pid):
    return [d for d in c.get(f'{API}/projects/{pid}/diagrams', headers=H).json() if d['type'] == 'package']


def check_decomposition(c):
    pid = c.post(f'{API}/projects', headers=H, json={'name': 'Clinic'}).json()['id']
    d = f'{API}/projects/{pid}/design'
    r1, r2 = db.insert_statements(pid, [{'text': 'Patients book appointments online.'},
                                        {'text': 'Patients pay invoices online.'}])
    assert c.post(f'{API}/projects/{pid}/confirmation', headers=H).status_code == 201
    items = {n: db.uid('it') for n in ('Patient', 'Appointment', 'Invoice', 'Receptionist', 'Book appointment')}
    item = lambda n, cat, s=None, t=None: {'id': items.get(n, db.uid('it')), 'category': cat, 'name': n,  # noqa: E731
                                           'description': None, 'statement_ids': [r1], 'source_item_id': s,
                                           'target_item_id': t}
    db.add_system_items(pid, [item('Patient', 'entity'), item('Appointment', 'entity'), item('Invoice', 'entity'),
                              item('Receptionist', 'actor'), item('Book appointment', 'process'),
                              item('has', 'relationship', items['Patient'], items['Appointment'])])

    # Locked until the design goals are confirmed.
    locked = section(c, pid, 'decomposition')
    assert (locked['title'], locked['status'], locked['locked']) == ('Subsystem decomposition', 'empty', True), locked
    for method, path in (('POST', '/decomposition/draft-jobs'), ('PUT', '/decomposition'),
                         ('POST', '/decomposition/confirm')):
        r = c.request(method, f'{d}{path}', headers=H, json={'content': {}})
        assert (r.status_code, r.json()) == (409, {'detail': 'Confirm Design goals first.'}), (path, r.text)
    goals = {'goals': [{'name': 'Reliability', 'reason': '', 'statement_ids': [r1]}]}
    assert c.put(f'{d}/goals', headers=H, json={'content': goals}).status_code == 200
    assert c.post(f'{d}/goals/confirm', headers=H).status_code == 200
    assert not section(c, pid, 'decomposition')['locked']

    # The draft job sends the requirements and the extracted model, and stores a draft with its derived values.
    job = c.post(f'{d}/decomposition/draft-jobs', headers=H)
    assert job.status_code == 202 and job.json()['kind'] == 'design_decomposition', job.text
    assert c.get(f'{API}/jobs/{job.json()["id"]}', headers=H).json()['status'] == 'succeeded'
    sent = AI['decompose'][-1]
    assert [r['id'] for r in sent['requirements']] == [r1, r2]
    model = {'classes': ['Patient', 'Appointment', 'Invoice'],
             'relations': [{'source': 'Patient', 'target': 'Appointment'}],
             'use_cases': ['Book appointment'], 'actors': ['Receptionist']}
    assert sent['model'] == model, sent['model']
    drafted = section(c, pid, 'decomposition')
    assert (drafted['status'], drafted['version'], drafted['stale']) == ('draft', 1, False), drafted
    assert [s['id'] for s in drafted['content']['subsystems']] == ['web-ui', 'booking']
    derived = drafted['derived']
    assert derived['subsystems'] == [{'id': 'web-ui', 'cohesion': None, 'coupling': 1},
                                     {'id': 'booking', 'cohesion': 1.0, 'coupling': 1}], derived
    assert derived['cohesion'] == 1.0
    assert [w['code'] for w in derived['warnings']] == ['unassigned_class']
    assert 'Invoice' in derived['warnings'][0]['message']
    assert '"Booking" as booking' in derived['package_diagram']
    assert package_diagrams(c, pid) == []  # the diagram is stored on confirm, not on draft

    # PUT validation: one readable string per refusal, nothing stored.
    other = c.post(f'{API}/projects', headers=THEIRS, json={'name': 'Other clinic'}).json()['id']
    (foreign,) = db.insert_statements(other, [{'text': 'Someone else.'}])
    ui = lambda **kw: {**subsystem('web-ui', 'Web interface', 1, sids=[r1]), **kw}  # noqa: E731
    core = lambda **kw: {**subsystem('booking', 'Booking', 2, ['Patient'], sids=[r1]), **kw}  # noqa: E731
    bad = {
        'none': ([], 'Define 1 to 20 subsystems.'),
        'too many': ([ui(id=f's{n}', name=f'S{n}') for n in range(21)], 'Define 1 to 20 subsystems.'),
        'duplicate id': ([ui(), core(id='web-ui')], 'Each subsystem id can be used only once: web-ui.'),
        'duplicate name': ([ui(), core(name='Web interface')],
                           'Each subsystem name can be used only once: Web interface.'),
        'unknown depends_on': ([ui(depends_on=['nope']), core()], 'Unknown subsystem in depends_on: nope.'),
        'self dependency': ([ui(), core(depends_on=['booking'])], 'A subsystem cannot depend on itself: booking.'),
        'class owned twice': ([ui(classes=['Patient']), core()], 'A class can belong to only one subsystem: Patient.'),
        'name too long': ([ui(name='x' * 81)], 'A subsystem name must be 1 to 80 characters.'),
        'empty name': ([ui(name='  ')], 'A subsystem name must be 1 to 80 characters.'),
        'description too long': ([ui(description='x' * 501)], 'A description can be at most 500 characters.'),
        'service name': ([ui(services=[{'name': '', 'operations': []}])],
                         'Service and operation names must be 1 to 120 characters.'),
        'operation name': ([ui(services=[{'name': 'S', 'operations': ['x' * 121]}])],
                           'Service and operation names must be 1 to 120 characters.'),
        'bad id': ([ui(id='Web UI')], 'A subsystem id must be a short slug: lowercase letters, digits and hyphens, '
                                      'at most 40 characters.'),
        'bad layer': ([ui(layer=0)], "A subsystem's layer must be a whole number, 1 for the top layer."),
        'foreign statement': ([ui(statement_ids=[foreign])], 'A subsystem can only cite requirements of this project.'),
    }
    for label, (subs, message) in bad.items():
        r = c.put(f'{d}/decomposition', headers=H, json={'content': {'architecture': 'closed', 'subsystems': subs}})
        assert (r.status_code, r.json()) == (422, {'detail': message}), (label, r.text)
    for content in ({'architecture': 'layered', 'subsystems': [ui()]}, {'architecture': 'open', 'subsystems': 'x'},
                    {'architecture': 'open', 'subsystems': [ui(classes='Patient')]}):
        r = c.put(f'{d}/decomposition', headers=H, json={'content': content})
        assert (r.status_code, r.json()) == (422, {'detail': 'The subsystem decomposition is not in the expected '
                                                             'form.'}), r.text
    assert section(c, pid, 'decomposition')['version'] == 1

    # An upward dependency is saved and reported as a warning, not refused; text is trimmed, duplicates dropped.
    content = {'architecture': 'closed', 'subsystems': [
        ui(name=' Web interface ', depends_on=['booking', 'booking']),
        core(classes=['Patient', 'Appointment'], depends_on=['web-ui'], statement_ids=[]),
    ]}
    saved = c.put(f'{d}/decomposition', headers=H, json={'content': content})
    assert saved.status_code == 200, saved.text
    saved = saved.json()
    assert (saved['status'], saved['version']) == ('draft', 2)
    assert saved['content']['subsystems'][0]['name'] == 'Web interface'
    assert saved['content']['subsystems'][0]['depends_on'] == ['booking']
    assert [w['code'] for w in saved['derived']['warnings']] == ['upward_dependency', 'unassigned_class']
    assert saved['derived']['warnings'][0]['subsystem_ids'] == ['booking', 'web-ui']
    assert '#red' in saved['derived']['package_diagram']

    # Confirm is refused while a subsystem cites nothing, then succeeds and stores the package diagram.
    r = c.post(f'{d}/decomposition/confirm', headers=H)
    assert (r.status_code, r.json()) == (422, {'detail': 'Every subsystem must cite at least one requirement: '
                                                          'Booking.'}), r.text
    content['subsystems'][1]['statement_ids'] = [r2]
    content['subsystems'][1]['depends_on'] = []
    assert c.put(f'{d}/decomposition', headers=H, json={'content': content}).status_code == 200
    confirmed = c.post(f'{d}/decomposition/confirm', headers=H)
    assert confirmed.status_code == 200 and confirmed.json()['status'] == 'confirmed', confirmed.text
    (stored,) = package_diagrams(c, pid)
    assert stored['title'] == 'Clinic · Package', stored
    diagram = c.get(f'{API}/diagrams/{stored["id"]}', headers=H).json()
    assert sorted(s['id'] for s in diagram['statements']) == sorted([r1, r2])
    assert diagram['plantuml_source'] == confirmed.json()['derived']['package_diagram']
    assert diagram['svg'].startswith('<svg')
    assert [(e['element_id'], e['kind'], e['statement_ids']) for e in diagram['elements']] == [
        ('web-ui', 'package', [r1]), ('booking', 'package', [r2])]
    print('GET /projects/{id}/design (confirmed decomposition):')
    print(json.dumps(c.get(d, headers=H).json()['sections'][1], indent=2))

    # Confirming again without a change stores nothing new; a changed, re-confirmed section adds a version.
    assert c.post(f'{d}/decomposition/confirm', headers=H).status_code == 200
    assert len(package_diagrams(c, pid)) == 1
    content['architecture'] = 'open'
    assert c.put(f'{d}/decomposition', headers=H, json={'content': content}).json()['status'] == 'draft'
    assert c.post(f'{d}/decomposition/confirm', headers=H).status_code == 200
    versions = package_diagrams(c, pid)
    assert len(versions) == 2 and versions[0]['title'] == versions[1]['title'] and not versions[0]['parent_id']

    # Kroki down: the confirm fails readably and the section stays a draft without a new diagram.
    content['architecture'] = 'closed'
    c.put(f'{d}/decomposition', headers=H, json={'content': content})
    AI['kroki_down'] = True
    r = c.post(f'{d}/decomposition/confirm', headers=H)
    AI['kroki_down'] = False
    assert (r.status_code, r.json()) == (424, {'detail': "Couldn't confirm the subsystem decomposition: the diagram "
                                                          "renderer is unavailable. Try again in a minute."}), r.text
    assert section(c, pid, 'decomposition')['status'] == 'draft' and len(package_diagrams(c, pid)) == 2

    # The stored diagram is viewed and exported through the existing routes; what does not apply answers a 4xx.
    did = versions[0]['id']
    source = c.get(f'{API}/diagrams/{did}/export?format=source', headers=H)
    assert source.status_code == 200 and source.text.startswith('@startuml'), source.text
    for fmt in ('png', 'svg', 'pdf'):
        assert c.get(f'{API}/diagrams/{did}/export?format={fmt}', headers=H).status_code == 200, fmt
    archive = c.get(f'{API}/projects/{pid}/diagrams/export?versions=latest', headers=H)
    assert archive.status_code == 200
    assert 'clinic-package.puml' in zipfile.ZipFile(io.BytesIO(archive.content)).namelist()
    assert c.get(f'{API}/projects/{pid}/coverage', headers=H).json()['with_diagrams'] == 2
    assert 'Clinic · Package' in c.get(f'{API}/projects/{pid}/report.html', headers=H).text
    r = c.post(f'{API}/diagrams/{did}/revisions', headers=H, json={'instruction': 'Add a layer.'})
    assert (r.status_code, r.json()) == (422, {'detail': 'Editing is not available for this diagram type.'}), r.text
    arranging = ('Arranging is not available for package diagrams. Change the subsystem decomposition in the Design '
                 'step.')
    r = c.get(f'{API}/diagrams/{did}/layout', headers=H)
    assert (r.status_code, r.json()) == (422, {'detail': arranging}), r.text
    r = c.post(f'{API}/diagrams/{did}/layout', headers=H, json={'positions': {'web-ui': {'x': 1, 'y': 2}}})
    assert (r.status_code, r.json()) == (422, {'detail': arranging}), r.text
    v = c.get(f'{API}/diagrams/{did}/validation', headers=H)
    assert v.status_code == 200 and v.json()['warnings'] == [], v.text
    r = c.post(f'{API}/projects/{pid}/generations', headers=H, json={'diagram_types': ['package']})
    assert r.status_code == 422, r.text

    # Renaming a class of the extracted model makes the decomposition stale (its derived values read the model);
    # the goals do not read it, so they stay fresh.
    assert c.post(f'{d}/decomposition/confirm', headers=H).status_code == 200
    assert not section(c, pid, 'decomposition')['stale']
    r = c.patch(f'{API}/projects/{pid}/items/{items["Invoice"]}', headers=H, json={'name': 'Bill'})
    assert r.status_code == 200, r.text
    assert section(c, pid, 'decomposition')['stale'] and not section(c, pid, 'goals')['stale']
    c.patch(f'{API}/projects/{pid}/items/{items["Invoice"]}', headers=H, json={'name': 'Invoice'})
    assert not section(c, pid, 'decomposition')['stale']

    # Saving the goals again sends the confirmed decomposition, built on the old goals, back to draft.
    assert section(c, pid, 'decomposition')['status'] == 'confirmed'
    assert c.put(f'{d}/goals', headers=H, json={'content': goals}).status_code == 200
    assert section(c, pid, 'goals')['status'] == 'draft' and section(c, pid, 'decomposition')['status'] == 'draft'
    assert section(c, pid, 'decomposition')['locked']  # locked again until the goals are confirmed

    # Editing a cited requirement makes the section stale.
    c.patch(f'{API}/projects/{pid}/statements/{r2}', headers=H, json={'text': 'Patients pay invoices by card.'})
    assert section(c, pid, 'decomposition')['stale']


def main():
    original = integrated.httpx.AsyncClient
    integrated.httpx.AsyncClient = FakeDesignAI
    try:
        with TestClient(app) as client:
            check(client)
            check_decomposition(client)
        print('design sections integration test passed')
    finally:
        integrated.httpx.AsyncClient = original
        with psycopg.connect(os.environ['DATABASE_URL'], prepare_threshold=None) as c:
            for e in (EMAIL, OTHER):
                c.execute('DELETE FROM projects WHERE owner_id=%s', (f'dev:{e}',))
                c.execute('DELETE FROM consents WHERE user_id=%s', (f'dev:{e}',))


if __name__ == '__main__':
    main()
