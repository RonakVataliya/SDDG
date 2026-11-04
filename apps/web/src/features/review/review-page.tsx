import { ChevronDownIcon, ChevronLeftIcon, ChevronRightIcon, PencilIcon } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import type { ExtractedItem, ItemCategory, RequirementStatement } from '@/api/client'
import { errorMessage } from '@/api/errors'
import { ITEMS_PAGE_SIZE, useConfirmExtraction, useItems, useStatements } from '@/api/queries'
import { Badge, RefTag } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Notice } from '@/components/ui/notice'
import { PageLoading, Spinner } from '@/components/ui/spinner'
import { StepHeading } from '@/features/input/input-page'
import { useWorkspace } from '@/routes/workspace-layout'
import { cn, formatRelative } from '@/lib/utils'
import { EditItemDialog } from './edit-item-dialog'
import { CATEGORIES, categoryLabel, QUALIFIERS } from './labels'

export function ReviewPage() {
  const { project } = useWorkspace()
  const [category, setCategory] = useState<ItemCategory | undefined>()
  const [page, setPage] = useState(1)
  const [editing, setEditing] = useState<ExtractedItem | null>(null)
  const items = useItems(project.id, category, page)
  const statements = useStatements(project.id)
  const highlight = useSearchParams()[0].get('requirement') // set by search: open and highlight this requirement
  const canEdit = project.role !== 'viewer'

  const byId = useMemo(
    () => new Map((statements.data ?? []).map((s) => [s.id, s])),
    [statements.data],
  )

  if (project.item_count === 0 && !items.data?.total) {
    return (
      <div className="space-y-4">
        <StepHeading title="Review extracted items" />
        <Notice title="Nothing to review yet">
          Add requirement text first.{' '}
          <Link to="../input" className="font-medium underline">
            Go to Requirements
          </Link>
        </Notice>
      </div>
    )
  }

  const counts = items.data?.counts ?? {}
  const total = Object.values(counts).reduce((a, b) => a + b, 0)
  const pageCount = items.data ? Math.max(1, Math.ceil(items.data.total / ITEMS_PAGE_SIZE)) : 1

  return (
    <div className="flex flex-1 flex-col space-y-5">
      <StepHeading
        title="Review extracted items"
        description="Check what was pulled out of your requirements. Fix anything wrong, then confirm. Diagrams are generated only from confirmed items."
      />

      <div role="group" aria-label="Filter by category" className="-mx-1 flex gap-1 overflow-x-auto px-1 pb-1">
        {[{ value: undefined, plural: 'All', count: total }, ...CATEGORIES.map((c) => ({ ...c, count: counts[c.value] ?? 0 }))].map(
          (c) => {
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
                className={cn(
                  'shrink-0 rounded-md border px-3 py-1.5 text-sm',
                  active ? 'border-ink bg-ink text-white' : 'border-rule bg-surface text-ink hover:border-rule-strong',
                )}
              >
                {c.plural} <span className={cn('tabular-nums', active ? 'text-white/70' : 'text-slate')}>{c.count}</span>
              </button>
            )
          },
        )}
      </div>

      {items.isError ? (
        <Notice tone="error" title="Couldn't load the items">
          {errorMessage(items.error)}
        </Notice>
      ) : !items.data ? (
        <PageLoading label="Loading items" />
      ) : items.data.items.length === 0 ? (
        <p className="rounded-lg border border-rule bg-surface px-5 py-8 text-center text-slate">
          No {category ? categoryLabel[category].toLowerCase() : ''} items were extracted.
        </p>
      ) : (
        <div className={cn('relative overflow-x-auto rounded-lg border border-rule bg-surface', items.isPlaceholderData && 'opacity-60')}>
          <table className="w-full text-left text-sm">
            <thead className="border-b border-rule text-slate">
              <tr>
                <th scope="col" className="px-4 py-2.5 font-medium">Item</th>
                {!category && <th scope="col" className="px-4 py-2.5 font-medium">Category</th>}
                <th scope="col" className="px-4 py-2.5 font-medium">Source</th>
                <th scope="col" className="px-4 py-2.5 font-medium">Status</th>
                {canEdit && <th scope="col" className="w-12 px-2 py-2.5"><span className="sr-only">Actions</span></th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-rule">
              {items.data.items.map((item) => (
                <tr key={item.id} className="align-top hover:bg-paper/60">
                  <td className="px-4 py-3">
                    <p className="font-medium">{item.name}</p>
                    {item.description && <p className="mt-0.5 max-w-md text-slate">{item.description}</p>}
                  </td>
                  {!category && <td className="px-4 py-3 whitespace-nowrap text-slate">{categoryLabel[item.category]}</td>}
                  <td className="px-4 py-3">
                    <SourceRefs ids={item.statement_ids} byId={byId} />
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      {item.origin !== 'system-extracted' && (
                        <Badge tone="violet">{item.origin === 'user-edited' ? 'Edited by you' : 'Added by you'}</Badge>
                      )}
                      {item.qualifiers.map((q) => (
                        <Badge key={q} tone="amber" title={QUALIFIERS[q].hint}>
                          {QUALIFIERS[q].label}
                        </Badge>
                      ))}
                    </div>
                  </td>
                  {canEdit && (
                    <td className="px-2 py-2">
                      <Button variant="ghost" size="icon" aria-label={`Edit ${item.name}`} onClick={() => setEditing(item)}>
                        <PencilIcon />
                      </Button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {items.data && items.data.total > ITEMS_PAGE_SIZE && (
        <nav aria-label="Pagination" className="flex items-center justify-end gap-2 text-sm">
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

      <StatementList statements={statements.data ?? []} highlight={highlight} />

      <ConfirmBar />

      <EditItemDialog projectId={project.id} item={editing} confirmed={project.confirmed} onClose={() => setEditing(null)} />
    </div>
  )
}

function SourceRefs({ ids, byId }: { ids: string[]; byId: Map<string, RequirementStatement> }) {
  if (ids.length === 0) return <span className="text-slate">None</span>
  return (
    <div className="flex flex-wrap gap-1">
      {ids.map((id) => {
        const st = byId.get(id)
        return (
          <RefTag key={id} title={st?.text}>
            {st?.ref ?? '…'}
          </RefTag>
        )
      })}
    </div>
  )
}

function StatementList({ statements, highlight }: { statements: RequirementStatement[]; highlight: string | null }) {
  const [open, setOpen] = useState(highlight !== null)
  if (statements.length === 0) return null
  return (
    <div className="rounded-lg border border-rule bg-surface">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-medium"
      >
        Requirement statements ({statements.length})
        <ChevronDownIcon className={cn('size-4 text-slate transition-transform', open && 'rotate-180')} />
      </button>
      {open && (
        <ol className="divide-y divide-rule border-t border-rule">
          {statements.map((s) => (
            <li
              key={s.id}
              ref={s.ref === highlight ? (el) => el?.scrollIntoView?.({ block: 'center' }) : undefined}
              className={cn('flex gap-3 px-4 py-2.5 text-sm', s.ref === highlight && 'bg-teal-wash')}
            >
              <RefTag className="h-fit shrink-0">{s.ref}</RefTag>
              <p className="min-w-0 flex-1">
                {s.label && <span className="mr-1.5 text-slate">{s.label}</span>}
                {s.text}
              </p>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

/** FR5e: the gate. Generation stays locked until the current extraction is confirmed; any edit clears it. */
function ConfirmBar() {
  const { project } = useWorkspace()
  const confirm = useConfirmExtraction(project.id)
  const navigate = useNavigate()
  const canEdit = project.role !== 'viewer'

  return (
    <div className="sticky bottom-0 z-20 -mx-5 mt-auto -mb-5 rounded-b-xl border-t border-rule bg-surface/95 backdrop-blur">
      <div className="flex flex-wrap items-center gap-3 px-5 py-3">
        <p className="min-w-0 flex-1 text-sm">
          {project.confirmed ? (
            <>
              <span className="font-medium text-teal-deep">Confirmed</span>
              <span className="text-slate">
                {project.confirmed_at && ` ${formatRelative(project.confirmed_at)}`}. Editing any item clears this.
              </span>
            </>
          ) : confirm.isError ? (
            <span className="text-danger">{errorMessage(confirm.error)}</span>
          ) : (
            <span className="text-slate">Generating is locked until you confirm these items.</span>
          )}
        </p>
        {project.confirmed ? (
          <Button onClick={() => navigate('../generate')}>Continue to Generate</Button>
        ) : (
          canEdit && (
            <Button disabled={confirm.isPending} onClick={() => confirm.mutate()}>
              {confirm.isPending && <Spinner className="text-white" label="Confirming" />}
              Confirm extracted items
            </Button>
          )
        )}
      </div>
    </div>
  )
}
