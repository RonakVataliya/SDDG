import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderApp } from '@/test/render'
import { seedDiagram } from '@/test/seed'
import { markExported } from './exported'

const SEARCH = '/projects/pr_1/search'

async function searchFor(text: string) {
  const user = userEvent.setup()
  const box = await screen.findByLabelText('Search')
  await user.type(box, `${text}{Enter}`)
  return user
}

describe('FR26 search page', () => {
  it('finds a diagram by one of its element labels', async () => {
    seedDiagram() // diagram "Library system · Use Case" containing "Issue book"
    const user = userEvent.setup()
    renderApp(SEARCH)
    await user.type(await screen.findByLabelText('Search'), 'issue book')
    expect(await screen.findByText('Library system · Use Case')).toBeInTheDocument()
  })

  it('opens a diagram when its exact ID is entered', async () => {
    seedDiagram()
    const { router } = renderApp(SEARCH)
    await searchFor('dg_1')
    await waitFor(() => expect(router.state.location.pathname).toBe('/projects/pr_1/diagrams/dg_1'))
  })

  it('opens a requirement when its exact ID is entered', async () => {
    seedDiagram()
    const { router } = renderApp(SEARCH)
    await searchFor('R-001')
    await waitFor(() => expect(router.state.location.pathname).toBe('/projects/pr_1/review'))
    expect(router.state.location.search).toBe('?requirement=R-001')
  })

  it('tells the user to press Enter while an exact ID is typed, instead of showing No results', async () => {
    seedDiagram()
    const user = userEvent.setup()
    renderApp(SEARCH)
    await user.type(await screen.findByLabelText('Search'), 'R-001')
    expect(await screen.findByText('Press Enter to open R-001')).toBeInTheDocument()
    expect(screen.queryByText('No results')).not.toBeInTheDocument()
  })

  it('says Not found for an ID that does not exist', async () => {
    seedDiagram()
    const { router } = renderApp(SEARCH)
    await searchFor('R-999')
    expect(await screen.findByText('Not found')).toBeInTheDocument()
    expect(router.state.location.pathname).toBe(SEARCH)
  })

  it('shows an empty state when nothing matches', async () => {
    seedDiagram()
    const user = userEvent.setup()
    renderApp(SEARCH)
    await user.type(await screen.findByLabelText('Search'), 'zzz')
    expect(await screen.findByText('No results')).toBeInTheDocument()
  })

  it('shows an empty state for a diagram type with no diagrams', async () => {
    seedDiagram()
    const user = userEvent.setup()
    renderApp(SEARCH)
    await user.click(await screen.findByLabelText('Class'))
    expect(await screen.findByText(/No Class diagrams match/)).toBeInTheDocument()
  })

  it('filters by Exported', async () => {
    seedDiagram()
    markExported('dg_1')
    const user = userEvent.setup()
    renderApp(SEARCH)
    await user.click(await screen.findByLabelText('Exported'))
    expect(await screen.findByText('Library system · Use Case')).toBeInTheDocument()
    expect(screen.queryByText('Librarian')).not.toBeInTheDocument()
  })
})
