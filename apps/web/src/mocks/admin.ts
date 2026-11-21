/**
 * MOCK ONLY. Admin console (FR23): the same routes, rules and messages as apps/api/routers/admin.py, over a fixed
 * in-memory list of 30 users (so paging shows). Only emails in ADMINS are administrators.
 */
import { http, HttpResponse, type HttpResponseResolver } from 'msw'
import type { AdminError, AdminSettings, AdminUsage, AdminUser } from '@/api/client'
import { feedbackHandlers } from './comments'

type Helpers = {
  u: (path: string) => string
  authed: (fn: (ctx: { email: string; params: Record<string, string | readonly string[] | undefined>; request: Request }) => Response | Promise<Response>) => HttpResponseResolver
  fail: (status: number, detail: string, code?: string) => Response
}
type Row = AdminUser & { shared_owned: number } // shared_owned: projects they alone own that others are members of

const PAGE_SIZE = 25
const ADMINS = new Set(['admin@sddg.test'])
const hoursAgo = (h: number) => new Date(Date.now() - h * 3_600_000).toISOString()
const seed = (): Row[] =>
  Array.from({ length: 30 }, (_, i) => {
    const n = i + 1
    const id = `person${String(n).padStart(2, '0')}@acme.test`
    return {
      id, email: id, is_admin: n === 1, projects: n === 5 ? 2 : n % 4, last_seen_at: n % 7 === 0 ? null : hoursAgo(n * 5),
      status: n % 9 === 0 ? 'deactivated' : 'active', shared_owned: n === 5 ? 2 : 0,
    }
  })
let rows = seed()

/** For tests and the browser console: make this email an administrator. */
export const makeAdmin = (email: string) => ADMINS.add(email)
export function resetAdminMock() {
  rows = seed()
  ADMINS.clear()
  ADMINS.add('admin@sddg.test')
}
/** Fixed numbers, shaped like the API's GET /admin/usage; tests and the demo read these. */
export const MOCK_USAGE: AdminUsage = {
  window_days: 7, active_window_minutes: 15, active_users: 14, accounts: 21, projects: 23, archived_projects: 4,
  storage_bytes: 182 * 1048576, storage_limit_bytes: 500 * 1048576, storage_warning: false,
  limits: { max_document_bytes: 10 * 1048576, max_documents_per_project: 15, max_pages_per_project: 100 },
  generation: { runs: 42, median_seconds: 38.4, p95_seconds: 131.2, median_target_seconds: 60, p95_target_seconds: 120, median_ok: true, p95_ok: false },
  events: [
    { type: 'slow', description: 'Generation took 131 s', duration_seconds: 131.2, at: new Date(Date.now() - 2 * 60_000).toISOString() },
    { type: 'rate_limit', description: 'groq extract hit a rate limit, tried 3 time(s)', duration_seconds: 4, at: new Date(Date.now() - 3_600_000).toISOString() },
    { type: 'error', description: 'generation job failed', duration_seconds: 12.5, at: new Date(Date.now() - 86_400_000).toISOString() },
  ],
}
/** Shaped like GET /admin/errors: 30 rows (so paging shows), newest first, never any document text. */
const ERROR_KINDS: Pick<AdminError, 'type' | 'severity' | 'message'>[] = [
  { type: 'api', severity: 'error', message: 'ValueError in POST /projects/{project_id}/generate' },
  { type: 'job', severity: 'error', message: 'generation job failed' },
  { type: 'ai', severity: 'error', message: 'gemini render failed, tried 1 time(s)' },
  { type: 'rate_limit', severity: 'warning', message: 'groq extract hit a rate limit, tried 3 time(s)' },
]
export const MOCK_ERRORS: AdminError[] = Array.from({ length: 30 }, (_, i) => ({
  id: `err_${i + 1}`, ...ERROR_KINDS[i % 4], project_id: i % 4 === 0 ? null : 'proj_1', at: new Date(Date.now() - (i + 1) * 600_000).toISOString(),
}))
/** Shaped like GET /admin/settings: the values the real server shows. */
export const MOCK_SETTINGS: AdminSettings = {
  ai: {
    reachable: true, job_deadline_seconds: 600,
    providers: [{ name: 'groq', model: 'openai/gpt-oss-120b', available: true }, { name: 'gemini', model: 'gemini-3.5-flash', available: true }],
  },
  ai_key_set: true, storage_limit_bytes: 500 * 1048576, invitation_expiry_days: 7,
  session_timeout_hours: 24, failed_logins_before_lock: 5, lock_minutes: 15,
}
const view = ({ shared_owned: _, ...r }: Row): AdminUser => r

export function adminHandlers({ u, authed, fail }: Helpers) {
  const asAdmin = (fn: (email: string, params: Record<string, string | readonly string[] | undefined>, request: Request) => Response) =>
    authed(({ email, params, request }) => (ADMINS.has(email) ? fn(email, params, request) : fail(403, 'Administrators only')))
  return [
    http.get(u('/me'), authed(({ email }) => HttpResponse.json({ id: email, email, is_admin: ADMINS.has(email) }))),
    http.get(
      u('/admin/users'),
      asAdmin((_, __, request) => {
        const url = new URL(request.url)
        // Like the API: a space in the search matches any text, and the rest is literal.
        const words = (url.searchParams.get('q') ?? '').toLowerCase().split(/\s+/).filter(Boolean)
        const match = new RegExp(words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('.*'))
        const page = Math.max(1, Number(url.searchParams.get('page') ?? 1))
        const found = rows
          .filter((r) => match.test(r.email.toLowerCase()))
          .sort((a, b) => (b.last_seen_at ?? '').localeCompare(a.last_seen_at ?? '') || a.email.localeCompare(b.email))
        const users = found.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE).map(view)
        return HttpResponse.json({ users, total: found.length, page, page_size: PAGE_SIZE })
      }),
    ),
    http.get(u('/admin/usage'), asAdmin(() => HttpResponse.json(MOCK_USAGE))),
    http.get(u('/admin/settings'), asAdmin(() => HttpResponse.json(MOCK_SETTINGS))),
    http.get(
      u('/admin/errors'),
      asAdmin((_, __, request) => {
        const q = new URL(request.url).searchParams
        const page = Math.max(1, Number(q.get('page') ?? 1))
        const found = MOCK_ERRORS.filter((e) => (!q.get('type') || e.type === q.get('type')) && (!q.get('severity') || e.severity === q.get('severity')))
        return HttpResponse.json({ errors: found.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE), total: found.length, page, page_size: PAGE_SIZE })
      }),
    ),
    http.post(
      u('/admin/users/:user_id/deactivate'),
      asAdmin((email, params) => {
        const r = rows.find((x) => x.id === params.user_id)
        if (!r) return fail(404, 'User not found')
        if (r.status === 'deactivated') return HttpResponse.json(view(r))
        if (r.id === email) return fail(409, "You can't deactivate your own account.")
        if (r.shared_owned)
          return fail(409, `They are the only owner of ${r.shared_owned} project${r.shared_owned === 1 ? '' : 's'} with other members. Reassign ownership first.`)
        r.status = 'deactivated'
        return HttpResponse.json(view(r))
      }),
    ),
    http.post(
      u('/admin/users/:user_id/reactivate'),
      asAdmin((_, params) => {
        const r = rows.find((x) => x.id === params.user_id)
        if (!r) return fail(404, 'User not found')
        r.status = 'active'
        return HttpResponse.json(view(r))
      }),
    ),
    // Feedback page (FR27c, Raj): the issue reports kept by src/mocks/comments.ts
    ...feedbackHandlers(u, asAdmin, fail),
  ]
}
