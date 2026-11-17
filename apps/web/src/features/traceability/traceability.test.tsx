import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { getDb, save, uid } from '@/mocks/db'
import type { UseCaseModel } from '@/mocks/render'
import { renderUseCase } from '@/mocks/render'
import { renderApp } from '@/test/render'
import { seedDiagram } from '@/test/seed'

/** A second version of dg_1 made by hand, with `change` applied to its model. */
function editVersion(change: (m: UseCaseModel) => UseCaseModel, instruction: string | null = 'Remove Issue book') {
  const root = getDb().diagrams[0]
  const model = change(structuredClone(root.model!))
  // instruction null: change what the generator itself drew, rather than adding an edited version.
  if (instruction === null) {
    root.model = model
    root.svg = renderUseCase(model)
    save()
    return root
  }
  const row = {
    ...root, id: uid('dg'), created_at: new Date().toISOString(), parent_id: root.id, instruction, model,
    svg: renderUseCase(model),
  }
  getDb().diagrams.push(row)
  save()
  return row
}

describe('FR17a sources of a diagram element', () => {
  it('shows the requirement behind an element, and says so when there is none', async () => {
    seedDiagram()
    // "Log in" is the kind of use case a generator adds although no requirement asks for it (DR2a).
    editVersion((m) => ({ ...m, cases: [...m.cases, { id: 'assumed-login', name: 'Log in', assumed: true }] }), null)
    const user = userEvent.setup()
    renderApp('/projects/pr_1/diagrams/dg_1')

    await user.click(await screen.findByRole('button', { name: 'Issue book' }))
    const panel = await screen.findByRole('complementary', { name: 'Sources for Issue book' })
    expect(within(panel).getByText('R-001')).toBeInTheDocument()
    expect(within(panel).getByText('The librarian shall issue a book to a member.')).toBeInTheDocument()
    expect(within(panel).getByText(/Pasted text · paragraph 1/)).toBeInTheDocument()

    await user.click(within(panel).getByRole('button', { name: 'Close sources' }))
    // "Log in" is added by the generator; no requirement mentions it (DR2a).
    await user.click(await screen.findByRole('button', { name: /Log in/ }))
    expect(await screen.findByText(/No source requirement – assumption/)).toBeInTheDocument()
  })
})

describe('FR17d drift warning', () => {
  it('warns when an edit removes an element a requirement calls for', async () => {
    seedDiagram()
    const edited = editVersion((m) => ({ ...m, cases: m.cases.filter((c) => c.name !== 'Issue book') }))
    renderApp(`/projects/pr_1/diagrams/${edited.id}`)
    expect(await screen.findByText(/R-001 calls for "Issue book", but this version no longer has it\./)).toBeInTheDocument()
    expect(screen.getByText(/This version no longer matches a requirement/)).toBeInTheDocument()
  })

  it('never warns on the version the generator drew', async () => {
    seedDiagram()
    editVersion((m) => ({ ...m, cases: m.cases.filter((c) => c.name !== 'Issue book') }))
    renderApp('/projects/pr_1/diagrams/dg_1')
    expect(await screen.findByRole('button', { name: 'Issue book' })).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByText(/no longer has it/)).not.toBeInTheDocument())
  })

  it('says nothing when the edit keeps what the requirements ask for', async () => {
    seedDiagram()
    const edited = editVersion((m) => ({ ...m, cases: [...m.cases, { id: 'extra', name: 'Print receipt', assumed: true }] }), 'Add Print receipt')
    renderApp(`/projects/pr_1/diagrams/${edited.id}`)
    expect(await screen.findByRole('button', { name: /Print receipt/ })).toBeInTheDocument()
    expect(screen.queryByText(/no longer matches/)).not.toBeInTheDocument()
  })
})

describe('FR17b requirements that are not in any diagram', () => {
  it('lists them, and the count matches the coverage count', async () => {
    seedDiagram()
    getDb().statements.pr_1.push({
      id: 'st_2', ref: 'R-002', text: 'The system shall email a receipt.', label: 'FR4',
      source: { document: 'Pasted text', page: null, paragraph: 2 },
    })
    save()
    renderApp('/projects/pr_1/traceability')

    const card = await screen.findByRole('region', { name: /Not in any diagram/ })
    expect(within(card).getByRole('heading', { name: 'Not in any diagram 1' })).toBeInTheDocument()
    expect(within(card).getByText('R-002')).toBeInTheDocument()
    expect(within(card).getByText('The system shall email a receipt.')).toBeInTheDocument()
    expect(within(card).queryByText('R-001')).not.toBeInTheDocument() // R-001 is drawn
    expect(within(card).getByText('1 of 2 requirements are drawn')).toBeInTheDocument()
  })

  it('says every requirement is drawn when none are missing', async () => {
    seedDiagram()
    renderApp('/projects/pr_1/traceability')
    expect(await screen.findByText('Every requirement appears in a diagram.')).toBeInTheDocument()
  })
})

describe('FR17e naming consistency', () => {
  it('flags one item named two ways and applies the chosen name to every diagram', async () => {
    seedDiagram()
    const model: UseCaseModel = {
      system: 'Library system',
      actors: [{ id: 'it_1', name: 'Library staff' }], // the same model item as dg_1's "Librarian"
      cases: [{ id: 'it_2', name: 'Issue book', assumed: false }],
      links: [{ actor: 'it_1', case: 'it_2' }],
    }
    getDb().diagrams.push({
      id: 'dg_2', project_id: 'pr_1', type: 'use_case', title: 'Library system · Class', created_at: new Date().toISOString(),
      parent_id: null, instruction: null, model, svg: renderUseCase(model),
    })
    save()
    const user = userEvent.setup()
    renderApp('/projects/pr_1/traceability')

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
    const model: UseCaseModel = {
      system: 'Library system',
      actors: [{ id: 'it_9', name: 'Librarian' }], // a different model item with the same name
      cases: [{ id: 'it_2', name: 'Issue book', assumed: false }],
      links: [],
    }
    getDb().diagrams.push({
      id: 'dg_2', project_id: 'pr_1', type: 'use_case', title: 'Library system · DFD', created_at: new Date().toISOString(),
      parent_id: null, instruction: null, model, svg: renderUseCase(model),
    })
    save()
    renderApp('/projects/pr_1/traceability')
    expect(await screen.findByRole('region', { name: /Not in any diagram/ })).toBeInTheDocument()
    expect(screen.queryByText(/The same item is called/)).not.toBeInTheDocument()
  })
})
