
import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { createQueryClient } from '@/lib/query-client'
import { getDb } from '@/mocks/db'
import { renderApp } from '@/test/render'
import { seedDiagram } from '@/test/seed'
import { StylePanel } from './style-panel'

function renderPanel(diagramType: 'use_case' | 'activity' = 'use_case') {
  const queryClient = createQueryClient()
  queryClient.setDefaultOptions({
    queries: { retry: false },
    mutations: { retry: false },
  })

  // useBlocker needs a data router; /elsewhere stands in for another version.
  const router = createMemoryRouter(
    [
      { path: '/', element: <StylePanel diagramId="dg_1" diagramType={diagramType} onPreviewChange={() => {}} /> },
      { path: '/elsewhere', element: <p>Another version</p> },
    ],
    { initialEntries: ['/'] },
  )

  return {
    router,
    ...render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    ),
  }
}

beforeEach(() => {
  localStorage.setItem(
    'sddg.mock.session',
    JSON.stringify({
      email: 'dev@sddg.test',
      accessToken: 'mock-token:dev@sddg.test',
    }),
  )
  seedDiagram()
})

describe('StylePanel', () => {
  it('asks for confirmation before saving low-contrast colours', async () => {
    const user = userEvent.setup()
    renderPanel()

    await screen.findByRole('heading', { name: 'Customise diagram' })

    fireEvent.change(screen.getByLabelText('Text colour'), {
      target: { value: '#ffffff' },
    })

    await user.click(screen.getByRole('button', { name: 'Save changes' }))

    const dialog = await screen.findByRole('alertdialog', {
      name: 'Low contrast warning',
    })

    expect(
      screen.getByText('Text might be hard to read. Apply anyway?'),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cancel' })).toHaveFocus()
    expect(getDb().diagrams[0].style).toBeUndefined()

    await user.click(
      screen.getByRole('button', { name: 'Cancel' }),
    )

    expect(dialog).not.toBeInTheDocument()
    expect(getDb().diagrams[0].style).toBeUndefined()
  })

  it('saves low-contrast colours after Apply anyway is confirmed', async () => {
    const user = userEvent.setup()
    renderPanel()

    await screen.findByRole('heading', { name: 'Customise diagram' })

    fireEvent.change(screen.getByLabelText('Text colour'), {
      target: { value: '#ffffff' },
    })

    await user.click(screen.getByRole('button', { name: 'Save changes' }))
    await screen.findByRole('alertdialog', { name: 'Low contrast warning' })

    await user.click(screen.getByRole('button', { name: 'Apply anyway' }))

    await waitFor(() => {
      expect(getDb().diagrams[0].style).toMatchObject({
        text: '#ffffff',
      })
    })
  })

  it('closes the low-contrast warning when any setting changes', async () => {
    const user = userEvent.setup()
    renderPanel()
    await screen.findByRole('heading', { name: 'Customise diagram' })

    fireEvent.change(screen.getByLabelText('Text colour'), { target: { value: '#ffffff' } })
    await user.click(screen.getByRole('button', { name: 'Save changes' }))
    await screen.findByRole('alertdialog', { name: 'Low contrast warning' })

    fireEvent.change(screen.getByLabelText('Font size'), { target: { value: '18' } })
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
  })

  it('asks before leaving with unsaved changes, and lets you stay or leave', async () => {
    const user = userEvent.setup()
    const { router } = renderPanel()
    await screen.findByRole('heading', { name: 'Customise diagram' })

    fireEvent.change(screen.getByLabelText('Font size'), { target: { value: '18' } })
    void router.navigate('/elsewhere')
    expect(await screen.findByText('Leave without saving the new look?')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Stay' }))
    expect(screen.getByText('18 pt')).toBeInTheDocument()

    void router.navigate('/elsewhere')
    await user.click(await screen.findByRole('button', { name: 'Leave without saving' }))
    expect(await screen.findByText('Another version')).toBeInTheDocument()
  })

  it('does not ask before leaving once the changes are saved', async () => {
    const user = userEvent.setup()
    const { router } = renderPanel()
    await screen.findByRole('heading', { name: 'Customise diagram' })

    await user.selectOptions(screen.getByLabelText('Layout direction'), 'TB')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(getDb().diagrams[0].style).toMatchObject({ direction: 'TB' }))

    void router.navigate('/elsewhere')
    expect(await screen.findByText('Another version')).toBeInTheDocument()
  })

  it('allows font sizes from 8 to 24', async () => {
    renderPanel()

    await screen.findByRole('heading', { name: 'Customise diagram' })

    const slider = screen.getByLabelText('Font size')

    expect(slider).toHaveAttribute('min', '8')
    expect(slider).toHaveAttribute('max', '24')

   fireEvent.change(slider, { target: { value: '8' } })
   expect(slider).toHaveValue('8')

   fireEvent.change(slider, { target: { value: '24' } })
   expect(slider).toHaveValue('24')

  })

  it('saves a changed layout direction', async () => {
    const user = userEvent.setup()
    renderPanel()

    await screen.findByRole('heading', { name: 'Customise diagram' })

    await user.selectOptions(
      screen.getByLabelText('Layout direction'),
      'TB',
    )

    await user.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() => {
      expect(getDb().diagrams[0].style).toMatchObject({
        direction: 'TB',
      })
    })
  })

  it('loads the saved font size again after the panel is remounted', async () => {
    const user = userEvent.setup()
    const firstRender = renderPanel()

    await screen.findByRole('heading', { name: 'Customise diagram' })

    fireEvent.change(screen.getByLabelText('Font size'), {
      target: { value: '18' },
    })

    await user.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() => {
      expect(getDb().diagrams[0].style).toMatchObject({
        font_size: 18,
      })
    })

    firstRender.unmount()

    renderPanel()

    expect(await screen.findByText('18 pt')).toBeInTheDocument()
  })

  it('hides layout direction for activity diagrams', async () => {
    renderPanel('activity')
    await screen.findByRole('heading', { name: 'Customise diagram' })
    expect(screen.queryByLabelText('Layout direction')).not.toBeInTheDocument()
  })

  it('is offered on a version drawn by Kroki, and replaced by a note on a version with moved elements', async () => {
    const { unmount } = renderApp('/projects/pr_1/diagrams/dg_1')
    expect(await screen.findByRole('heading', { name: 'Customise diagram' })).toBeInTheDocument()
    unmount()

    getDb().diagrams[0].layout = { it_1: [150, 150] }
    renderApp('/projects/pr_1/diagrams/dg_1')
    expect(await screen.findByText(/were moved by hand, so it keeps the standard look/)).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Customise diagram' })).not.toBeInTheDocument()
  })
})
