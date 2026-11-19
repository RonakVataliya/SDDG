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

describe('document and job polling rules', () => {
  it('document polling continues for uploaded/processing and stops for processed/failed', () => {
    const documentPollingInterval = (docs: Array<{ status: string }>) =>
      docs.some((d) => d.status === 'uploaded' || d.status === 'processing') ? 1500 : false

    expect(documentPollingInterval([{ status: 'uploaded' }])).toBe(1500)
    expect(documentPollingInterval([{ status: 'processing' }])).toBe(1500)
    expect(documentPollingInterval([{ status: 'processed' }])).toBe(false)
    expect(documentPollingInterval([{ status: 'failed' }])).toBe(false)
    expect(documentPollingInterval([{ status: 'processed' }, { status: 'failed' }])).toBe(false)
    expect(documentPollingInterval([{ status: 'processed' }, { status: 'processing' }])).toBe(1500)
  })

  it('job polling continues for queued/running and stops for succeeded/failed', () => {
    const isActive = (job?: { status: string } | null) => job?.status === 'queued' || job?.status === 'running'
    const jobPollingInterval = (job?: { status: string } | null) =>
      job && !isActive(job) ? false : 1500

    expect(jobPollingInterval({ status: 'queued' })).toBe(1500)
    expect(jobPollingInterval({ status: 'running' })).toBe(1500)
    expect(jobPollingInterval({ status: 'succeeded' })).toBe(false)
    expect(jobPollingInterval({ status: 'failed' })).toBe(false)
  })
})

