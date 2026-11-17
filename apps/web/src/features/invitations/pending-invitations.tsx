import { CopyIcon, MailIcon } from 'lucide-react'
import { useState } from 'react'
import { errorMessage } from '@/api/errors'
import { useInvitations, useRevokeInvitation } from '@/api/queries'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Notice } from '@/components/ui/notice'
import { Spinner } from '@/components/ui/spinner'
import { displayName, roleLabel } from '@/lib/people'
import { toast } from '@/lib/toast'
import { formatRelative } from '@/lib/utils'

/** Days left, as "Expires in 7 days" / "Expires today". */
function expiresIn(iso: string) {
  const days = Math.ceil((new Date(iso).getTime() - Date.now()) / 86_400_000)
  if (days <= 0) return 'Expires today'
  return `Expires in ${days} ${days === 1 ? 'day' : 'days'}`
}

export const inviteLink = (token: string) => `${window.location.origin}/invite?token=${encodeURIComponent(token)}`

/** FR24a: the "Pending invitations" card under Members. Owners can copy an invitation's link or revoke it. */
export function PendingInvitations({ projectId, canManage }: { projectId: string; canManage: boolean }) {
  const { data, isPending, isError, error } = useInvitations(projectId)
  const revoke = useRevokeInvitation(projectId)
  const [copied, setCopied] = useState<string | null>(null)

  if (isPending)
    return (
      <div className="rounded-lg border border-rule bg-surface p-4">
        <Spinner label="Loading invitations" />
      </div>
    )
  if (isError)
    return (
      <Notice tone="error" title="Couldn't load the invitations">
        {errorMessage(error)}
      </Notice>
    )
  if (!data.length) return null

  async function copy(token: string, id: string) {
    try {
      await navigator.clipboard.writeText(inviteLink(token))
      setCopied(id)
      setTimeout(() => setCopied((c) => (c === id ? null : c)), 2000)
    } catch {
      toast('Could not copy the link. Copy it from the address bar instead.', 'error')
    }
  }

  return (
    <section className="rounded-lg border border-rule bg-surface" aria-labelledby="pending-invitations">
      <h3 id="pending-invitations" className="border-b border-rule px-4 py-3 text-sm font-medium">
        Pending invitations {data.length}
      </h3>
      <ul className="divide-y divide-rule">
        {data.map((i) => (
          <li key={i.id} className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3">
            <MailIcon className="size-4 shrink-0 text-slate" aria-hidden />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm">{i.email}</p>
              <p className="mt-0.5 text-xs text-slate">
                Invited by {displayName(i.invited_by.email)} {formatRelative(i.created_at)}
              </p>
            </div>
            <Badge tone={i.role === 'owner' ? 'violet' : i.role === 'editor' ? 'teal' : 'neutral'}>{roleLabel[i.role]}</Badge>
            <Badge tone="amber">{expiresIn(i.expires_at)}</Badge>
            {canManage && i.token && (
              <Button variant="ghost" size="sm" onClick={() => copy(i.token!, i.id)}>
                <CopyIcon /> {copied === i.id ? 'Copied' : 'Copy link'}
              </Button>
            )}
            {canManage && (
              <Button
                variant="ghost"
                size="sm"
                className="text-danger hover:bg-danger-wash hover:text-danger"
                onClick={() => revoke.mutate(i.id)}
                disabled={revoke.isPending}
              >
                Revoke
              </Button>
            )}
          </li>
        ))}
      </ul>
      {revoke.isError && (
        <p role="alert" className="border-t border-rule px-4 py-2 text-sm text-danger">
          {errorMessage(revoke.error, "That invitation couldn't be revoked.")}
        </p>
      )}
    </section>
  )
}
