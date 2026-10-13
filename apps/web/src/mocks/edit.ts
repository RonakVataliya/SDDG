/**
 * MOCK ONLY. Stands in for the backend's LLM diagram edit. Understands a few plain-language commands:
 *   rename / change / edit A to B · remove A · add actor A · add use case A [for Actor] · connect Actor to A
 * Anything else is rejected with a hint, which is how the UI's 422 path gets exercised.
 */
import { uid } from './db'
import type { UseCaseModel } from './render'

export type EditResult = { ok: true; model: UseCaseModel } | { ok: false; detail: string }

const HINT = 'Try something like “rename Browse canteen menu to Browse menu card”, “remove Log in” or “add use case Rate a dish for Student”.'

const norm = (s: string) => s.toLowerCase().replace(/\s+/g, ' ').trim()

/** Strips the words people wrap around a name: quotes, "the", "use case", a trailing full stop. */
function clean(raw: string) {
  return raw
    .trim()
    .replace(/[.!]+$/, '')
    .replace(/^["“'‘]|["”'’]$/g, '')
    .replace(/^the\s+/i, '')
    .replace(/\s+(use case|usecase|actor|oval|bubble|box)$/i, '')
    .replace(/^(use case|usecase|actor)\s+/i, '')
    .replace(/^["“'‘]|["”'’]$/g, '')
    .trim()
}

const titleCase = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

type Found = { kind: 'actor' | 'case'; id: string; name: string }

function find(model: UseCaseModel, raw: string, exactOnly = false): Found | null {
  const q = norm(clean(raw))
  if (!q) return null
  const all: Found[] = [
    ...model.actors.map((a) => ({ kind: 'actor' as const, id: a.id, name: a.name })),
    ...model.cases.map((c) => ({ kind: 'case' as const, id: c.id, name: c.name })),
  ]
  const exact = all.find((e) => norm(e.name) === q)
  if (exact || exactOnly) return exact ?? null
  const partial = all.filter((e) => norm(e.name).includes(q) || q.includes(norm(e.name)))
  return partial.length === 1 ? partial[0] : null
}

/** "A to B" where A may itself contain the separator ("Add to cart to Add to basket"): try each split point. */
function splitOn(text: string, separators: RegExp, isLeft: (left: string) => boolean): [string, string] | null {
  for (const m of text.matchAll(separators)) {
    const left = text.slice(0, m.index)
    const right = text.slice(m.index! + m[0].length)
    if (right.trim() && isLeft(left)) return [left, right]
  }
  return null
}

/** Splits so the left side names an element, preferring an exact name over a partial one. */
const splitAtElement = (model: UseCaseModel, text: string, separators: RegExp) =>
  splitOn(text, separators, (left) => !!find(model, left, true)) ?? splitOn(text, separators, (left) => !!find(model, left))

export function applyInstruction(model: UseCaseModel, instruction: string): EditResult {
  const text = instruction.trim().replace(/^(please|can you|could you)\s+/i, '')
  const next: UseCaseModel = structuredClone(model)

  let m = text.match(/^(?:rename|change|edit|replace|update|call)\s+(.+)$/i)
  if (m) {
    const parts = splitAtElement(next, m[1], /\s+(?:to|into|as|with)\s+/gi)
    if (!parts) return { ok: false, detail: `I couldn't find that element in the diagram. ${HINT}` }
    const target = find(next, parts[0])!
    const name = titleCase(clean(parts[1]))
    if (!name) return { ok: false, detail: `What should “${target.name}” be called instead? ${HINT}` }
    const list = target.kind === 'actor' ? next.actors : next.cases
    list.find((e) => e.id === target.id)!.name = name
    return { ok: true, model: next }
  }

  m = text.match(/^(?:remove|delete|drop|get rid of)\s+(.+)$/i)
  if (m) {
    const target = find(next, m[1])
    if (!target) return { ok: false, detail: `I couldn't find “${clean(m[1])}” in the diagram. ${HINT}` }
    if (target.kind === 'actor') next.actors = next.actors.filter((a) => a.id !== target.id)
    else next.cases = next.cases.filter((c) => c.id !== target.id)
    next.links = next.links.filter((l) => l.actor !== target.id && l.case !== target.id)
    return { ok: true, model: next }
  }

  m = text.match(/^add\s+(?:an?\s+|new\s+)*actor\s+(?:called\s+|named\s+)?(.+)$/i)
  if (m) {
    next.actors.push({ id: uid('act'), name: titleCase(clean(m[1])) })
    return { ok: true, model: next }
  }

  m = text.match(/^add\s+(?:an?\s+|new\s+)*(?:use\s*case\s+)?(?:called\s+|named\s+)?(.+)$/i)
  if (m) {
    const withActor = splitOn(m[1], /\s+for\s+/gi, () => true)
    const actor = withActor ? find(next, withActor[1]) : null
    const name = titleCase(clean(actor ? withActor![0] : m[1]))
    if (!name) return { ok: false, detail: HINT }
    const id = uid('uc')
    next.cases.push({ id, name, assumed: false })
    if (actor?.kind === 'actor') next.links.push({ actor: actor.id, case: id })
    return { ok: true, model: next }
  }

  m = text.match(/^(?:connect|link|associate)\s+(.+)$/i)
  if (m) {
    const parts = splitAtElement(next, m[1], /\s+(?:to|with|and)\s+/gi)
    const a = parts && find(next, parts[0])
    const b = parts && find(next, parts[1])
    const actor = [a, b].find((e) => e?.kind === 'actor')
    const useCase = [a, b].find((e) => e?.kind === 'case')
    if (!actor || !useCase) return { ok: false, detail: `Name one actor and one use case to connect. ${HINT}` }
    if (!next.links.some((l) => l.actor === actor.id && l.case === useCase.id)) next.links.push({ actor: actor.id, case: useCase.id })
    return { ok: true, model: next }
  }

  return { ok: false, detail: `I didn't understand that change. ${HINT}` }
}
