import type { ExtractedItem, RequirementStatement } from '@/api/client'
import type { InvitationRow } from '@/mocks/collab'
import { getDb, save } from '@/mocks/db'
import { renderUseCase, type UseCaseModel } from '@/mocks/render'

const EMAIL = 'dev@sddg.test'

export function seedProject({ confirmed = false, consent = false } = {}) {
  const db = getDb()
  const at = new Date().toISOString()
  db.projects.push({ id: 'pr_1', name: 'Library system', owner: EMAIL, created_at: at, updated_at: at, confirmed_at: confirmed ? at : null, extracted_nodes: confirmed ? ['actors', 'processes', 'interactions'] : [] })
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

/** An open invitation to pr_1 addressed to the signed-in user (FR24a). */
export function seedInvitation(over: Partial<InvitationRow> = {}) {
  const now = Date.now()
  const row: InvitationRow = {
    id: 'inv_1', project_id: 'pr_1', email: EMAIL, role: 'editor', token: 'tok_1',
    invited_by: 'ronak.vataliya@sddg.test', created_at: new Date(now).toISOString(),
    expires_at: new Date(now + 7 * 86_400_000).toISOString(), accepted_at: null, revoked_at: null, ...over,
  }
  getDb().collab.invitations.push(row)
  save()
  return row
}

/** pr_1 owned by someone else, so the signed-in user only reaches it through an invitation. */
export function seedOthersProject(name = 'Acme Clinic') {
  const at = new Date().toISOString()
  getDb().projects.push({
    id: 'pr_1', name, owner: 'ronak.vataliya@sddg.test', created_at: at, updated_at: at, confirmed_at: at,
    extracted_nodes: [],
  })
  save()
}
