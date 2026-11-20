export const WAKING_STATUSES = new Set([502, 503, 504])

export class ApiError extends Error {
  status: number
  code?: string
  /** The whole error body, for answers that carry more than a message (an edit conflict carries the current version). */
  body?: unknown
  constructor(status: number, detail: string, code?: string, body?: unknown) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.body = body
  }
}

/** A request that failed because the server is asleep or unreachable, as opposed to a real rejection. */
export function isWakingError(error: unknown) {
  if (error instanceof ApiError) return WAKING_STATUSES.has(error.status)
  return error instanceof TypeError // fetch() network failure
}

export function errorMessage(error: unknown, fallback = 'Something went wrong. Try again.') {
  if (isWakingError(error)) return 'The server did not respond. It may still be starting; try again in a moment.'
  if (error instanceof Error && error.message) return error.message
  return fallback
}
