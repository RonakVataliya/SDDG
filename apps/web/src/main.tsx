import { QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router/dom'
import { AuthProvider } from '@/features/auth/auth-context'
import { env } from '@/lib/env'
import { createQueryClient } from '@/lib/query-client'
import { router } from '@/routes/router'
import './index.css'

async function start() {
  if (env.useMocks) {
    const { worker } = await import('./mocks/browser')
    await worker.start({ onUnhandledRequest: 'bypass', quiet: true })
  }
  const queryClient = createQueryClient()
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <RouterProvider router={router} />
        </AuthProvider>
      </QueryClientProvider>
    </StrictMode>,
  )
}

void start()
