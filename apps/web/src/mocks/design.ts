/**
 * MOCK ONLY. System design (Feature 4): the same routes, rules and messages as apps/api/routers/design.py, backed by
 * the in-browser mock database. Derived values use a small copy of services/ai-extraction/app/design/goals.py.
 */
import { http, HttpResponse, type HttpResponseResolver } from 'msw'
import type { DesignSection, Job } from '@/api/client'
import { GOAL_NAMES } from '@/features/design/goals'
import { AI_SECTION_VERSION } from '@/features/privacy/policy'
import { advance, createJob, getDb, publicJob, registerJobKind, save, type JobRow } from './db'

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
