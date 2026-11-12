/** MOCK ONLY. MSW handlers for the FE draft contract (src/api/openapi.draft.yaml). Delete once H3 is live. */
import { delay, http, HttpResponse, type HttpResponseResolver } from 'msw'
import { SAMPLE_REQUIREMENTS, SAMPLE_USER_STORIES, TEST_SRS_PDF_TEXT } from '@/features/input/sample'
import { AI_SECTION_VERSION } from '@/features/privacy/policy'
import { slugify } from '@/features/viewer/export-formats'
import { jpegToPdf } from '@/features/viewer/pdf'
import { env } from '@/lib/env'
import { advance, createJob, diagramView, getDb, projectView, publicJob, save, touch, uid, type DiagramRow } from './db'
import { applyInstruction } from './edit'
import { layoutView } from './layout'
import { renderUseCase } from './render'
import { useCaseSource } from './source'
import { makeZip } from './zip'

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
      const pages = Math.ceil(text.length / 3000)
      if (text.length > 300000)
        return fail(413, `Input is ${text.length.toLocaleString()} characters (${pages} pages); the maximum allowed is 100 pages (300,000 characters).`)
      const currentDocPages = (getDb().documents?.[p.id] ?? []).reduce((s, d) => s + d.page_count, 0)
      if (currentDocPages + pages > 100)
        return fail(413, `This input counts as ${pages} pages, which exceeds the remaining project capacity (${100 - currentDocPages} pages available out of 100).`)
      const job = createJob(p.id, 'extraction', { payload: text })
      touch(p.id, { clearConfirmation: true })
      save()
      return HttpResponse.json(publicJob(job), { status: 202 })
    }),
  ),

  http.get(
    u('/projects/:project_id/documents'),
    authed(({ email, params }) => {
      const p = ownedProject(email, params.project_id)
      if (!p) return notFound()
      const docs = getDb().documents?.[p.id] ?? []
      for (const d of docs) {
        if (d.status === 'processing' || d.status === 'uploaded') {
          const job = getDb().jobs.find((j) => j.id === d.job_id)
          if (job) advance(job, { fast: true })
        }
      }
      return HttpResponse.json(getDb().documents?.[p.id] ?? [])
    }),
  ),

  http.post(
    u('/projects/:project_id/documents'),
    authed(async ({ email, params, request }) => {
      const p = ownedProject(email, params.project_id)
      if (!p) return notFound()
      if (getDb().consent[email]?.version !== AI_SECTION_VERSION)
        return fail(403, 'Agree to AI processing before submitting requirements.', 'consent_required')

      const headerName = request.headers.get('x-filename')
      const headerSize = Number(request.headers.get('x-filesize') ?? '1000')

      let name = headerName ? decodeURIComponent(headerName) : 'document'
      let size = headerSize
      let file: File | null = null
      let extractedPayload = ''

      try {
        const formData = await Promise.race([
          request.formData(),
          new Promise<null>((r) => setTimeout(() => r(null), 100)),
        ])
        if (formData) {
          file = (formData.get('file') as File) || null
          if (file) {
            name = (formData.get('filename') as string) || file.name || name
            size = file.size || size
            const text = await Promise.race([
              file.text(),
              new Promise<string>((r) => setTimeout(() => r(''), 100)),
            ])
            if (text && (text.includes('FR') || text.includes('shall') || text.includes('want'))) {
              extractedPayload = text
            }
          }
        }
      } catch {}

      if (!extractedPayload) {
        if (name.toLowerCase().includes('empty')) {
          extractedPayload = ''
        } else if (name.toLowerCase().includes('srs') || name.toLowerCase().includes('test')) {
          extractedPayload = TEST_SRS_PDF_TEXT
        } else {
          extractedPayload = `${SAMPLE_REQUIREMENTS}\n\n${SAMPLE_USER_STORIES}`
        }
      }

      const ext = name.slice(name.lastIndexOf('.')).toLowerCase()
      if (ext !== '.pdf' && ext !== '.docx')
        return fail(415, 'Unsupported file type. Supported file types are PDF (.pdf) and DOCX (.docx).')

      const MAX_BYTES = 10 * 1024 * 1024
      if (size > MAX_BYTES)
        return fail(
          413,
          `File size is ${(size / (1024 * 1024)).toFixed(2)} MB (${size.toLocaleString()} bytes); the maximum allowed size is 10 MB (10 × 1,048,576 bytes).`,
        )

      const existingDocs = getDb().documents?.[p.id] ?? []
      if (existingDocs.length >= 15)
        return fail(400, 'A project can contain at most 15 documents.')

      let pageCount = Math.max(1, Math.min(100, Math.ceil(size / 3000)))
      if (ext === '.pdf' && file) {
        try {
          const buffer = await file.arrayBuffer()
          const binStr = new TextDecoder('latin1').decode(buffer)
          const matches = binStr.match(/\/Type\s*\/Page\b/g)
          if (matches && matches.length > 0) {
            pageCount = Math.min(100, matches.length)
          } else if (name.toLowerCase().includes('srs') || name.toLowerCase().includes('test')) {
            pageCount = 2
          }
        } catch {
          if (name.toLowerCase().includes('srs') || name.toLowerCase().includes('test')) {
            pageCount = 2
          }
        }
      } else if (name.toLowerCase().includes('srs') || name.toLowerCase().includes('test')) {
        pageCount = ext === '.docx' ? 1 : 2
      }
      const totalPages = existingDocs.reduce((sum, d) => sum + d.page_count, 0)
      if (totalPages + pageCount > 100)
        return fail(
          413,
          `This document has ${pageCount} pages, which exceeds the remaining project limit of ${100 - totalPages} pages (100 pages maximum).`,
        )

      const docId = uid('doc')
      const job = createJob(p.id, 'extraction', { payload: extractedPayload })
      const doc = {
        id: docId,
        project_id: p.id,
        filename: name,
        storage_path: `${p.id}/${docId}/${name}`,
        content_type:
          file?.type ||
          (ext === '.pdf'
            ? 'application/pdf'
            : 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
        size_bytes: size,
        page_count: pageCount,
        status: 'processing' as const,
        warning: null,
        skipped_pages: [],
        job_id: job.id,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      }

      getDb().documents = getDb().documents ?? {}
      getDb().documents[p.id] = [doc, ...existingDocs]

      touch(p.id, { clearConfirmation: true })
      save()
      return HttpResponse.json({ document: doc, job: publicJob(job) }, { status: 202 })
    }),
  ),

  http.delete(
    u('/projects/:project_id/documents/:document_id'),
    authed(({ email, params }) => {
      const p = ownedProject(email, params.project_id)
      if (!p) return notFound()
      const docId = String(params.document_id)
      const docs = getDb().documents?.[p.id] ?? []
      const doc = docs.find((d) => d.id === docId)
      if (!doc) return fail(404, 'Document not found.')
      getDb().documents[p.id] = docs.filter((d) => d.id !== docId)
      touch(p.id, { clearConfirmation: true })
      save()
      return HttpResponse.json({ deleted: true, id: docId })
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
    authed(async ({ email, params, request }) => {
      const d = getDb().diagrams.find((x) => x.id === params.diagram_id)
      if (!d || !ownedProject(email, d.project_id)) return notFound()
      const format = new URL(request.url).searchParams.get('format')?.toLowerCase()
      if (format === 'svg') return new HttpResponse(d.svg, { headers: { 'Content-Type': 'image/svg+xml' } })
      if (format === 'pdf') return new HttpResponse(await svgToPdf(d.svg), { headers: { 'Content-Type': 'application/pdf' } })
      if (format === 'png') return new HttpResponse(await svgToPng(d.svg), { headers: { 'Content-Type': 'image/png' } })
      if (format === 'source') {
        if (!d.model) return fail(409, 'This diagram has no stored diagram source. Regenerate the diagram before exporting SOURCE.')
        return new HttpResponse(useCaseSource(d.model), { headers: { 'Content-Type': 'text/x-plantuml; charset=utf-8' } })
      }
      return fail(422, 'Unsupported export format. Choose one of: PNG, SVG, PDF, SOURCE.')
    }),
  ),
  http.get(
    u('/projects/:project_id/diagrams/export'),
    authed(({ email, params, request }) => {
      const p = ownedProject(email, params.project_id)
      if (!p) return notFound()
      const rows = getDb().diagrams.filter((d) => d.project_id === p.id)
      if (!rows.length) return fail(404, 'This project has no diagrams yet. Generate one first.')
      const versions = new URL(request.url).searchParams.get('versions') ?? 'all'
      if (versions !== 'all' && versions !== 'latest') return fail(422, "versions must be 'all' or 'latest'.")
      const names = versions === 'latest' ? latestOnly(zipLayout(rows)) : zipLayout(rows)
      const files: { name: string; data: string }[] = []
      const index = [`${p.name} - diagrams exported from SDDG (mock mode: SVG and source only; the real API adds PNG and PDF)`, '']
      for (const d of rows.filter((r) => r.id in names).sort((a, b) => names[a.id].localeCompare(names[b.id]))) {
        index.push(`${names[d.id]}  ${d.title}${d.instruction ? `  (edit: ${d.instruction})` : ''}`)
        files.push({ name: zipPath(names[d.id], 'svg'), data: d.svg })
        if (d.model) files.push({ name: zipPath(names[d.id], 'puml'), data: useCaseSource(d.model) })
      }
      const readme = versions === 'all' ? [{ name: 'README.txt', data: index.join('\n') + '\n' }] : []
      return new HttpResponse(makeZip([...readme, ...files]), {
        headers: { 'Content-Type': 'application/zip' },
      })
    }),
  ),
]

/** Same naming as the API's zip_layout: '<title>/v<n>'. Every diagram with the same title (regenerations and edits)
 *  is a version of one diagram, numbered by creation time. */
function zipLayout(rows: DiagramRow[]) {
  const groups = new Map<string, DiagramRow[]>()
  for (const r of rows) groups.set(slugify(r.title), [...(groups.get(slugify(r.title)) ?? []), r])
  const names: Record<string, string> = {}
  for (const [folder, versions] of groups) {
    versions.sort((a, b) => a.created_at.localeCompare(b.created_at)).forEach((r, i) => (names[r.id] = `${folder}/v${i + 1}`))
  }
  return names
}

/** Same as the API's zip_path: 'title/v2' -> 'title/v2/title-v2.svg'; 'title' (latest only) -> 'title.svg'. */
function zipPath(name: string, extension: string) {
  return name.includes('/') ? `${name}/${name.replace('/', '-')}.${extension}` : `${name}.${extension}`
}

/** Same as the API's latest_only: the newest version of each diagram, without the version folder. */
function latestOnly(names: Record<string, string>) {
  const newest = new Map<string, [string, number]>()
  for (const [id, name] of Object.entries(names)) {
    const [folder, version] = name.split('/v')
    if (!newest.has(folder) || Number(version) > newest.get(folder)![1]) newest.set(folder, [id, Number(version)])
  }
  return Object.fromEntries([...newest].map(([folder, [id]]) => [id, folder]))
}

/** Draws the SVG on a canvas at `scale` (capped so the longest side stays within 8,000 px, as in FR18a). */
async function rasterise(svg: string, scale: number) {
  const img = new Image()
  const url = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml' }))
  await new Promise((res, rej) => {
    img.onload = res
    img.onerror = rej
    img.src = url
  })
  const s = Math.min(scale, 8000 / Math.max(img.width, img.height))
  const canvas = Object.assign(document.createElement('canvas'), {
    width: Math.round(img.width * s),
    height: Math.round(img.height * s),
  })
  const ctx = canvas.getContext('2d')!
  ctx.fillStyle = '#ffffff' // JPEG has no transparency
  ctx.fillRect(0, 0, canvas.width, canvas.height)
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
  URL.revokeObjectURL(url)
  return { canvas, width: img.width, height: img.height }
}

/** Stand-in for the backend's PNG export (FR18a): 2x scale, longest side capped at 8,000 px. */
async function svgToPng(svg: string): Promise<Blob> {
  const { canvas } = await rasterise(svg, 2)
  return new Promise((res) => canvas.toBlob((b) => res(b!), 'image/png'))
}

/** Stand-in for Kroki's PDF output: a one-page PDF the size of the diagram, holding a 2x JPEG of it. */
async function svgToPdf(svg: string): Promise<Blob> {
  const { canvas, width, height } = await rasterise(svg, 2)
  const jpeg = await new Promise<Blob>((res) => canvas.toBlob((b) => res(b!), 'image/jpeg', 0.95))
  const bytes = new Uint8Array(await jpeg.arrayBuffer())
  // The image is drawn at the diagram's own size; its pixel size is the 2x canvas.
  return jpegToPdf(bytes, canvas.width, canvas.height, width, height)
}
