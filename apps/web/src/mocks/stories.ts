/**
 * MOCK ONLY. Stories backlog (3.4): the same routes, rules and messages as apps/api/routers/stories.py, backed by the
 * in-browser mock database. The mock has no other members, so the owner is the only assignee.
 */
import { http, HttpResponse, type HttpResponseResolver } from 'msw'
import type { Story } from '@/api/client'
import { getDb, save, uid, type StoryRow } from './db'

type Helpers = {
  u: (path: string) => string
  authed: (fn: (ctx: { email: string; params: Record<string, string | readonly string[] | undefined>; request: Request }) => Response | Promise<Response>) => HttpResponseResolver
  ownedProject: (email: string, id: unknown) => { id: string; owner: string } | undefined
  fail: (status: number, detail: string, code?: string) => Response
  notFound: () => Response
}

type Fields = Partial<Omit<StoryRow, 'id' | 'project_id' | 'ref' | 'created_at' | 'updated_at'>>
const LABELS = { role: 'user role', goal: 'goal', reason: 'reason' } as const
const PRIORITIES = ['must', 'should', 'could', 'wont']
const STATUSES = ['todo', 'in_progress', 'done']
const KEYS = ['role', 'goal', 'reason', 'priority', 'estimate', 'status', 'assignee_id', 'confirmations', 'statement_ids'] as const
// Like the API's request models: unknown fields are ignored.
const pick = (body: Record<string, unknown>): Fields => Object.fromEntries(Object.entries(body).filter(([k]) => (KEYS as readonly string[]).includes(k)))
const members = (p: { owner: string }) => [{ id: p.owner, email: p.owner }]

/** Mirrors the API's _clean: trims and checks the given fields in place; returns the refusal message, if any. */
function clean(p: { id: string; owner: string }, f: Fields): string | null {
  for (const [k, label] of Object.entries(LABELS) as [keyof typeof LABELS, string][]) {
    if (k in f) {
      f[k] = String(f[k] ?? '').trim()
      if (f[k]!.length < 1 || f[k]!.length > 300) return `The ${label} must be 1 to 300 characters.`
    }
  }
  // The API's request model refuses these with a 422 before _clean runs.
  if ('priority' in f && !PRIORITIES.includes(f.priority!)) return 'Unknown priority.'
  if ('status' in f && !STATUSES.includes(f.status!)) return 'Unknown status.'
  if (f.estimate != null && !(Number.isInteger(f.estimate) && f.estimate >= 0 && f.estimate <= 100)) return 'The estimate must be 0 to 100.'
  if (f.confirmations) {
    f.confirmations = f.confirmations.map((c) => c.trim()).filter(Boolean)
    if (f.confirmations.length > 20 || f.confirmations.some((c) => c.length > 500))
      return 'A story can have at most 20 confirmations of up to 500 characters each.'
  }
  if (f.statement_ids) {
    f.statement_ids = [...new Set(f.statement_ids)]
    if (!f.statement_ids.length) return 'A story must link to at least one requirement.'
    const live = new Set((getDb().statements[p.id] ?? []).map((s) => s.id))
    if (!f.statement_ids.every((s) => live.has(s))) return 'A story can only link to requirements of this project.'
  }
  if (f.assignee_id && !members(p).some((m) => m.id === f.assignee_id)) return 'The assignee must be a member of this project.'
  return null
}

/** The API drops a deleted requirement's links (ON DELETE CASCADE); the mock does it on read instead. */
function view(s: StoryRow): Story {
  const { project_id, ...rest } = s
  const live = new Set((getDb().statements[project_id] ?? []).map((st) => st.id))
  const assignee = getDb().projects.find((p) => p.id === project_id && p.owner === s.assignee_id)
  return { ...rest, statement_ids: s.statement_ids.filter((id) => live.has(id)), assignee_email: assignee?.owner ?? null }
}

export function storiesHandlers({ u, authed, ownedProject, fail, notFound }: Helpers) {
  const find = (pid: string, id: unknown) => getDb().stories.find((s) => s.project_id === pid && s.id === id)
  return [
    http.get(
      u('/projects/:project_id/stories'),
      authed(({ email, params }) => {
        const p = ownedProject(email, params.project_id)
        if (!p) return notFound()
        const stories = getDb().stories.filter((s) => s.project_id === p.id).map(view)
        return HttpResponse.json({ stories, members: members(p) })
      }),
    ),
    http.post(
      u('/projects/:project_id/stories'),
      authed(async ({ email, params, request }) => {
        const p = ownedProject(email, params.project_id)
        if (!p) return notFound()
        const f: Fields = { priority: 'should', estimate: null, status: 'todo', assignee_id: null, confirmations: [], statement_ids: [], ...pick(await request.json()) }
        const refusal = clean(p, f)
        if (refusal) return fail(422, refusal)
        const db = getDb()
        // S-numbers are never reused, so numbering continues from the last story ever issued.
        const n = db.nextStory[p.id] ?? 1
        db.nextStory[p.id] = n + 1
        const at = new Date().toISOString()
        const row = { ...(f as Required<Fields>), id: uid('us'), project_id: p.id, ref: `S-${String(n).padStart(3, '0')}`, created_at: at, updated_at: at }
        db.stories.push(row)
        save()
        return HttpResponse.json(view(row), { status: 201 })
      }),
    ),
    http.patch(
      u('/projects/:project_id/stories/:story_id'),
      authed(async ({ email, params, request }) => {
        const p = ownedProject(email, params.project_id)
        const s = p && find(p.id, params.story_id)
        if (!p || !s) return notFound()
        const f = pick(await request.json())
        const refusal = clean(p, f)
        if (refusal) return fail(422, refusal)
        Object.assign(s, f, { updated_at: new Date().toISOString() })
        save()
        return HttpResponse.json(view(s))
      }),
    ),
    http.delete(
      u('/projects/:project_id/stories/:story_id'),
      authed(({ email, params }) => {
        const p = ownedProject(email, params.project_id)
        if (!p || !find(p.id, params.story_id)) return notFound()
        getDb().stories = getDb().stories.filter((s) => s.id !== params.story_id)
        save()
        return new HttpResponse(null, { status: 204 })
      }),
    ),
  ]
}
