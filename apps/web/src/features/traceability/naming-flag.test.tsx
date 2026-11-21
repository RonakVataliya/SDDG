import { QueryClientProvider } from '@tanstack/react-query'
import { configure, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import type { Role } from '@/api/client'
import { createQueryClient } from '@/lib/query-client'
import { getDb, save } from '@/mocks/db'
import { renderUseCase, type UseCaseModel } from '@/mocks/render'
import { seedDiagram, seedInvitation, seedOthersProject } from '@/test/seed'
import { NamingFlag } from './naming-flag'

// A CI runner is slower than a laptop: the mock API needs more than the one second
// testing-library waits by default, so these waits get a real budget.
configure({ asyncUtilTimeout: 5000 })
vi.setConfig({ testTimeout: 20000 })

/** A second diagram that calls the same model item (it_1) something else, so there is an issue to flag. */
function seedDisagreement() {
  const model: UseCaseModel = {
    system: 'Library system',
    actors: [{ id: 'it_1', name: 'Library staff' }],
    cases: [{ id: 'it_2', name: 'Issue book', assumed: false }],
    links: [],
  }
  getDb().diagrams.push({
    id: 'dg_2', project_id: 'pr_1', type: 'class', title: 'Library system - Class',
    created_at: new Date().toISOString(), parent_id: null, instruction: null, model, svg: renderUseCase(model),
  })
  save()
}

function renderFlag(role: Role) {
  localStorage.setItem('sddg.mock.session', JSON.stringify({ email: 'dev@sddg.test', accessToken: 'mock-token:dev@sddg.test' }))
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <NamingFlag projectId="pr_1" role={role} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('FR17e who may apply a name', () => {
  it('offers the rename to an Editor', async () => {
    seedDiagram()
    seedDisagreement()
    renderFlag('editor')

    expect(await screen.findByText(/The same item is called/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Apply this name to all diagrams/ })).toBeInTheDocument()
  })

  it('shows a Viewer the finding but none of the controls', async () => {
    seedDiagram()
    seedDisagreement()
    renderFlag('viewer')

    // The disagreement is worth knowing about even if you cannot fix it.
    const flag = await screen.findByText(/The same item is called/)
    expect(flag).toHaveTextContent('Librarian')
    expect(flag).toHaveTextContent('Library staff')
    expect(screen.queryByRole('button', { name: /Apply this name to all diagrams/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('radiogroup', { name: 'Name to use' })).not.toBeInTheDocument()
  })

  it('is refused by the server even if the page thinks the role is higher', async () => {
    // Hiding the button is not the access check. Someone whose role changed while the page was open, or who
    // reaches the mutation another way, is still a Viewer as far as the API is concerned.
    seedOthersProject('Library system')
    seedInvitation({ role: 'viewer', accepted_at: new Date().toISOString() })
    seedDisagreement()
    getDb().diagrams.push({
      id: 'dg_1', project_id: 'pr_1', type: 'use_case', title: 'Library system - Use Case',
      created_at: new Date().toISOString(), parent_id: null, instruction: null,
      model: { system: 'Library system', actors: [{ id: 'it_1', name: 'Librarian' }], cases: [], links: [] },
      svg: '<svg/>',
    })
    save()
    const before = getDb().diagrams.length
    const user = userEvent.setup()
    renderFlag('editor') // a stale role: the UI offers the button

    await user.click(await screen.findByRole('button', { name: /Apply this name to all diagrams/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/Not permitted/)
    expect(getDb().diagrams).toHaveLength(before) // no new version was written
  })
})
