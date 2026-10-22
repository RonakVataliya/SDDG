/** MOCK ONLY. Mirrors the backend's routers/layout.py (#37): positions are kept per version, lines come from the model by element id. */
import type { DiagramLayout } from '@/api/client'
import type { DiagramRow } from './db'

export function layoutView(d: DiagramRow): DiagramLayout {
  const m = d.model
  const nodes = m
    ? [...m.actors.map((a) => ({ id: a.id, kind: 'actor', label: a.name })), ...m.cases.map((c) => ({ id: c.id, kind: 'use_case', label: c.name }))]
    : []
  const saved = d.layout ?? {}
  const elements = nodes.map((n, i) => {
    const [x, y] = saved[n.id] ?? [120 + (i % 4) * 220, 100 + Math.floor(i / 4) * 150] // default: a simple grid, as the backend does
    return { ...n, x, y }
  })
  const ids = new Set(nodes.map((n) => n.id))
  const lines = (m?.links ?? [])
    .filter((l) => ids.has(l.actor) && ids.has(l.case))
    .map((l) => ({ id: `${l.actor}-${l.case}`, kind: 'association', source: l.actor, target: l.case }))
  return { diagram_id: d.id, type: d.type, saved: Object.keys(saved).length > 0, elements, lines }
}
