import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MOCK_USAGE, makeAdmin, resetAdminMock } from '@/mocks/admin'
import { server } from '@/mocks/node'
import { renderApp } from '@/test/render'

beforeEach(() => {
  resetAdminMock()
  makeAdmin('dev@sddg.test')
})

describe('FR25 / NFR1 admin Usage page', () => {
  it('is reached from the sidebar and shows the tiles, the NFR1 checks and the events', async () => {
    const user = userEvent.setup()
    renderApp('/admin/users')
    await user.click(await screen.findByRole('link', { name: 'Usage' }))

    expect(await screen.findByRole('heading', { name: 'Usage' })).toBeInTheDocument()
    expect(screen.getByText('Last 7 days')).toBeInTheDocument()

    const active = within(await screen.findByRole('region', { name: 'ACTIVE USERS' }))
    expect(active.getByText('14')).toBeInTheDocument()
    expect(active.getByText('of 21 accounts')).toBeInTheDocument()
    const projects = within(screen.getByRole('region', { name: 'PROJECTS' }))
    expect(projects.getByText('23')).toBeInTheDocument()
    expect(projects.getByText(/4 archived/)).toBeInTheDocument()
    const storage = within(screen.getByRole('region', { name: 'STORAGE' }))
    expect(storage.getByText('182 MB')).toBeInTheDocument()
    expect(storage.getByText(/36% of the 500 MB limit/)).toBeInTheDocument()
    expect(storage.getByText(/10 MB per file, 15 documents, 100 pages/)).toBeInTheDocument()
    expect(storage.queryByText('80% or more')).not.toBeInTheDocument()

    // Median 38 s is within its 60 s target; the 95th percentile 131 s is over its 120 s target.
    const median = within(screen.getByRole('region', { name: 'GENERATION TIME: MEDIAN' }))
    expect(median.getByText('38 s')).toBeInTheDocument()
    expect(median.getByText('Within NFR1')).toBeInTheDocument()
    const p95 = within(screen.getByRole('region', { name: 'GENERATION TIME: 95TH PERCENTILE' }))
    expect(p95.getByText('131 s')).toBeInTheDocument()
    expect(p95.getByText('Over the target')).toBeInTheDocument()

    const table = within(screen.getByRole('region', { name: 'Slow runs and recent errors' }))
    for (const [type, text] of [['Slow run', 'Generation took 131 s'], ['Rate limit', /hit a rate limit/], ['Error', 'generation job failed']] as const) {
      expect(table.getByText(type)).toBeInTheDocument()
      expect(table.getByText(text)).toBeInTheDocument()
    }
    expect(table.getByText('2 min ago')).toBeInTheDocument()
  })

  it('flags storage at 80% and says so when nothing has run or failed', async () => {
    server.use(
      http.get('*/admin/usage', () =>
        HttpResponse.json({
          ...MOCK_USAGE, storage_bytes: 400 * 1048576, storage_warning: true, events: [],
          generation: { ...MOCK_USAGE.generation, runs: 0, median_seconds: null, p95_seconds: null, median_ok: null, p95_ok: null },
        }),
      ),
    )
    renderApp('/admin/usage')
    expect(await screen.findByText('80% or more')).toBeInTheDocument()
    expect(screen.getAllByText('No finished runs yet.')).toHaveLength(2)
    expect(screen.getByText(/Nothing to report in the last 7 days/)).toBeInTheDocument()
  })

  it('refuses a user who is not an administrator', async () => {
    resetAdminMock() // dev@sddg.test is no longer an administrator
    renderApp('/admin/usage')
    expect(await screen.findByText('Administrators only')).toBeInTheDocument()
  })
})
