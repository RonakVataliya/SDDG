import { ClockIcon, SparklesIcon, XIcon } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import type { Job } from '@/api/client'
import { cn } from '@/lib/utils'

const AI_SLOTS = 5 // NFR9a: the API runs at most 5 AI jobs at once

/** FR10g: status of a queued/running/failed job (extraction or generation), from polling GET /jobs/{id}. */
export function JobProgress({ job, title, children }: { job: Job; title: string; children?: ReactNode }) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    if (job.status !== 'queued' && job.status !== 'running' && job.status !== 'waiting') return
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [job.status])

  const { step, total, label } = job.progress
  const pct = job.status === 'succeeded' ? 100 : total ? Math.max(4, (step / total) * 100) : 4
  const startedAt = job.started_at ?? job.created_at
  const end = job.finished_at ? new Date(job.finished_at).getTime() : now
  const elapsed = startedAt ? Math.max(0, Math.round((end - new Date(startedAt).getTime()) / 1000)) : 0
  const clock = `${Math.floor(elapsed / 60)}:${String(elapsed % 60).padStart(2, '0')}`
  const queued = job.status === 'queued'
  const failed = job.status === 'failed'
  const ahead = Math.max(0, (job.queue_position ?? 1) - 1)

  return (
    <div className="ticks rounded-xl border border-rule bg-field p-7" aria-live="polite">
      <div className="flex items-start gap-3">
        <span
          className={cn(
            'grid size-9 shrink-0 place-items-center rounded-full border-[1.5px]',
            failed ? 'border-danger bg-danger-wash text-danger' : 'border-accent text-accent',
          )}
        >
          {failed ? <XIcon className="size-4" /> : queued ? <ClockIcon className="size-4" /> : <SparklesIcon className="size-4" />}
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="text-xl font-semibold">
            {queued ? `Queued${job.queue_position ? `, position ${job.queue_position}` : ''}` : title}
          </h2>
          <p className={cn('text-[13px]', failed ? 'text-danger' : 'text-slate')}>
            {queued
              ? ahead > 0
                ? `All AI slots are busy. Yours starts after ${ahead} more ${ahead === 1 ? 'job' : 'jobs'}.`
                : 'All AI slots are busy. Yours is next.'
              : failed
                ? (job.error ?? 'The job failed.')
                : job.status === 'waiting' // the AI provider's rate limit; the job resumes by itself
                  ? (
                      <>
                        <span>{`${label}. The AI provider's rate limit was reached; this continues by itself.`}</span> · {clock}
                      </>
                    )
                  : `${label}${total ? ` · step ${step} of ${total}` : ''} · ${clock}`}
          </p>
        </div>
      </div>

      {queued ? (
        <div className="mt-6" aria-hidden>
          <div className="flex gap-2">
            {Array.from({ length: AI_SLOTS }, (_, i) => (
              <span key={i} className="grid h-9 flex-1 place-items-center rounded-lg bg-ink font-mono text-[11px] text-slate">
                busy
              </span>
            ))}
            <span className="w-4" />
            {Array.from({ length: Math.min(ahead, 3) }, (_, i) => (
              <span key={i} className="grid h-9 w-16 place-items-center rounded-lg border-[1.5px] border-dashed border-rule-strong font-mono text-[11px] text-slate">
                #{i + 1}
              </span>
            ))}
            <span className="grid h-9 w-16 place-items-center rounded-lg border-[1.5px] border-accent bg-accent-wash font-mono text-[11px] text-accent">you</span>
          </div>
          <div className="mt-2 flex justify-between text-[11.5px] text-slate">
            <span>{AI_SLOTS} of {AI_SLOTS} AI slots in use</span>
            <span>Waiting line</span>
          </div>
        </div>
      ) : (
        !failed && (
          <div
            className="mt-6 h-1.5 overflow-hidden rounded-full bg-rule"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={total}
            aria-valuenow={step}
            aria-label={label}
          >
            <div className="h-full rounded-full bg-accent transition-[width] duration-700" style={{ width: `${pct}%` }} />
          </div>
        )
      )}
      {children && <div className="mt-6">{children}</div>}
    </div>
  )
}
