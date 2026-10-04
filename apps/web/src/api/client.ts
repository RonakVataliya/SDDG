import createClient, { type Middleware } from 'openapi-fetch'
import { auth } from '@/features/auth/auth'
import { env } from '@/lib/env'
import { serverStatus } from '@/lib/server-status'
import { ApiError, WAKING_STATUSES } from './errors'
import type { components, paths } from './schema'

export type Schemas = components['schemas']
export type Project = Schemas['Project']
export type Job = Schemas['Job']
export type ExtractedItem = Schemas['ExtractedItem']
export type ItemCategory = Schemas['ItemCategory']
export type RequirementStatement = Schemas['RequirementStatement']
export type Diagram = Schemas['Diagram']
export type DiagramType = Schemas['DiagramType']

const authMiddleware: Middleware = {
  async onRequest({ request }) {
    const token = await auth.getAccessToken()
    if (token) request.headers.set('Authorization', `Bearer ${token}`)
    return request
  },
  onResponse({ response }) {
    serverStatus.setWaking(WAKING_STATUSES.has(response.status))
    // NFR4a: an expired or revoked token is rejected by the API; send the user back to login.
    if (response.status === 401) void auth.handleUnauthorized()
    return response
  },
  onError({ error }) {
    serverStatus.setWaking(true)
    return error instanceof Error ? error : new TypeError('Network error')
  },
}

// fetch is looked up per call (not captured at import) so MSW can intercept it in tests.
export const api = createClient<paths>({ baseUrl: env.apiUrl, fetch: (request) => globalThis.fetch(request) })
api.use(authMiddleware)

/** Turns openapi-fetch's { data, error, response } into data-or-throw, which TanStack Query expects. */
export async function unwrap<T>(
  promise: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await promise
  if (response.ok) return data as T
  const body = (error ?? {}) as { detail?: unknown; code?: string }
  const detail = typeof body.detail === 'string' ? body.detail : defaultMessage(response.status)
  throw new ApiError(response.status, detail, body.code)
}

function defaultMessage(status: number) {
  if (status === 404) return 'Not found, or you do not have access to it.'
  if (status === 401) return 'Your session has ended. Log in again.'
  if (WAKING_STATUSES.has(status)) return 'The server is starting.'
  return `Request failed (${status}).`
}
