import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { Button } from '@/components/ui/button'
import { Toaster } from '@/components/ui/toaster'
import { createQueryClient } from '@/lib/query-client'
import { clearToasts } from '@/lib/toast'
import { getDb } from '@/mocks/db'
import { seedInvitation, seedProject } from '@/test/seed'
import { InviteDialog } from './invite-dialog'
import { PendingInvitations } from './pending-invitations'

function renderPiece(ui: React.ReactNode) {
  localStorage.setItem('sddg.mock.session', JSON.stringify({ email: 'dev@sddg.test', accessToken: 'mock-token:dev@sddg.test' }))
  const queryClient = createQueryClient()
  queryClient.setDefaultOptions({ queries: { retry: false }, mutations: { retry: false } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        {ui}
        <Toaster />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

afterEach(() => clearToasts())

describe('FR24a invite dialog', () => {
  it('sends an invitation with the chosen role and confirms it', async () => {
    seedProject()
    const user = userEvent.setup()
    renderPiece(<InviteDialog projectId="pr_1" projectName="Library system" trigger={<Button>Invite</Button>} />)

    await user.click(screen.getByRole('button', { name: 'Invite' }))
    expect(await screen.findByText('Invite to Library system')).toBeInTheDocument()
    expect(screen.getByText(/It expires in 7 days/)).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Viewer' })).toHaveAttribute('aria-checked', 'true') // Viewer by default

    await user.type(screen.getByLabelText('Email address'), 'Priya@Example.com')
    await user.click(screen.getByRole('radio', { name: 'Editor' }))
    await user.click(screen.getByRole('button', { name: 'Send invite' }))

    expect(await screen.findByText('Invitation sent to priya@example.com.')).toBeInTheDocument()
    const sent = getDb().collab.invitations
    expect(sent).toHaveLength(1)
    expect(sent[0]).toMatchObject({ email: 'priya@example.com', role: 'editor', project_id: 'pr_1' })
    const days = Math.round((new Date(sent[0].expires_at).getTime() - new Date(sent[0].created_at).getTime()) / 86_400_000)
    expect(days).toBe(7)
  })

  it('shows the server message when the person already has an open invitation', async () => {
    seedProject()
    seedInvitation({ email: 'priya@example.com' })
    const user = userEvent.setup()
    renderPiece(<InviteDialog projectId="pr_1" projectName="Library system" trigger={<Button>Invite</Button>} />)
    await user.click(screen.getByRole('button', { name: 'Invite' }))
    await user.type(await screen.findByLabelText('Email address'), 'priya@example.com')
    await user.click(screen.getByRole('button', { name: 'Send invite' }))
    expect(await screen.findByText(/already has an open invitation/)).toBeInTheDocument()
    expect(getDb().collab.invitations).toHaveLength(1)
  })

  it('refuses an address the server does not accept', async () => {
    seedProject()
    const user = userEvent.setup()
    renderPiece(<InviteDialog projectId="pr_1" projectName="Library system" trigger={<Button>Invite</Button>} />)
    await user.click(screen.getByRole('button', { name: 'Invite' }))
    // The field is type=email, so the browser stops "priya" by itself; "priya@example" gets past it and the
    // server has the last word (NFR: never trust the browser's check).
    await user.type(await screen.findByLabelText('Email address'), 'priya@example')
    await user.click(screen.getByRole('button', { name: 'Send invite' }))
    expect(await screen.findByText('Enter a valid email address.')).toBeInTheDocument()
    expect(getDb().collab.invitations).toHaveLength(0)
  })
})

describe('FR24a pending invitations', () => {
  it('lists an open invitation and revokes it', async () => {
    seedProject()
    seedInvitation({ email: 'priya@example.com', role: 'viewer', invited_by: 'dev@sddg.test' })
    const user = userEvent.setup()
    renderPiece(<PendingInvitations projectId="pr_1" canManage />)

    const card = await screen.findByRole('region', { name: /Pending invitations/ })
    expect(within(card).getByText('priya@example.com')).toBeInTheDocument()
    expect(within(card).getByText('Viewer')).toBeInTheDocument()
    expect(within(card).getByText('Expires in 7 days')).toBeInTheDocument()

    await user.click(within(card).getByRole('button', { name: 'Revoke' }))
    await waitFor(() => expect(getDb().collab.invitations[0].revoked_at).not.toBeNull())
    await waitFor(() => expect(screen.queryByText('priya@example.com')).not.toBeInTheDocument())
  })

  it('hides the link and revoke button from someone who cannot manage invitations', async () => {
    seedProject()
    seedInvitation({ email: 'priya@example.com' })
    renderPiece(<PendingInvitations projectId="pr_1" canManage={false} />)
    expect(await screen.findByText('priya@example.com')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Copy link/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Revoke' })).not.toBeInTheDocument()
  })
})
