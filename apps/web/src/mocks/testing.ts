/**
 * MOCK ONLY. MSW handlers for the Tests feature (stream 6) - the same routes and shapes as apps/api, backed by the
 * in-browser mock database, so the Tests screens work with VITE_USE_MOCKS=true and in the vitest suite.
 *
 * AI requests 1 and 2 are faked by ./testing-engine.ts. Like the real backend, a test job takes a few seconds and the
 * page sees it through GET /jobs/{id}.
 */
import { http, HttpResponse, type HttpResponseResolver } from 'msw'
import type {
  CaseKind,
  CasePriority,
  Condition,
  Flag,
  FlagType,
  ResultStatus,
  RunMode,
  RunSelection,
  TestCase,
  TestDesign,
  TestRequirementSummary,
  TestRun,
  TestRunSummary,
} from '@/api/client'
import { AI_SECTION_VERSION } from '@/features/privacy/policy'
import { createJob, getDb, publicJob, registerJobKind, save, uid, type JobRow } from './db'
import {
  boundariesFor,
  buildDrafts,
  classesFor,
  fakeCriteria,
  fakeSteps,
  isVague,
  type EngineCondition,
  type EngineFlow,
  type EngineTarget,
} from './testing-engine'

/* ---------- rows ---------- */

type DesignRow = { statement_id: string; project_id: string; text_at_generation: string; generated_at: string }
type CriterionRow = { id: string; project_id: string; statement_id: string; given: string; when: string; then: string }
type ConditionRow = EngineCondition & { id: string; project_id: string; statement_id: string; description: string; unit: string | null }
type FlowRow = EngineFlow & { id: string; project_id: string; statement_id: string }
type CaseRow = Omit<TestCase, 'statement_ref' | 'freshness' | 'last_result'> & { project_id: string; text_at_generation: string }
type RunRow = { id: string; project_id: string; name: string; mode: RunMode; case_ids: string[]; created_by: string; created_at: string; finished_at: string | null }
type ResultRow = { run_id: string; case_id: string; project_id: string; status: ResultStatus; note: string | null; marked_by: string; marked_at: string }
type FlagRow = Omit<Flag, 'statement_ref' | 'has_suggestion' | 'suggestion'> & { project_id: string; suggested_fix: string | null; template: string | null }

type Rows = {
  designs: Record<string, DesignRow>
  criteria: CriterionRow[]
  conditions: ConditionRow[]
  flows: FlowRow[]
  targets: Record<string, EngineTarget[]>
  cases: CaseRow[]
  runs: RunRow[]
  results: ResultRow[]
  flags: FlagRow[]
  nextCase: Record<string, number>
}
const T = () => getDb().tests as unknown as Rows
const now = () => new Date().toISOString()
const statementsOf = (pid: string) => getDb().statements[pid] ?? []
const statementOf = (pid: string, sid: string) => statementsOf(pid).find((s) => s.id === sid)

/** Mirrors the database's ON DELETE CASCADE: a deleted requirement takes its design, cases and their results with it. */
/** The project's Tests job still queued, running or waiting, if any: only one runs at a time (like the API). */
function activeTestJob(pid: string) {
  return getDb()
    .jobs.filter((j) => j.project_id === pid && j.kind.startsWith('test_') && ['queued', 'running', 'waiting'].includes(j.status))
    .at(-1)
}

const BUSY = 'Test generation is already running for this project. Wait for it to finish, then try again.'

function cascade(pid: string) {
  const live = new Set(statementsOf(pid).map((s) => s.id))
  const t = T()
  const gone = (r: { project_id: string; statement_id: string }) => r.project_id === pid && !live.has(r.statement_id)
  if (![...t.criteria, ...t.conditions, ...t.flows, ...t.cases, ...t.flags].some(gone)) return
  const goneCases = new Set(t.cases.filter(gone).map((c) => c.id))
  t.criteria = t.criteria.filter((r) => !gone(r))
  t.conditions = t.conditions.filter((r) => !gone(r))
  t.flows = t.flows.filter((r) => !gone(r))
  t.cases = t.cases.filter((r) => !gone(r))
  t.flags = t.flags.filter((r) => !gone(r))
  t.results = t.results.filter((r) => !goneCases.has(r.case_id))
  // runs count only the cases that still exist, so their unmarked count can still reach 0
  for (const run of t.runs) if (run.project_id === pid) run.case_ids = run.case_ids.filter((id) => !goneCases.has(id))
  for (const [sid, d] of Object.entries(t.designs)) if (d.project_id === pid && !live.has(sid)) delete t.designs[sid]
  save()
}

/* ---------- views ---------- */

function openFlagTypes(pid: string, sid: string): FlagType[] {
  const types = new Set<FlagType>()
  const text = statementOf(pid, sid)?.text ?? ''
  if (isVague(text)) types.add('ambiguous') // the mock's stand-in for the quality checker
  for (const f of T().flags) if (f.statement_id === sid && f.status === 'open') types.add(f.type)
  return [...types]
}

function flagView(f: FlagRow): Flag {
  const { project_id: _p, template: _t, suggested_fix, ...rest } = f
  return {
    ...rest,
    statement_ref: statementOf(f.project_id, f.statement_id)?.ref ?? '',
    has_suggestion: !!suggested_fix,
    suggestion: suggested_fix ?? 'No suggestion available.',
  }
}

function lastResult(caseId: string): ResultStatus | null {
  const runs = new Map(T().runs.map((r) => [r.id, r]))
  const mine = T()
    .results.filter((r) => r.case_id === caseId)
    .sort((a, b) => (runs.get(b.run_id)?.created_at ?? '').localeCompare(runs.get(a.run_id)?.created_at ?? ''))
  return mine[0]?.status ?? null
}

function caseView(c: CaseRow): TestCase {
  const { project_id: _p, text_at_generation, ...rest } = c
  const st = statementOf(c.project_id, c.statement_id)
  return {
    ...rest,
    statement_ref: st?.ref ?? '',
    freshness: st && st.text !== text_at_generation ? 'out_of_date' : 'current',
    last_result: lastResult(c.id),
  }
}

function conditionView(c: ConditionRow): Condition {
  return {
    id: c.id,
    name: c.name,
    kind: c.kind,
    description: c.description,
    min: c.min,
    max: c.max,
    unit: c.unit,
    values: c.values,
    invalid_values: c.invalid_values,
    classes: classesFor(c),
    boundaries: boundariesFor(c),
  }
}

function summary(pid: string, sid: string): TestRequirementSummary {
  const st = statementOf(pid, sid)!
  const design = T().designs[sid]
  const cases = T().cases.filter((c) => c.statement_id === sid)
  const drafts = cases.filter((c) => c.status === 'draft' && c.origin === 'generated')
  return {
    statement_id: sid,
    ref: st.ref,
    text: st.text,
    label: st.label ?? null,
    designed: !!design,
    stale: !!design && design.text_at_generation !== st.text,
    criteria_count: T().criteria.filter((c) => c.statement_id === sid).length,
    draft_count: drafts.length,
    kept_count: drafts.filter((c) => c.kept).length,
    ready_count: cases.filter((c) => c.status === 'ready').length,
    boundary_count: T().conditions.filter((c) => c.statement_id === sid).reduce((n, c) => n + boundariesFor(c).length, 0),
    open_question: T().flags.some((f) => f.statement_id === sid && f.type === 'untestable' && f.status === 'open'),
    open_flags: openFlagTypes(pid, sid),
  }
}

function designView(pid: string, sid: string): TestDesign {
  const s = summary(pid, sid)
  const questions = T().flags.filter((f) => f.statement_id === sid && f.type === 'untestable')
  return {
    statement_id: sid,
    ref: s.ref,
    text: s.text,
    label: s.label,
    designed: s.designed,
    stale: s.stale,
    generated_at: T().designs[sid]?.generated_at ?? null,
    criteria: T().criteria.filter((c) => c.statement_id === sid).map(({ id, given, when, then }) => ({ id, given, when, then })),
    conditions: T().conditions.filter((c) => c.statement_id === sid).map(conditionView),
    flows: T().flows.filter((f) => f.statement_id === sid).map(({ id, kind, text }) => ({ id, kind, text })),
    performance_targets: T().targets[sid] ?? [],
    drafts: T().cases.filter((c) => c.statement_id === sid && c.origin === 'generated').map(caseView),
    question: questions.length ? flagView(questions.at(-1)!) : null,
    open_flags: s.open_flags,
  }
}

function tally(run: RunRow): TestRunSummary['tally'] {
  const results = T().results.filter((r) => r.run_id === run.id)
  const count = (s: ResultStatus) => results.filter((r) => r.status === s).length
  return { pass: count('pass'), fail: count('fail'), blocked: count('blocked'), skipped: count('skipped'), unmarked: run.case_ids.length - results.length }
}

function runSummary(run: RunRow): TestRunSummary {
  const { project_id: _p, case_ids, ...rest } = run
  return { ...rest, case_count: case_ids.length, tally: tally(run) }
}

function runView(run: RunRow): TestRun {
  const cases = new Map(T().cases.map((c) => [c.id, c]))
  return {
    ...runSummary(run),
    items: run.case_ids
      .filter((id) => cases.has(id))
      .map((id) => {
        const r = T().results.find((x) => x.run_id === run.id && x.case_id === id)
        return {
          case: caseView(cases.get(id)!),
          result: r ? { case_id: id, status: r.status, note: r.note, marked_by: r.marked_by, marked_at: r.marked_at } : null,
        }
      }),
  }
}

/* ---------- design storage (same rules as the backend) ---------- */

function nextNumber(pid: string) {
  const n = (T().nextCase[pid] ?? 0) + 1
  T().nextCase[pid] = n // the counter never hands out a number twice
  return `TC-${String(n).padStart(3, '0')}`
}

const tc = (number: string) => Number(number.split('-')[1])

/** Replaces this requirement's generated drafts with the engine's; ready and hand-written cases stay. Same rule as
 *  the backend: a draft with an unchanged title keeps its number and keep/discard choice, other new drafts take the
 *  replaced drafts' numbers first (drafts are never run), then new ones. */
function rebuildDrafts(pid: string, sid: string) {
  const st = statementOf(pid, sid)!
  const t = T()
  const isDraft = (c: CaseRow) => c.statement_id === sid && c.origin === 'generated' && c.status === 'draft'
  const old = t.cases.filter(isDraft)
  t.cases = t.cases.filter((c) => !isDraft(c))
  const taken = new Set(t.cases.filter((c) => c.statement_id === sid).map((c) => c.title))
  const fresh = buildDrafts(
    t.conditions.filter((c) => c.statement_id === sid),
    t.flows.filter((f) => f.statement_id === sid),
    t.targets[sid] ?? [],
    t.criteria.filter((c) => c.statement_id === sid),
  ).filter((d) => {
    if (taken.has(d.title)) return false // already listed: a kept or hand-written case, or an identical new draft
    taken.add(d.title)
    return true
  })
  const byTitle = new Map(old.map((o) => [o.title, o]))
  const same = new Set(fresh.filter((d) => byTitle.has(d.title)).map((d) => d.title))
  const pool = old.filter((o) => !same.has(o.title)).map((o) => o.number).sort((a, b) => tc(a) - tc(b))
  const used = new Set<string>()
  for (const d of fresh) {
    const prev = byTitle.get(d.title)
    const reuse = prev && !used.has(prev.number)
    const number = reuse ? prev.number : (pool.shift() ?? nextNumber(pid))
    used.add(number)
    t.cases.push({
      ...d,
      id: uid('tc'),
      project_id: pid,
      statement_id: sid,
      number,
      status: 'draft',
      kept: reuse ? prev.kept : true,
      origin: 'generated',
      preconditions: [],
      steps: [],
      expected: null,
      created_at: now(),
      text_at_generation: st.text,
    })
  }
  t.cases.sort((a, b) => tc(a.number) - tc(b.number))
}

function applyCriteria(job: JobRow) {
  const pid = job.project_id
  const t = T()
  for (const sid of JSON.parse(job.payload ?? '[]') as string[]) {
    const st = statementOf(pid, sid)
    if (!st) continue
    const ai = fakeCriteria(st.text)
    t.criteria = t.criteria.filter((c) => c.statement_id !== sid)
    t.conditions = t.conditions.filter((c) => c.statement_id !== sid)
    t.flows = t.flows.filter((f) => f.statement_id !== sid)
    t.designs[sid] = { statement_id: sid, project_id: pid, text_at_generation: st.text, generated_at: now() }
    t.targets[sid] = ai.targets
    t.criteria.push(...ai.criteria.map((c) => ({ ...c, id: uid('cr'), project_id: pid, statement_id: sid })))
    t.conditions.push(...ai.conditions.map((c) => ({ ...c, id: uid('cd'), project_id: pid, statement_id: sid })))
    t.flows.push(...ai.flows.map((f) => ({ ...f, id: uid('fl'), project_id: pid, statement_id: sid })))
    const open = t.flags.find((f) => f.statement_id === sid && f.type === 'untestable' && f.status === 'open')
    if (!ai.testable) {
      if (open) open.question = ai.question
      else
        t.flags.push({
          id: uid('fg'), project_id: pid, statement_id: sid, type: 'untestable',
          reason: 'The AI could not write a measurable test for this requirement.',
          trigger_text: null, question: ai.question, answer: null, status: 'open', resolved_by: null,
          suggested_fix: null, template: ai.suggestion_template,
        })
    } else if (open) {
      open.status = 'resolved'
      open.resolved_by = 're-analysis'
    }
    rebuildDrafts(pid, sid)
  }
}

function applySteps(job: JobRow) {
  const ids = new Set(JSON.parse(job.payload ?? '[]') as string[])
  for (const c of T().cases) {
    if (!ids.has(c.id) || !c.kept || c.status !== 'draft') continue
    const st = statementOf(c.project_id, c.statement_id)
    const written = fakeSteps({ title: c.title, statement_ref: st?.ref ?? '', test_data: c.test_data, outcome: c.outcome ?? null })
    Object.assign(c, written, { status: 'ready' })
  }
}

const test = import.meta.env.MODE === 'test'
registerJobKind('test_criteria', {
  steps: ['Asking the AI for criteria and conditions', 'Building classes, boundaries and drafts'],
  queueMs: test ? 0 : 1000,
  stepMs: test ? 40 : 1400,
  apply: applyCriteria,
})
registerJobKind('test_steps', {
  steps: ['Asking the AI to write steps', 'Saving the steps'],
  queueMs: test ? 0 : 1000,
  stepMs: test ? 40 : 1400,
  apply: applySteps,
})

/* ---------- run selection (same rules as the backend) ---------- */

function selection(pid: string): RunSelection {
  const cases = T().cases.filter((c) => c.project_id === pid).map(caseView)
  const ready = cases.filter((c) => c.status === 'ready' && c.kept).sort((a, b) => a.number.localeCompare(b.number))
  const lastRun = T()
    .runs.filter((r) => r.project_id === pid && r.finished_at)
    .sort((a, b) => b.created_at.localeCompare(a.created_at))[0]
  const lastStatus = new Map(lastRun ? T().results.filter((r) => r.run_id === lastRun.id).map((r) => [r.case_id, r.status]) : [])
  const troubled = (id: string) => ['fail', 'blocked'].includes(lastStatus.get(id) ?? '')

  const failed = ready.filter((c) => troubled(c.id))
  const changed = [...new Set(cases.filter((c) => c.freshness === 'out_of_date').map((c) => c.statement_id))]
  const refOf = (sid: string) => statementOf(pid, sid)?.ref ?? sid
  const shared = new Map<string, string>() // statement id -> "shares X with R-00n"
  for (const item of getDb().items[pid] ?? []) {
    const hit = changed.find((sid) => item.statement_ids.includes(sid))
    if (!hit) continue
    for (const sid of item.statement_ids) if (!changed.includes(sid) && !shared.has(sid)) shared.set(sid, `shares ${item.name} with ${refOf(hit)}`)
  }
  const regression = ready
    .filter((c) => changed.includes(c.statement_id) || shared.has(c.statement_id))
    .sort((a, b) => Number(troubled(b.id)) - Number(troubled(a.id)))
  const reasonFor = (c: TestCase) =>
    [
      troubled(c.id) ? `${lastStatus.get(c.id) === 'fail' ? 'failed' : 'blocked'} last run` : null,
      changed.includes(c.statement_id) ? `${c.statement_ref} changed` : shared.get(c.statement_id),
    ]
      .filter(Boolean)
      .join(' · ')

  const base = changed.length ? regression : ready
  const minimal: TestCase[] = []
  for (const sid of [...new Set(base.map((c) => c.statement_id))]) {
    for (const kind of ['positive', 'negative', 'edge'] as const) {
      const pick = base.find((c) => c.statement_id === sid && c.kind === kind)
      if (pick) minimal.push(pick)
    }
  }
  const mode = (list: TestCase[], reason: (c: TestCase) => string | undefined, warning: string | null = null) => ({
    case_ids: list.map((c) => c.id),
    reasons: Object.fromEntries(list.map((c) => [c.id, reason(c) ?? ''] as const).filter(([, r]) => r)),
    warning,
  })
  return {
    changed_refs: changed.map(refOf),
    all: mode(ready, () => undefined),
    failed: mode(failed, (c) => `${lastStatus.get(c.id) === 'fail' ? 'failed' : 'blocked'} in ${lastRun?.name}`, lastRun ? null : 'No run has finished yet.'),
    regression: mode(regression, reasonFor, changed.length ? null : 'No requirement has changed since its cases were made.'),
    minimal: mode(minimal, (c) => `one ${c.kind} case for ${c.statement_ref}`, 'A minimal set drops cases and can miss faults. Prioritised regression is the default.'),
  }
}

/* ---------- handlers ---------- */

type Helpers = {
  u: (path: string) => string
  authed: (fn: (ctx: { email: string; params: Record<string, string | readonly string[] | undefined>; request: Request }) => Response | Promise<Response>) => HttpResponseResolver
  ownedProject: (email: string, id: unknown) => { id: string } | undefined
  fail: (status: number, detail: string, code?: string) => Response
  notFound: () => Response
}

const KINDS: CaseKind[] = ['positive', 'negative', 'edge']
const PRIORITIES: CasePriority[] = ['high', 'medium', 'low']
const RESULTS: ResultStatus[] = ['pass', 'fail', 'blocked', 'skipped']
const MODES: RunMode[] = ['all', 'failed', 'regression', 'minimal', 'pick']

export function testingHandlers({ u, authed, ownedProject, fail, notFound }: Helpers) {
  const consentRequired = (email: string) =>
    getDb().consent[email]?.version !== AI_SECTION_VERSION
      ? fail(403, 'Agree to AI processing before generating tests.', 'consent_required')
      : null

  return [
    http.post(
      u('/projects/:project_id/flags/:flag_id/answer'),
      authed(async ({ email, params, request }) => {
        const p = ownedProject(email, params.project_id)
        const flag = p && T().flags.find((f) => f.id === params.flag_id && f.project_id === p.id)
        if (!p || !flag) return notFound()
        const answer = String(((await request.json()) as { answer?: string }).answer ?? '').trim()
        if (!answer) return fail(422, 'Write an answer first.')
        flag.answer = answer
        flag.status = 'resolved'
        flag.resolved_by = email
        if (flag.template) flag.suggested_fix = flag.template.replace('{answer}', answer)
        save()
        return HttpResponse.json(flagView(flag))
      }),
    ),

    http.get(
      u('/projects/:project_id/tests/requirements'),
      authed(({ email, params }) => {
        const p = ownedProject(email, params.project_id)
        if (p) cascade(p.id)
        if (!p) return notFound()
        const active = activeTestJob(p.id)
        return HttpResponse.json({
          requirements: statementsOf(p.id).map((s) => summary(p.id, s.id)),
          active_job: active ? publicJob(active) : null,
        })
      }),
    ),
    http.get(
      u('/projects/:project_id/tests/requirements/:statement_id'),
      authed(({ email, params }) => {
        const p = ownedProject(email, params.project_id)
        if (p) cascade(p.id)
        if (!p || !statementOf(p.id, String(params.statement_id))) return notFound()
        return HttpResponse.json(designView(p.id, String(params.statement_id)))
      }),
    ),
    http.post(
      u('/projects/:project_id/tests/criteria-jobs'),
      authed(async ({ email, params, request }) => {
        const p = ownedProject(email, params.project_id)
        if (!p) return notFound()
        const refused = consentRequired(email)
        if (refused) return refused
        const ids = ((await request.json()) as { statement_ids?: string[] }).statement_ids ?? []
        if (!ids.length || ids.length > 30) return fail(422, 'Choose between 1 and 30 requirements.')
        if (ids.some((id) => !statementOf(p.id, id))) return fail(422, 'One of the requirements no longer exists.')
        if (activeTestJob(p.id)) return fail(409, BUSY)
        const job = createJob(p.id, 'test_criteria', { payload: JSON.stringify(ids), progress: { step: 0, total: 2, label: 'Queued' } })
        return HttpResponse.json(publicJob(job), { status: 202 })
      }),
    ),
    http.patch(
      u('/projects/:project_id/tests/conditions/:condition_id'),
      authed(async ({ email, params, request }) => {
        const p = ownedProject(email, params.project_id)
        const c = p && T().conditions.find((x) => x.id === params.condition_id && x.project_id === p.id)
        if (!p || !c) return notFound()
        const body = (await request.json()) as { min?: number | null; max?: number | null; values?: string[]; invalid_values?: string[] }
        const next = { ...c, ...body }
        if (next.kind !== 'set' && next.min !== null && next.max !== null && next.min > next.max)
          return fail(422, 'The lower limit must not be above the upper limit.')
        if (next.kind === 'count' && (next.min ?? 0) < 0) return fail(422, 'A count cannot go below zero.')
        if (next.kind === 'set' && !next.values.length) return fail(422, 'A set needs at least one valid value.')
        Object.assign(c, body)
        rebuildDrafts(p.id, c.statement_id)
        save()
        return HttpResponse.json(designView(p.id, c.statement_id))
      }),
    ),
    http.patch(
      u('/projects/:project_id/tests/criteria/:criterion_id'),
      authed(async ({ email, params, request }) => {
        const p = ownedProject(email, params.project_id)
        const c = p && T().criteria.find((x) => x.id === params.criterion_id && x.project_id === p.id)
        if (!p || !c) return notFound()
        const { given, when, then } = (await request.json()) as { given: string; when: string; then: string }
        if (![given, when, then].every((s) => s?.trim())) return fail(422, 'Fill in Given, When and Then.')
        Object.assign(c, { given: given.trim(), when: when.trim(), then: then.trim() })
        save()
        return HttpResponse.json({ id: c.id, given: c.given, when: c.when, then: c.then })
      }),
    ),
    http.post(
      u('/projects/:project_id/tests/step-jobs'),
      authed(async ({ email, params, request }) => {
        const p = ownedProject(email, params.project_id)
        if (!p) return notFound()
        const refused = consentRequired(email)
        if (refused) return refused
        const asked = ((await request.json()) as { case_ids?: string[] }).case_ids
        const kept = T().cases.filter((c) => c.project_id === p.id && c.status === 'draft' && c.kept && (!asked || asked.includes(c.id)))
        if (!kept.length) return fail(409, 'There are no kept draft cases to write steps for.')
        if (activeTestJob(p.id)) return fail(409, BUSY)
        const job = createJob(p.id, 'test_steps', { payload: JSON.stringify(kept.map((c) => c.id)), progress: { step: 0, total: 2, label: 'Queued' } })
        return HttpResponse.json(publicJob(job), { status: 202 })
      }),
    ),

    http.get(
      u('/projects/:project_id/tests/cases'),
      authed(({ email, params }) => {
        const p = ownedProject(email, params.project_id)
        if (p) cascade(p.id)
        if (!p) return notFound()
        return HttpResponse.json(
          T()
            .cases.filter((c) => c.project_id === p.id)
            .sort((a, b) => a.number.localeCompare(b.number))
            .map(caseView),
        )
      }),
    ),
    http.post(
      u('/projects/:project_id/tests/cases'),
      authed(async ({ email, params, request }) => {
        const p = ownedProject(email, params.project_id)
        if (!p) return notFound()
        const b = (await request.json()) as { statement_id: string; title: string; kind: CaseKind; priority: CasePriority; preconditions?: string[]; steps: string[]; expected: string }
        const st = statementOf(p.id, b.statement_id)
        if (!st) return fail(422, 'Pick the requirement this case tests.')
        if (!b.title?.trim() || !b.expected?.trim() || !b.steps?.some((s) => s.trim())) return fail(422, 'A case needs a title, at least one step and an expected result.')
        if (!KINDS.includes(b.kind) || !PRIORITIES.includes(b.priority)) return fail(422, 'Unknown kind or priority.')
        const row: CaseRow = {
          id: uid('tc'), project_id: p.id, statement_id: st.id, number: nextNumber(p.id), title: b.title.trim(),
          technique: 'Manual', kind: b.kind, priority: b.priority, status: 'ready', kept: true, origin: 'manual',
          outcome: null, test_data: {}, covers: [], preconditions: (b.preconditions ?? []).filter((s) => s.trim()),
          steps: b.steps.filter((s) => s.trim()), expected: b.expected.trim(), created_at: now(), text_at_generation: st.text,
        }
        T().cases.push(row)
        save()
        return HttpResponse.json(caseView(row), { status: 201 })
      }),
    ),
    http.patch(
      u('/projects/:project_id/tests/cases/:case_id'),
      authed(async ({ email, params, request }) => {
        const p = ownedProject(email, params.project_id)
        const c = p && T().cases.find((x) => x.id === params.case_id && x.project_id === p.id)
        if (!p || !c) return notFound()
        const b = (await request.json()) as Partial<Pick<TestCase, 'kept' | 'title' | 'priority' | 'preconditions' | 'steps' | 'expected'>>
        if (c.status === 'draft' && Object.keys(b).some((k) => k !== 'kept'))
          return fail(409, 'A draft can only be kept or discarded. Write its steps first, then edit the case.')
        if (b.title !== undefined && !b.title.trim()) return fail(422, 'A case needs a title.')
        if (b.priority !== undefined && !PRIORITIES.includes(b.priority)) return fail(422, 'Unknown priority.')
        Object.assign(c, b)
        save()
        return HttpResponse.json(caseView(c))
      }),
    ),

    http.get(
      u('/projects/:project_id/tests/runs'),
      authed(({ email, params }) => {
        const p = ownedProject(email, params.project_id)
        if (p) cascade(p.id)
        if (!p) return notFound()
        return HttpResponse.json(
          T()
            .runs.filter((r) => r.project_id === p.id)
            .sort((a, b) => b.created_at.localeCompare(a.created_at))
            .map(runSummary),
        )
      }),
    ),
    // Before /runs/:run_id, which would otherwise match "selection".
    http.get(
      u('/projects/:project_id/tests/runs/selection'),
      authed(({ email, params }) => {
        const p = ownedProject(email, params.project_id)
        if (p) cascade(p.id)
        return p ? HttpResponse.json(selection(p.id)) : notFound()
      }),
    ),
    http.post(
      u('/projects/:project_id/tests/runs'),
      authed(async ({ email, params, request }) => {
        const p = ownedProject(email, params.project_id)
        if (!p) return notFound()
        const b = (await request.json()) as { name?: string; mode?: RunMode; case_ids?: string[] }
        const name = (b.name ?? '').trim()
        if (!name || name.length > 100) return fail(422, 'Give the run a name of 1–100 characters.')
        if (!b.mode || !MODES.includes(b.mode)) return fail(422, 'Unknown run mode.')
        let ids: string[]
        if (b.mode === 'pick') {
          const ready = new Set(T().cases.filter((c) => c.project_id === p.id && c.status === 'ready' && c.kept).map((c) => c.id))
          ids = (b.case_ids ?? []).filter((id) => ready.has(id))
        } else ids = selection(p.id)[b.mode].case_ids
        if (!ids.length) return fail(422, 'This selection has no ready cases.')
        const run: RunRow = { id: uid('run'), project_id: p.id, name, mode: b.mode, case_ids: ids, created_by: email, created_at: now(), finished_at: null }
        T().runs.push(run)
        save()
        return HttpResponse.json(runView(run), { status: 201 })
      }),
    ),
    http.get(
      u('/projects/:project_id/tests/runs/:run_id'),
      authed(({ email, params }) => {
        const p = ownedProject(email, params.project_id)
        if (p) cascade(p.id)
        const run = p && T().runs.find((r) => r.id === params.run_id && r.project_id === p.id)
        return run ? HttpResponse.json(runView(run)) : notFound()
      }),
    ),
    http.put(
      u('/projects/:project_id/tests/runs/:run_id/results/:case_id'),
      authed(async ({ email, params, request }) => {
        const p = ownedProject(email, params.project_id)
        const run = p && T().runs.find((r) => r.id === params.run_id && r.project_id === p.id)
        if (!p || !run || !run.case_ids.includes(String(params.case_id))) return notFound()
        if (run.finished_at) return fail(409, 'This run is finished. Start a new run to test again.')
        const b = (await request.json()) as { status?: ResultStatus; note?: string | null }
        if (!b.status || !RESULTS.includes(b.status)) return fail(422, 'Mark the case Pass, Fail, Blocked or Skipped.')
        const t = T()
        t.results = t.results.filter((r) => !(r.run_id === run.id && r.case_id === params.case_id))
        const row: ResultRow = {
          run_id: run.id, case_id: String(params.case_id), project_id: p.id, status: b.status,
          note: b.note?.trim() || null, marked_by: email, marked_at: now(),
        }
        t.results.push(row)
        save()
        return HttpResponse.json({ case_id: row.case_id, status: row.status, note: row.note, marked_by: row.marked_by, marked_at: row.marked_at })
      }),
    ),
    http.post(
      u('/projects/:project_id/tests/runs/:run_id/finish'),
      authed(({ email, params }) => {
        const p = ownedProject(email, params.project_id)
        const run = p && T().runs.find((r) => r.id === params.run_id && r.project_id === p.id)
        if (!run) return notFound()
        run.finished_at ??= now()
        save()
        return HttpResponse.json(runView(run))
      }),
    ),
  ]
}
