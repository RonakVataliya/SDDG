import type * as React from 'react'
import type { DiagramType } from '@/api/client'

/** Small line drawings of each diagram type, for pickers and thumbnails. Theme-aware via CSS variables. */
const ink = { stroke: 'var(--ink)', strokeWidth: 1.4, fill: 'none', strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }
const hot = { stroke: 'var(--accent)', strokeWidth: 1.4, fill: 'var(--accent-wash)' }

const GLYPHS: Record<DiagramType, React.ReactNode> = {
  use_case: (
    <>
      <g {...ink}>
        <circle cx="22" cy="26" r="5" />
        <path d="M22 31v13M14 36h16M22 44l-6 9M22 44l6 9" />
        <path d="M30 36l26-12M30 36l26 10" strokeWidth={1} />
      </g>
      <ellipse cx="80" cy="24" rx="24" ry="9" {...hot} />
      <ellipse cx="80" cy="48" rx="24" ry="9" {...ink} />
    </>
  ),
  class: (
    <>
      <g {...ink}>
        <rect x="10" y="12" width="40" height="46" rx="2" />
        <path d="M10 24h40M10 42h40M16 31h22M16 36h16M16 49h20M50 34h18" />
        <path d="m64 30 6 4-6 4z" fill="var(--field)" />
      </g>
      <rect x="70" y="18" width="38" height="34" rx="2" {...hot} />
      <path d="M70 29h38" stroke="var(--accent)" strokeWidth={1.4} />
    </>
  ),
  activity: (
    <>
      <circle cx="20" cy="35" r="5" fill="var(--ink)" />
      <g {...ink}>
        <path d="M25 35h10M62 35h8M92 24v-6h-40v6M92 46v6h-40v-6" />
        <path d="M52 35l10-10 10 10-10 10z" fill="var(--field)" />
        <rect x="76" y="27" width="28" height="16" rx="6" fill="var(--field)" />
      </g>
      <rect x="35" y="27" width="17" height="16" rx="6" {...hot} />
    </>
  ),
  sequence: (
    <>
      <g {...ink}>
        <rect x="8" y="8" width="26" height="12" rx="2" />
        <rect x="47" y="8" width="26" height="12" rx="2" />
        <rect x="86" y="8" width="26" height="12" rx="2" />
        <path d="M21 20v42M60 20v42M99 20v42" strokeDasharray="3 3" strokeWidth={1} />
      </g>
      <g stroke="var(--accent)" strokeWidth={1.5} fill="none">
        <path d="M21 30h37M60 42h37M97 54H23" />
        <path d="m54 27 4 3-4 3M93 39l4 3-4 3M27 51l-4 3 4 3" />
      </g>
    </>
  ),
  dfd: (
    <>
      <g {...ink}>
        <rect x="6" y="26" width="22" height="18" rx="1" />
        <path d="M80 18h30M80 30h30M84 18v12M28 35h18M74 35h10v-5M60 49v10H92M80 52h30M80 62h30" />
      </g>
      <circle cx="60" cy="35" r="14" {...hot} />
    </>
  ),
  component: (
    <>
      <g {...ink}>
        <rect x="10" y="18" width="40" height="30" rx="2" />
        <path d="M6 26h8M6 34h8" strokeWidth={2.4} />
        <path d="M50 33h14M70 33h4" />
        <circle cx="68" cy="33" r="4" />
      </g>
      <rect x="74" y="18" width="38" height="30" rx="2" {...hot} />
    </>
  ),
  package: (
    <>
      <g {...ink}>
        <path d="M10 22v-6h16v6" />
        <rect x="10" y="22" width="40" height="30" rx="1" />
        <path d="M50 37h18m-6-4 6 4-6 4" />
      </g>
      <path d="M72 22v-6h16v6" {...hot} />
      <rect x="72" y="22" width="38" height="30" rx="1" {...hot} />
    </>
  ),
}

export function DiagramGlyph({ type, className }: { type: DiagramType; className?: string }) {
  return (
    <svg viewBox="0 0 120 70" className={className} aria-hidden>
      {GLYPHS[type]}
    </svg>
  )
}
