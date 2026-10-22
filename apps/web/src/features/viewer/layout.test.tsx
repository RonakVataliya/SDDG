import { cleanup, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { env } from '@/lib/env'
import { getDb } from '@/mocks/db'
import { server } from '@/mocks/node'
import { renderApp } from '@/test/render'
import { seedDiagram } from '@/test/seed'
import { boxFor, route } from './layout-geometry'

// Default grid from the server: the actor (it_1) at 120,100 and the use case (it_2) at 340,100.
const position = (id: string) => document.querySelector(`[data-element="${id}"]`)?.getAttribute('transform')
const linePath = () => document.querySelector('[data-line="it_1-it_2"] path')?.getAttribute('d')

async function openEditor() {
  const user = userEvent.setup()
  const result = renderApp('/projects/pr_1/diagrams/dg_1')
  const button = await screen.findByRole('button', { name: 'Move elements' })
  await waitFor(() => expect(button).toBeEnabled())
  await user.click(button)
  return { user, ...result }
}

describe('#37 move and reposition elements', () => {
  it('moves one element, saves it as a new version and draws it there after a reload, with its line attached', async () => {
    seedDiagram()
    const { user, router } = await openEditor()
    await user.click(screen.getByRole('button', { name: 'Librarian (actor)' }))
    await user.keyboard('{ArrowRight}{ArrowRight}{ArrowRight}{Shift>}{ArrowDown}{/Shift}')
    expect(position('it_1')).toBe('translate(150 150)')
    expect(screen.getByText('1 element moved, not saved yet.')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Save positions' }))
    await waitFor(() => expect(router.state.location.pathname).not.toBe('/projects/pr_1/diagrams/dg_1'))
    const next = getDb().diagrams.at(-1)!
    expect(next).toMatchObject({ parent_id: 'dg_1', layout: { it_1: [150, 150] } })
    expect(getDb().diagrams[0].layout).toBeUndefined() // the old version is kept as it was

    cleanup() // reload
    renderApp(`/projects/pr_1/diagrams/${next.id}`)
    await waitFor(() => expect(position('it_1')).toBe('translate(150 150)'))
    expect(position('it_2')).toBe('translate(340 100)')
    const expected = route(boxFor('actor', 'Librarian'), { x: 150, y: 150 }, boxFor('use_case', 'Issue book'), { x: 340, y: 100 })
    expect(linePath()).toBe(expected.d)
  })

  it('moves several elements together and the line between them follows', async () => {
    seedDiagram()
    const { user } = await openEditor()
    const before = linePath()
    screen.getByRole('button', { name: 'Librarian (actor)' }).focus()
    await user.keyboard(' ')
    screen.getByRole('button', { name: 'Issue book (use case)' }).focus()
    await user.keyboard(' {ArrowDown}{ArrowDown}')
    expect(position('it_1')).toBe('translate(120 120)')
    expect(position('it_2')).toBe('translate(340 120)')
    expect(linePath()).not.toBe(before)
    expect(document.querySelector('[data-line="it_1-it_2"]')).toHaveAttribute('data-source', 'it_1')

    await user.click(screen.getByRole('button', { name: 'Save positions' }))
    await waitFor(() => expect(getDb().diagrams).toHaveLength(2))
    expect(getDb().diagrams[1].layout).toEqual({ it_1: [120, 120], it_2: [340, 120] })
  })

  it('shows an error when saving fails, does not claim the move was saved, and keeps it to try again', async () => {
    seedDiagram()
    server.use(http.post(`${env.apiUrl.replace(/\/$/, '')}/diagrams/:id/layout`, () => HttpResponse.json({ detail: 'Database unavailable.' }, { status: 500 })))
    const { user, router } = await openEditor()
    await user.click(screen.getByRole('button', { name: 'Issue book (use case)' }))
    await user.keyboard('{ArrowLeft}')
    await user.click(screen.getByRole('button', { name: 'Save positions' }))

    expect(await screen.findByText('The new positions were not saved')).toBeInTheDocument()
    expect(screen.getByText(/Database unavailable\./)).toBeInTheDocument()
    expect(screen.getByText('1 element moved, not saved yet.')).toBeInTheDocument()
    expect(position('it_2')).toBe('translate(330 100)')
    expect(screen.getByRole('button', { name: 'Save positions' })).toBeEnabled()
    expect(router.state.location.pathname).toBe('/projects/pr_1/diagrams/dg_1')
    expect(getDb().diagrams).toHaveLength(1)
  })

  it('cancel puts everything back and saves nothing', async () => {
    seedDiagram()
    const { user } = await openEditor()
    await user.click(screen.getByRole('button', { name: 'Librarian (actor)' }))
    await user.keyboard('{ArrowUp}')
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('button', { name: 'Librarian (actor)' })).not.toBeInTheDocument()
    expect(getDb().diagrams).toHaveLength(1)
  })

  it('the server refuses unknown elements and positions that are not numbers, and makes no version', async () => {
    seedDiagram()
    const token = { Authorization: 'Bearer mock-token:dev@sddg.test', 'Content-Type': 'application/json' }
    const post = (positions: unknown) =>
      fetch(`${env.apiUrl.replace(/\/$/, '')}/diagrams/dg_1/layout`, { method: 'POST', headers: token, body: JSON.stringify({ positions }) })
    expect((await post({ nope: { x: 1, y: 1 } })).status).toBe(422)
    expect((await post({ it_1: { x: 'left', y: 1 } })).status).toBe(422)
    expect(getDb().diagrams).toHaveLength(1)
  })
})
