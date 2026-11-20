import { PlusIcon } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import type { Project } from '@/api/client'
import { errorMessage } from '@/api/errors'
import { useProjects } from '@/api/queries'
import { DiagramGlyph } from '@/components/diagram-glyph'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Notice } from '@/components/ui/notice'
import { cn, formatRelative, plural } from '@/lib/utils'
import { CreateProjectDialog } from './create-project-dialog'
import { projectStage, stageLabel, stageStep, type Stage } from './stage'

const FILTERS: { id: string; label: string; match: (s: Stage) => boolean }[] = [
  { id: 'all', label: 'All', match: () => true },
  { id: 'review', label: 'Needs review', match: (s) => s === 'review' },
  { id: 'progress', label: 'In progress', match: (s) => s === 'input' || s === 'extracting' || s === 'generate' || s === 'failed' },
  { id: 'done', label: 'Done', match: (s) => s === 'done' },
]

export function ProjectsPage() {
  const { data: projects, isPending, isError, error, refetch } = useProjects()
  const [filter, setFilter] = useState('all')
  // Archived projects sit in their own section below; the filters only cover active ones.
  const active = projects?.filter((p) => !p.archived_at) ?? []
  const archived = projects?.filter((p) => p.archived_at) ?? []
  const shown = active.filter((p) => FILTERS.find((f) => f.id === filter)!.match(projectStage(p)))

  return (
    <div className="mx-auto w-full max-w-[1344px] px-4 py-9 sm:px-8 lg:px-12">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="font-mono text-[11px] tracking-[0.08em] text-slate uppercase">Workspace</p>
          <h1 className="mt-1.5 text-[30px] font-semibold">Projects</h1>
        </div>
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

      {isPending ? (
        <div className="mt-8 grid gap-5 sm:grid-cols-2 xl:grid-cols-4" aria-label="Loading projects">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-72 animate-pulse rounded-xl border border-dashed border-rule-strong bg-surface" />
          ))}
        </div>
      ) : isError ? (
        <Notice
          className="mt-8"
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
        <>
          <div role="group" aria-label="Filter projects" className="mt-6 flex flex-wrap gap-2">
            {FILTERS.map((f) => {
              const n = active.filter((p) => f.match(projectStage(p))).length
              return (
                <button
                  key={f.id}
                  type="button"
                  aria-pressed={filter === f.id}
                  onClick={() => setFilter(f.id)}
                  className={cn(
                    'h-[30px] rounded-full border px-3 text-[13px] font-medium',
                    filter === f.id ? 'border-ink bg-ink text-on-ink' : 'border-rule-strong text-ink-2 hover:bg-ink/5',
                  )}
                >
                  {f.label} <span className="opacity-60">{n}</span>
                </button>
              )
            })}
          </div>
          <ul aria-label="Active projects" className="mt-5 grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
            {shown.map((p) => (
              <li key={p.id}>
                <ProjectCard project={p} />
              </li>
            ))}
            {filter === 'all' && (
              <li>
                <CreateProjectDialog
                  trigger={
                    <button
                      type="button"
                      className="grid h-full min-h-[280px] w-full place-items-center rounded-xl border-[1.5px] border-dashed border-rule-strong text-slate hover:border-ink-2 hover:text-ink"
                    >
                      <span>
                        <span className="mx-auto grid size-11 place-items-center rounded-xl border-[1.5px] border-rule-strong">
                          <PlusIcon className="size-5" />
                        </span>
                        <span className="mt-2.5 block font-semibold text-ink">New project</span>
                        <span className="text-[13px]">Start from pasted requirements</span>
                      </span>
                    </button>
                  }
                />
              </li>
            )}
          </ul>
          {archived.length > 0 && (
            <section aria-labelledby="archived-heading" className="mt-12">
              <h2 id="archived-heading" className="font-mono text-[11px] tracking-[0.08em] text-slate uppercase">
                Archived
              </h2>
              <ul aria-label="Archived projects" className="mt-3 grid gap-5 opacity-80 sm:grid-cols-2 xl:grid-cols-4">
                {archived.map((p) => (
                  <li key={p.id}>
                    <ProjectCard project={p} />
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}
    </div>
  )
}

function MiniPipe({ step }: { step: number }) {
  return (
    <span className="flex items-center" aria-hidden>
      {[1, 2, 3, 4].map((n) => (
        <span key={n} className="flex items-center">
          <span
            className={cn(
              'size-[9px] rounded-full border-[1.5px] border-rule-strong',
              n < step && 'border-ink bg-ink',
              n === step && 'border-accent bg-accent shadow-[0_0_0_3px_var(--accent-wash)]',
            )}
          />
          {n < 4 && <span className={cn('h-[1.5px] w-5', n < step ? 'bg-ink' : 'bg-rule')} />}
        </span>
      ))}
    </span>
  )
}

function ProjectCard({ project: p }: { project: Project }) {
  const stage = projectStage(p)
  return (
    <Link
      to={`/projects/${p.id}`}
      className="ticks group block overflow-hidden rounded-xl border border-rule bg-surface transition-shadow hover:shadow-[var(--shadow)]"
    >
      <div className="grid-bg grid h-[140px] place-items-center border-b border-rule bg-paper/60">
        {p.diagram_count > 0 ? (
          <span className="relative">
            <DiagramGlyph type="use_case" className="h-24 w-44" />
            <Badge className="absolute -right-6 -bottom-1" tone="accent">
              {plural(p.diagram_count, 'diagram')}
            </Badge>
          </span>
        ) : (
          <span className="text-[13px] text-slate">No diagrams yet</span>
        )}
      </div>
      <div className="px-[18px] py-4">
        <p className="truncate font-semibold group-hover:text-accent">{p.name}</p>
        <p className="mt-0.5 truncate text-[12.5px] text-slate">
          {p.client_name && `${p.client_name} · `}
          {p.statement_count > 0 ? plural(p.statement_count, 'requirement') : 'Empty project'}
          {p.open_flag_count ? <span className="text-amber"> · {plural(p.open_flag_count, 'open flag')}</span> : null}
        </p>
        <div className="mt-4 flex items-center gap-2.5">
          <MiniPipe step={stageStep[stage]} />
          <span className="truncate text-[12px] font-medium">{stageLabel[stage]}</span>
          {p.archived_at ? (
            <Badge className="ml-auto">Archived</Badge>
          ) : stage === 'failed' && (
            <Badge tone="danger" className="ml-auto">
              Failed
            </Badge>
          )}
        </div>
      </div>
      <p className="border-t border-rule px-[18px] py-2.5 text-[11.5px] text-slate">Updated {formatRelative(p.updated_at)}</p>
    </Link>
  )
}

function EmptyState() {
  return (
    <div className="grid-bg mt-8 grid place-items-center rounded-2xl border border-dashed border-rule-strong px-6 py-20 text-center">
      <div className="max-w-md">
        <svg viewBox="0 0 260 120" className="mx-auto w-64" aria-hidden>
          <g fill="none" stroke="var(--rule-strong)" strokeWidth="1.5" strokeDasharray="5 4">
            <rect x="10" y="40" width="70" height="40" rx="6" />
            <ellipse cx="200" cy="30" rx="48" ry="16" />
            <ellipse cx="200" cy="90" rx="48" ry="16" />
            <path d="M80 60h40l30-30h2M120 60l30 30h2" />
          </g>
        </svg>
        <h2 className="mt-4 text-xl font-semibold">No projects yet</h2>
        <p className="mt-1.5 text-slate">A project holds one system&rsquo;s requirements and every diagram made from them.</p>
        <CreateProjectDialog
          trigger={
            <Button size="lg" className="mt-6">
              <PlusIcon /> Create your first project
            </Button>
          }
        />
      </div>
    </div>
  )
}
