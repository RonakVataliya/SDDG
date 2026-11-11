import type { ExtractedItem, RequirementStatement } from '@/api/client'
import { buildResults, filterResults, findById, looksLikeId, type Filters } from './search'

const statements: RequirementStatement[] = [
  { id: 'st_1', ref: 'R-001', text: 'The librarian shall issue a book to a member.', source: { document: 'Pasted text' } },
  { id: 'st_2', ref: 'R-002', text: 'The system shall send overdue notices.', source: { document: 'Pasted text' } },
]
const item = (over: Partial<ExtractedItem>): ExtractedItem => ({
  id: 'it_1', category: 'actor', name: 'Librarian', origin: 'system-extracted', qualifiers: [], statement_ids: ['st_1'], ...over,
})
const items: ExtractedItem[] = [
  item({}), // clean
  item({ id: 'it_2', category: 'process', name: 'Send notice', qualifiers: ['low-confidence'], statement_ids: ['st_2'] }), // flagged + unresolved
  item({ id: 'it_3', name: 'Member', qualifiers: ['minimal'], origin: 'user-edited' }), // flagged, already resolved
]
const diagrams = [
  { id: 'dg_1', type: 'use_case' as const, title: 'Library system · Use Case', elements: [{ label: 'Librarian' }, { label: 'Issue book' }] },
  { id: 'dg_2', type: 'class' as const, title: 'Loan classes', elements: [{ label: 'Loan' }] },
]
const all = buildResults({ statements, items, diagrams, exportedIds: ['dg_2'] })

const none: Filters = { query: '', statuses: [], types: [] }
const ids = (f: Partial<Filters>) => filterResults(all, { ...none, ...f }).map((r) => r.id)

describe('keyword search', () => {
  it('matches requirement text', () => expect(ids({ query: 'overdue' })).toEqual(['R-002']))
  it('matches extracted-item names', () => expect(ids({ query: 'send notice' })).toEqual(['it_2']))
  it('matches diagram titles', () => expect(ids({ query: 'loan classes' })).toEqual(['dg_2']))
  it('matches diagram element labels', () => expect(ids({ query: 'issue book' })).toEqual(['dg_1']))
  it('ignores case', () => expect(ids({ query: 'LIBRARIAN' })).toEqual(['R-001', 'it_1', 'dg_1']))
})

describe('ID search', () => {
  it('finds a requirement and a diagram by exact ID, ignoring case', () => {
    expect(findById(all, 'r-001')?.to).toBe('../review?requirement=R-001')
    expect(findById(all, ' dg_2 ')?.to).toBe('../diagrams/dg_2')
  })
  it('finds nothing for a missing ID, which still looks like an ID', () => {
    expect(looksLikeId('R-999')).toBe(true)
    expect(findById(all, 'R-999')).toBeUndefined()
    expect(findById(all, 'dg_missing')).toBeUndefined()
  })
  it('does not treat a plain keyword as an ID', () => expect(looksLikeId('librarian')).toBe(false))
})

describe('status filters', () => {
  it('Flagged: anything with a qualifier, and requirements built from it', () =>
    expect(ids({ statuses: ['flagged'] })).toEqual(['R-001', 'R-002', 'it_2', 'it_3']))
  it('Unresolved: flagged and not yet edited by the user', () =>
    expect(ids({ statuses: ['unresolved'] })).toEqual(['R-002', 'it_2']))
  it('Exported: diagrams the user exported', () => expect(ids({ statuses: ['exported'] })).toEqual(['dg_2']))
  it('several statuses combine with OR', () =>
    expect(ids({ statuses: ['unresolved', 'exported'] })).toEqual(['R-002', 'it_2', 'dg_2']))
})

describe('diagram-type filters', () => {
  it('one type', () => expect(ids({ types: ['class'] })).toEqual(['dg_2']))
  it('several types combine with OR', () => expect(ids({ types: ['use_case', 'class'] })).toEqual(['dg_1', 'dg_2']))
})

describe('mixed categories', () => {
  it('status AND type', () => {
    expect(ids({ statuses: ['exported'], types: ['class'] })).toEqual(['dg_2'])
    expect(ids({ statuses: ['exported'], types: ['use_case'] })).toEqual([])
  })
  it('keyword AND status', () => expect(ids({ query: 'notice', statuses: ['unresolved'] })).toEqual(['R-002', 'it_2']))
  it('keyword AND type', () => expect(ids({ query: 'librarian', types: ['use_case'] })).toEqual(['dg_1']))
})

describe('empty results', () => {
  it('no keyword match', () => expect(ids({ query: 'zzz' })).toEqual([]))
  it('a diagram type with no diagrams', () => expect(ids({ types: ['sequence'] })).toEqual([]))
})
