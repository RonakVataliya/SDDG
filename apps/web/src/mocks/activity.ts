/** MOCK ONLY. The project Activity tab (FR22): the same filters, paging and rules as apps/api/routers/activity.py, over a
 * fixed log. The mock signs in one person at a time and that person owns the project, so only Owners ever get here. */
import { HttpResponse, http, type HttpResponseResolver } from 'msw'
import type { ActivityEvent } from '@/api/client'

type Deps = {
  u: (path: string) => string
  authed: (fn: (ctx: { email: string; params: Record<string, string | readonly string[] | undefined>; request: Request }) => Response | Promise<Response>) => HttpResponseResolver
  ownedProject: (email: string, id: unknown) => { id: string } | undefined
  notFound: () => Response
}

const WORDS: Record<string, string[]> = { members: ['member', 'role'], requirements: ['statement'], diagrams: ['diagram'], comments: ['comment'] }
const GROUP_OF = Object.fromEntries(Object.entries(WORDS).flatMap(([g, ws]) => ws.map((w) => [w, g]))) as Record<string, ActivityEvent['group']>
const PAGE_SIZE = 25
const minutesAgo = (m: number) => new Date(Date.now() - m * 60_000).toISOString()
const ev = (n: number, minutes: number, actor: string, action: string, extra: Partial<ActivityEvent> = {}): ActivityEvent => ({
  id: `act_${n}`, action, group: GROUP_OF[action.split('.')[0]] ?? null, actor_id: `dev:${actor}`, actor_email: actor,
  subject_email: null, target: null, detail: null, at: minutesAgo(minutes), ...extra,
})

/** Newest first, shaped like GET /projects/{id}/activity. */
export const MOCK_ACTIVITY: ActivityEvent[] = [
  ev(1, 2, 'dev@sddg.test', 'diagram.regenerated', { target: 'Use case diagram v3', detail: { reason: 'requirement_change' } }),
  ev(2, 15, 'priya@sddg.test', 'comment.created', { target: 'R-006' }),
  ev(3, 40, 'priya@sddg.test', 'statement.edited', { target: 'R-004 - rev 2 -> 3' }),
  ev(4, 90, 'dev@sddg.test', 'role.changed', { subject_email: 'karan@sddg.test', detail: { from: 'viewer', to: 'editor' } }),
  ev(5, 200, 'meera@sddg.test', 'member.joined', { subject_email: 'meera@sddg.test', detail: { role: 'editor' } }),
  ev(6, 300, 'dev@sddg.test', 'member.invited', { subject_email: 'meera@sddg.test', detail: { role: 'editor' } }),
]

export function activityHandlers({ u, authed, ownedProject, notFound }: Deps) {
  return [
    http.get(
      u('/projects/:project_id/activity'),
      authed(({ email, params, request }) => {
        if (!ownedProject(email, params.project_id)) return notFound()
        const q = new URL(request.url).searchParams
        const words = WORDS[q.get('group') ?? 'all']
        const page = Math.max(1, Number(q.get('page') ?? 1))
        const found = MOCK_ACTIVITY.filter((e) => (!words || words.includes(e.action.split('.')[0])) && (!q.get('actor') || e.actor_id === q.get('actor')))
        const actors = [...new Map(MOCK_ACTIVITY.map((e) => [e.actor_id, { id: e.actor_id, email: e.actor_email }])).values()]
        return HttpResponse.json({ events: found.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE), actors, total: found.length, page, page_size: PAGE_SIZE })
      }),
    ),
  ]
}
