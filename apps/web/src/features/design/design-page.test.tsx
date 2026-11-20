/** System Design (Feature 4) group 1: the Design step, its section shell and 4.1 Design goals, against the mock API. */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeAll, describe, expect, it } from 'vitest'
import { env } from '@/lib/env'
import { getDb, save } from '@/mocks/db'
import { renderApp } from '@/test/render'
import { seedProject } from '@/test/seed'

const JOB = { timeout: 10000 }
const headers = { Authorization: 'Bearer mock-token:dev@sddg.test', 'Content-Type': 'application/json' }
const call = (method: string, path: string, body?: unknown) =>
  fetch(`${env.apiUrl.replace(/\/$/, '')}/projects/pr_1${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) })

type Goal = { name: string; reason?: string; statement_ids?: string[] }
const goal = ({ name, reason = '', statement_ids = [] }: Goal) => ({ name, reason, statement_ids })

/** pr_1 with R-001 (st_1) and R-002 (st_2); confirmed unless asked otherwise; optional saved goals. */
async function seedDesign({ confirmed = true, consent = true, goals }: { confirmed?: boolean; consent?: boolean; goals?: Goal[] } = {}) {
  seedProject({ confirmed, consent })
  getDb().statements.pr_1.push({ id: 'st_2', ref: 'R-002', text: 'Search results appear within 2 seconds.', label: 'NFR', source: { document: 'Pasted text', page: null, paragraph: 2 } })
  save()
  if (goals) expect((await call('PUT', '/design/goals', { content: { goals: goals.map(goal) } })).status).toBe(200)
}

const names = () => [...document.querySelectorAll<HTMLElement>('li[data-goal]')].map((li) => li.dataset.goal)
const goalItem = (name: string) => document.querySelector<HTMLElement>(`li[data-goal="${name}"]`)!
const serverNames = async () =>
  ((await (await call('GET', '/design')).json()) as { sections: { content: { goals: Goal[] } }[] }).sections[0].content.goals.map((g) => g.name)

describe('Design page', () => {
  beforeAll(() => {
    // jsdom has no ResizeObserver (a Checkbox measures itself); stub just enough.
    globalThis.ResizeObserver ??= class {
      observe() {}
      unobserve() {}
      disconnect() {}
    } as unknown as typeof ResizeObserver
  })

  it('is a project area, locked until the requirements are confirmed', async () => {
    await seedDesign({ confirmed: false })
    const first = renderApp('/projects/pr_1/review')
    const rail = await screen.findByRole('navigation', { name: 'Project areas' })
    expect(within(rail).getByText('Design').closest('[aria-disabled]')).not.toBeNull()
    expect(within(rail).queryByRole('link', { name: /Design/ })).not.toBeInTheDocument()
    first.unmount()

    getDb().projects[0].confirmed_at = new Date().toISOString()
    save()
    const user = userEvent.setup()
    renderApp('/projects/pr_1/review')
    const areas = await screen.findByRole('navigation', { name: 'Project areas' })
    await user.click(within(areas).getByRole('link', { name: 'Design' }))
    expect(await screen.findByRole('tab', { name: 'Design goals', selected: true })).toBeInTheDocument()
    expect(screen.queryByRole('complementary', { name: 'Generate' })).not.toBeInTheDocument()
  })

  it('drafts the goals with AI: Empty, then the drafted goals with their requirements, as a Draft', async () => {
    await seedDesign()
    const user = userEvent.setup()
    renderApp('/projects/pr_1/design')
    expect(await within(await screen.findByRole('tabpanel')).findByText('Empty')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Draft with AI' }))
    await waitFor(() => expect(names().length).toBeGreaterThanOrEqual(5), JOB)
    expect(names()[0]).toBe('Reliability')
    expect(within(goalItem('Reliability')).getByText('R-001')).toBeInTheDocument()
    expect(within(goalItem('Efficiency')).getByText('R-002')).toBeInTheDocument()
    expect(within(screen.getByRole('tabpanel')).getByText('Draft')).toBeInTheDocument()
    expect(getDb().jobs.filter((j) => j.kind === 'design_goals')).toHaveLength(1)
  })

  it('reorders, removes and adds goals, and saves the new order; Confirm waits for the save', async () => {
    await seedDesign({ goals: [
      { name: 'Reliability', statement_ids: ['st_1'] },
      { name: 'Efficiency', statement_ids: ['st_2'] },
      { name: 'Portability', statement_ids: ['st_1'] },
    ] })
    const user = userEvent.setup()
    const view = renderApp('/projects/pr_1/design')
    await screen.findByRole('button', { name: 'Move Efficiency up' })
    await user.click(screen.getByRole('button', { name: 'Move Efficiency up' }))
    await user.click(screen.getByRole('button', { name: 'Remove Portability' }))
    await user.selectOptions(screen.getByLabelText('Add a goal'), 'Ease of use')
    await user.click(screen.getByRole('button', { name: 'Add' }))
    expect(names()).toEqual(['Efficiency', 'Reliability', 'Ease of use'])
    expect(screen.getByRole('button', { name: 'Confirm' })).toBeDisabled()
    expect(screen.getByText(/Save your changes before confirming/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirm' })).toBeEnabled())
    expect(await serverNames()).toEqual(['Efficiency', 'Reliability', 'Ease of use'])
    view.unmount()
    renderApp('/projects/pr_1/design')
    await screen.findByRole('button', { name: 'Move Reliability up' })
    expect(names()).toEqual(['Efficiency', 'Reliability', 'Ease of use'])
  })

  it('refuses to confirm a goal that cites nothing, then confirms once it cites a requirement', async () => {
    await seedDesign({ goals: [{ name: 'Reliability', statement_ids: ['st_1'] }, { name: 'Maintainability' }] })
    const user = userEvent.setup()
    renderApp('/projects/pr_1/design')
    await user.click(await screen.findByRole('button', { name: 'Confirm' }))
    expect(await screen.findByText('Every design goal must cite at least one requirement: Maintainability.')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Requirements for Maintainability' }))
    await user.click(screen.getByRole('checkbox', { name: 'Maintainability cites R-002' }))
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirm' })).toBeEnabled())
    await user.click(screen.getByRole('button', { name: 'Confirm' }))
    expect(await within(screen.getByRole('tabpanel')).findByText('Confirmed')).toBeInTheDocument()
  })

  it('shows the trade-offs and who each goal matters to, from the saved version', async () => {
    await seedDesign({ goals: [
      { name: 'Reliability', statement_ids: ['st_1'] },
      { name: 'Efficiency', statement_ids: ['st_2'] },
      { name: 'Portability', statement_ids: ['st_1'] },
    ] })
    const user = userEvent.setup()
    renderApp('/projects/pr_1/design')
    const tradeOffs = await screen.findByRole('region', { name: 'Trade-offs to watch' })
    expect(within(tradeOffs).getByText(/Efficiency vs\. Portability \(or Modifiability\)/)).toBeInTheDocument()
    const groups = screen.getByRole('region', { name: 'By stakeholder' })
    for (const group of ['Client', 'End user', 'Developer/maintainer'])
      expect(within(within(groups).getByRole('list', { name: group })).getByText('Reliability')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Remove Portability' }))
    expect(within(groups).getByText(/reflect the last saved version/)).toBeInTheDocument()
  })

  it('shows Out of date when a cited requirement changes', async () => {
    await seedDesign({ goals: [{ name: 'Reliability', statement_ids: ['st_1'] }] })
    expect((await call('PATCH', '/statements/st_1', { text: 'The librarian shall issue up to 5 books to a member.' })).status).toBe(200)
    renderApp('/projects/pr_1/design')
    expect(await screen.findByText('Out of date')).toBeInTheDocument()
  })

  it('asks before an AI draft replaces existing content', async () => {
    await seedDesign({ goals: [{ name: 'Reliability', statement_ids: ['st_1'] }] })
    const user = userEvent.setup()
    renderApp('/projects/pr_1/design')
    await user.click(await screen.findByRole('button', { name: 'Draft with AI' }))
    const dialog = await screen.findByRole('dialog', { name: 'Replace the design goals?' })
    await user.click(within(dialog).getByRole('button', { name: 'Keep mine' }))
    expect(getDb().jobs.filter((j) => j.kind === 'design_goals')).toHaveLength(0)

    await user.click(screen.getByRole('button', { name: 'Draft with AI' }))
    await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Replace' }))
    await waitFor(() => expect(getDb().jobs.filter((j) => j.kind === 'design_goals')).toHaveLength(1))
    await waitFor(() => expect(names().length).toBeGreaterThanOrEqual(5), JOB)
  })

  it('asks for AI consent first and starts the draft once the user agrees', async () => {
    await seedDesign({ consent: false })
    const user = userEvent.setup()
    renderApp('/projects/pr_1/design')
    await user.click(await screen.findByRole('button', { name: 'Draft with AI' }))
    const dialog = await screen.findByRole('dialog')
    expect(getDb().jobs.filter((j) => j.kind === 'design_goals')).toHaveLength(0)
    await user.click(within(dialog).getByRole('checkbox'))
    await user.click(within(dialog).getByRole('button', { name: 'Agree and extract' }))
    await waitFor(() => expect(getDb().jobs.filter((j) => j.kind === 'design_goals')).toHaveLength(1))
    await waitFor(() => expect(names().length).toBeGreaterThanOrEqual(5), JOB)
  })

  it('shows the server refusal when Save is rejected', async () => {
    await seedDesign({ goals: [{ name: 'Reliability', statement_ids: ['st_1'] }] })
    const user = userEvent.setup()
    renderApp('/projects/pr_1/design')
    await user.click(await screen.findByRole('button', { name: 'Remove Reliability' }))
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('Choose 1 to 28 design goals.')).toBeInTheDocument()
  })
})
