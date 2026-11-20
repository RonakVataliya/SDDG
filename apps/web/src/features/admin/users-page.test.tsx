import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { makeAdmin, resetAdminMock } from '@/mocks/admin'
import { renderApp } from '@/test/render'

beforeEach(resetAdminMock)

const rowOf = async (email: string) => within((await screen.findByText(email)).closest('tr')!)

describe('FR23 admin console', () => {
  it('hides the Admin console from a normal user and refuses the page', async () => {
    renderApp('/projects')
    expect(await screen.findByRole('heading', { name: /projects/i })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Admin console' })).not.toBeInTheDocument()

    renderApp('/admin/users')
    expect(await screen.findByText('Administrators only')).toBeInTheDocument()
  })

  it('shows the button to an administrator and lists users 25 per page, searchable', async () => {
    makeAdmin('dev@sddg.test')
    const user = userEvent.setup()
    renderApp('/projects')
    await user.click(await screen.findByRole('link', { name: 'Admin console' }))

    expect(await screen.findByRole('heading', { name: 'Users' })).toBeInTheDocument()
    expect(await screen.findByText('1–25 of 30')).toBeInTheDocument()
    expect(screen.getAllByRole('row')).toHaveLength(26) // header + 25
    await user.click(screen.getByRole('button', { name: 'Next' }))
    expect(await screen.findByText('26–30 of 30')).toBeInTheDocument()

    await user.type(screen.getByLabelText('Search users'), 'person07')
    expect(await screen.findByText('1–1 of 1')).toBeInTheDocument()
    // A space matches any text, like the API: "person 07" finds person07@acme.test (shown as "Person07").
    await user.clear(screen.getByLabelText('Search users'))
    await user.type(screen.getByLabelText('Search users'), 'person 07')
    expect(await screen.findByText('1–1 of 1')).toBeInTheDocument()
    expect((await rowOf('person07@acme.test')).getByText('never')).toBeInTheDocument() // never signed in
  })

  it('deactivates and reactivates, keeping their projects, and explains a refusal', async () => {
    makeAdmin('dev@sddg.test')
    const user = userEvent.setup()
    renderApp('/admin/users')
    await user.type(await screen.findByLabelText('Search users'), 'person02')
    await user.click(await screen.findByRole('button', { name: 'Actions for person02@acme.test' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Deactivate' }))
    expect(await screen.findByText('Access revoked. Their 2 projects are kept.')).toBeInTheDocument()
    await waitFor(async () => expect((await rowOf('person02@acme.test')).getByText('Deactivated')).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: 'Actions for person02@acme.test' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Reactivate' }))
    await waitFor(async () => expect((await rowOf('person02@acme.test')).getByText('Active')).toBeInTheDocument())

    // The only owner of projects other people are in cannot be deactivated until ownership moves.
    await user.clear(screen.getByLabelText('Search users'))
    await user.type(screen.getByLabelText('Search users'), 'person05')
    await user.click(await screen.findByRole('button', { name: 'Actions for person05@acme.test' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Deactivate' }))
    expect(await screen.findByText(/only owner of 2 projects with other members/)).toBeInTheDocument()
    expect((await rowOf('person05@acme.test')).getByText('Active')).toBeInTheDocument()
  })
})
