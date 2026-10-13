import { ApiError } from '@/api/errors'
import { retryDelay, shouldRetry } from './query-client'

describe('FR30c retry policy', () => {
  it('keeps retrying while the server is waking (503 or network error)', () => {
    expect(shouldRetry(10, new ApiError(503, 'waking'))).toBe(true)
    expect(shouldRetry(10, new TypeError('Failed to fetch'))).toBe(true)
    expect(retryDelay(3, new ApiError(502, 'x'))).toBe(5000)
  })

  it('gives up eventually', () => {
    expect(shouldRetry(24, new ApiError(503, 'waking'))).toBe(false)
  })

  it('never retries a real rejection', () => {
    expect(shouldRetry(0, new ApiError(404, 'not found'))).toBe(false)
    expect(shouldRetry(0, new ApiError(409, 'duplicate'))).toBe(false)
  })
})
