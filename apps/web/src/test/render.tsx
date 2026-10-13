import { QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { AuthProvider } from '@/features/auth/auth-context'
import { createQueryClient } from '@/lib/query-client'
import { routes } from '@/routes/router'

/** Signs in as a verified mock user and renders the real route tree at `path`. */
export function renderApp(path: string, { signedIn = true } = {}) {
  if (signedIn) {
    localStorage.setItem('sddg.mock.users', JSON.stringify([{ email: 'dev@sddg.test', password: 'password1', verified: true }]))
    localStorage.setItem('sddg.mock.session', JSON.stringify({ email: 'dev@sddg.test', accessToken: 'mock-token:dev@sddg.test' }))
  }
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  const queryClient = createQueryClient()
  queryClient.setDefaultOptions({ queries: { retry: false }, mutations: { retry: false } })
  return {
    router,
    ...render(
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <RouterProvider router={router} />
        </AuthProvider>
      </QueryClientProvider>,
    ),
  }
}
