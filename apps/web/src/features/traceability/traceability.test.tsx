import { configure, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { getDb, save, uid } from '@/mocks/db'
import { renderUseCase, type UseCaseModel } from '@/mocks/render'
import { renderApp } from '@/test/render'
import { seedDiagram } from '@/test/seed'

// A CI runner is slower than a laptop: the mock API needs more than the one second
// testing-library waits by default, so these waits get a real budget.
configure({ asyncUtilTimeout: 5000 })
vi.setConfig({ testTimeout: 20000 })

/** A hand-edited version of dg_1, with `change` applied to its model. */
function editVersion(change: (m: UseCaseModel) => UseCaseModel, instruction = 'Remove Issue book') {
  const root = getDb().diagrams[0]
  const model = change(structuredClone(root.model!))
  const row = { ...root, id: uid('dg'), created_at: new Date().toISOString(), parent_id: root.id, instruction, model, svg: renderUseCase(model) }
  getDb().diagrams.push(row)
  save()
  return row
}

describe('FR17d drift warning', () => {
  it('warns when an edit removes an element a requirement calls for', async () => {
    seedDiagram()
    const edited = editVersion((m) => ({ ...m, cases: m.cases.filter((c) => c.name !== 'Issue book') }))
    renderApp(`/projects/pr_1/diagrams/${edited.id}`)
    expect(await screen.findByText(/R-001 calls for "Issue book", but this version no longer has it\./)).toBeInTheDocument()
  })

  it('never warns on the version the generator drew', async () => {
    seedDiagram()
    editVersion((m) => ({ ...m, cases: m.cases.filter((c) => c.name !== 'Issue book') }))
    renderApp('/projects/pr_1/diagrams/dg_1')
    await screen.findAllByText(/Generated/)
    await waitFor(() => expect(screen.queryByText(/no longer has it/)).not.toBeInTheDocument())
  })

  it('says nothing when the edit keeps what the requirements ask for', async () => {
    seedDiagram()
    const edited = editVersion((m) => ({ ...m, cases: [...m.cases, { id: 'extra', name: 'Print receipt', assumed: true }] }), 'Add Print receipt')
    renderApp(`/projects/pr_1/diagrams/${edited.id}`)
    await screen.findByText(/Edited/)
    await waitFor(() => expect(screen.queryByText(/no longer matches/)).not.toBeInTheDocument())
  })
})

describe('FR17e naming consistency', () => {
  /** A second diagram that calls the same model item (it_1) something else. */
  function seedSecondDiagram(actorName: string, actorId = 'it_1') {
    const model: UseCaseModel = {
      system: 'Library system',
      actors: [{ id: actorId, name: actorName }],
      cases: [{ id: 'it_2', name: 'Issue book', assumed: false }],
      links: [],
    }
    getDb().diagrams.push({
      id: 'dg_2', project_id: 'pr_1', type: 'class', title: 'Library system · Class',
      created_at: new Date().toISOString(), parent_id: null, instruction: null, model, svg: renderUseCase(model),
    })
    save()
  }

  it('flags one item named two ways and applies the chosen name to every diagram', async () => {
    seedDiagram()
    seedSecondDiagram('Library staff')
    const user = userEvent.setup()
    renderApp('/projects/pr_1/coverage')

    const flag = await screen.findByText(/The same item is called/)
    expect(flag).toHaveTextContent('“Librarian”')
    expect(flag).toHaveTextContent('“Library staff”')

    await user.click(screen.getByRole('radio', { name: 'Librarian' }))
    await user.click(screen.getByRole('button', { name: /Apply this name to all diagrams/ }))

    expect(await screen.findByText('Renamed to "Librarian" on 1 diagram.')).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByText(/The same item is called/)).not.toBeInTheDocument())
    const newest = getDb().diagrams.at(-1)!
    expect(newest.parent_id).toBe('dg_2') // a new version; dg_2 itself is kept
    expect(newest.model!.actors[0].name).toBe('Librarian')
    expect(getDb().diagrams.find((d) => d.id === 'dg_2')!.model!.actors[0].name).toBe('Library staff')
  })

  it('does not flag two different items that share a name', async () => {
    seedDiagram()
    seedSecondDiagram('Librarian', 'it_9') // a different model item that happens to share the name
    renderApp('/projects/pr_1/coverage')
    await screen.findByTestId('coverage-totals')
    expect(screen.queryByText(/The same item is called/)).not.toBeInTheDocument()
  })
})
