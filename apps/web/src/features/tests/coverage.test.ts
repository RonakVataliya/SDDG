import { describe, expect, it } from 'vitest'
import type { TestCase, TestRequirementSummary, TestRunSummary } from '@/api/client'
import { computeCoverage } from './coverage'

const req = (n: number, extra: Partial<TestRequirementSummary> = {}): TestRequirementSummary => ({
  statement_id: `st_${n}`, ref: `R-00${n}`, text: `Requirement ${n}`, label: 'FR', designed: true, stale: false,
  criteria_count: 2, draft_count: 0, kept_count: 0, ready_count: 0, boundary_count: 0, open_question: false, open_flags: [],
  ...extra,
})
let seq = 0
const tc = (statement: number, extra: Partial<TestCase> = {}): TestCase => ({
  id: `tc_${++seq}`, number: `TC-${String(seq).padStart(3, '0')}`, statement_id: `st_${statement}`, statement_ref: `R-00${statement}`,
  title: 't', technique: 'EC', kind: 'positive', priority: 'high', status: 'ready', kept: true, origin: 'generated', outcome: 'accepted',
  test_data: {}, covers: [], preconditions: [], steps: ['s'], expected: 'e', freshness: 'current', last_result: null,
  created_at: '2026-11-04T10:00:00Z', ...extra,
})
const run = (finished: string | null, tally: Partial<TestRunSummary['tally']>): TestRunSummary => ({
  id: `run_${finished}`, name: 'Run', mode: 'all', case_count: 3, created_by: 'a@b.c', created_at: '2026-11-04T10:00:00Z',
  finished_at: finished, tally: { pass: 0, fail: 0, blocked: 0, skipped: 0, unmarked: 0, ...tally },
})

describe('computeCoverage', () => {
  const requirements = [req(1), req(3, { boundary_count: 6 }), req(4, { boundary_count: 9 }), req(5)]
  const cases = [
    tc(3, { kind: 'positive', last_result: 'pass' }),
    tc(3, { kind: 'negative', technique: 'BVA+EC', covers: ['EC:len:low', 'BVA:len:7'], last_result: 'pass' }),
    tc(3, { kind: 'edge', technique: 'BVA', covers: ['BVA:len:8'] }),
    tc(4, { kind: 'negative', technique: 'BVA+EC', covers: ['BVA:days:31'], last_result: 'fail', freshness: 'out_of_date' }),
    tc(4, { kind: 'edge', technique: 'BVA', covers: ['BVA:days:2'], status: 'draft', steps: [], kept: false }),
    tc(5, { status: 'draft', steps: [] }),
  ]
  const result = computeCoverage(requirements, cases, [run('2026-11-04T12:00:00Z', { pass: 20, fail: 1, blocked: 1 }), run(null, { pass: 3 })])

  it('marks each requirement Covered, Out of date or No tests', () => {
    expect(result.rows.map((r) => [r.ref, r.status])).toEqual([
      ['R-001', 'no_tests'], ['R-003', 'covered'], ['R-004', 'out_of_date'], ['R-005', 'no_tests'],
    ])
    expect(result.requirementsWithTests).toBe(2)
  })

  it('counts ready cases by kind and their last results', () => {
    const r3 = result.rows[1]
    expect([r3.positive, r3.negative, r3.edge]).toEqual([1, 1, 1])
    expect(r3.lastRun).toEqual({ pass: 2, fail: 0, blocked: 0, skipped: 0, unmarked: 1 })
    expect(result.rows[0].lastRun).toBeNull()
  })

  it('totals cases, boundaries and the newest finished run', () => {
    expect([result.readyCases, result.draftCases]).toEqual([4, 2])
    expect([result.boundaryCovered, result.boundaryTotal]).toEqual([3, 15]) // the discarded draft's boundary does not count
    expect(result.lastRun).toEqual({ pass: 20, fail: 1, blocked: 1, skipped: 0, unmarked: 0 })
  })

  it('treats a changed requirement as out of date even before its cases are rerun', () => {
    const stale = computeCoverage([req(3, { stale: true })], [tc(3)], [])
    expect(stale.rows[0].status).toBe('out_of_date')
    expect(stale.lastRun).toBeNull()
  })
})
