import { useDrift } from '@/api/queries'
import { Notice } from '@/components/ui/notice'

/**
 * FR17d: a manual edit that moved away from the requirements — an element a requirement calls for was removed, or
 * a relationship the requirements do not support was added. Nothing is stored, so the banner goes away by itself
 * when the edit is reverted or the requirement is updated to match.
 */
export function DriftBanner({ diagramId }: { diagramId: string }) {
  const { data } = useDrift(diagramId)
  const warnings = data?.warnings ?? []
  if (!warnings.length) return null

  return (
    <Notice
      tone="warning"
      title={`This version no longer matches ${warnings.length === 1 ? 'a requirement' : 'the requirements'}`}
      className="mx-5 mt-3"
    >
      <ul className="space-y-1">
        {warnings.map((w) => (
          <li key={w.id}>{w.message}</li>
        ))}
      </ul>
      <p className="mt-2 text-xs">
        Update the requirement to match, or revert the change. The warning clears by itself once they agree.
      </p>
    </Notice>
  )
}
