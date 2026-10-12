/**
 * MOCK ONLY. Stands in for DG's Kroki renderer (X12). The real backend returns a still PNG, so the mock builds a small
 * model, draws it as SVG, and the export handler rasterises that SVG. Edits (mocks/edit.ts) change the model and redraw.
 */
import type { ExtractedItem } from '@/api/client'

export type UseCaseModel = {
  system: string
  actors: { id: string; name: string }[]
  /** `assumed`: no requirement mentions it (DR2a), drawn dashed amber. */
  cases: { id: string; name: string; assumed: boolean }[]
  links: { actor: string; case: string }[]
}

const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]!)

export function buildUseCaseModel(items: ExtractedItem[], systemName: string): UseCaseModel {
  const actors = items.filter((i) => i.category === 'actor')
  const rels = items.filter((i) => i.category === 'relationship' && i.relation_type === 'association')
  const linkedProcessIds = new Set(rels.map((r) => r.target_item_id))
  const useCases = items.filter((i) => i.category === 'process' && (linkedProcessIds.has(i.id) || i.statement_ids.length > 0))
  return {
    system: systemName,
    actors: actors.map((a) => ({ id: a.id, name: a.name })),
    // An LLM typically adds "Log in" even when no requirement mentions it: exactly what DR2a must expose.
    cases: [...useCases.map((u) => ({ id: u.id, name: u.name, assumed: false })), { id: 'assumed-login', name: 'Log in', assumed: true }],
    links: rels
      .filter((r) => r.source_item_id && r.target_item_id && useCases.some((u) => u.id === r.target_item_id))
      .map((r) => ({ actor: r.source_item_id!, case: r.target_item_id! })),
  }
}

export function renderUseCase(model: UseCaseModel): string {
  const { actors, cases } = model
  const ROW = 64
  const boxX = 220
  const boxW = 360
  const top = 60
  const height = Math.max(cases.length, actors.length, 1) * ROW + 60
  const width = boxX + boxW + 60
  const cx = boxX + boxW / 2
  const caseY = new Map(cases.map((c, i) => [c.id, top + 30 + i * ROW]))
  const actorY = new Map(actors.map((a, i) => [a.id, top + 10 + ((i + 0.5) * (height - 80)) / Math.max(actors.length, 1)]))

  const parts: string[] = []
  model.links.forEach((l) => {
    const ay = actorY.get(l.actor)
    const cy = caseY.get(l.case)
    if (ay == null || cy == null) return
    parts.push(`<line x1="88" y1="${ay + 22}" x2="${cx - 140}" y2="${cy}" stroke="#1a2233" stroke-width="1.2"/>`)
  })
  parts.push(
    `<rect x="${boxX}" y="${top - 20}" width="${boxW}" height="${height}" rx="6" fill="none" stroke="#1a2233" stroke-width="1.4"/>` +
      `<text x="${cx}" y="${top}" text-anchor="middle" font-size="14" font-weight="600" fill="#1a2233">${esc(model.system)}</text>`,
  )
  cases.forEach((c) => {
    const y = caseY.get(c.id)!
    const stroke = c.assumed ? 'stroke="#b26b00" stroke-dasharray="5 4"' : 'stroke="#1a2233"'
    parts.push(
      `<ellipse cx="${cx}" cy="${y}" rx="140" ry="22" fill="#ffffff" ${stroke} stroke-width="1.4"/>` +
        `<text x="${cx}" y="${y + 5}" text-anchor="middle" font-size="13" fill="#1a2233">${esc(c.name)}</text>`,
    )
  })
  actors.forEach((a) => {
    const y = actorY.get(a.id)!
    const x = 70
    parts.push(
      `<g stroke="#1a2233" stroke-width="1.4" fill="none" stroke-linecap="round"><circle cx="${x}" cy="${y - 6}" r="8"/>` +
        `<path d="M${x} ${y + 2}v22M${x - 12} ${y + 10}h24M${x} ${y + 24}l-10 16M${x} ${y + 24}l10 16"/></g>` +
        `<text x="${x}" y="${y + 58}" text-anchor="middle" font-size="12" fill="#1a2233">${esc(a.name)}</text>`,
    )
  })

  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height + top}" width="${width}" height="${height + top}" font-family="Helvetica, Arial, sans-serif">` +
    `<rect width="100%" height="100%" fill="#ffffff"/>${parts.join('')}</svg>`
  )
}
