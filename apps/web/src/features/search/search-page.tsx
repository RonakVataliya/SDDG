import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router'
import type { DiagramType } from '@/api/client'
import { errorMessage } from '@/api/errors'
import { useDiagramDetails, useDiagrams, useItems, useStatements } from '@/api/queries'
import { Badge, RefTag } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Notice } from '@/components/ui/notice'
import { PageLoading } from '@/components/ui/spinner'
import { DIAGRAM_TYPES, typeLabel } from '@/features/generate/diagram-types'
import { StepHeading } from '@/features/input/input-page'
import { useWorkspace } from '@/routes/workspace-layout'
import { getExportedIds } from './exported'
import { buildResults, filterResults, findById, looksLikeId, STATUSES, toggle, type Status } from './search'

const statusTone = { flagged: 'amber', unresolved: 'danger', exported: 'teal' } as const

export function SearchPage() {
  const { project } = useWorkspace()
  const navigate = useNavigate()
  const statements = useStatements(project.id)
  const items = useItems(project.id, undefined, 1)
  const diagrams = useDiagrams(project.id)
  const details = useDiagramDetails(diagrams.data ?? []) // the list has no element labels; each diagram's own response does

  const [query, setQuery] = useState('')
  const [statuses, setStatuses] = useState<Status[]>([])
  const [types, setTypes] = useState<DiagramType[]>([])
  const [missingId, setMissingId] = useState<string | null>(null)

  const failed = [statements, items, diagrams, ...details].find((q) => q.isError)
  if (failed) {
    return (
      <Notice tone="error" title="Couldn't load the project data">
        {errorMessage(failed.error)}
      </Notice>
    )
  }
  if (!statements.data || !items.data || !diagrams.data || details.some((q) => q.isPending)) {
    return <PageLoading label="Loading search" />
  }

  const all = buildResults({
    statements: statements.data,
    items: items.data.items,
    diagrams: diagrams.data.map((d, i) => ({ ...d, elements: details[i].data?.elements })),
    exportedIds: getExportedIds(),
  })
  const results = filterResults(all, { query, statuses, types })
  const idHit = findById(all, query)

  // Pressing Enter on an exact ID opens it; an ID that doesn't exist says so.
  function submit(e: FormEvent) {
    e.preventDefault()
    if (!looksLikeId(query)) return
    const hit = findById(all, query)
    if (hit) navigate(hit.to)
    else setMissingId(query.trim())
  }

  return (
    <div className="space-y-5">
      <StepHeading
        title="Search"
        description="Find requirements, extracted items and diagrams. Type an ID such as R-001 and press Enter to open it."
      />

      <form onSubmit={submit} className="flex gap-2">
        <Input
          type="search"
          aria-label="Search"
          placeholder="Keyword or ID"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            setMissingId(null)
          }}
        />
        <Button type="submit">Search</Button>
      </form>

      <div className="flex flex-wrap gap-x-8 gap-y-3">
        <fieldset className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <legend className="mb-1 text-sm font-medium">Status</legend>
          {STATUSES.map((s) => (
            <label key={s.value} className="flex items-center gap-2 text-sm">
              <Checkbox checked={statuses.includes(s.value)} onCheckedChange={() => setStatuses(toggle(statuses, s.value))} />
              {s.label}
            </label>
          ))}
        </fieldset>
        <fieldset className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <legend className="mb-1 text-sm font-medium">Diagram type</legend>
          {DIAGRAM_TYPES.map((t) => (
            <label key={t.value} className="flex items-center gap-2 text-sm">
              <Checkbox checked={types.includes(t.value)} onCheckedChange={() => setTypes(toggle(types, t.value))} />
              {t.label}
            </label>
          ))}
        </fieldset>
      </div>

      {missingId ? (
        <Notice tone="error" title="Not found">
          There is no requirement or diagram with the ID “{missingId}” in this project.
        </Notice>
      ) : looksLikeId(query) ? (
        // An ID is only looked up on Enter, so say so instead of showing a misleading "No results".
        <Notice title={idHit ? `Press Enter to open ${idHit.id}` : 'Press Enter to look up this ID'}>
          {idHit ? idHit.title : 'Exact IDs look like R-001 or dg_…'}
        </Notice>
      ) : results.length === 0 ? (
        <EmptyState types={types} />
      ) : (
        <ul className="divide-y divide-rule rounded-lg border border-rule bg-surface">
          {results.map((r) => (
            <li key={`${r.kind}-${r.id}`}>
              <Link to={r.to} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3 hover:bg-paper/60">
                <span className="min-w-0 flex-1">
                  <span className="block font-medium">{r.title}</span>
                  <span className="block text-sm text-slate">{r.subtitle}</span>
                </span>
                {r.statuses.map((s) => (
                  <Badge key={s} tone={statusTone[s]}>
                    {STATUSES.find((x) => x.value === s)?.label}
                  </Badge>
                ))}
                {r.kind !== 'item' && <RefTag>{r.id}</RefTag>}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function EmptyState({ types }: { types: DiagramType[] }) {
  return (
    <div className="rounded-lg border border-rule bg-surface px-5 py-8 text-center">
      <p className="font-medium">No results</p>
      <p className="mt-1 text-slate">
        {types.length > 0
          ? `No ${types.map((t) => typeLabel[t]).join(' or ')} diagrams match your search and filters.`
          : 'Nothing matches your search and filters. Try a different keyword or clear a filter.'}
      </p>
    </div>
  )
}
