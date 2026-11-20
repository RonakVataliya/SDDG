/** MOCK ONLY. In-browser stand-in for the backend's Postgres, persisted to localStorage between reloads. */
import type { Diagram, ExtractedItem, Job, ProjectDocument, RequirementStatement, Story } from '@/api/client'
import { DEFAULT_STYLE, type DiagramStyle } from '@/features/viewer/style'
import type { components } from '@/api/schema'
import { extractItems, splitStatements } from './extract'
import { detectFlags, type FlagRow } from './flags'
import { buildUseCaseModel, renderPlaceholder, renderUseCase, type UseCaseModel } from './render'
import { emptyCollab, type CollabState } from './collab'

type ProjectRow = {
  id: string
  name: string
  owner: string
  created_at: string
  updated_at: string
  confirmed_at: string | null
  /** Extraction nodes already run on the confirmed requirements (requirements-first workflow). */
  extracted_nodes?: string[]
  // Project settings (Feature 3.1); optional so projects stored before it still load.
  client_name?: string | null
  contact_email?: string | null
  archived_at?: string | null
  archived_by?: string | null
}
export type JobRow = Job & { project_id: string; payload?: string; applied?: boolean }
/** The server keeps the model and drawing; the API only exposes the summary fields and the PNG. */
export type DiagramRow = Diagram & {
  project_id: string
  model?: UseCaseModel
  svg: string
  /** Positions moved by hand (#37), element id → centre [x, y]. Like the backend, the PNG export ignores them. */
  layout?: Record<string, [number, number]>
  /** A package diagram (from the Design step): its PlantUML source and the statements its section cites, as the API stores. */
  source?: string
  statement_ids?: string[]
  /** #38: the look chosen by the user; undefined = inherit from parent_id, else the default */
  style?: DiagramStyle
}

/** Stories backlog (3.4); the assignee's email is looked up on read, like the API's join. */
export type StoryRow = Omit<Story, 'assignee_email'> & { project_id: string }

/** Tests feature (stream 6) rows; shapes live in ./testing.ts. */
export type TestsState = {
  designs: Record<string, unknown>
  criteria: unknown[]
  conditions: unknown[]
  flows: unknown[]
  targets: Record<string, unknown[]>
  cases: unknown[]
  runs: unknown[]
  results: unknown[]
  flags: unknown[]
  nextCase: Record<string, number>
}
export const emptyTests = (): TestsState => ({
  designs: {}, criteria: [], conditions: [], flows: [], targets: {}, cases: [], runs: [], results: [], flags: [], nextCase: {},
})

/** System design sections (Feature 4) per project and kind; shapes live in ./design.ts. */
export type DesignState = Record<string, Record<string, unknown>>

export type MockDb = {
  collab: CollabState
  tests: TestsState
  design: DesignState
  consent: Record<string, { version: string; at: string }>
  projects: ProjectRow[]
  statements: Record<string, RequirementStatement[]>
  items: Record<string, ExtractedItem[]>
  jobs: JobRow[]
  diagrams: DiagramRow[]
  nextStatement: Record<string, number>
  stories: StoryRow[]
  nextStory: Record<string, number>
  documents: Record<string, ProjectDocument[]>
  flags: Record<string, FlagRow[]>
}

const KEY = 'sddg.mock.db'
const empty = (): MockDb => ({ collab: emptyCollab(), tests: emptyTests(), design: {}, consent: {}, projects: [], statements: {}, items: {}, jobs: [], diagrams: [], nextStatement: {}, stories: [], nextStory: {}, flags: {}, documents: {} })

let db: MockDb = load()

function load(): MockDb {
  try {
    const raw = typeof localStorage !== 'undefined' ? localStorage.getItem(KEY) : null
    return raw ? { ...empty(), ...JSON.parse(raw) } : empty()
  } catch {
    return empty()
  }
}
export function save() {
  try {
    localStorage.setItem(KEY, JSON.stringify(db))
  } catch {
    /* storage unavailable (tests, private mode): keep it in memory */
  }
}
export function resetDb(next: MockDb = empty()) {
  db = next
}
export const getDb = () => db

export const uid = (prefix: string) => `${prefix}_${Math.random().toString(36).slice(2, 10)}`
const now = () => new Date().toISOString()

/* ---------- job timing: status is derived from elapsed time, so polling shows real progress ---------- */

const QUEUE_DEFAULT_MS = 1200
const STEP_DEFAULT_MS = 1600
const EXTRACTION_STEPS = ['Splitting the text into requirements', 'Checking requirement quality', 'Requirements ready to review']

/** Extra job kinds (the Tests feature registers test_criteria and test_steps) with their steps and result. */
type JobKindPlugin = { steps: string[]; queueMs: number; stepMs: number; apply: (job: JobRow) => void }
const plugins: Record<string, JobKindPlugin> = {}
export function registerJobKind(kind: string, plugin: JobKindPlugin) {
  plugins[kind] = plugin
}

export function advance(job: JobRow, opts: { fast?: boolean } = {}): JobRow {
  if (job.status === 'succeeded' || job.status === 'failed') return job
  const plugin = plugins[job.kind]
  // Mirrors the API: generation is "extract building blocks" + one step per diagram type.
  const steps =
    plugin?.steps ??
    (job.kind === 'extraction'
      ? EXTRACTION_STEPS
      : ['Extracting building blocks', ...(job.diagram_types ?? []).map((t) => `Generating and rendering ${TYPE_LABEL[t]} diagram`)])
  const QUEUE_MS = plugin?.queueMs ?? QUEUE_DEFAULT_MS
  const STEP_MS = plugin?.stepMs ?? STEP_DEFAULT_MS
  const elapsed = opts.fast ? 10000 : Date.now() - new Date(job.created_at!).getTime()
  if (elapsed < QUEUE_MS) {
    job.status = 'queued'
    job.queue_position = 1
    job.progress = { step: 0, total: steps.length, label: 'Queued' }
    return job
  }
  job.started_at ??= new Date(new Date(job.created_at!).getTime() + QUEUE_MS).toISOString()
  job.queue_position = null
  const step = Math.floor((elapsed - QUEUE_MS) / STEP_MS)
  if (step < steps.length) {
    job.status = 'running'
    job.progress = { step: step + 1, total: steps.length, label: steps[step] }
    return job
  }
  if (job.kind === 'extraction' && splitStatements(job.payload ?? '').length === 0) {
    job.status = 'failed'
    job.error = 'No requirements could be extracted from this document.'
    job.finished_at = now()
    job.progress = { step: steps.length, total: steps.length, label: 'Failed' }
    if (db.documents?.[job.project_id]) {
      for (const doc of db.documents[job.project_id]) {
        if (doc.job_id === job.id || doc.status === 'processing' || doc.status === 'uploaded') {
          doc.status = 'failed'
          doc.warning = 'No requirements could be extracted from this document.'
        }
      }
    }
    save()
    return job
  }
  job.status = 'succeeded'
  job.finished_at = now()
  job.progress = { step: steps.length, total: steps.length, label: 'Done' }
  if (!job.applied) {
    job.applied = true
    if (plugin) plugin.apply(job)
    else if (job.kind === 'extraction') applyExtraction(job)
    else applyGeneration(job)
  }
  save()
  return job
}

function applyExtraction(job: JobRow) {
  const pid = job.project_id
  const start = db.nextStatement[pid] ?? 1
  // IDs are never reused (FR4g), so numbering continues from the last statement ever issued.
  const statements = splitStatements(job.payload ?? '').map((s, i) => ({
    ...s,
    id: uid('st'),
    ref: `R-${String(start + i).padStart(3, '0')}`,
  }))
  db.nextStatement[pid] = start + statements.length
  db.statements[pid] = [...(db.statements[pid] ?? []), ...statements]
  db.flags[pid] = [...(db.flags[pid] ?? []), ...detectFlags(statements, db.statements[pid], uid)]

  // FR1b: the uploaded document this extraction came from is now processed.
  for (const doc of db.documents?.[pid] ?? []) {
    if (doc.job_id === job.id) doc.status = 'processed'
  }

  resetModel(pid) // requirements-first: building blocks are extracted later, for the chosen diagrams
}

/** A requirement changed: drop the building blocks and the confirmation (mirrors db.reset_model). */
export function resetModel(pid: string) {
  // Items the user added or edited are kept, like the API.
  db.items[pid] = (db.items[pid] ?? []).filter((i) => i.origin !== 'system-extracted')
  const p = db.projects.find((x) => x.id === pid)
  if (p) p.extracted_nodes = []
  touch(pid, { clearConfirmation: true })
}

/** Mirrors the API's extract_building_blocks: the mock extracts every node once, over the confirmed requirements. */
function extractBuildingBlocks(pid: string) {
  const p = db.projects.find((x) => x.id === pid)!
  if (p.extracted_nodes?.length) return
  const drafts = extractItems(db.statements[pid] ?? [])
  const idFor = new Map(drafts.map((d) => [d.key, uid('it')]))
  const kept = db.items[pid] ?? []
  db.items[pid] = [
    ...kept,
    ...drafts
      .filter((d) => !kept.some((k) => k.category === d.category && k.name.toLowerCase() === d.name.toLowerCase()))
      .map(({ key, ...d }) => ({
        ...d,
        id: idFor.get(key)!,
        source_item_id: d.source_item_id ? (idFor.get(d.source_item_id) ?? null) : null,
        target_item_id: d.target_item_id ? (idFor.get(d.target_item_id) ?? null) : null,
      })),
  ]
  p.extracted_nodes = ['actors', 'dataflows', 'entities', 'interactions', 'processes', 'relationships']
}

const TYPE_LABEL: Record<string, string> = { use_case: 'Use Case', class: 'Class', activity: 'Activity', sequence: 'Sequence', dfd: 'Data Flow', component: 'Component', package: 'Package' }

function applyGeneration(job: JobRow) {
  const pid = job.project_id
  const project = db.projects.find((p) => p.id === pid)!
  extractBuildingBlocks(pid)
  const ids: string[] = []
  for (const type of job.diagram_types?.length ? job.diagram_types : ['use_case' as const]) {
    const model = type === 'use_case' ? buildUseCaseModel(db.items[pid] ?? [], project.name) : undefined
    const diagram: DiagramRow = {
      id: uid('dg'),
      project_id: pid,
      type,
      title: `${project.name} · ${TYPE_LABEL[type]}`,
      created_at: now(),
      parent_id: null,
      instruction: null,
      model,
      svg: model ? renderUseCase(model) : renderPlaceholder(TYPE_LABEL[type], db.items[pid] ?? []),
    }
    db.diagrams.push(diagram)
    ids.push(diagram.id)
  }
  job.diagram_ids = ids
  touch(pid)
}

export function touch(pid: string, opts: { clearConfirmation?: boolean } = {}) {
  const p = db.projects.find((x) => x.id === pid)
  if (!p) return
  p.updated_at = now()
  if (opts.clearConfirmation) p.confirmed_at = null
}

export function createJob(projectId: string, kind: Job['kind'], extra: Partial<JobRow> = {}): JobRow {
  const job: JobRow = {
    id: uid('job'),
    project_id: projectId,
    kind,
    status: 'queued',
    queue_position: 1,
    progress: { step: 0, total: 3, label: 'Queued' },
    created_at: now(),
    started_at: null,
    finished_at: null,
    error: null,
    diagram_types: [],
    diagram_ids: [],
    ...extra,
  }
  db.jobs.push(job)
  save()
  return job
}

export function publicJob({ project_id: _p, payload: _t, applied: _a, ...job }: JobRow): Job {
  return job
}

/** #38: a version's own style, else the nearest earlier version's, else the default. */
export function styleFor(d: DiagramRow): DiagramStyle {
  const seen = new Set<string>()
  for (let v: DiagramRow | undefined = d; v && !seen.has(v.id); v = db.diagrams.find((x) => x.id === v!.parent_id)) {
    if (v.style) return v.style
    seen.add(v.id)
  }
  return DEFAULT_STYLE
}

export function diagramView(d: DiagramRow): Diagram {
  return {
    id: d.id,
    type: d.type,
    title: d.title,
    created_at: d.created_at,
    parent_id: d.parent_id ?? null,
    instruction: d.instruction ?? null,
    svg: d.svg,
    elements: elementsOf(d),
    statements: db.statements[d.project_id] ?? [],
  }
}

/** Traceability for the viewer: each drawn actor / use case with the requirements behind it. */
function elementsOf(d: DiagramRow) {
  if (!d.model) return []
  const items = new Map((db.items[d.project_id] ?? []).map((i) => [i.id, i]))
  return [
    ...d.model.actors.map((a) => ({ element_id: a.id, model_item_id: a.id, kind: 'actor', label: a.name, statement_ids: items.get(a.id)?.statement_ids ?? [] })),
    ...d.model.cases.map((c) => ({ element_id: c.id, model_item_id: c.assumed ? null : c.id, kind: 'use_case', label: c.name, statement_ids: items.get(c.id)?.statement_ids ?? [] })),
  ]
}

export function projectView(p: ProjectRow): components['schemas']['Project'] {
  const extraction = db.jobs.filter((j) => j.project_id === p.id && j.kind === 'extraction').at(-1)
  return {
    id: p.id,
    name: p.name,
    role: 'owner',
    is_owner: true, // the mock has no other members: only the owner can see a project
    archived_at: p.archived_at ?? null,
    archived_by: p.archived_by ?? null,
    client_name: p.client_name ?? null,
    contact_email: p.contact_email ?? null,
    created_at: p.created_at,
    updated_at: p.updated_at,
    statement_count: db.statements[p.id]?.length ?? 0,
    item_count: db.items[p.id]?.length ?? 0,
    extraction: extraction ? publicJob(advance(extraction)) : null,
    confirmed: p.confirmed_at !== null,
    confirmed_at: p.confirmed_at,
    diagram_count: db.diagrams.filter((d) => d.project_id === p.id).length,
    document_count: db.documents?.[p.id]?.length ?? 0,
    document_page_count: (db.documents?.[p.id] ?? []).reduce((sum, d) => sum + d.page_count, 0),
    open_flag_count: (db.flags[p.id] ?? []).filter((f) => f.status === 'open' && db.statements[p.id]?.some((s) => s.id === f.statement_id)).length,
    extracted_nodes: p.extracted_nodes ?? [],
  }
}
