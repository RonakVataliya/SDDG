import { NavLink, Outlet } from 'react-router'
import { useMe } from '@/api/queries'
import { errorMessage } from '@/api/errors'
import { Notice } from '@/components/ui/notice'
import { PageLoading } from '@/components/ui/spinner'
import { cn } from '@/lib/utils'

const PAGES = [
  { to: 'users', label: 'Users' },
  { to: 'usage', label: 'Usage' },
  { to: 'errors', label: 'Errors' },
  { to: 'feedback', label: 'Feedback' },
  { to: 'settings', label: 'Settings' },
]

/** The Admin console shell (FR23). The API refuses every /admin call from a non-administrator; this only hides the UI. */
export function AdminLayout() {
  const me = useMe()
  if (me.isPending) return <PageLoading label="Checking access" />
  if (me.isError)
    return (
      <div className="p-5">
        <Notice tone="error" title="Couldn't check your access">
          {errorMessage(me.error)}
        </Notice>
      </div>
    )
  if (!me.data.is_admin)
    return (
      <div className="p-5">
        <Notice tone="error" title="Administrators only">
          Your account is not a System Administrator.
        </Notice>
      </div>
    )
  return (
    <div className="flex min-h-0 flex-1 flex-col md:flex-row">
      <nav aria-label="Admin console" className="shrink-0 border-b border-rule p-3 md:w-52 md:border-r md:border-b-0 md:p-4">
        <p className="px-2 pb-2 text-[11px] font-semibold tracking-wider text-slate">ADMIN CONSOLE</p>
        <ul className="flex gap-1 md:flex-col">
          {PAGES.map((p) => (
            <li key={p.to}>
              <NavLink
                to={p.to}
                className={({ isActive }) => cn('block rounded-md px-2.5 py-1.5 text-[13px] font-medium', isActive ? 'bg-accent-wash text-accent-deep' : 'text-ink-2 hover:bg-ink/5')}
              >
                {p.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
      <section className="min-w-0 flex-1 p-4 sm:p-6">
        <Outlet />
      </section>
    </div>
  )
}
