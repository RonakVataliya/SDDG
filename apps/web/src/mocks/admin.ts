/**
 * MOCK ONLY. Admin console (FR23): the same routes, rules and messages as apps/api/routers/admin.py, over a fixed
 * in-memory list of 30 users (so paging shows). Only emails in ADMINS are administrators.
 */
import { http, HttpResponse, type HttpResponseResolver } from 'msw'
import type { AdminUser } from '@/api/client'

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
  ]
}
