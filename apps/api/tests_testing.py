"""Integration test for the Tests feature (Sprint 3, stream 6), run against the Postgres in DATABASE_URL.

AI requests 1 and 2 are replaced with deterministic responses (as tests_integration.py does for extraction), so this
exercises the real routes, storage, encryption, black-box engine, jobs and run selection without an LLM key.
It uses a throwaway user and deletes everything it created. Run: python tests_testing.py
"""
import importlib.util
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

EMAIL = f'tt-{uuid.uuid4().hex[:8]}@example.com'
H = {'Authorization': f'Bearer mock-token:{EMAIL}'}
BOOKING = ('A patient books an appointment 1 to 30 days ahead, may already hold at most 2 upcoming appointments, '
           'and picks Consultation, Follow-up or Test.')
SLOW = 'The appointment list must load fast for receptionists.'

DESIGNS = {
    'R-001': {
        'requirement_id': 'R-001', 'testable': True, 'question': None, 'suggestion_template': None,
        'criteria': [{'given': 'A patient holding 1 upcoming appointment', 'when': 'they book a Consultation 10 days ahead',
                      'then': 'the booking is confirmed'},
                     {'given': 'A patient who already holds 2 appointments', 'when': 'they try to book another',
                      'then': 'it is refused'}],
        'conditions': [
            {'name': 'days_ahead', 'kind': 'range', 'description': 'days ahead', 'min_value': 1, 'max_value': 30,
             'unit': 'days', 'values': [], 'invalid_values': []},
            {'name': 'held', 'kind': 'count', 'description': 'upcoming appointments', 'min_value': 0, 'max_value': 2,
             'unit': None, 'values': [], 'invalid_values': []},
            {'name': 'type', 'kind': 'set', 'description': 'appointment type', 'min_value': None, 'max_value': None,
             'unit': None, 'values': ['Consultation', 'Follow-up', 'Test'], 'invalid_values': ['Surgery']}],
        'flows': [{'kind': 'basic', 'text': 'Patient picks type, date and a free slot; the booking is confirmed.'},
                  {'kind': 'alternate', 'text': 'The slot is taken by another patient first.'}],
        'performance_targets': []},
    'R-002': {
        'requirement_id': 'R-002', 'testable': False, 'question': 'What load time counts as fast, and for how many?',
        'suggestion_template': 'The appointment list loads in {answer}.',
        'criteria': [], 'conditions': [], 'flows': [], 'performance_targets': []},
    'R-002-fixed': {
        'requirement_id': 'R-002', 'testable': True, 'question': None, 'suggestion_template': None,
        'criteria': [{'given': '50 receptionists are signed in', 'when': 'they all open the list', 'then': 'it loads in under 2 s'}],
        'conditions': [], 'flows': [],
        'performance_targets': [{'measure': 'list load time', 'limit': 2, 'unit': 's', 'load': '50 receptionists'}]},
}
AI_CALLS = {'criteria': 0, 'steps': 0, 'step_cases': 0, 'derive': 0}

# /tests/derive is plain code, so the fake answers it with the AI service's real engine file (it has no imports).
_spec = importlib.util.spec_from_file_location(
    'services_blackbox', Path(__file__).resolve().parents[2] / 'services/ai-extraction/app/testgen/blackbox.py')
ENGINE = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ENGINE)


class FakeTestsAI(tests_integration.FakeAIClient):
    async def post(self, url, **kwargs):
        body = kwargs.get('json') or {}
        if url.endswith('/tests/criteria'):
            AI_CALLS['criteria'] += 1
            assert len(body['requirements']) <= 5
            out = []
            for r in body['requirements']:
                key = 'R-002-fixed' if r['id'] == 'R-002' and 'loads in' in r['text'] else r['id']
                out.append(DESIGNS[key])
            return tests_integration.FakeResponse({'requirements': out, 'errors': [], 'metadata': {}})
        if url.endswith('/tests/derive'):
            AI_CALLS['derive'] += 1
            return tests_integration.FakeResponse(ENGINE.derive(body['conditions'], body['flows'],
                                                                body['performance_targets'], body['criteria']))
        if url.endswith('/tests/steps'):
            AI_CALLS['steps'] += 1
            AI_CALLS['step_cases'] += len(body['cases'])
            assert len(body['cases']) <= 6
            return tests_integration.FakeResponse({'cases': [{
                'case_id': c['case_id'], 'preconditions': ['Patient Asha Patel is signed in'],
                'steps': ['Open Book appointment', f"Enter {c['test_data']}", 'Press Book'],
                'expected_result': 'The booking is refused.' if c['expected_outcome'] == 'rejected' else 'Confirmed.',
            } for c in body['cases']], 'errors': [], 'metadata': {}})
        return await super().post(url, **kwargs)


def sql(query, *args):
    with psycopg.connect(os.environ['DATABASE_URL'], prepare_threshold=None) as c:
        return c.execute(query, args).fetchall()


def check(c):
    api = '/api/v1'
    pid = c.post(f'{api}/projects', headers=H, json={'name': 'Tests feature'}).json()['id']
    t = f'{api}/projects/{pid}/tests'
    r1, r2 = db.insert_statements(pid, [{'text': BOOKING}, {'text': SLOW}])
    db.add_system_items(pid, [{'id': db.uid('it'), 'category': 'entity', 'name': 'Appointment', 'description': None,
                               'qualifiers': [], 'statement_ids': [r1, r2]}])

    # AI request 1 needs consent, then designs both requirements in one call (5 per call).
    assert c.post(f'{t}/criteria-jobs', headers=H, json={'statement_ids': [r1, r2]}).status_code == 403
    c.post(f'{api}/me/consent', headers=H, json={'policy_version': integrated.POLICY_VERSION})
    job = c.post(f'{t}/criteria-jobs', headers=H, json={'statement_ids': [r1, r2]}).json()
    assert c.get(f'{api}/jobs/{job["id"]}', headers=H).json()['status'] == 'succeeded'
    assert AI_CALLS['criteria'] == 1
    reqs = {r['ref']: r for r in c.get(f'{t}/requirements', headers=H).json()['requirements']}
    assert (reqs['R-001']['draft_count'], reqs['R-001']['boundary_count']) == (15, 9), reqs['R-001']
    assert reqs['R-002']['open_question'] and reqs['R-002']['draft_count'] == 0

    # Classes and boundaries are plain code; editing a condition recomputes them without an AI call.
    design = c.get(f'{t}/requirements/{r1}', headers=H).json()
    days = design['conditions'][0]
    assert [b['value'] for b in days['boundaries']] == [0, 1, 2, 29, 30, 31]
    assert [k['label'] for k in design['conditions'][1]['classes']] == ['0–2', '> 2']
    edited = c.patch(f'{t}/conditions/{days["id"]}', headers=H, json={'max': 60}).json()
    assert edited['conditions'][0]['boundaries'][-1]['value'] == 61
    back = c.patch(f'{t}/conditions/{days["id"]}', headers=H, json={'max': 30}).json()
    assert len(back['drafts']) == 15 and AI_CALLS['criteria'] == 1
    # Numbers stay stable across the edit and back: the same drafts carry the same TC numbers, in TC order.
    assert [(d['number'], d['title']) for d in back['drafts']] == [(d['number'], d['title']) for d in design['drafts']]
    assert [d['number'] for d in edited['drafts']] == [d['number'] for d in design['drafts']]

    # The untestable question survives a quality-check rerun, and the answer completes the suggested requirement.
    question = c.get(f'{t}/requirements/{r2}', headers=H).json()['question']
    db.save_flags(pid, [], [r2])
    answered = c.post(f'{api}/projects/{pid}/flags/{question["id"]}/answer', headers=H,
                      json={'answer': 'under 2 seconds with 50 receptionists at once'}).json()
    assert answered['suggestion'] == 'The appointment list loads in under 2 seconds with 50 receptionists at once.'
    c.patch(f'{api}/projects/{pid}/statements/{r2}', headers=H, json={'text': answered['suggestion']})
    assert c.get(f'{t}/requirements', headers=H).json()['requirements'][1]['stale'] is True
    c.post(f'{t}/criteria-jobs', headers=H, json={'statement_ids': [r2]})  # regenerate just R-002
    perf = c.get(f'{t}/requirements/{r2}', headers=H).json()
    assert [d['technique'] for d in perf['drafts']] == ['NFR'] and not perf['stale']

    # Untick 4 drafts: AI request 2 writes steps for the 12 kept cases only, 6 per call.
    drafts = back['drafts']
    for d in drafts[4:8]:  # days_ahead = 1, 2, 29, 30
        c.patch(f'{t}/cases/{d["id"]}', headers=H, json={'kept': False})
    c.post(f'{t}/step-jobs', headers=H, json={})
    assert (AI_CALLS['steps'], AI_CALLS['step_cases']) == (2, 12), AI_CALLS  # 6 + 6
    cases = c.get(f'{t}/cases', headers=H).json()
    assert sum(x['status'] == 'ready' for x in cases) == 12 and sum(x['status'] == 'draft' for x in cases) == 4
    over = next(x for x in cases if x['title'] == 'days_ahead = 31 (above 30) → rejected')
    assert over['expected'] == 'The booking is refused.' and over['test_data'] == {'days_ahead': 31, 'held': 1, 'type': 'Consultation'}

    # Stored content is encrypted.
    for (title,) in sql('SELECT title FROM test_cases WHERE project_id=%s', pid):
        assert title.startswith(PREFIX)

    # A manual run: results record who and when; a finished run is read-only.
    run = c.post(f'{t}/runs', headers=H, json={'name': 'Run 1', 'mode': 'all'}).json()
    ids = [i['case']['id'] for i in run['items']]
    nfr = next(i['case']['id'] for i in run['items'] if i['case']['technique'] == 'NFR')
    for cid in ids:
        status = 'fail' if cid == over['id'] else 'blocked' if cid == nfr else 'pass'
        note = 'Calendar still lets me pick day 31.' if status == 'fail' else None
        r = c.put(f'{t}/runs/{run["id"]}/results/{cid}', headers=H, json={'status': status, 'note': note}).json()
        assert r['marked_by'] == EMAIL
    done = c.post(f'{t}/runs/{run["id"]}/finish', headers=H).json()
    assert done['tally'] == {'pass': 10, 'fail': 1, 'blocked': 1, 'skipped': 0, 'unmarked': 0}, done['tally']
    assert c.put(f'{t}/runs/{run["id"]}/results/{ids[0]}', headers=H, json={'status': 'pass'}).status_code == 409

    # A change request on R-001 (the Review page's own edit route): its cases go Out of date. Editing a requirement
    # clears the extracted building blocks (requirements-first), so regression first picks R-001's cases only,
    # the failed one first.
    c.patch(f'{api}/projects/{pid}/statements/{r1}', headers=H, json={'text': BOOKING.replace('30 days', '45 days')})
    assert {x['freshness'] for x in c.get(f'{t}/cases', headers=H).json() if x['statement_ref'] == 'R-001'} == {'out_of_date'}
    assert db.get_items(pid) == []
    sel = c.get(f'{t}/runs/selection', headers=H).json()
    reg = sel['regression']
    assert sel['changed_refs'] == ['R-001'] and reg['case_ids'][0] == over['id'] and nfr not in reg['case_ids']
    assert reg['reasons'][over['id']] == 'failed last run · R-001 changed'
    # Generating diagrams again extracts the building blocks again; R-002 shares Appointment with R-001, so its case
    # joins the regression run, and the failed and blocked cases come first.
    db.add_system_items(pid, [{'id': db.uid('it'), 'category': 'entity', 'name': 'Appointment', 'description': None,
                               'qualifiers': [], 'statement_ids': [r1, r2]}])
    sel = c.get(f'{t}/runs/selection', headers=H).json()
    assert sel['regression']['case_ids'][:2] == [over['id'], nfr]
    assert sel['regression']['reasons'][nfr] == 'blocked last run · shares Appointment with R-001'
    assert sel['failed']['case_ids'] == [over['id'], nfr] and sel['minimal']['warning']
    minimal = c.post(f'{t}/runs', headers=H, json={'name': 'Run 2', 'mode': 'minimal'}).json()
    assert [i['case']['kind'] for i in minimal['items']] == ['positive', 'negative', 'edge', 'positive']
    # Deleting a requirement deletes its test design and cases (database cascade); runs keep the other cases.
    assert c.delete(f'{api}/projects/{pid}/statements/{r2}', headers=H).status_code == 204
    assert {x['statement_ref'] for x in c.get(f'{t}/cases', headers=H).json()} == {'R-001'}
    assert nfr not in [i['case']['id'] for i in c.get(f'{t}/runs/{run["id"]}', headers=H).json()['items']]
    assert [r['ref'] for r in c.get(f'{t}/requirements', headers=H).json()['requirements']] == ['R-001']
    assert [r['name'] for r in c.get(f'{t}/runs', headers=H).json()] == ['Run 2', 'Run 1']
    return pid


# ---------------------------------------------------------------------------------------------------------------------
# Edge cases: failures, odd input, concurrency
# ---------------------------------------------------------------------------------------------------------------------

ODD = "Le patient réserve 2.5 à 9.75 jours ✓ — 'quote' \"dq\" <b>x</b> '; DROP TABLE test_cases; -- દર્દી"
EDGE_DESIGN = {
    'requirement_id': None, 'testable': True, 'question': None, 'suggestion_template': None,
    'criteria': [{'given': ODD, 'when': 'w', 'then': 't'}],
    'conditions': [
        {'name': 'price', 'kind': 'range', 'description': ODD, 'min_value': 2.5, 'max_value': 9.75, 'unit': None,
         'values': [], 'invalid_values': []},
        {'name': 'age', 'kind': 'range', 'description': 'min only', 'min_value': 18, 'max_value': None, 'unit': None,
         'values': [], 'invalid_values': []},
        {'name': 'seats', 'kind': 'count', 'description': '', 'min_value': 1, 'max_value': 3, 'unit': None,
         'values': [], 'invalid_values': []},
        {'name': 'mode', 'kind': 'set', 'description': '', 'min_value': None, 'max_value': None, 'unit': None,
         'values': ['A ✓', "B'; --"], 'invalid_values': []}],
    'flows': [], 'performance_targets': []}
FAIL_NEXT = {'criteria': False, 'derive': False, 'steps_skip': 0}


class EdgeAI(tests_integration.FakeAIClient):
    async def post(self, url, **kwargs):
        body = kwargs.get('json') or {}
        if url.endswith('/tests/derive') and FAIL_NEXT['derive']:
            FAIL_NEXT['derive'] = False
            return integrated.httpx.Response(503, json={'detail': 'AI service is not available.'},
                                             request=integrated.httpx.Request('POST', url))
        if url.endswith('/tests/criteria'):
            AI_CALLS['criteria'] += 1
            if FAIL_NEXT['criteria']:
                FAIL_NEXT['criteria'] = False
                return integrated.httpx.Response(503, json={'detail': 'AI service is not available.'},
                                                 request=integrated.httpx.Request('POST', url))
            out = [{**EDGE_DESIGN, 'requirement_id': r['id']} for r in body['requirements']]
            out.append({**EDGE_DESIGN, 'requirement_id': 'R-999'})  # an id that was never asked for is ignored
            return tests_integration.FakeResponse({'requirements': out, 'errors': [], 'metadata': {}})
        if url.endswith('/tests/steps'):
            AI_CALLS['steps'] += 1
            cases = body['cases'][FAIL_NEXT['steps_skip']:]  # the AI may leave cases out
            return tests_integration.FakeResponse({'cases': [{
                'case_id': c['case_id'], 'preconditions': [ODD], 'steps': [ODD, 'Press Save'], 'expected_result': ODD,
            } for c in cases], 'errors': [], 'metadata': {}})
        return await FakeTestsAI.post(self, url, **kwargs)


def check_edges(c):
    import threading
    from core import testing_db as tdb
    api = '/api/v1'
    pid = c.post(f'{api}/projects', headers=H, json={'name': 'Edges'}).json()['id']
    t = f'{api}/projects/{pid}/tests'
    c.post(f'{api}/me/consent', headers=H, json={'policy_version': integrated.POLICY_VERSION})
    ids = db.insert_statements(pid, [{'text': f'{ODD} #{i}'} for i in range(12)])

    # Input limits.
    assert c.post(f'{t}/criteria-jobs', headers=H, json={'statement_ids': []}).status_code == 422
    assert c.post(f'{t}/criteria-jobs', headers=H, json={'statement_ids': ids * 3}).status_code == 422  # > 30
    assert c.patch(f'{api}/projects/{pid}/statements/{ids[0]}', headers=H, json={'text': 'x' * 2001}).status_code == 422
    assert c.post(f'{t}/runs', headers=H, json={'name': 'R', 'mode': 'sometimes'}).status_code == 422

    # The AI service is down: the job fails cleanly and nothing is half-written; the next try works.
    FAIL_NEXT['criteria'] = True
    job = c.post(f'{t}/criteria-jobs', headers=H, json={'statement_ids': ids[:2]}).json()
    failed = c.get(f'{api}/jobs/{job["id"]}', headers=H).json()
    assert failed['status'] == 'failed' and failed['error'].startswith('Test generation failed'), failed
    assert c.get(f'{t}/cases', headers=H).json() == []
    assert c.get(f'{t}/requirements', headers=H).json()['active_job'] is None

    # 12 requirements go out as 5 + 5 + 2; an id the AI invents is ignored.
    before = AI_CALLS['criteria']
    job = c.post(f'{t}/criteria-jobs', headers=H, json={'statement_ids': ids}).json()
    assert job['progress']['total'] == 4
    assert c.get(f'{api}/jobs/{job["id"]}', headers=H).json()['status'] == 'succeeded'
    assert AI_CALLS['criteria'] - before == 3
    reqs = c.get(f'{t}/requirements', headers=H).json()['requirements']
    assert all(r['designed'] for r in reqs) and len(reqs) == 12

    # Decimals, a missing upper limit, a count above zero, and a set without invalid values.
    d = c.get(f'{t}/requirements/{ids[0]}', headers=H).json()
    price, age, seats, mode = d['conditions']
    assert [b['value'] for b in price['boundaries']] == [2.49, 2.5, 2.51, 9.74, 9.75, 9.76]
    assert [k['label'] for k in age['classes']] == ['≥ 18', '< 18'] and [b['value'] for b in age['boundaries']] == [17, 18, 19]
    assert [k['label'] for k in seats['classes']] == ['1–3', '< 1', '> 3'] and [b['value'] for b in seats['boundaries']] == [0, 1, 3, 4]
    assert [k['label'] for k in mode['classes']] == ['A ✓', "B'; --", 'any other value']
    assert d['criteria'][0]['given'] == ODD and price['description'] == ODD  # text round-trips intact
    assert len(d['drafts']) == 2 + 6 + 3 + 4  # positives per set value + boundaries; no invalid value to test
    assert c.patch(f'{t}/conditions/{mode["id"]}', headers=H, json={'values': ['  ', '']}).status_code == 422
    FAIL_NEXT['derive'] = True  # the AI service is down during an edit: 503, and the old limits stay
    assert c.patch(f'{t}/conditions/{price["id"]}', headers=H, json={'max': 99}).status_code == 503
    assert c.get(f'{t}/requirements/{ids[0]}', headers=H).json()['conditions'][0]['max'] == 9.75
    assert c.patch(f'{t}/conditions/{age["id"]}', headers=H, json={'min': None, 'max': None}).status_code == 422
    below18 = next(x for x in d['drafts'] if x['title'] == 'age = 17 (below 18) → rejected')
    c.patch(f'{t}/cases/{below18["id"]}', headers=H, json={'kept': False})
    flt = c.patch(f'{t}/conditions/{price["id"]}', headers=H, json={'min': 0.1, 'max': 0.3}).json()
    assert [b['value'] for b in flt['conditions'][0]['boundaries']] == [0, 0.1, 0.2, 0.3, 0.4], flt['conditions'][0]
    still = next(x for x in flt['drafts'] if x['title'] == below18['title'])
    assert still['number'] == below18['number'] and still['kept'] is False  # an edit elsewhere keeps the user's choice
    assert {x['number'] for x in flt['drafts']} <= {x['number'] for x in d['drafts']}  # 6 price boundaries became 5

    # 20 cases added at once get 20 different TC numbers.
    text = db.get_statements(pid)[1]['text']
    errors = []

    def add():
        try:
            tdb.add_manual_case(pid, ids[1], text, {'title': 'Concurrent', 'kind': 'edge', 'priority': 'low',
                                                    'steps': ['s'], 'expected': 'e'})
        except Exception as e:  # noqa: BLE001
            errors.append(e)
    threads = [threading.Thread(target=add) for _ in range(20)]
    [th.start() for th in threads]
    [th.join() for th in threads]
    numbers = [x['number'] for x in c.get(f'{t}/cases', headers=H).json()]
    assert not errors and len(numbers) == len(set(numbers)), errors or numbers

    # The AI leaves a case out: it stays a draft and the job says so.
    FAIL_NEXT['steps_skip'] = 1
    one = [x['id'] for x in c.get(f'{t}/requirements/{ids[2]}', headers=H).json()['drafts'][:3]]
    job = c.post(f'{t}/step-jobs', headers=H, json={'case_ids': one}).json()
    assert c.get(f'{api}/jobs/{job["id"]}', headers=H).json()['progress']['label'] == 'Steps written for 2 of 3 cases'
    FAIL_NEXT['steps_skip'] = 0
    after = {x['id']: x for x in c.get(f'{t}/cases', headers=H).json()}
    assert [after[i]['status'] for i in one] == ['draft', 'ready', 'ready'] and after[one[1]]['steps'][0] == ODD

    # Regenerating keeps cases with steps (they show Out of date if the text changed) and numbering continues.
    c.patch(f'{api}/projects/{pid}/statements/{ids[2]}', headers=H, json={'text': ODD + ' (edited)'})
    drafts_before = sorted(x['number'] for x in after.values() if x['statement_id'] == ids[2] and x['status'] == 'draft')
    c.post(f'{t}/criteria-jobs', headers=H, json={'statement_ids': [ids[2]]})
    again = [x for x in c.get(f'{t}/cases', headers=H).json() if x['statement_id'] == ids[2]]
    kept = [x for x in again if x['id'] in one[1:]]
    assert len(kept) == 2 and {x['freshness'] for x in kept} == {'out_of_date'}
    assert sorted(x['number'] for x in again if x['status'] == 'draft') == drafts_before  # same drafts, same numbers
    listed = [x['number'] for x in c.get(f'{t}/cases', headers=H).json()]
    assert listed == sorted(listed, key=lambda n: int(n[3:]))  # the Cases tab lists in TC order
    unchanged = c.patch(f'{api}/projects/{pid}/statements/{ids[3]}', headers=H, json={'text': db.get_statements(pid)[3]['text']})
    assert unchanged.status_code == 200 and not c.get(f'{t}/requirements', headers=H).json()['requirements'][3]['stale']

    # Runs: picking another project's case, notes over the limit, a case outside the run, finishing twice.
    assert c.post(f'{t}/runs', headers=H, json={'name': 'R', 'mode': 'pick', 'case_ids': ['tc_elsewhere']}).status_code == 422
    run = c.post(f'{t}/runs', headers=H, json={'name': ODD[:100], 'mode': 'pick', 'case_ids': one[1:]}).json()
    assert run['name'] == ODD[:100] and run['case_count'] == 2
    res = f'{t}/runs/{run["id"]}/results'
    assert c.put(f'{res}/{one[1]}', headers=H, json={'status': 'fail', 'note': 'n' * 1001}).status_code == 422
    assert c.put(f'{res}/{one[0]}', headers=H, json={'status': 'pass'}).status_code == 404
    assert c.put(f'{res}/{one[1]}', headers=H, json={'status': 'fail', 'note': ODD}).json()['note'] == ODD
    assert c.put(f'{res}/{one[1]}', headers=H, json={'status': 'pass', 'note': '  '}).json()['note'] is None
    first = c.post(f'{t}/runs/{run["id"]}/finish', headers=H).json()['finished_at']
    assert c.post(f'{t}/runs/{run["id"]}/finish', headers=H).json()['finished_at'] == first
    assert c.get(f'{t}/runs/{run["id"]}', headers=H).json()['items'][0]['result']['status'] == 'pass'
    assert c.get(f'{t}/runs/run_nope', headers=H).status_code == 404

    # Everything stored from the odd text is encrypted.
    for table, col in (('test_criteria', 'given_text'), ('test_conditions', 'description'),
                       ('test_conditions', 'classes'), ('test_conditions', 'boundaries'), ('test_cases', 'steps'),
                       ('test_runs', 'name'), ('test_results', 'note')):
        for (value,) in sql(f'SELECT {col} FROM {table} WHERE project_id=%s AND {col} IS NOT NULL', pid):
            assert value.startswith(PREFIX), (table, col)
    assert sql('SELECT count(*) FROM test_cases WHERE project_id=%s', pid)[0][0] > 0  # the DROP TABLE text did nothing
    return pid


# ---------------------------------------------------------------------------------------------------------------------
# Points from the pull request review
# ---------------------------------------------------------------------------------------------------------------------

REVIEW_DESIGN = {
    'requirement_id': None, 'testable': True, 'question': None, 'suggestion_template': None,
    'criteria': [{'given': 'A signed-in patient', 'when': 'they book', 'then': 'the booking is confirmed'}],
    'conditions': [{'name': 'days', 'kind': 'range', 'description': 'days ahead', 'min_value': 1, 'max_value': 3,
                    'unit': 'days', 'values': [], 'invalid_values': []}],
    'flows': [{'kind': 'basic', 'text': 'The patient books a slot.'}] * 2,  # the AI repeats a flow
    'performance_targets': []}


class ReviewAI(EdgeAI):
    async def post(self, url, **kwargs):
        if url.endswith('/tests/criteria'):
            body = kwargs.get('json') or {}
            return tests_integration.FakeResponse({'requirements': [
                {**REVIEW_DESIGN, 'requirement_id': r['id']} for r in body['requirements']], 'errors': [], 'metadata': {}})
        return await EdgeAI.post(self, url, **kwargs)


def check_review(c):
    api = '/api/v1'
    pid = c.post(f'{api}/projects', headers=H, json={'name': 'Review'}).json()['id']
    t = f'{api}/projects/{pid}/tests'
    c.post(f'{api}/me/consent', headers=H, json={'policy_version': integrated.POLICY_VERSION})
    ids = db.insert_statements(pid, [{'text': 'A patient books a slot 1 to 3 days ahead.'},
                                     {'text': 'A patient cancels a slot.'}])
    assert c.post(f'{t}/criteria-jobs', headers=H, json={'statement_ids': ids}).status_code == 202

    # The AI repeats a flow: the same test is listed once, and stays once (same number) after a condition edit.
    d = c.get(f'{t}/requirements/{ids[0]}', headers=H).json()
    titles = [x['title'] for x in d['drafts']]
    assert titles.count('Basic flow: The patient books a slot.') == 1 and len(titles) == len(set(titles)), titles
    flow = next(x for x in d['drafts'] if x['title'].startswith('Basic flow'))
    edited = c.patch(f'{t}/conditions/{d["conditions"][0]["id"]}', headers=H, json={'max': 5}).json()
    assert [x['number'] for x in edited['drafts'] if x['title'] == flow['title']] == [flow['number']]

    # A draft can only be kept or discarded: drafts are rebuilt when their conditions change, so other edits would be
    # lost. Once its steps are written, the case is ready and can be edited.
    draft = c.get(f'{t}/requirements/{ids[0]}', headers=H).json()['drafts'][0]
    for body in ({'title': 'Mine'}, {'steps': ['Open the page']}, {'kept': True, 'expected': 'Shown'}):
        r = c.patch(f'{t}/cases/{draft["id"]}', headers=H, json=body)
        assert r.status_code == 409 and r.json()['detail'].startswith('A draft can only be kept'), (body, r.text)
    assert c.patch(f'{t}/cases/{draft["id"]}', headers=H, json={'kept': False}).json()['kept'] is False
    assert c.patch(f'{t}/cases/{draft["id"]}', headers=H, json={'kept': True}).json()['kept'] is True
    job = c.post(f'{t}/step-jobs', headers=H, json={'case_ids': [draft['id']]}).json()
    assert c.get(f'{api}/jobs/{job["id"]}', headers=H).json()['status'] == 'succeeded'
    assert c.patch(f'{t}/cases/{draft["id"]}', headers=H, json={'title': 'Mine'}).json()['title'] == 'Mine'

    # Deleting a requirement deletes its cases and their results (database cascade). A run then counts only the cases
    # that still exist, so marking those leaves nothing unmarked.
    other = c.get(f'{t}/requirements/{ids[1]}', headers=H).json()['drafts'][0]
    job = c.post(f'{t}/step-jobs', headers=H, json={'case_ids': [other['id']]}).json()
    assert c.get(f'{api}/jobs/{job["id"]}', headers=H).json()['status'] == 'succeeded'
    run = c.post(f'{t}/runs', headers=H, json={'name': 'Both', 'mode': 'pick', 'case_ids': [draft['id'], other['id']]}).json()
    assert run['case_count'] == 2 and run['tally']['unmarked'] == 2
    c.put(f'{t}/runs/{run["id"]}/results/{draft["id"]}', headers=H, json={'status': 'pass'})
    assert c.delete(f'{api}/projects/{pid}/statements/{ids[1]}', headers=H).status_code == 204
    listed = next(r for r in c.get(f'{t}/runs', headers=H).json() if r['id'] == run['id'])
    assert listed['case_count'] == 1 and listed['tally'] == {'pass': 1, 'fail': 0, 'blocked': 0, 'skipped': 0,
                                                              'unmarked': 0}, listed
    assert [i['case']['id'] for i in c.get(f'{t}/runs/{run["id"]}', headers=H).json()['items']] == [draft['id']]

    # One Tests job at a time per project: while one is queued, running or waiting, both kinds of start are refused,
    # also when 10 requests arrive at the same moment.
    import threading
    from core import testing_db as tdb
    busy = tdb.start_test_job(pid, 'test_criteria', 2, 'Queued')  # a job that has not run yet
    assert busy and tdb.start_test_job(pid, 'test_steps', 2, 'Queued') is None
    assert c.get(f'{t}/requirements', headers=H).json()['active_job']['id'] == busy['id']
    for path, body in (('criteria-jobs', {'statement_ids': [ids[0]]}), ('step-jobs', {})):
        r = c.post(f'{t}/{path}', headers=H, json=body)
        assert r.status_code == 409 and r.json()['detail'].startswith('Test generation is already running'), r.text
    db.update_job(busy['id'], status='failed', finished_at=db.now())
    started = []
    threads = [threading.Thread(target=lambda: started.append(tdb.start_test_job(pid, 'test_criteria', 2, 'Queued')))
               for _ in range(10)]
    [th.start() for th in threads]
    [th.join() for th in threads]
    winners = [j for j in started if j]
    assert len(started) == 10 and len(winners) == 1, started
    db.update_job(winners[0]['id'], status='failed', finished_at=db.now())
    job = c.post(f'{t}/criteria-jobs', headers=H, json={'statement_ids': [ids[0]]}).json()  # free again
    assert c.get(f'{api}/jobs/{job["id"]}', headers=H).json()['status'] == 'succeeded'

    # Boundary values are encrypted like their sibling classes, on generation and on an edit; a row stored in plain
    # JSON before this change still reads.
    cond = c.get(f'{t}/requirements/{ids[0]}', headers=H).json()['conditions'][0]
    assert sql('SELECT boundaries FROM test_conditions WHERE id=%s', cond['id'])[0][0].startswith(PREFIX)
    edited = c.patch(f'{t}/conditions/{cond["id"]}', headers=H, json={'max': 4}).json()['conditions'][0]
    assert [b['value'] for b in edited['boundaries']] == [0, 1, 2, 3, 4, 5]
    assert sql('SELECT boundaries FROM test_conditions WHERE id=%s', cond['id'])[0][0].startswith(PREFIX)
    with psycopg.connect(os.environ['DATABASE_URL'], prepare_threshold=None) as conn:
        conn.execute('UPDATE test_conditions SET boundaries=%s WHERE id=%s', ('[{"value": 7, "valid": true}]', cond['id']))
    assert c.get(f'{t}/requirements/{ids[0]}', headers=H).json()['conditions'][0]['boundaries'] == [{'value': 7, 'valid': True}]
    return pid


def main():
    original = integrated.httpx.AsyncClient
    integrated.httpx.AsyncClient = FakeTestsAI
    try:
        with TestClient(app) as client:
            check(client)
            integrated.httpx.AsyncClient = EdgeAI
            check_edges(client)
            integrated.httpx.AsyncClient = ReviewAI
            check_review(client)
        print('tests feature integration test passed (main flow and edge cases)')
    finally:
        integrated.httpx.AsyncClient = original
        sql_run = 'DELETE FROM projects WHERE owner_id=%s'
        with psycopg.connect(os.environ['DATABASE_URL'], prepare_threshold=None) as c:
            c.execute(sql_run, (f'dev:{EMAIL}',))
            c.execute('DELETE FROM consents WHERE user_id=%s', (f'dev:{EMAIL}',))


if __name__ == '__main__':
    main()
