import { PlayIcon } from 'lucide-react'
import { useState } from 'react'
import type { TestRunSummary } from '@/api/client'
import { errorMessage } from '@/api/errors'
import { useTestCases, useTestRun, useTestRuns } from '@/api/queries'
import { Badge, RefTag } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Notice } from '@/components/ui/notice'
import { PageLoading } from '@/components/ui/spinner'
import { cn, formatDate } from '@/lib/utils'
import { useWorkspace } from '@/routes/workspace-layout'
import { RESULT, RUN_MODE } from './labels'
import { RunRunner } from './run-runner'
import { StartRunDialog } from './start-run-dialog'

/** Runs tab: the record of manual runs. Start a run, continue an open one, read the notes of the last one. */
export function RunsTab({ projectId }: { projectId: string }) {
  const { project } = useWorkspace()
  const canEdit = project.role !== 'viewer'
  const runs = useTestRuns(projectId)
  const cases = useTestCases(projectId)
  const [openRunId, setOpenRunId] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)
  const latestFinished = runs.data?.find((r) => r.finished_at) ?? null
  const latest = useTestRun(projectId, latestFinished?.id ?? null)
  const readyCount = (cases.data ?? []).filter((c) => c.status === 'ready' && c.kept).length

  if (openRunId) return <RunRunner projectId={projectId} runId={openRunId} onClose={() => setOpenRunId(null)} />
  if (runs.isPending) return <PageLoading label="Loading runs" />
  if (runs.isError)
    return (
      <Notice tone="error" title="Couldn't load the runs">
        {errorMessage(runs.error)}
      </Notice>
    )

  const tally = latestFinished?.tally
  const notes = (latest.data?.items ?? []).filter((i) => i.result?.note)

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4" aria-label={latestFinished ? `Results of ${latestFinished.name}` : 'No finished run yet'}>
        {(['pass', 'fail', 'blocked', 'skipped'] as const).map((s) => (
          <div key={s} className="rounded-xl border border-rule bg-field px-4 py-3">
            <p className="text-xs text-slate">{s === 'pass' ? 'Passed' : s === 'fail' ? 'Failed' : s === 'blocked' ? 'Blocked' : 'Skipped'}</p>
            <p
              className={cn(
                'text-3xl font-semibold tabular-nums',
                s === 'pass' && 'text-accent-deep',
                s === 'fail' && tally?.fail && 'text-danger',
                s === 'blocked' && tally?.blocked && 'text-amber',
              )}
            >
              {tally ? tally[s] : '—'}
            </p>
          </div>
        ))}
      </div>

      <section aria-label="Runs" className="overflow-hidden rounded-xl border border-rule bg-field">
        <header className="flex items-center justify-between border-b border-rule px-4 py-2.5">
          <h3 className="text-sm font-semibold">Runs</h3>
          {canEdit && (
            <Button size="sm" disabled={!readyCount} onClick={() => setStarting(true)} title={readyCount ? undefined : 'Write steps for some cases first'}>
              <PlayIcon /> Start run
            </Button>
          )}
        </header>
        {!runs.data.length ? (
          <p className="px-5 py-8 text-center text-sm text-slate">
            {readyCount ? 'No runs yet. Start one to record results.' : 'No case is ready to run. Write steps on the Design tab first.'}
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-rule text-xs text-slate">
                <tr>
                  {['Run', 'Mode', 'Cases', 'Result', 'By', 'Finished'].map((h) => (
                    <th key={h} scope="col" className="px-4 py-2 font-medium">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-rule">
                {runs.data.map((r) => (
                  <RunRow key={r.id} run={r} onOpen={() => setOpenRunId(r.id)} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {notes.length > 0 && latestFinished && (
        <section aria-label="Notes from the last run" className="rounded-xl border border-rule bg-field px-4 py-3">
          <h4 className="text-xs font-semibold tracking-wide text-slate uppercase">Notes from {latestFinished.name}</h4>
          <ul className="mt-2 space-y-1.5 text-sm">
            {notes.map(({ case: c, result }) => (
              <li key={c.id} className="flex flex-wrap items-center gap-2">
                <RefTag>{c.number}</RefTag>
                <Badge tone={RESULT[result!.status].tone}>{RESULT[result!.status].label}</Badge>
                {result!.note}
              </li>
            ))}
          </ul>
        </section>
      )}

      {starting && (
        <StartRunDialog
          projectId={projectId}
          runCount={runs.data.length}
          onOpenChange={setStarting}
          onStarted={(id) => {
            setStarting(false)
            setOpenRunId(id)
          }}
        />
      )}
    </div>
  )
}

function RunRow({ run: r, onOpen }: { run: TestRunSummary; onOpen: () => void }) {
  const total = Math.max(1, r.case_count)
  const parts = (['pass', 'fail', 'blocked', 'skipped'] as const).filter((s) => r.tally[s])
  return (
    <tr className="hover:bg-paper/60">
      <td className="px-4 py-2.5">
        <button type="button" className="font-medium hover:underline" onClick={onOpen}>
          {r.name}
        </button>
      </td>
      <td className="px-4 py-2.5 text-slate">{RUN_MODE[r.mode].label}</td>
      <td className="px-4 py-2.5 tabular-nums">{r.case_count}</td>
      <td className="px-4 py-2.5">
        <div className="flex items-center gap-2">
          <div className="flex h-2 w-28 overflow-hidden rounded-full bg-ink/8" aria-hidden>
            {parts.map((s) => (
              <div key={s} className={RESULT[s].dot} style={{ width: `${(r.tally[s] / total) * 100}%` }} />
            ))}
          </div>
          <span className="text-xs whitespace-nowrap text-slate">
            {parts.map((s) => `${r.tally[s]} ${RESULT[s].label.toLowerCase()}`).join(' · ') || 'nothing marked'}
          </span>
        </div>
      </td>
      <td className="px-4 py-2.5 text-slate">{r.created_by}</td>
      <td className="px-4 py-2.5 whitespace-nowrap">
        {r.finished_at ? (
          formatDate(r.finished_at)
        ) : (
          <Button variant="link" size="sm" onClick={onOpen}>
            Continue
          </Button>
        )}
      </td>
    </tr>
  )
}
