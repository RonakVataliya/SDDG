import { CheckIcon, LockIcon } from 'lucide-react'
import { Link, Navigate, NavLink, Outlet, useOutletContext, useParams } from 'react-router'
import type { Project } from '@/api/client'
import { ApiError, errorMessage } from '@/api/errors'
import { useDiagrams, useProject } from '@/api/queries'
import { Notice } from '@/components/ui/notice'
import { PageLoading, Spinner } from '@/components/ui/spinner'
import { GeneratePanel } from '@/features/generate/generate-panel'
import { projectStage } from '@/features/projects/stage'
import { cn, plural } from '@/lib/utils'
import { NotFoundPage } from './not-found-page'

type StepState = 'done' | 'active' | 'open' | 'locked' | 'working'
type Step = { n: number; to: string; label: string; detail: string; state: StepState }

function buildSteps(project: Project, latestDiagramId?: string): Step[] {
  const stage = projectStage(project)
  const extracted = project.item_count > 0
  return [
    {
      n: 1,
      to: 'input',
      label: 'Requirements',
      detail: stage === 'extracting' ? 'Extracting…' : project.statement_count ? plural(project.statement_count, 'statement') : 'Paste text',
      state: stage === 'extracting' ? 'working' : project.statement_count ? 'done' : 'open',
    },
    {
      n: 2,
      to: 'review',
      label: 'Review and confirm',
      detail: project.confirmed
        ? 'Confirmed'
        : extracted
          ? `${plural(project.item_count, 'item')} to check`
          : project.extraction?.status === 'succeeded'
            ? 'No items found'
            : 'Waiting for extraction',
      state: project.confirmed ? 'done' : extracted ? 'open' : 'locked',
    },
    {
      n: 3,
      to: 'generate',
      label: 'Generate',
      detail: project.confirmed ? 'Use Case diagram' : 'Locked until you confirm',
      state: project.confirmed ? (project.diagram_count ? 'done' : 'open') : 'locked',
    },
    {
      n: 4,
      to: latestDiagramId ? `diagrams/${latestDiagramId}` : 'generate',
      label: 'Diagram',
      detail: project.diagram_count ? 'View and export' : 'Not generated yet',
      state: latestDiagramId ? 'done' : 'locked',
    },
  ]
}

function StepMarker({ n, state, current }: { n: number; state: StepState; current: boolean }) {
  return (
    <span
      className={cn(
        'grid size-7 shrink-0 place-items-center rounded-full border text-xs font-semibold tabular-nums',
        current
          ? 'border-teal bg-teal text-white'
          : state === 'done'
            ? 'border-teal/40 bg-teal-wash text-teal-deep'
            : state === 'locked'
              ? 'border-dashed border-rule-strong text-slate'
              : 'border-rule-strong bg-surface text-ink',
      )}
    >
      {state === 'working' ? (
        <Spinner className={cn('size-3.5', current && 'text-white')} label="In progress" />
      ) : state === 'locked' && !current ? (
        <LockIcon className="size-3" aria-label="Locked" />
      ) : state === 'done' && !current ? (
        <CheckIcon className="size-3.5" strokeWidth={3} aria-label="Done" />
      ) : (
        n
      )}
    </span>
  )
}

function PipelineRail({ steps }: { steps: Step[] }) {
  return (
    <nav aria-label="Project steps">
      <ol className="flex gap-1 overflow-x-auto pb-1 lg:flex-col lg:gap-0 lg:overflow-visible">
        {steps.map((s, i) => {
          const locked = s.state === 'locked'
          const inner = (current: boolean) => (
            <>
              <span className="relative flex flex-col items-center self-stretch">
                <StepMarker n={s.n} state={s.state} current={current} />
                {i < steps.length - 1 && (
                  <span
                    aria-hidden
                    className={cn(
                      'mt-1 hidden w-px flex-1 lg:block',
                      steps[i + 1].state === 'locked' ? 'border-l border-dashed border-rule-strong' : 'bg-teal/35',
                    )}
                  />
                )}
              </span>
              <span className="min-w-0 pb-6 lg:pb-7">
                <span className={cn('block text-sm font-medium', locked && 'text-slate', current && 'text-teal-deep')}>
                  {s.label}
                </span>
                <span className="block text-xs whitespace-nowrap text-slate">{s.detail}</span>
              </span>
            </>
          )
          return (
            <li key={s.label} className="shrink-0 lg:shrink">
              {locked ? (
                <span aria-disabled className="flex cursor-not-allowed gap-3 rounded-md px-2 pt-2 opacity-80">
                  {inner(false)}
                </span>
              ) : (
                <NavLink
                  to={s.to}
                  className={({ isActive }) =>
                    cn('flex gap-3 rounded-md px-2 pt-2 hover:bg-ink/4', isActive && 'bg-surface ring-1 ring-rule')
                  }
                >
                  {({ isActive }) => inner(isActive)}
                </NavLink>
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}

const panel = 'min-w-0 rounded-xl border border-rule bg-surface xl:overflow-y-auto'

export type WorkspaceContext = { project: Project }
export const useWorkspace = () => useOutletContext<WorkspaceContext>()

export function WorkspaceLayout() {
  const { projectId = '' } = useParams()
  const { data: project, isPending, error } = useProject(projectId)
  const { data: diagrams } = useDiagrams(projectId)

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

  return (
    <div className="px-4 py-4 sm:px-6">
      <div className="flex min-w-0 items-baseline gap-1.5">
        <Link to="/projects" className="shrink-0 text-sm text-slate hover:text-ink hover:underline">
          Projects
        </Link>
        <span className="text-sm text-rule-strong">/</span>
        <h1 className="truncate text-lg font-semibold tracking-tight">{project.name}</h1>
      </div>
      {/* Three panels: steps | current step | generate. Below xl the generate panel drops under the current step. */}
      <div className="mt-3 grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-[15rem_minmax(0,1fr)] xl:h-[calc(100dvh-7.5rem)] xl:min-h-[34rem] xl:grid-cols-[15rem_minmax(0,1fr)_19rem]">
        <aside className={cn(panel, 'p-3 lg:row-span-2 xl:row-span-1')} aria-label="Steps">
          <h2 className="hidden px-2 pb-3 text-sm font-medium text-slate lg:block">Steps</h2>
          <PipelineRail steps={buildSteps(project, diagrams?.[0]?.id)} />
        </aside>
        <section className={cn(panel, 'flex flex-col p-5')}>
          <Outlet context={{ project } satisfies WorkspaceContext} />
        </section>
        <aside className={cn(panel, 'p-4 lg:col-start-2 xl:col-start-3')} aria-label="Generate">
          <GeneratePanel project={project} />
        </aside>
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
