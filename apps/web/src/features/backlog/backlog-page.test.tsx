/** Stories backlog (Feature 3.4): "As a <role> I want to <goal> so I can <reason>", each linked to a requirement. */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { beforeAll, describe, expect, it } from 'vitest'
import { env } from '@/lib/env'
import { getDb, save, type StoryRow } from '@/mocks/db'
import { server } from '@/mocks/node'
import { renderApp } from '@/test/render'
import { seedProject } from '@/test/seed'

const source = { document: 'Pasted text', page: null, paragraph: 2 }
const at = new Date().toISOString()

function story(n: number, extra: Partial<StoryRow> = {}): StoryRow {
  return {
    id: `us_${n}`, project_id: 'pr_1', ref: `S-00${n}`, role: 'member', goal: `goal ${n}`, reason: `reason ${n}`,
    priority: 'should', estimate: null, status: 'todo', assignee_id: null, confirmations: [], statement_ids: ['st_1'],
    created_at: at, updated_at: at, ...extra,
  }
}

/** pr_1 with R-001 (st_1) and R-002 (st_2), and the given stories. */
function seedBacklog(stories: StoryRow[] = []) {
  seedProject()
  const db = getDb()
  db.statements.pr_1.push({ id: 'st_2', ref: 'R-002', text: 'Members shall reserve a book.', label: 'FR', source })
  db.stories = stories
  db.nextStory.pr_1 = stories.length + 1
  save()
}

const item = (ref: string) => document.querySelector<HTMLElement>(`li[data-story="${ref}"]`)!
const refs = () => [...document.querySelectorAll<HTMLElement>('li[data-story]')].map((li) => li.dataset.story)

describe('Stories backlog', () => {
  beforeAll(() => {
    // jsdom has no ResizeObserver (a Checkbox inside a form measures itself); stub just enough.
    globalThis.ResizeObserver ??= class {
      observe() {}
      unobserve() {}
      disconnect() {}
    } as unknown as typeof ResizeObserver
  })

  it('creates a story once the sentence is filled and a requirement is ticked', async () => {
    seedBacklog()
    const user = userEvent.setup()
    renderApp('/projects/pr_1/backlog')
    expect(await screen.findByText('No stories yet')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /New story/ }))
    const dialog = await screen.findByRole('dialog')
    const saveButton = within(dialog).getByRole('button', { name: 'Add story' })
    expect(saveButton).toBeDisabled()
    await user.type(within(dialog).getByLabelText('User role'), 'librarian')
    await user.type(within(dialog).getByLabelText('Goal'), 'issue a book')
    await user.type(within(dialog).getByLabelText('Reason'), 'members can borrow it')
    expect(saveButton).toBeDisabled()
    await user.click(within(dialog).getByRole('checkbox', { name: /R-001/ }))
    expect(saveButton).toBeEnabled()
    await user.click(saveButton)

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    await screen.findByText('S-001')
    const li = item('S-001')
    expect(li).toHaveTextContent('As a librarian I want to issue a book so I can members can borrow it')
    expect(within(li).getByText('R-001')).toBeInTheDocument()
  })

  it('edits priority and confirmations, and changes status from the list', async () => {
    seedBacklog([story(1)])
    const user = userEvent.setup()
    renderApp('/projects/pr_1/backlog')
    await user.click(await screen.findByRole('button', { name: 'Edit S-001' }))
    const dialog = await screen.findByRole('dialog')
    await user.selectOptions(within(dialog).getByLabelText('Priority'), 'must')
    await user.type(within(dialog).getByLabelText(/Confirmations/), 'Shows the due date{Enter}Rejects a blocked member')
    await user.click(within(dialog).getByRole('button', { name: 'Save story' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    const li = item('S-001')
    expect(within(li).getByText('Must')).toBeInTheDocument()
    expect(within(li).getByText('Shows the due date')).toBeInTheDocument()
    expect(within(li).getByText('Rejects a blocked member')).toBeInTheDocument()

    await user.selectOptions(within(li).getByLabelText('Status of S-001'), 'in_progress')
    await waitFor(() => expect(getDb().stories[0].status).toBe('in_progress'))
    expect(getDb().stories[0].priority).toBe('must')
  })

  it('deletes a story after confirmation', async () => {
    seedBacklog([story(1), story(2)])
    const user = userEvent.setup()
    renderApp('/projects/pr_1/backlog')
    await user.click(await screen.findByRole('button', { name: 'Delete S-001' }))
    expect(refs()).toEqual(['S-001', 'S-002'])
    await user.click(screen.getByRole('button', { name: 'Delete S-001' }))
    await waitFor(() => expect(refs()).toEqual(['S-002']))
    expect(getDb().stories.map((s) => s.ref)).toEqual(['S-002'])
  })

  it('filters by status, priority, assignee and requirement', async () => {
    seedBacklog([
      story(1, { status: 'done', priority: 'must', assignee_id: 'dev@sddg.test' }),
      story(2, { statement_ids: ['st_2'] }),
      story(3, { priority: 'could', statement_ids: ['st_1', 'st_2'] }),
    ])
    const user = userEvent.setup()
    renderApp('/projects/pr_1/backlog')
    await screen.findByText('S-001')
    expect(refs()).toEqual(['S-001', 'S-002', 'S-003'])

    await user.selectOptions(screen.getByLabelText('Filter by status'), 'done')
    expect(refs()).toEqual(['S-001'])
    await user.selectOptions(screen.getByLabelText('Filter by status'), '')
    await user.selectOptions(screen.getByLabelText('Filter by priority'), 'could')
    expect(refs()).toEqual(['S-003'])
    await user.selectOptions(screen.getByLabelText('Filter by priority'), '')
    await user.selectOptions(screen.getByLabelText('Filter by assignee'), 'none')
    expect(refs()).toEqual(['S-002', 'S-003'])
    await user.selectOptions(screen.getByLabelText('Filter by assignee'), '')
    await user.selectOptions(screen.getByLabelText('Filter by requirement'), 'st_2')
    expect(refs()).toEqual(['S-002', 'S-003'])
  })

  it('filters by requirement from the URL', async () => {
    seedBacklog([story(1), story(2, { statement_ids: ['st_2'] })])
    renderApp('/projects/pr_1/backlog?requirement=st_2')
    await screen.findByText('S-002')
    expect(refs()).toEqual(['S-002'])
    expect(screen.getByLabelText('Filter by requirement')).toHaveValue('st_2')
  })

  it('marks a story whose requirements were deleted', async () => {
    seedBacklog([story(1, { statement_ids: [] })])
    renderApp('/projects/pr_1/backlog')
    await screen.findByText('S-001')
    expect(within(item('S-001')).getByText('Needs a requirement')).toBeInTheDocument()
  })

  it('shows an API refusal in the dialog', async () => {
    seedBacklog()
    server.use(
      http.post(`${env.apiUrl.replace(/\/$/, '')}/projects/:project_id/stories`, () =>
        HttpResponse.json({ detail: 'A story can only link to requirements of this project.' }, { status: 422 }),
      ),
    )
    const user = userEvent.setup()
    renderApp('/projects/pr_1/backlog')
    await user.click(await screen.findByRole('button', { name: /New story/ }))
    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText('User role'), 'librarian')
    await user.type(within(dialog).getByLabelText('Goal'), 'issue a book')
    await user.type(within(dialog).getByLabelText('Reason'), 'members can borrow it')
    await user.click(within(dialog).getByRole('checkbox', { name: /R-001/ }))
    await user.click(within(dialog).getByRole('button', { name: 'Add story' }))
    expect(await within(dialog).findByText('A story can only link to requirements of this project.')).toBeInTheDocument()
  })

  it('disables New story when the project has no requirements', async () => {
    seedProject()
    getDb().statements.pr_1 = []
    save()
    renderApp('/projects/pr_1/backlog')
    expect(await screen.findByRole('button', { name: /New story/ })).toBeDisabled()
    expect(screen.getByText(/Add requirements first/)).toBeInTheDocument()
  })

  it('is linked from the workspace header', async () => {
    seedProject()
    const user = userEvent.setup()
    const { router } = renderApp('/projects/pr_1/search')
    await user.click(await screen.findByRole('link', { name: 'Backlog' }))
    expect(router.state.location.pathname).toBe('/projects/pr_1/backlog')
    expect(await screen.findByRole('heading', { name: 'Backlog' })).toBeInTheDocument()
  })
})
