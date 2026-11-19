import { ArrowLeftIcon, BanIcon, CheckIcon, SkipForwardIcon, XIcon } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { ResultStatus, TestRun } from '@/api/client'
import { errorMessage } from '@/api/errors'
import { useFinishRun, useMarkResult, useTestRun } from '@/api/queries'
import { Badge, RefTag } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/input'
import { Notice } from '@/components/ui/notice'
import { PageLoading } from '@/components/ui/spinner'
import { cn, formatRelative } from '@/lib/utils'
import { CaseBody } from './case-detail'
import { KIND, RESULT } from './labels'

const BUTTONS: { status: ResultStatus; key: string; Icon: typeof CheckIcon }[] = [
  { status: 'pass', key: '1', Icon: CheckIcon },
  { status: 'fail', key: '2', Icon: XIcon },
  { status: 'blocked', key: '3', Icon: BanIcon },
  { status: 'skipped', key: '4', Icon: SkipForwardIcon },
]

/** Runs one manual run: pick a case on the left, follow its steps, mark it. Keys 1-4 mark the open case. */
export function RunRunner({ projectId, runId, onClose }: { projectId: string; runId: string; onClose: () => void }) {
  const run = useTestRun(projectId, runId)
  if (run.isPending) return <PageLoading label="Loading the run" />
  if (run.isError)
    return (
      <Notice tone="error" title="Couldn't load this run">
        {errorMessage(run.error)}
      </Notice>
    )
  return <Runner projectId={projectId} run={run.data} onClose={onClose} />
}

function Runner({ projectId, run, onClose }: { projectId: string; run: TestRun; onClose: () => void }) {
  const mark = useMarkResult(projectId, run.id)
  const finish = useFinishRun(projectId)
  const firstOpen = Math.max(0, run.items.findIndex((i) => !i.result))
  const [index, setIndex] = useState(firstOpen)
  const item = run.items[Math.min(index, run.items.length - 1)]
  const [note, setNote] = useState(item?.result?.note ?? '')
  const finished = !!run.finished_at
  const marked = run.items.filter((i) => i.result).length

  useEffect(() => setNote(item?.result?.note ?? ''), [item?.case.id, item?.result?.note])

  const record = (status: ResultStatus) => {
    if (!item || finished) return
    mark.mutate(
      { caseId: item.case.id, status, note: note.trim() || null },
      {
        onSuccess: () => {
          const next = run.items.findIndex((i, n) => n > index && !i.result)
          if (next !== -1) setIndex(next)
        },
      },
    )
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement
      if (target.closest('input, textarea, select, [role="dialog"]') || e.metaKey || e.ctrlKey) return
      const hit = BUTTONS.find((b) => b.key === e.key)
      if (hit) record(hit.status)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  return (
    <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[17rem_minmax(0,1fr)]">
      <section aria-label="Cases in this run" className="flex min-h-0 flex-col rounded-xl border border-rule bg-field">
        <header className="border-b border-rule px-3 py-2.5">
          <Button variant="ghost" size="sm" className="-ml-2" onClick={onClose}>
            <ArrowLeftIcon /> All runs
          </Button>
          <p className="mt-1 font-semibold">{run.name}</p>
          <p className="text-xs text-slate">
            {marked} of {run.case_count} marked{finished && ' · finished'}
          </p>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-ink/8" aria-hidden>
            <div className="h-full bg-accent" style={{ width: `${(marked / Math.max(1, run.case_count)) * 100}%` }} />
          </div>
        </header>
        <ol className="min-h-0 flex-1 overflow-y-auto py-1">
          {run.items.map((i, n) => (
            <li key={i.case.id}>
              <button
                type="button"
                onClick={() => setIndex(n)}
                aria-current={n === index || undefined}
                className={cn('flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-paper', n === index && 'bg-accent-wash/70')}
              >
                <span className={cn('size-2 shrink-0 rounded-full', i.result ? RESULT[i.result.status].dot : 'border border-rule-strong')} />
                <span className="font-mono text-xs">{i.case.number}</span>
                <span className="min-w-0 truncate">{i.case.title}</span>
              </button>
            </li>
          ))}
        </ol>
      </section>

      {item && (
        <section aria-label={`Case ${item.case.number}`} className="min-w-0 space-y-4 overflow-y-auto rounded-xl border border-rule bg-field p-5">
          <div className="flex flex-wrap items-center gap-2">
            <RefTag>{item.case.number}</RefTag>
            <Badge>{item.case.technique}</Badge>
            <Badge tone={KIND[item.case.kind].tone}>{KIND[item.case.kind].label}</Badge>
            {item.case.freshness === 'out_of_date' && <Badge tone="amber">Out of date</Badge>}
            <span className="ml-auto text-sm text-slate tabular-nums">
              {index + 1} of {run.items.length}
            </span>
          </div>
          <h3 className="text-lg font-semibold tracking-tight">
            {item.case.statement_ref} · {item.case.title}
          </h3>
          <CaseBody c={item.case} />
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4" role="group" aria-label="Mark this case">
            {BUTTONS.map(({ status, key, Icon }) => {
              const active = item.result?.status === status
              return (
                <Button
                  key={status}
                  variant="secondary"
                  disabled={finished || mark.isPending}
                  onClick={() => record(status)}
                  aria-pressed={active}
                  className={cn(
                    'justify-between',
                    active && status === 'pass' && 'border-accent bg-accent text-on-ink hover:bg-accent-deep',
                    active && status === 'fail' && 'border-danger bg-danger text-on-ink hover:bg-danger/90',
                    active && status === 'blocked' && 'border-amber bg-amber text-on-ink hover:bg-amber/90',
                    active && status === 'skipped' && 'border-slate bg-slate text-on-ink hover:bg-slate/90',
                  )}
                >
                  <span className="inline-flex items-center gap-2">
                    <Icon /> {RESULT[status].label}
                  </span>
                  <kbd className="rounded-sm border border-current/30 px-1 font-mono text-[11px] opacity-70">{key}</kbd>
                </Button>
              )
            })}
          </div>
          <Textarea
            aria-label="Note"
            placeholder="Note (optional): what you saw, why it is blocked…"
            className="min-h-16"
            value={note}
            disabled={finished}
            onChange={(e) => setNote(e.target.value)}
          />
          {mark.isError && <p className="text-sm text-danger">{errorMessage(mark.error)}</p>}
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate">
            <span>
              {item.result ? `Marked ${RESULT[item.result.status].label} by ${item.result.marked_by} · ${formatRelative(item.result.marked_at)}` : 'Not marked yet'}
            </span>
            {!finished && (
              <Button size="sm" disabled={finish.isPending} onClick={() => finish.mutate(run.id, { onSuccess: onClose })}>
                Finish run
              </Button>
            )}
          </div>
        </section>
      )}
    </div>
  )
}
