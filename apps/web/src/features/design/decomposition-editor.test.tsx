/** System Design 4.2: the Subsystem decomposition tab and its package diagram, against the mock API. */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeAll, describe, expect, it } from 'vitest'
import type { ExtractedItem } from '@/api/client'
import { env } from '@/lib/env'
import { getDb, save } from '@/mocks/db'
import { renderApp } from '@/test/render'
import { seedProject } from '@/test/seed'

const JOB = { timeout: 10000 }
const headers = { Authorization: 'Bearer mock-token:dev@sddg.test', 'Content-Type': 'application/json' }
const call = (method: string, path: string, body?: unknown) =>
  fetch(`${env.apiUrl.replace(/\/$/, '')}/projects/pr_1${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) })

type Sub = { id: string; name: string; layer: number; depends_on?: string[]; classes?: string[]; statement_ids?: string[] }
const sub = ({ depends_on = [], classes = [], statement_ids = ['st_1'], ...s }: Sub) => ({
  description: '', services: [{ name: 'Lending', operations: ['Issue book'] }], depends_on, classes, statement_ids, ...s,
})
/** Three layers, each depending on the one directly below. */
const THREE: Sub[] = [
  { id: 'ui', name: 'User interface', layer: 1, depends_on: ['logic'] },
  { id: 'logic', name: 'Lending', layer: 2, depends_on: ['store'], classes: ['Book'] },
  { id: 'store', name: 'Storage', layer: 3 },
]

const entity = (id: string, name: string): ExtractedItem => ({ id, category: 'entity', name, description: null, origin: 'system-extracted', qualifiers: [], statement_ids: ['st_1'] })

/** pr_1 confirmed with R-001..R-002, entities Book, Member and Loan; goals confirmed unless asked; optional saved decomposition. */
async function seedDecomposition({ goalsConfirmed = true, architecture = 'closed', subsystems }: { goalsConfirmed?: boolean; architecture?: string; subsystems?: Sub[] } = {}) {
  seedProject({ confirmed: true, consent: true })
  const db = getDb()
  db.statements.pr_1.push({ id: 'st_2', ref: 'R-002', text: 'Search results appear within 2 seconds.', label: 'NFR', source: { document: 'Pasted text', page: null, paragraph: 2 } })
  db.items.pr_1.push(entity('it_b', 'Book'), entity('it_m', 'Member'), entity('it_l', 'Loan'), {
    id: 'it_r', category: 'relationship', name: 'Loan of a book', description: null, origin: 'system-extracted', qualifiers: [],
    statement_ids: ['st_1'], source_item_id: 'it_l', target_item_id: 'it_b', relation_type: 'association',
  })
  save()
  expect((await call('PUT', '/design/goals', { content: { goals: [{ name: 'Reliability', reason: '', statement_ids: ['st_1'] }] } })).status).toBe(200)
  if (goalsConfirmed) expect((await call('POST', '/design/goals/confirm')).status).toBe(200)
  if (subsystems) expect((await call('PUT', '/design/decomposition', { content: { architecture, subsystems: subsystems.map(sub) } })).status).toBe(200)
}

const card = (id: string) => document.querySelector<HTMLElement>(`li[data-subsystem="${id}"]`)!
const layerOf = (id: string) => card(id).closest('section')!.getAttribute('aria-label')
const saved = async () =>
  ((await (await call('GET', '/design')).json()) as { sections: { content: { subsystems: Required<Sub>[] } }[] }).sections[1].content.subsystems

async function save_(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: 'Save' }))
  await waitFor(() => expect(screen.getByRole('button', { name: 'Confirm' })).toBeEnabled())
}

describe('Subsystem decomposition', () => {
  beforeAll(() => {
    globalThis.ResizeObserver ??= class {
      observe() {}
      unobserve() {}
      disconnect() {}
    } as unknown as typeof ResizeObserver
  })

  it('is locked with the reason until the design goals are confirmed, then opens', async () => {
    await seedDecomposition({ goalsConfirmed: false })
    const user = userEvent.setup()
    renderApp('/projects/pr_1/design')
    const tab = await screen.findByRole('tab', { name: /Subsystem decomposition/ })
    expect(tab).toBeDisabled()
    expect(within(tab).getByText('Confirm Design goals first.')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Confirm' }))
    await waitFor(() => expect(screen.getByRole('tab', { name: /Subsystem decomposition/ })).toBeEnabled())
    await user.click(screen.getByRole('tab', { name: /Subsystem decomposition/ }))
    expect(screen.getByRole('tab', { name: 'Subsystem decomposition', selected: true })).toBeInTheDocument()
    expect(await within(screen.getByRole('tabpanel')).findByText('Empty')).toBeInTheDocument()
  })

  it('drafts with AI: subsystems under their layers, with services, classes and cited requirements', async () => {
    await seedDecomposition()
    const user = userEvent.setup()
    renderApp('/projects/pr_1/design?tab=decomposition')
    await user.click(await screen.findByRole('button', { name: 'Draft with AI' }))
    await waitFor(() => expect(document.querySelectorAll('li[data-subsystem]').length).toBe(3), JOB)
    expect(screen.getByRole('region', { name: 'Layer 1 (top)' })).toBeInTheDocument()
    expect(layerOf('user-interface')).toBe('Layer 1 (top)')
    expect(layerOf('application')).toBe('Layer 2')
    expect(layerOf('storage')).toBe('Layer 3')
    const app = card('application')
    expect(within(app).getByRole('checkbox', { name: 'Application logic owns Book' })).toBeChecked()
    expect(within(app).getByLabelText('Service name')).toHaveValue('Lending')
    expect(within(app).getByText('R-001')).toBeInTheDocument()
    expect(within(screen.getByRole('tabpanel')).getByText('Draft')).toBeInTheDocument()
    expect(getDb().jobs.filter((j) => j.kind === 'design_decomposition')).toHaveLength(1)
  })

  it('flags an upward dependency on both subsystems, and clears it once removed', async () => {
    await seedDecomposition({ subsystems: THREE })
    const user = userEvent.setup()
    renderApp('/projects/pr_1/design?tab=decomposition')
    await user.type(await screen.findByLabelText('New subsystem name'), 'Reports')
    await user.click(screen.getByRole('button', { name: 'Add subsystem' }))
    expect(layerOf('reports')).toBe('Layer 1 (top)')
    await user.click(within(card('reports')).getByRole('button', { name: 'Move Reports to the layer below' }))
    expect(layerOf('reports')).toBe('Layer 2')
    await user.click(within(card('reports')).getByRole('checkbox', { name: 'Reports depends on User interface' }))
    await save_(user)

    const upward = /Reports \(layer 2\) depends on User interface in the higher layer 1/
    expect(within(card('reports')).getByText(upward)).toBeInTheDocument()
    expect(within(card('ui')).getByText(upward)).toBeInTheDocument()

    await user.click(within(card('reports')).getByRole('checkbox', { name: 'Reports depends on User interface' }))
    await save_(user)
    expect(screen.queryByText(upward)).not.toBeInTheDocument()
  })

  it('flags a skipped layer in a closed architecture, and not in an open one', async () => {
    await seedDecomposition({ subsystems: [{ ...THREE[0], depends_on: ['logic', 'store'] }, THREE[1], THREE[2]] })
    const user = userEvent.setup()
    renderApp('/projects/pr_1/design?tab=decomposition')
    const skipped = /User interface \(layer 1\) calls Storage in layer 3/
    await waitFor(() => expect(within(card('ui')).getByText(skipped)).toBeInTheDocument())
    expect(within(card('store')).getByText(skipped)).toBeInTheDocument()

    await user.click(screen.getByRole('radio', { name: /Open/ }))
    await save_(user)
    expect(screen.getByRole('radio', { name: /Open/ })).toBeChecked()
    expect(screen.queryByText(skipped)).not.toBeInTheDocument()
  })

  it('keeps dependencies when a subsystem is renamed', async () => {
    await seedDecomposition({ subsystems: THREE })
    const user = userEvent.setup()
    renderApp('/projects/pr_1/design?tab=decomposition')
    await screen.findByRole('region', { name: 'Layer 2' })
    const name = within(card('logic')).getByLabelText('Name')
    await user.clear(name)
    await user.type(name, 'Loans')
    await save_(user)
    expect(within(card('ui')).getByRole('checkbox', { name: 'User interface depends on Loans' })).toBeChecked()
    const after = await saved()
    expect(after.find((s) => s.id === 'logic')!.name).toBe('Loans')
    expect(after.find((s) => s.id === 'ui')!.depends_on).toEqual(['logic'])
  })

  it('offers a class to one subsystem only', async () => {
    await seedDecomposition({ subsystems: THREE })
    const user = userEvent.setup()
    renderApp('/projects/pr_1/design?tab=decomposition')
    await screen.findByRole('region', { name: 'Layer 3' })
    expect(await within(card('store')).findByRole('checkbox', { name: 'Storage owns Member' })).toBeInTheDocument()
    expect(within(card('store')).queryByRole('checkbox', { name: 'Storage owns Book' })).not.toBeInTheDocument()
    expect(within(card('logic')).getByRole('checkbox', { name: 'Lending owns Book' })).toBeChecked()
    await user.click(within(card('ui')).getByRole('checkbox', { name: 'User interface owns Member' }))
    expect(within(card('store')).queryByRole('checkbox', { name: 'Storage owns Member' })).not.toBeInTheDocument()
  })

  it('refuses to confirm while a subsystem cites nothing, then confirms and shows the package diagram', async () => {
    await seedDecomposition({ subsystems: [THREE[0], THREE[1], { ...THREE[2], statement_ids: [] }] })
    const user = userEvent.setup()
    renderApp('/projects/pr_1/design?tab=decomposition')
    expect(await screen.findByText(/package diagram is drawn when you confirm/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Confirm' }))
    expect(await screen.findByText('Every subsystem must cite at least one requirement: Storage.')).toBeInTheDocument()

    await user.click(within(card('store')).getByRole('button', { name: 'Requirements for Storage' }))
    await user.click(screen.getByRole('checkbox', { name: 'Storage cites R-001' }))
    await save_(user)
    await user.click(screen.getByRole('button', { name: 'Confirm' }))
    expect(await within(screen.getByRole('tabpanel')).findByText('Confirmed')).toBeInTheDocument()
    const diagram = getDb().diagrams.find((d) => d.type === 'package')!
    expect(await screen.findByRole('link', { name: 'Open in the viewer' })).toHaveAttribute('href', `/projects/pr_1/diagrams/${diagram.id}`)
    const list = (await (await call('GET', '/diagrams')).json()) as { type: string; title: string }[]
    expect(list).toContainEqual(expect.objectContaining({ type: 'package', title: 'Library system · Package' }))
  })

  it('shows cohesion and coupling from the saved derived values, a dash when there is none', async () => {
    await seedDecomposition({ subsystems: THREE })
    const row = (getDb().design as Record<string, Record<string, { derived: Record<string, unknown> }>>).pr_1.decomposition
    row.derived.cohesion = 0.42
    row.derived.subsystems = [{ id: 'ui', cohesion: null, coupling: 1 }, { id: 'logic', cohesion: 0.67, coupling: 2 }, { id: 'store', cohesion: 1, coupling: 3 }]
    save()
    renderApp('/projects/pr_1/design?tab=decomposition')
    const metrics = await screen.findByRole('region', { name: 'Cohesion and coupling' })
    expect(within(metrics).getByText('0.42')).toBeInTheDocument()
    const cells = (name: string) => within(within(metrics).getByRole('row', { name: new RegExp(`^${name}`) })).getAllByRole('cell').map((c) => c.textContent)
    expect(cells('User interface')).toEqual(['—', '1'])
    expect(cells('Lending')).toEqual(['0.67', '2'])
  })
})

describe('Package diagrams elsewhere', () => {
  it('are not offered on the Choose diagrams page; the viewer shows one as Package without arrange or AI edits', async () => {
    await seedDecomposition({ subsystems: THREE })
    expect((await call('POST', '/design/decomposition/confirm')).status).toBe(200)
    const id = getDb().diagrams.find((d) => d.type === 'package')!.id
    const viewer = renderApp(`/projects/pr_1/diagrams/${id}`)
    expect(await screen.findByRole('heading', { name: 'Package diagram' })).toBeInTheDocument()
    const list = screen.getByRole('navigation', { name: 'Your diagrams' })
    expect(within(list).getByText('Package')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Move elements' })).toBeDisabled()
    expect(screen.queryByLabelText('Describe a change to the diagram')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Design step/ })).toHaveAttribute('href', '/projects/pr_1/design?tab=decomposition')
    viewer.unmount()

    renderApp('/projects/pr_1/generate')
    const types = await screen.findByRole('group', { name: 'Diagram types' })
    expect(within(types).queryByRole('checkbox', { name: /Package/ })).not.toBeInTheDocument()
    expect(within(await screen.findByRole('list', { name: 'Your diagrams' })).getByRole('link', { name: /Package/ })).toBeInTheDocument()
  })
})
