import { ArrowRightIcon, CheckIcon, FlagIcon, PencilIcon, PlusIcon, SearchIcon, Trash2Icon } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import type { RequirementStatement, Schemas } from '@/api/client'
import { errorMessage } from '@/api/errors'
import { useAddStatement, useConfirmExtraction, useDeleteStatement, useFlags, useFlagSummary, useStatements, useUpdateStatement } from '@/api/queries'
import { Badge, RefTag } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { FieldError, Input, Textarea } from '@/components/ui/input'
import { Notice } from '@/components/ui/notice'
import { PageLoading, Spinner } from '@/components/ui/spinner'
import { FLAG_LABEL, FLAG_TONE, FlagPill, FlagsDrawer, Highlighted } from '@/features/flags/flags'
import { useWorkspace } from '@/routes/workspace-layout'
import { cn, formatRelative, plural } from '@/lib/utils'

type Label = NonNullable<Schemas['StatementWrite']['label']>
const LABELS: { id: Label; short: string; long: string }[] = [
  { id: 'functional', short: 'FR', long: 'Functional' },
  { id: 'non_functional', short: 'NFR', long: 'Non-functional' },
  { id: 'user_story', short: 'Story', long: 'User story' },
]
const shortLabel = (l: string | null | undefined) => LABELS.find((x) => x.id === l)?.short ?? (l && l !== 'unknown' ? l : '')
const EMPTY = 'Requirement text can’t be empty.'

/** Step 2: review the requirements the AI found, fix them, then confirm. Nothing is drawn before this. */
export function ReviewPage() {
  const { project } = useWorkspace()
  const statements = useStatements(project.id)
  const summary = useFlagSummary(project.id)
  const flags = useFlags(project.id)
  const [onlyFlagged, setOnlyFlagged] = useState(false)
  const [query, setQuery] = useState('')
  const [editing, setEditing] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  const [drawer, setDrawer] = useState<{ open: boolean; focus?: string | null }>({ open: false })
  const highlight = useSearchParams()[0].get('requirement') // set by search: show this requirement
  const canEdit = project.role !== 'viewer'

  const summaryById = useMemo(() => new Map((summary.data ?? []).map((s) => [s.statement_id, s])), [summary.data])
  const openFlagByStatement = useMemo(() => {
    const m = new Map<string, NonNullable<typeof flags.data>[number]>()
    for (const f of flags.data ?? []) if (f.status === 'open' && !m.has(f.statement_id)) m.set(f.statement_id, f)
    return m
  }, [flags.data])

  if (statements.isPending) return <PageLoading label="Loading requirements" />
  if (project.statement_count === 0 && !statements.data?.length) {
    return (
      <div className="p-7">
        <Notice title="Nothing to review yet">
          Add requirement text first.{' '}
          <Link to="../input" className="font-medium underline">
            Go to Requirements
          </Link>
        </Notice>
      </div>
    )
  }

  const all = statements.data ?? []
  const flaggedCount = (summary.data ?? []).filter((s) => s.open > 0).length
  const q = query.trim().toLowerCase()
  const shown = all.filter((s) => (!onlyFlagged || (summaryById.get(s.id)?.open ?? 0) > 0) && (!q || `${s.ref} ${s.text}`.toLowerCase().includes(q)))

  return (
    <div className="mx-auto grid w-full max-w-[1400px] flex-1 gap-6 p-4 sm:p-7 lg:grid-cols-[minmax(0,1fr)_360px]">
      <section aria-label="Requirements" className="flex min-h-0 flex-col self-start overflow-hidden rounded-xl border border-rule bg-field">
        <div className="flex flex-wrap items-center gap-3 border-b border-rule px-4 py-3">
          <h2 className="font-sans text-[15px] font-semibold tracking-normal">
            Requirements <span className="font-normal text-slate">{all.length}</span>
          </h2>
          <div role="group" aria-label="Show" className="flex rounded-[9px] bg-rule p-[3px] text-[12.5px] font-medium">
            {[false, true].map((f) => (
              <button
                key={String(f)}
                type="button"
                aria-pressed={onlyFlagged === f}
                onClick={() => setOnlyFlagged(f)}
                className={cn('rounded-[7px] px-3 py-1 text-ink-2', onlyFlagged === f && 'bg-field text-ink shadow-sm')}
              >
                {f ? `Flagged ${flaggedCount}` : 'All'}
              </button>
            ))}
          </div>
          <label className="relative ml-auto w-full max-w-56">
            <span className="sr-only">Filter requirements</span>
            <SearchIcon className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-slate" />
            <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Filter" className="h-8 pl-8 text-[13px]" />
          </label>
          {canEdit && (
            <Button variant="secondary" size="sm" onClick={() => setAdding(true)}>
              <PlusIcon /> Add requirement
            </Button>
          )}
        </div>

        <ol>
          {shown.map((s) =>
            editing === s.id ? (
              <EditRow key={s.id} projectId={project.id} statement={s} onDone={() => setEditing(null)} />
            ) : (
              <Row
                key={s.id}
                projectId={project.id}
                statement={s}
                flag={openFlagByStatement.get(s.id)}
                summary={summaryById.get(s.id)}
                highlighted={s.ref === highlight}
                canEdit={canEdit}
                onEdit={() => setEditing(s.id)}
                onFlags={() => setDrawer({ open: true, focus: s.id })}
              />
            ),
          )}
          {shown.length === 0 && <li className="px-5 py-8 text-center text-[13px] text-slate">No requirements match.</li>}
        </ol>
        {adding && <AddRow projectId={project.id} nextRef={nextRef(all)} onDone={() => setAdding(false)} />}
      </section>

      <ConfirmPanel count={all.length} summary={summary.data ?? []} onFlags={() => setDrawer({ open: true })} />

      <FlagsDrawer projectId={project.id} open={drawer.open} onOpenChange={(open) => setDrawer((d) => ({ ...d, open }))} focusStatementId={drawer.focus} statements={all} />
    </div>
  )
}

const nextRef = (all: RequirementStatement[]) => `R-${String(Math.max(0, ...all.map((s) => Number(s.ref.slice(2)) || 0)) + 1).padStart(3, '0')}`

function Row({
  projectId,
  statement: s,
  flag,
  summary,
  highlighted,
  canEdit,
  onEdit,
  onFlags,
}: {
  projectId: string
  statement: RequirementStatement
  flag?: Schemas['Flag']
  summary?: Schemas['FlagSummary']
  highlighted?: boolean
  canEdit: boolean
  onEdit: () => void
  onFlags: () => void
}) {
  const remove = useDeleteStatement(projectId)
  const [confirming, setConfirming] = useState(false)
  return (
    <li
      ref={highlighted ? (el) => el?.scrollIntoView?.({ block: 'center' }) : undefined}
      aria-current={highlighted || undefined}
      className={cn(
        'group flex items-start gap-3 border-b border-rule px-4 py-2.5 last:border-b-0',
        highlighted && 'bg-accent-wash shadow-[inset_3px_0_0_var(--accent)]',
      )}
    >
      <RefTag className="mt-0.5 shrink-0">{s.ref}</RefTag>
      <span className="mt-0.5 w-10 shrink-0 font-mono text-[11px] text-slate">{shortLabel(s.label)}</span>
      <p className="min-w-0 flex-1 text-[13.5px] leading-[22px]">
        <Highlighted text={s.text} trigger={flag?.trigger_text} type={flag?.type} />
      </p>
      <FlagPill summary={summary} onClick={onFlags} />
      {canEdit &&
        (confirming ? (
          <span className="flex shrink-0 items-center gap-1">
            <Button size="sm" variant="danger" disabled={remove.isPending} onClick={() => remove.mutate(s.id)}>
              {remove.isPending && <Spinner className="text-on-ink" label="Deleting" />}
              Delete {s.ref}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setConfirming(false)}>
              Keep
            </Button>
          </span>
        ) : (
          <span className="flex shrink-0 gap-0.5 opacity-40 group-hover:opacity-100 focus-within:opacity-100">
            <Button variant="ghost" size="icon" className="size-7" aria-label={`Edit ${s.ref}`} onClick={onEdit}>
              <PencilIcon className="size-3.5" />
            </Button>
            <Button variant="ghost" size="icon" className="size-7" aria-label={`Delete ${s.ref}`} onClick={() => setConfirming(true)}>
              <Trash2Icon className="size-3.5" />
            </Button>
          </span>
        ))}
      {remove.isError && <FieldError>{errorMessage(remove.error)}</FieldError>}
    </li>
  )
}

function LabelPicker({ value, onChange }: { value: Label | null; onChange: (l: Label) => void }) {
  return (
    <div role="radiogroup" aria-label="Type" className="flex rounded-[8px] bg-rule p-0.5 text-[12px] font-medium">
      {LABELS.map((l) => (
        <button key={l.id} type="button" role="radio" aria-checked={value === l.id} onClick={() => onChange(l.id)} className={cn('rounded-[6px] px-2.5 py-1 text-ink-2', value === l.id && 'bg-field text-ink shadow-sm')}>
          {l.long}
        </button>
      ))}
    </div>
  )
}

function EditRow({ projectId, statement: s, onDone }: { projectId: string; statement: RequirementStatement; onDone: () => void }) {
  const [text, setText] = useState(s.text)
  const [label, setLabel] = useState<Label | null>(LABELS.some((l) => l.id === s.label) ? (s.label as Label) : null)
  const update = useUpdateStatement(projectId)
  const empty = !text.trim()
  const changed = text.trim() !== s.text || (label !== null && label !== s.label)
  return (
    <li className="border-b border-rule bg-accent-wash px-4 py-3.5 shadow-[inset_3px_0_0_var(--accent)]">
      <div className="flex flex-wrap items-center gap-3">
        <RefTag className="border-accent text-accent">{s.ref}</RefTag>
        <LabelPicker value={label} onChange={setLabel} />
      </div>
      <label htmlFor={`edit-${s.id}`} className="sr-only">
        Requirement text
      </label>
      <Textarea id={`edit-${s.id}`} autoFocus value={text} aria-invalid={empty} onChange={(e) => setText(e.target.value)} className="mt-2.5 min-h-16 text-[13.5px]" />
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <FieldError>{empty ? EMPTY : update.isError ? errorMessage(update.error) : null}</FieldError>
        <span className="text-[11.5px] text-slate">Editing a requirement asks you to confirm the list again.</span>
        <Button size="sm" variant="ghost" className="ml-auto" onClick={onDone}>
          Cancel
        </Button>
        <Button
          size="sm"
          disabled={empty || !changed || update.isPending}
          onClick={async () => {
            const ok = await update.mutateAsync({ id: s.id, text: text.trim(), ...(label ? { label } : {}) }).catch(() => null)
            if (ok) onDone()
          }}
        >
          {update.isPending && <Spinner className="text-on-ink" label="Saving" />}
          Save
        </Button>
      </div>
    </li>
  )
}

function AddRow({ projectId, nextRef: ref, onDone }: { projectId: string; nextRef: string; onDone: () => void }) {
  const [text, setText] = useState('')
  const [label, setLabel] = useState<Label>('functional')
  const add = useAddStatement(projectId)
  async function save() {
    if (!text.trim()) return
    const ok = await add.mutateAsync({ text: text.trim(), label }).catch(() => null)
    if (ok) {
      setText('')
      onDone()
    }
  }
  return (
    <div className="border-t border-rule bg-surface px-4 py-3.5">
      <div className="flex flex-wrap items-center gap-3">
        <RefTag>{ref}</RefTag>
        <span className="text-[11.5px] text-slate">new</span>
        <LabelPicker value={label} onChange={setLabel} />
      </div>
      <label htmlFor="new-requirement" className="sr-only">
        New requirement
      </label>
      <Input
        id="new-requirement"
        autoFocus
        value={text}
        placeholder="The librarian shall …"
        className="mt-2.5"
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') void save()
          if (e.key === 'Escape') onDone()
        }}
      />
      <div className="mt-2 flex items-center gap-2">
        <FieldError>{add.isError ? errorMessage(add.error) : null}</FieldError>
        <span className="text-[11.5px] text-slate">Enter to save · Esc to cancel</span>
        <Button size="sm" variant="ghost" className="ml-auto" onClick={onDone}>
          Cancel
        </Button>
        <Button size="sm" disabled={!text.trim() || add.isPending} onClick={save}>
          {add.isPending && <Spinner className="text-on-ink" label="Adding" />}
          Add
        </Button>
      </div>
    </div>
  )
}

/** The gate: diagrams are drawn only from confirmed requirements. Flags are advice and never block it. */
function ConfirmPanel({ count, summary, onFlags }: { count: number; summary: Schemas['FlagSummary'][]; onFlags: () => void }) {
  const { project } = useWorkspace()
  const confirm = useConfirmExtraction(project.id)
  const navigate = useNavigate()
  const open = summary.reduce((n, s) => n + s.open, 0)
  const byType = new Map<Schemas['FlagType'], number>()
  for (const s of summary) if (s.open) for (const t of s.types) byType.set(t, (byType.get(t) ?? 0) + 1)

  return (
    <aside className="space-y-4 self-start">
      <div className="ticks rounded-xl border border-rule bg-field p-5">
        {project.confirmed ? (
          <>
            <p className="flex items-center gap-2 text-[15px] font-semibold text-success">
              <CheckIcon className="size-4" /> {plural(count, 'requirement')} confirmed
            </p>
            <p className="mt-1 text-[13px] text-slate">
              {project.confirmed_at && `Confirmed ${formatRelative(project.confirmed_at)}. `}Editing a requirement asks you to confirm again.
            </p>
            <Button size="lg" className="mt-5 w-full" onClick={() => navigate('../generate')}>
              Choose diagrams <ArrowRightIcon />
            </Button>
          </>
        ) : (
          <>
            <p className="text-[15px] font-semibold">Ready to confirm?</p>
            <p className="mt-1 text-[13px] text-slate">Check the list reads right. You can still edit afterwards; that just asks you to confirm again.</p>
            <dl className="mt-4 space-y-1.5 text-[13px]">
              <div className="flex justify-between">
                <dt>Requirements</dt>
                <dd className="font-semibold">{count}</dd>
              </div>
              <div className="flex justify-between">
                <dt>Open flags</dt>
                <dd className={cn('font-semibold', open && 'text-amber')}>{open}</dd>
              </div>
            </dl>
            {byType.size > 0 && (
              <div className="mt-2.5 flex flex-wrap gap-1.5">
                {[...byType].map(([t, n]) => (
                  <Badge key={t} tone={FLAG_TONE[t]}>
                    {n} {FLAG_LABEL[t].toLowerCase()}
                  </Badge>
                ))}
              </div>
            )}
            {open > 0 && (
              <Button variant="link" size="sm" className="mt-3" onClick={onFlags}>
                <FlagIcon className="size-3.5" /> Go through flags
              </Button>
            )}
            {confirm.isError && <p role="alert" className="mt-3 text-[12.5px] text-danger">{errorMessage(confirm.error)}</p>}
            {project.role !== 'viewer' && (
              <Button size="lg" className="mt-5 w-full" disabled={confirm.isPending || count === 0} onClick={() => confirm.mutate()}>
                {confirm.isPending && <Spinner className="text-on-ink" label="Confirming" />}
                Confirm {plural(count, 'requirement')}
                <ArrowRightIcon />
              </Button>
            )}
            <p className="mt-2 text-center text-[11.5px] text-slate">Flags are advice. They never block you.</p>
          </>
        )}
      </div>
      <div className="rounded-xl border border-rule bg-surface p-5">
        <p className="font-mono text-[11px] tracking-[0.08em] text-slate uppercase">Next</p>
        <p className="mt-1.5 text-[13px]">Choose the diagrams you want. Only then does the AI extract actors, entities and the rest, and only what those diagrams need.</p>
      </div>
    </aside>
  )
}
