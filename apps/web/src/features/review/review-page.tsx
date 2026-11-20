import { ArrowRightIcon, CheckIcon, FlagIcon, PencilIcon, PlusIcon, SearchIcon, Trash2Icon } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import type { RequirementStatement, Schemas, StatementConflict } from '@/api/client'
import { ApiError, errorMessage } from '@/api/errors'
import { useAddStatement, useConfirmExtraction, useDeleteStatement, useFlags, useFlagSummary, useStatements, useStories, useUpdateStatement } from '@/api/queries'
import { Badge, RefTag } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { FieldError, Input, Textarea } from '@/components/ui/input'
import { Notice } from '@/components/ui/notice'
import { PageLoading, Spinner } from '@/components/ui/spinner'
import { FLAG_LABEL, FLAG_TONE, FlagPill, FlagsDrawer, Highlighted } from '@/features/flags/flags'
import { toast } from '@/lib/toast'
import { ConflictDialog } from './conflict-dialog'
import { CommentsButton } from '@/features/comments/comments-panel'
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
  const [savedId, setSavedId] = useState<string | null>(null) // FR24f: the row just saved shows its new revision
  const [adding, setAdding] = useState(false)
  const [drawer, setDrawer] = useState<{ open: boolean; focus?: string | null }>({ open: false })
  const stories = useStories(project.id).data?.stories ?? [] // 3.4: each requirement links to its stories
  const highlight = useSearchParams()[0].get('requirement') // set by search: show this requirement
  const canEdit = project.role !== 'viewer'

  const summaryById = useMemo(() => new Map((summary.data ?? []).map((s) => [s.statement_id, s])), [summary.data])
  // The summary's `types` also lists resolved flags' types, so the pill and counts take them from open flags only.
  const openTypes = useMemo(() => {
    const m = new Map<string, Schemas['FlagType'][]>()
    for (const f of flags.data ?? []) {
      if (f.status !== 'open') continue
      const have = m.get(f.statement_id) ?? []
      if (!have.includes(f.type)) m.set(f.statement_id, [...have, f.type])
    }
    return m
  }, [flags.data])
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
              <EditRow
                key={s.id}
                projectId={project.id}
                statement={s}
                onDone={(saved) => {
                  setEditing(null)
                  setSavedId(saved ? s.id : null)
                }}
              />
            ) : (
              <Row
                key={s.id}
                projectId={project.id}
                statement={s}
                flag={openFlagByStatement.get(s.id)}
                summary={summaryById.get(s.id)}
                openTypes={openTypes.get(s.id)}
                storyRefs={stories.filter((st) => st.statement_ids.includes(s.id)).map((st) => st.ref)}
                highlighted={s.ref === highlight}
                saved={savedId === s.id}
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

      <ConfirmPanel count={all.length} summary={summary.data ?? []} openTypes={openTypes} onFlags={() => setDrawer({ open: true })} />

      <FlagsDrawer projectId={project.id} open={drawer.open} onOpenChange={(open) => setDrawer((d) => ({ ...d, open }))} focusStatementId={drawer.focus} statements={all} canEdit={canEdit} />
    </div>
  )
}

const nextRef = (all: RequirementStatement[]) => `R-${String(Math.max(0, ...all.map((s) => Number(s.ref.slice(2)) || 0)) + 1).padStart(3, '0')}`

function Row({
  projectId,
  statement: s,
  flag,
  summary,
  openTypes,
  storyRefs,
  highlighted,
  saved = false,
  canEdit,
  onEdit,
  onFlags,
}: {
  projectId: string
  statement: RequirementStatement
  flag?: Schemas['Flag']
  summary?: Schemas['FlagSummary']
  openTypes?: Schemas['FlagType'][]
  storyRefs: string[]
  highlighted?: boolean
  saved?: boolean
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
      {saved && (
        <span role="status" className="mt-0.5 shrink-0 text-[11.5px] text-success">
          rev {s.revision ?? 1} · Saved
        </span>
      )}
      {/* FR1/FR2: the requirement's own ID from the input (FR-001, NFR-2, …) */}
      {s.source_label && (
        <Badge tone="neutral" className="mt-0.5 h-fit shrink-0 font-mono text-[11px]">
          {s.source_label}
        </Badge>
      )}
      <div className="min-w-0 flex-1">
        <p className="text-[13.5px] leading-[22px]">
          <Highlighted text={s.text} trigger={flag?.trigger_text} type={flag?.type} />
        </p>
        {/* FR1: structured user story (As a <role>, I want <goal>, so that <reason>) */}
        {Boolean(s.metadata?.structured && s.metadata.role) && (
          <p className="mt-0.5 text-xs text-slate">
            Role: <strong className="font-medium text-ink">{String(s.metadata?.role)}</strong> · Goal:{' '}
            <span className="text-ink">{String(s.metadata?.goal)}</span>
            {s.metadata?.reason ? ` · Reason: ${String(s.metadata.reason)}` : ''}
          </p>
        )}
        {storyRefs.length > 0 && (
          <p className="mt-0.5 text-[12px] text-slate">
            Stories:{' '}
            {storyRefs.map((ref, i) => (
              <span key={ref}>
                {i > 0 && ', '}
                <Link to={`/projects/${projectId}/backlog?requirement=${s.id}`} className="font-medium text-accent hover:underline">
                  {ref}
                </Link>
              </span>
            ))}
          </p>
        )}
      </div>
      <CommentsButton projectId={projectId} target={{ type: 'statement', id: s.id, label: s.ref, text: s.text }} />
      <FlagPill summary={summary} openTypes={openTypes} onClick={onFlags} />
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

function EditRow({ projectId, statement: s, onDone }: { projectId: string; statement: RequirementStatement; onDone: (saved: boolean) => void }) {
  const [text, setText] = useState(s.text)
  const [label, setLabel] = useState<Label | null>(LABELS.some((l) => l.id === s.label) ? (s.label as Label) : null)
  const update = useUpdateStatement(projectId)
  const empty = !text.trim()
  const changed = text.trim() !== s.text || (label !== null && label !== s.label)
  // FR24f: the revision and text this edit started from. The save sends the revision; if someone saved since, the API
  // refuses it (409) and the dialog shows their version next to this change.
  const [opened] = useState({ revision: s.revision ?? 1, text: s.text })
  const [conflict, setConflict] = useState<StatementConflict | null>(null)
  const conflicted = update.error instanceof ApiError && update.error.code === 'edit_conflict'

  async function save(body: { text: string; base_revision: number; resolves_conflict?: boolean }) {
    try {
      const saved = (await update.mutateAsync({ id: s.id, ...body, ...(label ? { label } : {}) })) as RequirementStatement
      setConflict(null)
      if (body.resolves_conflict) toast(`Saved ${s.ref} as revision ${saved.revision}`)
      onDone(true)
    } catch (e) {
      if (e instanceof ApiError && e.code === 'edit_conflict') setConflict(e.body as StatementConflict)
    }
  }

  return (
    <li className="border-b border-rule bg-accent-wash px-4 py-3.5 shadow-[inset_3px_0_0_var(--accent)]">
      <div className="flex flex-wrap items-center gap-3">
        <RefTag className="border-accent text-accent">{s.ref}</RefTag>
        <LabelPicker value={label} onChange={setLabel} />
        <span className="ml-auto text-[11.5px] text-slate">based on rev {opened.revision}</span>
      </div>
      <label htmlFor={`edit-${s.id}`} className="sr-only">
        Requirement text
      </label>
      <Textarea id={`edit-${s.id}`} autoFocus value={text} aria-invalid={empty} onChange={(e) => setText(e.target.value)} className="mt-2.5 min-h-16 text-[13.5px]" />
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <FieldError>{empty ? EMPTY : update.isError && !conflicted ? errorMessage(update.error) : null}</FieldError>
        <span className="text-[11.5px] text-slate">Editing a requirement asks you to confirm the list again.</span>
        <Button size="sm" variant="ghost" className="ml-auto" onClick={() => onDone(false)}>
          Cancel
        </Button>
        <Button
          size="sm"
          disabled={empty || !changed || update.isPending}
          onClick={() => void save({ text: text.trim(), base_revision: opened.revision })}
        >
          {update.isPending && <Spinner className="text-on-ink" label="Saving" />}
          Save
        </Button>
      </div>
      {conflict && (
        <ConflictDialog
          conflict={conflict}
          base={opened.text}
          mine={text.trim()}
          saving={update.isPending}
          onCancel={() => setConflict(null)}
          onUseTheirs={() => {
            setConflict(null)
            onDone(false) // the list was refetched after the conflict and shows their version
          }}
          onSave={(merged) =>
            void save({ text: merged, base_revision: conflict.current.revision ?? conflict.base_revision + 1, resolves_conflict: true })
          }
        />
      )}
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
function ConfirmPanel({ count, summary, openTypes, onFlags }: { count: number; summary: Schemas['FlagSummary'][]; openTypes: Map<string, Schemas['FlagType'][]>; onFlags: () => void }) {
  const { project } = useWorkspace()
  const confirm = useConfirmExtraction(project.id)
  const navigate = useNavigate()
  const open = summary.reduce((n, s) => n + s.open, 0)
  const byType = new Map<Schemas['FlagType'], number>()
  for (const types of openTypes.values()) for (const t of types) byType.set(t, (byType.get(t) ?? 0) + 1)

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
