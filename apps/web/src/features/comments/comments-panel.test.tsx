/** Raj: comments and issue reports (FR32, FR27a-b) on the Review page: empty state, post, resolve, issue report, @mention,
 * and a Viewer who can post but cannot resolve someone else's thread. */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { beforeAll, describe, expect, it } from 'vitest'
import type { Schemas } from '@/api/client'
import { getDb, membersOf, projectView, save } from '@/mocks/db'
import { server } from '@/mocks/node'
import { renderApp } from '@/test/render'
import { seedProject } from '@/test/seed'

type Row = Schemas['Comment'] & { project_id: string }
const stored = () => (getDb() as unknown as { comments?: Row[] }).comments ?? []
/** The posted thread (not the text box, which holds the same words until the post finishes). */
const thread = async (panel: HTMLElement) => within(await within(panel).findByRole('list', { name: 'Comments' }))

async function openPanel() {
  const user = userEvent.setup()
  renderApp('/projects/pr_1/review')
  await user.click(await screen.findByRole('button', { name: 'Comments on R-001' }))
  const panel = await screen.findByRole('dialog', { name: 'Comments R-001' })
  return { user, panel }
}

describe('Comments panel', () => {
  beforeAll(() => {
    // jsdom has no ResizeObserver (the Radix Checkbox measures itself); stub just enough, like the backlog test.
    globalThis.ResizeObserver ??= class {
      observe() {}
      unobserve() {}
      disconnect() {}
    } as unknown as typeof ResizeObserver
  })

  it('shows the requirement and "No comments yet." when there are none', async () => {
    seedProject()
    const { panel } = await openPanel()
    expect(within(panel).getByText('The librarian shall issue a book to a member.')).toBeInTheDocument()
    expect(await within(panel).findByText('No comments yet.')).toBeInTheDocument()
    expect(within(panel).getByRole('button', { name: 'Post' })).toBeDisabled()
  })

  it('posts a comment, counts it on the row, then resolves it', async () => {
    seedProject()
    const { user, panel } = await openPanel()
    await user.type(within(panel).getByLabelText('Comment'), 'Should this say weekdays only?')
    await user.click(within(panel).getByRole('button', { name: 'Post' }))
    expect(await (await thread(panel)).findByText('Should this say weekdays only?')).toBeInTheDocument()
    await waitFor(() => expect(within(panel).getByLabelText('Comment')).toHaveValue(''))
    expect(await screen.findByRole('button', { name: 'Comments on R-001 (1 open)', hidden: true })).toBeInTheDocument()

    await user.click(within(panel).getByRole('button', { name: 'Resolve' }))
    expect(await within(panel).findByText(/Resolved by Dev/)).toBeInTheDocument()
    expect(within(panel).queryByRole('button', { name: 'Resolve' })).not.toBeInTheDocument()
    expect(stored()[0]).toMatchObject({ status: 'resolved', target_type: 'statement', target_id: 'st_1' })
  })

  it('sends an issue report when the box is ticked', async () => {
    seedProject()
    const { user, panel } = await openPanel()
    await user.type(within(panel).getByLabelText('Comment'), 'R-001 is drawn twice.')
    await user.click(within(panel).getByRole('checkbox', { name: 'Send as an issue report' }))
    await user.click(within(panel).getByRole('button', { name: 'Post' }))
    expect(await (await thread(panel)).findByText('Issue report')).toBeInTheDocument()
    expect(stored()).toHaveLength(1)
    expect(stored()[0].is_issue_report).toBe(true)
    expect(within(panel).getByRole('checkbox', { name: 'Send as an issue report' })).not.toBeChecked() // reset for the next one
  })

  it('suggests members after @ and sends the picked person as a mention', async () => {
    seedProject()
    membersOf('pr_1').push({ email: 'priya@sddg.test', role: 'editor', joined_at: new Date().toISOString() })
    save()
    let sent: Schemas['CommentCreate'] | undefined
    server.use(
      http.post('*/projects/:project_id/comments', async ({ request }) => {
        sent = (await request.clone().json()) as Schemas['CommentCreate']
        // nothing returned: the normal mock handler answers
      }),
    )
    const { user, panel } = await openPanel()
    await user.type(within(panel).getByLabelText('Comment'), 'Over to @pr')
    await user.click(await within(panel).findByRole('option', { name: /Priya/ }))
    expect(within(panel).getByLabelText('Comment')).toHaveValue('Over to @Priya ')
    await user.click(within(panel).getByRole('button', { name: 'Post' }))
    await waitFor(() => expect(sent?.mentions).toEqual(['dev:priya@sddg.test']))
    expect(await (await thread(panel)).findByText('Over to @Priya')).toBeInTheDocument() // wait for the post to finish
  })

  it('lets a Viewer post but not resolve someone else’s thread', async () => {
    seedProject()
    ;(getDb() as unknown as { comments: Row[] }).comments = [
      {
        id: 'cm_1', project_id: 'pr_1', target_type: 'statement', target_id: 'st_1', target_label: 'R-001', body: 'Check the loan limit.',
        is_issue_report: false, status: 'open', author: { id: 'dev:priya@sddg.test', email: 'priya@sddg.test' },
        resolved_by: null, resolved_at: null, created_at: new Date().toISOString(),
      },
    ]
    save()
    server.use(http.get('*/projects/:project_id', () => HttpResponse.json({ ...projectView(getDb().projects[0]), role: 'viewer', is_owner: false })))
    const { user, panel } = await openPanel()
    expect(await (await thread(panel)).findByText('Check the loan limit.')).toBeInTheDocument()
    expect(within(panel).queryByRole('button', { name: 'Resolve' })).not.toBeInTheDocument()

    await user.type(within(panel).getByLabelText('Comment'), 'Agreed.')
    await user.click(within(panel).getByRole('button', { name: 'Post' }))
    expect(await (await thread(panel)).findByText('Agreed.')).toBeInTheDocument()
    expect(within(panel).getAllByRole('button', { name: 'Resolve' })).toHaveLength(1) // only on the Viewer's own comment
  })
})
