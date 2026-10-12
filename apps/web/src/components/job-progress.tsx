import { useEffect, useState } from 'react'
import type { Job } from '@/api/client'
import { Spinner } from '@/components/ui/spinner'
import { cn } from '@/lib/utils'

/** FR10g: status of a queued/running job (extraction or generation), from polling GET /jobs/{id}. */
export function JobProgress({ job, title }: { job: Job; title: string }) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    if (job.status !== 'queued' && job.status !== 'running') return
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [job.status])

  const { step, total, label } = job.progress
  const pct = job.status === 'succeeded' ? 100 : total ? Math.max(4, (step / total) * 100) : 4
  const startedAt = job.started_at ?? job.created_at
  const elapsed = startedAt ? Math.max(0, Math.round(((job.finished_at ? new Date(job.finished_at).getTime() : now) - new Date(startedAt).getTime()) / 1000)) : 0

  return (
    <div className="rounded-lg border border-rule bg-surface p-5" aria-live="polite">
      <div className="flex items-center gap-3">
        {(job.status === 'queued' || job.status === 'running') && <Spinner label={title} />}
        <p className="font-medium">{title}</p>
        <span className="ml-auto text-sm text-slate tabular-nums">{elapsed}s</span>
      </div>
      <div
        className="mt-4 h-1.5 overflow-hidden rounded-full bg-ink/8"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={step}
        aria-label={label}
      >
        <div
          className={cn('h-full rounded-full transition-[width] duration-700', job.status === 'failed' ? 'bg-danger' : 'bg-teal')}
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="mt-3 text-sm text-slate">
        {job.status === 'queued'
          ? `Queued${job.queue_position ? `, position ${job.queue_position}` : ''}. It will start shortly.`
          : job.status === 'failed'
            ? (job.error ?? 'The job failed.')
            : `${label}${job.status === 'running' && total ? ` (step ${step} of ${total})` : ''}`}
      </p>
    </div>
  )
}
