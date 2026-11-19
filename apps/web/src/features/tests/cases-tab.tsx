import { PlusIcon, SearchIcon } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { TestCase } from '@/api/client'
import { errorMessage } from '@/api/errors'
import { useTestCases, useTestRequirements } from '@/api/queries'
import { Badge, RefTag } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Notice } from '@/components/ui/notice'
import { PageLoading } from '@/components/ui/spinner'
import { cn } from '@/lib/utils'
import { useWorkspace } from '@/routes/workspace-layout'
import { CaseDetail } from './case-detail'
import { CaseDialog } from './case-dialog'
import { KIND, PRIORITY, RESULT, TECHNIQUE } from './labels'

type Filter = 'all' | 'ready' | 'draft'

/** Cases tab: every test case with its freshness and last result; open one to read or edit it. */
export function CasesTab({ projectId }: { projectId: string }) {
  const { project } = useWorkspace()
  const canEdit = project.role !== 'viewer'
  const cases = useTestCases(projectId)
  const requirements = useTestRequirements(projectId)
  const [filter, setFilter] = useState<Filter>('all')
  const [query, setQuery] = useState('')
  const [openId, setOpenId] = useState<string | null>(null)
  const [dialog, setDialog] = useState<'add' | 'edit' | null>(null)

  const all = useMemo(() => cases.data ?? [], [cases.data])
  const shown = all.filter(
    (c) =>
      (filter === 'all' || c.status === filter) &&
      (!query.trim() || `${c.number} ${c.statement_ref} ${c.title}`.toLowerCase().includes(query.trim().toLowerCase())),
  )
  const open = all.find((c) => c.id === openId) ?? null

  if (cases.isPending) return <PageLoading label="Loading test cases" />
  if (cases.isError)
    return (
      <Notice tone="error" title="Couldn't load the test cases">
        {errorMessage(cases.error)}
      </Notice>
    )

  const count = (f: Filter) => (f === 'all' ? all.length : all.filter((c) => c.status === f).length)

  return (
    <div className={cn('grid min-h-0 flex-1 gap-4', open && 'xl:grid-cols-[minmax(0,1fr)_24rem]')}>
      <section aria-label="Test cases" className="flex min-h-0 min-w-0 flex-col rounded-xl border border-rule bg-field">
        <header className="flex flex-wrap items-center gap-2 border-b border-rule px-4 py-2.5">
          <h3 className="text-sm font-semibold">
            Test cases <span className="font-normal text-slate tabular-nums">{all.length}</span>
          </h3>
          <div role="group" aria-label="Filter by status" className="flex rounded-md border border-rule p-0.5">
            {(['all', 'ready', 'draft'] as const).map((f) => (
              <button
                key={f}
                type="button"
                aria-pressed={filter === f}
                onClick={() => setFilter(f)}
                className={cn('rounded-sm px-2 py-0.5 text-xs capitalize', filter === f ? 'bg-ink text-on-ink' : 'text-slate hover:text-ink')}
              >
                {f} {count(f)}
              </button>
            ))}
          </div>
          <label className="relative ml-auto">
            <SearchIcon className="absolute top-1/2 left-2 size-3.5 -translate-y-1/2 text-slate" />
            <span className="sr-only">Filter cases</span>
            <Input className="h-8 w-44 pl-7 text-sm" placeholder="Filter" value={query} onChange={(e) => setQuery(e.target.value)} />
          </label>
          {canEdit && (
            <Button size="sm" variant="secondary" disabled={!requirements.data?.requirements.length} onClick={() => setDialog('add')}>
              <PlusIcon /> Add case
            </Button>
          )}
        </header>
        {!all.length ? (
          <p className="px-5 py-10 text-center text-sm text-slate">No test cases yet. Generate some on the Design tab.</p>
        ) : (
          <div className="min-h-0 flex-1 overflow-auto">
            <table className="w-full text-left text-sm">
              <thead className="sticky top-0 border-b border-rule bg-field text-xs text-slate">
                <tr>
                  {['Case', 'Title', 'Technique', 'Kind', 'Priority', 'Req', 'Status', 'Freshness', 'Last result'].map((h) => (
                    <th key={h} scope="col" className="px-3 py-2 font-medium whitespace-nowrap">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-rule">
                {shown.map((c) => (
                  <CaseRow key={c.id} c={c} active={c.id === openId} onOpen={() => setOpenId(c.id === openId ? null : c.id)} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      {open && <CaseDetail c={open} canEdit={canEdit} onEdit={() => setDialog('edit')} onClose={() => setOpenId(null)} />}
      {dialog && requirements.data && (
        <CaseDialog
          key={dialog === 'edit' ? open?.id : 'add'}
          projectId={projectId}
          open
          onOpenChange={(o) => !o && setDialog(null)}
          requirements={requirements.data.requirements}
          existing={dialog === 'edit' ? (open ?? undefined) : undefined}
        />
      )}
    </div>
  )
}

function CaseRow({ c, active, onOpen }: { c: TestCase; active: boolean; onOpen: () => void }) {
  const result = c.last_result ? RESULT[c.last_result] : null
  return (
    <tr
      onClick={onOpen}
      aria-selected={active}
      className={cn('cursor-pointer align-top hover:bg-paper/70', active && 'bg-accent-wash/60', !c.kept && 'text-slate')}
    >
      <td className="px-3 py-2">
        <button type="button" className="focus-visible:outline-2" onClick={(e) => {
            e.stopPropagation()
            onOpen()
          }}>
          <RefTag>{c.number}</RefTag>
        </button>
      </td>
      <td className="max-w-80 px-3 py-2">{c.title}</td>
      <td className="px-3 py-2 font-mono text-xs whitespace-nowrap" title={TECHNIQUE[c.technique]}>
        {c.technique}
      </td>
      <td className="px-3 py-2">
        <Badge tone={KIND[c.kind].tone}>{KIND[c.kind].label}</Badge>
      </td>
      <td className="px-3 py-2">{PRIORITY[c.priority]}</td>
      <td className="px-3 py-2 font-mono text-xs">{c.statement_ref}</td>
      <td className="px-3 py-2">
        <Badge tone={c.status === 'ready' ? 'accent' : 'neutral'}>{c.status === 'ready' ? 'Ready' : c.kept ? 'Draft' : 'Discarded'}</Badge>
      </td>
      <td className="px-3 py-2 whitespace-nowrap">
        {c.freshness === 'out_of_date' ? <Badge tone="amber">Out of date · {c.statement_ref} changed</Badge> : <span className="text-slate">Current</span>}
      </td>
      <td className="px-3 py-2 whitespace-nowrap">
        {result ? (
          <span className="inline-flex items-center gap-1.5">
            <span className={cn('size-2 rounded-full', result.dot)} aria-hidden />
            {result.label}
          </span>
        ) : (
          <span className="text-slate">—</span>
        )}
      </td>
    </tr>
  )
}
