import { configure, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { collabState } from '@/mocks/collab'
import { getDb, membersOf } from '@/mocks/db'
import { renderApp } from '@/test/render'
import { seedDiagram, seedInvitation, seedOthersProject, seedProject } from '@/test/seed'

// A CI runner is slower than a laptop: the mock API needs more than the one second
// testing-library waits by default, so these waits get a real budget.
configure({ asyncUtilTimeout: 5000 })
vi.setConfig({ testTimeout: 20000 })

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

describe('FR32 an @mention in a comment', () => {
  /** What the API writes: IDs and the target's short label, never the comment's text. */
  function seedMention(over: Record<string, string> = {}) {
    seedProject()
    collabState().notifications.push({
      id: 'nt_m1', user: 'dev@sddg.test', type: 'mention',
      payload: {
        project_id: 'pr_1', comment_id: 'cm_1', from_user_id: 'priya.shah@sddg.test',
        target_type: 'statement', target_id: 'st_1', target: 'R-001', ...over,
      },
      read_at: null, created_at: new Date().toISOString(),
    })
  }

  it('says who mentioned you and on what, and takes you to the requirement', async () => {
    seedMention()
    const user = userEvent.setup()
    const { router } = renderApp('/projects')

    await user.click(await screen.findByRole('button', { name: 'Notifications, 1 unread' }))
    expect(await screen.findByText('Priya Shah mentioned you on R-001 in Library system')).toBeInTheDocument()
    await user.click(screen.getByRole('link', { name: 'View requirement' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/projects/pr_1/review'))
    // Following the link marks it read, like every other row.
    await waitFor(() => expect(screen.getByRole('button', { name: 'Notifications' })).toBeInTheDocument())
  })

  it('takes you to the diagram when the comment was on one', async () => {
    seedMention({ target_type: 'diagram', target_id: 'dg_1', target: 'Use Case diagram v3' })
    const user = userEvent.setup()
    const { router } = renderApp('/projects')

    await user.click(await screen.findByRole('button', { name: 'Notifications, 1 unread' }))
    expect(await screen.findByText(/mentioned you on Use Case diagram v3/)).toBeInTheDocument()
    await user.click(screen.getByRole('link', { name: 'View diagram' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/projects/pr_1/diagrams/dg_1'))
  })

  it('posting a comment puts a mention in the other person\'s bell, with no comment text in it', async () => {
    seedProject()
    membersOf('pr_1').push({ email: 'priya.shah@sddg.test', role: 'editor', joined_at: new Date().toISOString() })
    const secret = 'Zebra-this-text-must-not-travel'

    const r = await fetch('http://localhost/api/v1/projects/pr_1/comments', {
      method: 'POST',
      headers: { 'content-type': 'application/json', authorization: 'Bearer mock-token:dev@sddg.test' },
      body: JSON.stringify({
        target_type: 'statement', target_id: 'st_1', body: secret,
        mentions: ['dev:priya.shah@sddg.test', 'dev:priya.shah@sddg.test', 'dev:dev@sddg.test'],
      }),
    })
    expect(r.status).toBe(201)

    const mentions = collabState().notifications.filter((n) => n.type === 'mention')
    expect(mentions).toHaveLength(1) // named twice is once, and the author is not told
    expect(mentions[0].user).toBe('priya.shah@sddg.test')
    expect(mentions[0].payload.target).toBe('R-001')
    expect(JSON.stringify(mentions[0])).not.toContain(secret)
  })
})
