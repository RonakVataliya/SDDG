/** MOCK ONLY. Notifications bell, invitations (FR24a) and traceability (FR17b/d/e) for the draft contract. */
import { HttpResponse, type HttpResponseResolver } from 'msw'
import type { components } from '@/api/schema'
import { advance, getDb, save, uid, type DiagramRow } from './db'

type Role = components['schemas']['Role']
type Ctx = { email: string; params: Record<string, string | readonly string[] | undefined>; request: Request }
type Deps = {
  u: (path: string) => string
  authed: (fn: (ctx: Ctx) => Response | Promise<Response>) => HttpResponseResolver
  ownedProject: (email: string, id: unknown) => { id: string; name: string; owner: string } | undefined
  fail: (status: number, detail: string, code?: string) => Response
  notFound: () => Response
  projectView: (p: never) => unknown
}

export type InvitationRow = {
  id: string
  project_id: string
  email: string
  role: Role
  token: string
  invited_by: string
  created_at: string
  expires_at: string
  accepted_at: string | null
  revoked_at: string | null
}
export type NotificationRow = {
  id: string
  user: string
  type: components['schemas']['NotificationType']
  payload: Record<string, string>
  read_at: string | null
  created_at: string
}
export type CollabState = { invitations: InvitationRow[]; notifications: NotificationRow[] }
export const emptyCollab = (): CollabState => ({ invitations: [], notifications: [] })

const state = (): CollabState => {
  const db = getDb() as unknown as { collab?: CollabState }
  db.collab ??= emptyCollab()
  return db.collab
}

const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/
const DAY = 86_400_000
const isOpen = (i: InvitationRow) => !i.accepted_at && !i.revoked_at && new Date(i.expires_at).getTime() > Date.now()
const status = (i: InvitationRow) => (i.accepted_at ? 'accepted' : i.revoked_at ? 'revoked' : isOpen(i) ? 'open' : 'expired')

function invitationView(i: InvitationRow, withToken: boolean) {
  return {
    id: i.id, project_id: i.project_id, email: i.email, role: i.role,
    invited_by: { id: i.invited_by, email: i.invited_by },
    created_at: i.created_at, expires_at: i.expires_at, token: withToken ? i.token : null,
  }
}

/** Every open invitation for this address reaches the bell, like the server's sync on read. */
function syncBell(email: string) {
  const s = state()
  // Issue #36: a generation that has finished tells every member of the project, once.
  for (const job of getDb().jobs) {
    if (job.kind !== 'generation') continue
    const done = advance(job)
    if (done.status !== 'succeeded' && done.status !== 'failed') continue
    const project = getDb().projects.find((p) => p.id === done.project_id)
    if (!project || project.owner !== email) continue
    if (s.notifications.some((n) => n.user === email && n.payload.job_id === done.id)) continue
    s.notifications.push({
      id: uid('nt'), user: email,
      type: done.status === 'succeeded' ? 'generation_ready' : 'generation_failed',
      payload: {
        project_id: project.id, job_id: done.id,
        ...(done.diagram_ids?.[0] ? { diagram_id: done.diagram_ids[0] } : {}),
      },
      read_at: null, created_at: done.finished_at ?? new Date().toISOString(),
    })
  }
  for (const i of s.invitations.filter((x) => x.email === email && isOpen(x))) {
    if (!s.notifications.some((n) => n.user === email && n.payload.invitation_id === i.id)) {
      s.notifications.push({
        id: uid('nt'), user: email, type: 'invitation',
        payload: { invitation_id: i.id, project_id: i.project_id, from_user_id: i.invited_by },
        read_at: null, created_at: i.created_at,
      })
    }
  }
}

function notificationView(n: NotificationRow) {
  const s = state()
  const project = getDb().projects.find((p) => p.id === n.payload.project_id)
  const inv = s.invitations.find((i) => i.id === n.payload.invitation_id)
  return {
    id: n.id, type: n.type, payload: n.payload, read_at: n.read_at, created_at: n.created_at,
    project: project ? { id: project.id, name: project.name } : null,
    from_user: n.payload.from_user_id ? { id: n.payload.from_user_id, email: n.payload.from_user_id } : null,
    invitation: inv ? { id: inv.id, role: inv.role, email: inv.email, status: status(inv), expires_at: inv.expires_at } : null,
  }
}

const mine = (email: string) => {
  syncBell(email)
  return state().notifications.filter((n) => n.user === email).slice().reverse()
}

/** Projects this user reached by accepting an invitation, with the role they were given. */
export function acceptedProjects(email: string) {
  return state()
    .invitations.filter((i) => i.email === email && i.accepted_at)
    .flatMap((i) => {
      const p = getDb().projects.find((x) => x.id === i.project_id)
      return p ? [{ project: p, role: i.role, joined_at: i.accepted_at!, owner_email: p.owner }] : []
    })
}

/* ---------- traceability (FR17b, FR17d, FR17e) ---------- */

const words = (text: string) => new Set((text.toLowerCase().match(/[a-z0-9]+/g) ?? []).map((w) => w.replace(/(ing|es|ed|s|e)$/, '')))
const STOP = new Set(['a', 'an', 'the', 'of', 'to', 'for', 'and', 'or', 'in', 'on', 'by', 'with', 'from', 'is', 'are', 'be'])

/** Does the requirement text talk about this label? Same rule as the server's core/traceability.py. */
export function mentions(text: string, label: string) {
  const have = words(text)
  const need = [...words(label)].filter((w) => !STOP.has(w))
  return need.length > 0 && need.every((w) => have.has(w))
}

/** The elements of a mock diagram, as the real API returns them (model item, label, source requirements). */
export function elementsOf(d: DiagramRow) {
  const model = d.model
  if (!model) return []
  return [
    ...model.actors.map((a) => ({ element_id: a.id, model_item_id: a.id, kind: 'actor', label: a.name })),
    ...model.cases.map((c) => ({ element_id: c.id, model_item_id: c.assumed ? null : c.id, kind: 'use_case', label: c.name })),
  ].map((e) => {
    const statements = getDb().statements[d.project_id] ?? []
    const refs = statements.filter((s) => mentions(s.text, e.label)).map((s) => s.id)
    return { ...e, statement_ids: refs, is_assumption: refs.length === 0 }
  })
}

const latestOf = (projectId: string) => {
  const byTitle = new Map<string, DiagramRow[]>()
  for (const d of getDb().diagrams.filter((x) => x.project_id === projectId)) {
    byTitle.set(d.title, [...(byTitle.get(d.title) ?? []), d])
  }
  return [...byTitle.values()].map((versions) => ({
    row: versions[versions.length - 1],
    version: versions.length,
  }))
}

export function collabHandlers({ u, authed, ownedProject, fail, notFound, projectView }: Deps, http: typeof import('msw').http) {
  const project = (email: string, id: unknown) => ownedProject(email, id) ?? getDb().projects.find((p) => p.id === id && state().invitations.some((i) => i.project_id === p.id && i.email === email && i.accepted_at))
  /** The caller's role on a project they can reach: the owner is an Owner, everyone else joined with a role. */
  const roleOf = (email: string, p: { id: string; owner: string }): Role =>
    p.owner === email
      ? 'owner'
      : (state().invitations.find((i) => i.project_id === p.id && i.email === email && i.accepted_at)?.role ?? 'viewer')

  return [
    http.get(u('/notifications'), authed(({ email }) => {
      const items = mine(email)
      return HttpResponse.json({ unread_count: items.filter((n) => !n.read_at).length, items: items.map(notificationView) })
    })),
    http.get(u('/notifications/unread-count'), authed(({ email }) =>
      HttpResponse.json({ count: mine(email).filter((n) => !n.read_at).length }))),
    http.post(u('/notifications/read-all'), authed(({ email }) => {
      for (const n of mine(email)) n.read_at ??= new Date().toISOString()
      save()
      return new HttpResponse(null, { status: 204 })
    })),
    http.post(u('/notifications/:notification_id/read'), authed(({ email, params }) => {
      const n = state().notifications.find((x) => x.id === params.notification_id && x.user === email)
      if (!n) return notFound()
      n.read_at ??= new Date().toISOString()
      save()
      return new HttpResponse(null, { status: 204 })
    })),

    http.get(u('/projects/:project_id/invitations'), authed(({ email, params }) => {
      const p = project(email, params.project_id)
      if (!p) return notFound()
      const open = state().invitations.filter((i) => i.project_id === p.id && isOpen(i))
      return HttpResponse.json(open.map((i) => invitationView(i, p.owner === email)))
    })),
    http.post(u('/projects/:project_id/invitations'), authed(async ({ email, params, request }) => {
      const p = ownedProject(email, params.project_id)
      if (!p) return getDb().projects.some((x) => x.id === params.project_id) ? fail(403, 'Only an Owner can invite people or revoke invitations.') : notFound()
      const body = (await request.json()) as { email?: string; role?: Role }
      const address = (body.email ?? '').trim().toLowerCase()
      if (!EMAIL.test(address)) return fail(422, 'Enter a valid email address.')
      if (address === p.owner) return fail(409, 'That person is already a member of this project.')
      const s = state()
      if (s.invitations.some((i) => i.project_id === p.id && i.email === address && i.accepted_at))
        return fail(409, 'That person is already a member of this project.')
      if (s.invitations.some((i) => i.project_id === p.id && i.email === address && isOpen(i)))
        return fail(409, 'That person already has an open invitation. Revoke it first to send a new one.')
      const now = new Date()
      const row: InvitationRow = {
        id: uid('inv'), project_id: p.id, email: address, role: body.role ?? 'viewer', token: uid('tok'),
        invited_by: email, created_at: now.toISOString(), expires_at: new Date(now.getTime() + 7 * DAY).toISOString(),
        accepted_at: null, revoked_at: null,
      }
      s.invitations.push(row)
      save()
      return HttpResponse.json(invitationView(row, true), { status: 201 })
    })),
    http.delete(u('/projects/:project_id/invitations/:invitation_id'), authed(({ email, params }) => {
      const p = ownedProject(email, params.project_id)
      if (!p) return getDb().projects.some((x) => x.id === params.project_id) ? fail(403, 'Only an Owner can invite people or revoke invitations.') : notFound()
      const i = state().invitations.find((x) => x.id === params.invitation_id && x.project_id === p.id && isOpen(x))
      if (!i) return notFound()
      i.revoked_at = new Date().toISOString()
      save()
      return new HttpResponse(null, { status: 204 })
    })),

    http.post(u('/invitations/accept'), authed(async ({ email, request }) => {
      const { token } = (await request.json()) as { token?: string }
      return acceptInvitation(state().invitations.find((i) => i.token === token), email, fail, notFound, projectView)
    })),
    http.post(u('/invitations/:invitation_id/accept'), authed(({ email, params }) =>
      acceptInvitation(state().invitations.find((i) => i.id === params.invitation_id), email, fail, notFound, projectView))),

    http.get(u('/projects/:project_id/coverage'), authed(({ email, params }) => {
      const p = project(email, params.project_id)
      if (!p) return notFound()
      const statements = getDb().statements[p.id] ?? []
      const latest = latestOf(p.id)
      const rows = statements.map((s) => {
        const drawn = latest.filter(({ row }) => elementsOf(row).some((e) => e.statement_ids.includes(s.id)))
        return {
          id: s.id, ref: s.ref, text: s.text, label: s.label ?? null, source: s.source.document,
          diagrams: drawn.map(({ row, version }) => ({ id: row.id, type: row.type, title: row.title, version })),
          open_flags: [], tests: null,
        }
      })
      const missing = rows.filter((r) => !r.diagrams.length).map((r) => r.ref)
      return HttpResponse.json({
        total: rows.length, with_diagrams: rows.length - missing.length, not_represented: missing.length,
        not_represented_refs: missing, with_open_flags: 0, with_tests: null, rows,
      })
    })),

    http.get(u('/diagrams/:diagram_id/drift'), authed(({ email, params }) => {
      const d = getDb().diagrams.find((x) => x.id === params.diagram_id)
      if (!d || !project(email, d.project_id)) return notFound()
      let root = d
      const seen = new Set([d.id])
      while (root.parent_id && !seen.has(root.parent_id)) {
        const parent = getDb().diagrams.find((x) => x.id === root.parent_id)
        if (!parent) break
        seen.add(parent.id)
        root = parent
      }
      if (root.id === d.id) return HttpResponse.json({ baseline_id: null, warnings: [] })
      const statements = getDb().statements[d.project_id] ?? []
      const here = new Set(elementsOf(d).map((e) => e.label.toLowerCase()))
      const warnings = elementsOf(root)
        .filter((e) => !e.is_assumption && !here.has(e.label.toLowerCase()))
        .flatMap((e) =>
          statements
            .filter((s) => e.statement_ids.includes(s.id) && mentions(s.text, e.label))
            .map((s) => ({
              id: `element_removed:${e.element_id}:${s.id}`, kind: 'element_removed' as const, element_id: e.element_id,
              label: e.label, statement_id: s.id, ref: s.ref,
              message: `${s.ref} calls for "${e.label}", but this version no longer has it.`,
            })),
        )
      return HttpResponse.json({ baseline_id: root.id, warnings })
    })),

    http.get(u('/projects/:project_id/traceability/naming'), authed(({ email, params }) => {
      const p = project(email, params.project_id)
      if (!p) return notFound()
      const byItem = new Map<string, Map<string, { diagram_id: string; title: string; version: number }[]>>()
      for (const { row, version } of latestOf(p.id)) {
        for (const e of elementsOf(row)) {
          if (!e.model_item_id || !e.label.trim()) continue
          const labels = byItem.get(e.model_item_id) ?? new Map()
          const label = e.label.trim().replace(/\s+/g, ' ')
          labels.set(label, [...(labels.get(label) ?? []), { diagram_id: row.id, title: row.title, version }])
          byItem.set(e.model_item_id, labels)
        }
      }
      const items = getDb().items[p.id] ?? []
      const issues = [...byItem.entries()]
        .filter(([, labels]) => labels.size > 1)
        .map(([model_item_id, labels]) => ({
          model_item_id,
          names: [...labels.entries()].map(([label, diagrams]) => ({ label, diagrams })),
          item_name: items.find((i) => i.id === model_item_id)?.name ?? null,
        }))
      return HttpResponse.json({ issues })
    })),

    http.post(u('/projects/:project_id/traceability/naming/apply'), authed(async ({ email, params, request }) => {
      const p = project(email, params.project_id)
      if (!p) return notFound()
      // Like the API: renaming across diagrams needs Editor, so a Viewer is refused even if the UI offered it.
      if (roleOf(email, p) === 'viewer') return fail(403, 'Not permitted: your role on this project does not allow this.')
      const body = (await request.json()) as { model_item_id?: string; name?: string }
      const name = (body.name ?? '').trim().replace(/\s+/g, ' ')
      if (!name) return fail(422, 'Choose a name.')
      const touched = latestOf(p.id).filter(({ row }) =>
        elementsOf(row).some((e) => e.model_item_id === body.model_item_id))
      if (!touched.length) return notFound()
      const updated = []
      for (const { row, version } of touched) {
        const model = row.model
        if (!model) continue
        const rename = <T extends { id: string; name: string }>(x: T) => (x.id === body.model_item_id ? { ...x, name } : x)
        const next = { ...model, actors: model.actors.map(rename), cases: model.cases.map(rename) }
        if (JSON.stringify(next) === JSON.stringify(model)) continue
        const copy: DiagramRow = {
          ...row, id: uid('dg'), created_at: new Date().toISOString(), parent_id: row.id,
          instruction: `Renamed to "${name}" on all diagrams`, model: next,
        }
        getDb().diagrams.push(copy)
        updated.push({ id: copy.id, type: copy.type, title: copy.title, version: version + 1 })
      }
      const item = (getDb().items[p.id] ?? []).find((i) => i.id === body.model_item_id)
      if (item) item.name = name
      save()
      return HttpResponse.json({ updated })
    })),
  ]
}

function acceptInvitation(
  i: InvitationRow | undefined,
  email: string,
  fail: Deps['fail'],
  notFound: Deps['notFound'],
  projectView: Deps['projectView'],
) {
  if (!i || i.email !== email) return notFound()
  if (i.revoked_at) return fail(410, 'This invitation was withdrawn.')
  if (!i.accepted_at && new Date(i.expires_at).getTime() <= Date.now())
    return fail(410, 'This invitation has expired. Ask for a new one.')
  i.accepted_at ??= new Date().toISOString()
  for (const n of state().notifications.filter((n) => n.user === email && n.payload.invitation_id === i.id))
    n.read_at ??= new Date().toISOString()
  const p = getDb().projects.find((x) => x.id === i.project_id)
  if (!p) return notFound()
  save()
  return HttpResponse.json({ ...(projectView(p as never) as object), role: i.role, owner_email: p.owner })
}
