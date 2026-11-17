import { Link } from 'react-router'
import { useCoverage } from '@/api/queries'
import { RefTag } from '@/components/ui/badge'
import { plural } from '@/lib/utils'

/**
 * FR17b: requirements that no latest diagram version draws. The count always equals the coverage count, because
 * both come from the same response; a requirement drawn by a new generation leaves the list by itself.
 */
export function UnrepresentedList({ projectId }: { projectId: string }) {
  const { data } = useCoverage(projectId)
  if (!data) return null

  const missing = data.rows.filter((r) => data.not_represented_refs.includes(r.ref))

  return (
    <section aria-labelledby="unrepresented" className="rounded-lg border border-rule bg-surface">
      <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-rule px-4 py-3">
        <h3 id="unrepresented" className="text-sm font-medium">
          Not in any diagram {data.not_represented}
        </h3>
        <p className="text-xs text-slate">
          {data.with_diagrams} of {plural(data.total, 'requirement is', 'requirements are')} drawn
        </p>
      </div>
      {data.not_represented === 0 ? (
        <p className="px-4 py-4 text-sm text-slate">
          {data.total ? 'Every requirement appears in a diagram.' : 'No requirements yet.'}
        </p>
      ) : (
        <>
          <ul className="divide-y divide-rule">
            {missing.map((r) => (
              <li key={r.id} className="px-4 py-3">
                <RefTag>{r.ref}</RefTag>
                <p className="mt-1.5 text-sm">{r.text}</p>
              </li>
            ))}
          </ul>
          <p className="border-t border-rule px-4 py-2.5 text-xs text-slate">
            A requirement leaves this list once a diagram draws it.{' '}
            <Link to={`/projects/${projectId}/generate`} className="text-teal hover:underline">
              Generate again
            </Link>
          </p>
        </>
      )}
    </section>
  )
}
