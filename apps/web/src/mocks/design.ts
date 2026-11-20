/**
 * MOCK ONLY. System design (Feature 4): the same routes, rules and messages as apps/api/routers/design.py, backed by
 * the in-browser mock database. Derived values use small copies of services/ai-extraction/app/design/goals.py and
 * decomposition.py.
 */
import { http, HttpResponse, type HttpResponseResolver } from 'msw'
import type { DesignSection, Job } from '@/api/client'
import { GOAL_NAMES } from '@/features/design/goals'
import { AI_SECTION_VERSION } from '@/features/privacy/policy'
import { advance, createJob, getDb, publicJob, registerJobKind, save, uid, type JobRow } from './db'
import { esc } from './render'

type Helpers = {
  u: (path: string) => string
  authed: (fn: (ctx: { email: string; params: Record<string, string | readonly string[] | undefined>; request: Request }) => Response | Promise<Response>) => HttpResponseResolver
  ownedProject: (email: string, id: unknown) => { id: string; owner: string; confirmed_at: string | null } | undefined
  fail: (status: number, detail: string, code?: string) => Response
  notFound: () => Response
}

type Content = Record<string, unknown>
/** `cited` keeps the cited statements' texts at write time; the API keeps an HMAC of them instead. */
type Row = { status: 'draft' | 'confirmed'; version: number; content: Content; derived: Content; cited: Record<string, string>; updated_at: string }
type Goal = { name: string; reason: string; statement_ids: string[] }

/* ---------- 4.1 design goals ---------- */

const GROUPS: Record<string, string[]> = {
  client: ['Low cost', 'Increased productivity', 'Backward compatibility', 'Rapid development', 'Flexibility', 'Efficiency', 'Portability', 'Good documentation', 'Reliability'],
  end_user: ['Functionality', 'User-friendliness', 'Ease of use', 'Ease of learning', 'Fault tolerance', 'Robustness', 'Efficiency', 'Reliability'],
  developer: ['Minimum number of errors', 'Modifiability', 'Readability', 'Reusability', 'Adaptability', 'Well-defined interfaces', 'Traceability of requirements', 'Portability', 'Good documentation', 'Reliability'],
}
const TRADE_OFFS: [string, string[], string[]][] = [
  ['Functionality vs. Usability', ['Functionality'], ['User-friendliness', 'Ease of use', 'Ease of learning', 'Ease of remembering']],
  ['Cost vs. Robustness', ['Low cost', 'Cost-effectiveness'], ['Robustness']],
  ['Efficiency vs. Portability (or Modifiability)', ['Efficiency', 'High performance'], ['Portability', 'Modifiability']],
  ['Rapid development vs. Functionality', ['Rapid development'], ['Functionality']],
  ['Cost vs. Reusability', ['Low cost', 'Cost-effectiveness'], ['Reusability', 'Reuse of components']],
  ['Backward compatibility vs. Readability', ['Backward compatibility'], ['Readability']],
]

function deriveGoals(content: Content) {
  const names = (content.goals as Goal[]).map((g) => g.name)
  const groups: Record<string, string[]> = Object.fromEntries(Object.entries(GROUPS).map(([k, members]) => [k, names.filter((n) => members.includes(n))]))
  groups.other = names.filter((n) => !Object.values(GROUPS).some((m) => m.includes(n)))
  const conflicts = TRADE_OFFS.flatMap(([pair, left, right]) =>
    left.filter((a) => names.includes(a)).flatMap((a) => right.filter((b) => names.includes(b)).map((b) => ({ a, b, pair }))),
  )
  return { groups, conflicts }
}

/** Mirrors the API's _clean_goals: the stored content, or the refusal message. */
function cleanGoals(content: Content, known: Set<string>): Content | string {
  const goals = content.goals
  const form = 'The design goals are not in the expected form.'
  if (!Array.isArray(goals) || !goals.every((g) => g && typeof g === 'object')) return form
  if (goals.length < 1 || goals.length > GOAL_NAMES.length) return `Choose 1 to ${GOAL_NAMES.length} design goals.`
  const out: Goal[] = []
  for (const { name, reason = '', statement_ids = [] } of goals as Partial<Goal>[]) {
    if (typeof reason !== 'string' || !Array.isArray(statement_ids) || !statement_ids.every((s) => typeof s === 'string')) return form
    if (!GOAL_NAMES.includes(name!)) return `Unknown design goal: ${name}.`
    if (out.some((o) => o.name === name)) return `Each design goal can be chosen only once: ${name}.`
    if (reason.trim().length > 300) return 'A reason can be at most 300 characters.'
    if (!statement_ids.every((s) => known.has(s))) return 'A design goal can only cite requirements of this project.'
    out.push({ name: name!, reason: reason.trim(), statement_ids: [...new Set(statement_ids)] })
  }
  return { goals: out }
}

function uncitedGoals(content: Content) {
  const missing = (content.goals as Goal[]).filter((g) => !g.statement_ids.length).map((g) => g.name)
  return missing.length ? `Every design goal must cite at least one requirement: ${missing.join(', ')}.` : null
}

/** The mock "AI": a fixed, plausible ranking citing the project's first requirements. */
function draftGoals(ids: string[]): Content {
  const at = (i: number) => [ids[Math.min(i, ids.length - 1)]]
  return {
    goals: [
      { name: 'Reliability', reason: 'Users depend on every request being recorded correctly.', statement_ids: at(0) },
      { name: 'Ease of use', reason: 'Staff use the system daily with little training.', statement_ids: at(0) },
      { name: 'Efficiency', reason: 'Responses must come back quickly.', statement_ids: at(1) },
      { name: 'Maintainability', reason: 'Requirements are expected to change after release.', statement_ids: at(2) },
      { name: 'Portability', reason: 'It should run on the browsers and devices people already have.', statement_ids: at(0) },
    ],
  }
}

/* ---------- 4.2 subsystem decomposition ---------- */

type Service = { name: string; operations: string[] }
type Subsystem = { id: string; name: string; description: string; layer: number; services: Service[]; classes: string[]; depends_on: string[]; statement_ids: string[] }
type Warning = { code: string; message: string; subsystem_ids: string[] }

const strings = (v: unknown): v is string[] => Array.isArray(v) && v.every((x) => typeof x === 'string')
const text = (v: unknown, high: number, low = 1) => (typeof v === 'string' && v.trim().length >= low && v.trim().length <= high ? v.trim() : null)

/** Mirrors the API's _clean_decomposition. */
function cleanDecomposition(content: Content, known: Set<string>): Content | string {
  const subsystems = content.subsystems
  const form = 'The subsystem decomposition is not in the expected form.'
  if (!['closed', 'open'].includes(content.architecture as string) || !Array.isArray(subsystems) || !subsystems.every((s) => s && typeof s === 'object'))
    return form
  if (subsystems.length < 1 || subsystems.length > 20) return 'Define 1 to 20 subsystems.'
  const out: Subsystem[] = []
  const owner: Record<string, string> = {}
  for (const s of subsystems as Partial<Subsystem>[]) {
    const { id, layer, services = [], classes = [], depends_on = [], statement_ids = [] } = s
    if (!strings(classes) || !strings(depends_on) || !strings(statement_ids) || !Array.isArray(services) || !services.every((v) => v && typeof v === 'object' && strings(v.operations ?? [])))
      return form
    if (typeof id !== 'string' || !/^[a-z0-9][a-z0-9-]{0,39}$/.test(id))
      return 'A subsystem id must be a short slug: lowercase letters, digits and hyphens, at most 40 characters.'
    if (!Number.isInteger(layer) || layer! < 1) return "A subsystem's layer must be a whole number, 1 for the top layer."
    const name = text(s.name, 80)
    if (name === null) return 'A subsystem name must be 1 to 80 characters.'
    const description = text(s.description ?? '', 500, 0)
    if (description === null) return 'A description can be at most 500 characters.'
    const cleanServices: Service[] = []
    for (const v of services) {
      const ops = (v.operations ?? []).map((o) => text(o, 120))
      const serviceName = text(v.name, 120)
      if (serviceName === null || ops.includes(null)) return 'Service and operation names must be 1 to 120 characters.'
      cleanServices.push({ name: serviceName, operations: ops as string[] })
    }
    if (out.some((o) => o.id === id)) return `Each subsystem id can be used only once: ${id}.`
    if (out.some((o) => o.name === name)) return `Each subsystem name can be used only once: ${name}.`
    if (!statement_ids.every((x) => known.has(x))) return 'A subsystem can only cite requirements of this project.'
    const cleanClasses = classes.map((c) => text(c, 120))
    if (cleanClasses.includes(null)) return 'A class name must be 1 to 120 characters.'
    for (const c of new Set(cleanClasses as string[])) {
      if ((owner[c] ??= id) !== id) return `A class can belong to only one subsystem: ${c}.`
    }
    out.push({ id, name, description, layer: layer!, services: cleanServices, classes: [...new Set(cleanClasses as string[])], depends_on: [...new Set(depends_on)], statement_ids: [...new Set(statement_ids)] })
  }
  const ids = new Set(out.map((o) => o.id))
  for (const o of out)
    for (const target of o.depends_on) {
      if (target === o.id) return `A subsystem cannot depend on itself: ${target}.`
      if (!ids.has(target)) return `Unknown subsystem in depends_on: ${target}.`
    }
  return { architecture: content.architecture, subsystems: out }
}

function uncitedSubsystems(content: Content) {
  const missing = (content.subsystems as Subsystem[]).filter((s) => !s.statement_ids.length).map((s) => s.name)
  return missing.length ? `Every subsystem must cite at least one requirement: ${missing.join(', ')}.` : null
}

/** The API's design_model, from the mock db: entity names and the relations between two of them. */
function modelOf(pid: string) {
  const items = getDb().items[pid] ?? []
  const classes = new Map(items.filter((i) => i.category === 'entity').map((i) => [i.id, i.name]))
  const relations = items
    .filter((i) => i.category === 'relationship' && classes.has(i.source_item_id ?? '') && classes.has(i.target_item_id ?? ''))
    .map((i) => ({ source: classes.get(i.source_item_id!)!, target: classes.get(i.target_item_id!)! }))
  return { classes: [...new Set(classes.values())], relations }
}

const score = (internal: number, crossing: number) => (internal + crossing ? Math.round((internal / (internal + crossing)) * 100) / 100 : null)

/** Mirrors derive_decomposition: layers, cohesion and coupling over the model, warnings and the PlantUML source. */
function deriveDecomposition(content: Content, pid: string) {
  const subsystems = content.subsystems as Subsystem[]
  const model = modelOf(pid)
  const layer = Object.fromEntries(subsystems.map((s) => [s.id, s.layer]))
  const name = (id: string) => subsystems.find((s) => s.id === id)!.name
  const owner: Record<string, string> = {}
  subsystems.forEach((s) => s.classes.forEach((c) => (owner[c] ??= s.id)))
  const edges = subsystems.flatMap((s) => s.depends_on.filter((t) => t in layer && t !== s.id).map((t) => [s.id, t] as const))
  const internal: Record<string, number> = Object.fromEntries(subsystems.map((s) => [s.id, 0]))
  const crossing = { ...internal }
  const linked: Record<string, Set<string>> = Object.fromEntries(subsystems.map((s) => [s.id, new Set()]))
  const link = (a: string, b: string) => {
    linked[a].add(b)
    linked[b].add(a)
  }
  edges.forEach(([a, b]) => link(a, b))
  for (const r of model.relations) {
    const [a, b] = [owner[r.source], owner[r.target]]
    if (!a || !b) continue
    if (a === b) internal[a]++
    else {
      crossing[a]++
      crossing[b]++
      link(a, b)
    }
  }
  const layers = [...new Set(Object.values(layer))].sort((a, b) => a - b)
  const warnings: Warning[] = []
  if (subsystems.length > 9) warnings.push({ code: 'too_many_subsystems', subsystem_ids: [], message: `${subsystems.length} subsystems: keep to about 7 plus or minus 2.` })
  if (layers.length > 6) warnings.push({ code: 'too_many_layers', subsystem_ids: [], message: `${layers.length} layers: keep to about 4 plus or minus 2 (3 is a good default).` })
  for (const [a, b] of edges)
    if (layer[b] < layer[a])
      warnings.push({ code: 'upward_dependency', subsystem_ids: [a, b], message: `${name(a)} (layer ${layer[a]}) depends on ${name(b)} in the higher layer ${layer[b]}; a layer should know nothing of the layers above it.` })
  for (const [a, b] of edges)
    if (content.architecture === 'closed' && layer[b] > layer[a] + 1)
      warnings.push({ code: 'skipped_layer', subsystem_ids: [a, b], message: `${name(a)} (layer ${layer[a]}) calls ${name(b)} in layer ${layer[b]}; in a closed architecture a layer calls only the layer directly below.` })
  for (const c of model.classes) if (!(c in owner)) warnings.push({ code: 'unassigned_class', subsystem_ids: [], message: `The class ${c} belongs to no subsystem.` })
  for (const s of subsystems)
    if (!s.classes.length && !s.services.length) warnings.push({ code: 'empty_subsystem', subsystem_ids: [s.id], message: `${s.name} has no classes and no services.` })
  const sum = (o: Record<string, number>) => Object.values(o).reduce((a, b) => a + b, 0)
  return {
    layers: layers.map((n) => ({ layer: n, subsystem_ids: subsystems.filter((s) => s.layer === n).map((s) => s.id) })),
    subsystems: subsystems.map((s) => ({ id: s.id, cohesion: score(internal[s.id], crossing[s.id]), coupling: linked[s.id].size })),
    cohesion: score(sum(internal), sum(crossing) / 2),
    warnings,
    // shortcut: plain aliases, not the AI service's escaping; the mock never renders this source, only stores it.
    package_diagram: [
      '@startuml',
      ...layers.flatMap((n) => [`package "Layer ${n}" {`, ...subsystems.filter((s) => s.layer === n).map((s) => `  package "${s.name}" as ${s.id.replace(/-/g, '_')} {\n  }`), '}']),
      ...edges.map(([a, b]) => (layer[b] < layer[a] ? `${b.replace(/-/g, '_')} <.. ${a.replace(/-/g, '_')} #red;text:red : upward` : `${a.replace(/-/g, '_')} ..> ${b.replace(/-/g, '_')}`)),
      '@enduml',
    ].join('\n'),
  }
}

/** The mock "AI": three layers (closed), the project's entities split between the logic and storage layers. */
function draftDecomposition(ids: string[], pid: string): Content {
  const at = (i: number) => [ids[Math.min(i, ids.length - 1)]]
  const items = getDb().items[pid] ?? []
  const classes = modelOf(pid).classes
  const half = Math.ceil(classes.length / 2)
  const cases = items.filter((i) => i.category === 'process').map((i) => i.name)
  const s = (id: string, name: string, description: string, layer: number, services: Service[], cls: string[], depends_on: string[], statement_ids: string[]) =>
    ({ id, name, description, layer, services, classes: cls, depends_on, statement_ids })
  return {
    architecture: 'closed',
    subsystems: [
      s('user-interface', 'User interface', 'Screens and forms the users work with.', 1, [{ name: 'Screens', operations: ['Show screen', 'Submit form'] }], [], ['application'], at(0)),
      s('application', 'Application logic', 'The rules behind each use case.', 2, [{ name: 'Lending', operations: cases.length ? cases.slice(0, 4) : ['Handle request'] }], classes.slice(0, half), ['storage'], at(0)),
      s('storage', 'Data storage', 'Keeps the records.', 3, [{ name: 'Persistence', operations: ['Save record', 'Load record'] }], classes.slice(half), [], at(1)),
    ],
  }
}

/** Stand-in for Kroki drawing the package diagram: one box per layer, top first, its subsystems side by side. */
function renderPackage(subsystems: Subsystem[]) {
  const layers = [...new Set(subsystems.map((s) => s.layer))].sort((a, b) => a - b)
  const width = 40 + Math.max(...layers.map((n) => subsystems.filter((s) => s.layer === n).length)) * 200
  const rows = layers.map((n, i) => {
    const y = 20 + i * 120
    const boxes = subsystems
      .filter((s) => s.layer === n)
      .map((s, j) => `<rect x="${30 + j * 200}" y="${y + 30}" width="180" height="60" fill="#f4f8f7" stroke="#2f6f68"/><text x="${120 + j * 200}" y="${y + 65}" text-anchor="middle" font-size="13">${esc(s.name)}</text>`)
    return `<rect x="10" y="${y}" width="${width - 20}" height="105" fill="none" stroke="#999"/><text x="20" y="${y + 18}" font-size="12">Layer ${n}</text>${boxes.join('')}`
  })
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${30 + layers.length * 120}" font-family="sans-serif">${rows.join('')}</svg>`
}

/** Mirrors _store_package_diagram: confirming stores the package diagram with the project's diagrams, a new version each time. */
function storePackageDiagram(pid: string, section: DesignSection) {
  const db = getDb()
  const subsystems = (section.content as { subsystems: Subsystem[] }).subsystems
  db.diagrams.push({
    id: uid('dg'), project_id: pid, type: 'package', title: `${db.projects.find((p) => p.id === pid)!.name} · Package`,
    created_at: new Date().toISOString(), parent_id: null, instruction: null, svg: renderPackage(subsystems),
    source: (section.derived as { package_diagram: string }).package_diagram, statement_ids: [...new Set(citedIn(subsystems))],
  })
}

/* ---------- section kinds, in order ---------- */

type Kind = {
  title: string
  clean: (c: Content, known: Set<string>) => Content | string
  confirmError: (c: Content) => string | null
  derive: (c: Content, pid: string) => Content
  draft: (ids: string[], pid: string) => Content
  onConfirm?: (pid: string, section: DesignSection) => void
}
const KINDS: Record<string, Kind> = {
  goals: { title: 'Design goals', clean: cleanGoals, confirmError: uncitedGoals, derive: deriveGoals, draft: draftGoals },
  decomposition: { title: 'Subsystem decomposition', clean: cleanDecomposition, confirmError: uncitedSubsystems, derive: deriveDecomposition, draft: draftDecomposition, onConfirm: storePackageDiagram },
}
const RUNNING = ['queued', 'running', 'waiting']

const rowsOf = (pid: string) => ((getDb().design ??= {})[pid] ??= {}) as Record<string, Row>
const textsOf = (pid: string) => Object.fromEntries((getDb().statements[pid] ?? []).map((s) => [s.id, s.text]))
const citedIn = (value: unknown): string[] =>
  Array.isArray(value) ? value.flatMap(citedIn)
  : value && typeof value === 'object' ? Object.entries(value).flatMap(([k, v]) => (k === 'statement_ids' ? (v as string[]) : citedIn(v)))
  : []
const latestJob = (pid: string, kind: string) => getDb().jobs.filter((j) => j.project_id === pid && j.kind === `design_${kind}`).at(-1)

function views(pid: string): DesignSection[] {
  const rows = rowsOf(pid)
  const texts = textsOf(pid)
  const out: DesignSection[] = []
  for (const [kind, k] of Object.entries(KINDS)) {
    const r = rows[kind]
    const job = latestJob(pid, kind)
    out.push({
      kind: kind as DesignSection['kind'], title: k.title, status: r?.status ?? 'empty', version: r?.version ?? 0,
      content: r?.content ?? null, derived: r?.derived ?? null,
      stale: !!r && Object.entries(r.cited).some(([id, text]) => texts[id] !== text),
      locked: out.length > 0 && out.at(-1)!.status !== 'confirmed',
      job: job ? publicJob(advance(job)) : null,
      updated_at: r?.updated_at ?? null,
    })
  }
  return out
}

/** Checks, derives and stores the content as a draft, one version up; the refusal message otherwise. */
function store(pid: string, kind: string, content: Content): string | null {
  const texts = textsOf(pid)
  const clean = KINDS[kind].clean(content ?? {}, new Set(Object.keys(texts)))
  if (typeof clean === 'string') return clean
  const rows = rowsOf(pid)
  rows[kind] = {
    status: 'draft', version: (rows[kind]?.version ?? 0) + 1, content: clean, derived: KINDS[kind].derive(clean, pid),
    cited: Object.fromEntries(citedIn(clean).map((id) => [id, texts[id]])), updated_at: new Date().toISOString(),
  }
  save()
  return null
}

function applyDraft(job: JobRow) {
  const kind = job.kind.replace(/^design_/, '')
  const ids = (getDb().statements[job.project_id] ?? []).map((s) => s.id)
  const refusal = ids.length ? store(job.project_id, kind, KINDS[kind].draft(ids, job.project_id)) : 'no requirement to draft from.'
  if (refusal) Object.assign(job, { status: 'failed', error: `Drafting failed: ${refusal}` })
  else job.progress.label = 'Draft ready'
}

const test = import.meta.env.MODE === 'test'
for (const [kind, k] of Object.entries(KINDS))
  registerJobKind(`design_${kind}`, {
    steps: [`Drafting the ${k.title.toLowerCase()}`, `Checking the ${k.title.toLowerCase()}`],
    queueMs: test ? 0 : 1000,
    stepMs: test ? 40 : 1400,
    apply: applyDraft,
  })

export function designHandlers({ u, authed, ownedProject, fail, notFound }: Helpers) {
  /** The section's view, or the refusal: 404 for an unknown kind, 409 while the section before it is not confirmed. */
  function section(pid: string, kind: string): DesignSection | Response {
    if (!(kind in KINDS)) return notFound()
    const all = views(pid)
    const n = Object.keys(KINDS).indexOf(kind)
    return all[n].locked ? fail(409, `Confirm ${all[n - 1].title} first.`) : all[n]
  }
  return [
    http.get(
      u('/projects/:project_id/design'),
      authed(({ email, params }) => {
        const p = ownedProject(email, params.project_id)
        return p ? HttpResponse.json({ sections: views(p.id) }) : notFound()
      }),
    ),
    http.post(
      u('/projects/:project_id/design/:kind/draft-jobs'),
      authed(({ email, params }) => {
        const p = ownedProject(email, params.project_id)
        const kind = String(params.kind)
        if (!p || !(kind in KINDS)) return notFound()
        if (getDb().consent[email]?.version !== AI_SECTION_VERSION)
          return fail(403, 'Agree to AI processing before drafting with AI.', 'consent_required')
        if (!p.confirmed_at) return fail(409, 'Confirm the requirements first.')
        const s = section(p.id, kind)
        if (s instanceof Response) return s
        if (s.job && RUNNING.includes(s.job.status)) return fail(409, 'A draft of this section is already running.')
        const job = createJob(p.id, `design_${kind}` as Job['kind'], { progress: { step: 0, total: 2, label: 'Queued' } })
        return HttpResponse.json(publicJob(job), { status: 202 })
      }),
    ),
    http.put(
      u('/projects/:project_id/design/:kind'),
      authed(async ({ email, params, request }) => {
        const p = ownedProject(email, params.project_id)
        if (!p) return notFound()
        const s = section(p.id, String(params.kind))
        if (s instanceof Response) return s
        const refusal = store(p.id, s.kind, ((await request.json()) as { content: Content }).content)
        return refusal ? fail(422, refusal) : HttpResponse.json(section(p.id, s.kind))
      }),
    ),
    http.post(
      u('/projects/:project_id/design/:kind/confirm'),
      authed(({ email, params }) => {
        const p = ownedProject(email, params.project_id)
        if (!p) return notFound()
        const s = section(p.id, String(params.kind))
        if (s instanceof Response) return s
        if (s.status === 'empty') return fail(422, `Write or draft the ${s.title.toLowerCase()} first.`)
        if (s.stale) return fail(422, 'A requirement this section cites has changed. Review the section and save it again.')
        const refusal = KINDS[s.kind].confirmError(s.content!)
        if (refusal) return fail(422, refusal)
        if (s.status !== 'confirmed') KINDS[s.kind].onConfirm?.(p.id, s) // confirming again without a change adds nothing
        rowsOf(p.id)[s.kind].status = 'confirmed'
        save()
        return HttpResponse.json(section(p.id, s.kind))
      }),
    ),
  ]
}
