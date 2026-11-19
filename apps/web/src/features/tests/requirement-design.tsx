import { CpuIcon, PencilIcon, RefreshCwIcon } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import type { Condition, Criterion, TestDesign, TestRequirementSummary } from '@/api/client'
import { errorMessage } from '@/api/errors'
import { useTestDesign, useUpdateCondition, useUpdateCriterion } from '@/api/queries'
import { Badge, RefTag } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Notice } from '@/components/ui/notice'
import { PageLoading } from '@/components/ui/spinner'
import { cn } from '@/lib/utils'
import { AiBadge } from './ai-badge'
import { DraftCases } from './draft-cases'
import { QuestionCard } from './question-card'

/** Right-hand panel of the Design tab: one requirement's criteria, conditions (with their classes and boundaries)
 *  and flows. Conditions can be edited; the server recomputes classes, boundaries and drafts with no AI call. */
export function RequirementDesign({
  projectId,
  requirement,
  canEdit,
  onRegenerate,
}: {
  projectId: string
  requirement: TestRequirementSummary
  canEdit: boolean
  /** Reruns AI request 1 for this one requirement (its text changed since its design was made). */
  onRegenerate?: (statementId: string) => void
}) {
  const design = useTestDesign(projectId, requirement.statement_id)

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start gap-2 rounded-xl border border-rule bg-field px-4 py-3">
        <RefTag>{requirement.ref}</RefTag>
        <p className="min-w-0 flex-1 font-medium">{requirement.text}</p>
        {requirement.label && <Badge>{requirement.label}</Badge>}
        {requirement.stale && <Badge tone="amber">Requirement changed</Badge>}
        {requirement.stale && canEdit && onRegenerate && (
          <Button size="sm" variant="secondary" onClick={() => onRegenerate(requirement.statement_id)}>
            <RefreshCwIcon /> Regenerate {requirement.ref}
          </Button>
        )}
      </div>

      {design.isPending ? (
        <PageLoading label="Loading the design" />
      ) : design.isError ? (
        <Notice tone="error" title="Couldn't load this requirement's tests">
          {errorMessage(design.error)}
        </Notice>
      ) : !design.data.designed ? (
        <p className="rounded-lg border border-dashed border-rule-strong px-5 py-8 text-center text-sm text-slate">
          No tests yet. Tick {requirement.ref} on the left and click Generate criteria.
        </p>
      ) : (
        <DesignBody projectId={projectId} design={design.data} canEdit={canEdit} />
      )}
    </div>
  )
}

function DesignBody({ projectId, design, canEdit }: { projectId: string; design: TestDesign; canEdit: boolean }) {
  const question = design.question && <QuestionCard key={design.question.id} projectId={projectId} design={design} canEdit={canEdit} />
  if (!design.criteria.length) return question ?? null
  return (
    <>
      {design.question?.status === 'open' && question}
      <Section title="Acceptance criteria" note={`${design.criteria.length} · editable`} badges={<AiBadge n={1} />}>
        <ol className="divide-y divide-rule">
          {design.criteria.map((c, i) => (
            <CriterionRow key={c.id} index={i + 1} criterion={c} projectId={projectId} statementId={design.statement_id} canEdit={canEdit} />
          ))}
        </ol>
      </Section>

      {design.conditions.length > 0 && (
        <Section
          title="Conditions"
          note="inputs the requirement names"
          badges={
            <>
              <AiBadge n={1} />
              <Badge tone="accent">
                <CpuIcon className="size-3" /> Classes and boundaries: plain code, no AI
              </Badge>
            </>
          }
        >
          <ul className="divide-y divide-rule">
            {design.conditions.map((c) => (
              <ConditionRow key={c.id} condition={c} projectId={projectId} canEdit={canEdit} />
            ))}
          </ul>
        </Section>
      )}

      {design.flows.length > 0 && (
        <Section title="Flows" badges={<AiBadge n={1} />}>
          <ul className="divide-y divide-rule">
            {design.flows.map((f) => (
              <li key={f.id} className="flex gap-3 px-4 py-2.5 text-sm">
                <span className="w-12 shrink-0 font-mono text-[11px] font-semibold tracking-wide text-slate uppercase">
                  {f.kind === 'basic' ? 'Basic' : 'Alt'}
                </span>
                {f.text}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {design.performance_targets.length > 0 && (
        <Section title="Performance targets" note="from the requirement's measurable target">
          <ul className="divide-y divide-rule">
            {design.performance_targets.map((t) => (
              <li key={t.measure} className="px-4 py-2.5 text-sm">
                {t.measure} under {t.limit} {t.unit}
                {t.load && <span className="text-slate"> with {t.load}</span>}
              </li>
            ))}
          </ul>
        </Section>
      )}

      <DraftCases projectId={projectId} design={design} canEdit={canEdit} />
    </>
  )
}

function Section({ title, note, badges, children }: { title: string; note?: string; badges?: ReactNode; children: ReactNode }) {
  return (
    <section className="overflow-hidden rounded-xl border border-rule bg-field" aria-label={title}>
      <header className="flex flex-wrap items-center gap-2 border-b border-rule px-4 py-2.5">
        <h4 className="text-sm font-semibold">{title}</h4>
        {note && <span className="text-xs text-slate">{note}</span>}
        <span className="ml-auto flex flex-wrap gap-1.5">{badges}</span>
      </header>
      {children}
    </section>
  )
}

/* ---------- criteria ---------- */

function CriterionRow({
  index,
  criterion,
  projectId,
  statementId,
  canEdit,
}: {
  index: number
  criterion: Criterion
  projectId: string
  statementId: string
  canEdit: boolean
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(criterion)
  const save = useUpdateCriterion(projectId, statementId)
  const parts = [
    ['Given', 'given'],
    ['When', 'when'],
    ['Then', 'then'],
  ] as const

  if (editing) {
    return (
      <li className="space-y-2 px-4 py-3">
        {parts.map(([label, key]) => (
          <label key={key} className="flex items-center gap-3 text-sm">
            <span className="w-12 font-mono text-[11px] font-semibold text-accent-deep uppercase">{label}</span>
            <Input className="h-9" value={draft[key]} onChange={(e) => setDraft({ ...draft, [key]: e.target.value })} />
          </label>
        ))}
        {save.isError && <p className="text-sm text-danger">{errorMessage(save.error)}</p>}
        <div className="flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={() => setEditing(false)}>
            Cancel
          </Button>
          <Button
            size="sm"
            disabled={save.isPending}
            onClick={() => save.mutate({ criterionId: criterion.id, ...draft }, { onSuccess: () => setEditing(false) })}
          >
            Save criterion
          </Button>
        </div>
      </li>
    )
  }
  return (
    <li className="group flex gap-3 px-4 py-3 text-sm">
      <span className="w-4 shrink-0 text-slate tabular-nums">{index}</span>
      <dl className="grid flex-1 grid-cols-[3.5rem_minmax(0,1fr)] gap-x-2 gap-y-0.5">
        {parts.map(([label, key]) => (
          <div key={key} className="contents">
            <dt className="font-mono text-[11px] leading-5 font-semibold text-accent-deep uppercase">{label}</dt>
            <dd>{criterion[key]}</dd>
          </div>
        ))}
      </dl>
      {canEdit && (
        <Button
          variant="ghost"
          size="icon"
          className="size-7 opacity-60 group-hover:opacity-100"
          aria-label={`Edit criterion ${index}`}
          onClick={() => {
            setDraft(criterion)
            setEditing(true)
          }}
        >
          <PencilIcon />
        </Button>
      )}
    </li>
  )
}

/* ---------- conditions ---------- */

const fmt = (n: number) => String(Number(n.toFixed(6)))

function ConditionRow({ condition: c, projectId, canEdit }: { condition: Condition; projectId: string; canEdit: boolean }) {
  const update = useUpdateCondition(projectId)
  return (
    <li className="grid gap-x-4 gap-y-2 px-4 py-3 text-sm md:grid-cols-[9rem_minmax(0,1fr)]">
      <div>
        <p className="font-mono text-[13px] font-medium">{c.name}</p>
        <Badge className="mt-1">{c.kind}</Badge>
      </div>
      <div className="min-w-0 space-y-2">
        {c.kind === 'set' ? (
          <SetEditor condition={c} canEdit={canEdit} onSave={(body) => update.mutate({ conditionId: c.id, body })} />
        ) : (
          <LimitsEditor condition={c} canEdit={canEdit} onSave={(body) => update.mutate({ conditionId: c.id, body })} />
        )}
        {update.isError && <p className="text-sm text-danger">{errorMessage(update.error)}</p>}
        <ChipRow label="classes">
          {c.classes.map((k) => (
            <span
              key={`${k.valid}-${k.label}`}
              className={cn('rounded-sm px-1.5 py-px text-xs', k.valid ? 'bg-accent-wash text-accent-deep' : 'bg-danger-wash text-danger')}
            >
              {k.valid ? 'valid' : 'invalid'} {k.label}
            </span>
          ))}
        </ChipRow>
        {c.boundaries.length > 0 && (
          <ChipRow label="boundaries">
            {c.boundaries.map((b) => (
              <span
                key={b.value}
                title={b.valid ? 'Should be accepted' : 'Should be rejected'}
                className={cn(
                  'min-w-7 rounded-sm border px-1.5 py-px text-center font-mono text-xs tabular-nums',
                  b.valid ? 'border-rule-strong text-ink' : 'border-danger/40 bg-danger-wash text-danger',
                )}
              >
                {fmt(b.value)}
              </span>
            ))}
          </ChipRow>
        )}
      </div>
    </li>
  )
}

function ChipRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="w-20 shrink-0 text-xs text-slate">{label}</span>
      {children}
    </div>
  )
}

/** Inline number inputs; a change is saved when the field loses focus or Enter is pressed. */
function LimitsEditor({
  condition: c,
  canEdit,
  onSave,
}: {
  condition: Condition
  canEdit: boolean
  onSave: (body: { min?: number | null; max?: number | null }) => void
}) {
  const field = (key: 'min' | 'max') => {
    const value = c[key] ?? null
    return (
      <LimitInput
        key={`${key}-${value}`}
        label={`${c.name} ${key === 'min' ? 'lower' : 'upper'} limit`}
        value={value}
        disabled={!canEdit}
        onCommit={(n) => {
          if (n !== value) onSave({ [key]: n })
        }}
      />
    )
  }
  return (
    <p className="flex flex-wrap items-center gap-1.5 text-ink/90">
      {c.kind === 'range' && 'from'} {field('min')} to {field('max')} {c.unit ?? c.description}
    </p>
  )
}

function LimitInput({
  label,
  value,
  disabled,
  onCommit,
}: {
  label: string
  value: number | null
  disabled: boolean
  onCommit: (n: number | null) => void
}) {
  const [text, setText] = useState(value === null ? '' : fmt(value))
  const commit = () => {
    const trimmed = text.trim()
    if (trimmed === '') return onCommit(null)
    const n = Number(trimmed)
    if (Number.isFinite(n)) onCommit(n)
    else setText(value === null ? '' : fmt(value))
  }
  return (
    <input
      aria-label={label}
      inputMode="decimal"
      value={text}
      disabled={disabled}
      onChange={(e) => setText(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === 'Enter') (e.target as HTMLInputElement).blur()
      }}
      className="h-7 w-14 rounded-sm border border-dashed border-rule-strong bg-paper text-center font-mono text-[13px] tabular-nums focus-visible:border-solid focus-visible:border-accent focus-visible:outline-none disabled:border-transparent disabled:bg-transparent"
    />
  )
}

/** A set's values edited as comma-separated text; invalid values in a second field. */
function SetEditor({
  condition: c,
  canEdit,
  onSave,
}: {
  condition: Condition
  canEdit: boolean
  onSave: (body: { values?: string[]; invalid_values?: string[] }) => void
}) {
  const [editing, setEditing] = useState(false)
  const [values, setValues] = useState(c.values.join(', '))
  const [invalid, setInvalid] = useState(c.invalid_values.join(', '))
  const split = (s: string) =>
    s
      .split(',')
      .map((v) => v.trim())
      .filter(Boolean)

  if (!editing)
    return (
      <p className="flex flex-wrap items-center gap-2">
        {c.values.join(' · ')}
        {canEdit && (
          <Button variant="link" size="sm" onClick={() => setEditing(true)}>
            Edit values
          </Button>
        )}
      </p>
    )
  return (
    <div className="space-y-2">
      <Input className="h-9" aria-label={`${c.name} valid values`} value={values} onChange={(e) => setValues(e.target.value)} />
      <Input className="h-9" aria-label={`${c.name} invalid values`} value={invalid} onChange={(e) => setInvalid(e.target.value)} />
      <div className="flex justify-end gap-2">
        <Button variant="ghost" size="sm" onClick={() => setEditing(false)}>
          Cancel
        </Button>
        <Button
          size="sm"
          onClick={() => {
            onSave({ values: split(values), invalid_values: split(invalid) })
            setEditing(false)
          }}
        >
          Save values
        </Button>
      </div>
    </div>
  )
}
