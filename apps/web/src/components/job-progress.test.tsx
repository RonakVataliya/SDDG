import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { Job } from '@/api/client'
import { JobProgress } from './job-progress'

const job = (over: Partial<Job>): Job =>
  ({
    id: 'job_1',
    kind: 'generation',
    status: 'running',
    queue_position: null,
    progress: { step: 1, total: 3, label: 'Extracting building blocks' },
    diagram_types: ['use_case'],
    diagram_ids: [],
    error: null,
    created_at: new Date().toISOString(),
    started_at: new Date().toISOString(),
    finished_at: null,
    ...over,
  }) as Job

describe('JobProgress', () => {
  it('explains a job paused for the AI rate limit instead of showing an error', () => {
    render(<JobProgress job={job({ status: 'waiting', progress: { step: 1, total: 3, label: 'Waiting for AI capacity, about 40 s' } })} title="Generating your diagram" />)
    expect(screen.getByText("Waiting for AI capacity, about 40 s. The AI provider's rate limit was reached; this continues by itself.")).toBeInTheDocument()
    expect(screen.getByRole('progressbar')).toBeInTheDocument()
  })
})
