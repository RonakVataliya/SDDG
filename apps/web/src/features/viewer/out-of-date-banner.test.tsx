import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { getDb, markOutOfDate, save } from '@/mocks/db'
import { renderApp } from '@/test/render'
import { seedDiagram } from '@/test/seed'

describe('FR17c out-of-date diagrams', () => {
  it('shows the badge and the prompt after a requirement changed, and Later hides only the prompt', async () => {
    seedDiagram()
    markOutOfDate('pr_1')
    save()
    const user = userEvent.setup()
    renderApp('/projects/pr_1/diagrams/dg_1')

    const banner = await screen.findByText('Requirements changed')
    expect(banner.closest('[role]') ?? banner.parentElement).toHaveTextContent('Use Case diagram is out of date.')
    expect(screen.getByRole('link', { name: 'Regenerate now' })).toHaveAttribute('href', '/projects/pr_1/generate')
    // The badge is on the diagram's title and in the list.
    expect(within(await screen.findByRole('heading', { name: /Use Case diagram/ })).getByText('Out of date')).toBeInTheDocument()
    expect(within(screen.getByRole('navigation', { name: 'Your diagrams' })).getByText('Out of date')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Later' }))
    expect(screen.queryByText('Requirements changed')).not.toBeInTheDocument()
    expect(screen.getAllByText('Out of date').length).toBeGreaterThan(0) // never marked up to date by dismissing
  })

  it('sends you to Review first when the changed requirements are not confirmed again', async () => {
    seedDiagram()
    markOutOfDate('pr_1')
    getDb().projects[0].confirmed_at = null // an edit clears the confirmation
    save()
    renderApp('/projects/pr_1/diagrams/dg_1')
    expect(await screen.findByText(/Confirm the changed requirements first/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Regenerate now' })).toHaveAttribute('href', '/projects/pr_1/review')
  })

  it('clears once a new diagram of that type is generated, and shows nothing when nothing changed', async () => {
    seedDiagram()
    markOutOfDate('pr_1')
    const old = getDb().diagrams[0]
    getDb().diagrams.push({ ...old, id: 'dg_2', created_at: new Date(Date.now() + 1000).toISOString() }) // generated after the edit
    save()
    renderApp('/projects/pr_1/diagrams/dg_2')
    expect(await screen.findByRole('heading', { name: /Use Case diagram/ })).toBeInTheDocument()
    expect(screen.queryByText('Requirements changed')).not.toBeInTheDocument()
    expect(screen.queryByText('Out of date')).not.toBeInTheDocument()
  })
})
