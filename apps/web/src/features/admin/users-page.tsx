import { MoreHorizontalIcon } from 'lucide-react'
import { DropdownMenu } from 'radix-ui'
import { useEffect, useState } from 'react'
import type { AdminUser } from '@/api/client'
import { errorMessage } from '@/api/errors'
import { useAdminUsers, useSetUserActive } from '@/api/queries'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { fieldClass } from '@/components/ui/input'
import { Notice } from '@/components/ui/notice'
import { PageLoading } from '@/components/ui/spinner'
import { ago } from './time'

const item = 'flex cursor-pointer items-center gap-2 rounded-md px-2.5 py-2 text-[13px] outline-none data-[highlighted]:bg-ink/5'
// Accounts have no name yet, so the Name column is made from the email: priya.shah@x -> Priya Shah.
const nameOf = (email: string) =>
  email.split('@')[0].split(/[._-]+/).filter(Boolean).map((w) => w[0].toUpperCase() + w.slice(1)).join(' ')

/** FR23a-d: every account, searchable, 25 per page, with deactivate and reactivate. */
export function UsersPage() {
  const [text, setText] = useState('')
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)
  const [result, setResult] = useState<{ tone: 'info' | 'error'; text: string } | null>(null)
  const users = useAdminUsers(q, page)
  const setActive = useSetUserActive()

  useEffect(() => {
    const t = setTimeout(() => {
      setQ(text.trim())
      setPage(1)
    }, 300)
    return () => clearTimeout(t)
  }, [text])

  const act = (u: AdminUser, active: boolean) => {
    setResult(null)
    setActive.mutate(
      { userId: u.id, active },
      {
        onSuccess: () =>
          setResult({
            tone: 'info',
            text: active ? `${nameOf(u.email)} can sign in again.` : `Access revoked. Their ${u.projects} project${u.projects === 1 ? '' : 's'} ${u.projects === 1 ? 'is' : 'are'} kept.`,
          }),
        onError: (e) => setResult({ tone: 'error', text: errorMessage(e) }),
      },
    )
  }

  const data = users.data
  const first = data && data.total ? (data.page - 1) * data.page_size + 1 : 0
  const last = data ? Math.min(data.page * data.page_size, data.total) : 0

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">Users</h1>
        <Badge tone="neutral" className="bg-ink text-on-ink">System Administrator</Badge>
      </div>
      <input
        type="search"
        aria-label="Search users"
        placeholder="Search by name or email"
        value={text}
        onChange={(e) => setText(e.target.value)}
        className={`${fieldClass} h-9 max-w-sm text-sm`}
      />
      {result && <Notice tone={result.tone === 'error' ? 'error' : 'info'}>{result.text}</Notice>}
      {users.isPending ? (
        <PageLoading label="Loading users" />
      ) : users.isError ? (
        <Notice tone="error" title="Couldn't load users">
          {errorMessage(users.error)}
        </Notice>
      ) : (
        <>
          <div className="overflow-x-auto rounded-xl border border-rule">
            <table className="w-full text-left text-[13px]">
              <thead className="border-b border-rule bg-field text-[12px] text-slate">
                <tr>
                  {['Name', 'Email', 'Projects', 'Last active', 'Status'].map((h) => (
                    <th key={h} className="px-3 py-2 font-medium">{h}</th>
                  ))}
                  <th className="w-10 px-3 py-2"><span className="sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody>
                {data!.users.map((u) => (
                  <tr key={u.id} className="border-b border-rule last:border-0">
                    <td className="px-3 py-2 font-medium">
                      {nameOf(u.email)} {u.is_admin && <Badge tone="accent" className="ml-1">Admin</Badge>}
                    </td>
                    <td className="px-3 py-2 text-ink-2">{u.email}</td>
                    <td className="px-3 py-2">{u.projects}</td>
                    <td className="px-3 py-2 text-ink-2">{ago(u.last_seen_at)}</td>
                    <td className="px-3 py-2">
                      <Badge tone={u.status === 'active' ? 'success' : 'danger'}>{u.status === 'active' ? 'Active' : 'Deactivated'}</Badge>
                    </td>
                    <td className="px-3 py-2">
                      <DropdownMenu.Root>
                        <DropdownMenu.Trigger aria-label={`Actions for ${u.email}`} className="grid size-7 place-items-center rounded-md hover:bg-ink/5">
                          <MoreHorizontalIcon className="size-4" />
                        </DropdownMenu.Trigger>
                        <DropdownMenu.Portal>
                          <DropdownMenu.Content align="end" sideOffset={4} className="z-50 min-w-40 rounded-xl border border-rule bg-surface p-1.5 shadow-[var(--shadow)]">
                            {u.status === 'active' ? (
                              <DropdownMenu.Item className={item} onSelect={() => act(u, false)}>Deactivate</DropdownMenu.Item>
                            ) : (
                              <DropdownMenu.Item className={item} onSelect={() => act(u, true)}>Reactivate</DropdownMenu.Item>
                            )}
                          </DropdownMenu.Content>
                        </DropdownMenu.Portal>
                      </DropdownMenu.Root>
                    </td>
                  </tr>
                ))}
                {!data!.users.length && (
                  <tr><td colSpan={6} className="px-3 py-6 text-center text-slate">No users match.</td></tr>
                )}
              </tbody>
            </table>
          </div>
          <div className="flex items-center justify-between text-[13px] text-slate">
            <span>{first}–{last} of {data!.total}</span>
            <div className="flex gap-2">
              <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button>
              <Button size="sm" variant="secondary" disabled={last >= data!.total} onClick={() => setPage(page + 1)}>Next</Button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
