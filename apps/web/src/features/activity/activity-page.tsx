/** Activity tab (FR22): who did what in this project, for Owners and System Administrators. Rows come from the
 * activity log: user ids, an action and a target, never the text of a requirement. */
import { FileTextIcon, MessageSquareIcon, ShapesIcon, UsersIcon } from 'lucide-react'
import { useState } from 'react'
import type { ActivityEvent } from '@/api/client'
import { ApiError, errorMessage } from '@/api/errors'
import { useProjectActivity, type ActivityGroup } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { fieldClass } from '@/components/ui/input'
import { Notice } from '@/components/ui/notice'
import { PageLoading } from '@/components/ui/spinner'
import { nameOf } from '@/features/admin/name'
import { StepHeading } from '@/features/input/input-page'
import { cn, formatRelative } from '@/lib/utils'
import { useWorkspace } from '@/routes/workspace-layout'

const FILTERS: { key: ActivityGroup; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'members', label: 'Members' },
  { key: 'requirements', label: 'Requirements' },
  { key: 'diagrams', label: 'Diagrams' },
  { key: 'comments', label: 'Comments' },
]
const ICONS = { members: UsersIcon, requirements: FileTextIcon, diagrams: ShapesIcon, comments: MessageSquareIcon } as const
const cap = (s: unknown) => (typeof s === 'string' && s ? s[0].toUpperCase() + s.slice(1) : '')

/** The row's sentence, e.g. "Ronak invited meera@acme.example as Editor". Built from the action, the people and the
 * small values the log keeps; an action this page does not know yet falls back to its name. */
export function sentence(e: ActivityEvent): string {
  const who = e.actor_email ? nameOf(e.actor_email) : 'Someone'
  const subject = e.subject_email ?? 'someone'
  const d = e.detail ?? {}
  switch (e.action) {
    case 'member.invited': return `${who} invited ${subject} as ${cap(d.role) || 'a member'}`
    case 'member.joined': return `${who} accepted the invitation and joined as ${cap(d.role) || 'a member'}`
    case 'role.changed': return `${who} changed ${e.subject_email ? nameOf(e.subject_email) : 'someone'}'s role: ${cap(d.from)} → ${cap(d.to)}`
    case 'member.removed': return `${who} removed ${subject} from the project`
    case 'member.left': return `${who} left the project`
    case 'statement.edited': return `${who} edited ${e.target ?? 'a requirement'}`
    case 'statement.conflict_saved': return `${who} saved ${e.target ?? 'a requirement'} after an edit conflict`
    case 'statement.added': return `${who} added ${e.target ?? 'a requirement'}`
    case 'statement.deleted': return `${who} deleted ${e.target ?? 'a requirement'}`
    case 'comment.created': return `${who} commented on ${e.target ?? 'an item'}`
    case 'comment.resolved': return `${who} resolved the comment thread on ${e.target ?? 'an item'}`
    case 'diagram.saved': return `${who} saved ${e.target ?? 'a diagram'}${d.reason === 'naming' ? ' (naming consistency)' : ''}`
    case 'diagram.regenerated': return `${who} regenerated ${e.target ?? 'a diagram'}${d.reason === 'requirement_change' ? ' after a requirement change' : ''}`
    default: return `${who}: ${e.action}${e.target ? ` ${e.target}` : ''}`
  }
}

function Row({ e }: { e: ActivityEvent }) {
  const Icon = e.group ? ICONS[e.group] : FileTextIcon
  const initial = (e.actor_email ?? '?')[0].toUpperCase()
  return (
    <li className="flex items-center gap-3 px-4 py-3">
      <span className="grid size-8 shrink-0 place-items-center rounded-full bg-accent-wash text-accent-deep" aria-hidden><Icon className="size-4" /></span>
      <span className="grid size-7 shrink-0 place-items-center rounded-full bg-rule text-[12px] font-semibold text-ink-2" aria-hidden>{initial}</span>
      <span className="min-w-0 flex-1 text-[13.5px]">{sentence(e)}</span>
      <time dateTime={e.at} title={new Date(e.at).toLocaleString()} className="shrink-0 text-[12.5px] text-slate">{formatRelative(e.at)}</time>
    </li>
  )
}

export function ActivityPage() {
  const { project } = useWorkspace()
  const [group, setGroup] = useState<ActivityGroup>('all')
  const [actor, setActor] = useState('')
  const [page, setPage] = useState(1)
  const log = useProjectActivity(project.id, group, actor, page)
  const data = log.data
  const first = data && data.total ? (data.page - 1) * data.page_size + 1 : 0
  const last = data ? Math.min(data.page * data.page_size, data.total) : 0

  return (
    <div className="space-y-5">
      <StepHeading title="Activity" description="Who did what in this project. Only Owners can see this." />
      {log.isError && log.error instanceof ApiError && log.error.status === 403 ? (
        <Notice tone="error" title="Owners only">Only Owners and System Administrators can see a project's activity.</Notice>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
          <div className="min-w-0 space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <div role="group" aria-label="Show" className="flex flex-wrap gap-1">
                {FILTERS.map((f) => (
                  <button
                    key={f.key}
                    type="button"
                    aria-pressed={group === f.key}
                    onClick={() => { setGroup(f.key); setPage(1) }}
                    className={cn('rounded-full px-3 py-1.5 text-[13px]', group === f.key ? 'bg-accent-wash font-semibold text-accent-deep' : 'text-ink-2 hover:bg-ink/5')}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
              <select aria-label="Person" className={`${fieldClass} ml-auto h-9 w-auto text-sm`} value={actor} onChange={(e) => { setActor(e.target.value); setPage(1) }}>
                <option value="">Anyone</option>
                {(data?.actors ?? []).map((a) => <option key={a.id} value={a.id}>{a.email ? nameOf(a.email) : a.id}</option>)}
              </select>
            </div>
            {log.isPending ? (
              <PageLoading label="Loading activity" />
            ) : log.isError ? (
              <Notice tone="error" title="Couldn't load the activity">{errorMessage(log.error)}</Notice>
            ) : (
              <>
                <ul className="divide-y divide-rule rounded-lg border border-rule bg-surface">
                  {data!.events.map((e) => <Row key={e.id} e={e} />)}
                  {!data!.events.length && <li className="px-4 py-8 text-center text-[13px] text-slate">Nothing here yet.</li>}
                </ul>
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
          <aside aria-label="What the log stores" className="h-fit rounded-lg border border-rule bg-surface p-4 text-[13px]">
            <h3 className="text-[11px] font-semibold tracking-wider text-slate">WHAT THE LOG STORES</h3>
            <dl className="mt-3 space-y-2">
              <div><dt className="font-medium">Actor</dt><dd className="text-ink-2">the user ID of who did it</dd></div>
              <div><dt className="font-medium">Action</dt><dd className="text-ink-2">role.changed, statement.edited, comment.created, ...</dd></div>
              <div><dt className="font-medium">Target</dt><dd className="text-ink-2">R-004 - rev 3 → 4</dd></div>
              <div><dt className="font-medium">Time</dt><dd className="text-ink-2">when it happened</dd></div>
            </dl>
            <p className="mt-3 text-slate">Never the text of a requirement. Project content stays encrypted. Owners see their project's log.</p>
          </aside>
        </div>
      )}
    </div>
  )
}
