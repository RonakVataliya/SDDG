import { useSyncExternalStore } from 'react'

/** Appearance: Light / Dark / System (default) plus an accent colour. Saved per device in localStorage. */
export type ThemeMode = 'system' | 'light' | 'dark'
export const ACCENTS = [
  { id: 'blue', label: 'Blue', swatch: '#2443d6' },
  { id: 'teal', label: 'Teal', swatch: '#0e7c74' },
  { id: 'violet', label: 'Violet', swatch: '#6a45e8' },
  { id: 'orange', label: 'Orange', swatch: '#c4481a' },
  { id: 'graphite', label: 'Graphite', swatch: '#3b3f48' },
] as const
export type Accent = (typeof ACCENTS)[number]['id']

const MODE_KEY = 'sddg.theme'
const ACCENT_KEY = 'sddg.accent'
const listeners = new Set<() => void>()

function read<T extends string>(key: string, fallback: T, allowed: readonly string[]): T {
  try {
    const v = localStorage.getItem(key)
    return v && allowed.includes(v) ? (v as T) : fallback
  } catch {
    return fallback
  }
}

const media = typeof window !== 'undefined' && window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null
let state = {
  mode: read<ThemeMode>(MODE_KEY, 'system', ['system', 'light', 'dark']),
  accent: read<Accent>(ACCENT_KEY, 'blue', ACCENTS.map((a) => a.id)),
}

export const resolvedTheme = (mode: ThemeMode) => (mode === 'system' ? (media?.matches ? 'dark' : 'light') : mode)

function apply() {
  const root = document.documentElement
  root.dataset.theme = resolvedTheme(state.mode)
  root.dataset.accent = state.accent
}

function set(next: Partial<typeof state>) {
  state = { ...state, ...next }
  try {
    localStorage.setItem(MODE_KEY, state.mode)
    localStorage.setItem(ACCENT_KEY, state.accent)
  } catch {
    // private mode: the choice just isn't remembered
  }
  apply()
  listeners.forEach((l) => l())
}

media?.addEventListener?.('change', () => {
  if (state.mode !== 'system') return
  apply()
  listeners.forEach((l) => l())
})
if (typeof document !== 'undefined') apply()

const subscribe = (l: () => void) => {
  listeners.add(l)
  return () => listeners.delete(l)
}
const snapshot = () => state

export function useTheme() {
  const s = useSyncExternalStore(subscribe, snapshot, snapshot)
  return {
    ...s,
    resolved: resolvedTheme(s.mode),
    setMode: (mode: ThemeMode) => set({ mode }),
    setAccent: (accent: Accent) => set({ accent }),
  }
}
