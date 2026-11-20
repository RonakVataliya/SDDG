/** Members page (FR24c): the list, what each role can do, changing a role, removing someone, and never losing the
 * last Owner. */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { getDb, membersOf, save } from '@/mocks/db'
import { renderApp } from '@/test/render'
import { seedProject } from '@/test/seed'

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
