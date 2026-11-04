import { LogOutIcon } from 'lucide-react'
import { Link, Outlet, useNavigate } from 'react-router'
import { Footer } from '@/components/footer'
import { ServerWakingBanner } from '@/components/server-waking-banner'
import { Button } from '@/components/ui/button'
import { Wordmark } from '@/components/wordmark'
import { useAuth } from '@/features/auth/auth-context'
import { NotificationBell } from '@/features/notifications/NotificationBell'
import { useJobWatcher } from '@/features/notifications/useJobWatcher'

export function AppLayout() {
  const { session, signOut } = useAuth()
  const navigate = useNavigate()
  useJobWatcher()

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-30 border-b border-rule bg-surface/95 backdrop-blur">
        <div className="flex h-14 items-center justify-between gap-4 px-4 sm:px-6">
          <Link to="/projects" aria-label="SDDG projects">
            <Wordmark />
          </Link>
          <div className="flex min-w-0 items-center gap-2">
            <span className="hidden truncate text-sm text-slate sm:inline">{session?.email}</span>
            <NotificationBell />
            <Button
              variant="ghost"
              size="sm"
              onClick={async () => {
                await signOut()
                navigate('/login', { replace: true })
              }}
            >
              <LogOutIcon /> Log out
            </Button>
          </div>
        </div>
        <ServerWakingBanner />
      </header>
      <main className="flex-1">
        <Outlet />
      </main>
      <Footer />
    </div>
  )
}