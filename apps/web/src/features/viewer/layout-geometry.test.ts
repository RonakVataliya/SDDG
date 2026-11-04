import { bends, boxFor, edgePoint, route, selfLoop, wrapLabel } from './layout-geometry'

const onEllipse = (p: { x: number; y: number }, c: { x: number; y: number }, w: number, h: number) =>
  ((p.x - c.x) / (w / 2)) ** 2 + ((p.y - c.y) / (h / 2)) ** 2

describe('#37 layout geometry', () => {
  const actor = boxFor('actor', 'Librarian')
  const useCase = boxFor('use_case', 'Issue book')

  it('wraps long labels and sizes the shape to fit', () => {
    expect(wrapLabel('Browse the full canteen menu for today')).toEqual(['Browse the full canteen', 'menu for today'])
    expect(boxFor('use_case', 'Browse the full canteen menu for today').h).toBeGreaterThan(useCase.h)
  })

  it('ends a line on the outline of an ellipse and of a box, not at the centre', () => {
    const c = { x: 100, y: 100 }
    expect(onEllipse(edgePoint(useCase, c, { x: 400, y: 160 }), c, useCase.w, useCase.h)).toBeCloseTo(1)
    const p = edgePoint(actor, c, { x: 100, y: -300 })
    expect(p).toEqual({ x: 100, y: 100 - actor.h / 2 })
  })

  it('reroutes a line when either end moves, keeping both ends on the right elements', () => {
    const a = { x: 120, y: 100 }
    const before = route(actor, a, useCase, { x: 340, y: 100 })
    const b = { x: 340, y: 400 }
    const after = route(actor, a, useCase, b)
    expect(after.d).not.toBe(before.d)
    expect(onEllipse(after.end, b, useCase.w, useCase.h)).toBeCloseTo(1)
    expect(after.start.y).toBeGreaterThan(a.y) // leaves the actor towards the use case, now below it
  })

  it('curves several lines between the same two elements apart, whichever way they point', () => {
    const lines = [
      { id: 'm1', kind: 'message', source: 'a', target: 'b' },
      { id: 'm2', kind: 'message', source: 'b', target: 'a' },
      { id: 'm3', kind: 'message', source: 'a', target: 'b' },
    ]
    const offsets = bends(lines)
    const box = boxFor('participant', 'X')
    const at = { a: { x: 0, y: 0 }, b: { x: 300, y: 0 } }
    const paths = lines.map((l) => route(box, at[l.source as 'a'], box, at[l.target as 'b'], offsets.get(l.id)))
    expect(new Set(paths.map((p) => Math.round(p.mid.y))).size).toBe(3)
    expect(bends([{ id: 'one', kind: 'flow', source: 'a', target: 'b' }]).get('one')).toBe(0)
  })

  it('draws a line from an element to itself as a loop', () => {
    const box = boxFor('state', 'Waiting')
    const loop = selfLoop(box, { x: 0, y: 0 })
    expect(loop.d).toMatch(/^M.*C/)
    expect(loop.start).not.toEqual(loop.end)
  })
})
