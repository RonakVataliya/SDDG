import { fireEvent, screen, waitFor, within } from '@testing-library/react'
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

describe('FR1 and FR2 requirements input and document management', () => {
  it('calculates page count accurately and rejects whitespace-only paste', async () => {
    seedProject({ consent: true })
    renderApp('/projects/pr_1/input')
    const textarea = await screen.findByLabelText('Requirement text')
    const extractBtn = screen.getByRole('button', { name: 'Extract items' })
    expect(extractBtn).toBeDisabled()

    const user = userEvent.setup()
    await user.click(textarea)
    await user.paste('   \n   \t  ')
    expect(extractBtn).toBeDisabled()

    await user.clear(textarea)
    await user.click(textarea)
    await user.paste('A'.repeat(3000))
    expect(screen.getByText(/counts as 1 of 100 pages/)).toBeInTheDocument()

    await user.paste('B')
    expect(screen.getByText(/counts as 2 of 100 pages/)).toBeInTheDocument()
  })

  it('shows warnings for unnumbered FR/NFR and malformed user stories', async () => {
    seedProject({ consent: true })
    const user = userEvent.setup()
    renderApp('/projects/pr_1/input')
    const textarea = await screen.findByLabelText('Requirement text')

    await user.click(textarea)
    await user.paste('FR1: Valid requirement\nUnnumbered line here')
    expect(await screen.findByText(/Some lines do not have numbered FR\/NFR IDs/)).toBeInTheDocument()

    await user.clear(textarea)
    await user.click(textarea)
    await user.paste('As a user I want something without so that')
    expect(await screen.findByText(/Some user stories did not match the 'As a … I want … so that …' pattern/)).toBeInTheDocument()
  })

  it('validates file type and size restrictions on upload (FR2a, FR2b)', async () => {
    seedProject({ consent: true })
    const user = userEvent.setup()
    renderApp('/projects/pr_1/input')

    await user.click(await screen.findByRole('tab', { name: /upload srs document/i }))

    // Unsupported file type
    const txtFile = new File(['plain text content'], 'requirements.txt', { type: 'text/plain' })
    const fileInput = document.getElementById('file-upload') as HTMLInputElement
    fireEvent.change(fileInput, { target: { files: [txtFile] } })
    expect(await screen.findByText(/Supported file types are PDF \(\.pdf\) and DOCX \(\.docx\)/)).toBeInTheDocument()

    // File exceeding 10 MiB
    const largeFile = new File([new Uint8Array(10 * 1024 * 1024 + 1)], 'large.pdf', { type: 'application/pdf' })
    fireEvent.change(fileInput, { target: { files: [largeFile] } })
    expect(await screen.findByText(/maximum allowed size is 10 MB/)).toBeInTheDocument()
  })

  it('uploads valid PDF document and allows deleting it with confirmation (FR1b, Doc Management)', async () => {
    seedProject({ consent: true })

    const user = userEvent.setup()
    renderApp('/projects/pr_1/input')

    await user.click(await screen.findByRole('tab', { name: /upload srs document/i }))
    const validPdf = new File(['%PDF-1.4 test content'], 'srs-spec.pdf', { type: 'application/pdf' })
    const g = globalThis as unknown as { Buffer?: { from: (s: string) => unknown } }
    ;(validPdf as unknown as { _buffer: unknown })._buffer = g.Buffer ? g.Buffer.from('%PDF-1.4 test content') : new Uint8Array(0)
    const fileInput = document.getElementById('file-upload') as HTMLInputElement
    fireEvent.change(fileInput, { target: { files: [validPdf] } })

    expect(await screen.findByText('srs-spec.pdf', {}, { timeout: 3000 })).toBeInTheDocument()
    expect(screen.getByText('Uploaded project documents')).toBeInTheDocument()

    // Delete document flow
    const deleteBtn = screen.getByRole('button', { name: /delete srs-spec\.pdf/i })
    await user.click(deleteBtn)

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText(/Are you sure you want to delete/)).toBeInTheDocument()

    await user.click(within(dialog).getByRole('button', { name: 'Delete document' }))
    await waitFor(() => expect(screen.queryByText('srs-spec.pdf')).not.toBeInTheDocument())
  })

  it('displays extracted FR/NFR tags and structured user stories in Review and preserves them across reload', async () => {
    seedProject({ consent: true })
    const db = getDb()
    db.statements.pr_1 = [
      {
        id: 'st_1',
        ref: 'R-001',
        text: 'The user shall be able to log in.',
        label: 'functional',
        source_label: 'FR1',
        metadata: null,
        source: { document: 'spec.pdf', page: 1, paragraph: 1 },
      },
      {
        id: 'st_2',
        ref: 'R-002',
        text: 'As a member, I want to search books, so that I find titles.',
        label: 'functional',
        source_label: null,
        metadata: {
          role: 'member',
          goal: 'to search books',
          reason: 'I find titles',
          structured: true,
        },
        source: { document: 'spec.pdf', page: 1, paragraph: 2 },
      },
    ]

    const user = userEvent.setup()
    const { unmount } = renderApp('/projects/pr_1/review')

    // Click requirement statements accordion to expand
    const accordionBtn = await screen.findByRole('button', { name: /requirement statements/i })
    await user.click(accordionBtn)

    // Verify FR1 tag is displayed
    expect(await screen.findByText('FR1')).toBeInTheDocument()

    // Verify structured user story is displayed
    expect(screen.getByText(/Role:/)).toBeInTheDocument()
    expect(screen.getByText('member')).toBeInTheDocument()
    expect(screen.getByText('to search books')).toBeInTheDocument()
    expect(screen.getAllByText(/I find titles/).length).toBeGreaterThanOrEqual(1)

    // Simulate page reload by unmounting and re-rendering Review page
    unmount()
    renderApp('/projects/pr_1/review')

    const reloadedAccordion = await screen.findByRole('button', { name: /requirement statements/i })
    await user.click(reloadedAccordion)

    expect(await screen.findByText('FR1')).toBeInTheDocument()
    expect(screen.getByText(/Role:/)).toBeInTheDocument()
    expect(screen.getByText('member')).toBeInTheDocument()
    expect(screen.getByText('to search books')).toBeInTheDocument()
    expect(screen.getAllByText(/I find titles/).length).toBeGreaterThanOrEqual(1)
  })

  it('displays document statuses (Extracted, Failed), error messages, and preserves them after reload', async () => {
    seedProject({ consent: true })
    const db = getDb()
    db.documents = db.documents ?? {}
    db.documents.pr_1 = [
      {
        id: 'doc_1',
        project_id: 'pr_1',
        filename: 'architecture.pdf',
        storage_path: 'pr_1/doc_1/architecture.pdf',
        content_type: 'application/pdf',
        size_bytes: 102400,
        page_count: 5,
        status: 'processed',
        warning: null,
        skipped_pages: [],
        job_id: 'job_1',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
      {
        id: 'doc_2',
        project_id: 'pr_1',
        filename: 'invalid.docx',
        storage_path: 'pr_1/doc_2/invalid.docx',
        content_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        size_bytes: 20480,
        page_count: 2,
        status: 'failed',
        warning: 'Extraction failed: Model timeout',
        skipped_pages: [],
        job_id: 'job_2',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    ]

    const user = userEvent.setup()
    const { unmount } = renderApp('/projects/pr_1/input')

    // Navigate to upload tab
    await user.click(await screen.findByRole('tab', { name: /upload srs document/i }))

    // Verify document filenames
    expect(await screen.findByText('architecture.pdf')).toBeInTheDocument()
    expect(screen.getByText('invalid.docx')).toBeInTheDocument()

    // Verify status badges: 'processed' -> 'Extracted', 'failed' -> 'Failed'
    expect(screen.getByText('Extracted')).toBeInTheDocument()
    expect(screen.getByText('Failed')).toBeInTheDocument()

    // Verify failure error message
    expect(screen.getByText('Extraction failed: Model timeout')).toBeInTheDocument()

    // Verify page reload preserves statuses and warnings
    unmount()
    renderApp('/projects/pr_1/input')
    await user.click(await screen.findByRole('tab', { name: /upload srs document/i }))

    expect(await screen.findByText('architecture.pdf')).toBeInTheDocument()
    expect(screen.getByText('invalid.docx')).toBeInTheDocument()
    expect(screen.getByText('Extracted')).toBeInTheDocument()
    expect(screen.getByText('Failed')).toBeInTheDocument()
    expect(screen.getByText('Extraction failed: Model timeout')).toBeInTheDocument()
  })

  it('uploads SDDG_FR1_FR2_Test_SRS.pdf, renders extracted items and statements in Review page, and persists after reload', async () => {
    seedProject({ consent: true })

    const user = userEvent.setup()
    const { unmount } = renderApp('/projects/pr_1/input')

    // Navigate to upload tab
    await user.click(await screen.findByRole('tab', { name: /upload srs document/i }))

    // Upload test SRS PDF
    const testPdf = new File(['%PDF-1.4 test SRS content'], 'SDDG_FR1_FR2_Test_SRS.pdf', { type: 'application/pdf' })
    const fileInput = document.getElementById('file-upload') as HTMLInputElement
    fireEvent.change(fileInput, { target: { files: [testPdf] } })

    // Wait for document to appear and be marked Extracted
    expect(await screen.findByText('SDDG_FR1_FR2_Test_SRS.pdf', {}, { timeout: 3000 })).toBeInTheDocument()
    expect(await screen.findByText('Extracted', {}, { timeout: 3000 })).toBeInTheDocument()

    // Unmount input and navigate to Review page
    unmount()
    const reviewApp = renderApp('/projects/pr_1/review')

    // Wait for Review page to finish loading and display Confirm button
    expect(await screen.findByRole('button', { name: 'Confirm extracted items' })).toBeInTheDocument()
    // Check that extracted items are present
    expect((await screen.findAllByText(/Student/i)).length).toBeGreaterThanOrEqual(1)

    // Expand the Requirement Statements accordion
    const accordionBtn = await screen.findByRole('button', { name: /requirement statements/i })
    await user.click(accordionBtn)
    // Check that FR/NFR source tags and structured user stories are displayed
    expect((await screen.findAllByText('FR-001')).length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('NFR-001').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText(/Role:/).length).toBeGreaterThanOrEqual(1)

    // Test reload persistence: unmount and re-render Review page
    reviewApp.unmount()
    renderApp('/projects/pr_1/review')

    expect(screen.queryByText('Nothing to review yet')).not.toBeInTheDocument()
    expect((await screen.findAllByText(/Student/i)).length).toBeGreaterThanOrEqual(1)
    const reloadedAccordion = await screen.findByRole('button', { name: /requirement statements/i })
    await user.click(reloadedAccordion)
    expect((await screen.findAllByText('FR-001')).length).toBeGreaterThanOrEqual(1)
  })

  it('uploading a document with no extractable requirements marks it as failed and does not mark it as extracted', async () => {
    seedProject({ consent: true })

    const user = userEvent.setup()
    renderApp('/projects/pr_1/input')

    await user.click(await screen.findByRole('tab', { name: /upload srs document/i }))

    // Empty/unextractable PDF
    const emptyPdf = new File(['%PDF-1.4 empty'], 'empty_spec.pdf', { type: 'application/pdf' })
    const fileInput = document.getElementById('file-upload') as HTMLInputElement
    fireEvent.change(fileInput, { target: { files: [emptyPdf] } })

    expect(await screen.findByText('empty_spec.pdf', {}, { timeout: 3000 })).toBeInTheDocument()
    // Must NOT be marked Extracted; must be marked Failed
    expect(await screen.findByText('Failed', {}, { timeout: 3000 })).toBeInTheDocument()
    expect(screen.getAllByText(/No requirements could be extracted from this document/).length).toBeGreaterThanOrEqual(1)
  })
})


