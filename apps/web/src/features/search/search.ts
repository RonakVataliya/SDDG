import type { DiagramType, ExtractedItem, RequirementStatement } from '@/api/client'
import { typeLabel } from '@/features/generate/diagram-types'
import { categoryLabel } from '@/features/review/labels'

export type Status = 'flagged' | 'unresolved' | 'exported'

export const STATUSES: { value: Status; label: string }[] = [
  { value: 'flagged', label: 'Flagged' },
  { value: 'unresolved', label: 'Unresolved' },
  { value: 'exported', label: 'Exported' },
]

/** One searchable thing: a requirement, an extracted item, or a diagram. */
export type SearchResult = {
  kind: 'requirement' | 'item' | 'diagram'
  id: string // what the user can type to open it: "R-001" or "dg_…"
  title: string
  subtitle: string
  to: string // route, relative to the search page
  fields: string[] // every text the keyword search looks at
  statuses: Status[]
  diagramType?: DiagramType // diagrams only
}

export type Filters = { query: string; statuses: Status[]; types: DiagramType[] }

type DiagramInput = { id: string; type: DiagramType; title: string; elements?: { label: string }[] }

/* ---------- statuses ---------- */

/**
 * An item is flagged when the extractor attached a qualifier to it (low confidence, incomplete, …).
 * It stays unresolved until the user has edited it.
 */
function itemStatuses(item: ExtractedItem): Status[] {
  if (item.qualifiers.length === 0) return []
  return item.origin === 'system-extracted' ? ['flagged', 'unresolved'] : ['flagged']
}

/* ---------- building the list ---------- */

export function buildResults(input: {
  statements: RequirementStatement[]
  items: ExtractedItem[]
  diagrams: DiagramInput[]
  exportedIds: string[]
}): SearchResult[] {
  const requirements = input.statements.map((s): SearchResult => ({
    kind: 'requirement',
    id: s.ref,
    title: s.text,
    subtitle: 'Requirement',
    to: `../review?requirement=${s.ref}`,
    fields: [s.text],
    // A requirement takes the statuses of the items extracted from it.
    statuses: [...new Set(input.items.filter((i) => i.statement_ids.includes(s.id)).flatMap(itemStatuses))],
  }))

  const items = input.items.map((i): SearchResult => ({
    kind: 'item',
    id: i.id,
    title: i.name,
    subtitle: categoryLabel[i.category],
    to: '../review',
    fields: [i.name],
    statuses: itemStatuses(i),
  }))

  const diagrams = input.diagrams.map((d): SearchResult => ({
    kind: 'diagram',
    id: d.id,
    title: d.title,
    subtitle: `${typeLabel[d.type]} diagram`,
    to: `../diagrams/${d.id}`,
    fields: [d.title, ...(d.elements ?? []).map((e) => e.label)],
    statuses: input.exportedIds.includes(d.id) ? ['exported'] : [],
    diagramType: d.type,
  }))

  return [...requirements, ...items, ...diagrams]
}

/* ---------- searching ---------- */

/** Different filter categories combine with AND; the values inside one category combine with OR. */
export function filterResults(results: SearchResult[], { query, statuses, types }: Filters): SearchResult[] {
  const text = query.trim().toLowerCase()
  return results.filter(
    (r) =>
      (text === '' || r.fields.some((f) => f.toLowerCase().includes(text))) &&
      (statuses.length === 0 || statuses.some((s) => r.statuses.includes(s))) &&
      // Only diagrams have a type, so choosing a type hides requirements and items.
      (types.length === 0 || (r.diagramType !== undefined && types.includes(r.diagramType))),
  )
}

/** Requirement IDs look like R-001; diagram IDs look like dg_… */
export const looksLikeId = (query: string) => /^(R-\d+|dg_\w+)$/i.test(query.trim())

export function findById(results: SearchResult[], query: string): SearchResult | undefined {
  const id = query.trim().toLowerCase()
  return results.find((r) => r.kind !== 'item' && r.id.toLowerCase() === id)
}

export function toggle<T>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value]
}
