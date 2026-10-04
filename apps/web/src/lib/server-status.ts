import { useSyncExternalStore } from 'react'

/**
 * FR30c. The API runs on Render's free tier and sleeps after 15 min idle (~1 min to wake).
 * While it wakes, requests fail with a network error or 502/503/504. The API client flips this flag,
 * the banner reads it, and TanStack Query keeps retrying until a request gets through.
 */
let waking = false
let since: number | null = null
const listeners = new Set<() => void>()

export const serverStatus = {
  setWaking(next: boolean) {
    if (next === waking) return
    waking = next
    since = next ? Date.now() : null
    listeners.forEach((l) => l())
  },
  get: () => waking,
  since: () => since,
  subscribe(listener: () => void) {
    listeners.add(listener)
    return () => listeners.delete(listener)
  },
}

export function useServerWaking() {
  return useSyncExternalStore(serverStatus.subscribe, serverStatus.get, serverStatus.get)
}
