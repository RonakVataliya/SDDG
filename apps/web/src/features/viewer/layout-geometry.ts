/**
 * Drawing a diagram from element positions (issue #37). A position is the centre of an element. Lines are worked
 * out from the current positions on every draw, so they follow an element wherever it is moved and always end on
 * the edge of the right two elements.
 */
import type { LayoutLine, Point } from '@/api/client'

export type Shape = 'actor' | 'ellipse' | 'rect' | 'round' | 'store' | 'diamond' | 'start' | 'end'
/** Size of the outline lines attach to; an actor's name is drawn below it. */
export type Box = { shape: Shape; w: number; h: number; text: string[] }

const CHAR_W = 7 // average width of a 13px character
export const LINE_H = 16
const WRAP = 24 // characters per label line

const clamp = (n: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, n))

export function wrapLabel(label: string, width = WRAP): string[] {
  const lines: string[] = []
  let current = ''
  for (const word of label.split(/\s+/).filter(Boolean)) {
    if (current && `${current} ${word}`.length > width) {
      lines.push(current)
      current = word
    } else current = current ? `${current} ${word}` : word
  }
  if (current) lines.push(current)
  return lines.length ? lines : ['']
}

export function shapeOf(kind: string): Shape {
  switch (kind.toLowerCase()) {
    case 'actor':
      return 'actor'
    case 'use_case':
    case 'usecase':
      return 'ellipse'
    case 'start':
    case 'initial':
      return 'start'
    case 'end':
    case 'final':
    case 'stop':
      return 'end'
    case 'decision':
    case 'merge':
    case 'branch':
      return 'diamond'
    case 'data_store':
      return 'store'
    case 'external_entity':
    case 'class':
    case 'interface':
    case 'component':
    case 'participant':
      return 'rect'
    default:
      return 'round'
  }
}

export function boxFor(kind: string, label: string): Box {
  const shape = shapeOf(kind)
  const text = wrapLabel(label)
  const textW = Math.max(...text.map((l) => l.length)) * CHAR_W
  const textH = text.length * LINE_H
  switch (shape) {
    case 'actor':
      return { shape, w: 36, h: 52, text }
    case 'start':
      return { shape, w: 20, h: 20, text }
    case 'end':
      return { shape, w: 24, h: 24, text }
    case 'ellipse':
      return { shape, w: clamp(textW + 48, 120, 260), h: textH + 26, text }
    case 'diamond':
      return { shape, w: clamp(textW + 56, 60, 260), h: textH + 34, text }
    default:
      return { shape, w: clamp(textW + 28, 90, 240), h: textH + 20, text }
  }
}

/** Where the straight line from the centre `c` towards `toward` leaves the element's outline. */
export function edgePoint(box: Box, c: Point, toward: Point): Point {
  const dx = toward.x - c.x
  const dy = toward.y - c.y
  if (!dx && !dy) return c
  const a = box.w / 2
  const b = box.h / 2
  let t: number
  if (box.shape === 'ellipse' || box.shape === 'start' || box.shape === 'end') t = 1 / Math.hypot(dx / a, dy / b)
  else if (box.shape === 'diamond') t = 1 / (Math.abs(dx) / a + Math.abs(dy) / b)
  else t = Math.min(dx ? a / Math.abs(dx) : Infinity, dy ? b / Math.abs(dy) : Infinity)
  return { x: c.x + dx * t, y: c.y + dy * t }
}

/**
 * Sideways offset for each line, so several lines between the same two elements (sequence messages, two-way
 * flows) curve apart instead of lying on top of each other. 0 means straight.
 */
export function bends(lines: LayoutLine[], gap = 28): Map<string, number> {
  const groups = new Map<string, LayoutLine[]>()
  for (const l of lines) {
    const key = [l.source, l.target].sort().join('\u0000')
    groups.set(key, [...(groups.get(key) ?? []), l])
  }
  const out = new Map<string, number>()
  for (const group of groups.values()) {
    group.forEach((l, k) => {
      const offset = l.source === l.target ? k : (k - (group.length - 1) / 2) * gap
      // The sideways direction is taken from the line's own direction, so flip it for one of the two directions.
      out.set(l.id, l.source <= l.target ? offset : -offset)
    })
  }
  return out
}

export type Route = { d: string; start: Point; end: Point; mid: Point }

const r1 = (n: number) => Math.round(n * 10) / 10
const pt = (p: Point) => `${r1(p.x)} ${r1(p.y)}`

/** The path of one line between two placed elements. */
export function route(fromBox: Box, from: Point, toBox: Box, to: Point, bend = 0): Route {
  const dx = to.x - from.x
  const dy = to.y - from.y
  const len = Math.hypot(dx, dy) || 1
  // Control point of a quadratic curve whose middle passes `bend` px to the side of the straight line.
  const ctrl = { x: (from.x + to.x) / 2 + (-dy / len) * bend * 2, y: (from.y + to.y) / 2 + (dx / len) * bend * 2 }
  const start = edgePoint(fromBox, from, bend ? ctrl : to)
  const end = edgePoint(toBox, to, bend ? ctrl : from)
  if (!bend) return { d: `M${pt(start)}L${pt(end)}`, start, end, mid: { x: (start.x + end.x) / 2, y: (start.y + end.y) / 2 } }
  const mid = { x: 0.25 * start.x + 0.5 * ctrl.x + 0.25 * end.x, y: 0.25 * start.y + 0.5 * ctrl.y + 0.25 * end.y }
  return { d: `M${pt(start)}Q${pt(ctrl)} ${pt(end)}`, start, end, mid }
}

/** A line from an element back to itself (a self-message or self-transition): a loop off its top-right corner. */
export function selfLoop(box: Box, c: Point, index = 0): Route {
  const r = 26 + index * 14
  const start = { x: c.x + box.w * 0.2, y: c.y - box.h / 2 }
  const end = { x: c.x + box.w / 2, y: c.y - box.h * 0.1 }
  const d = `M${pt(start)}C${pt({ x: start.x, y: start.y - r * 1.6 })} ${pt({ x: end.x + r * 1.6, y: end.y })} ${pt(end)}`
  return { d, start, end, mid: { x: c.x + box.w / 2 + r * 0.6, y: c.y - box.h / 2 - r * 0.6 } }
}

export type LineLook = { dashed: boolean; head: 'none' | 'arrow' | 'triangle'; label?: string }

export function lineLook(kind: string): LineLook {
  switch (kind.toLowerCase()) {
    case 'include':
      return { dashed: true, head: 'arrow', label: '«include»' }
    case 'extend':
      return { dashed: true, head: 'arrow', label: '«extend»' }
    case 'inheritance':
    case 'generalization':
      return { dashed: false, head: 'triangle' }
    case 'realization':
    case 'implementation':
      return { dashed: true, head: 'triangle' }
    case 'dependency':
      return { dashed: true, head: 'arrow' }
    case 'association':
    case 'aggregation':
    case 'composition':
      return { dashed: false, head: 'none' }
    default: // message, data_flow, flow, transition
      return { dashed: false, head: 'arrow' }
  }
}

export type Rect = { x: number; y: number; w: number; h: number }

/** The area the drawing needs, with a margin, including actor names below the figure. */
export function boundsOf(items: { box: Box; at: Point }[], margin = 40): Rect {
  if (!items.length) return { x: 0, y: 0, w: 400, h: 300 }
  let [x0, y0, x1, y1] = [Infinity, Infinity, -Infinity, -Infinity]
  for (const { box, at } of items) {
    const below = box.shape === 'actor' ? box.text.length * LINE_H + 8 : 0
    const half = box.shape === 'actor' ? Math.max(box.w, Math.max(...box.text.map((l) => l.length)) * CHAR_W) / 2 : box.w / 2
    x0 = Math.min(x0, at.x - half)
    x1 = Math.max(x1, at.x + half)
    y0 = Math.min(y0, at.y - box.h / 2)
    y1 = Math.max(y1, at.y + box.h / 2 + below)
  }
  return { x: x0 - margin, y: y0 - margin, w: x1 - x0 + 2 * margin, h: y1 - y0 + 2 * margin }
}

export function union(a: Rect, b: Rect): Rect {
  const x = Math.min(a.x, b.x)
  const y = Math.min(a.y, b.y)
  return { x, y, w: Math.max(a.x + a.w, b.x + b.w) - x, h: Math.max(a.y + a.h, b.y + b.h) - y }
}
