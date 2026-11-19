import type * as React from 'react'
import type { CSSProperties, ReactNode } from 'react'

/**
 * Login backgrounds. One is picked at random per visit (see pickBackground), never the same one twice in a row.
 * All are drawn in a 1440×900 box that covers the screen; artwork stays near the edges so the centre is calm.
 * Colours come from theme tokens, so each background works in light and dark mode.
 */

const VB = '0 0 1440 900'
const d = (ms: number): CSSProperties => ({ animationDelay: `${ms}ms` })
const Svg = ({ children, className }: { children: ReactNode; className?: string }) => (
  <svg viewBox={VB} preserveAspectRatio="xMidYMid slice" className={`absolute inset-0 size-full ${className ?? ''}`} aria-hidden>
    {children}
  </svg>
)
/** A path that draws itself in. */
const P = ({ d: path, delay = 0, ...rest }: { d: string; delay?: number } & React.SVGProps<SVGPathElement>) => (
  <path d={path} pathLength={1} className="draw" style={d(delay)} {...rest} />
)
const T = ({ x, y, children, delay = 0, ...rest }: { x: number; y: number; children: ReactNode; delay?: number } & React.SVGProps<SVGTextElement>) => (
  <text x={x} y={y} className="fade-in" style={d(delay)} {...rest}>
    {children}
  </text>
)
const actorPath = (x: number, y: number) => `M${x} ${y - 12}a12 12 0 1 0 0.01 0M${x} ${y + 12}v32M${x - 20} ${y + 26}h40M${x} ${y + 44}l-15 24M${x} ${y + 44}l15 24`
const ellipsePath = (cx: number, cy: number, rx: number, ry: number) => `M${cx - rx} ${cy}a${rx} ${ry} 0 1 0 ${2 * rx} 0a${rx} ${ry} 0 1 0 ${-2 * rx} 0`
const rectPath = (x: number, y: number, w: number, h: number) => `M${x} ${y}h${w}v${h}h${-w}z`

/* ---------- 1 · Living blueprint ---------- */
function Blueprint() {
  const st = { stroke: 'var(--accent)', fill: 'none', strokeWidth: 1.4, strokeLinecap: 'round' as const }
  const mono = { fill: 'var(--accent)', fontSize: 12, fontFamily: 'var(--font-mono)' }
  const label = { fill: 'var(--accent)', fontSize: 13, fontFamily: 'var(--font-sans)', textAnchor: 'middle' as const }
  return (
    <>
      <div
        className="absolute inset-0"
        style={{
          backgroundImage:
            'linear-gradient(color-mix(in srgb,var(--accent) 9%,transparent) 1px,transparent 1px),linear-gradient(90deg,color-mix(in srgb,var(--accent) 9%,transparent) 1px,transparent 1px),linear-gradient(color-mix(in srgb,var(--accent) 4%,transparent) 1px,transparent 1px),linear-gradient(90deg,color-mix(in srgb,var(--accent) 4%,transparent) 1px,transparent 1px)',
          backgroundSize: '120px 120px,120px 120px,24px 24px,24px 24px',
          maskImage: 'radial-gradient(ellipse at center,#000 35%,transparent 80%)',
        }}
      />
      <Svg className="opacity-60">
        <g {...st}>
          <P d={actorPath(170, 300)} delay={200} />
          <P d={actorPath(170, 580)} delay={350} />
          <P d={ellipsePath(370, 250, 92, 26)} delay={500} />
          <P d={ellipsePath(370, 420, 92, 26)} delay={600} strokeDasharray="6 5" />
          <P d={ellipsePath(370, 640, 92, 26)} delay={700} />
          <P d="M192 330L280 258M192 330L280 416M192 610L280 636" delay={900} />
          <P d={rectPath(1030, 150, 200, 130) + 'M1030 184h200M1030 246h200'} delay={300} />
          <P d={rectPath(1120, 400, 200, 110) + 'M1120 434h200'} delay={500} />
          <P d={rectPath(1010, 630, 200, 110) + 'M1010 664h200'} delay={700} />
          <P d="M1130 280v50h90v70M1110 630v-60h110v-60" delay={1000} />
          <P d="M90 70h550M90 64v12M640 64v12M760 820h380M760 814v12M1140 814v12M60 120v660M54 120h12M54 780h12" delay={1200} strokeWidth={1} />
          <P d={rectPath(1250, 640, 160, 80) + 'M1250 666h160M1330 666v54'} delay={1300} strokeWidth={1} />
        </g>
        <g style={label}>
          <T x={370} y={255} delay={900}>Issue book</T>
          <T x={370} y={425} delay={950}>Reserve book</T>
          <T x={370} y={645} delay={1000}>Search catalogue</T>
          <T x={170} y={392} delay={700}>Librarian</T>
          <T x={170} y={672} delay={750}>Member</T>
          <T x={1130} y={172} delay={700}>Book</T>
          <T x={1220} y={422} delay={800}>Loan</T>
          <T x={1110} y={652} delay={900}>Member</T>
        </g>
        <g style={mono}>
          <T x={1046} y={208} delay={900}>+ isbn: String</T>
          <T x={1046} y={228} delay={950}>+ title: String</T>
          <T x={1046} y={268} delay={1000}>+ reserve()</T>
          <T x={1136} y={456} delay={1000}>+ dueDate: Date</T>
          <T x={1140} y={318} delay={1200}>1</T>
          <T x={1228} y={388} delay={1200}>0..*</T>
          <T x={300} y={60} delay={1400}>R-003 → Issue book</T>
          <T x={880} y={808} delay={1400}>R-007 → Loan.limit</T>
          <T x={1260} y={658} delay={1500}>SDDG · SHEET 01</T>
          <T x={1260} y={698} delay={1500}>SCALE 1:1</T>
          <T x={1340} y={698} delay={1500}>REV v3</T>
        </g>
      </Svg>
    </>
  )
}

/* ---------- 2 · Requirements become shapes ---------- */
function Story() {
  const chip = (x: number, y: number, r: number, ref: string, before: string, hl: string, after: string, delay: number) => (
    <g transform={`rotate(${r} ${x + 150} ${y + 40})`} className="rise" style={d(delay)}>
      <rect x={x} y={y} width={300} height={84} rx={14} fill="var(--surface)" stroke="var(--rule)" />
      <rect x={x + 16} y={y + 14} width={46} height={20} rx={4} fill="var(--field)" stroke="var(--rule-strong)" />
      <text x={x + 39} y={y + 28} textAnchor="middle" fontSize={11} fontFamily="var(--font-mono)" fill="var(--ink-2)">{ref}</text>
      <text x={x + 16} y={y + 60} fontSize={13.5} fontFamily="var(--font-sans)" fill="var(--ink)">
        {before}
        <tspan fill="var(--accent)" fontWeight={600}>{hl}</tspan>
        {after}
      </text>
    </g>
  )
  const ink = { stroke: 'var(--ink)', fill: 'none', strokeWidth: 1.6, strokeLinecap: 'round' as const }
  return (
    <>
      <div className="absolute inset-0" style={{ background: 'radial-gradient(circle at 15% 30%,var(--accent-wash),transparent 45%),radial-gradient(circle at 85% 70%,var(--amber-wash),transparent 40%)' }} />
      <Svg>
        <g stroke="var(--accent)" fill="none" strokeWidth={1.6} strokeDasharray="2 7" strokeLinecap="round" opacity={0.75} className="march">
          <path d="M400 210 C 640 90, 860 110, 1060 190" />
          <path d="M380 470 C 660 520, 840 380, 1080 440" />
          <path d="M420 720 C 650 820, 880 800, 1060 700" />
        </g>
        {chip(100, 150, -3, 'R-003', 'The librarian shall ', 'issue a book', '.', 200)}
        {chip(70, 410, 2, 'R-007', 'Each ', 'loan', ' has a due date.', 400)}
        {chip(120, 660, -1.5, 'R-011', 'A member may ', 'renew', ' a book once.', 600)}
        <g {...ink}>
          <P d={actorPath(1100, 182)} delay={800} />
          <P d="M1122 200l56-6" delay={1000} />
          <P d={rectPath(1090, 390, 210, 110) + 'M1090 422h210M1090 470h210'} delay={900} />
          <P d="M1087 700h30M1161 700h30M1117 700l22-22 22 22-22 22z" delay={1000} />
        </g>
        <circle cx={1080} cy={700} r={7} fill="var(--ink)" className="fade-in" style={d(1000)} />
        <ellipse cx={1270} cy={190} rx={90} ry={26} fill="var(--accent-wash)" stroke="var(--accent)" strokeWidth={1.8} className="fade-in" style={d(1100)} />
        <rect x={1191} y={680} width={130} height={40} rx={20} fill="var(--accent-wash)" stroke="var(--accent)" strokeWidth={1.6} className="fade-in" style={d(1200)} />
        <g fontFamily="var(--font-sans)" fontSize={14} textAnchor="middle" fill="var(--ink)">
          <T x={1270} y={195} delay={1200}>Issue book</T>
          <T x={1195} y={412} delay={1100}>Loan</T>
          <T x={1256} y={705} delay={1300}>Renew loan</T>
        </g>
        <g fontFamily="var(--font-mono)" fontSize={11} fill="var(--slate)">
          <T x={1104} y={449} delay={1200}>+ dueDate: Date</T>
          <T x={1104} y={490} delay={1250}>+ renew()</T>
        </g>
      </Svg>
    </>
  )
}

/* ---------- 3 · Whiteboard sketch ---------- */
function Sketch() {
  let seed = 3
  const r = () => (seed = (seed * 16807) % 2147483647) / 2147483647 - 0.5
  const wob = (pts: number[][], j = 3) => 'M' + pts.map(([x, y]) => `${(x + r() * j).toFixed(1)} ${(y + r() * j).toFixed(1)}`).join(' L')
  const line = (a: number[], b: number[], n = 6) => Array.from({ length: n + 1 }, (_, i) => [a[0] + ((b[0] - a[0]) * i) / n, a[1] + ((b[1] - a[1]) * i) / n])
  const ell = (cx: number, cy: number, rx: number, ry: number) => Array.from({ length: 29 }, (_, i) => [cx + rx * Math.cos((i / 26) * Math.PI * 2), cy + ry * Math.sin((i / 26) * Math.PI * 2)])
  const rect = (x: number, y: number, w: number, h: number) => [...line([x, y], [x + w, y]), ...line([x + w, y], [x + w, y + h]), ...line([x + w, y + h], [x, y + h]), ...line([x, y + h], [x, y - 3])]
  let t = 0
  const twice = (pts: number[][], color: string) => {
    t += 90
    const s = { fill: 'none', stroke: color, strokeWidth: 2.3, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }
    return (
      <>
        <P d={wob(pts)} delay={t} {...s} />
        <P d={wob(pts, 4)} delay={t + 60} {...s} opacity={0.55} />
      </>
    )
  }
  const ink = 'var(--ink)'
  const acc = 'var(--accent)'
  const arrow = (a: number[], b: number[]) => {
    const ang = Math.atan2(b[1] - a[1], b[0] - a[0])
    const h = (k: number) => [b[0] - 14 * Math.cos(ang + k), b[1] - 14 * Math.sin(ang + k)]
    return (
      <>
        {twice(line(a, b, 5), acc)}
        {twice([h(0.5), b, h(-0.5)], acc)}
      </>
    )
  }
  const actor = (x: number, y: number) => (
    <>
      {twice(ell(x, y, 13, 13), ink)}
      {twice(line([x, y + 13], [x, y + 50], 4), ink)}
      {twice(line([x - 22, y + 28], [x + 22, y + 28], 3), ink)}
      {twice([[x - 16, y + 76], [x, y + 50], [x + 16, y + 76]], ink)}
    </>
  )
  const hand = (x: number, y: number, s: string, size = 26, color = 'var(--ink)') => (
    <T x={x} y={y} delay={(t += 60)} textAnchor="middle" fontFamily="var(--font-hand)" fontSize={size} fill={color}>
      {s}
    </T>
  )
  const hi = (x: number, y: number, w: number) => <path d={`M${x} ${y}l${w} -2`} stroke="#fde047" strokeWidth={18} strokeLinecap="round" opacity={0.5} className="fade-in" style={d(t)} />
  return (
    <>
      <div className="absolute inset-0" style={{ backgroundImage: 'radial-gradient(color-mix(in srgb,var(--ink) 14%,transparent) 1px,transparent 1.3px)', backgroundSize: '26px 26px' }} />
      <Svg>
        {actor(160, 150)}
        {hand(160, 268, 'Librarian')}
        {hi(268, 152, 200)}
        {twice(ell(370, 150, 110, 38), acc)}
        {hand(370, 158, 'Issue book', 28, acc)}
        {arrow([190, 180], [258, 160])}
        {twice(rect(110, 420, 210, 120), ink)}
        {twice(line([110, 458], [320, 458]), ink)}
        {hand(215, 448, 'Book')}
        {hand(200, 498, '+ isbn, title', 22, 'var(--slate)')}
        {twice(ell(250, 720, 95, 34), ink)}
        {hand(250, 728, 'Search')}
        {arrow([215, 545], [240, 680])}
        {twice(rect(1080, 130, 220, 70), ink)}
        {hand(1190, 174, 'Log in / Sign up')}
        {arrow([1190, 205], [1190, 300])}
        {twice(ell(1150, 350, 80, 44), ink)}
        {hand(1150, 358, 'Id')}
        {twice(ell(1320, 380, 70, 40), ink)}
        {hand(1320, 388, 'Pass')}
        {arrow([1160, 400], [1210, 520])}
        {arrow([1310, 425], [1260, 520])}
        {hi(1185, 570, 110)}
        {twice(ell(1240, 570, 78, 40), acc)}
        {hand(1240, 578, 'Submit ✓', 28, acc)}
        {hand(1180, 790, 'v1 · first sketch', 24, 'var(--slate)')}
      </Svg>
    </>
  )
}

/* ---------- 4 · Swimlanes ---------- */
function Swimlanes() {
  const lanes: [string, number][] = [['Member', 110], ['Librarian', 390], ['System', 670]]
  const node = (x: number, y: number, label: string, hot: boolean, delay: number) => (
    <g className="rise" style={d(delay)}>
      <rect x={x - 80} y={y - 24} width={160} height={48} rx={24} fill={hot ? 'var(--accent-wash)' : 'var(--field)'} stroke={hot ? 'var(--accent)' : 'var(--ink)'} strokeWidth={1.5} />
      <text x={x} y={y + 5} textAnchor="middle" fontSize={14} fontFamily="var(--font-sans)" fill="var(--ink)">{label}</text>
    </g>
  )
  const ar = (path: string, delay: number) => <P d={path} delay={delay} fill="none" stroke="var(--ink)" strokeWidth={1.4} markerEnd="url(#sl-ah)" />
  return (
    <Svg>
      <defs>
        <marker id="sl-ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
          <path d="M0 0L10 5L0 10z" fill="var(--ink)" />
        </marker>
      </defs>
      {lanes.map(([n, y], i) => (
        <g key={n}>
          <rect x={0} y={y - 110} width={1440} height={280} fill={i % 2 ? 'color-mix(in srgb,var(--ink) 3%,transparent)' : 'transparent'} />
          <line x1={0} y1={y + 170} x2={1440} y2={y + 170} stroke="var(--rule)" />
          <text x={34} y={y + 30} transform={`rotate(-90 34 ${y + 30})`} textAnchor="middle" fontSize={12} letterSpacing={2} fontFamily="var(--font-mono)" fill="var(--slate)">
            {n.toUpperCase()}
          </text>
        </g>
      ))}
      <line x1={60} y1={0} x2={60} y2={900} stroke="var(--rule)" />
      <circle cx={130} cy={140} r={10} fill="var(--ink)" className="fade-in" />
      {ar('M140 140h50', 200)}
      {node(272, 140, 'Search book', false, 300)}
      {ar('M352 140h40v280h-30', 500)}
      {node(282, 420, 'Check limit', true, 700)}
      <path d="M282 444v50" stroke="var(--ink)" strokeWidth={1.4} />
      <path d="M282 494l24 24-24 24-24-24z" fill="var(--field)" stroke="var(--ink)" strokeWidth={1.4} className="fade-in" style={d(800)} />
      {ar('M306 518h80v180h-24', 900)}
      {node(282, 700, 'Record loan', false, 1000)}
      {ar('M1040 140h40', 300)}
      {node(1162, 140, 'Get notified', false, 1300)}
      {ar('M1242 140h60', 1400)}
      <circle cx={1320} cy={140} r={11} fill="none" stroke="var(--ink)" strokeWidth={2} className="fade-in" style={d(1500)} />
      <circle cx={1320} cy={140} r={6} fill="var(--ink)" className="fade-in" style={d(1500)} />
      {ar('M1040 420h40', 500)}
      {node(1162, 420, 'Issue book', true, 900)}
      {ar('M1162 396v-230', 1100)}
      {ar('M1040 700h40', 700)}
      {node(1162, 700, 'Send reminder', false, 1100)}
      {ar('M1162 676v-230', 1200)}
      <g fontSize={12} fontFamily="var(--font-mono)" fill="var(--accent)">
        <T x={1176} y={290} delay={1500}>R-003</T>
        <T x={200} y={600} delay={1500}>R-007 · limit 5</T>
      </g>
      {/* tokens travelling along the flow */}
      <circle r={5} fill="var(--accent)">
        <animateMotion dur="7s" repeatCount="indefinite" path="M140 140h212v280h-70v100h104v180" />
      </circle>
      <circle r={5} fill="var(--accent)">
        <animateMotion dur="6s" repeatCount="indefinite" path="M1162 676v-230M1162 396v-230h140" />
      </circle>
    </Svg>
  )
}

/* ---------- 5 · Sequence lifelines ---------- */
function Sequence() {
  const L: [string, number][] = [['Member', 130], ['Web app', 340], ['API', 720], ['AI service', 1110], ['Kroki', 1320]]
  const API = 720
  const msg = (a: number, b: number, y: number, label: string, ret: boolean, delay: number) => {
    const x1 = L[a][1]
    const x2 = L[b][1]
    const dir = x2 > x1 ? -1 : 1
    const color = ret ? 'var(--slate)' : 'var(--accent)'
    const lx = x1 === API ? x2 + dir * 16 : x2 === API ? x1 - dir * 16 : (x1 + x2) / 2
    const anchor = x1 === API ? (dir < 0 ? 'end' : 'start') : x2 === API ? (dir < 0 ? 'start' : 'end') : 'middle'
    return (
      <g key={label}>
        <P d={`M${x1} ${y}H${x2 + dir * 2}`} delay={delay} fill="none" stroke={color} strokeWidth={1.5} strokeDasharray={ret ? '5 5' : undefined} />
        <path d={`M${x2 + dir * 10} ${y - 5}L${x2 + dir * 2} ${y}L${x2 + dir * 10} ${y + 5}`} fill="none" stroke={color} strokeWidth={1.5} className="fade-in" style={d(delay + 600)} />
        <T x={lx} y={y - 8} delay={delay + 300} textAnchor={anchor} fontSize={12} fontFamily="var(--font-mono)" fill={color}>
          {label}
        </T>
      </g>
    )
  }
  return (
    <>
      <div className="absolute inset-0" style={{ background: 'radial-gradient(circle at 50% 50%,var(--accent-wash),transparent 50%)' }} />
      <Svg>
        {L.filter(([n]) => n !== 'API').map(([n, x], i) => (
          <g key={n} className="rise" style={d(i * 120)}>
            <rect x={x - 64} y={60} width={128} height={40} rx={8} fill="var(--field)" stroke="var(--ink)" strokeWidth={1.4} />
            <text x={x} y={85} textAnchor="middle" fontSize={14} fontFamily="var(--font-sans)" fill="var(--ink)">{n}</text>
            <line x1={x} y1={100} x2={x} y2={900} stroke="var(--rule-strong)" strokeDasharray="5 6" />
          </g>
        ))}
        {[[130, 150, 240], [340, 170, 640], [1110, 330, 240], [1320, 560, 120]].map(([x, y, h], i) => (
          <rect key={i} x={x - 6} y={y} width={12} height={h} rx={2} fill="var(--accent-wash)" stroke="var(--accent)" className="fade-in" style={d(500 + i * 200)} />
        ))}
        {msg(0, 1, 170, 'paste requirements', false, 500)}
        {msg(1, 2, 220, 'POST /inputs', false, 700)}
        {msg(2, 3, 340, 'split(text)', false, 900)}
        {msg(3, 2, 410, 'R-001 … R-010', true, 1100)}
        {msg(2, 1, 470, '202 · job queued', true, 1200)}
        {msg(1, 0, 540, 'review & confirm', true, 1300)}
        {msg(2, 4, 580, 'render(spec)', false, 1400)}
        {msg(4, 2, 650, 'diagram.png', true, 1500)}
        {msg(1, 0, 760, 'diagrams ready ✓', true, 1600)}
      </Svg>
    </>
  )
}

export const BACKGROUNDS = { blueprint: Blueprint, story: Story, sketch: Sketch, swimlanes: Swimlanes, sequence: Sequence }
export type BackgroundId = keyof typeof BACKGROUNDS
const IDS = Object.keys(BACKGROUNDS) as BackgroundId[]
const LAST_KEY = 'sddg.loginBg'

/** Random per page load (so sign-up keeps the same one), never the one shown last time. */
export function pickBackground(random = Math.random): BackgroundId {
  let last: string | null = null
  try {
    last = localStorage.getItem(LAST_KEY)
  } catch {
    // storage blocked: any pick is fine
  }
  const pool = IDS.filter((id) => id !== last)
  const pick = pool[Math.floor(random() * pool.length)] ?? IDS[0]
  try {
    localStorage.setItem(LAST_KEY, pick)
  } catch {
    // ignore
  }
  return pick
}
