import { Navigate, Outlet, useLocation } from 'react-router'
import { PageLoading } from '@/components/ui/spinner'
import { useAuth } from '@/features/auth/auth-context'

/** NFR4a: every app page requires login; the user returns to where they were after logging in. */
export function RequireAuth() {
  const { session, ready } = useAuth()
  const location = useLocation()
  if (!ready) return <PageLoading />
  if (!session) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  return <Outlet />
}
