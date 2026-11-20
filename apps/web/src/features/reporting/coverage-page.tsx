import { useState } from 'react'
import { Link } from 'react-router'
import { errorMessage } from '@/api/errors'
import { fetchProjectReport, useRequirementCoverage } from '@/api/queries'
import { Badge, RefTag } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Notice } from '@/components/ui/notice'
import { PageLoading, Spinner } from '@/components/ui/spinner'
import { typeLabel } from '@/features/generate/diagram-types'
import { StepHeading } from '@/features/input/input-page'
import { NamingFlag } from '@/features/traceability/naming-flag'
import { plural } from '@/lib/utils'
import { useWorkspace } from '@/routes/workspace-layout'
import { openReport, printReport } from './report'

/** FR20: which requirements the latest version of each diagram represents. */
export function CoveragePage() {
  const { project } = useWorkspace()
  const { data, error, isPending } = useRequirementCoverage(project.id)
  const [busy, setBusy] = useState<'open' | 'pdf' | null>(null)
  const [reportError, setReportError] = useState<string | null>(null)

  async function run(what: 'open' | 'pdf', show: typeof openReport) {
    setBusy(what)
    setReportError(null)
    try {
      await show(() => fetchProjectReport(project.id))
    } catch (e) {
      setReportError(errorMessage(e, "The report didn't load. Try again."))
    } finally {
      setBusy(null)
    }
  }

  if (isPending) return <PageLoading label="Loading coverage" />
  if (!data)
    return (
      <Notice tone="error" title="Couldn't load the coverage">
        {errorMessage(error)}
      </Notice>
    )

  return (
    <div className="space-y-5">
      <StepHeading
        title="Requirement coverage"
        description="Each requirement and the diagrams that represent it (latest version of each diagram)."
        actions={
          <div className="flex flex-col items-end gap-1.5">
            <div className="flex gap-2">
              <Button variant="secondary" disabled={busy !== null} onClick={() => void run('open', openReport)}>
                {busy === 'open' && <Spinner label="" />}
                Open report
              </Button>
              <Button variant="secondary" disabled={busy !== null} onClick={() => void run('pdf', printReport)}>
                {busy === 'pdf' && <Spinner label="" />}
                Download PDF
              </Button>
            </div>
            <p className="text-xs text-slate">In the print dialog, choose &ldquo;Save as PDF&rdquo; as the destination.</p>
          </div>
        }
      />
      {reportError && (
        <Notice tone="error" title="Couldn't load the report">
          {reportError}
        </Notice>
      )}
      {data.total === 0 ? (
        <Notice title="No requirements yet">Add requirements on the Input step to see which diagrams cover them.</Notice>
      ) : (
        <>
          {/* FR17e: the same model item named differently across diagrams, with "Apply this name to all diagrams". */}
          <NamingFlag projectId={project.id} />
          <p className="text-sm text-slate" data-testid="coverage-totals">
            {plural(data.total, 'requirement')} · {data.with_diagrams} covered by a diagram · {data.not_represented} not represented ·{' '}
            {data.with_open_flags} with open issues
          </p>
          <ul className="divide-y divide-rule rounded-xl border border-rule bg-field">
            {data.rows.map((r) => (
              <li key={r.id} className="flex flex-wrap items-start gap-x-3 gap-y-1 px-4 py-3">
                <RefTag>{r.ref}</RefTag>
                <span className="min-w-0 flex-1">{r.text}</span>
                <span className="flex flex-wrap items-center gap-2 text-sm">
                  {r.open_flags.map((f) => (
                    <Badge key={f} tone="amber" className="capitalize">
                      {f}
                    </Badge>
                  ))}
                  {r.diagrams.length === 0 ? (
                    <Badge tone="danger">Not represented</Badge>
                  ) : (
                    r.diagrams.map((d) => (
                      <Link key={d.id} to={`/projects/${project.id}/diagrams/${d.id}`} title={d.title} className="font-medium text-accent hover:underline">
                        {typeLabel[d.type]} v{d.version}
                      </Link>
                    ))
                  )}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}
