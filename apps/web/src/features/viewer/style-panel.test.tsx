
import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createQueryClient } from '@/lib/query-client'
import { getDb } from '@/mocks/db'
import { seedDiagram } from '@/test/seed'
import { StylePanel } from './style-panel'

function renderPanel() {
  const queryClient = createQueryClient()
  queryClient.setDefaultOptions({
    queries: { retry: false },
    mutations: { retry: false },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <StylePanel
        diagramId="dg_1"
        diagramType="use_case"
        onPreviewChange={() => {}}
      />
    </QueryClientProvider>,
  )
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
})
