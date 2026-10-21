/**
 * Diagram look (issue #38). A style is stored per diagram, apart from its source, and applied only when the
 * diagram is drawn, so changing it can never alter elements or relationships.
 */
import type { DiagramType, Schemas } from '@/api/client'
import { contrastRatio, isHexColour, MIN_TEXT_CONTRAST } from '@/lib/contrast'

export type DiagramStyle = Schemas['DiagramStyle']
export type LayoutDirection = DiagramStyle['direction']
export type StyleColours = Pick<DiagramStyle, 'background' | 'fill' | 'text' | 'line'>

export const FONT_SIZE_MIN = 8
export const FONT_SIZE_MAX = 24
export const DEFAULT_FONT_SIZE = 12

/** Every preset passes 4.5:1 for text on fill and text on background (checked in style.test.ts). */
export const STYLE_PRESETS: { id: string; label: string; colours: StyleColours }[] = [
  { id: 'default', label: 'Default', colours: { background: '#FFFFFF', fill: '#F4F6F8', text: '#1F2933', line: '#52606D' } },
  { id: 'high_contrast', label: 'High contrast', colours: { background: '#FFFFFF', fill: '#FFFFFF', text: '#000000', line: '#000000' } },
  { id: 'dark', label: 'Dark', colours: { background: '#1E1E24', fill: '#2B2D36', text: '#F5F5F5', line: '#A0A4B0' } },
  { id: 'blueprint', label: 'Blueprint', colours: { background: '#0B3D91', fill: '#12509E', text: '#FFFFFF', line: '#C9D8F0' } },
  { id: 'warm', label: 'Warm', colours: { background: '#FFFBF2', fill: '#FCEFD4', text: '#3B2F1E', line: '#8A6D3B' } },
]

export const DEFAULT_STYLE: DiagramStyle = {
  preset: 'default',
  ...STYLE_PRESETS[0].colours,
  direction: 'auto',
  font_size: DEFAULT_FONT_SIZE,
}

export const DIRECTION_LABELS: Record<LayoutDirection, string> = {
  auto: 'Automatic',
  TB: 'Top to bottom',
  LR: 'Left to right',
}

/** Sequence diagrams always run top to bottom: lifelines have no other direction. */
export const directionSupported = (type: DiagramType) => type !== 'sequence'

/** Same rules the server applies; returns plain-language problems, empty when the style is valid. */
export function styleProblems(style: DiagramStyle): string[] {
  const problems: string[] = []
  for (const key of ['background', 'fill', 'text', 'line'] as const) {
    if (!isHexColour(style[key])) problems.push(`The ${key} colour must look like #1A2B3C.`)
  }
  if (!(style.direction in DIRECTION_LABELS)) problems.push('Choose a layout direction.')
  if (!Number.isInteger(style.font_size) || style.font_size < FONT_SIZE_MIN || style.font_size > FONT_SIZE_MAX)
    problems.push(`Font size must be a whole number from ${FONT_SIZE_MIN} to ${FONT_SIZE_MAX} pt.`)
  return problems
}

export type ContrastProblem = { pair: 'text on fill' | 'text on background'; ratio: number }

/** Text/background pairs below 4.5:1. The panel warns about these before applying; it does not block. */
export function lowContrastPairs(style: StyleColours): ContrastProblem[] {
  const pairs = [
    { pair: 'text on fill' as const, ratio: contrastRatio(style.text, style.fill) },
    // Arrow and message labels sit straight on the background.
    { pair: 'text on background' as const, ratio: contrastRatio(style.text, style.background) },
  ]
  return pairs.filter((p) => p.ratio < MIN_TEXT_CONTRAST)
}

/** The style with a preset's colours applied. */
export function withPreset(style: DiagramStyle, presetId: string): DiagramStyle {
  const preset = STYLE_PRESETS.find((p) => p.id === presetId)
  return preset ? { ...style, ...preset.colours, preset: preset.id } : style
}
