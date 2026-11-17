/**
 * The mock Tests API follows the real one (core/testing_db.py, routers/testing_*.py) on the points from the pull
 * request review, so the screens behave the same in mock mode.
 */
import { beforeEach, describe, expect, it } from 'vitest'
import { api, unwrap, type TestCaseUpdate } from '@/api/client'
import { seedProject } from '@/test/seed'
import { getDb, save } from './db'

const BOOKING =
  'A patient books an appointment 1 to 30 days ahead, may already hold at most 2 upcoming appointments, and picks Consultation, Follow-up or Test.'
const P = { project_id: 'pr_1' }

beforeEach(() => {
  localStorage.setItem('sddg.mock.session', JSON.stringify({ email: 'dev@sddg.test', accessToken: 'mock-token:dev@sddg.test' }))
  seedProject({ confirmed: true, consent: true })
  const source = { document: 'Pasted text', page: null, paragraph: 1 }
  getDb().statements.pr_1 = [
    { id: 'st_4', ref: 'R-004', text: BOOKING, label: 'FR', source },
    { id: 'st_5', ref: 'R-005', text: 'A patient books a follow-up 1 to 14 days ahead.', label: 'FR', source },
  ]
  save()
})

async function finished(jobId: string) {
  for (let i = 0; i < 200; i++) {
    const job = await unwrap(api.GET('/jobs/{job_id}', { params: { path: { job_id: jobId } } }))
    if (!['queued', 'running', 'waiting'].includes(job.status)) return job
    await new Promise((r) => setTimeout(r, 50))
  }
  throw new Error(`job ${jobId} did not finish`)
}

async function generate(ids: string[]) {
  const job = await unwrap(api.POST('/projects/{project_id}/tests/criteria-jobs', { params: { path: P }, body: { statement_ids: ids } }))
  expect((await finished(job.id)).status).toBe('succeeded')
}

const designOf = (sid: string) =>
  unwrap(api.GET('/projects/{project_id}/tests/requirements/{statement_id}', { params: { path: { ...P, statement_id: sid } } }))

describe('mock Tests API after the review', () => {
  it('lists a repeated flow once, also after a condition edit', async () => {
    await generate(['st_4'])
    const flow = { project_id: 'pr_1', statement_id: 'st_4', kind: 'basic' as const, text: 'The patient books a slot.' }
    getDb().tests.flows.push({ ...flow, id: 'fl_a' }, { ...flow, id: 'fl_b' }) // the AI repeated a flow
    save()
    const days = (await designOf('st_4')).conditions.find((c) => c.name === 'days_ahead')!
    await unwrap(api.PATCH('/projects/{project_id}/tests/conditions/{condition_id}', { params: { path: { ...P, condition_id: days.id } }, body: { max: 29 } }))
    const titles = (await designOf('st_4')).drafts.map((d) => d.title)
    expect(titles.filter((t) => t === 'Basic flow: The patient books a slot.')).toHaveLength(1)
    expect(new Set(titles).size).toBe(titles.length)
  })

  it('lets a draft only be kept or discarded', async () => {
    await generate(['st_4'])
    const draft = (await designOf('st_4')).drafts[0]
    const patch = (body: TestCaseUpdate) =>
      unwrap(api.PATCH('/projects/{project_id}/tests/cases/{case_id}', { params: { path: { ...P, case_id: draft.id } }, body }))
    await expect(patch({ title: 'Mine' })).rejects.toMatchObject({ status: 409 })
    await expect(patch({ steps: ['Open the page'] })).rejects.toMatchObject({ status: 409 })
    expect((await patch({ kept: false })).kept).toBe(false)
  })

  it('counts only existing cases in a run after a requirement is deleted', async () => {
    await generate(['st_4', 'st_5'])
    const picked = [(await designOf('st_4')).drafts[0].id, (await designOf('st_5')).drafts[0].id]
    const steps = await unwrap(api.POST('/projects/{project_id}/tests/step-jobs', { params: { path: P }, body: { case_ids: picked } }))
    expect((await finished(steps.id)).status).toBe('succeeded')
    const run = await unwrap(api.POST('/projects/{project_id}/tests/runs', { params: { path: P }, body: { name: 'Both', mode: 'pick', case_ids: picked } }))
    expect(run.tally.unmarked).toBe(2)
    await unwrap(
      api.PUT('/projects/{project_id}/tests/runs/{run_id}/results/{case_id}', {
        params: { path: { ...P, run_id: run.id, case_id: picked[0] } },
        body: { status: 'pass' },
      }),
    )
    await api.DELETE('/projects/{project_id}/statements/{statement_id}', { params: { path: { ...P, statement_id: 'st_5' } } })
    const listed = (await unwrap(api.GET('/projects/{project_id}/tests/runs', { params: { path: P } }))).find((r) => r.id === run.id)!
    expect(listed.case_count).toBe(1)
    expect(listed.tally).toEqual({ pass: 1, fail: 0, blocked: 0, skipped: 0, unmarked: 0 })
  })

  it('runs one Tests job at a time per project', async () => {
    const start = () => unwrap(api.POST('/projects/{project_id}/tests/criteria-jobs', { params: { path: P }, body: { statement_ids: ['st_4'] } }))
    const first = await start()
    await expect(start()).rejects.toMatchObject({ status: 409 })
    expect((await finished(first.id)).status).toBe('succeeded')
    const steps = await unwrap(api.POST('/projects/{project_id}/tests/step-jobs', { params: { path: P }, body: {} }))
    await expect(start()).rejects.toMatchObject({ status: 409 }) // a steps job counts too
    expect((await finished(steps.id)).status).toBe('succeeded')
    expect((await finished((await start()).id)).status).toBe('succeeded') // free again
  })
})
