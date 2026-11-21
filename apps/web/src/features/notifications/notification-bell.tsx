import { BellIcon, CheckIcon, CircleAlertIcon, MailIcon, SparklesIcon } from 'lucide-react'
import { DropdownMenu as D } from 'radix-ui'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router'
import type { ServerNotification } from '@/api/client'
import { errorMessage } from '@/api/errors'
import { useAcceptInvitation, useMarkAllRead, useMarkRead, useNotifications, useUnreadCount } from '@/api/queries'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { displayName, roleLabel, withArticle } from '@/lib/people'
import { toast } from '@/lib/toast'
import { cn, formatRelative } from '@/lib/utils'

/** What a notification says, in one line. The server stores IDs only, so the wording is put together here. */
function line(n: ServerNotification) {
  const who = displayName(n.from_user?.email)
  const project = n.project?.name ?? 'a project'
  if (n.type === 'invitation') return `${who} invited you to ${project}`
  if (n.type === 'admin_invited') return `${who} (administrator) invited ${n.invitation?.email ?? 'someone'} to ${project}`
  if (n.type === 'generation_ready') return `Your diagram is ready in ${project}`
  if (n.type === 'generation_failed') return `Generating a diagram in ${project} did not finish`
  // FR32: the server sends the target's short label (a ref like R-006, or "Use Case diagram v3"), never the
  // comment's text. Older notifications have no target, so they keep the wording they were written with.
  if (n.payload.target) return `${who} mentioned you on ${n.payload.target} in ${project}`
  return `${who} mentioned you in ${project}`
}

/** Issue #36: where the row takes you — the diagram that was drawn, else the project's Generate step to try again. */
function destination(n: ServerNotification) {
  const projectId = n.payload.project_id
  if (!projectId) return null
  if (n.type === 'mention') {
    // FR32: take them to the thing that was commented on, not to the comment: a requirement lives on Review.
    if (n.payload.target_type === 'statement') return { to: `/projects/${projectId}/review`, label: 'View requirement' }
    if (n.payload.target_type === 'diagram' && n.payload.target_id)
      return { to: `/projects/${projectId}/diagrams/${n.payload.target_id}`, label: 'View diagram' }
    return { to: `/projects/${projectId}`, label: 'Open project' }
  }
  if (n.payload.diagram_id) return { to: `/projects/${projectId}/diagrams/${n.payload.diagram_id}`, label: 'View diagram' }
  if (n.type === 'generation_failed') return { to: `/projects/${projectId}/generate`, label: 'Try again' }
  if (n.type === 'generation_ready') return { to: `/projects/${projectId}/generate`, label: 'Open project' }
  return null
}

function Icon({ n, className }: { n: ServerNotification; className?: string }) {
  if (n.type === 'generation_failed') return <CircleAlertIcon className={className} aria-hidden />
  if (n.type === 'generation_ready') return <SparklesIcon className={className} aria-hidden />
  return <MailIcon className={className} aria-hidden />
}

function NotificationRow({ n, onDone }: { n: ServerNotification; onDone: () => void }) {
  const navigate = useNavigate()
  const accept = useAcceptInvitation()
  const markRead = useMarkRead()
  const unread = !n.read_at
  const open = n.type === 'invitation' && n.invitation?.status === 'open'
  const where = destination(n)
  const failed = n.type === 'generation_failed'

  async function onAccept() {
    if (!n.invitation) return
    const project = await accept.mutateAsync(n.invitation.id).catch(() => null)
    if (!project) return // the message stays in the row, so the dropdown is left open to try again
    toast(`You joined ${project.name} as ${withArticle(n.invitation.role)}.`)
    onDone()
    navigate(`/projects/${project.id}`)
  }

  return (
    <li className={cn('flex gap-2.5 border-b border-rule px-4 py-3 last:border-0', unread && 'bg-accent-wash/40')}>
      <Icon
        className={cn('mt-0.5 size-4 shrink-0', failed ? 'text-danger' : unread ? 'text-accent' : 'text-slate')}
        n={n}
      />
      <div className="min-w-0 flex-1">
        <p className="text-sm">{line(n)}</p>
        <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-slate">
          <span>{formatRelative(n.created_at)}</span>
          {n.invitation && (
            <>
              <span aria-hidden>·</span>
              <Badge tone={n.invitation.role === 'owner' ? 'violet' : n.invitation.role === 'editor' ? 'accent' : 'neutral'}>
                {roleLabel[n.invitation.role]}
              </Badge>
            </>
          )}
          {n.type === 'invitation' && n.invitation?.status === 'accepted' && <span>· Accepted</span>}
          {n.type === 'invitation' && n.invitation?.status === 'expired' && <span>· Expired</span>}
        </p>
        {where && (
          <Link
            to={where.to}
            className="mt-1 inline-block text-xs font-medium text-accent hover:underline"
            onClick={() => {
              if (unread) markRead.mutate(n.id)
              onDone()
            }}
          >
            {where.label}
          </Link>
        )}
        {open && (
          <div className="mt-2 flex items-center gap-2">
            <Button size="sm" onClick={onAccept} disabled={accept.isPending}>
              {accept.isPending ? <Spinner className="text-white" label="" /> : null} Accept
            </Button>
            {accept.isError && (
              <span role="alert" className="text-xs text-danger">
                {errorMessage(accept.error, 'That invitation could not be accepted.')}
              </span>
            )}
          </div>
        )}
      </div>
      {unread && (
        <button
          type="button"
          className="shrink-0 self-start rounded-sm p-0.5 text-slate hover:text-ink"
          aria-label="Mark as read"
          onClick={() => markRead.mutate(n.id)}
        >
          <CheckIcon className="size-3.5" />
        </button>
      )}
    </li>
  )
}

/** FR24a: invitations and @mentions. The count is polled; the list is fetched when the dropdown is opened. */
export function NotificationBell() {
  const [open, setOpen] = useState(false)
  const { data: count } = useUnreadCount()
  const { data, isPending, isError, error } = useNotifications(open)
  const markAll = useMarkAllRead()
  const unread = count?.count ?? data?.unread_count ?? 0

  return (
    <D.Root open={open} onOpenChange={setOpen}>
      <D.Trigger asChild>
        <button
          type="button"
          className="relative rounded-full p-2 text-slate hover:bg-ink/5 hover:text-ink focus-visible:outline-2 focus-visible:outline-accent/40"
          aria-label={unread ? `Notifications, ${unread} unread` : 'Notifications'}
        >
          <BellIcon className="size-5" aria-hidden />
          {unread > 0 && (
            <span
              aria-hidden
              className="absolute top-0.5 right-0.5 grid h-4 min-w-4 place-items-center rounded-full bg-danger px-1 text-[10px] font-semibold text-white tabular-nums"
            >
              {unread > 9 ? '9+' : unread}
            </span>
          )}
        </button>
      </D.Trigger>
      <D.Portal>
        <D.Content
          align="end"
          sideOffset={6}
          className="z-50 flex max-h-[28rem] w-[min(22rem,calc(100vw-2rem))] flex-col overflow-hidden rounded-lg border border-rule bg-surface shadow-[0_24px_48px_-12px_rgb(26_34_51/0.25)]"
        >
          <div className="flex shrink-0 items-center justify-between border-b border-rule px-4 py-2.5">
            <h2 className="text-sm font-medium">Notifications</h2>
            {unread > 0 && (
              <Button variant="link" size="sm" className="text-xs" onClick={() => markAll.mutate()} disabled={markAll.isPending}>
                Mark all read
              </Button>
            )}
          </div>
          {isPending ? (
            <div className="grid place-items-center py-10">
              <Spinner label="Loading notifications" />
            </div>
          ) : isError ? (
            <p role="alert" className="px-4 py-8 text-center text-sm text-danger">
              {errorMessage(error, "Couldn't load your notifications.")}
            </p>
          ) : data.items.length === 0 ? (
            <p className="px-4 py-10 text-center text-sm text-slate">Nothing yet. Invitations and mentions show up here.</p>
          ) : (
            <ul className="min-h-0 flex-1 overflow-y-auto">
              {data.items.map((n) => (
                <NotificationRow key={n.id} n={n} onDone={() => setOpen(false)} />
              ))}
            </ul>
          )}
        </D.Content>
      </D.Portal>
    </D.Root>
  )
}
