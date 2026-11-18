import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { getDb } from '@/mocks/db'
import { renderApp } from '@/test/render'
import { seedDiagram, seedInvitation, seedOthersProject, seedProject } from '@/test/seed'

describe('FR24a invitations in the bell', () => {
  it('shows an invitation, accepts it, and opens the project with the invited role', async () => {
    seedOthersProject()
    seedInvitation({ role: 'editor' })
    const user = userEvent.setup()
    const { router } = renderApp('/projects')

    const bell = await screen.findByRole('button', { name: 'Notifications, 1 unread' })
    await user.click(bell)
    expect(await screen.findByText(/invited you to Acme Clinic/)).toBeInTheDocument()
    const panel = screen.getByRole('menu')
    expect(within(panel).getByText('Editor')).toBeInTheDocument()

    await user.click(within(panel).getByRole('button', { name: 'Accept' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/projects/pr_1'))
    expect(await screen.findByText('You joined Acme Clinic as an Editor.')).toBeInTheDocument()
    expect(getDb().collab.invitations[0].accepted_at).not.toBeNull()
    // Accepting marks the notification read, so the badge goes.
    await waitFor(() => expect(screen.getByRole('button', { name: 'Notifications' })).toBeInTheDocument())

  })

  it('puts a project you joined in your list, with the role and whose project it is', async () => {
    seedOthersProject()
    seedInvitation({ role: 'editor', accepted_at: new Date().toISOString() })
    renderApp('/projects')

    const row = await screen.findByRole('link', { name: /Acme Clinic/ })
    expect(within(row).getByText('Editor')).toBeInTheDocument()
    expect(within(row).getByText(/Joined just now · owner Ronak Vataliya/)).toBeInTheDocument()
  })

  it('does not offer Accept for a revoked invitation', async () => {
    seedOthersProject()
    seedInvitation({ revoked_at: new Date().toISOString() })
    const user = userEvent.setup()
    renderApp('/projects')
    await user.click(await screen.findByRole('button', { name: 'Notifications' }))
    // A revoked invitation never reaches the bell.
    expect(await screen.findByText(/Invitations and mentions show up here/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Accept' })).not.toBeInTheDocument()
  })

  it('says so when there is nothing to show', async () => {
    seedProject()
    const user = userEvent.setup()
    renderApp('/projects')
    await user.click(await screen.findByRole('button', { name: 'Notifications' }))
    expect(await screen.findByText(/Invitations and mentions show up here/)).toBeInTheDocument()
  })
})

describe('FR24a invitation link', () => {
  it('joins the project when the copied link is opened', async () => {
    seedOthersProject()
    const inv = seedInvitation({ role: 'viewer' })
    const { router } = renderApp(`/invite?token=${inv.token}`)
    await waitFor(() => expect(router.state.location.pathname).toBe('/projects/pr_1'))
    expect(await screen.findByText('You joined Acme Clinic as a Viewer.')).toBeInTheDocument()
  })

  it('explains an expired link instead of joining', async () => {
    seedOthersProject()
    const inv = seedInvitation({ expires_at: new Date(Date.now() - 1000).toISOString() })
    renderApp(`/invite?token=${inv.token}`)
    expect(await screen.findByText(/This invitation has expired/)).toBeInTheDocument()
    expect(getDb().collab.invitations[0].accepted_at).toBeNull()
  })
})

describe('#36 generation finished or failed', () => {
  it('tells you a diagram is ready and takes you to it', async () => {
    seedDiagram()
    const at = new Date().toISOString()
    getDb().jobs.push({
      id: 'job_gen', project_id: 'pr_1', kind: 'generation', status: 'succeeded', applied: true,
      diagram_ids: ['dg_1'], progress: { step: 3, total: 3, label: 'Diagram ready' },
      created_at: at, started_at: at, finished_at: at,
    })
    const user = userEvent.setup()
    const { router } = renderApp('/projects')

    await user.click(await screen.findByRole('button', { name: 'Notifications, 1 unread' }))
    expect(await screen.findByText('Your diagram is ready in Library system')).toBeInTheDocument()
    await user.click(screen.getByRole('link', { name: 'View diagram' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/projects/pr_1/diagrams/dg_1'))
  })

  it('tells you a generation did not finish and offers to try again', async () => {
    seedDiagram()
    const at = new Date().toISOString()
    getDb().jobs.push({
      id: 'job_bad', project_id: 'pr_1', kind: 'generation', status: 'failed', applied: true,
      error: 'Kroki rejected the source', progress: { step: 3, total: 3, label: 'Generation failed' },
      created_at: at, started_at: at, finished_at: at,
    })
    const user = userEvent.setup()
    const { router } = renderApp('/projects')

    await user.click(await screen.findByRole('button', { name: 'Notifications, 1 unread' }))
    expect(await screen.findByText('Generating a diagram in Library system did not finish')).toBeInTheDocument()
    // The failure reason is never carried in the notification; only ids are.
    expect(screen.queryByText(/Kroki/)).not.toBeInTheDocument()
    await user.click(screen.getByRole('link', { name: 'Try again' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/projects/pr_1/generate'))
  })
})
