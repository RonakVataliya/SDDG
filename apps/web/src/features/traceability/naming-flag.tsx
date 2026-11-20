import { useState } from 'react'
import type { NamingIssue } from '@/api/client'
import { errorMessage } from '@/api/errors'
import { useApplyName, useNamingIssues } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { Notice } from '@/components/ui/notice'
import { Spinner } from '@/components/ui/spinner'
import { toast } from '@/lib/toast'
import { cn, plural } from '@/lib/utils'

function Issue({ projectId, issue }: { projectId: string; issue: NamingIssue }) {
  const names = issue.names
  const [chosen, setChosen] = useState(() => issue.item_name ?? names[0].label)
  const apply = useApplyName(projectId)

  async function onApply() {
    const result = await apply.mutateAsync({ model_item_id: issue.model_item_id, name: chosen }).catch(() => null)
    if (!result) return
    toast(
      result.updated.length
        ? `Renamed to "${chosen}" on ${plural(result.updated.length, 'diagram')}.`
        : `Every diagram already says "${chosen}".`,
    )
  }

  return (
    <li className="px-4 py-3">
      <p className="text-sm">
        The same item is called{' '}
        {names.map((n, i) => (
          <span key={n.label}>
            {i > 0 && (i === names.length - 1 ? ' and ' : ', ')}
            <strong className="font-medium">“{n.label}”</strong> on {n.diagrams.map((d) => d.title).join(', ')}
          </span>
        ))}
        .
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <div role="radiogroup" aria-label="Name to use" className="flex flex-wrap gap-1">
          {names.map((n) => (
            <button
              key={n.label}
              type="button"
              role="radio"
              aria-checked={chosen === n.label}
              onClick={() => setChosen(n.label)}
              className={cn(
                'rounded-sm border px-2 py-1 text-xs font-medium',
                chosen === n.label ? 'border-accent bg-accent-wash text-accent-deep' : 'border-rule-strong text-slate hover:text-ink',
              )}
            >
              {n.label}
            </button>
          ))}
        </div>
        <Button size="sm" variant="secondary" onClick={onApply} disabled={apply.isPending}>
          {apply.isPending ? <Spinner label="" /> : null} Apply this name to all diagrams
        </Button>
      </div>
      {apply.isError && (
        <p role="alert" className="mt-1.5 text-xs text-danger">
          {errorMessage(apply.error, "That name couldn't be applied.")}
        </p>
      )}
    </li>
  )
}

/**
 * FR17e: the same model item labelled differently on different diagrams. Items are matched by model item ID, so two
 * different items that happen to share a name are never flagged.
 */
export function NamingFlag({ projectId }: { projectId: string }) {
  const { data } = useNamingIssues(projectId)
  const issues = data?.issues ?? []
  if (!issues.length) return null

  return (
    <Notice tone="warning" title={`${plural(issues.length, 'item is', 'items are')} named differently across diagrams`} className="p-0">
      <ul className="divide-y divide-amber/20">
        {issues.map((i) => (
          <Issue key={i.model_item_id} projectId={projectId} issue={i} />
        ))}
      </ul>
    </Notice>
  )
}
