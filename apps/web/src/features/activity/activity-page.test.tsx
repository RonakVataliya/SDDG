import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '@/mocks/node'
import { renderApp } from '@/test/render'
import { seedProject } from '@/test/seed'


describe('FR22 project Activity tab', () => {
  it('is a tab for the Owner and lists who did what, newest first, in plain sentences', async () => {
    seedProject()
    const user = userEvent.setup()
    renderApp('/projects/pr_1/members')
    await user.click(await screen.findByRole('link', { name: 'Activity' }))

    expect(await screen.findByRole('heading', { name: 'Activity' })).toBeInTheDocument()
    expect(await screen.findByText('Dev regenerated Use case diagram v3 after a requirement change')).toBeInTheDocument()
    expect(screen.getByText('Priya commented on R-006')).toBeInTheDocument()
    expect(screen.getByText('Priya edited R-004 - rev 2 -> 3')).toBeInTheDocument()
    expect(screen.getByText("Dev changed Karan's role: Viewer → Editor")).toBeInTheDocument()
    expect(screen.getByText('Meera accepted the invitation and joined as Editor')).toBeInTheDocument()
    expect(screen.getByText('Dev invited meera@sddg.test as Editor')).toBeInTheDocument()
    expect(screen.getByText('2 min ago')).toBeInTheDocument()
    // The side card says what is kept, and what never is.
    const card = within(screen.getByRole('complementary', { name: 'What the log stores' }))
    expect(card.getByText(/Never the text of a requirement/)).toBeInTheDocument()
  })

  it('filters by what happened and by person', async () => {
    seedProject()
    const user = userEvent.setup()
    renderApp('/projects/pr_1/activity')
    await screen.findByText('1–6 of 6')

    await user.click(screen.getByRole('button', { name: 'Members' }))
    expect(await screen.findByText('1–3 of 3')).toBeInTheDocument()
    expect(screen.queryByText('Priya commented on R-006')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Comments' }))
    expect(await screen.findByText('1–1 of 1')).toBeInTheDocument()
    expect(screen.getByText('Priya commented on R-006')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'All' }))
    await screen.findByText('1–6 of 6')
    await user.selectOptions(screen.getByLabelText('Person'), 'dev:priya@sddg.test')
    expect(await screen.findByText('1–2 of 2')).toBeInTheDocument()
    expect(screen.queryByText(/invited meera/)).not.toBeInTheDocument()
  })

  it('says so when the log is empty', async () => {
    seedProject()
    server.use(http.get('*/projects/:id/activity', () => HttpResponse.json({ events: [], actors: [], total: 0, page: 1, page_size: 25 })))
    renderApp('/projects/pr_1/activity')
    expect(await screen.findByText('Nothing here yet.')).toBeInTheDocument()
  })

  it('shows the Owners-only message when the API refuses', async () => {
    seedProject()
    server.use(http.get('*/projects/:id/activity', () => HttpResponse.json({ detail: 'You do not have permission to do that.' }, { status: 403 })))
    renderApp('/projects/pr_1/activity')
    expect(await screen.findByText('Owners only')).toBeInTheDocument()
  })
})
