import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { getDb } from '@/mocks/db'
import { renderApp } from '@/test/render'
import { seedDiagram, seedProject } from '@/test/seed'

describe('NFR4a login required', () => {
  it('redirects a signed-out visitor to login', async () => {
    renderApp('/projects', { signedIn: false })
    expect(await screen.findByRole('heading', { name: 'Welcome back' })).toBeInTheDocument()
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
    await user.click((await screen.findAllByRole('button', { name: /new project/i }))[0])
    await user.type(screen.getByLabelText('Project name'), 'library system')
    await user.click(screen.getByRole('button', { name: 'Create project' }))
    expect(await screen.findByText(/already have a project called/i)).toBeInTheDocument()
  })

  it('lists archived projects apart, under Archived, and shows the client', async () => {
    seedProject()
    const at = new Date().toISOString()
    getDb().projects.push({
      id: 'pr_2', name: 'Old catalogue', owner: 'dev@sddg.test', created_at: at, updated_at: at, confirmed_at: null,
      client_name: 'Acme Libraries', archived_at: at, archived_by: 'dev@sddg.test',
    })
    renderApp('/projects')
    const archived = await screen.findByRole('region', { name: 'Archived' })
    expect(within(archived).getByText('Old catalogue')).toBeInTheDocument()
    expect(within(archived).getByText('Archived', { selector: 'span' })).toBeInTheDocument()
    expect(within(archived).getByText(/Acme Libraries/)).toBeInTheDocument()
    const active = screen.getByRole('list', { name: 'Active projects' })
    expect(within(active).getByText('Library system')).toBeInTheDocument()
    expect(within(active).queryByText('Old catalogue')).not.toBeInTheDocument()
  })
})

describe('NFR5d AI consent before first submission', () => {
  it('sends nothing until the user agrees', async () => {
    seedProject()
    const user = userEvent.setup()
    renderApp('/projects/pr_1/input')
    await user.type(await screen.findByLabelText('Requirement text'), 'A member can reserve a book.')
    const extract = screen.getByRole('button', { name: 'Extract requirements' })
    await waitFor(() => expect(extract).toBeEnabled()) // waits for the consent status to load
    await user.click(extract)

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByRole('button', { name: 'Agree and extract' })).toBeDisabled()
    await user.click(within(dialog).getByRole('button', { name: /don.t send/i }))
    expect(getDb().jobs.filter((j) => j.payload)).toHaveLength(0)

    await user.click(screen.getByRole('button', { name: 'Extract requirements' }))
    const again = await screen.findByRole('dialog')
    await user.click(within(again).getByRole('checkbox'))
    await user.click(within(again).getByRole('button', { name: 'Agree and extract' }))

    await waitFor(() => expect(getDb().jobs.filter((j) => j.payload)).toHaveLength(1))
    expect(getDb().consent['dev@sddg.test'].version).toBe('2026-11-16')
    expect(await screen.findByRole('heading', { name: /Queued|Finding your requirements/ })).toBeInTheDocument()
  })
})

describe('requirements-first review', () => {
  it('editing a requirement clears the confirmation and the building blocks', async () => {
    seedProject({ confirmed: true })
    const user = userEvent.setup()
    renderApp('/projects/pr_1/review')
    expect(await screen.findByRole('button', { name: /Choose diagrams/ })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Edit R-001' }))
    const box = screen.getByLabelText('Requirement text')
    await user.clear(box)
    expect(screen.getByText('Requirement text can’t be empty.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
    await user.type(box, 'The librarian shall lend a book to a member.')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('The librarian shall lend a book to a member.')).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: /Confirm 1 requirement/ })).toBeInTheDocument()
    expect(getDb().items.pr_1).toHaveLength(0)
    expect(getDb().projects[0].confirmed_at).toBeNull()
  })

  it('adds and deletes requirements, then confirms', async () => {
    seedProject()
    const user = userEvent.setup()
    renderApp('/projects/pr_1/review')
    await user.click(await screen.findByRole('button', { name: /Add requirement/ }))
    await user.type(screen.getByLabelText('New requirement'), 'A member can renew a book once.{Enter}')
    expect(await screen.findByText('A member can renew a book once.')).toBeInTheDocument()
    expect(getDb().statements.pr_1.map((s) => s.ref)).toEqual(['R-001', 'R-002'])
    await user.click(screen.getByRole('button', { name: 'Delete R-002' }))
    await user.click(screen.getByRole('button', { name: 'Delete R-002' }))
    await waitFor(() => expect(getDb().statements.pr_1).toHaveLength(1))
    await user.click(await screen.findByRole('button', { name: /Confirm 1 requirement/ }))
    await waitFor(() => expect(getDb().projects[0].confirmed_at).not.toBeNull())
  })

  it('the server rejects generation when the requirements are not confirmed', async () => {
    seedProject()
    const res = await fetch('http://localhost/api/v1/projects/pr_1/generations', {
      method: 'POST',
      headers: { Authorization: 'Bearer mock-token:dev@sddg.test', 'Content-Type': 'application/json' },
      body: JSON.stringify({ diagram_types: ['use_case'] }),
    })
    expect(res.status).toBe(409)
  })

  it('shows Choose diagrams as locked until confirmed', async () => {
    seedProject()
    renderApp('/projects/pr_1/generate')
    expect(await screen.findByText('Confirm the requirements first')).toBeInTheDocument()
  })

  it('an item fix (optional check) marks it user-edited and keeps the confirmation', async () => {
    seedDiagram()
    const user = userEvent.setup()
    renderApp('/projects/pr_1/items')
    await user.click(await screen.findByRole('button', { name: 'Edit Librarian' }))
    const name = screen.getByLabelText('Name')
    await user.clear(name)
    await user.type(name, 'Head librarian')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(await screen.findByText('Head librarian')).toBeInTheDocument()
    expect(screen.getByText('Edited by you')).toBeInTheDocument()
    expect(getDb().items.pr_1[0].origin).toBe('user-edited')
    expect(getDb().projects[0].confirmed_at).not.toBeNull()
    expect(screen.getByRole('button', { name: /Redraw 1 diagram/ })).toBeInTheDocument()
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

describe('requirement flags (issue #34)', () => {
  it('apply fix rewrites the requirement and resolves the flag', async () => {
    seedProject({ flagged: true })
    const user = userEvent.setup()
    renderApp('/projects/pr_1/review')
    await user.click(await screen.findByRole('button', { name: /1 open flags on R-002/ }))
    const drawer = await screen.findByRole('dialog')
    expect(within(drawer).getByText('quickly')).toBeInTheDocument() // trigger_text is highlighted
    await user.click(within(drawer).getByRole('button', { name: 'Apply fix' }))
    await waitFor(() => expect(getDb().statements.pr_1[1].text).toBe('The system shall respond within 2 seconds.'))
    expect(getDb().flags.pr_1[0].status).toBe('resolved')
    expect(await within(drawer).findByText('No open flags. Nice and clear.')).toBeInTheDocument()
  })

  it('an answer resolves the flag without changing the text', async () => {
    seedProject({ flagged: true })
    const user = userEvent.setup()
    renderApp('/projects/pr_1/review')
    await user.click(await screen.findByRole('button', { name: /Go through flags/ }))
    const drawer = await screen.findByRole('dialog')
    await user.type(await within(drawer).findByLabelText('Your answer'), 'Under 2 seconds')
    await user.click(within(drawer).getByRole('button', { name: /Save answer/ }))
    await waitFor(() => expect(getDb().flags.pr_1[0]).toMatchObject({ status: 'resolved', answer: 'Under 2 seconds' }))
    expect(getDb().statements.pr_1[1].text).toBe('The system should respond quickly.')
  })
})
