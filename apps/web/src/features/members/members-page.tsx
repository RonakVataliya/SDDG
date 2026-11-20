/** Members page (FR24c): who is in the project, what each role can do, and, for an Owner, changing roles and
 * removing people. Anyone can leave. The server enforces every rule here; the UI only hides what would be refused. */
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { LogOutIcon, UserMinusIcon } from 'lucide-react'
import type { Member, Role } from '@/api/client'
import { errorMessage } from '@/api/errors'
import { useChangeMemberRole, useMembers, useRemoveMember } from '@/api/queries'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogTitle } from '@/components/ui/dialog'
import { fieldClass } from '@/components/ui/input'
import { Notice } from '@/components/ui/notice'
import { PageLoading, Spinner } from '@/components/ui/spinner'
import { StepHeading } from '@/features/input/input-page'
import { cn, formatDate, plural } from '@/lib/utils'
import { useWorkspace } from '@/routes/workspace-layout'
import { RoleMatrix } from './role-matrix'

export const ROLES: Role[] = ['viewer', 'editor', 'owner']
export const roleLabel = (r: Role) => r[0].toUpperCase() + r.slice(1)

export function MembersPage() {
  const { project } = useWorkspace()
  const { data: members, isPending, error } = useMembers(project.id)
  const isOwner = project.role === 'owner'

  return (
    <div className="space-y-6">
      <StepHeading
        title="Members"
        description={members ? `${plural(members.length, 'person', 'people')} in this project.` : undefined}
      />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0">
          {isPending ? (
            <PageLoading label="Loading members" />
          ) : error ? (
            <Notice tone="error" title="Couldn't load the members">
              {errorMessage(error)}
            </Notice>
          ) : (
            <MembersTable members={members} isOwner={isOwner} />
          )}
        </div>
        <RoleMatrix />
      </div>
    </div>
  )
}

function MembersTable({ members, isOwner }: { members: Member[]; isOwner: boolean }) {
  const { project } = useWorkspace()
  const changeRole = useChangeMemberRole(project.id)
  const [removing, setRemoving] = useState<Member | null>(null)
  const problem = changeRole.error

  return (
    <div className="space-y-3">
      {problem && (
        <Notice tone="error" title="Role not changed">
          {errorMessage(problem)}
        </Notice>
      )}
      <table className="w-full text-left text-[13.5px]">
        <thead className="border-b border-rule text-[12px] text-slate">
          <tr>
            <th className="py-2 font-medium">Person</th>
            <th className="py-2 font-medium">Role</th>
            <th className="hidden py-2 font-medium sm:table-cell">Joined</th>
            <th className="w-10 py-2">
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {members.map((m) => (
            <tr key={m.user_id} className="border-b border-rule last:border-0">
              <td className="py-2.5 pr-3">
                <span className="font-medium">{m.email ?? m.user_id}</span>
                {m.is_you && <span className="text-slate"> (you)</span>}
              </td>
              <td className="py-2.5 pr-3">
                {isOwner ? (
                  <select
                    aria-label={`Role for ${m.email ?? m.user_id}`}
                    className={cn(fieldClass, 'h-8 w-28')}
                    value={m.role}
                    disabled={changeRole.isPending}
                    onChange={(e) => changeRole.mutate({ userId: m.user_id, role: e.target.value as Role })}
                  >
                    {ROLES.map((r) => (
                      <option key={r} value={r}>
                        {roleLabel(r)}
                      </option>
                    ))}
                  </select>
                ) : (
                  <Badge tone={m.role === 'owner' ? 'accent' : 'neutral'}>{roleLabel(m.role)}</Badge>
                )}
              </td>
              <td className="hidden py-2.5 pr-3 text-slate sm:table-cell">
                {m.is_creator ? 'Created the project' : m.joined_at ? formatDate(m.joined_at) : '—'}
              </td>
              <td className="py-2.5 text-right">
                {(m.is_you || isOwner) && (
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={m.is_you ? 'Leave project' : `Remove ${m.email ?? m.user_id}`}
                    title={m.is_you ? 'Leave project' : 'Remove from project'}
                    onClick={() => setRemoving(m)}
                  >
                    {m.is_you ? <LogOutIcon /> : <UserMinusIcon />}
                  </Button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {removing && <RemoveDialog member={removing} onClose={() => setRemoving(null)} />}
    </div>
  )
}

function RemoveDialog({ member, onClose }: { member: Member; onClose: () => void }) {
  const { project } = useWorkspace()
  const remove = useRemoveMember(project.id)
  const navigate = useNavigate()
  const leaving = member.is_you
  const who = member.email ?? member.user_id

  function confirm() {
    remove.mutate(
      { userId: member.user_id, leaving },
      {
        onSuccess: () => {
          onClose()
          if (leaving) void navigate('/projects')
        },
      },
    )
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogTitle>{leaving ? `Leave ${project.name}?` : `Remove ${who}?`}</DialogTitle>
        <DialogDescription>
          {leaving
            ? 'You lose access straight away. An Owner can add you back later.'
            : 'They lose access on their next request. Their past work in the project stays.'}
        </DialogDescription>
        {remove.error && (
          <Notice tone="error" title={leaving ? "Couldn't leave" : "Couldn't remove"}>
            {errorMessage(remove.error)}
          </Notice>
        )}
        <DialogFooter>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="danger" onClick={confirm} disabled={remove.isPending}>
            {remove.isPending && <Spinner />}
            {leaving ? 'Leave project' : 'Remove'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
