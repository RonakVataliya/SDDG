import { CheckIcon, ChevronRightIcon, LockIcon } from 'lucide-react'
import { Fragment } from 'react'
import { Link, Navigate, NavLink, Outlet, useLocation, useOutletContext, useParams } from 'react-router'
import type { Project } from '@/api/client'
import { ApiError, errorMessage } from '@/api/errors'
import { useDiagrams, useFlagSummary, useProject } from '@/api/queries'
import { Badge } from '@/components/ui/badge'
import { Notice } from '@/components/ui/notice'
import { PageLoading, Spinner } from '@/components/ui/spinner'
import { projectStage } from '@/features/projects/stage'
import { cn, plural } from '@/lib/utils'
import { NotFoundPage } from './not-found-page'

type StepState = 'done' | 'open' | 'locked' | 'working'
type Step = { n: number; to: string; label: string; state: StepState }

function buildSteps(project: Project, latestDiagramId?: string): Step[] {
  const stage = projectStage(project)
  return [
    { n: 1, to: 'input', label: 'Requirements', state: stage === 'extracting' ? 'working' : project.statement_count ? 'done' : 'open' },
    { n: 2, to: 'review', label: 'Review', state: project.confirmed ? 'done' : project.statement_count ? 'open' : 'locked' },
    { n: 3, to: 'generate', label: 'Choose diagrams', state: project.confirmed ? (project.diagram_count ? 'done' : 'open') : 'locked' },
    { n: 4, to: latestDiagramId ? `diagrams/${latestDiagramId}` : 'generate', label: 'Diagrams', state: latestDiagramId ? 'done' : 'locked' },
  ]
}

/** The 4 steps drawn as a tiny flow diagram: nodes joined by arrows, dashed once the path is locked. */
function Pipeline({ steps }: { steps: Step[] }) {
  return (
    <nav aria-label="Project steps" className="overflow-x-auto">
      <ol className="flex items-center">
        {steps.map((s, i) => {
          const locked = s.state === 'locked'
          const node = (current: boolean) => (
            <>
              <span
                className={cn(
                  'grid size-7 shrink-0 place-items-center rounded-full border-[1.5px] font-mono text-[11px] font-semibold',
                  current
                    ? 'border-accent bg-accent text-white shadow-[0_0_0_4px_var(--accent-wash)]'
                    : s.state === 'done'
                      ? 'border-ink text-ink'
                      : locked
                        ? 'border-dashed border-rule-strong text-slate'
                        : 'border-rule-strong bg-field text-slate',
                )}
              >
                {s.state === 'working' ? (
                  <Spinner className={cn('size-3.5', current && 'text-white')} label="In progress" />
                ) : s.state === 'done' && !current ? (
                  <CheckIcon className="size-3.5" strokeWidth={3} aria-label="Done" />
                ) : locked && !current ? (
                  <LockIcon className="size-3" aria-label="Locked" />
                ) : (
                  String(s.n).padStart(2, '0')
                )}
              </span>
              <span className={cn('text-[13px] whitespace-nowrap', current ? 'font-semibold text-ink' : s.state === 'done' ? 'text-ink-2' : 'text-slate')}>
                {s.label}
              </span>
            </>
          )
          const next = steps[i + 1]
          return (
            <Fragment key={s.label}>
              <li>
                {locked ? (
                  <span aria-disabled className="flex cursor-not-allowed items-center gap-2.5 px-1 py-1">
                    {node(false)}
                  </span>
                ) : (
                  <NavLink to={s.to} className="flex items-center gap-2.5 rounded-full px-1 py-1 hover:bg-ink/5">
                    {({ isActive }) => node(isActive)}
                  </NavLink>
                )}
              </li>
              {next && (
                <li aria-hidden className="mx-3 flex items-center">
                  <span className={cn('h-[1.5px] w-10', next.state === 'locked' ? 'bg-[repeating-linear-gradient(90deg,var(--rule-strong)_0_5px,transparent_5px_9px)]' : 'bg-ink')} />
                  <span className={cn('border-y-4 border-l-[6px] border-y-transparent', next.state === 'locked' ? 'border-l-rule-strong' : 'border-l-ink')} />
                </li>
              )}
            </Fragment>
          )
        })}
      </ol>
    </nav>
  )
}

type Area = { to: string; label: string; locked?: string }

/** Areas beyond the 4-step pipeline: same visual language, one quieter row under the pipeline header. */
function buildAreas(project: Project): Area[] {
  const stage = projectStage(project)
  const areas: Area[] = [
    // Tests work straight from the requirements, so they do not wait for diagrams.
    { to: 'tests', label: 'Tests', locked: project.statement_count && stage !== 'extracting' ? undefined : 'Locked until requirements exist' },
    { to: 'backlog', label: 'Backlog' },
    { to: 'items', label: 'Building blocks', locked: project.item_count > 0 ? undefined : 'Nothing extracted yet' },
    { to: 'search', label: 'Search' },
  ]
  return areas
}

function AreaNav({ areas }: { areas: Area[] }) {
  return (
    <nav aria-label="Project areas" className="overflow-x-auto">
      <ul className="flex items-center gap-1">
        {areas.map((a) => (
          <li key={a.to}>
            {a.locked ? (
              <span
                aria-disabled
                title={a.locked}
                className="flex cursor-not-allowed items-center gap-1.5 rounded-full px-3 py-1.5 text-[13px] whitespace-nowrap text-slate opacity-70"
              >
                <LockIcon className="size-3" aria-label="Locked" /> {a.label}
              </span>
            ) : (
              <NavLink
                to={a.to}
                className={({ isActive }) =>
                  cn(
                    'block rounded-full px-3 py-1.5 text-[13px] whitespace-nowrap',
                    isActive ? 'bg-accent-wash font-semibold text-accent-deep' : 'text-ink-2 hover:bg-ink/5 hover:text-ink',
                  )
                }
              >
                {a.label}
              </NavLink>
            )}
          </li>
        ))}
      </ul>
    </nav>
  )
}

/** Pages that came from the older panel layout get the same card frame the pipeline pages draw themselves. */
const FRAMED = ['tests', 'design', 'backlog', 'coverage', 'search', 'settings']

export type WorkspaceContext = { project: Project }
export const useWorkspace = () => useOutletContext<WorkspaceContext>()

export function WorkspaceLayout() {
  const { projectId = '' } = useParams()
  const { data: project, isPending, error } = useProject(projectId)
  const { data: diagrams } = useDiagrams(projectId)
  const { data: flagSummary } = useFlagSummary(projectId)
  const { pathname } = useLocation()
  const area = pathname.split('/')[3] ?? ''

  if (isPending) return <PageLoading label="Loading project" />
  if (error instanceof ApiError && error.status === 404) return <NotFoundPage />
  if (!project)
    return (
      <div className="mx-auto max-w-4xl px-4 py-10">
        <Notice tone="error" title="Couldn't load this project">
          {errorMessage(error)}
        </Notice>
      </div>
    )

  const openFlags = (flagSummary ?? []).reduce((n, s) => n + s.open, 0)
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-wrap items-center gap-x-8 gap-y-3 border-b border-rule bg-surface px-4 py-3.5 sm:px-7">
        <div className="min-w-0">
          <div className="flex min-w-0 items-center gap-1.5 text-[13px] text-slate">
            <Link to="/projects" className="hover:text-ink hover:underline">
              Projects
            </Link>
            <ChevronRightIcon className="size-3.5" aria-hidden />
          </div>
          <div className="flex min-w-0 items-center gap-2">
            <h1 className="truncate text-[20px] leading-tight font-semibold">{project.name}</h1>
            <Badge className="capitalize">{project.role}</Badge>
            {project.archived_at && <Badge tone="amber">Archived</Badge>}
          </div>
          <p className="mt-0.5 text-[12.5px] text-slate">
            {plural(project.statement_count, project.confirmed ? 'confirmed requirement' : 'requirement')}
            {project.diagram_count > 0 && ` · ${plural(project.diagram_count, 'diagram')}`}
            {openFlags > 0 && <span className="text-amber"> · {plural(openFlags, 'open flag')}</span>}
          </p>
        </div>
        <div className="ml-auto">
          <Pipeline steps={buildSteps(project, diagrams?.[0]?.id)} />
        </div>
      </div>
      <div className="border-b border-rule bg-surface px-3 py-1.5 sm:px-6">
        <AreaNav areas={buildAreas(project)} />
      </div>
      <div className="relative flex min-h-0 flex-1 flex-col">
        {FRAMED.includes(area) ? (
          <div className="mx-auto flex w-full max-w-[1400px] min-h-0 flex-1 flex-col p-4 sm:p-7">
            <section className="flex min-w-0 flex-1 flex-col rounded-xl border border-rule bg-surface p-5">
              <Outlet context={{ project } satisfies WorkspaceContext} />
            </section>
          </div>
        ) : (
          <Outlet context={{ project } satisfies WorkspaceContext} />
        )}
      </div>
    </div>
  )
}

/** /projects/:id picks the step the project is waiting on. */
export function WorkspaceIndex() {
  const { project } = useWorkspace()
  const { projectId = '' } = useParams()
  const { data: diagrams, isPending } = useDiagrams(projectId)
  const stage = projectStage(project)
  if (stage === 'done') {
    if (isPending) return <PageLoading />
    return <Navigate to={diagrams?.[0] ? `diagrams/${diagrams[0].id}` : 'generate'} replace />
  }
  const to = { input: 'input', extracting: 'input', failed: 'input', review: 'review', generate: 'generate' }[stage]
  return <Navigate to={to} replace />
}
