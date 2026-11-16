/** Placeholder from the Design tab commit; the criteria and conditions commit replaces this file. */
import type { TestRequirementSummary } from '@/api/client'
import { RefTag } from '@/components/ui/badge'

export function RequirementDesign({ requirement }: { projectId: string; requirement: TestRequirementSummary; canEdit: boolean }) {
  return (
    <div className="rounded-lg border border-rule bg-surface p-5">
      <p className="flex gap-2">
        <RefTag>{requirement.ref}</RefTag> {requirement.text}
      </p>
      <p className="mt-3 text-sm text-slate">
        {requirement.designed ? `${requirement.criteria_count} criteria · ${requirement.draft_count} drafts` : 'Not generated yet.'}
      </p>
    </div>
  )
}
