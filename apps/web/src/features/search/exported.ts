/**
 * Remembers which diagrams the user has exported.
 * The API has no "exported" state, so this is kept per browser in localStorage.
 */
const KEY = 'sddg.exported.diagrams'

export function getExportedIds(): string[] {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? '[]')
  } catch {
    return []
  }
}

export function markExported(diagramId: string) {
  try {
    localStorage.setItem(KEY, JSON.stringify([...new Set([...getExportedIds(), diagramId])]))
  } catch {
    /* storage unavailable: the diagram just won't show as exported */
  }
}
