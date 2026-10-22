import { useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react'
import type { LayoutElement, LayoutLine, Point } from '@/api/client'
import { cn } from '@/lib/utils'
import { bends, boundsOf, boxFor, LINE_H, lineLook, route, selfLoop, union, type Box, type Rect } from './layout-geometry'

const KEY_STEP = 10
const KEY_STEP_BIG = 50
const ARROWS: Record<string, Point> = { ArrowLeft: { x: -1, y: 0 }, ArrowRight: { x: 1, y: 0 }, ArrowUp: { x: 0, y: -1 }, ArrowDown: { x: 0, y: 1 } }

/** Client (screen) coordinates to drawing coordinates. Without a screen matrix (jsdom) they are taken as equal. */
function toDrawing(svg: SVGSVGElement, clientX: number, clientY: number): Point {
  const m = svg.getScreenCTM?.()
  if (!m) return { x: clientX, y: clientY }
  const p = new DOMPoint(clientX, clientY).matrixTransform(m.inverse())
  return { x: p.x, y: p.y }
}

/**
 * A diagram drawn in the browser from element positions (issue #37). With `onMove` the elements can be dragged
 * (shift-click picks several) or moved with the arrow keys; without it the drawing is read-only.
 */
export function LayoutCanvas({
  elements,
  lines,
  positions,
  onMove,
  label,
  className,
}: {
  elements: LayoutElement[]
  lines: LayoutLine[]
  positions: Record<string, Point>
  onMove?: (ids: string[], dx: number, dy: number) => void
  label: string
  className?: string
}) {
  const svgRef = useRef<SVGSVGElement>(null)
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set())
  const [drag, setDrag] = useState<{ ids: string[]; last: Point; pointerId: number; view: Rect } | null>(null)
  const editable = !!onMove

  const boxes = useMemo(() => new Map<string, Box>(elements.map((e) => [e.id, boxFor(e.kind, e.label)])), [elements])
  const placed = elements.map((e) => ({ el: e, box: boxes.get(e.id)!, at: positions[e.id] ?? { x: e.x, y: e.y } }))
  const at = new Map(placed.map((p) => [p.el.id, p.at]))

  // The view only grows: it never shrinks or jumps while an element is being dragged around.
  const [start] = useState<Rect>(() => boundsOf(elements.map((e) => ({ box: boxes.get(e.id)!, at: { x: e.x, y: e.y } }))))
  const view = drag ? drag.view : union(start, boundsOf(placed))

  const offsets = useMemo(() => bends(lines), [lines])

  function pick(id: string, add: boolean): string[] {
    const next = new Set(add ? selected : [])
    if (add && selected.has(id)) next.delete(id)
    else if (add || !selected.has(id)) next.add(id)
    else selected.forEach((s) => next.add(s)) // pressing on a picked element keeps the group, to drag them together
    setSelected(next)
    return [...next]
  }

  function onElementPointerDown(e: PointerEvent, id: string) {
    if (!editable || e.button !== 0) return
    e.stopPropagation()
    e.preventDefault() // no text selection while dragging, so focus is moved by hand for the arrow keys
    const element = e.currentTarget as SVGGElement
    element.focus()
    const ids = pick(id, e.shiftKey)
    if (!ids.includes(id)) return // shift-click took it out of the group
    svgRef.current!.setPointerCapture?.(e.pointerId)
    setDrag({ ids, last: toDrawing(svgRef.current!, e.clientX, e.clientY), pointerId: e.pointerId, view })
  }

  function onPointerMove(e: PointerEvent) {
    if (!drag || e.pointerId !== drag.pointerId) return
    const p = toDrawing(svgRef.current!, e.clientX, e.clientY)
    const dx = p.x - drag.last.x
    const dy = p.y - drag.last.y
    if (!dx && !dy) return
    onMove!(drag.ids, dx, dy)
    setDrag({ ...drag, last: p })
  }

  function endDrag(e: PointerEvent) {
    if (!drag || e.pointerId !== drag.pointerId) return
    svgRef.current!.releasePointerCapture?.(e.pointerId)
    setDrag(null)
  }

  function onElementKeyDown(e: KeyboardEvent, id: string) {
    const dir = ARROWS[e.key]
    if (dir) {
      e.preventDefault()
      const step = e.shiftKey ? KEY_STEP_BIG : KEY_STEP
      // Arrow keys move the picked elements, or the focused one when none are picked.
      onMove!(selected.size ? [...selected] : [id], dir.x * step, dir.y * step)
    } else if (e.key === ' ' || e.key === 'Enter') {
      e.preventDefault()
      pick(id, true)
    } else if (e.key === 'Escape') setSelected(new Set())
  }

  return (
    <svg
      ref={svgRef}
      role="group"
      aria-label={label}
      viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`}
      className={cn('block h-full w-full touch-none select-none', className)}
      fontFamily="inherit"
      onPointerDown={editable ? (e) => !e.shiftKey && setSelected(new Set()) : undefined}
      onPointerMove={editable ? onPointerMove : undefined}
      onPointerUp={editable ? endDrag : undefined}
      onPointerCancel={editable ? endDrag : undefined}
    >
      <defs>
        <marker id="layout-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" orient="auto-start-reverse">
          <path d="M1 1L9 5L1 9" fill="none" className="stroke-ink" strokeWidth="1.4" />
        </marker>
        <marker id="layout-triangle" viewBox="0 0 12 12" refX="11" refY="6" markerWidth="12" markerHeight="12" orient="auto-start-reverse">
          <path d="M1 1L11 6L1 11Z" className="fill-surface stroke-ink" strokeWidth="1.2" />
        </marker>
      </defs>

      <g>
        {lines.map((line) => {
          const from = at.get(line.source)
          const to = at.get(line.target)
          if (!from || !to) return null
          const r =
            line.source === line.target
              ? selfLoop(boxes.get(line.source)!, from, offsets.get(line.id))
              : route(boxes.get(line.source)!, from, boxes.get(line.target)!, to, offsets.get(line.id))
          const look = lineLook(line.kind)
          return (
            <g key={line.id} data-line={line.id} data-source={line.source} data-target={line.target}>
              <path
                d={r.d}
                fill="none"
                className="stroke-ink"
                strokeWidth="1.3"
                strokeDasharray={look.dashed ? '6 4' : undefined}
                markerEnd={look.head === 'none' ? undefined : `url(#layout-${look.head})`}
              />
              {look.label && (
                <text x={r.mid.x} y={r.mid.y - 4} textAnchor="middle" className="fill-slate text-[11px]">
                  {look.label}
                </text>
              )}
            </g>
          )
        })}
      </g>

      {placed.map(({ el, box, at: p }) => {
        const isSelected = selected.has(el.id)
        return (
          <g
            key={el.id}
            data-element={el.id}
            transform={`translate(${p.x} ${p.y})`}
            role={editable ? 'button' : undefined}
            tabIndex={editable ? 0 : undefined}
            aria-label={editable ? `${el.label} (${el.kind.replace(/_/g, ' ')})` : undefined}
            aria-pressed={editable ? isSelected : undefined}
            className={cn(editable && 'cursor-grab focus:outline-none [&:focus-visible_.shape-edge]:stroke-teal', drag && 'cursor-grabbing')}
            onPointerDown={editable ? (e) => onElementPointerDown(e, el.id) : undefined}
            onKeyDown={editable ? (e) => onElementKeyDown(e, el.id) : undefined}
          >
            <ElementShape box={box} selected={isSelected} />
            <ElementText box={box} />
          </g>
        )
      })}
    </svg>
  )
}

function ElementShape({ box, selected }: { box: Box; selected: boolean }) {
  const { w, h } = box
  const cls = cn('shape-edge', selected ? 'fill-teal-wash stroke-teal' : 'fill-surface stroke-ink')
  const sw = selected ? 2.4 : 1.4
  switch (box.shape) {
    case 'actor':
      return (
        <g className={cn('fill-none', selected ? 'stroke-teal' : 'stroke-ink')} strokeWidth={sw} strokeLinecap="round">
          <rect x={-w / 2} y={-h / 2} width={w} height={h} className="shape-edge fill-transparent stroke-transparent" />
          <circle cy={-h / 2 + 8} r="8" />
          <path d={`M0 ${-h / 2 + 16}v18M-12 ${-h / 2 + 24}h24M0 ${-h / 2 + 34}l-10 ${h / 2 - 8}M0 ${-h / 2 + 34}l10 ${h / 2 - 8}`} />
        </g>
      )
    case 'ellipse':
      return <ellipse rx={w / 2} ry={h / 2} className={cls} strokeWidth={sw} />
    case 'diamond':
      return <path d={`M0 ${-h / 2}L${w / 2} 0L0 ${h / 2}L${-w / 2} 0Z`} className={cls} strokeWidth={sw} />
    case 'start':
      return <circle r={w / 2} className={cn('shape-edge', selected ? 'fill-teal stroke-teal' : 'fill-ink stroke-ink')} strokeWidth={sw} />
    case 'end':
      return (
        <g>
          <circle r={w / 2} className={cls} strokeWidth={sw} />
          <circle r={w / 2 - 5} className={selected ? 'fill-teal' : 'fill-ink'} />
        </g>
      )
    case 'store':
      return (
        <g>
          <rect x={-w / 2} y={-h / 2} width={w} height={h} className={cn(cls, 'stroke-transparent')} />
          <path d={`M${w / 2} ${-h / 2}H${-w / 2}V${h / 2}H${w / 2}`} fill="none" className={cn('shape-edge', selected ? 'stroke-teal' : 'stroke-ink')} strokeWidth={sw} />
        </g>
      )
    default:
      return <rect x={-w / 2} y={-h / 2} width={w} height={h} rx={box.shape === 'round' ? 8 : 2} className={cls} strokeWidth={sw} />
  }
}

function ElementText({ box }: { box: Box }) {
  if (box.shape === 'start' || box.shape === 'end') return null
  // An actor's name goes under the figure; everything else is labelled inside.
  const top = box.shape === 'actor' ? box.h / 2 + LINE_H : -((box.text.length - 1) * LINE_H) / 2 + 4.5
  return (
    <text textAnchor="middle" className="pointer-events-none fill-ink text-[13px]">
      {box.text.map((line, i) => (
        <tspan key={i} x="0" y={top + i * LINE_H}>
          {line}
        </tspan>
      ))}
    </text>
  )
}
