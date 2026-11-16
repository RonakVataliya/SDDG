/**
 * MOCK ONLY. Stands in for DG's Kroki renderer (X12). The real backend returns a still PNG, so the mock builds a small
 * model, draws it as SVG, and the export handler rasterises that SVG. Edits (mocks/edit.ts) change the model and redraw.
 */
import type { ExtractedItem } from '@/api/client'
import type { DiagramStyle } from '@/features/viewer/style'

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

type Palette = { background: string; fill: string; text: string; line: string }

/** The look Sprint 1 drew with; used when no style is given so existing pictures stay the same. */
const SPRINT1: Palette = { background: '#ffffff', fill: '#ffffff', text: '#1a2233', line: '#1a2233' }
const ASSUMED = '#b26b00'

/**
 * Draws the model. With a style (#38) it uses its colours, font size and direction, like the real renderer: boxes
 * grow to fit their labels so a bigger font never clips, and TB puts the actors above the system instead of beside it.
 */
export function renderUseCase(model: UseCaseModel, style?: DiagramStyle): string {
  const { actors, cases } = model
  const c: Palette = style ?? SPRINT1
  const fs = style ? Math.round((style.font_size * 4) / 3) : 13 // pt to px
  const rxFor = (name: string) => (style ? Math.max(140, Math.ceil(name.length * fs * 0.3) + 24) : 140)
  const rx = Math.max(140, ...cases.map((u) => rxFor(u.name)))
  const ry = Math.max(22, Math.round(fs * 1.4))
  const ROW = Math.max(64, ry * 2 + 20)
  const vertical = style?.direction === 'TB'

  const boxW = rx * 2 + 80
  const boxH = Math.max(vertical ? cases.length : Math.max(cases.length, actors.length), 1) * ROW + 60
  const actorGap = Math.max(140, ...actors.map((a) => Math.ceil(a.name.length * (fs - 1) * 0.6) + 20))
  const actorsW = actors.length * actorGap
  const top = 60
  // LR: actors in a column left of the system. TB: actors in a row above it.
  const boxX = vertical ? Math.max(40, (actorsW + 40 - boxW) / 2) : 220
  const boxY = vertical ? top + 120 : top - 20
  const width = vertical ? Math.max(boxX + boxW + 40, actorsW + 40) : boxX + boxW + 60
  const height = boxY + boxH + 20
  const cx = boxX + boxW / 2
  const caseY = new Map(cases.map((u, i) => [u.id, boxY + 28 + ry + i * ROW]))
  const actorAt = new Map(
    actors.map((a, i) =>
      vertical
        ? [a.id, { x: 20 + actorGap * (i + 0.5), y: top }]
        : [a.id, { x: 70, y: top + 10 + ((i + 0.5) * (boxH - 80)) / Math.max(actors.length, 1) }],
    ),
  )

  const parts: string[] = []
  model.links.forEach((l) => {
    const a = actorAt.get(l.actor)
    const cy = caseY.get(l.case)
    if (!a || cy == null) return
    const [x1, y1, x2, y2] = vertical ? [a.x, a.y + 62, cx, cy - ry] : [a.x + 18, a.y + 22, cx - rx, cy]
    parts.push(`<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${c.line}" stroke-width="1.2"/>`)
  })
  parts.push(
    `<rect x="${boxX}" y="${boxY}" width="${boxW}" height="${boxH}" rx="6" fill="none" stroke="${c.line}" stroke-width="1.4"/>` +
      `<text x="${cx}" y="${boxY + 20}" text-anchor="middle" font-size="${fs + 1}" font-weight="600" fill="${c.text}">${esc(model.system)}</text>`,
  )
  cases.forEach((u) => {
    const y = caseY.get(u.id)!
    const stroke = u.assumed ? `stroke="${ASSUMED}" stroke-dasharray="5 4"` : `stroke="${c.line}"`
    parts.push(
      `<ellipse cx="${cx}" cy="${y}" rx="${rx}" ry="${ry}" fill="${c.fill}" ${stroke} stroke-width="1.4"/>` +
        `<text x="${cx}" y="${y + Math.round(fs * 0.38)}" text-anchor="middle" font-size="${fs}" fill="${c.text}">${esc(u.name)}</text>`,
    )
  })
  actors.forEach((a) => {
    const { x, y } = actorAt.get(a.id)!
    parts.push(
      `<g stroke="${c.line}" stroke-width="1.4" fill="none" stroke-linecap="round"><circle cx="${x}" cy="${y - 6}" r="8"/>` +
        `<path d="M${x} ${y + 2}v22M${x - 12} ${y + 10}h24M${x} ${y + 24}l-10 16M${x} ${y + 24}l10 16"/></g>` +
        `<text x="${x}" y="${y + 58}" text-anchor="middle" font-size="${fs - 1}" fill="${c.text}">${esc(a.name)}</text>`,
    )
  })

  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" font-family="Helvetica, Arial, sans-serif">` +
    `<rect width="100%" height="100%" fill="${c.background}"/>${parts.join('')}</svg>`
  )
}
