import { useState, type FormEvent, type ReactNode } from 'react'
import type { Role } from '@/api/client'
import { errorMessage } from '@/api/errors'
import { useInvite } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { FieldError, Input, Label } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { roleLabel } from '@/lib/people'
import { toast } from '@/lib/toast'
import { cn } from '@/lib/utils'

const ROLES: Role[] = ['viewer', 'editor', 'owner']
const WHAT_EACH_ROLE_DOES: Record<Role, string> = {
  viewer: 'Can read, comment and export.',
  editor: 'Can also edit requirements and diagrams, and run generations.',
  owner: 'Can also invite people, change roles and delete the project.',
}

/** FR24a: invite someone to this project by email. Opened by the Invite button on the Members page. */
export function InviteDialog({ projectId, projectName, trigger }: { projectId: string; projectName: string; trigger: ReactNode }) {
  const [open, setOpen] = useState(false)
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<Role>('viewer')
  const invite = useInvite(projectId)

  function close(next: boolean) {
    setOpen(next)
    if (!next) {
      setEmail('')
      setRole('viewer')
      invite.reset()
    }
  }

  async function send(e: FormEvent) {
    e.preventDefault()
    const address = email.trim()
    if (!address || invite.isPending) return
    const sent = await invite.mutateAsync({ email: address, role }).catch(() => null)
    if (!sent) return
    toast(`Invitation sent to ${sent.email}.`)
    close(false)
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogTitle>Invite to {projectName}</DialogTitle>
        <DialogDescription>They'll see the invitation in SDDG after they log in. It expires in 7 days.</DialogDescription>
        <form onSubmit={send} className="mt-5 space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="invite-email">Email address</Label>
            <Input
              id="invite-email"
              type="email"
              autoComplete="off"
              value={email}
              onChange={(e) => {
                setEmail(e.target.value)
                if (invite.isError) invite.reset()
              }}
              aria-invalid={invite.isError || undefined}
              aria-describedby={invite.isError ? 'invite-error' : undefined}
              placeholder="name@example.com"
            />
            {invite.isError && <FieldError id="invite-error">{errorMessage(invite.error)}</FieldError>}
          </div>

          <fieldset className="space-y-1.5">
            <legend className="text-sm font-medium text-ink">Role</legend>
            <div role="radiogroup" aria-label="Role" className="flex rounded-md border border-rule-strong p-0.5">
              {ROLES.map((r) => (
                <button
                  key={r}
                  type="button"
                  role="radio"
                  aria-checked={role === r}
                  onClick={() => setRole(r)}
                  className={cn(
                    'flex-1 rounded-[5px] px-3 py-1.5 text-sm font-medium',
                    role === r ? 'bg-teal text-white' : 'text-slate hover:bg-ink/5 hover:text-ink',
                  )}
                >
                  {roleLabel[r]}
                </button>
              ))}
            </div>
            <p className="text-xs text-slate">{WHAT_EACH_ROLE_DOES[role]}</p>
          </fieldset>

          <DialogFooter>
            <Button type="button" variant="secondary" onClick={() => close(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!email.trim() || invite.isPending}>
              {invite.isPending ? <Spinner className="text-white" label="" /> : null} Send invite
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
