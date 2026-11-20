import { useQueryClient } from '@tanstack/react-query'
import { ArrowRightIcon, CheckIcon, ClockIcon, LockIcon, XIcon } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, NavLink, useNavigate, useSearchParams } from 'react-router'
import type { DiagramType, Job } from '@/api/client'
import { errorMessage } from '@/api/errors'
import { keys, useDiagrams, useJob, useStartGeneration } from '@/api/queries'
import { DiagramGlyph } from '@/components/diagram-glyph'
import { JobProgress } from '@/components/job-progress'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogTitle } from '@/components/ui/dialog'
import { Notice } from '@/components/ui/notice'
import { PageLoading, Spinner } from '@/components/ui/spinner'
import { isConsentError, useConsentRetry } from '@/features/tests/consent-retry'
import { useCanEdit, useWorkspace } from '@/routes/workspace-layout'
import { cn, formatRelative, plural } from '@/lib/utils'
import { ALL_NODES, DIAGRAM_TYPES, NEEDS, NODE_LABEL, typeLabel } from './diagram-types'

// Package diagrams are drawn from the Design step, never generated here.
const PICKABLE = DIAGRAM_TYPES.filter((t) => t.value !== 'package')
const AVAILABLE = PICKABLE.filter((t) => t.available).map((t) => t.value)

/** Step 3: pick diagram types (FR9d), confirm, then follow the run here; the first diagram opens when it's done. */
export function GeneratePage() {
  const { project } = useWorkspace()
  const canEdit = useCanEdit()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [params, setParams] = useSearchParams()
  const jobId = params.get('job')
  const { data: job } = useJob(jobId)
  const [selected, setSelected] = useState<DiagramType[]>(['use_case'])
  const [confirmOpen, setConfirmOpen] = useState(false)
  const start = useStartGeneration(project.id)
  const diagrams = useDiagrams(project.id)
  const consent = useConsentRetry()

  // A run keeps going on the server when the user leaves this page; coming back shows it again.
  const runKey = `sddg.generation.${project.id}`
  useEffect(() => {
    const saved = sessionStorage.getItem(runKey)
    if (!jobId && saved) setParams({ job: saved }, { replace: true })
  }, [jobId, runKey, setParams])
  useEffect(() => {
    if (job?.status === 'succeeded' || job?.status === 'failed') sessionStorage.removeItem(runKey)
  }, [job?.status, runKey])

  useEffect(() => {
    if (job?.status !== 'succeeded') return
    void qc.invalidateQueries({ queryKey: keys.project(project.id), exact: true })
    void qc.invalidateQueries({ queryKey: keys.diagrams(project.id) })
    if (job.diagram_ids?.[0]) navigate(`../diagrams/${job.diagram_ids[0]}`, { replace: true })
  }, [job?.status, job?.diagram_ids, navigate, project.id, qc])

  if (!project.confirmed && !jobId) {
    return (
      <div className="p-7">
        <Notice tone="warning" title="Confirm the requirements first">
          Diagrams are built only from confirmed requirements.{' '}
          <Link to="../review" className="font-medium underline">
            Go to Review
          </Link>
        </Notice>
      </div>
    )
  }

  if (jobId && !job) return <PageLoading label="Loading run" />
  if (jobId && job) return <RunView job={job} onAgain={() => setParams({})} />

  const toggle = (t: DiagramType) => setSelected((s) => (s.includes(t) ? s.filter((x) => x !== t) : [...s, t]))
  const all = AVAILABLE.every((t) => selected.includes(t)) && selected.length === AVAILABLE.length

  return (
    <div className="mx-auto grid w-full max-w-[1400px] gap-6 p-4 sm:p-7 lg:grid-cols-[minmax(0,1fr)_380px]">
      <div>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold">Choose diagrams</h2>
            <p className="mt-1 text-[13px] text-slate">Pick any combination. Every shape links back to the requirement it came from.</p>
          </div>
          <Badge tone="success">
            <CheckIcon /> {plural(project.statement_count, 'requirement')} confirmed
          </Badge>
        </div>
        <fieldset className="mt-5 grid grid-cols-2 gap-3.5 md:grid-cols-3 xl:grid-cols-4">
          <legend className="sr-only">Diagram types</legend>
          {PICKABLE.map((t) => {
            const on = selected.includes(t.value) && t.available
            return (
              <label
                key={t.value}
                title={t.available ? t.shows : 'Not available yet'}
                className={cn(
                  'rounded-xl border bg-field p-3.5 transition-shadow',
                  t.available ? 'cursor-pointer hover:shadow-[var(--shadow)]' : 'cursor-not-allowed opacity-55',
                  on ? 'border-accent shadow-[0_0_0_1px_var(--accent)]' : 'border-rule',
                )}
              >
                <span className="grid-bg grid h-[100px] place-items-center rounded-lg bg-paper/60">
                  <DiagramGlyph type={t.value} className="h-20 w-36" />
                </span>
                <span className="mt-3 flex items-center gap-2">
                  <input
                    type="checkbox"
                    className="size-4 accent-[var(--accent)]"
                    checked={on}
                    disabled={!t.available}
                    onChange={() => toggle(t.value)}
                  />
                  <span className="text-[13.5px] font-semibold">{t.label}</span>
                  {!t.available && <Badge className="ml-auto">Coming soon</Badge>}
                </span>
                <span className="mt-0.5 block pl-6 text-[12px] text-slate">{t.available ? t.shows : 'Not available yet'}</span>
                <span className="mt-2 block pl-6 font-mono text-[11px] text-slate">needs {NEEDS[t.value].map((n) => NODE_LABEL[n]).join(', ')}</span>
              </label>
            )
          })}
          {AVAILABLE.length > 1 && (
            <button
              type="button"
              onClick={() => setSelected(all ? ['use_case'] : AVAILABLE)}
              className="grid place-items-center rounded-xl border-[1.5px] border-dashed border-rule-strong p-4 text-center text-[13px] text-slate hover:text-ink"
            >
              <span>
                <b className="block text-ink">{all ? 'Clear selection' : `Select all ${AVAILABLE.length}`}</b>
                Good for a full design review
              </span>
            </button>
          )}
        </fieldset>
      </div>

      <aside className="self-start rounded-xl border border-rule bg-surface p-5">
        <h3 className="font-sans text-[15px] font-semibold tracking-normal">Your selection</h3>
        <p className="mt-0.5 text-[12px] text-slate">
          From {plural(project.statement_count, 'confirmed requirement')}
          {project.confirmed_at && ` · confirmed ${formatRelative(project.confirmed_at)}`}
        </p>
        <ul className="mt-4 space-y-2 text-[13px]">
          {selected.length === 0 && <li className="text-slate">Nothing selected yet.</li>}
          {selected.map((t) => (
            <li key={t} className="flex items-center gap-2">
              <CheckIcon className="size-3.5" /> {typeLabel[t]}
            </li>
          ))}
        </ul>
        <ExtractPlan selected={selected} done={project.extracted_nodes ?? []} />
        {start.isError && !isConsentError(start.error) && (
          <Notice tone="error" className="mt-3" title="Couldn't start generation">
            {errorMessage(start.error)}
          </Notice>
        )}
        <Button size="lg" className="mt-5 w-full" disabled={!canEdit || selected.length === 0 || start.isPending} onClick={() => setConfirmOpen(true)}>
          Extract &amp; draw {selected.length === 1 ? `${typeLabel[selected[0]]} diagram` : plural(selected.length, 'diagram')}
          <ArrowRightIcon />
        </Button>

        <div className="mt-6 border-t border-rule pt-4">
          <h3 className="font-sans text-[13.5px] font-semibold tracking-normal">Your diagrams</h3>
          {diagrams.data?.length ? (
            <ul aria-label="Your diagrams" className="mt-2 space-y-1">
              {diagrams.data.map((d) => (
                <li key={d.id}>
                  <NavLink
                    to={`../diagrams/${d.id}`}
                    className={({ isActive }) =>
                      cn('flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-[13px] hover:bg-ink/5', isActive && 'bg-accent-wash text-accent-deep')
                    }
                  >
                    <DiagramGlyph type={d.type} className="h-6 w-10 shrink-0" />
                    <span className="min-w-0">
                      <span className="flex items-center gap-1.5 font-medium">
                        {typeLabel[d.type]}
                        {d.out_of_date && <Badge tone="amber">Out of date</Badge>}
                      </span>
                      <span className="block truncate text-[11.5px] text-slate">
                        {d.instruction ? `Edited: “${d.instruction}”` : d.type === 'package' ? 'From the Design step' : 'Generated'} · {formatRelative(d.created_at)}
                      </span>
                    </span>
                  </NavLink>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-1 text-[12.5px] text-slate">Diagrams you generate will appear here.</p>
          )}
          {project.item_count > 0 && (
            <Link to="../items" className="mt-3 block rounded-lg border border-dashed border-rule-strong px-2.5 py-2 text-[13px] hover:bg-ink/5">
              <span className="block font-medium">Building blocks</span>
              <span className="block text-[11.5px] text-slate">Check the extracted items (optional)</span>
            </Link>
          )}
        </div>
      </aside>
      {consent.dialog}

      {/* FR9d: the selection is confirmed explicitly and cannot change while the run is going. */}
      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent>
          <DialogTitle>Generate these diagrams?</DialogTitle>
          <DialogDescription>The selection is locked once generation starts. To change it, start a new run afterwards.</DialogDescription>
          <ul className="mt-4 space-y-1.5 text-[13px]">
            {selected.map((t) => (
              <li key={t} className="flex items-center gap-2">
                <LockIcon className="size-3.5 text-slate" aria-hidden /> {typeLabel[t]}
              </li>
            ))}
          </ul>
          <DialogFooter>
            <Button variant="secondary" onClick={() => setConfirmOpen(false)}>
              Back
            </Button>
            <Button
              disabled={start.isPending}
              onClick={async () => {
                const types = selected.filter((t) => AVAILABLE.includes(t))
                setConfirmOpen(false)
                // X8: a 403 consent_required opens the consent dialog and the run starts once the user agrees.
                await consent
                  .run(async () => {
                    const job = await start.mutateAsync(types)
                    sessionStorage.setItem(runKey, job.id)
                    setParams({ job: job.id })
                  })
                  .catch(() => undefined)
              }}
            >
              {start.isPending && <Spinner className="text-on-ink" label="Starting" />}
              Start generating
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

/** What the AI will extract for this selection, what it can reuse, and what it skips. */
function ExtractPlan({ selected, done }: { selected: DiagramType[]; done: string[] }) {
  const needed = new Set(selected.flatMap((t) => NEEDS[t]))
  const run = ALL_NODES.filter((n) => needed.has(n) && !done.includes(n))
  const reuse = ALL_NODES.filter((n) => needed.has(n) && done.includes(n))
  const skip = ALL_NODES.filter((n) => !needed.has(n))
  return (
    <div className="mt-5 rounded-[10px] bg-paper p-3.5">
      <p className="text-[12px] font-semibold">The AI will extract</p>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {run.length === 0 && <span className="text-[12px] text-slate">Nothing new; everything needed is already extracted.</span>}
        {run.map((n) => (
          <Badge key={n} tone="accent">{NODE_LABEL[n]}</Badge>
        ))}
        {reuse.map((n) => (
          <Badge key={n} tone="success" title="Already extracted; reused">
            <CheckIcon /> {NODE_LABEL[n]}
          </Badge>
        ))}
        {skip.map((n) => (
          <Badge key={n} className="line-through opacity-60" title="Not needed by your selection">
            {NODE_LABEL[n]}
          </Badge>
        ))}
      </div>
      {skip.length > 0 && selected.length > 0 && <p className="mt-2 text-[11.5px] text-slate">Crossed-out ones are skipped: none of your picks need them.</p>}
      <p className="mt-2 text-[11.5px] text-slate">About 30–60 seconds. The selection is locked once it starts.</p>
    </div>
  )
}

/** Step 1 of a run extracts the building blocks; then each type is drawn and its id published as soon as it's ready. */
function RunView({ job, onAgain }: { job: Job; onAgain: () => void }) {
  const types = job.diagram_types ?? []
  const ready = job.diagram_ids ?? []
  // 'waiting' = the AI provider hit its rate limit; the run resumes by itself, so it counts as running.
  const active = job.status === 'running' || job.status === 'waiting'
  const extracting = active && job.progress.step <= 1
  const current = active ? job.progress.step - 2 : -1
  const stateOf = (i: number) =>
    i < ready.length ? 'done' : job.status === 'queued' ? 'queued' : job.status === 'failed' ? (job.error?.includes(typeLabel[types[i]]) ? 'failed' : 'stopped') : extracting ? 'blocks' : i === current ? 'running' : 'waiting'

  return (
    <div className="mx-auto grid w-full max-w-[1400px] gap-6 p-4 sm:p-7 lg:grid-cols-2">
      <div className="self-start">
        <JobProgress job={job} title={job.status === 'failed' ? 'This run stopped' : extracting ? 'Extracting building blocks' : 'Drawing your diagrams'}>
          {job.status === 'failed' ? (
            <Button variant="secondary" onClick={onAgain}>
              Choose again
            </Button>
          ) : (
            !extracting &&
            job.status !== 'queued' && (
              <p className="text-[13px] text-slate">
                Want to check them?{' '}
                <Link to="../items" className="font-medium text-accent hover:underline">
                  Review extracted items (optional)
                </Link>
              </p>
            )
          )}
        </JobProgress>
      </div>
      <section className="self-start rounded-xl border border-rule bg-surface p-6">
        <h2 className="text-xl font-semibold">Diagrams</h2>
        <p className="mt-0.5 text-[12px] text-slate">Each one opens as soon as it is drawn.</p>
        <ul className="mt-4 space-y-3">
          {types.map((t, i) => {
            const s = stateOf(i)
            return (
              <li key={t} className="flex items-center gap-3 rounded-[10px] border border-rule bg-field p-3">
                <DiagramGlyph type={t} className="h-10 w-16" />
                <span className="min-w-0 flex-1">
                  <span className="block text-[13.5px] font-semibold">{typeLabel[t]}</span>
                  <span className={cn('block text-[12px]', s === 'done' ? 'text-success' : s === 'running' || s === 'blocks' ? 'text-accent' : s === 'failed' ? 'text-danger' : 'text-slate')}>
                    {{ done: 'Ready', running: 'Drawing…', blocks: 'Waiting for building blocks', waiting: 'Waiting', queued: job.queue_position ? `Queued, position ${job.queue_position}` : 'Queued', failed: 'Failed', stopped: 'Not drawn' }[s]}
                  </span>
                </span>
                {s === 'done' ? (
                  <Button asChild variant="secondary" size="sm">
                    <Link to={`../diagrams/${ready[i]}`}>Open</Link>
                  </Button>
                ) : s === 'running' ? (
                  <Spinner label="Drawing" />
                ) : s === 'failed' ? (
                  <XIcon className="size-4 text-danger" />
                ) : (
                  <ClockIcon className="size-4 text-slate" />
                )}
              </li>
            )
          })}
        </ul>
      </section>
    </div>
  )
}
