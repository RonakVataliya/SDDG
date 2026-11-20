/** Requirement coverage (Feature 3.2): every requirement with the latest diagrams that represent it. */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { env } from '@/lib/env'
import { getDb, save } from '@/mocks/db'
import { server } from '@/mocks/node'
import { renderApp } from '@/test/render'
import { seedDiagram, seedProject } from '@/test/seed'

const source = { document: 'Pasted text', page: null, paragraph: 2 }

describe('Requirement coverage', () => {
  it('lists every requirement with its covering diagrams, and the totals', async () => {
    seedDiagram() // dg_1 draws it_1 / it_2, both from st_1 (R-001)
    getDb().statements.pr_1.push({ id: 'st_2', ref: 'R-002', text: 'Members shall reserve a book.', label: 'FR', source })
    save()
    renderApp('/projects/pr_1/coverage')

    const covered = (await screen.findByText('The librarian shall issue a book to a member.')).closest('li')!
    expect(within(covered).getByText('R-001')).toBeInTheDocument()
    expect(within(covered).getByRole('link', { name: /Use Case.*v1/ })).toHaveAttribute('href', '/projects/pr_1/diagrams/dg_1')
    expect(within(covered).queryByText('Not represented')).not.toBeInTheDocument()

    const missing = screen.getByText('Members shall reserve a book.').closest('li')!
    expect(within(missing).getByText('R-002')).toBeInTheDocument()
    expect(within(missing).getByText('Not represented')).toBeInTheDocument()
    expect(within(missing).queryByRole('link')).not.toBeInTheDocument()

    expect(screen.getByTestId('coverage-totals')).toHaveTextContent(
      '2 requirements · 1 covered by a diagram · 1 not represented · 0 with open issues',
    )
  })

  it('shows the empty state for a project with no requirements', async () => {
    seedProject()
    getDb().statements.pr_1 = []
    save()
    renderApp('/projects/pr_1/coverage')
    expect(await screen.findByText('No requirements yet')).toBeInTheDocument()
  })

  it('is linked from the workspace header', async () => {
    seedProject()
    const user = userEvent.setup()
    const { router } = renderApp('/projects/pr_1/search')
    await user.click(await screen.findByRole('link', { name: 'Coverage' }))
    expect(router.state.location.pathname).toBe('/projects/pr_1/coverage')
    expect(await screen.findByRole('heading', { name: 'Requirement coverage' })).toBeInTheDocument()
  })
})

describe('Project report (Feature 3.3)', () => {
  const originalCreate = URL.createObjectURL
  const originalRevoke = URL.revokeObjectURL
  const auth: (string | null)[] = []
  const blobs: Blob[] = []

  beforeEach(() => {
    auth.length = 0
    blobs.length = 0
    server.events.on('request:start', ({ request }) => {
      if (request.url.endsWith('/projects/pr_1/report.html')) auth.push(request.headers.get('Authorization'))
    })
    // jsdom has no object URLs, window.open or print.
    URL.createObjectURL = vi.fn((b: Blob | MediaSource) => (blobs.push(b as Blob), 'blob:report'))
    URL.revokeObjectURL = vi.fn()
  })

  afterEach(() => {
    server.events.removeAllListeners()
    URL.createObjectURL = originalCreate
    URL.revokeObjectURL = originalRevoke
    vi.restoreAllMocks()
  })

  const fakeTab = () => ({ location: { href: '' }, opener: window as unknown, close: vi.fn() })

  it('"Open report" fetches the report with the token and opens it in a new tab', async () => {
    seedProject()
    const tab = fakeTab()
    const open = vi.spyOn(window, 'open').mockReturnValue(tab as unknown as Window)
    const user = userEvent.setup()
    renderApp('/projects/pr_1/coverage')
    await user.click(await screen.findByRole('button', { name: 'Open report' }))

    expect(open).toHaveBeenCalledTimes(1) // opened in the click itself, before the request, so pop-up blockers allow it
    await waitFor(() => expect(tab.location.href).toBe('blob:report'))
    expect(auth).toEqual([expect.stringMatching(/^Bearer /)])
    expect(blobs[0].type).toMatch(/^text\/html/)
    expect(await blobs[0].text()).toContain('Library system – project report')
    expect(tab.opener).toBeNull()
  })

  it('"Download PDF" prints the report from a hidden iframe, not the app', async () => {
    seedProject()
    const appPrint = vi.spyOn(window, 'print').mockImplementation(() => {})
    const framePrint = vi.fn()
    const append = document.body.appendChild.bind(document.body)
    vi.spyOn(document.body, 'appendChild').mockImplementation(<T extends Node>(node: T) => {
      append(node)
      if (node instanceof HTMLIFrameElement) {
        expect(node.getAttribute('sandbox')).not.toContain('allow-scripts')
        node.contentWindow!.print = framePrint
        setTimeout(() => node.dispatchEvent(new Event('load'))) // jsdom does not load blob: URLs
      }
      return node
    })
    const user = userEvent.setup()
    renderApp('/projects/pr_1/coverage')
    await user.click(await screen.findByRole('button', { name: 'Download PDF' }))

    await waitFor(() => expect(framePrint).toHaveBeenCalledTimes(1))
    expect(auth).toEqual([expect.stringMatching(/^Bearer /)])
    expect(appPrint).not.toHaveBeenCalled()
    expect(screen.getByText(/Save as PDF/)).toBeInTheDocument()

    document.querySelector('iframe')!.contentWindow!.dispatchEvent(new Event('afterprint'))
    expect(document.querySelector('iframe')).toBeNull()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:report')
  })

  it('shows the error and opens or prints nothing when the report fails', async () => {
    seedProject()
    server.use(http.get(`${env.apiUrl.replace(/\/$/, '')}/projects/:project_id/report.html`, () => HttpResponse.json({ detail: 'The report could not be built.' }, { status: 500 })))
    const tab = fakeTab()
    vi.spyOn(window, 'open').mockReturnValue(tab as unknown as Window)
    const appPrint = vi.spyOn(window, 'print').mockImplementation(() => {})
    const user = userEvent.setup()
    renderApp('/projects/pr_1/coverage')

    await user.click(await screen.findByRole('button', { name: 'Open report' }))
    expect(await screen.findByText('The report could not be built.')).toBeInTheDocument()
    expect(tab.close).toHaveBeenCalled()
    expect(tab.location.href).toBe('')

    await user.click(screen.getByRole('button', { name: 'Download PDF' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Download PDF' })).toBeEnabled())
    expect(screen.getByText('The report could not be built.')).toBeInTheDocument()
    expect(document.querySelector('iframe')).toBeNull()
    expect(appPrint).not.toHaveBeenCalled()
    expect(URL.createObjectURL).not.toHaveBeenCalled()
  })
})
