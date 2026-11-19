import { ArrowDownIcon, ArrowUpIcon, PlusIcon, XIcon } from 'lucide-react'
import { useState } from 'react'
import type { DesignGoals, DesignGoalsDerived } from '@/api/client'
import { RefTag } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { fieldClass, Label, Textarea } from '@/components/ui/input'
import { Notice } from '@/components/ui/notice'
import { cn } from '@/lib/utils'
import type { EditorProps } from './design-page'
import { GOAL_NAMES } from './goals'

type Goal = DesignGoals['goals'][number]
const GROUPS = [
  ['client', 'Client'],
  ['end_user', 'End user'],
  ['developer', 'Developer/maintainer'],
  ['other', 'Other'],
] as const

/** 4.1 Design goals: a ranked list (first = most important), each with a reason and the requirements behind it. */
export function GoalsEditor({ content, derived, dirty, disabled, requirements, onChange }: EditorProps) {
  const goals = (content as DesignGoals).goals
  const summary = derived as DesignGoalsDerived | null
  const [adding, setAdding] = useState('')
  const [open, setOpen] = useState<string | null>(null)
  const refOf = new Map(requirements.map((r) => [r.id, r.ref]))
  const remaining = GOAL_NAMES.filter((n) => !goals.some((g) => g.name === n))

  const update = (next: Goal[]) => onChange({ goals: next })
  const change = (i: number, patch: Partial<Goal>) => update(goals.map((g, j) => (j === i ? { ...g, ...patch } : g)))
  const move = (i: number, by: number) => {
    const next = [...goals]
    ;[next[i], next[i + by]] = [next[i + by], next[i]]
    update(next)
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_18rem]">
      <div className="space-y-3">
        {goals.length === 0 ? (
          <p className="rounded-lg border border-dashed border-rule-strong p-6 text-center text-sm text-slate">
            No design goals yet. Draft them with AI or add them from the list below.
          </p>
        ) : (
          <ol aria-label="Ranked design goals" className="space-y-3">
            {goals.map((g, i) => (
              <li key={g.name} data-goal={g.name} className="rounded-xl border border-rule bg-field p-3">
                <div className="flex items-center gap-2">
                  <span className="grid size-6 shrink-0 place-items-center rounded-full bg-accent-wash text-xs font-semibold text-accent-deep tabular-nums">
                    {i + 1}
                  </span>
                  <h4 className="min-w-0 flex-1 font-medium">{g.name}</h4>
                  <Button variant="ghost" size="icon" aria-label={`Move ${g.name} up`} disabled={disabled || i === 0} onClick={() => move(i, -1)}>
                    <ArrowUpIcon />
                  </Button>
                  <Button variant="ghost" size="icon" aria-label={`Move ${g.name} down`} disabled={disabled || i === goals.length - 1} onClick={() => move(i, 1)}>
                    <ArrowDownIcon />
                  </Button>
                  <Button variant="ghost" size="icon" aria-label={`Remove ${g.name}`} disabled={disabled} onClick={() => update(goals.filter((_, j) => j !== i))}>
                    <XIcon />
                  </Button>
                </div>
                <div className="mt-2 space-y-1">
                  <Label htmlFor={`goal-reason-${i}`}>Reason for {g.name}</Label>
                  <Textarea
                    id={`goal-reason-${i}`}
                    className="min-h-14"
                    maxLength={300}
                    value={g.reason}
                    disabled={disabled}
                    onChange={(e) => change(i, { reason: e.target.value })}
                  />
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                  {g.statement_ids.map((id) => (
                    <RefTag key={id}>{refOf.get(id) ?? 'Deleted requirement'}</RefTag>
                  ))}
                  {!g.statement_ids.length && <span className="text-xs text-amber">Cites no requirement yet</span>}
                  <Button
                    variant="link"
                    size="sm"
                    className="ml-1"
                    aria-expanded={open === g.name}
                    disabled={disabled}
                    onClick={() => setOpen(open === g.name ? null : g.name)}
                  >
                    Requirements for {g.name}
                  </Button>
                </div>
                {open === g.name && (
                  // Scrolls on its own so a project with many requirements stays usable.
                  <fieldset className="mt-2 max-h-48 space-y-1.5 overflow-y-auto rounded-md border border-rule p-2">
                    <legend className="sr-only">Requirements {g.name} cites</legend>
                    {requirements.map((r) => (
                      <label key={r.id} className="flex items-start gap-2 text-sm">
                        <Checkbox
                          className="mt-0.5"
                          aria-label={`${g.name} cites ${r.ref}`}
                          checked={g.statement_ids.includes(r.id)}
                          onCheckedChange={(on) =>
                            change(i, { statement_ids: on ? [...g.statement_ids, r.id] : g.statement_ids.filter((id) => id !== r.id) })
                          }
                        />
                        <span>
                          <span className="font-mono text-[12px]">{r.ref}</span> {r.text}
                        </span>
                      </label>
                    ))}
                  </fieldset>
                )}
              </li>
            ))}
          </ol>
        )}
        {!disabled && remaining.length > 0 && (
          <div className="flex items-end gap-2">
            <div className="flex-1 space-y-1">
              <Label htmlFor="add-goal">Add a goal</Label>
              <select id="add-goal" className={cn(fieldClass, 'h-9')} value={adding} onChange={(e) => setAdding(e.target.value)}>
                <option value="">Choose a design goal</option>
                {remaining.map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </div>
            <Button
              variant="secondary"
              disabled={!adding}
              onClick={() => {
                update([...goals, { name: adding, reason: '', statement_ids: [] }])
                setAdding('')
              }}
            >
              <PlusIcon /> Add
            </Button>
          </div>
        )}
      </div>

      {summary && (
        <aside className="space-y-4">
          <section aria-label="By stakeholder" className="rounded-xl border border-rule bg-field p-3">
            <h4 className="text-sm font-semibold">By stakeholder</h4>
            {dirty && <p className="mt-1 text-xs text-slate">These summaries reflect the last saved version. Save to update them.</p>}
            {GROUPS.map(([key, label]) => (
              <div key={key} className="mt-3">
                <h5 className="text-xs font-medium text-slate">{label}</h5>
                <ul aria-label={label} className="mt-1 text-sm">
                  {summary.groups[key].length ? summary.groups[key].map((n) => <li key={n}>{n}</li>) : <li className="text-slate">None</li>}
                </ul>
              </div>
            ))}
          </section>
          {summary.conflicts.length > 0 && (
            <section aria-label="Trade-offs to watch">
              <Notice tone="warning" title="Trade-offs to watch">
                <ul className="space-y-1">
                  {summary.conflicts.map((c) => (
                    <li key={`${c.a}|${c.b}`}>
                      {c.a} and {c.b}: {c.pair}
                    </li>
                  ))}
                </ul>
              </Notice>
            </section>
          )}
        </aside>
      )}
    </div>
  )
}
