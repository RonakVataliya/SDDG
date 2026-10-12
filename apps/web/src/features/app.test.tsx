import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { getDb } from '@/mocks/db'
import { renderApp } from '@/test/render'
import { seedDiagram, seedProject } from '@/test/seed'

describe('NFR4a login required', () => {
  it('redirects a signed-out visitor to login', async () => {
    renderApp('/projects', { signedIn: false })
    expect(await screen.findByRole('heading', { name: 'Log in' })).toBeInTheDocument()
  })
})

describe('X14 sign-up password rules', () => {
  it('blocks a weak password and a mismatched confirmation, then accepts a strong one', async () => {
    const user = userEvent.setup()
    const { router } = renderApp('/signup', { signedIn: false })
    await user.type(await screen.findByLabelText('Email'), 'new@sddg.test')
    await user.type(screen.getByLabelText('Password'), 'password')
    await user.type(screen.getByLabelText('Confirm password'), 'passwort')
    await user.click(screen.getByRole('button', { name: 'Create account' }))

    expect(screen.getByText('Your password does not meet every rule below.')).toBeInTheDocument()
    expect(screen.getByText('Passwords do not match.')).toBeInTheDocument()
    expect(within(screen.getByRole('list', { name: 'Password rules' })).getByText(/At least 8 characters/)).toHaveTextContent('(done)')
    expect(router.state.location.pathname).toBe('/signup')

    await user.clear(screen.getByLabelText('Password'))
    await user.type(screen.getByLabelText('Password'), 'Library#42')
    await user.clear(screen.getByLabelText('Confirm password'))
    await user.type(screen.getByLabelText('Confirm password'), 'Library#42')
    expect(screen.getByText('Passwords match')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Create account' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/verify-email'))
  })
})

describe('FR3c / FR3a projects', () => {
  it('shows the empty state, then creates a project and opens it', async () => {
    const user = userEvent.setup()
    const { router } = renderApp('/projects')
    expect(await screen.findByText('No projects yet')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /create your first project/i }))
    await user.type(screen.getByLabelText('Project name'), 'Library system')
    await user.click(screen.getByRole('button', { name: 'Create project' }))

    await waitFor(() => expect(router.state.location.pathname).toMatch(/^\/projects\/pr_\w+\/input$/))
    expect(getDb().projects[0].name).toBe('Library system')
  })

  it('shows the server message for a duplicate name', async () => {
    seedProject()
    const user = userEvent.setup()
    renderApp('/projects')
    await user.click(await screen.findByRole('button', { name: /new project/i }))
    await user.type(screen.getByLabelText('Project name'), 'library system')
    await user.click(screen.getByRole('button', { name: 'Create project' }))
    expect(await screen.findByText(/already have a project called/i)).toBeInTheDocument()
  })
})

describe('NFR5d AI consent before first submission', () => {
  it('sends nothing until the user agrees', async () => {
    seedProject()
    const user = userEvent.setup()
    renderApp('/projects/pr_1/input')
    await user.type(await screen.findByLabelText('Requirement text'), 'A member can reserve a book.')
    const extract = screen.getByRole('button', { name: 'Extract items' })
    await waitFor(() => expect(extract).toBeEnabled()) // waits for the consent status to load
    await user.click(extract)

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByRole('button', { name: 'Agree and extract' })).toBeDisabled()
    await user.click(within(dialog).getByRole('button', { name: /don.t send/i }))
    expect(getDb().jobs.filter((j) => j.payload)).toHaveLength(0)

    await user.click(screen.getByRole('button', { name: 'Extract items' }))
    const again = await screen.findByRole('dialog')
    await user.click(within(again).getByRole('checkbox'))
    await user.click(within(again).getByRole('button', { name: 'Agree and extract' }))

    await waitFor(() => expect(getDb().jobs.filter((j) => j.payload)).toHaveLength(1))
    expect(getDb().consent['dev@sddg.test'].version).toBe('2026-09-01')
    expect(await screen.findByText('Reading your requirements')).toBeInTheDocument()
  })
})

describe('FR5b / FR5e review', () => {
  it('editing an item marks it user-edited and clears the confirmation', async () => {
    seedProject({ confirmed: true })
    const user = userEvent.setup()
    renderApp('/projects/pr_1/review')

    expect(await screen.findByRole('button', { name: 'Continue to Generate' })).toBeInTheDocument()
    await user.click(await screen.findByRole('button', { name: 'Edit Librarian' }))
    const name = screen.getByLabelText('Name')
    await user.clear(name)
    await user.type(name, 'Head librarian')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))

    expect(await screen.findByText('Head librarian')).toBeInTheDocument()
    expect(screen.getByText('Edited by you')).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: 'Confirm extracted items' })).toBeInTheDocument()
    expect(getDb().items.pr_1[0].origin).toBe('user-edited')
  })

  it('the server rejects generation when items are not confirmed', async () => {
    seedProject()
    const res = await fetch('http://localhost/api/v1/projects/pr_1/generations', {
      method: 'POST',
      headers: { Authorization: 'Bearer mock-token:dev@sddg.test', 'Content-Type': 'application/json' },
      body: JSON.stringify({ diagram_types: ['use_case'] }),
    })
    expect(res.status).toBe(409)
  })

  it('shows Generate as locked until confirmed', async () => {
    seedProject()
    renderApp('/projects/pr_1/generate')
    expect(await screen.findByText('Confirm the extracted items first')).toBeInTheDocument()
  })
})

describe('diagram edits by chat', () => {
  it('applies a plain-language change as a new version and keeps the old one', async () => {
    seedDiagram()
    const user = userEvent.setup()
    const { router } = renderApp('/projects/pr_1/diagrams/dg_1')
    await user.type(await screen.findByLabelText('Describe a change to the diagram'), 'rename the issue book to Lend a book')
    await user.click(screen.getByRole('button', { name: 'Apply change' }))

    await waitFor(() => expect(router.state.location.pathname).not.toBe('/projects/pr_1/diagrams/dg_1'))
    const next = getDb().diagrams.at(-1)!
    expect(router.state.location.pathname).toBe(`/projects/pr_1/diagrams/${next.id}`)
    expect(next).toMatchObject({ parent_id: 'dg_1', instruction: 'rename the issue book to Lend a book' })
    expect(next.model!.cases[0].name).toBe('Lend a book')
    expect(getDb().diagrams[0].model!.cases[0].name).toBe('Issue book')
    expect(await screen.findByText('Version 2, showing now')).toBeInTheDocument()
  })

  it('shows why a change could not be made and keeps the text to fix', async () => {
    seedDiagram()
    const user = userEvent.setup()
    renderApp('/projects/pr_1/diagrams/dg_1')
    const box = await screen.findByLabelText('Describe a change to the diagram')
    await user.type(box, 'make it prettier')
    await user.click(screen.getByRole('button', { name: 'Apply change' }))

    expect(await screen.findByText(/didn.t understand that change/)).toBeInTheDocument()
    expect(box).toHaveValue('make it prettier')
    expect(getDb().diagrams).toHaveLength(1)
  })
})
