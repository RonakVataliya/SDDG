import type { ExtractedItem, RequirementStatement } from '@/api/client'
import { getDb, save } from '@/mocks/db'
import { renderUseCase, type UseCaseModel } from '@/mocks/render'

const EMAIL = 'dev@sddg.test'

export function seedProject({ confirmed = false, consent = false } = {}) {
  const db = getDb()
  const at = new Date().toISOString()
  db.projects.push({ id: 'pr_1', name: 'Library system', owner: EMAIL, created_at: at, updated_at: at, confirmed_at: confirmed ? at : null })
  const statements: RequirementStatement[] = [
    { id: 'st_1', ref: 'R-001', text: 'The librarian shall issue a book to a member.', label: 'FR3', source: { document: 'Pasted text', page: null, paragraph: 1 } },
  ]
  const items: ExtractedItem[] = [
    { id: 'it_1', category: 'actor', name: 'Librarian', description: null, origin: 'system-extracted', qualifiers: [], statement_ids: ['st_1'] },
    { id: 'it_2', category: 'process', name: 'Issue book', description: null, origin: 'system-extracted', qualifiers: [], statement_ids: ['st_1'] },
  ]
  db.statements.pr_1 = statements
  db.items.pr_1 = items
  db.jobs.push({
    id: 'job_x', project_id: 'pr_1', kind: 'extraction', status: 'succeeded', applied: true,
    progress: { step: 3, total: 3, label: 'Done' }, created_at: at, started_at: at, finished_at: at,
  })
  if (consent) db.consent[EMAIL] = { version: '2026-09-01', at }
  save()
}

/** A generated Use Case diagram (dg_1) on a confirmed pr_1. */
export function seedDiagram() {
  seedProject({ confirmed: true })
  const model: UseCaseModel = {
    system: 'Library system',
    actors: [{ id: 'it_1', name: 'Librarian' }],
    cases: [{ id: 'it_2', name: 'Issue book', assumed: false }],
    links: [{ actor: 'it_1', case: 'it_2' }],
  }
  const at = new Date().toISOString()
  getDb().diagrams.push({
    id: 'dg_1', project_id: 'pr_1', type: 'use_case', title: 'Library system · Use Case', created_at: at,
    parent_id: null, instruction: null, model, svg: renderUseCase(model),
  })
  save()
}
