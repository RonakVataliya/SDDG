import { CpuIcon } from 'lucide-react'
import type { TestCase, TestDesign } from '@/api/client'
import { errorMessage } from '@/api/errors'
import { useUpdateCase } from '@/api/queries'
import { Badge, RefTag } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { cn } from '@/lib/utils'
import { KIND, TECHNIQUE, testDataLine } from './labels'

/** The requirement's generated cases. Untick a draft you don't need: AI request 2 only writes steps for kept ones. */
export function DraftCases({ projectId, design, canEdit }: { projectId: string; design: TestDesign; canEdit: boolean }) {
  const update = useUpdateCase(projectId)
  const fromFlows = design.drafts.filter((d) => d.technique === 'Flow').length
  if (!design.drafts.length) return null
  return (
    <section className="overflow-hidden rounded-lg border border-rule bg-surface" aria-label="Draft test cases">
      <header className="flex flex-wrap items-center gap-2 border-b border-rule px-4 py-2.5">
        <h4 className="text-sm font-semibold">Draft test cases</h4>
        <span className="text-xs text-slate" data-testid="draft-summary">
          {design.drafts.length - fromFlows} from conditions + {fromFlows} from flows
        </span>
        <Badge tone="teal" className="ml-auto">
          <CpuIcon className="size-3" /> Built by code
        </Badge>
      </header>
      {update.isError && <p className="px-4 pt-2 text-sm text-danger">{errorMessage(update.error)}</p>}
      <ul className="max-h-[28rem] divide-y divide-rule overflow-y-auto">
        {design.drafts.map((c) => (
          <DraftRow
            key={c.id}
            draft={c}
            disabled={!canEdit || c.status === 'ready' || update.isPending}
            onKeep={(kept) => update.mutate({ caseId: c.id, body: { kept } })}
          />
        ))}
      </ul>
    </section>
  )
}

function DraftRow({ draft: c, disabled, onKeep }: { draft: TestCase; disabled: boolean; onKeep: (kept: boolean) => void }) {
  const kind = KIND[c.kind]
  return (
    <li className={cn('flex items-start gap-3 px-4 py-2.5 text-sm', !c.kept && 'opacity-55')}>
      <Checkbox
        checked={c.kept}
        disabled={disabled}
        onCheckedChange={(v) => onKeep(v === true)}
        aria-label={`Keep ${c.number}`}
        className="mt-0.5"
      />
      <RefTag>{c.number}</RefTag>
      <span className="w-14 shrink-0 font-mono text-xs leading-5 text-slate" title={TECHNIQUE[c.technique]}>
        {c.technique}
      </span>
      <Badge tone={kind.tone} className="w-[4.5rem] justify-center">
        {kind.label}
      </Badge>
      <span className="min-w-0 flex-1">
        <span className={cn('block', !c.kept && 'line-through')}>{c.title}</span>
        {Object.keys(c.test_data).length > 0 && (
          <span className="block font-mono text-xs text-slate">{testDataLine(c.test_data)}</span>
        )}
      </span>
      {c.status === 'ready' && <Badge tone="teal">Ready</Badge>}
    </li>
  )
}
