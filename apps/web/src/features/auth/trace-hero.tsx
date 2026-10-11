import { useLayoutEffect, useRef, useState } from 'react'
import { RefTag } from '@/components/ui/badge'

/**
 * Auth-screen hero: three requirement sentences traced into the Use Case diagram they produce.
 * Traces are routed like wiring: down into the gap under their word, sideways to a gutter lane, down the lane,
 * then into the shape. Use cases are stacked in reverse sentence order so the lanes nest and never cross.
 * "Log in" gets no trace on purpose: it is the generator's guess, shown as an assumption.
 */

type Id = 'librarian' | 'member' | 'register' | 'issue' | 'reserve'
type Part = string | { text: string; id: Id }

const REQUIREMENTS: { ref: string; parts: Part[] }[] = [
  { ref: 'R-001', parts: ['The ', { text: 'librarian', id: 'librarian' }, ' shall ', { text: 'register a member', id: 'register' }, '.'] },
  { ref: 'R-003', parts: ['The ', { text: 'librarian', id: 'librarian' }, ' shall ', { text: 'issue a book', id: 'issue' }, '.'] },
  { ref: 'R-004', parts: ['A ', { text: 'member', id: 'member' }, ' can ', { text: 'reserve a book', id: 'reserve' }, '.'] },
]

/** Gutter lane per trace, in px from that side's edge. Outer lanes serve the traces that span furthest. */
const ROUTE: Record<Id, { side: 'left' | 'right'; lane: number }> = {
  librarian: { side: 'left', lane: 8 },
  member: { side: 'left', lane: 20 },
  register: { side: 'right', lane: 8 },
  issue: { side: 'right', lane: 20 },
  reserve: { side: 'right', lane: 32 },
}

type Trace = { key: string; id: Id; d: string; start: [number, number]; end: [number, number]; order: number }

function roundedPath(pts: [number, number][], radius = 7) {
  let d = `M${pts[0][0]},${pts[0][1]}`
  for (let i = 1; i < pts.length - 1; i++) {
    const [x0, y0] = pts[i - 1]
    const [x1, y1] = pts[i]
    const [x2, y2] = pts[i + 1]
    const d1 = Math.hypot(x1 - x0, y1 - y0)
    const d2 = Math.hypot(x2 - x1, y2 - y1)
    if (d1 === 0 || d2 === 0) continue
    const r = Math.min(radius, d1 / 2, d2 / 2)
    d += ` L${x1 - ((x1 - x0) / d1) * r},${y1 - ((y1 - y0) / d1) * r}`
    d += ` Q${x1},${y1} ${x1 + ((x2 - x1) / d2) * r},${y1 + ((y2 - y1) / d2) * r}`
  }
  const [lx, ly] = pts[pts.length - 1]
  return `${d} L${lx},${ly}`
}

export function TraceHero() {
  const ref = useRef<HTMLDivElement>(null)
  const [traces, setTraces] = useState<Trace[]>([])
  const [size, setSize] = useState({ w: 0, h: 0 })
  const [active, setActive] = useState<Id | null>(null)

  useLayoutEffect(() => {
    const root = ref.current
    if (!root) return
    const measure = () => {
      const c = root.getBoundingClientRect()
      const next: Trace[] = []
      root.querySelectorAll<HTMLElement>('[data-mark]').forEach((mark, order) => {
        const id = mark.dataset.mark as Id
        const anchor = root.querySelector(`[data-anchor="${id}"]`)
        if (!anchor) return
        const m = mark.getBoundingClientRect()
        const a = anchor.getBoundingClientRect()
        const sx = m.left + m.width / 2 - c.left
        const sy = m.bottom - c.top
        const gapY = sy + 14 // middle of the gap under the line
        const ax = a.left + a.width / 2 - c.left
        const ay = a.top + a.height / 2 - c.top
        const { side, lane } = ROUTE[id]
        const laneX = side === 'left' ? lane : c.width - lane
        next.push({
          key: mark.dataset.key!,
          id,
          order,
          start: [sx, sy],
          end: [ax, ay],
          d: roundedPath([[sx, sy], [sx, gapY], [laneX, gapY], [laneX, ay], [ax, ay]]),
        })
      })
      setTraces(next)
      setSize({ w: c.width, h: c.height })
    }
    measure()
    void document.fonts?.ready.then(measure)
    if (typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(measure)
    ro.observe(root)
    return () => ro.disconnect()
  }, [])

  const hover = (target: EventTarget) => {
    const id = (target as Element).closest?.('[data-trace-id]')?.getAttribute('data-trace-id') as Id | null
    setActive(id ?? null)
  }
  const isActive = (id: Id) => (active === id ? 'true' : undefined)

  return (
    <div
      ref={ref}
      role="img"
      aria-label="Example: three requirement sentences traced to the actors and use cases they produce in a Use Case diagram. The Log in use case has no source requirement and is marked as an assumption."
      className="trace-hero relative w-full max-w-[36rem] px-11"
      data-has-active={active ? 'true' : undefined}
      onPointerOver={(e) => hover(e.target)}
      onPointerLeave={() => setActive(null)}
    >
      <svg aria-hidden className="pointer-events-none absolute inset-0 overflow-visible" width={size.w} height={size.h}>
        {traces.map((t) => (
          <g key={t.key} className="th-trace" data-active={isActive(t.id)}>
            <path
              d={t.d}
              pathLength={1}
              fill="none"
              className="th-draw"
              style={{ animationDelay: `${1150 + t.order * 130}ms` }}
            />
            <circle cx={t.start[0]} cy={t.start[1]} r={2.25} className="th-dot" style={{ animationDelay: `${1150 + t.order * 130}ms` }} />
            <circle cx={t.end[0]} cy={t.end[1]} r={2.75} className="th-dot" style={{ animationDelay: `${1900 + t.order * 130}ms` }} />
          </g>
        ))}
      </svg>

      <div aria-hidden className="space-y-7 text-[15px] leading-6 text-ink/85">
        {REQUIREMENTS.map((r, i) => (
          <p key={r.ref} className="th-rise flex items-baseline gap-2.5" style={{ animationDelay: `${i * 120}ms` }}>
            <RefTag className="shrink-0">{r.ref}</RefTag>
            <span>
              {r.parts.map((p, j) =>
                typeof p === 'string' ? (
                  p
                ) : (
                  <span
                    key={j}
                    data-mark={p.id}
                    data-key={`${r.ref}-${p.id}`}
                    data-trace-id={p.id}
                    data-active={isActive(p.id)}
                    className="th-mark rounded-[3px] px-0.5 text-teal-deep"
                    style={{ animationDelay: `${650 + i * 120 + j * 60}ms` }}
                  >
                    {p.text}
                  </span>
                ),
              )}
            </span>
          </p>
        ))}
      </div>

      <UseCaseSketch isActive={isActive} />
    </div>
  )
}

function UseCaseSketch({ isActive }: { isActive: (id: Id) => 'true' | undefined }) {
  const useCases: { id: Id; label: string; cy: number }[] = [
    { id: 'reserve', label: 'Reserve book', cy: 58 },
    { id: 'issue', label: 'Issue book', cy: 106 },
    { id: 'register', label: 'Register member', cy: 154 },
  ]
  const actors: { id: Id; label: string; y: number }[] = [
    { id: 'member', label: 'Member', y: 48 },
    { id: 'librarian', label: 'Librarian', y: 140 },
  ]
  const associations: [number, number][] = [
    [62, 58], // member → reserve
    [154, 106], // librarian → issue
    [154, 154], // librarian → register
  ]

  return (
    <svg aria-hidden viewBox="0 0 400 250" className="mt-12 w-full overflow-visible" style={{ fontFamily: 'var(--font-sans)' }}>
      <g className="th-fade" style={{ animationDelay: '900ms' }}>
        <rect x="100" y="6" width="292" height="238" rx="6" className="th-boundary" />
        <text x="114" y="26" fontSize="11" fontWeight="600" className="fill-slate">
          Library system
        </text>
      </g>
      <g className="th-fade" style={{ animationDelay: '1750ms' }}>
        {associations.map(([y1, y2], i) => (
          <line key={i} x1="58" y1={y1} x2="158" y2={y2} className="th-assoc" />
        ))}
      </g>
      {actors.map((a, i) => (
        <g key={a.id} data-trace-id={a.id} data-active={isActive(a.id)} className="th-shape th-fade" style={{ animationDelay: `${1650 + i * 120}ms` }}>
          <rect x="4" y={a.y - 14} width="80" height="76" fill="transparent" />
          <g className="th-figure">
            <circle cx="44" cy={a.y} r="7" />
            <path d={`M44 ${a.y + 7}v20M32 ${a.y + 14}h24M44 ${a.y + 27}l-8 14M44 ${a.y + 27}l8 14`} />
          </g>
          <text x="44" y={a.y + 56} textAnchor="middle" fontSize="11.5" className="fill-ink">
            {a.label}
          </text>
          <circle data-anchor={a.id} cx="26" cy={a.y + 14} r="0.5" fill="none" />
        </g>
      ))}
      {useCases.map((u, i) => (
        <g key={u.id} data-trace-id={u.id} data-active={isActive(u.id)} className="th-shape th-fade" style={{ animationDelay: `${1850 + i * 130}ms` }}>
          <ellipse cx="250" cy={u.cy} rx="92" ry="17" className="th-oval" />
          <text x="250" y={u.cy + 4} textAnchor="middle" fontSize="12" className="fill-ink">
            {u.label}
          </text>
          <circle data-anchor={u.id} cx="342" cy={u.cy} r="0.5" fill="none" />
        </g>
      ))}
      <g className="th-assumed th-fade" style={{ animationDelay: '2700ms' }}>
        <ellipse cx="250" cy="204" rx="92" ry="17" />
        <text x="250" y="208" textAnchor="middle" fontSize="12" className="fill-ink">
          Log in
        </text>
        <text x="250" y="236" textAnchor="middle" fontSize="9.5" className="th-assumed-label" style={{ fontFamily: 'var(--font-mono)' }}>
          assumption · no requirement
        </text>
      </g>
    </svg>
  )
}
