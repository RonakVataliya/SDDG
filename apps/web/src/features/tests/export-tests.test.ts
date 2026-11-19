import { describe, expect, it } from 'vitest'
import type { TestCase, TestRequirementSummary } from '@/api/client'
import { boundaryCondition, csvField, testsToCsv, testsToGherkin } from './export-tests'

const req: TestRequirementSummary = {
  statement_id: 'st_4', ref: 'R-004', text: 'A patient books 1 to 30 days ahead.', label: 'FR', designed: true, stale: false,
  criteria_count: 1, draft_count: 0, kept_count: 0, ready_count: 3, boundary_count: 6, open_question: false, open_flags: [],
}

const base: TestCase = {
  id: 'tc_1', number: 'TC-001', statement_id: 'st_4', statement_ref: 'R-004', title: 'Valid values, Consultation → accepted',
  technique: 'EC', kind: 'positive', priority: 'high', status: 'ready', kept: true, origin: 'generated', outcome: 'accepted',
  test_data: { days_ahead: 15, type: 'Consultation' }, covers: ['EC:days_ahead:valid'],
  preconditions: ['Patient Asha is signed in'], steps: ['Open Book appointment', 'Press Book'],
  expected: 'The booking is confirmed, and shown under "Upcoming".', freshness: 'current', last_result: 'pass',
  created_at: '2026-11-04T10:00:00Z',
}
const bva = (n: number, value: number, outcome: 'accepted' | 'rejected'): TestCase => ({
  ...base, id: `tc_${n}`, number: `TC-00${n}`, title: `days_ahead = ${value}`, technique: outcome === 'rejected' ? 'BVA+EC' : 'BVA',
  kind: outcome === 'rejected' ? 'negative' : 'edge', outcome, test_data: { days_ahead: value, type: 'Consultation' },
  covers: [`BVA:days_ahead:${value}`], steps: [], status: 'draft', last_result: null,
})

describe('CSV export', () => {
  it('quotes fields with commas, quotes and line breaks', () => {
    expect(csvField('plain')).toBe('plain')
    expect(csvField('a, b')).toBe('"a, b"')
    expect(csvField('say "hi"')).toBe('"say ""hi"""')
    expect(csvField('1. a\n2. b')).toBe('"1. a\n2. b"')
  })

  it('writes a header and one row per case', () => {
    const csv = testsToCsv([base, bva(4, 0, 'rejected')], [req])
    const lines = csv.replace('\uFEFF', '').trim().split('\r\n')
    expect(lines[0]).toBe('Case,Requirement,Title,Technique,Kind,Priority,Status,Freshness,Preconditions,Steps,Test data,Expected result,Last result')
    expect(lines).toHaveLength(3)
    expect(csv).toContain('"1. Open Book appointment\n2. Press Book"')
    expect(csv).toContain('"The booking is confirmed, and shown under ""Upcoming""."')
    expect(lines[2]).toContain('days_ahead = 0; type = Consultation')
  })
})

describe('Gherkin export', () => {
  it('turns boundary cases into one Scenario Outline with an Examples row each', () => {
    const cases = [base, bva(4, 0, 'rejected'), bva(5, 1, 'accepted'), bva(9, 31, 'rejected')]
    const out = testsToGherkin(cases, [req])
    expect(boundaryCondition(cases[1])).toBe('days_ahead')
    expect(out).toContain('Feature: R-004 A patient books 1 to 30 days ahead.')
    expect(out).toContain('Scenario: TC-001 Valid values, Consultation → accepted')
    expect(out).toContain('    Given Patient Asha is signed in\n    When Open Book appointment\n    And Press Book\n    Then')
    expect(out).toContain('Scenario Outline: R-004 days_ahead boundaries')
    expect(out).toContain('When the tester submits days_ahead = <days_ahead>, type = <type>')
    expect(out).toMatch(/\| TC-004 \| 0 +\| Consultation \| rejected \|/)
    expect(out.match(/\| TC-00\d/g)).toHaveLength(3)
  })

  it('leaves out discarded drafts and requirements without cases', () => {
    const out = testsToGherkin([{ ...bva(6, 2, 'accepted'), kept: false }], [req])
    expect(out).not.toContain('Feature:')
  })
})
