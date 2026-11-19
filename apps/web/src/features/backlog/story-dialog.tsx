import { useState } from 'react'
import type { RequirementStatement, Story, StoryPriority, StoryStatus } from '@/api/client'
import { errorMessage } from '@/api/errors'
import { useCreateStory, useUpdateStory } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogTitle } from '@/components/ui/dialog'
import { fieldClass, Input, Label, Textarea } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import { PRIORITY, STATUS } from './labels'

const lines = (s: string) =>
  s
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)

/** Write a story (no `existing`) or edit one. Confirmations are typed one per line. */
export function StoryDialog({
  projectId,
  onOpenChange,
  requirements,
  members,
  existing,
}: {
  projectId: string
  onOpenChange: (open: boolean) => void
  requirements: RequirementStatement[]
  members: { id: string; email: string }[]
  existing?: Story
}) {
  const create = useCreateStory(projectId)
  const update = useUpdateStory(projectId)
  const [role, setRole] = useState(existing?.role ?? '')
  const [goal, setGoal] = useState(existing?.goal ?? '')
  const [reason, setReason] = useState(existing?.reason ?? '')
  const [priority, setPriority] = useState<StoryPriority>(existing?.priority ?? 'should')
  const [estimate, setEstimate] = useState(existing?.estimate?.toString() ?? '')
  const [status, setStatus] = useState<StoryStatus>(existing?.status ?? 'todo')
  const [assignee, setAssignee] = useState(existing?.assignee_id ?? '')
  const [confirmations, setConfirmations] = useState(existing?.confirmations.join('\n') ?? '')
  const [statementIds, setStatementIds] = useState<string[]>(existing?.statement_ids ?? [])
  const pending = create.isPending || update.isPending
  const error = create.error ?? update.error
  const valid = role.trim() && goal.trim() && reason.trim() && statementIds.length > 0

  const save = () => {
    const body = {
      role: role.trim(),
      goal: goal.trim(),
      reason: reason.trim(),
      priority,
      estimate: estimate === '' ? null : Number(estimate),
      status,
      assignee_id: assignee || null,
      confirmations: lines(confirmations),
      statement_ids: statementIds,
    }
    const done = { onSuccess: () => onOpenChange(false) }
    if (existing) update.mutate({ storyId: existing.id, body }, done)
    else create.mutate(body, done)
  }

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogTitle>{existing ? `Edit ${existing.ref}` : 'New story'}</DialogTitle>
        <DialogDescription>As a [user role] I want to [goal] so I can [reason].</DialogDescription>
        <form
          className="mt-4 space-y-3"
          onSubmit={(e) => {
            e.preventDefault()
            if (valid) save()
          }}
        >
          <div className="space-y-1">
            <Label htmlFor="story-role">User role</Label>
            <Input id="story-role" value={role} placeholder="librarian" onChange={(e) => setRole(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="story-goal">Goal</Label>
            <Input id="story-goal" value={goal} placeholder="issue a book to a member" onChange={(e) => setGoal(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="story-reason">Reason</Label>
            <Input id="story-reason" value={reason} placeholder="the member can take it home" onChange={(e) => setReason(e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label htmlFor="story-priority">Priority</Label>
              <select id="story-priority" className={cn(fieldClass, 'h-10')} value={priority} onChange={(e) => setPriority(e.target.value as StoryPriority)}>
                {Object.entries(PRIORITY).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="story-estimate">Estimate (story points)</Label>
              <Input id="story-estimate" type="number" min={0} max={100} value={estimate} onChange={(e) => setEstimate(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="story-status">Status</Label>
              <select id="story-status" className={cn(fieldClass, 'h-10')} value={status} onChange={(e) => setStatus(e.target.value as StoryStatus)}>
                {Object.entries(STATUS).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="story-assignee">Assignee</Label>
              <select id="story-assignee" className={cn(fieldClass, 'h-10')} value={assignee} onChange={(e) => setAssignee(e.target.value)}>
                <option value="">Unassigned</option>
                {members.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.email}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="space-y-1">
            <Label htmlFor="story-confirmations">Confirmations (acceptance criteria), one per line</Label>
            <Textarea id="story-confirmations" className="min-h-16" value={confirmations} onChange={(e) => setConfirmations(e.target.value)} />
          </div>
          <fieldset className="space-y-1.5">
            <legend className="text-sm font-medium text-ink">Requirements (at least one)</legend>
            <div className="max-h-40 space-y-1.5 overflow-y-auto">
              {requirements.map((r) => (
                <label key={r.id} className="flex items-start gap-2 text-sm">
                  <Checkbox
                    className="mt-0.5"
                    checked={statementIds.includes(r.id)}
                    onCheckedChange={(on) => setStatementIds(on ? [...statementIds, r.id] : statementIds.filter((id) => id !== r.id))}
                  />
                  <span>
                    <span className="font-mono text-[12px]">{r.ref}</span> {r.text}
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
          {error && <p className="text-sm text-danger">{errorMessage(error)}</p>}
          <DialogFooter>
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!valid || pending}>
              {existing ? 'Save story' : 'Add story'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
