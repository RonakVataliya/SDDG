/**
 * MOCK ONLY. Comments and issue reports (FR32, FR27a-b): the same routes, rules and messages as
 * apps/api/routers/comments.py, kept in the in-browser mock database. The mock signs in one person at a time and that
 * person owns the project, so they can resolve any thread and see every report.
 */
import { http, HttpResponse, type HttpResponseResolver } from 'msw'
import type { Schemas } from '@/api/client'
import { typeLabel } from '@/features/generate/diagram-types'
import { collabState } from './collab'
import { getDb, membersOf, save, uid } from './db'

type Comment = Schemas['Comment']
type Helpers = {
  u: (path: string) => string
  authed: (fn: (ctx: { email: string; params: Record<string, string | readonly string[] | undefined>; request: Request }) => Response | Promise<Response>) => HttpResponseResolver
  ownedProject: (email: string, id: unknown) => { id: string; owner: string } | undefined
  fail: (status: number, detail: string, code?: string) => Response
  notFound: () => Response
}

const MAX_BODY = 2000
const memberId = (email: string) => `dev:${email}`
const firstName = (email: string) => {
  const local = email.split('@')[0]
  return local.slice(0, 1).toUpperCase() + local.slice(1)
}
/** Kept on the mock database object, so it is cleared with it (between tests) and saved with it (in the browser). */
type Row = Comment & { project_id: string }
const rows = () => ((getDb() as unknown as { comments?: Row[] }).comments ??= [])
const view = ({ project_id: _, ...c }: Row): Comment => c

function targetLabel(pid: string, type: Comment['target_type'], id: string): string | null {
  if (type === 'project') return id === pid ? 'Project' : null
  if (type === 'statement') return getDb().statements[pid]?.find((s) => s.id === id)?.ref ?? null
  const d = getDb().diagrams.find((x) => x.id === id && x.project_id === pid)
  return d ? `${typeLabel[d.type] ?? d.type} diagram` : null
}

export function commentsHandlers({ u, authed, ownedProject, fail, notFound }: Helpers) {
  return [
    http.get(
      u('/projects/:project_id/comments'),
      authed(({ email, params, request }) => {
        if (!ownedProject(email, params.project_id)) return notFound()
        const q = new URL(request.url).searchParams
        const found = rows().filter(
          (c) => c.project_id === params.project_id && (!q.get('target_type') || c.target_type === q.get('target_type')) && (!q.get('target_id') || c.target_id === q.get('target_id')),
        )
        return HttpResponse.json(found.map(view))
      }),
    ),
    http.post(
      u('/projects/:project_id/comments'),
      authed(async ({ email, params, request }) => {
        const p = ownedProject(email, params.project_id)
        if (!p) return notFound()
        const b = (await request.json()) as Schemas['CommentCreate']
        const body = (b.body ?? '').trim()
        if (!body) return fail(422, 'Write a comment first.')
        if (body.length > MAX_BODY) return fail(422, `A comment can be at most ${MAX_BODY} characters.`)
        const label = targetLabel(p.id, b.target_type, b.target_id)
        if (!label) return notFound()
        const members = new Set(membersOf(p.id).map((m) => memberId(m.email)))
        if ((b.mentions ?? []).some((m) => !members.has(m))) return fail(422, 'You can only mention members of this project.')
        const row: Row = {
          id: uid('cm'), project_id: p.id, target_type: b.target_type, target_id: b.target_id, target_label: label, body,
          is_issue_report: !!b.is_issue_report, status: 'open', author: { id: memberId(email), email },
          resolved_by: null, resolved_at: null, created_at: new Date().toISOString(),
        }
        rows().push(row)
        // FR32: everyone named with @, except yourself, gets a 'mention' in the bell. IDs and the target's label
        // only, exactly like core/notifications.py notify_mentions: never the comment's text.
        for (const id of new Set(b.mentions ?? [])) {
          if (id === memberId(email)) continue
          collabState().notifications.push({
            id: uid('nt'), user: id.replace(/^dev:/, ''), type: 'mention',
            payload: {
              project_id: p.id, comment_id: row.id, from_user_id: email,
              target_type: b.target_type, target_id: b.target_id, target: label,
            },
            read_at: null, created_at: row.created_at,
          })
        }
        save()
        return HttpResponse.json(view(row), { status: 201 })
      }),
    ),
    http.post(
      u('/projects/:project_id/comments/:comment_id/resolve'),
      authed(({ email, params }) => {
        if (!ownedProject(email, params.project_id)) return notFound()
        const row = rows().find((c) => c.id === params.comment_id && c.project_id === params.project_id)
        if (!row) return notFound()
        if (row.status === 'open') Object.assign(row, { status: 'resolved', resolved_by: firstName(email), resolved_at: new Date().toISOString() })
        save()
        return HttpResponse.json(view(row))
      }),
    ),
    http.get(
      u('/projects/:project_id/reports'),
      authed(({ email, params }) => {
        if (!ownedProject(email, params.project_id)) return notFound()
        const found = rows().filter((c) => c.project_id === params.project_id && c.is_issue_report)
        return HttpResponse.json(found.reverse().map(view))
      }),
    ),
  ]
}

// --- Raj: admin Feedback page (FR27c) ------------------------------------------------------------------------------
type AsAdmin = (fn: (email: string, params: Record<string, string | readonly string[] | undefined>, request: Request) => Response) => HttpResponseResolver
type Feedback = Schemas['AdminFeedback']
const FEEDBACK_PAGE = 25

function feedbackView(c: Row): Feedback {
  return {
    id: c.id, report: c.body, on: c.target_type === 'project' ? 'Project export' : c.target_label, target_type: c.target_type,
    target_id: c.target_id, project_id: c.project_id, project_name: getDb().projects.find((p) => p.id === c.project_id)?.name ?? '',
    from: c.author.email, status: c.status, resolved_by: c.resolved_by, resolved_at: c.resolved_at, at: c.created_at,
  }
}

/** GET /admin/feedback and POST /admin/feedback/{id}/resolve over the issue reports above; asAdmin comes from admin.ts. */
export function feedbackHandlers(u: (path: string) => string, asAdmin: AsAdmin, fail: Helpers['fail']) {
  return [
    http.get(
      u('/admin/feedback'),
      asAdmin((_, __, request) => {
        const q = new URL(request.url).searchParams
        const page = Math.max(1, Number(q.get('page') ?? 1))
        const found = rows()
          .filter((c) => c.is_issue_report && (!q.get('status') || c.status === q.get('status')))
          .sort((a, b) => b.created_at.localeCompare(a.created_at))
        return HttpResponse.json({ reports: found.slice((page - 1) * FEEDBACK_PAGE, page * FEEDBACK_PAGE).map(feedbackView), total: found.length, page, page_size: FEEDBACK_PAGE })
      }),
    ),
    http.post(
      u('/admin/feedback/:report_id/resolve'),
      asAdmin((email, params) => {
        const c = rows().find((x) => x.id === params.report_id && x.is_issue_report)
        if (!c) return fail(404, 'Report not found')
        if (c.status === 'open') Object.assign(c, { status: 'resolved', resolved_by: firstName(email), resolved_at: new Date().toISOString() })
        save()
        return HttpResponse.json(feedbackView(c))
      }),
    ),
  ]
}
// --- end Raj: admin Feedback ---------------------------------------------------------------------------------------
