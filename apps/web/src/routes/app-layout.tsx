import { LogOutIcon, ShieldCheckIcon } from 'lucide-react'
import { DropdownMenu } from 'radix-ui'
import { Link, Outlet, useNavigate } from 'react-router'
import { AppearanceMenu } from '@/components/appearance'
import { ServerWakingBanner } from '@/components/server-waking-banner'
import { Wordmark } from '@/components/wordmark'
import { useAuth } from '@/features/auth/auth-context'
import { NotificationBell } from '@/features/notifications/NotificationBell'
import { useMe } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { useJobWatcher } from '@/features/notifications/useJobWatcher'

const item = 'flex cursor-pointer items-center gap-2 rounded-md px-2.5 py-2 text-[13px] outline-none data-[highlighted]:bg-ink/5'

export function AppLayout() {
  const { session, signOut } = useAuth()
  const me = useMe()
  const navigate = useNavigate()
  useJobWatcher() // notifications (#46): watch started jobs on every page
  const initials = (session?.email ?? '?').slice(0, 2).toUpperCase()

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-30 border-b border-rule bg-surface/95 backdrop-blur">
        <div className="flex h-14 items-center gap-3 px-4 sm:px-5">
          <Link to="/projects" aria-label="SDDG projects">
            <Wordmark />
          </Link>
          <div className="ml-auto flex items-center gap-1.5">
            {me.data?.is_admin && (
              <Button asChild variant="secondary" size="sm">
                <Link to="/admin/users">Admin console</Link>
              </Button>
            )}
            <AppearanceMenu />
            <NotificationBell />
            <DropdownMenu.Root>
              <DropdownMenu.Trigger
                aria-label="Account"
                className="grid size-8 place-items-center rounded-full bg-accent text-[12px] font-semibold text-on-ink"
              >
                {initials}
              </DropdownMenu.Trigger>
              <DropdownMenu.Portal>
                <DropdownMenu.Content align="end" sideOffset={8} className="z-50 min-w-56 rounded-xl border border-rule bg-surface p-1.5 shadow-[var(--shadow)]">
                  <p className="truncate px-2.5 pt-1.5 pb-2 text-[12px] text-slate">{session?.email}</p>
                  <DropdownMenu.Item className={item} onSelect={() => navigate('/privacy')}>
                    <ShieldCheckIcon className="size-4" /> Privacy Policy
                  </DropdownMenu.Item>
                  <DropdownMenu.Item
                    className={item}
                    onSelect={async () => {
                      await signOut()
                      navigate('/login', { replace: true })
                    }}
                  >
                    <LogOutIcon className="size-4" /> Log out
                  </DropdownMenu.Item>
                </DropdownMenu.Content>
              </DropdownMenu.Portal>
            </DropdownMenu.Root>
          </div>
        </div>
        <ServerWakingBanner />
      </header>
      <main className="flex min-h-0 flex-1 flex-col">
        <Outlet />
      </main>
    </div>
  )
}