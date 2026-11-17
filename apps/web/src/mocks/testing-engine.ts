/**
 * MOCK ONLY. A TypeScript copy of the black-box engine (services/ai-extraction/app/testgen/blackbox.py) plus two fake "AI
 * requests", so the Tests screens can be built and tested without the backend or an LLM.
 *
 * The rules match blackbox.py; if they ever disagree, blackbox.py is right and this file should follow it.
 */
import type { BoundaryValue, CaseKind, CasePriority, CaseTechnique, ConditionKind, EquivalenceClass } from '@/api/client'

export type EngineCondition = {
  name: string
  kind: ConditionKind
  min: number | null
  max: number | null
  values: string[]
  invalid_values: string[]
}
export type EngineFlow = { kind: 'basic' | 'alternate'; text: string }
export type EngineTarget = { measure: string; limit: number; unit: string; load: string | null }
export type EngineCriterion = { given: string; when: string; then: string }

export type DraftCase = {
  title: string
  technique: CaseTechnique
  kind: CaseKind
  priority: CasePriority
  outcome: 'accepted' | 'rejected' | null
  test_data: Record<string, string | number>
  covers: string[]
}

export const fmt = (n: number) => (Number.isInteger(n) ? String(n) : String(Number(n.toFixed(6))))

const decimals = (n: number) => (Number.isInteger(n) ? 0 : (String(n).split('.')[1] ?? '').length)

/** Smallest step between two values of a range: 1 for whole numbers, else 10^-decimals (2.5–9.75 -> 0.01). */
function stepOf(c: EngineCondition) {
  const d = Math.max(decimals(c.min ?? 0), decimals(c.max ?? 0))
  return d === 0 ? 1 : 10 ** -d
}

const round = (n: number) => Number(n.toFixed(6))

/** Equivalence classes: a range gives 1 valid + 2 invalid classes; a count cannot go below zero, so it only gets an
 *  invalid class above its limit (and below it when the limit is above zero); a set gives one valid class per value
 *  plus its invalid values. */
export function classesFor(c: EngineCondition): EquivalenceClass[] {
  if (c.kind === 'set') {
    const invalid = c.invalid_values.length ? c.invalid_values : ['any other value']
    return [...c.values.map((v) => ({ label: v, valid: true })), ...invalid.map((v) => ({ label: v, valid: false }))]
  }
  const lo = c.kind === 'count' ? (c.min ?? 0) : c.min
  const hi = c.max
  const out: EquivalenceClass[] = []
  if (lo !== null && hi !== null) out.push({ label: `${fmt(lo)}–${fmt(hi)}`, valid: true })
  else if (lo !== null) out.push({ label: `≥ ${fmt(lo)}`, valid: true })
  else if (hi !== null) out.push({ label: `≤ ${fmt(hi)}`, valid: true })
  if (lo !== null && (c.kind === 'range' || lo > 0)) out.push({ label: `< ${fmt(lo)}`, valid: false })
  if (hi !== null) out.push({ label: `> ${fmt(hi)}`, valid: false })
  return out
}

/** Boundary values. A range gets min-1, min, min+1, max-1, max, max+1. A count gets min (and min-1 when min > 0),
 *  max and max+1: counts are small, so the inner neighbours repeat values already covered. */
export function boundariesFor(c: EngineCondition): BoundaryValue[] {
  if (c.kind === 'set') return []
  const s = stepOf(c)
  const lo = c.kind === 'count' ? (c.min ?? 0) : c.min
  const hi = c.max
  const values: number[] = []
  if (c.kind === 'range') {
    if (lo !== null) values.push(lo - s, lo, lo + s)
    if (hi !== null) values.push(hi - s, hi, hi + s)
  } else {
    if (lo !== null) values.push(...(lo > 0 ? [lo - 1, lo] : [lo]))
    if (hi !== null) values.push(hi, hi + 1)
  }
  const unique = [...new Set(values.map(round))].sort((a, b) => a - b)
  return unique.map((v) => ({ value: v, valid: (lo === null || v >= lo) && (hi === null || v <= hi) }))
}

/** A typical valid value: the middle of a range/count (rounded down), the first value of a set. */
export function nominal(c: EngineCondition): string | number {
  if (c.kind === 'set') return c.values[0] ?? ''
  const lo = c.kind === 'count' ? (c.min ?? 0) : c.min
  const hi = c.max
  if (lo !== null && hi !== null) {
    const s = stepOf(c)
    return round(lo + Math.floor((hi - lo) / 2 / s) * s)
  }
  return lo ?? hi ?? 0
}

/** Draft cases (single-fault assumption: one invalid or boundary value per case, every other input valid):
 *  - valid classes combined into a few positive cases, one per value of the largest set;
 *  - one case per boundary value (an out-of-range boundary also stands for its invalid class: BVA+EC);
 *  - one case per invalid set value;
 *  - one case per flow and per performance target;
 *  - only when none of those exist, one case per acceptance criterion. */
export function buildDrafts(
  conditions: EngineCondition[],
  flows: EngineFlow[],
  targets: EngineTarget[],
  criteria: EngineCriterion[],
): DraftCase[] {
  const drafts: DraftCase[] = []
  const base: Record<string, string | number> = Object.fromEntries(conditions.map((c) => [c.name, nominal(c)]))
  const sets = conditions.filter((c) => c.kind === 'set' && c.values.length)
  const positives = sets.length ? Math.max(...sets.map((c) => c.values.length)) : conditions.length ? 1 : 0

  for (let i = 0; i < positives; i++) {
    const data = { ...base }
    for (const c of sets) data[c.name] = c.values[i % c.values.length]
    const picked = sets.map((c) => String(data[c.name]))
    drafts.push({
      title: `Valid values${picked.length ? `, ${picked.join(', ')}` : ''} → accepted`,
      technique: 'EC',
      kind: 'positive',
      priority: 'high',
      outcome: 'accepted',
      test_data: data,
      covers: conditions.map((c) => `EC:${c.name}:${c.kind === 'set' ? data[c.name] : 'valid'}`),
    })
  }

  for (const c of conditions) {
    if (c.kind === 'set') continue
    const lo = c.kind === 'count' ? (c.min ?? 0) : c.min
    for (const b of boundariesFor(c)) {
      const data = { ...base, [c.name]: b.value }
      if (b.valid) {
        drafts.push({
          title: `${c.name} = ${fmt(b.value)} → accepted`,
          technique: 'BVA',
          kind: 'edge',
          priority: 'medium',
          outcome: 'accepted',
          test_data: data,
          covers: [`BVA:${c.name}:${fmt(b.value)}`],
        })
      } else {
        const below = lo !== null && b.value < lo
        drafts.push({
          title: `${c.name} = ${fmt(b.value)} (${below ? `below ${fmt(lo!)}` : `above ${fmt(c.max!)}`}) → rejected`,
          technique: 'BVA+EC',
          kind: 'negative',
          priority: 'medium',
          outcome: 'rejected',
          test_data: data,
          covers: [`EC:${c.name}:${below ? 'low' : 'high'}`, `BVA:${c.name}:${fmt(b.value)}`],
        })
      }
    }
  }

  for (const c of sets) {
    for (const bad of c.invalid_values) {
      drafts.push({
        title: `${c.name} = ${bad} (not in the set) → rejected`,
        technique: 'EC',
        kind: 'negative',
        priority: 'medium',
        outcome: 'rejected',
        test_data: { ...base, [c.name]: bad },
        covers: [`EC:${c.name}:invalid`],
      })
    }
  }

  for (const f of flows) {
    drafts.push({
      title: `${f.kind === 'basic' ? 'Basic flow' : 'Alternate'}: ${f.text}`,
      technique: 'Flow',
      kind: f.kind === 'basic' ? 'positive' : 'negative',
      priority: f.kind === 'basic' ? 'high' : 'medium',
      outcome: null,
      test_data: {},
      covers: [`Flow:${f.kind}`],
    })
  }

  for (const t of targets) {
    drafts.push({
      title: `Performance: ${t.measure} < ${fmt(t.limit)} ${t.unit}${t.load ? ` with ${t.load}` : ''}`,
      technique: 'NFR',
      kind: 'positive',
      priority: 'medium',
      outcome: null,
      test_data: { limit: `${fmt(t.limit)} ${t.unit}`, ...(t.load ? { load: t.load } : {}) },
      covers: [`NFR:${t.measure}`],
    })
  }

  if (!drafts.length) {
    criteria.forEach((c, i) =>
      drafts.push({
        title: `${c.when} → ${c.then}`,
        technique: 'AC',
        kind: 'positive',
        priority: 'high',
        outcome: null,
        test_data: {},
        covers: [`AC:${i + 1}`],
      }),
    )
  }
  return drafts
}

/* ---------- fake AI request 1: a rough reading of the requirement text, good enough for a demo ---------- */

const VAGUE = /\b(fast|quick(ly)?|user-friendly|intuitive|easy to use|responsive|efficient(ly)?)\b/i
const slug = (s: string) =>
  s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_|_$/g, '')

export function isVague(text: string) {
  return VAGUE.test(text)
}

export type FakeDesign = {
  testable: boolean
  question: string | null
  suggestion_template: string | null
  criteria: EngineCriterion[]
  conditions: (EngineCondition & { description: string; unit: string | null })[]
  flows: EngineFlow[]
  targets: EngineTarget[]
}

export function fakeCriteria(text: string): FakeDesign {
  const vague = text.match(VAGUE)
  if (vague) {
    return {
      testable: false,
      question: `What counts as “${vague[0]}”, and under what load? Give a number a tester can measure.`,
      suggestion_template: text.replace(VAGUE, '{answer}'),
      criteria: [],
      conditions: [],
      flows: [],
      targets: [],
    }
  }
  const conditions: FakeDesign['conditions'] = []
  for (const m of text.matchAll(/(\d+(?:\.\d+)?)\s*(?:to|-|–)\s*(\d+(?:\.\d+)?)\s+([a-z]+(?:\s[a-z]+)?)/gi)) {
    const words = m[3].toLowerCase()
    const name = words.startsWith('character') ? 'length' : slug(words)
    conditions.push({ name, kind: 'range', min: Number(m[1]), max: Number(m[2]), values: [], invalid_values: [], description: words, unit: null })
  }
  for (const m of text.matchAll(/at most (\d+)\s+([a-z]+(?:\s[a-z]+)?)/gi)) {
    conditions.push({ name: slug(m[2]), kind: 'count', min: 0, max: Number(m[1]), values: [], invalid_values: [], description: m[2], unit: null })
  }
  const list = text.match(/([A-Z][\w-]*), ([A-Z][\w-]*),? (?:or|and) ([A-Z][\w-]*)/)
  if (list) {
    conditions.push({ name: 'type', kind: 'set', min: null, max: null, values: [list[1], list[2], list[3]], invalid_values: ['Other'], description: 'type', unit: null })
  }
  const target = text.match(/(?:under|within|less than)\s+(\d+(?:\.\d+)?)\s*(seconds?|s|ms|minutes?)(?:\s+with\s+([^.,]+))?/i)
  const action = text.replace(/\.$/, '')
  return {
    testable: true,
    question: null,
    suggestion_template: null,
    criteria: [
      { given: 'a signed-in user with valid data', when: action.charAt(0).toLowerCase() + action.slice(1), then: 'the system completes it and shows the result' },
      ...(conditions.length ? [{ given: 'a signed-in user', when: 'they enter a value outside the allowed limits', then: 'the system refuses it and explains why' }] : []),
    ],
    conditions,
    flows: [
      { kind: 'basic', text: `The user does what ${action.length > 60 ? 'the requirement' : `"${action}"`} describes; it succeeds.` },
      { kind: 'alternate', text: 'An input is invalid; the user is told what to fix.' },
    ],
    targets: target ? [{ measure: 'response time', limit: Number(target[1]), unit: target[2].startsWith('s') ? 's' : target[2], load: target[3]?.trim() ?? null }] : [],
  }
}

/* ---------- fake AI request 2 ---------- */

export function fakeSteps(c: { title: string; statement_ref: string; test_data: Record<string, string | number>; outcome: string | null }) {
  const data = Object.entries(c.test_data)
  return {
    preconditions: ['The tester is signed in with a test account', 'The test data below exists'],
    steps: [
      `Open the screen ${c.statement_ref} describes`,
      ...(data.length ? [`Enter ${data.map(([k, v]) => `${k} = ${v}`).join(', ')}`] : [`Follow the case: ${c.title}`]),
      'Submit',
    ],
    expected:
      c.outcome === 'rejected'
        ? 'The system refuses the input and shows a message saying what is allowed. Nothing is saved.'
        : 'The system accepts the input, saves it and shows the result.',
  }
}
