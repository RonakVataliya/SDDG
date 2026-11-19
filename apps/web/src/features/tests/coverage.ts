/**
 * Coverage of the Tests feature (stream 6, section 11), computed from data the page already loaded - no AI, no
 * extra request.
 *
 * A requirement is Covered when it has at least one ready case (kept, with steps) and is not Out of date; Out of date
 * when its text changed after its design or cases were made; otherwise it has No tests. Boundary coverage counts the
 * boundary values (BVA:<condition>:<value>) that a ready case tests, against all boundary values of all conditions.
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

const isReady = (c: TestCase) => c.status === 'ready' && c.kept

function lastResults(ready: TestCase[]): ResultCounts | null {
  if (!ready.some((c) => c.last_result)) return null
  const counts: ResultCounts = { pass: 0, fail: 0, blocked: 0, skipped: 0, unmarked: 0 }
  for (const c of ready) counts[c.last_result ?? 'unmarked']++
  return counts
}

export function computeCoverage(requirements: TestRequirementSummary[], cases: TestCase[], runs: TestRunSummary[]): Coverage {
  let boundaryCovered = 0
  const rows = requirements.map((r): RequirementCoverage => {
    const ready = cases.filter((c) => c.statement_id === r.statement_id && isReady(c))
    const tested = new Set(ready.flatMap((c) => c.covers.filter((t) => t.startsWith('BVA:'))))
    boundaryCovered += Math.min(tested.size, r.boundary_count)
    const outOfDate = r.stale || ready.some((c) => c.freshness === 'out_of_date')
    return {
      statementId: r.statement_id,
      ref: r.ref,
      text: r.text,
      criteria: r.criteria_count,
      positive: ready.filter((c) => c.kind === 'positive').length,
      negative: ready.filter((c) => c.kind === 'negative').length,
      edge: ready.filter((c) => c.kind === 'edge').length,
      lastRun: lastResults(ready),
      status: !ready.length ? 'no_tests' : outOfDate ? 'out_of_date' : 'covered',
    }
  })
  const finished = runs
    .filter((r) => r.finished_at)
    .sort((a, b) => (b.finished_at ?? '').localeCompare(a.finished_at ?? ''))[0]
  return {
    requirementCount: requirements.length,
    requirementsWithTests: rows.filter((r) => r.status !== 'no_tests').length,
    readyCases: cases.filter(isReady).length,
    draftCases: cases.filter((c) => c.status === 'draft').length,
    lastRun: finished ? { ...finished.tally } : null,
    boundaryCovered,
    boundaryTotal: requirements.reduce((n, r) => n + r.boundary_count, 0),
    rows,
  }
}
