/** MOCK ONLY. In-browser stand-in for the backend's Postgres, persisted to localStorage between reloads. */
import type { Diagram, ExtractedItem, Job, RequirementStatement } from '@/api/client'
import type { components } from '@/api/schema'
import { extractItems, splitStatements } from './extract'
import { buildUseCaseModel, renderUseCase, type UseCaseModel } from './render'

type ProjectRow = {
  id: string
  name: string
  owner: string
  created_at: string
  updated_at: string
  confirmed_at: string | null
}
type JobRow = Job & { project_id: string; payload?: string; applied?: boolean }
/** The server keeps the model and drawing; the API only exposes the summary fields and the PNG. */
export type DiagramRow = Diagram & { project_id: string; model?: UseCaseModel; svg: string }

export type MockDb = {
  consent: Record<string, { version: string; at: string }>
  projects: ProjectRow[]
  statements: Record<string, RequirementStatement[]>
  items: Record<string, ExtractedItem[]>
  jobs: JobRow[]
  diagrams: DiagramRow[]
  nextStatement: Record<string, number>
}

const KEY = 'sddg.mock.db'
const empty = (): MockDb => ({ consent: {}, projects: [], statements: {}, items: {}, jobs: [], diagrams: [], nextStatement: {} })

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

const QUEUE_MS = 1200
const STEP_MS = 1600
const EXTRACTION_STEPS = ['Splitting into requirement statements', 'Extracting modelling items', 'Merging and checking items']
const GENERATION_STEPS = ['Building the diagram model', 'Rendering the diagram', 'Checking notation']

export function advance(job: JobRow): JobRow {
  if (job.status === 'succeeded' || job.status === 'failed') return job
  const steps = job.kind === 'extraction' ? EXTRACTION_STEPS : GENERATION_STEPS
  const elapsed = Date.now() - new Date(job.created_at!).getTime()
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
    const prefix = job.kind === 'generation' ? 'Generating diagram 1 of 1: ' : ''
    job.progress = { step: step + 1, total: steps.length, label: prefix + steps[step] }
    return job
  }
  job.status = 'succeeded'
  job.finished_at = now()
  job.progress = { step: steps.length, total: steps.length, label: 'Done' }
  if (!job.applied) {
    job.applied = true
    if (job.kind === 'extraction') applyExtraction(job)
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

  const drafts = extractItems(db.statements[pid])
  const idFor = new Map(drafts.map((d) => [d.key, uid('it')]))
  // Keep user-added / user-edited items: they are never overwritten by re-extraction (A18).
  const kept = (db.items[pid] ?? []).filter((i) => i.origin !== 'system-extracted')
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
  touch(pid, { clearConfirmation: true })
}

function applyGeneration(job: JobRow) {
  const pid = job.project_id
  const project = db.projects.find((p) => p.id === pid)!
  const model = buildUseCaseModel(db.items[pid] ?? [], project.name)
  const diagram: DiagramRow = {
    id: uid('dg'),
    project_id: pid,
    type: 'use_case',
    title: `${project.name} · Use Case`,
    created_at: now(),
    parent_id: null,
    instruction: null,
    model,
    svg: renderUseCase(model),
  }
  db.diagrams.push(diagram)
  job.diagram_ids = [diagram.id]
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

export function diagramView(d: DiagramRow): Diagram {
  return {
    id: d.id,
    type: d.type,
    title: d.title,
    created_at: d.created_at,
    parent_id: d.parent_id ?? null,
    instruction: d.instruction ?? null,
  }
}

export function projectView(p: ProjectRow): components['schemas']['Project'] {
  const extraction = db.jobs.filter((j) => j.project_id === p.id && j.kind === 'extraction').at(-1)
  return {
    id: p.id,
    name: p.name,
    role: 'owner',
    created_at: p.created_at,
    updated_at: p.updated_at,
    statement_count: db.statements[p.id]?.length ?? 0,
    item_count: db.items[p.id]?.length ?? 0,
    extraction: extraction ? publicJob(advance(extraction)) : null,
    confirmed: p.confirmed_at !== null,
    confirmed_at: p.confirmed_at,
    diagram_count: db.diagrams.filter((d) => d.project_id === p.id).length,
  }
}
