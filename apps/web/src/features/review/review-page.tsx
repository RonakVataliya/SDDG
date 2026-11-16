import { PencilIcon, PlusIcon, Trash2Icon } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import type { RequirementStatement, Schemas } from '@/api/client'
import { errorMessage } from '@/api/errors'
import { useAddStatement, useConfirmExtraction, useDeleteStatement, useStatements, useUpdateStatement } from '@/api/queries'
import { RefTag } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { FieldError, Input, Textarea } from '@/components/ui/input'
import { Notice } from '@/components/ui/notice'
import { PageLoading, Spinner } from '@/components/ui/spinner'
import { StepHeading } from '@/features/input/input-page'
import { useWorkspace } from '@/routes/workspace-layout'
import { cn, formatRelative, plural } from '@/lib/utils'

type Label = NonNullable<Schemas['StatementWrite']['label']>
const LABELS: { id: Label; long: string }[] = [
  { id: 'functional', long: 'Functional' },
  { id: 'non_functional', long: 'Non-functional' },
  { id: 'user_story', long: 'User story' },
]
const EMPTY = 'Requirement text can’t be empty.'

/** Step 2 (requirements-first): review the requirements the AI found, fix them, then confirm. Nothing is drawn before this. */
export function ReviewPage() {
  const { project } = useWorkspace()
  const statements = useStatements(project.id)
  const [editing, setEditing] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  const highlight = useSearchParams()[0].get('requirement') // set by search: show this requirement
  const canEdit = project.role !== 'viewer'

  if (statements.isPending) return <PageLoading label="Loading requirements" />
  if (project.statement_count === 0 && !statements.data?.length) {
    return (
      <div className="space-y-4">
        <StepHeading title="Review requirements" />
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

  return (
    <div className="flex flex-1 flex-col space-y-5">
      <StepHeading
        title="Review requirements"
        description="Check the list reads right: edit, add or delete anything, then confirm. Actors, entities and the rest are extracted later, only for the diagrams you pick."
        actions={
          canEdit && (
            <Button variant="secondary" size="sm" onClick={() => setAdding(true)}>
              <PlusIcon /> Add requirement
            </Button>
          )
        }
      />

      {statements.isError && (
        <Notice tone="error" title="Couldn't load the requirements">
          {errorMessage(statements.error)}
        </Notice>
      )}

      <ol aria-label="Requirements" className="divide-y divide-rule rounded-lg border border-rule bg-surface">
        {all.map((s) =>
          editing === s.id ? (
            <EditRow key={s.id} projectId={project.id} statement={s} onDone={() => setEditing(null)} />
          ) : (
            <Row key={s.id} projectId={project.id} statement={s} canEdit={canEdit} highlighted={s.ref === highlight} onEdit={() => setEditing(s.id)} />
          ),
        )}
        {adding && <AddRow projectId={project.id} nextRef={nextRef(all)} onDone={() => setAdding(false)} />}
      </ol>

      <ConfirmBar count={all.length} />
    </div>
  )
}

const nextRef = (all: RequirementStatement[]) => `R-${String(Math.max(0, ...all.map((s) => Number(s.ref.slice(2)) || 0)) + 1).padStart(3, '0')}`

function Row({
  projectId,
  statement: s,
  canEdit,
  highlighted,
  onEdit,
}: {
  projectId: string
  statement: RequirementStatement
  canEdit: boolean
  highlighted?: boolean
  onEdit: () => void
}) {
  const remove = useDeleteStatement(projectId)
  const [confirming, setConfirming] = useState(false)
  return (
    <li
      ref={highlighted ? (el) => el?.scrollIntoView?.({ block: 'center' }) : undefined}
      aria-current={highlighted || undefined}
      className={cn('group flex flex-wrap items-start gap-3 px-4 py-2.5 text-sm', highlighted && 'bg-teal-wash')}
    >
      <RefTag className="h-fit shrink-0">{s.ref}</RefTag>
      <p className="min-w-0 flex-1">
        {s.label && s.label !== 'unknown' && <span className="mr-1.5 text-slate">{s.label}</span>}
        {s.text}
      </p>
      {canEdit &&
        (confirming ? (
          <span className="flex shrink-0 items-center gap-1">
            <Button size="sm" variant="danger" disabled={remove.isPending} onClick={() => remove.mutate(s.id)}>
              {remove.isPending && <Spinner className="text-white" label="Deleting" />}
              Delete {s.ref}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setConfirming(false)}>
              Keep
            </Button>
          </span>
        ) : (
          <span className="flex shrink-0 gap-0.5">
            <Button variant="ghost" size="icon" className="size-8" aria-label={`Edit ${s.ref}`} onClick={onEdit}>
              <PencilIcon />
            </Button>
            <Button variant="ghost" size="icon" className="size-8" aria-label={`Delete ${s.ref}`} onClick={() => setConfirming(true)}>
              <Trash2Icon />
            </Button>
          </span>
        ))}
      {remove.isError && (
        <div className="basis-full">
          <FieldError>{errorMessage(remove.error)}</FieldError>
        </div>
      )}
    </li>
  )
}

function LabelPicker({ value, onChange }: { value: Label | null; onChange: (l: Label) => void }) {
  return (
    <div role="radiogroup" aria-label="Type" className="flex gap-1">
      {LABELS.map((l) => (
        <button
          key={l.id}
          type="button"
          role="radio"
          aria-checked={value === l.id}
          onClick={() => onChange(l.id)}
          className={cn(
            'rounded-md border px-2.5 py-1 text-xs',
            value === l.id ? 'border-ink bg-ink text-white' : 'border-rule bg-surface text-ink hover:border-rule-strong',
          )}
        >
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
    <li className="space-y-2.5 bg-teal-wash/50 px-4 py-3.5">
      <div className="flex flex-wrap items-center gap-3">
        <RefTag>{s.ref}</RefTag>
        <LabelPicker value={label} onChange={setLabel} />
      </div>
      <label htmlFor={`edit-${s.id}`} className="sr-only">
        Requirement text
      </label>
      <Textarea id={`edit-${s.id}`} autoFocus value={text} aria-invalid={empty} onChange={(e) => setText(e.target.value)} className="min-h-16" />
      <div className="flex flex-wrap items-center gap-2">
        <FieldError>{empty ? EMPTY : update.isError ? errorMessage(update.error) : null}</FieldError>
        <span className="text-xs text-slate">Editing a requirement asks you to confirm the list again.</span>
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
          {update.isPending && <Spinner className="text-white" label="Saving" />}
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
    <li className="space-y-2.5 px-4 py-3.5">
      <div className="flex flex-wrap items-center gap-3">
        <RefTag>{ref}</RefTag>
        <span className="text-xs text-slate">new</span>
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
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') void save()
          if (e.key === 'Escape') onDone()
        }}
      />
      <div className="flex flex-wrap items-center gap-2">
        <FieldError>{add.isError ? errorMessage(add.error) : null}</FieldError>
        <span className="text-xs text-slate">Enter to save · Esc to cancel</span>
        <Button size="sm" variant="ghost" className="ml-auto" onClick={onDone}>
          Cancel
        </Button>
        <Button size="sm" disabled={!text.trim() || add.isPending} onClick={save}>
          {add.isPending && <Spinner className="text-white" label="Adding" />}
          Add
        </Button>
      </div>
    </li>
  )
}

/** The gate: diagrams are drawn only from confirmed requirements; any requirement change clears it. */
function ConfirmBar({ count }: { count: number }) {
  const { project } = useWorkspace()
  const confirm = useConfirmExtraction(project.id)
  const navigate = useNavigate()
  const canEdit = project.role !== 'viewer'

  return (
    <div className="sticky bottom-0 z-20 -mx-5 mt-auto -mb-5 rounded-b-xl border-t border-rule bg-surface/95 backdrop-blur">
      <div className="flex flex-wrap items-center gap-3 px-5 py-3">
        <p className="min-w-0 flex-1 text-sm">
          {project.confirmed ? (
            <>
              <span className="font-medium text-teal-deep">{plural(count, 'requirement')} confirmed</span>
              <span className="text-slate">
                {project.confirmed_at && ` ${formatRelative(project.confirmed_at)}`}. Editing a requirement clears this.
              </span>
            </>
          ) : confirm.isError ? (
            <span className="text-danger">{errorMessage(confirm.error)}</span>
          ) : (
            <span className="text-slate">Generating is locked until you confirm these requirements.</span>
          )}
        </p>
        {project.confirmed ? (
          <Button onClick={() => navigate('../generate')}>Continue to Generate</Button>
        ) : (
          canEdit && (
            <Button disabled={confirm.isPending || count === 0} onClick={() => confirm.mutate()}>
              {confirm.isPending && <Spinner className="text-white" label="Confirming" />}
              Confirm {plural(count, 'requirement')}
            </Button>
          )
        )}
      </div>
    </div>
  )
}
