import { QueryClient } from '@tanstack/react-query'
import { ApiError, isWakingError } from '@/api/errors'

/** ~1 min Render cold start → keep retrying every 5 s for up to 2 min before giving up (FR30c). */
const WAKE_RETRY_DELAY = 5_000
const WAKE_MAX_RETRIES = 24

export function shouldRetry(failureCount: number, error: unknown) {
  if (isWakingError(error)) return failureCount < WAKE_MAX_RETRIES
  if (error instanceof ApiError && error.status < 500) return false // 4xx is a real answer
  return failureCount < 2
}

export function retryDelay(attempt: number, error: unknown) {
  return isWakingError(error) ? WAKE_RETRY_DELAY : Math.min(1000 * 2 ** attempt, 8000)
}

export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: shouldRetry, retryDelay, staleTime: 15_000, refetchOnWindowFocus: false },
      // A 502/503/504 means the request never reached the app, so a mutation is safe to resend.
      // A raw network error is not retried for mutations: the POST may have landed.
      mutations: {
        retry: (n, e) => e instanceof ApiError && isWakingError(e) && n < WAKE_MAX_RETRIES,
        retryDelay: WAKE_RETRY_DELAY,
      },
    },
  })
}
