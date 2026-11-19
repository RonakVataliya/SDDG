import { CheckIcon, ChevronDownIcon, FlagIcon, MessageSquareIcon, RotateCcwIcon, WandSparklesIcon, XIcon } from 'lucide-react'
import { Dialog as D } from 'radix-ui'
import { useState } from 'react'
import type { Flag, FlagSummary, FlagType, RequirementStatement } from '@/api/client'
import { errorMessage } from '@/api/errors'
import { useFlagAction, useFlags } from '@/api/queries'
import { Badge, RefTag } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { cn, formatRelative } from '@/lib/utils'

/** Flag colours are fixed (they never follow the accent) so a type always looks the same. */
// `untestable` is raised by the Tests feature (answered there in question-card.tsx); here it is shown like any other flag.
export const FLAG_TONE: Record<FlagType, 'amber' | 'violet' | 'danger' | 'neutral'> = { ambiguous: 'amber', incomplete: 'violet', conflict: 'danger', untestable: 'neutral' }
export const FLAG_LABEL: Record<FlagType, string> = { ambiguous: 'Ambiguous', incomplete: 'Incomplete', conflict: 'Conflict', untestable: 'Untestable' }
const WAVY: Record<FlagType, string> = { ambiguous: 'wavy-amber', incomplete: 'wavy-violet', conflict: 'wavy-danger', untestable: 'wavy-violet' }
const QUOTE_BORDER: Record<FlagType, string> = { ambiguous: 'border-amber', incomplete: 'border-violet', conflict: 'border-danger', untestable: 'border-rule-strong' }
const MAX_ANSWER = 1000

/** Requirement text with its flag's trigger words underlined. */
export function Highlighted({ text, trigger, type }: { text: string; trigger?: string | null; type?: FlagType }) {
  const at = trigger && type ? text.toLowerCase().indexOf(trigger.toLowerCase()) : -1
  if (at < 0 || !type) return <>{text}</>
  return (
    <>
      {text.slice(0, at)}
      <span className={WAVY[type]}>{text.slice(at, at + trigger!.length)}</span>
      {text.slice(at + trigger!.length)}
    </>
  )
}

/** The pill beside a requirement: its first open flag type (+count), or "Resolved" once none are open. */
export function FlagPill({ summary, openTypes, onClick }: { summary?: FlagSummary; openTypes?: FlagType[]; onClick?: () => void }) {
  if (!summary) return null
  // summary.types also lists the types of resolved flags, so the open ones come from the flags list.
  const type = openTypes?.[0] ?? summary.types[0]
  const body =
    summary.open > 0 ? (
      <Badge tone={FLAG_TONE[type]}>
        <FlagIcon /> {FLAG_LABEL[type]}
        {summary.open > 1 && ` +${summary.open - 1}`}
      </Badge>
    ) : (
      <Badge tone="success">
        <CheckIcon /> Resolved
      </Badge>
    )
  return onClick ? (
    <button type="button" onClick={onClick} aria-label={`${summary.open} open flags on ${summary.statement_ref}`} className="shrink-0">
      {body}
    </button>
  ) : (
    body
  )
}

/** Side sheet listing a project's flags with answer / apply fix / resolve / reopen. */
export function FlagsDrawer({
  projectId,
  open,
  onOpenChange,
  focusStatementId,
  statements,
  canEdit,
}: {
  projectId: string
  open: boolean
  onOpenChange: (o: boolean) => void
  focusStatementId?: string | null
  statements: RequirementStatement[]
  canEdit: boolean
}) {
  const flags = useFlags(projectId)
  const [tab, setTab] = useState<'open' | 'resolved'>('open')
  const all = flags.data ?? []
  const shown = all.filter((f) => f.status === tab)
  const firstFocus = shown.find((f) => f.statement_id === focusStatementId)?.id ?? shown[0]?.id
  const [expanded, setExpanded] = useState<string | null>(null)
  const current = expanded && shown.some((f) => f.id === expanded) ? expanded : firstFocus
  const byId = new Map(statements.map((s) => [s.id, s]))

  return (
    <D.Root open={open} onOpenChange={onOpenChange}>
      <D.Portal>
        <D.Overlay className="fixed inset-0 z-40 bg-[rgb(17_19_24/0.2)]" />
        <D.Content className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[520px] flex-col border-l border-rule bg-surface shadow-[var(--shadow)]">
          <div className="px-5 pt-5">
            <div className="flex items-center justify-between">
              <D.Title className="flex items-center gap-2 font-display text-xl font-semibold">
                <FlagIcon className="size-5" /> Requirement flags
              </D.Title>
              <D.Close className="rounded-md p-1 text-slate hover:text-ink" aria-label="Close">
                <XIcon className="size-5" />
              </D.Close>
            </div>
            <D.Description className="mt-1 text-[12px] text-slate">
              Things that may make a requirement hard to model or test. Fix, answer or dismiss them; nothing is blocked.
            </D.Description>
            <div role="tablist" className="mt-4 flex gap-5 border-b border-rule text-[13px]">
              {(['open', 'resolved'] as const).map((t) => (
                <button
                  key={t}
                  role="tab"
                  type="button"
                  aria-selected={tab === t}
                  onClick={() => setTab(t)}
                  className={cn('-mb-px border-b-2 px-0.5 pb-2.5 capitalize', tab === t ? 'border-ink font-semibold' : 'border-transparent text-slate')}
                >
                  {t} <span className="text-slate">{all.filter((f) => f.status === t).length}</span>
                </button>
              ))}
            </div>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {flags.isPending ? (
              <p className="p-5 text-[13px] text-slate">Loading flags…</p>
            ) : shown.length === 0 ? (
              <p className="p-5 text-[13px] text-slate">{tab === 'open' ? 'No open flags. Nice and clear.' : 'Nothing resolved yet.'}</p>
            ) : (
              shown.map((f) =>
                f.id === current ? (
                  <FlagCard
                    key={f.id}
                    projectId={projectId}
                    canEdit={canEdit}
                    flag={f}
                    text={f.statement_text ?? byId.get(f.statement_id)?.text ?? ''}
                    related={f.related_statement_id ? byId.get(f.related_statement_id) : undefined}
                  />
                ) : (
                  <button
                    key={f.id}
                    type="button"
                    onClick={() => setExpanded(f.id)}
                    className="flex w-full items-center gap-3 border-b border-rule px-5 py-3.5 text-left hover:bg-ink/3"
                  >
                    <Badge tone={FLAG_TONE[f.type]}>{FLAG_LABEL[f.type]}</Badge>
                    <RefTag>{f.statement_ref}</RefTag>
                    <span className="min-w-0 flex-1 truncate text-[13px]">{f.status === 'resolved' && f.answer ? `Answer: ${f.answer}` : f.reason}</span>
                    <ChevronDownIcon className="size-4 text-slate" />
                  </button>
                ),
              )
            )}
          </div>
        </D.Content>
      </D.Portal>
    </D.Root>
  )
}

function FlagCard({ projectId, canEdit, flag: f, text, related }: { projectId: string; canEdit: boolean; flag: Flag; text: string; related?: RequirementStatement }) {
  const [answer, setAnswer] = useState('')
  const act = useFlagAction(projectId)
  const pending = act.isPending ? act.variables?.kind : null
  const resolved = f.status === 'resolved'

  return (
    <div className="border-b border-rule bg-field px-5 py-5">
      <div className="flex items-center gap-2">
        <Badge tone={FLAG_TONE[f.type]}>{FLAG_LABEL[f.type]}</Badge>
        <RefTag>{f.statement_ref}</RefTag>
        {resolved ? (
          <Badge tone="success" className="ml-auto">
            <CheckIcon /> Resolved
          </Badge>
        ) : (
          <span className="ml-auto text-[11.5px] text-slate">Advisory</span>
        )}
      </div>

      {f.type === 'conflict' && related ? (
        <div className="mt-4 grid grid-cols-[1fr_auto_1fr] items-center gap-2">
          <div className="rounded-[9px] border border-rule p-3">
            <RefTag>{related.ref}</RefTag>
            <p className="mt-1.5 text-[13px]">{related.text}</p>
          </div>
          <span className="text-danger" aria-label="conflicts with">≠</span>
          <div className="rounded-[9px] border-[1.5px] border-danger bg-danger-wash p-3">
            <RefTag>{f.statement_ref}</RefTag>
            <p className="mt-1.5 text-[13px]">
              <Highlighted text={text} trigger={f.trigger_text} type={f.type} />
            </p>
          </div>
        </div>
      ) : (
        <blockquote className={cn('mt-4 rounded-r-lg border-l-[3px] bg-paper px-3 py-2.5 text-[13px]', QUOTE_BORDER[f.type])}>
          <Highlighted text={text} trigger={f.trigger_text} type={f.type} />
        </blockquote>
      )}
      <p className="mt-3 text-[13px] text-ink-2">
        <b>Why:</b> {f.reason}
      </p>

      {resolved ? (
        <>
          {f.answer && (
            <p className="mt-3 rounded-lg bg-paper px-3 py-2 text-[13px]">
              <b>Answer:</b> {f.answer}
            </p>
          )}
          <div className="mt-3 flex items-center justify-between text-[12px] text-slate">
            <span>
              {f.resolved_by ?? 'Resolved'}
              {f.resolved_at && ` · ${formatRelative(f.resolved_at)}`}
            </span>
            {canEdit && (
              <Button variant="link" size="sm" disabled={!!pending} onClick={() => act.mutate({ kind: 'reopen', flagId: f.id })}>
                <RotateCcwIcon className="size-3.5" /> Reopen
              </Button>
            )}
          </div>
        </>
      ) : !canEdit ? (
        <>
          {f.has_suggestion && (
            <p className="mt-4 rounded-[10px] bg-accent-wash p-3.5 text-[13px]">
              <b>Suggested rewrite:</b> {f.suggestion}
            </p>
          )}
          <p className="mt-4 text-[12px] text-slate">Only editors can answer or resolve flags.</p>
        </>
      ) : (
        <>
          {f.question && (
            <p className="mt-4 flex items-start gap-2 text-[13px] font-semibold">
              <MessageSquareIcon className="mt-0.5 size-3.5 shrink-0" /> {f.question}
            </p>
          )}
          <label htmlFor={`answer-${f.id}`} className="sr-only">
            Your answer
          </label>
          <Textarea
            id={`answer-${f.id}`}
            value={answer}
            maxLength={MAX_ANSWER}
            onChange={(e) => setAnswer(e.target.value)}
            placeholder="Type your answer. The requirement text stays as is."
            className="mt-2 min-h-16 text-[13.5px]"
          />
          <div className="mt-2 flex items-center gap-2">
            <span className="font-mono text-[11px] text-slate">
              {answer.length} / {MAX_ANSWER}
            </span>
            <Button
              variant="secondary"
              size="sm"
              className="ml-auto"
              disabled={!answer.trim() || !!pending}
              onClick={() => act.mutate({ kind: 'answer', flagId: f.id, answer: answer.trim() })}
            >
              {pending === 'answer' && <Spinner label="Saving" />}
              Save answer &amp; resolve
            </Button>
          </div>

          {f.has_suggestion ? (
            <div className="mt-4 rounded-[10px] bg-accent-wash p-3.5">
              <p className="flex items-center gap-2 text-[13px] font-semibold text-accent-deep">
                <WandSparklesIcon className="size-3.5" /> Suggested rewrite
              </p>
              <p className="mt-2 text-[13px] text-slate line-through">{text}</p>
              <p className="mt-1 text-[13px]">{f.suggestion}</p>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <Button variant="accent" size="sm" disabled={!!pending} onClick={() => act.mutate({ kind: 'apply-fix', flagId: f.id })}>
                  {pending === 'apply-fix' ? <Spinner className="text-on-ink" label="Applying" /> : <CheckIcon />}
                  Apply fix
                </Button>
                <span className="text-[11.5px] text-accent-deep">
                  Replaces {f.statement_ref}&rsquo;s text{f.type === 'conflict' ? ' and can close the matching conflict flag' : ''}
                </span>
              </div>
            </div>
          ) : (
            <p className="mt-4 text-[12px] text-slate">No automatic fix for this one. Answer the question, or mark it resolved.</p>
          )}
          <Button variant="link" size="sm" className="mt-3 text-ink-2" disabled={!!pending} onClick={() => act.mutate({ kind: 'resolve', flagId: f.id })}>
            Mark resolved without changes
          </Button>
        </>
      )}
      {act.isError && <p role="alert" className="mt-2 text-[12.5px] text-danger">{errorMessage(act.error)}</p>}
    </div>
  )
}
