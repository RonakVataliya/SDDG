import { ChevronRightIcon, PlusIcon } from 'lucide-react'
import { Link } from 'react-router'
import { errorMessage } from '@/api/errors'
import { useProjects } from '@/api/queries'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Notice } from '@/components/ui/notice'
import { PageLoading } from '@/components/ui/spinner'
import { formatRelative, plural } from '@/lib/utils'
import { CreateProjectDialog } from './create-project-dialog'
import { projectStage, stageLabel, type Stage } from './stage'

const stageTone: Record<Stage, 'neutral' | 'teal' | 'amber' | 'danger'> = {
  input: 'neutral',
  extracting: 'neutral',
  review: 'amber',
  generate: 'teal',
  done: 'teal',
  failed: 'danger',
}

export function ProjectsPage() {
  const { data: projects, isPending, isError, error, refetch } = useProjects()

  return (
    <div className="mx-auto max-w-4xl px-4 py-10 sm:px-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <h1 className="text-2xl font-semibold tracking-tight">Projects</h1>
        {!!projects?.length && (
          <CreateProjectDialog
            trigger={
              <Button>
                <PlusIcon /> New project
              </Button>
            }
          />
        )}
      </div>

      <div className="mt-8">
        {isPending ? (
          <PageLoading label="Loading projects" />
        ) : isError ? (
          <Notice
            tone="error"
            title="Couldn't load your projects"
            action={
              <Button size="sm" variant="secondary" onClick={() => refetch()}>
                Try again
              </Button>
            }
          >
            {errorMessage(error)}
          </Notice>
        ) : projects.length === 0 ? (
          <EmptyState />
        ) : (
          <ul className="divide-y divide-rule overflow-hidden rounded-lg border border-rule bg-surface">
            {projects.map((p) => {
              const stage = projectStage(p)
              return (
                <li key={p.id}>
                  <Link
                    to={`/projects/${p.id}`}
                    className="group flex items-center gap-4 px-5 py-4 hover:bg-paper focus-visible:bg-paper"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium group-hover:text-teal-deep">{p.name}</p>
                      <p className="mt-0.5 text-sm text-slate">
                        {p.statement_count > 0
                          ? `${plural(p.statement_count, 'requirement')} · ${plural(p.item_count, 'item')}`
                          : 'No requirements yet'}
                        {' · '}updated {formatRelative(p.updated_at)}
                      </p>
                    </div>
                    <Badge tone={stageTone[stage]} className="hidden sm:inline-flex">
                      {stageLabel[stage]}
                    </Badge>
                    <ChevronRightIcon className="size-4 text-slate" />
                  </Link>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </div>
  )
}

function EmptyState() {
  return (
    <div className="rounded-lg border border-dashed border-rule-strong bg-surface px-6 py-14 text-center">
      <svg viewBox="0 0 120 56" className="mx-auto w-28" aria-hidden>
        <g stroke="var(--color-rule-strong)" strokeWidth="1.5" fill="none" strokeLinecap="round">
          <circle cx="14" cy="12" r="6" />
          <path d="M14 18v16M5 24h18M14 34l-7 11M14 34l7 11" />
          <path d="M26 28h24" strokeDasharray="3 3" />
          <ellipse cx="84" cy="28" rx="32" ry="13" strokeDasharray="4 3" />
        </g>
      </svg>
      <h2 className="mt-5 text-lg font-semibold">No projects yet</h2>
      <p className="mx-auto mt-1.5 max-w-sm text-slate">
        Create a project, paste your requirements, and SDDG will draft a Use Case diagram you can trace back to each
        requirement.
      </p>
      <CreateProjectDialog
        trigger={
          <Button className="mt-6">
            <PlusIcon /> Create your first project
          </Button>
        }
      />
    </div>
  )
}
