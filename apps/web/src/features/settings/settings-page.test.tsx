/** Project settings (Feature 3.1): the owner renames, sets the client, archives, reopens and deletes; members cannot. */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { env } from '@/lib/env'
import { getDb, projectView } from '@/mocks/db'
import { server } from '@/mocks/node'
import { renderApp } from '@/test/render'
import { seedProject } from '@/test/seed'

const header = () => screen.getByRole('heading', { level: 1 })

describe('Project settings', () => {
  it('lets the owner rename the project, and the header shows the new name', async () => {
    seedProject()
    const user = userEvent.setup()
    renderApp('/projects/pr_1/settings')
    const name = await screen.findByLabelText('Project name')
    expect(screen.getByRole('link', { name: 'Settings' })).toBeInTheDocument()
    await user.clear(name)
    await user.type(name, 'Library v2')
    await user.click(screen.getByRole('button', { name: 'Rename' }))
    await waitFor(() => expect(header()).toHaveTextContent('Library v2'))
    expect(getDb().projects[0].name).toBe('Library v2')
  })

  it('sets the client name and e-mail, then clears them', async () => {
    seedProject()
    const user = userEvent.setup()
    renderApp('/projects/pr_1/settings')
    await user.type(await screen.findByLabelText('Client name'), 'Acme Libraries')
    await user.type(screen.getByLabelText('Contact e-mail'), 'Ops@Acme.test')
    await user.click(screen.getByRole('button', { name: 'Save client' }))
    await waitFor(() => expect(getDb().projects[0]).toMatchObject({ client_name: 'Acme Libraries', contact_email: 'ops@acme.test' }))
    await waitFor(() => expect(screen.getByLabelText('Contact e-mail')).toHaveValue('ops@acme.test'))

    await user.clear(screen.getByLabelText('Client name'))
    await user.clear(screen.getByLabelText('Contact e-mail'))
    await user.click(screen.getByRole('button', { name: 'Save client' }))
    await waitFor(() => expect(getDb().projects[0]).toMatchObject({ client_name: null, contact_email: null }))
  })

  it('archives the project and reopens it', async () => {
    seedProject()
    const user = userEvent.setup()
    renderApp('/projects/pr_1/settings')
    await user.click(await screen.findByRole('button', { name: 'Archive project' }))
    expect(await screen.findByRole('button', { name: 'Reopen project' })).toBeInTheDocument()
    expect(within(header().parentElement!).getByText('Archived')).toBeInTheDocument()
    expect(screen.getByText(/by dev@sddg\.test/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Reopen project' }))
    expect(await screen.findByRole('button', { name: 'Archive project' })).toBeInTheDocument()
    expect(within(header().parentElement!).queryByText('Archived')).not.toBeInTheDocument()
  })

  it('deletes only after the exact name is typed, then goes back to the project list', async () => {
    seedProject()
    const user = userEvent.setup()
    const { router } = renderApp('/projects/pr_1/settings')
    await user.click(await screen.findByRole('button', { name: 'Delete project…' }))
    const dialog = screen.getByRole('dialog')
    const confirm = within(dialog).getByRole('button', { name: 'Delete project' })
    const input = within(dialog).getByLabelText(/Type the project name/)
    expect(confirm).toBeDisabled()
    await user.type(input, 'library system')
    expect(confirm).toBeDisabled()
    await user.clear(input)
    await user.type(input, 'Library system')
    expect(confirm).toBeEnabled()
    await user.click(confirm)
    await waitFor(() => expect(router.state.location.pathname).toBe('/projects'))
    expect(await screen.findByText('No projects yet')).toBeInTheDocument()
    expect(getDb().projects).toHaveLength(0)
  })

  it('shows a member who is not the owner a notice, no forms and no Settings link', async () => {
    seedProject()
    server.use(
      http.get(`${env.apiUrl.replace(/\/$/, '')}/projects/:project_id`, () =>
        HttpResponse.json({ ...projectView(getDb().projects[0]), is_owner: false }),
      ),
    )
    renderApp('/projects/pr_1/settings')
    expect(await screen.findByText('Only the project owner can change these settings.')).toBeInTheDocument()
    expect(screen.queryByLabelText('Project name')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Client name')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Archive|Reopen|Delete|Rename|Save client/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Settings' })).not.toBeInTheDocument()
  })
})
