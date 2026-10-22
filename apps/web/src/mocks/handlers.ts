/** MOCK ONLY. MSW handlers for the FE draft contract (src/api/openapi.draft.yaml). Delete once H3 is live. */
import { delay, http, HttpResponse, type HttpResponseResolver } from 'msw'
import { AI_SECTION_VERSION } from '@/features/privacy/policy'
import { env } from '@/lib/env'
import { advance, createJob, diagramView, getDb, projectView, publicJob, save, touch, uid, type DiagramRow } from './db'
import { applyInstruction } from './edit'
import { layoutView } from './layout'
import { renderUseCase } from './render'

const base = env.apiUrl.replace(/\/$/, '')
const u = (path: string) => `${base}${path}`
const fail = (status: number, detail: string, code?: string) => HttpResponse.json({ detail, code }, { status })

let coldStartRemaining = env.mockColdStart ? 4 : 0

/** Resolves the caller from the bearer token: a mock token or a real Supabase JWT. */
function caller(request: Request): string | null {
  const token = request.headers.get('Authorization')?.replace(/^Bearer\s+/i, '')
  if (!token) return null
  if (token.startsWith('mock-token:')) return token.slice('mock-token:'.length)
  try {
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
    return (payload.email as string) ?? null
  } catch {
    return null
  }
}

type Ctx = { email: string; params: Record<string, string | readonly string[] | undefined>; request: Request }

/** Wraps a handler with latency, the cold-start simulation (FR30c) and the 401 check (NFR4a). */
function authed(fn: (ctx: Ctx) => Response | Promise<Response>): HttpResponseResolver {
  return async ({ request, params }) => {
    await delay(env.useMocks ? 250 : 0)
    if (coldStartRemaining > 0) {
      coldStartRemaining--
      return fail(503, 'Service is waking up')
    }
    const email = caller(request)
    if (!email) return fail(401, 'Your session has ended. Log in again.')
    return fn({ email, params, request })
  }
}

function ownedProject(email: string, id: unknown) {
  return getDb().projects.find((p) => p.id === id && p.owner === email)
}
const notFound = () => fail(404, 'Not found, or you do not have access to it.')

export const handlers = [
  http.get(u('/health'), () => HttpResponse.json({ status: 'ok' })),

  http.get(
    u('/me/consent'),
    authed(({ email }) => {
      const c = getDb().consent[email]
      return HttpResponse.json({
        consented: c?.version === AI_SECTION_VERSION,
        policy_version: c?.version ?? null,
        consented_at: c?.at ?? null,
        current_policy_version: AI_SECTION_VERSION,
      })
    }),
  ),
  http.post(
    u('/me/consent'),
    authed(async ({ email, request }) => {
      const { policy_version } = (await request.json()) as { policy_version: string }
      const at = new Date().toISOString()
      getDb().consent[email] = { version: policy_version, at }
      save()
      return HttpResponse.json(
        { consented: policy_version === AI_SECTION_VERSION, policy_version, consented_at: at, current_policy_version: AI_SECTION_VERSION },
        { status: 201 },
      )
    }),
  ),

  http.get(
    u('/projects'),
    authed(({ email }) =>
      HttpResponse.json(
        getDb()
          .projects.filter((p) => p.owner === email)
          .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
          .map(projectView),
      ),
    ),
  ),
  http.post(
    u('/projects'),
    authed(async ({ email, request }) => {
      const { name } = (await request.json()) as { name: string }
      const trimmed = (name ?? '').trim()
      if (trimmed.length < 1 || trimmed.length > 100) return fail(422, 'Project names must be 1–100 characters.')
      if (getDb().projects.some((p) => p.owner === email && p.name.toLowerCase() === trimmed.toLowerCase()))
        return fail(409, `You already have a project called “${trimmed}”.`, 'duplicate_name')
      const at = new Date().toISOString()
      const row = { id: uid('pr'), name: trimmed, owner: email, created_at: at, updated_at: at, confirmed_at: null }
      getDb().projects.push(row)
      save()
      return HttpResponse.json(projectView(row), { status: 201 })
    }),
  ),
  http.get(
    u('/projects/:project_id'),
    authed(({ email, params }) => {
      const p = ownedProject(email, params.project_id)
      return p ? HttpResponse.json(projectView(p)) : notFound()
    }),
  ),

  http.post(
    u('/projects/:project_id/inputs'),
    authed(async ({ email, params, request }) => {
      const p = ownedProject(email, params.project_id)
      if (!p) return notFound()
      // X8: the server refuses to send anything to the AI provider without current consent.
      if (getDb().consent[email]?.version !== AI_SECTION_VERSION)
        return fail(403, 'Agree to AI processing before submitting requirements.', 'consent_required')
      const { text } = (await request.json()) as { text: string }
      if (!text?.trim()) return fail(422, 'Paste or type at least one requirement.')
      const job = createJob(p.id, 'extraction', { payload: text })
      touch(p.id, { clearConfirmation: true })
      save()
      return HttpResponse.json(publicJob(job), { status: 202 })
    }),
  ),

  http.get(
    u('/projects/:project_id/statements'),
    authed(({ email, params }) => {
      const p = ownedProject(email, params.project_id)
      return p ? HttpResponse.json(getDb().statements[p.id] ?? []) : notFound()
    }),
  ),
  http.get(
    u('/projects/:project_id/items'),
    authed(({ email, params, request }) => {
      const p = ownedProject(email, params.project_id)
      if (!p) return notFound()
      const url = new URL(request.url)
      const category = url.searchParams.get('category')
      const page = Math.max(1, Number(url.searchParams.get('page') ?? 1))
      const pageSize = Math.min(200, Number(url.searchParams.get('page_size') ?? 200))
      const all = getDb().items[p.id] ?? []
      const counts: Record<string, number> = {}
      all.forEach((i) => (counts[i.category] = (counts[i.category] ?? 0) + 1))
      const filtered = category ? all.filter((i) => i.category === category) : all
      return HttpResponse.json({
        items: filtered.slice((page - 1) * pageSize, page * pageSize),
        total: filtered.length,
        page,
        page_size: pageSize,
        counts,
      })
    }),
  ),
  http.patch(
    u('/projects/:project_id/items/:item_id'),
    authed(async ({ email, params, request }) => {
      const p = ownedProject(email, params.project_id)
      if (!p) return notFound()
      const item = (getDb().items[p.id] ?? []).find((i) => i.id === params.item_id)
      if (!item) return notFound()
      const body = (await request.json()) as { name?: string; description?: string | null }
      if (body.name !== undefined && !body.name.trim()) return fail(422, 'Name cannot be empty.')
      if (body.name !== undefined) item.name = body.name.trim()
      if (body.description !== undefined) item.description = body.description
      if (item.origin === 'system-extracted') item.origin = 'user-edited' // FR5b
      touch(p.id, { clearConfirmation: true }) // FR5e
      save()
      return HttpResponse.json(item)
    }),
  ),
  http.post(
    u('/projects/:project_id/confirmation'),
    authed(({ email, params }) => {
      const p = ownedProject(email, params.project_id)
      if (!p) return notFound()
      if (!(getDb().items[p.id]?.length)) return fail(409, 'There is nothing to confirm yet.')
      p.confirmed_at = new Date().toISOString()
      save()
      return HttpResponse.json(projectView(p), { status: 201 })
    }),
  ),

  http.post(
    u('/projects/:project_id/generations'),
    authed(async ({ email, params, request }) => {
      const p = ownedProject(email, params.project_id)
      if (!p) return notFound()
      // FR5e: enforced on the server, not only by the disabled button.
      if (!p.confirmed_at) return fail(409, 'Confirm the extracted items before generating.', 'not_confirmed')
      const { diagram_types } = (await request.json()) as { diagram_types: string[] }
      if (diagram_types.some((t) => t !== 'use_case'))
        return fail(422, 'Only the Use Case diagram is available in this version.')
      const job = createJob(p.id, 'generation', { diagram_types: ['use_case'] })
      return HttpResponse.json(publicJob(job), { status: 202 })
    }),
  ),
  http.get(
    u('/jobs/:job_id'),
    authed(({ email, params }) => {
      const job = getDb().jobs.find((j) => j.id === params.job_id)
      if (!job || !ownedProject(email, job.project_id)) return notFound()
      return HttpResponse.json(publicJob(advance(job)))
    }),
  ),

  http.get(
    u('/projects/:project_id/diagrams'),
    authed(({ email, params }) => {
      const p = ownedProject(email, params.project_id)
      if (!p) return notFound()
      return HttpResponse.json(
        getDb()
          .diagrams.filter((d) => d.project_id === p.id)
          .map(diagramView)
          .reverse(),
      )
    }),
  ),
  http.get(
    u('/diagrams/:diagram_id'),
    authed(({ email, params }) => {
      const d = getDb().diagrams.find((x) => x.id === params.diagram_id)
      if (!d || !ownedProject(email, d.project_id)) return notFound()
      return HttpResponse.json(diagramView(d))
    }),
  ),
  http.post(
    u('/diagrams/:diagram_id/revisions'),
    authed(async ({ email, params, request }) => {
      const d = getDb().diagrams.find((x) => x.id === params.diagram_id)
      if (!d || !ownedProject(email, d.project_id)) return notFound()
      const { instruction } = (await request.json()) as { instruction?: string }
      const text = (instruction ?? '').trim()
      if (!text) return fail(422, 'Describe the change you want.')
      if (text.length > 500) return fail(422, 'Keep the change under 500 characters.')
      if (!d.model) return fail(422, 'This diagram was made before editing was available. Generate it again, then edit.')
      await delay(import.meta.env.MODE === 'test' ? 0 : 900) // an LLM edit takes a moment
      const result = applyInstruction(d.model, text)
      if (!result.ok) return fail(422, result.detail)
      const row: DiagramRow = {
        ...d,
        id: uid('dg'),
        created_at: new Date().toISOString(),
        parent_id: d.id,
        instruction: text,
        model: result.model,
        svg: renderUseCase(result.model),
      }
      getDb().diagrams.push(row)
      touch(d.project_id)
      save()
      return HttpResponse.json(diagramView(row), { status: 201 })
    }),
  ),
  http.get(
    u('/diagrams/:diagram_id/layout'),
    authed(({ email, params }) => {
      const d = getDb().diagrams.find((x) => x.id === params.diagram_id)
      if (!d || !ownedProject(email, d.project_id)) return notFound()
      return HttpResponse.json(layoutView(d))
    }),
  ),
  http.post(
    u('/diagrams/:diagram_id/layout'),
    authed(async ({ email, params, request }) => {
      const d = getDb().diagrams.find((x) => x.id === params.diagram_id)
      if (!d || !ownedProject(email, d.project_id)) return notFound()
      const { positions } = (await request.json()) as { positions?: Record<string, { x?: unknown; y?: unknown }> }
      if (!positions || typeof positions !== 'object') return fail(422, 'Send the moved positions.')
      const known = new Set(layoutView(d).elements.map((e) => e.id))
      const unknown = Object.keys(positions).filter((id) => !known.has(id)).sort()
      if (unknown.length) return fail(422, `Not an element of this diagram: ${unknown.join(', ')}`)
      const moved = Object.entries(positions)
      if (!moved.every(([, p]) => Number.isFinite(p?.x) && Number.isFinite(p?.y))) return fail(422, 'Positions must be numbers.')
      const row: DiagramRow = {
        ...d,
        id: uid('dg'),
        created_at: new Date().toISOString(),
        parent_id: d.id,
        instruction: `Moved ${moved.length} element(s)`,
        layout: { ...d.layout, ...Object.fromEntries(moved.map(([id, p]) => [id, [p.x as number, p.y as number]])) },
      }
      getDb().diagrams.push(row)
      touch(d.project_id)
      save()
      return HttpResponse.json(diagramView(row), { status: 201 })
    }),
  ),
  http.get(
    u('/diagrams/:diagram_id/export'),
    authed(async ({ email, params }) => {
      const d = getDb().diagrams.find((x) => x.id === params.diagram_id)
      if (!d || !ownedProject(email, d.project_id)) return notFound()
      return new HttpResponse(await svgToPng(d.svg), { headers: { 'Content-Type': 'image/png' } })
    }),
  ),
]

/** Stand-in for the backend's PNG export (FR18a): 2x scale, longest side capped at 8,000 px. */
async function svgToPng(svg: string): Promise<Blob> {
  const img = new Image()
  const url = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml' }))
  await new Promise((res, rej) => {
    img.onload = res
    img.onerror = rej
    img.src = url
  })
  const scale = Math.min(2, 8000 / Math.max(img.width, img.height))
  const canvas = Object.assign(document.createElement('canvas'), {
    width: Math.round(img.width * scale),
    height: Math.round(img.height * scale),
  })
  canvas.getContext('2d')!.drawImage(img, 0, 0, canvas.width, canvas.height)
  URL.revokeObjectURL(url)
  return new Promise((res) => canvas.toBlob((b) => res(b!), 'image/png'))
}
