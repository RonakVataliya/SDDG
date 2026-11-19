import { useState } from 'react'
import type { CaseKind, CasePriority, TestCase, TestRequirementSummary } from '@/api/client'
import { errorMessage } from '@/api/errors'
import { useCreateCase, useUpdateCase } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogTitle } from '@/components/ui/dialog'
import { fieldClass, Input, Label, Textarea } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import { KIND, PRIORITY } from './labels'

const lines = (s: string) =>
  s
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)

/** Add a case by hand (no `existing`) or edit one. Steps and preconditions are typed one per line. */
export function CaseDialog({
  projectId,
  open,
  onOpenChange,
  requirements,
  existing,
}: {
  projectId: string
  open: boolean
  onOpenChange: (open: boolean) => void
  requirements: TestRequirementSummary[]
  existing?: TestCase
}) {
  const create = useCreateCase(projectId)
  const update = useUpdateCase(projectId)
  const [statementId, setStatementId] = useState(existing?.statement_id ?? requirements[0]?.statement_id ?? '')
  const [title, setTitle] = useState(existing?.title ?? '')
  const [kind, setKind] = useState<CaseKind>(existing?.kind ?? 'positive')
  const [priority, setPriority] = useState<CasePriority>(existing?.priority ?? 'medium')
  const [pre, setPre] = useState(existing?.preconditions.join('\n') ?? '')
  const [steps, setSteps] = useState(existing?.steps.join('\n') ?? '')
  const [expected, setExpected] = useState(existing?.expected ?? '')
  const pending = create.isPending || update.isPending
  const error = create.error ?? update.error
  const valid = title.trim() && lines(steps).length && expected.trim() && statementId

  const save = () => {
    const body = { title: title.trim(), priority, preconditions: lines(pre), steps: lines(steps), expected: expected.trim() }
    const done = { onSuccess: () => onOpenChange(false) }
    if (existing) update.mutate({ caseId: existing.id, body }, done)
    else create.mutate({ ...body, statement_id: statementId, kind }, done)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogTitle>{existing ? `Edit ${existing.number}` : 'Add a test case'}</DialogTitle>
        <DialogDescription>
          {existing ? 'Changes are saved to this case only.' : 'A case you write is ready to run straight away.'}
        </DialogDescription>
        <form
          className="mt-4 space-y-3"
          onSubmit={(e) => {
            e.preventDefault()
            if (valid) save()
          }}
        >
          {!existing && (
            <div className="space-y-1">
              <Label htmlFor="case-req">Requirement</Label>
              <select id="case-req" className={cn(fieldClass, 'h-10')} value={statementId} onChange={(e) => setStatementId(e.target.value)}>
                {requirements.map((r) => (
                  <option key={r.statement_id} value={r.statement_id}>
                    {r.ref} · {r.text.slice(0, 70)}
                  </option>
                ))}
              </select>
            </div>
          )}
          <div className="space-y-1">
            <Label htmlFor="case-title">Title</Label>
            <Input id="case-title" value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            {!existing && (
              <div className="space-y-1">
                <Label htmlFor="case-kind">Kind</Label>
                <select id="case-kind" className={cn(fieldClass, 'h-10')} value={kind} onChange={(e) => setKind(e.target.value as CaseKind)}>
                  {Object.entries(KIND).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v.label}
                    </option>
                  ))}
                </select>
              </div>
            )}
            <div className="space-y-1">
              <Label htmlFor="case-priority">Priority</Label>
              <select
                id="case-priority"
                className={cn(fieldClass, 'h-10')}
                value={priority}
                onChange={(e) => setPriority(e.target.value as CasePriority)}
              >
                {Object.entries(PRIORITY).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="space-y-1">
            <Label htmlFor="case-pre">Preconditions, one per line</Label>
            <Textarea id="case-pre" className="min-h-16" value={pre} onChange={(e) => setPre(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="case-steps">Steps, one per line</Label>
            <Textarea id="case-steps" value={steps} onChange={(e) => setSteps(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="case-expected">Expected result</Label>
            <Textarea id="case-expected" className="min-h-16" value={expected} onChange={(e) => setExpected(e.target.value)} />
          </div>
          {error && <p className="text-sm text-danger">{errorMessage(error)}</p>}
          <DialogFooter>
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!valid || pending}>
              {existing ? 'Save case' : 'Add case'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
