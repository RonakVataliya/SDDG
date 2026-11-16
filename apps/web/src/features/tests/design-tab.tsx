import { FlaskConicalIcon, SparklesIcon } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link } from 'react-router'
import type { TestRequirementSummary } from '@/api/client'
import { errorMessage } from '@/api/errors'
import { useStartCriteria, useTestJob, useTestRequirements } from '@/api/queries'
import { JobProgress } from '@/components/job-progress'
import { Badge, RefTag } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Notice } from '@/components/ui/notice'
import { PageLoading } from '@/components/ui/spinner'
import { cn, plural } from '@/lib/utils'
import { useWorkspace } from '@/routes/workspace-layout'
import { isConsentError, useConsentRetry } from './consent-retry'
import { RequirementDesign } from './requirement-design'

const AI_BATCH = 5 // the server sends AI request 1 five requirements at a time

/** Design tab: tick requirements, run AI request 1, then review each requirement's design on the right. */
export function DesignTab({ projectId }: { projectId: string }) {
  const { project } = useWorkspace()
  const canEdit = project.role !== 'viewer'
  const requirements = useTestRequirements(projectId)
  const start = useStartCriteria(projectId)
  const consent = useConsentRetry()
  const [ticked, setTicked] = useState<Set<string>>(new Set())
  const [focusedId, setFocusedId] = useState<string | null>(null)
  const [startedJobId, setStartedJobId] = useState<string | null>(null)

  const list = useMemo(() => requirements.data?.requirements ?? [], [requirements.data])
  const job = useTestJob(projectId, startedJobId ?? requirements.data?.active_job?.id)
  const busy = job.data?.status === 'queued' || job.data?.status === 'running' || job.data?.status === 'waiting'
  const focused = list.find((r) => r.statement_id === focusedId) ?? list.find((r) => ticked.has(r.statement_id)) ?? null
  const chosen = list.filter((r) => ticked.has(r.statement_id))
  const ambiguous = chosen.filter((r) => r.open_flags.includes('ambiguous'))

  if (requirements.isPending) return <PageLoading label="Loading requirements" />
  if (requirements.isError)
    return (
      <Notice tone="error" title="Couldn't load the requirements">
        {errorMessage(requirements.error)}
      </Notice>
    )
  if (!list.length)
    return (
      <Notice title="No requirements yet">
        Tests are built from requirements.{' '}
        <Link to="../input" className="font-medium underline">
          Add requirements
        </Link>
      </Notice>
    )

  const toggle = (id: string, on: boolean) =>
    setTicked((prev) => {
      const next = new Set(prev)
      if (on) next.add(id)
      else next.delete(id)
      return next
    })

  const generate = () =>
    consent.run(async () => {
      const ids = chosen.map((r) => r.statement_id)
      const started = await start.mutateAsync(ids)
      setStartedJobId(started.id)
      setFocusedId(ids[0])
    })

  return (
    <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[minmax(17rem,22rem)_minmax(0,1fr)]">
      <section aria-label="Requirements to test" className="flex min-h-0 flex-col rounded-lg border border-rule bg-surface">
        <header className="flex items-baseline justify-between border-b border-rule px-4 py-3">
          <h3 className="text-sm font-semibold">
            Requirements <span className="font-normal text-slate tabular-nums">{list.length}</span>
          </h3>
          <span className="text-xs text-slate">Tick what to test</span>
        </header>
        <ul className="min-h-0 flex-1 divide-y divide-rule overflow-y-auto">
          {list.map((r) => (
            <RequirementRow
              key={r.statement_id}
              requirement={r}
              ticked={ticked.has(r.statement_id)}
              focused={focused?.statement_id === r.statement_id}
              disabled={!canEdit || busy}
              onTick={(on) => toggle(r.statement_id, on)}
              onFocus={() => setFocusedId(r.statement_id)}
            />
          ))}
        </ul>
        <footer className="space-y-3 border-t border-rule p-3">
          {ambiguous.length > 0 && (
            <Notice tone="warning">
              {ambiguous.map((r) => r.ref).join(', ')} {ambiguous.length === 1 ? 'has' : 'have'} an open Ambiguous flag, so
              {ambiguous.length === 1 ? ' its' : ' their'} tests may be vague. You can still generate.
            </Notice>
          )}
          {start.isError && !isConsentError(start.error) && (
            <Notice tone="error" title="Couldn't start">
              {errorMessage(start.error)}
            </Notice>
          )}
          <div className="flex items-center justify-between gap-3">
            <span className="text-sm text-slate">{chosen.length} selected</span>
            {canEdit && (
              <Button size="sm" disabled={!chosen.length || busy || start.isPending} onClick={() => void generate()}>
                <SparklesIcon /> Generate criteria
              </Button>
            )}
          </div>
          {chosen.length > AI_BATCH && (
            <p className="text-xs text-slate">
              Sent to the AI in {Math.ceil(chosen.length / AI_BATCH)} requests of up to {AI_BATCH} requirements.
            </p>
          )}
        </footer>
      </section>

      <div className="min-w-0 space-y-4 overflow-y-auto">
        {job.data && busy && (
          <JobProgress job={job.data} title={job.data.kind === 'test_steps' ? 'Writing steps' : 'Generating criteria'} />
        )}
        {job.data?.status === 'failed' && startedJobId && (
          <Notice tone="error" title="Test generation failed">
            {job.data.error ?? 'Try again in a moment.'}
          </Notice>
        )}
        {focused ? (
          <RequirementDesign projectId={projectId} requirement={focused} canEdit={canEdit && !busy} />
        ) : (
          !busy && (
            <div className="grid min-h-60 place-items-center rounded-lg border border-dashed border-rule-strong p-8 text-center">
              <div>
                <FlaskConicalIcon className="mx-auto size-6 text-slate" />
                <p className="mt-2 font-medium">Pick requirements and generate</p>
                <p className="mt-1 max-w-sm text-sm text-slate">
                  SDDG writes acceptance criteria, then derives test cases with equivalence classes, boundary values and
                  use-case flows.
                </p>
              </div>
            </div>
          )
        )}
      </div>
      {consent.dialog}
    </div>
  )
}

function RequirementRow({
  requirement: r,
  ticked,
  focused,
  disabled,
  onTick,
  onFocus,
}: {
  requirement: TestRequirementSummary
  ticked: boolean
  focused: boolean
  disabled: boolean
  onTick: (on: boolean) => void
  onFocus: () => void
}) {
  return (
    <li className={cn('flex gap-3 px-4 py-3', focused && 'bg-teal-wash/60 shadow-[inset_3px_0_0_var(--color-teal)]')}>
      <Checkbox
        checked={ticked}
        disabled={disabled}
        onCheckedChange={(v) => onTick(v === true)}
        aria-label={`Select ${r.ref}`}
        className="mt-0.5"
      />
      <button type="button" onClick={onFocus} className="min-w-0 flex-1 text-left" aria-current={focused || undefined}>
        <span className="flex flex-wrap items-center gap-1.5">
          <RefTag>{r.ref}</RefTag>
          {r.label && <span className="text-xs text-slate">{r.label}</span>}
          {r.open_flags.includes('ambiguous') && <Badge tone="amber">Ambiguous</Badge>}
          {r.stale && <Badge tone="amber">Requirement changed</Badge>}
        </span>
        <span className="mt-1 line-clamp-2 block text-sm">{r.text}</span>
        {(r.designed || r.open_question) && (
          <span className="mt-1.5 flex flex-wrap gap-1">
            {r.criteria_count > 0 && <Badge>{plural(r.criteria_count, 'criterion', 'criteria')}</Badge>}
            {r.draft_count > 0 && <Badge>{plural(r.draft_count, 'draft')}</Badge>}
            {r.ready_count > 0 && <Badge tone="teal">{r.ready_count} ready</Badge>}
            {r.open_question && <Badge tone="violet">1 question</Badge>}
          </span>
        )}
      </button>
    </li>
  )
}
