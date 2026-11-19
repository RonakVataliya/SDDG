import { CpuIcon } from 'lucide-react'
import { errorMessage } from '@/api/errors'
import { useTestCases, useTestRequirements, useTestRuns } from '@/api/queries'
import { Badge, RefTag } from '@/components/ui/badge'
import { Notice } from '@/components/ui/notice'
import { PageLoading } from '@/components/ui/spinner'
import { cn } from '@/lib/utils'
import { computeCoverage, type CoverageStatus, type ResultCounts } from './coverage'
import { RESULT } from './labels'

const STATUS: Record<CoverageStatus, { label: string; tone: 'neutral' | 'accent' | 'amber' }> = {
  no_tests: { label: 'No tests', tone: 'neutral' },
  covered: { label: 'Covered', tone: 'accent' },
  out_of_date: { label: 'Out of date', tone: 'amber' },
}

/** Coverage tab: which requirements have tests and how they did, computed from stored data (no AI). */
export function CoverageTab({ projectId }: { projectId: string }) {
  const requirements = useTestRequirements(projectId)
  const cases = useTestCases(projectId)
  const runs = useTestRuns(projectId)

  if (requirements.isPending || cases.isPending || runs.isPending) return <PageLoading label="Working out coverage" />
  const error = requirements.error ?? cases.error ?? runs.error
  if (error || !requirements.data || !cases.data || !runs.data)
    return (
      <Notice tone="error" title="Couldn't work out coverage">
        {errorMessage(error)}
      </Notice>
    )

  const cov = computeCoverage(requirements.data.requirements, cases.data, runs.data)
  const last = cov.lastRun

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Requirements with tests" value={cov.requirementsWithTests} suffix={`of ${cov.requirementCount}`} />
        <Stat label="Test cases" value={cov.readyCases} suffix={`ready · ${cov.draftCases} draft`} />
        <div className="rounded-xl border border-rule bg-field px-4 py-3">
          <p className="text-xs text-slate">Last run</p>
          {last ? (
            <p className="mt-0.5 text-lg font-semibold tabular-nums">
              {last.pass} pass
              {last.fail > 0 && <span className="text-danger"> · {last.fail} fail</span>}
              {last.blocked > 0 && <span className="text-amber"> · {last.blocked} blocked</span>}
            </p>
          ) : (
            <p className="mt-0.5 text-lg font-semibold text-slate">No finished run</p>
          )}
        </div>
        <Stat label="Boundary points covered" value={cov.boundaryCovered} suffix={`of ${cov.boundaryTotal}`} />
      </div>

      <section aria-label="Coverage by requirement" className="overflow-hidden rounded-xl border border-rule bg-field">
        <header className="flex flex-wrap items-center gap-2 border-b border-rule px-4 py-2.5">
          <h3 className="text-sm font-semibold">Coverage by requirement</h3>
          <Badge tone="accent" className="ml-auto">
            <CpuIcon className="size-3" /> Computed from stored data · no AI
          </Badge>
        </header>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-rule text-xs text-slate">
              <tr>
                <th scope="col" className="px-4 py-2 font-medium">Requirement</th>
                {['Criteria', 'Positive', 'Negative', 'Edge'].map((h) => (
                  <th key={h} scope="col" className="px-3 py-2 text-right font-medium">
                    {h}
                  </th>
                ))}
                <th scope="col" className="px-4 py-2 font-medium">Last run</th>
                <th scope="col" className="px-4 py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-rule">
              {cov.rows.map((r) => (
                <tr key={r.statementId} className="align-top">
                  <td className="max-w-md px-4 py-2.5">
                    <span className="flex gap-2">
                      <RefTag className="h-fit">{r.ref}</RefTag>
                      <span className="line-clamp-2">{r.text}</span>
                    </span>
                  </td>
                  {[r.criteria, r.positive, r.negative, r.edge].map((n, i) => (
                    <td key={i} className={cn('px-3 py-2.5 text-right tabular-nums', !n && 'text-slate')}>
                      {n || '—'}
                    </td>
                  ))}
                  <td className="px-4 py-2.5">{r.lastRun ? <ResultBar counts={r.lastRun} /> : <span className="text-slate">—</span>}</td>
                  <td className="px-4 py-2.5">
                    <Badge tone={STATUS[r.status].tone}>{STATUS[r.status].label}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}

function Stat({ label, value, suffix }: { label: string; value: number; suffix: string }) {
  return (
    <div className="rounded-xl border border-rule bg-field px-4 py-3">
      <p className="text-xs text-slate">{label}</p>
      <p className="mt-0.5 text-lg font-semibold tabular-nums">
        {value} <span className="text-sm font-normal text-slate">{suffix}</span>
      </p>
    </div>
  )
}

function ResultBar({ counts }: { counts: ResultCounts }) {
  const total = Math.max(1, counts.pass + counts.fail + counts.blocked + counts.skipped + counts.unmarked)
  const parts = (['pass', 'fail', 'blocked', 'skipped'] as const).filter((s) => counts[s])
  return (
    <div
      className="flex h-2 w-24 overflow-hidden rounded-full bg-ink/8"
      role="img"
      aria-label={parts.map((s) => `${counts[s]} ${RESULT[s].label.toLowerCase()}`).join(', ') || 'not run'}
    >
      {parts.map((s) => (
        <div key={s} className={RESULT[s].dot} style={{ width: `${(counts[s] / total) * 100}%` }} />
      ))}
    </div>
  )
}
