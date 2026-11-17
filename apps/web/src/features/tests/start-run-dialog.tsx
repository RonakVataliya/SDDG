import { TriangleAlertIcon } from 'lucide-react'
import { useState } from 'react'
import type { RunMode, TestCase } from '@/api/client'
import { errorMessage } from '@/api/errors'
import { useRunSelection, useStartRun, useTestCases } from '@/api/queries'
import { RefTag } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogTitle } from '@/components/ui/dialog'
import { Input, Label } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { cn, plural } from '@/lib/utils'
import { RUN_MODE } from './labels'

const MODES: RunMode[] = ['all', 'failed', 'regression', 'minimal', 'pick']

/** Start a manual run: name it and choose which ready cases it includes. */
export function StartRunDialog({
  projectId,
  runCount,
  onOpenChange,
  onStarted,
}: {
  projectId: string
  runCount: number
  onOpenChange: (open: boolean) => void
  onStarted: (runId: string) => void
}) {
  const selection = useRunSelection(projectId)
  const cases = useTestCases(projectId)
  const start = useStartRun(projectId)
  const today = new Date().toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
  const [name, setName] = useState(`Run ${runCount + 1} · ${today}`)
  const [mode, setMode] = useState<RunMode>('all')
  const [picked, setPicked] = useState<Set<string>>(new Set())

  const ready = (cases.data ?? []).filter((c) => c.status === 'ready' && c.kept)
  const byId = new Map(ready.map((c) => [c.id, c]))
  const chosen = mode === 'pick' ? [...picked] : (selection.data?.[mode].case_ids ?? [])
  const countOf = (m: RunMode) => (m === 'pick' ? picked.size : (selection.data?.[m].case_ids.length ?? 0))

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogTitle>Start a test run</DialogTitle>
        <DialogDescription>Testing is manual: you follow each case's steps and mark the result.</DialogDescription>
        <form
          className="mt-4 space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            start.mutate(
              { name: name.trim(), mode, case_ids: mode === 'pick' ? [...picked] : undefined },
              { onSuccess: (run) => onStarted(run.id) },
            )
          }}
        >
          <div className="space-y-1">
            <Label htmlFor="run-name">Name</Label>
            <Input id="run-name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <fieldset className="space-y-1.5">
            <legend className="mb-1.5 text-sm font-medium">Which cases</legend>
            {selection.isPending ? (
              <Spinner label="Loading the selections" />
            ) : (
              MODES.map((m) => (
                <label
                  key={m}
                  className={cn(
                    'flex cursor-pointer items-start gap-3 rounded-md border px-3 py-2',
                    mode === m ? 'border-teal bg-teal-wash/50' : 'border-rule hover:border-rule-strong',
                  )}
                >
                  <input type="radio" name="mode" value={m} checked={mode === m} onChange={() => setMode(m)} className="mt-1 accent-teal" />
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-medium">{RUN_MODE[m].label}</span>
                    <span className="block text-xs text-slate">
                      {m === 'pick' ? RUN_MODE[m].hint : `${plural(countOf(m), 'case')} · ${RUN_MODE[m].hint.toLowerCase()}`}
                    </span>
                  </span>
                </label>
              ))
            )}
          </fieldset>

          {mode === 'pick' ? (
            <PickList cases={ready} picked={picked} onChange={setPicked} />
          ) : (
            selection.data && (
              <Preview
                ids={chosen}
                byId={byId}
                reasons={selection.data[mode].reasons}
                warning={selection.data[mode].warning}
                showReasons={mode === 'regression' || mode === 'failed'}
              />
            )
          )}

          {start.isError && <p className="text-sm text-danger">{errorMessage(start.error)}</p>}
          <DialogFooter>
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!name.trim() || !chosen.length || start.isPending}>
              Start run
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function Preview({
  ids,
  byId,
  reasons,
  warning,
  showReasons,
}: {
  ids: string[]
  byId: Map<string, TestCase>
  reasons: Record<string, string>
  warning: string | null
  showReasons: boolean
}) {
  return (
    <div className="space-y-2">
      {warning && (
        <p className="flex gap-2 rounded-md bg-amber-wash px-3 py-2 text-sm text-amber">
          <TriangleAlertIcon className="mt-0.5 size-4 shrink-0" /> {warning}
        </p>
      )}
      {showReasons && ids.length > 0 && (
        <div className="rounded-md border border-rule">
          <p className="border-b border-rule px-3 py-1.5 text-xs text-slate">{plural(ids.length, 'case')} selected, in priority order</p>
          <ul className="max-h-44 divide-y divide-rule overflow-y-auto text-sm">
            {ids.map((id) => (
              <li key={id} className="flex items-center gap-2 px-3 py-1.5">
                <RefTag>{byId.get(id)?.number}</RefTag>
                <span className="min-w-0 flex-1 truncate">{byId.get(id)?.title}</span>
                <span className="shrink-0 text-xs text-slate">{reasons[id]}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function PickList({ cases, picked, onChange }: { cases: TestCase[]; picked: Set<string>; onChange: (s: Set<string>) => void }) {
  if (!cases.length) return <p className="text-sm text-slate">No case is ready yet.</p>
  return (
    <ul className="max-h-52 divide-y divide-rule overflow-y-auto rounded-md border border-rule text-sm">
      {cases.map((c) => (
        <li key={c.id} className="flex items-center gap-2 px-3 py-1.5">
          <Checkbox
            checked={picked.has(c.id)}
            aria-label={`Pick ${c.number}`}
            onCheckedChange={(v) => {
              const next = new Set(picked)
              if (v === true) next.add(c.id)
              else next.delete(c.id)
              onChange(next)
            }}
          />
          <RefTag>{c.number}</RefTag>
          <span className="min-w-0 flex-1 truncate">{c.title}</span>
          <span className="font-mono text-xs text-slate">{c.statement_ref}</span>
        </li>
      ))}
    </ul>
  )
}
