import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { makeAdmin, resetAdminMock } from '@/mocks/admin'
import { server } from '@/mocks/node'
import { renderApp } from '@/test/render'

beforeEach(() => {
  resetAdminMock()
  makeAdmin('dev@sddg.test')
})

const rows = () => within(screen.getByRole('table')).getAllByRole('row').slice(1)

describe('FR25d admin Errors page', () => {
  it('is reached from the sidebar and lists recent errors with time, type and severity', async () => {
    const user = userEvent.setup()
    renderApp('/admin/users')
    await user.click(await screen.findByRole('link', { name: 'Errors' }))

    expect(await screen.findByRole('heading', { name: 'Errors' })).toBeInTheDocument()
    await screen.findByText('1–25 of 30')
    const first = rows()[0]
    expect(within(first).getByText('ValueError in POST /projects/{project_id}/generate')).toBeInTheDocument()
    expect(within(first).getByText('API crash')).toBeInTheDocument()
    expect(within(first).getByText('Error')).toBeInTheDocument()
    expect(within(first).getByText('(10 min ago)')).toBeInTheDocument()
    expect(rows()).toHaveLength(25)
    expect(screen.getByText('1–25 of 30')).toBeInTheDocument()
  })

  it('filters by type and by severity, and pages', async () => {
    const user = userEvent.setup()
    renderApp('/admin/errors')
    await screen.findByText('1–25 of 30')

    await user.selectOptions(screen.getByLabelText('Type'), 'rate_limit')
    expect(await screen.findByText('1–7 of 7')).toBeInTheDocument() // every 4th of the 30 rows is a rate limit
    expect(rows().every((r) => within(r).queryByText('Rate limit'))).toBe(true)
    expect(within(rows()[0]).getByText('Warning')).toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('Severity'), 'error') // rate limits are warnings, so none match both
    expect(await screen.findByText(/No errors recorded for this filter/)).toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('Type'), '')
    await user.selectOptions(screen.getByLabelText('Severity'), '')
    await screen.findByText('1–25 of 30')
    await user.click(screen.getByRole('button', { name: 'Next' }))
    expect(await screen.findByText('26–30 of 30')).toBeInTheDocument()
    expect(rows()).toHaveLength(5)
  })

  it('says so when nothing has been recorded', async () => {
    server.use(http.get('*/admin/errors', () => HttpResponse.json({ errors: [], total: 0, page: 1, page_size: 25 })))
    renderApp('/admin/errors')
    expect(await screen.findByText('No errors recorded.')).toBeInTheDocument()
  })

  it('refuses a user who is not an administrator', async () => {
    resetAdminMock()
    renderApp('/admin/errors')
    expect(await screen.findByText('Administrators only')).toBeInTheDocument()
  })
})
