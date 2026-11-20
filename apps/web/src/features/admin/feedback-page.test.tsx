/** Raj: admin Feedback page (FR27c). Only issue reports show, never plain comments; filter by status; close a report;
 * a non-administrator is refused. */
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { Schemas } from '@/api/client'
import { makeAdmin, resetAdminMock } from '@/mocks/admin'
import { getDb, save } from '@/mocks/db'
import { renderApp } from '@/test/render'
import { seedProject } from '@/test/seed'

type Row = Schemas['Comment'] & { project_id: string }
const minutesAgo = (m: number) => new Date(Date.now() - m * 60_000).toISOString()
const row = (n: number, extra: Partial<Row>): Row => ({
  id: `cm_${n}`, project_id: 'pr_1', target_type: 'statement', target_id: 'st_1', target_label: 'R-001', body: `Comment ${n}`,
  is_issue_report: true, status: 'open', author: { id: 'dev:priya@sddg.test', email: 'priya@sddg.test' },
  resolved_by: null, resolved_at: null, created_at: minutesAgo(n), ...extra,
})

function seedReports() {
  seedProject()
  ;(getDb() as unknown as { comments: Row[] }).comments = [
    row(1, { body: 'R-001 is drawn twice.' }),
    row(2, { body: 'The ZIP export is empty.', target_type: 'project', target_id: 'pr_1', target_label: 'Project' }),
    row(3, { body: 'Just a note, not a report.', is_issue_report: false }),
    row(4, { body: 'Fixed already.', status: 'resolved', resolved_by: 'Dev', resolved_at: minutesAgo(1) }),
  ]
  save()
}

const rows = () => within(screen.getByRole('table')).getAllByRole('row').slice(1)

describe('FR27c admin Feedback page', () => {
  beforeEach(() => {
    resetAdminMock()
    makeAdmin('dev@sddg.test')
  })

  it('is reached from the sidebar, between Errors and Settings, and lists open reports only', async () => {
    seedReports()
    const user = userEvent.setup()
    renderApp('/admin/users')
    const nav = await screen.findByRole('navigation', { name: 'Admin console' })
    expect(within(nav).getAllByRole('link').map((l) => l.textContent)).toEqual(['Users', 'Usage', 'Errors', 'Feedback', 'Settings'])
    await user.click(within(nav).getByRole('link', { name: 'Feedback' }))

    expect(await screen.findByRole('heading', { name: 'Feedback' })).toBeInTheDocument()
    await screen.findByText('1–2 of 2')
    const [first, second] = rows()
    expect(within(first).getByText('R-001 is drawn twice.')).toBeInTheDocument()
    expect(within(first).getByText('R-001')).toBeInTheDocument() // the chip: the ref, never the requirement's text
    expect(within(first).getByText('Library system')).toBeInTheDocument()
    expect(within(first).getByText('priya@sddg.test')).toBeInTheDocument()
    expect(within(first).getByText('Open')).toBeInTheDocument()
    expect(within(second).getByText('Project export')).toBeInTheDocument()
    expect(screen.queryByText('Just a note, not a report.')).not.toBeInTheDocument() // a plain comment never shows
    expect(screen.queryByText('The librarian shall issue a book to a member.')).not.toBeInTheDocument()
  })

  it('filters by status and closes a report', async () => {
    seedReports()
    const user = userEvent.setup()
    renderApp('/admin/feedback')
    await screen.findByText('1–2 of 2')

    await user.selectOptions(screen.getByLabelText('Status'), 'resolved')
    expect(await screen.findByText('1–1 of 1')).toBeInTheDocument()
    expect(within(rows()[0]).getByText('Resolved by Dev')).toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('Status'), '')
    expect(await screen.findByText('1–3 of 3')).toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('Status'), 'open')
    await screen.findByText('1–2 of 2')
    await user.click(screen.getByRole('button', { name: 'Close the report on R-001' }))
    expect(await screen.findByText('1–1 of 1')).toBeInTheDocument()
    expect(screen.queryByText('R-001 is drawn twice.')).not.toBeInTheDocument()
    const closed = (getDb() as unknown as { comments: Row[] }).comments.find((c) => c.id === 'cm_1')
    expect(closed).toMatchObject({ status: 'resolved', resolved_by: 'Dev' })
  })

  it('says so when there are no reports', async () => {
    seedProject()
    renderApp('/admin/feedback')
    expect(await screen.findByText('No open reports.')).toBeInTheDocument()
  })

  it('refuses a user who is not an administrator', async () => {
    resetAdminMock()
    renderApp('/admin/feedback')
    expect(await screen.findByText('Administrators only')).toBeInTheDocument()
  })
})
