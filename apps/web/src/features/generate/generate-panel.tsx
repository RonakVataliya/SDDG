import { LockIcon } from 'lucide-react'
import { useState } from 'react'
import { Link, NavLink, useNavigate } from 'react-router'
import type { DiagramType, Project } from '@/api/client'
import { errorMessage } from '@/api/errors'
import { useDiagrams, useStartGeneration } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogTitle } from '@/components/ui/dialog'
import { Notice } from '@/components/ui/notice'
import { Spinner } from '@/components/ui/spinner'
import { cn, formatRelative } from '@/lib/utils'
import { DIAGRAM_TYPES, typeLabel } from './diagram-types'

/** Right-hand workspace panel: pick diagram types and start a run (FR9d), then find every version made so far. */
export function GeneratePanel({ project }: { project: Project }) {
  const navigate = useNavigate()
  const [selected, setSelected] = useState<DiagramType[]>(['use_case'])
  const [confirmOpen, setConfirmOpen] = useState(false)
  const start = useStartGeneration(project.id)
  const diagrams = useDiagrams(project.id)
  const locked = !project.confirmed

  const toggle = (t: DiagramType) => setSelected((s) => (s.includes(t) ? s.filter((x) => x !== t) : [...s, t]))

  return (
    <div className="flex h-full flex-col gap-4">
      <div>
        <h2 className="font-semibold tracking-tight">Generate diagrams</h2>
        <p className="mt-0.5 text-sm text-slate">Choose which diagrams to generate from your confirmed items.</p>
      </div>

      {locked && (
        <p className="flex items-start gap-2 rounded-md border border-dashed border-rule-strong px-3 py-2 text-sm text-slate">
          <LockIcon className="mt-1 size-3.5 shrink-0" aria-hidden />
          <span>
            Locked until you confirm the extracted items.{' '}
            {project.item_count > 0 && (
              <Link to="review" className="font-medium text-teal hover:underline">
                Review items
              </Link>
            )}
          </span>
        </p>
      )}

      <fieldset disabled={locked}>
        <legend className="sr-only">Diagram types</legend>
        <div className="grid grid-cols-2 gap-2">
          {DIAGRAM_TYPES.map((t) => {
            const checked = selected.includes(t.value)
            const disabled = locked || !t.available
            return (
              <label
                key={t.value}
                title={t.available ? t.shows : 'Not available yet'}
                className={cn(
                  'flex min-h-16 gap-2 rounded-lg border bg-surface p-2.5',
                  disabled ? 'cursor-not-allowed opacity-55' : 'cursor-pointer hover:border-rule-strong',
                  checked && !disabled ? 'border-teal ring-1 ring-teal' : 'border-rule',
                )}
              >
                <input
                  type="checkbox"
                  className="mt-0.5 size-4 shrink-0 accent-teal"
                  checked={checked && t.available}
                  disabled={disabled}
                  onChange={() => toggle(t.value)}
                />
                <span className="min-w-0">
                  <span className="block text-sm leading-5 font-medium">{t.label}</span>
                 <span className="block text-xs leading-4 text-slate">{t.available ? t.shows : 'Not available yet'}</span>
                </span>
              </label>
            )
          })}
        </div>
      </fieldset>

      {start.isError && (
        <Notice tone="error" title="Couldn't start generation">
          {errorMessage(start.error)}
        </Notice>
      )}

      <Button disabled={locked || selected.length === 0 || start.isPending} onClick={() => setConfirmOpen(true)}>
        Generate {selected.length === 1 ? typeLabel[selected[0]] + ' diagram' : `${selected.length} diagrams`}
      </Button>

      <div className="mt-2 min-h-0 flex-1 border-t border-rule pt-4">
        <h3 className="text-sm font-medium">Your diagrams</h3>
        {diagrams.data?.length ? (
          <ul className="mt-2 space-y-1">
            {diagrams.data.map((d) => (
              <li key={d.id}>
                <NavLink
                  to={`diagrams/${d.id}`}
                  className={({ isActive }) =>
                    cn('block rounded-md px-2.5 py-2 text-sm hover:bg-ink/4', isActive && 'bg-teal-wash text-teal-deep')
                  }
                >
                  <span className="block font-medium">{typeLabel[d.type]}</span>
                  <span className="block truncate text-xs text-slate">
                    {d.instruction ? `Edited: “${d.instruction}”` : 'Generated'} · {formatRelative(d.created_at)}
                  </span>
                </NavLink>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-sm text-slate">Diagrams you generate will appear here.</p>
        )}
      </div>

      {/* FR9d: the selection is confirmed explicitly and cannot change while the run is going. */}
      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent>
          <DialogTitle>Generate these diagrams?</DialogTitle>
          <DialogDescription>The selection is locked once generation starts. To change it, start a new run afterwards.</DialogDescription>
          <ul className="mt-4 space-y-1 text-sm">
            {selected.map((t) => (
              <li key={t} className="flex items-center gap-2">
                <LockIcon className="size-3.5 text-slate" aria-hidden /> {typeLabel[t]}
              </li>
            ))}
          </ul>
          <DialogFooter>
            <Button variant="secondary" onClick={() => setConfirmOpen(false)}>
              Back
            </Button>
            <Button
              disabled={start.isPending}
              onClick={async () => {
                const job = await start.mutateAsync(selected).catch(() => null)
                setConfirmOpen(false)
                if (job) navigate(`generate?job=${job.id}`)
              }}
            >
              {start.isPending && <Spinner className="text-white" label="Starting" />}
              Start generating
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
