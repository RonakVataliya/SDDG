import type * as React from 'react'
import { ChevronLeftIcon, ChevronRightIcon, PencilIcon, RefreshCwIcon } from 'lucide-react'
import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import type { ExtractedItem, FlagType, ItemCategory, RequirementStatement } from '@/api/client'
import { errorMessage } from '@/api/errors'
import { ITEMS_PAGE_SIZE, useDiagrams, useFlags, useFlagSummary, useItems, useStartGeneration, useStatements } from '@/api/queries'
import { Badge, RefTag } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Notice } from '@/components/ui/notice'
import { PageLoading, Spinner } from '@/components/ui/spinner'
import { FlagPill, FlagsDrawer, Highlighted } from '@/features/flags/flags'
import { DIAGRAM_TYPES } from '@/features/generate/diagram-types'
import { useWorkspace } from '@/routes/workspace-layout'
import { cn, plural } from '@/lib/utils'
import { EditItemDialog } from './edit-item-dialog'
import { CATEGORIES, categoryLabel, QUALIFIERS } from './labels'

/** Optional check of the building blocks extracted for the diagrams. Fixing one offers to redraw the diagrams. */
export function ItemsPage() {
  const { project } = useWorkspace()
  const [category, setCategory] = useState<ItemCategory | undefined>()
  const [page, setPage] = useState(1)
  const [editing, setEditing] = useState<ExtractedItem | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [drawer, setDrawer] = useState<{ open: boolean; focus?: string | null }>({ open: false })
  const items = useItems(project.id, category, page)
  const statements = useStatements(project.id)
  const summary = useFlagSummary(project.id)
  const flags = useFlags(project.id)
  const canEdit = project.role !== 'viewer'

  const byId = useMemo(() => new Map((statements.data ?? []).map((s) => [s.id, s])), [statements.data])
  const summaryById = useMemo(() => new Map((summary.data ?? []).map((s) => [s.statement_id, s])), [summary.data])
  const openFlagByStatement = useMemo(() => {
    const m = new Map<string, NonNullable<typeof flags.data>[number]>()
    for (const f of flags.data ?? []) if (f.status === 'open' && !m.has(f.statement_id)) m.set(f.statement_id, f)
    return m
  }, [flags.data])
  // The summary's `types` also lists resolved flags' types, so the pill takes them from open flags only.
  const openTypes = useMemo(() => {
    const m = new Map<string, FlagType[]>()
    for (const f of flags.data ?? []) {
      if (f.status !== 'open') continue
      const have = m.get(f.statement_id) ?? []
      if (!have.includes(f.type)) m.set(f.statement_id, [...have, f.type])
    }
    return m
  }, [flags.data])

  if (project.item_count === 0 && !items.data?.total) {
    return (
      <div className="p-7">
        <Notice title="No building blocks yet">
          They are extracted when you generate diagrams.{' '}
          <Link to="../generate" className="font-medium underline">
            Choose diagrams
          </Link>
        </Notice>
      </div>
    )
  }

  const counts = items.data?.counts ?? {}
  const total = Object.values(counts).reduce((a, b) => a + b, 0)
  const pageCount = items.data ? Math.max(1, Math.ceil(items.data.total / ITEMS_PAGE_SIZE)) : 1
  const groups = CATEGORIES.map((c) => ({ ...c, items: (items.data?.items ?? []).filter((i) => i.category === c.value) })).filter((g) => g.items.length)

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-wrap items-end justify-between gap-3 px-4 pt-5 sm:px-7">
        <div>
          <h2 className="text-xl font-semibold">Building blocks <span className="font-sans text-[13px] font-normal text-slate">(optional check)</span></h2>
          <p className="mt-1 text-[13px] text-slate">Your diagrams are already drawn from these. Pick a requirement to see what came from it; fix something only if a diagram looks wrong.</p>
        </div>
        <RedrawButton />
      </div>

      <TraceGrid selected={selected}>
        <section aria-label="Requirements" className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-rule bg-field">
          <h3 className="border-b border-rule px-4 py-3 font-sans text-[15px] font-semibold tracking-normal">
            Requirements <span className="font-normal text-slate">{statements.data?.length ?? ''}</span>
          </h3>
          <ol className="min-h-0 flex-1 overflow-y-auto">
            {(statements.data ?? []).map((s) => {
              const on = s.id === selected
              const flag = openFlagByStatement.get(s.id)
              return (
                <li key={s.id} data-src={on ? '' : undefined} className={cn('flex items-start gap-3 border-b border-rule px-4 py-2.5', on && 'bg-accent-wash shadow-[inset_3px_0_0_var(--accent)]')}>
                  <button type="button" onClick={() => setSelected(on ? null : s.id)} aria-pressed={on} className="flex min-w-0 flex-1 items-start gap-3 text-left">
                    <RefTag className={cn('mt-0.5 shrink-0', on && 'border-accent text-accent')}>{s.ref}</RefTag>
                    <span className="min-w-0 flex-1 text-[13px] leading-[22px]">
                      {s.label && <span className="mr-1.5 font-mono text-[11px] text-slate">{s.label}</span>}
                      <Highlighted text={s.text} trigger={flag?.trigger_text} type={flag?.type} />
                    </span>
                  </button>
                  <FlagPill summary={summaryById.get(s.id)} openTypes={openTypes.get(s.id)} onClick={() => setDrawer({ open: true, focus: s.id })} />
                </li>
              )
            })}
          </ol>
        </section>

        <section aria-label="Extracted items" className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-rule bg-field">
          <div role="group" aria-label="Filter by category" className="flex gap-1.5 overflow-x-auto border-b border-rule px-4 py-2.5">
            {[{ value: undefined, plural: 'All', count: total }, ...CATEGORIES.map((c) => ({ ...c, count: counts[c.value] ?? 0 }))].map((c) => {
              const active = category === c.value
              return (
                <button
                  key={c.plural}
                  type="button"
                  aria-pressed={active}
                  onClick={() => {
                    setCategory(c.value)
                    setPage(1)
                  }}
                  className={cn('h-7 shrink-0 rounded-full border px-3 text-[12.5px]', active ? 'border-ink bg-ink text-on-ink' : 'border-rule text-ink-2 hover:border-rule-strong')}
                >
                  {c.plural} <span className="opacity-60">{c.count}</span>
                </button>
              )
            })}
          </div>
          <div className={cn('min-h-0 flex-1 overflow-y-auto py-1', items.isPlaceholderData && 'opacity-60')}>
            {items.isError ? (
              <Notice className="m-4" tone="error" title="Couldn't load the items">
                {errorMessage(items.error)}
              </Notice>
            ) : !items.data ? (
              <PageLoading label="Loading items" />
            ) : items.data.items.length === 0 ? (
              <p className="px-5 py-8 text-center text-slate">No {category ? categoryLabel[category].toLowerCase() : ''} items were extracted.</p>
            ) : (
              groups.map((g) => (
                <div key={g.value}>
                  <p className="px-4 pt-3 pb-1 font-mono text-[11px] tracking-[0.08em] text-slate uppercase">{g.plural}</p>
                  {g.items.map((item) => (
                    <ItemRow key={item.id} item={item} byId={byId} selected={selected} canEdit={canEdit} onEdit={() => setEditing(item)} />
                  ))}
                </div>
              ))
            )}
          </div>
          {items.data && items.data.total > ITEMS_PAGE_SIZE && (
            <nav aria-label="Pagination" className="flex items-center justify-end gap-2 border-t border-rule px-4 py-2 text-[13px]">
              <span className="mr-2 text-slate tabular-nums">
                {(page - 1) * ITEMS_PAGE_SIZE + 1}–{Math.min(page * ITEMS_PAGE_SIZE, items.data.total)} of {items.data.total}
              </span>
              <Button variant="secondary" size="icon" aria-label="Previous page" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                <ChevronLeftIcon />
              </Button>
              <Button variant="secondary" size="icon" aria-label="Next page" disabled={page >= pageCount} onClick={() => setPage((p) => p + 1)}>
                <ChevronRightIcon />
              </Button>
            </nav>
          )}
        </section>
      </TraceGrid>

      <EditItemDialog projectId={project.id} item={editing} confirmed={project.confirmed} onClose={() => setEditing(null)} />
      <FlagsDrawer
        projectId={project.id}
        open={drawer.open}
        onOpenChange={(open) => setDrawer((d) => ({ ...d, open }))}
        focusStatementId={drawer.focus}
        statements={statements.data ?? []}
        canEdit={canEdit}
      />
    </div>
  )
}

function ItemRow({
  item,
  byId,
  selected,
  canEdit,
  onEdit,
}: {
  item: ExtractedItem
  byId: Map<string, RequirementStatement>
  selected: string | null
  canEdit: boolean
  onEdit: () => void
}) {
  const hit = !!selected && item.statement_ids.includes(selected)
  return (
    <div data-dst={hit ? '' : undefined} className={cn('flex items-start gap-3 px-4 py-2', hit && 'bg-accent-wash')}>
      <div className="w-48 shrink-0">
        <p className="text-[13px] font-semibold">{item.name}</p>
        {item.description && <p className="text-[12px] text-slate">{item.description}</p>}
      </div>
      <div className="flex min-w-0 flex-1 flex-wrap gap-1">
        {item.statement_ids.length === 0 ? (
          <span className="text-[12px] text-slate">No source</span>
        ) : (
          item.statement_ids.map((id) => {
            const st = byId.get(id)
            return (
              <RefTag key={id} title={st?.text} className={cn(id === selected && 'border-accent bg-accent-wash text-accent')}>
                {st?.ref ?? '…'}
              </RefTag>
            )
          })
        )}
      </div>
      <div className="flex flex-wrap justify-end gap-1">
        {item.origin !== 'system-extracted' && <Badge tone="violet">{item.origin === 'user-edited' ? 'Edited by you' : 'Added by you'}</Badge>}
        {item.qualifiers.map((q) => (
          <Badge key={q} tone="amber" title={QUALIFIERS[q].hint}>
            {QUALIFIERS[q].label}
          </Badge>
        ))}
      </div>
      {canEdit && (
        <Button variant="ghost" size="icon" className="size-7" aria-label={`Edit ${item.name}`} onClick={onEdit}>
          <PencilIcon className="size-3.5" />
        </Button>
      )}
    </div>
  )
}

/** Two columns with curved trace lines from the selected requirement to the items it produced (wide screens). */
function TraceGrid({ selected, children }: { selected: string | null; children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null)
  const [paths, setPaths] = useState<{ d: string; end: [number, number] }[]>([])
  const [start, setStart] = useState<[number, number] | null>(null)

  useLayoutEffect(() => {
    const root = ref.current
    if (!root) return
    const measure = () => {
      const c = root.getBoundingClientRect()
      const src = root.querySelector('[data-src]')
      if (!src || window.innerWidth < 1024) {
        setPaths([])
        setStart(null)
        return
      }
      const a = src.getBoundingClientRect()
      const sx = a.right - c.left
      const sy = a.top + a.height / 2 - c.top
      const next: { d: string; end: [number, number] }[] = []
      root.querySelectorAll('[data-dst]').forEach((el) => {
        const b = el.getBoundingClientRect()
        const box = (el.closest('.overflow-y-auto') ?? root).getBoundingClientRect()
        if (b.bottom < box.top || b.top > box.bottom) return
        const ex = b.left - c.left
        const ey = b.top + b.height / 2 - c.top
        next.push({ d: `M${sx} ${sy} C${sx + 28} ${sy} ${ex - 28} ${ey} ${ex} ${ey}`, end: [ex, ey] })
      })
      setStart([sx, sy])
      setPaths(next)
    }
    measure()
    const ro = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measure)
    ro?.observe(root)
    root.addEventListener('scroll', measure, true)
    return () => {
      ro?.disconnect()
      root.removeEventListener('scroll', measure, true)
    }
  }, [selected])

  return (
    <div ref={ref} className="relative grid min-h-0 flex-1 gap-4 px-4 py-4 sm:px-7 lg:grid-cols-[minmax(0,460px)_minmax(0,1fr)] lg:gap-10 lg:overflow-hidden">
      <svg aria-hidden className="pointer-events-none absolute inset-0 z-10 hidden size-full overflow-visible lg:block">
        {paths.map((p, i) => (
          <g key={i}>
            <path d={p.d} fill="none" stroke="var(--accent)" strokeWidth={1.4} />
            <circle cx={p.end[0]} cy={p.end[1]} r={3} fill="var(--accent)" />
          </g>
        ))}
        {start && paths.length > 0 && <circle cx={start[0]} cy={start[1]} r={3.5} fill="var(--accent)" />}
      </svg>
      {children}
    </div>
  )
}

/** After fixing items, redraw the project's diagram types; nothing is re-extracted (finished nodes are skipped). */
function RedrawButton() {
  const { project } = useWorkspace()
  const diagrams = useDiagrams(project.id)
  const start = useStartGeneration(project.id)
  const navigate = useNavigate()
  // Package diagrams come from the Design step and unavailable types cannot be generated, so neither is redrawn here.
  const types = [...new Set((diagrams.data ?? []).map((d) => d.type))].filter((t) => DIAGRAM_TYPES.some((x) => x.value === t && x.available && t !== 'package'))
  if (!types.length) return null
  return (
    <div className="flex items-center gap-2">
      {start.isError && <span className="text-[12.5px] text-danger">{errorMessage(start.error)}</span>}
      <Button
        variant="secondary"
        disabled={start.isPending}
        onClick={async () => {
          const job = await start.mutateAsync(types).catch(() => null)
          if (job) navigate(`../generate?job=${job.id}`)
        }}
      >
        {start.isPending ? <Spinner label="Starting" /> : <RefreshCwIcon />}
        Redraw {plural(types.length, 'diagram')}
      </Button>
    </div>
  )
}
