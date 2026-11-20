/** Members page (FR24c): the list, what each role can do, changing a role, removing someone, and never losing the
 * last Owner. */
import { configure, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { env } from '@/lib/env'
import { getDb, membersOf, projectView, save } from '@/mocks/db'
import { server } from '@/mocks/node'
import { renderApp } from '@/test/render'
import { seedInvitation, seedProject } from '@/test/seed'

// The invitation round trips go through several mock requests; give the waits the same budget as invitations.test.
configure({ asyncUtilTimeout: 5000 })
vi.setConfig({ testTimeout: 20000 })

function seedTeam() {
  seedProject()
  const at = new Date().toISOString()
  membersOf('pr_1').push(
    { email: 'priya@sddg.test', role: 'editor', joined_at: at },
    { email: 'karan@sddg.test', role: 'viewer', joined_at: at },
  )
  save()
}

const row = (name: string | RegExp) => screen.getByRole('row', { name })

describe('Members page', () => {
  it('lists everyone with their role, and explains each role', async () => {
    seedTeam()
    renderApp('/projects/pr_1/members')
    expect(await screen.findByText('3 people in this project.')).toBeInTheDocument()
    expect(within(row(/dev@sddg\.test/)).getByText('(you)')).toBeInTheDocument()
    expect(within(row(/dev@sddg\.test/)).getByText('Created the project')).toBeInTheDocument()
    expect(screen.getByLabelText('Role for priya@sddg.test')).toHaveValue('editor')
    expect(screen.getByLabelText('Role for karan@sddg.test')).toHaveValue('viewer')
    const matrix = screen.getByRole('complementary', { name: 'What each role can do' })
    const edit = within(matrix).getByRole('row', { name: /Edit requirements and diagrams/ })
    expect(within(edit).getAllByLabelText('Yes')).toHaveLength(2) // Editor and Owner, not Viewer
    expect(screen.getByRole('link', { name: 'Members' })).toBeInTheDocument()
  })

  it('lets the Owner change a role', async () => {
    seedTeam()
    const user = userEvent.setup()
    renderApp('/projects/pr_1/members')
    await user.selectOptions(await screen.findByLabelText('Role for karan@sddg.test'), 'editor')
    await waitFor(() => expect(getDb().members?.pr_1.find((m) => m.email === 'karan@sddg.test')?.role).toBe('editor'))
    expect(screen.getByLabelText('Role for karan@sddg.test')).toHaveValue('editor')
  })

  it('refuses to demote the last Owner and says why', async () => {
    seedTeam()
    const user = userEvent.setup()
    renderApp('/projects/pr_1/members')
    await user.selectOptions(await screen.findByLabelText('Role for dev@sddg.test'), 'viewer')
    expect(await screen.findByText(/needs at least one Owner/)).toBeInTheDocument()
    expect(getDb().members?.pr_1[0].role).toBe('owner')
  })

  it('removes a member after confirming', async () => {
    seedTeam()
    const user = userEvent.setup()
    renderApp('/projects/pr_1/members')
    await user.click(await screen.findByRole('button', { name: 'Remove priya@sddg.test' }))
    expect(screen.getByRole('heading', { name: 'Remove priya@sddg.test?' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Remove' }))
    await waitFor(() => expect(screen.queryByText('priya@sddg.test')).not.toBeInTheDocument())
    expect(getDb().members?.pr_1.map((m) => m.email)).toEqual(['dev@sddg.test', 'karan@sddg.test'])
  })
})

/** The signed-in user's role on pr_1 as the project view reports it (the mock owner sees the project as this role). */
function signedInAs(role: 'editor' | 'viewer') {
  server.use(
    http.get(`${env.apiUrl.replace(/\/$/, '')}/projects/:project_id`, () =>
      HttpResponse.json({ ...projectView(getDb().projects[0]), role, is_owner: false }),
    ),
  )
}

describe('Members page: invitations (FR24a)', () => {
  it('lets an Owner invite someone, then copy or revoke the pending invitation', async () => {
    seedTeam()
    const user = userEvent.setup()
    renderApp('/projects/pr_1/members')
    expect(await screen.findByRole('heading', { name: 'Members 3' })).toBeInTheDocument()
    expect(screen.getByText('3 people in this project.')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Invite' }))
    expect(await screen.findByText('Invite to Library system')).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Viewer' })).toHaveAttribute('aria-checked', 'true')
    await user.type(screen.getByLabelText('Email address'), 'meera@sddg.test')
    await user.click(screen.getByRole('radio', { name: 'Editor' }))
    await user.click(screen.getByRole('button', { name: 'Send invite' }))

    const pending = await screen.findByRole('region', { name: 'Pending invitations 1' })
    expect(within(pending).getByText('meera@sddg.test')).toBeInTheDocument()
    expect(within(pending).getByText('Editor')).toBeInTheDocument()
    expect(within(pending).getByText('Expires in 7 days')).toBeInTheDocument()
    expect(within(pending).getByRole('button', { name: 'Copy link' })).toBeInTheDocument()

    await user.click(within(pending).getByRole('button', { name: 'Revoke' }))
    await waitFor(() => expect(screen.queryByRole('region', { name: /Pending invitations/ })).not.toBeInTheDocument())
    expect(getDb().collab.invitations[0].revoked_at).toBeTruthy()
  })

  it.each(['editor', 'viewer'] as const)('shows an %s no Invite button and the pending invitations read-only', async (role) => {
    seedTeam()
    seedInvitation({ email: 'meera@sddg.test' })
    signedInAs(role)
    renderApp('/projects/pr_1/members')
    const pending = await screen.findByRole('region', { name: 'Pending invitations 1' })
    expect(within(pending).getByText('meera@sddg.test')).toBeInTheDocument()
    expect(within(pending).queryByRole('button', { name: 'Copy link' })).not.toBeInTheDocument()
    expect(within(pending).queryByRole('button', { name: 'Revoke' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Invite' })).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Members 3' })).toBeInTheDocument()
  })
})
