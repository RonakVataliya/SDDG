/**
 * Coverage of the Tests feature (stream 6, section 11), computed from data the page already loaded - no AI, no
 * extra request.
 *
 * STUB from the API contract commit: the types are fixed so the Coverage tab can be built against them.
 * The real implementation replaces computeCoverage's body.
 */
import type { TestCase, TestRequirementSummary, TestRunSummary } from '@/api/client'

export type CoverageStatus = 'no_tests' | 'covered' | 'out_of_date'

export type ResultCounts = { pass: number; fail: number; blocked: number; skipped: number; unmarked: number }

export type RequirementCoverage = {
  statementId: string
  ref: string
  text: string
  criteria: number
  positive: number
  negative: number
  edge: number
  /** Last results of this requirement's ready cases; null when none of them has been run. */
  lastRun: ResultCounts | null
  status: CoverageStatus
}

export type Coverage = {
  requirementCount: number
  requirementsWithTests: number
  readyCases: number
  draftCases: number
  /** Tally of the newest finished run; null before the first run is finished. */
  lastRun: ResultCounts | null
  boundaryCovered: number
  boundaryTotal: number
  rows: RequirementCoverage[]
}

export function computeCoverage(requirements: TestRequirementSummary[], _cases: TestCase[], _runs: TestRunSummary[]): Coverage {
  return {
    requirementCount: requirements.length,
    requirementsWithTests: 0,
    readyCases: 0,
    draftCases: 0,
    lastRun: null,
    boundaryCovered: 0,
    boundaryTotal: 0,
    rows: requirements.map((r) => ({
      statementId: r.statement_id,
      ref: r.ref,
      text: r.text,
      criteria: 0,
      positive: 0,
      negative: 0,
      edge: 0,
      lastRun: null,
      status: 'no_tests',
    })),
  }
}
