import { useSyncExternalStore } from 'react'

export type Toast = { id: number; message: string; tone: 'success' | 'info' | 'error' }

let toasts: Toast[] = []
let nextId = 1
const listeners = new Set<() => void>()
const emit = () => listeners.forEach((l) => l())

export function dismissToast(id: number) {
  toasts = toasts.filter((t) => t.id !== id)
  emit()
}

/** A short message in the corner of the screen ("You joined Acme Clinic as an Editor."). Goes away by itself. */
export function toast(message: string, tone: Toast['tone'] = 'success', ms = 5000) {
  const id = nextId++
  toasts = [...toasts, { id, message, tone }]
  emit()
  if (ms > 0) setTimeout(() => dismissToast(id), ms)
  return id
}

export function clearToasts() {
  toasts = []
  emit()
}

export function useToasts() {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l)
      return () => listeners.delete(l)
    },
    () => toasts,
  )
}
