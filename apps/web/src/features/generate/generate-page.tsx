import { useQueryClient } from '@tanstack/react-query'
import { LockIcon, MousePointerClickIcon } from 'lucide-react'
import { useEffect } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { keys, useJob } from '@/api/queries'
import { JobProgress } from '@/components/job-progress'
import { Button } from '@/components/ui/button'
import { Notice } from '@/components/ui/notice'
import { PageLoading } from '@/components/ui/spinner'
import { StepHeading } from '@/features/input/input-page'
import { useWorkspace } from '@/routes/workspace-layout'
import { typeLabel } from './diagram-types'

/** Middle panel for step 3. The type picker lives in the Generate panel (generate-panel.tsx); a run's progress shows here. */
export function GeneratePage() {
  const { project } = useWorkspace()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [params, setParams] = useSearchParams()
  const jobId = params.get('job')
  const { data: job } = useJob(jobId)

  useEffect(() => {
    if (job?.status !== 'succeeded') return
    void qc.invalidateQueries({ queryKey: keys.project(project.id), exact: true })
    void qc.invalidateQueries({ queryKey: keys.diagrams(project.id) })
    if (job.diagram_ids?.[0]) navigate(`../diagrams/${job.diagram_ids[0]}`, { replace: true })
  }, [job?.status, job?.diagram_ids, navigate, project.id, qc])

  if (!project.confirmed && !jobId) {
    return (
      <div className="space-y-4">
        <StepHeading title="Generate diagrams" />
        <Notice tone="warning" title="Confirm the extracted items first">
          Diagrams are built only from confirmed items.{' '}
          <Link to="../review" className="font-medium underline">
            Go to Review
          </Link>
        </Notice>
      </div>
    )
  }

  if (jobId && !job) return <PageLoading label="Loading run" />

  // A run is in progress (or just failed): the selection is locked, so show it read-only with the progress.
  if (jobId && job) {
    const types = job.diagram_types ?? []
    return (
      <div className="space-y-4">
        <StepHeading title="Generating" />
        <p className="flex flex-wrap items-center gap-2 text-sm text-slate">
          <LockIcon className="size-3.5" aria-hidden /> Locked for this run:
          {types.map((t) => (
            <span key={t} className="font-medium text-ink">
              {typeLabel[t]}
            </span>
          ))}
        </p>
        <JobProgress job={job} title={job.status === 'failed' ? 'Generation failed' : 'Generating your diagram'} />
        {job.status === 'failed' && (
          <Button variant="secondary" onClick={() => setParams({})}>
            Choose again
          </Button>
        )}
      </div>
    )
  }

  return (
    <div className="grid h-full min-h-64 place-items-center text-center">
      <div className="max-w-sm">
        <MousePointerClickIcon className="mx-auto size-6 text-teal" aria-hidden />
        <h2 className="mt-3 text-lg font-semibold tracking-tight">Ready to generate</h2>
        <p className="mt-1 text-slate">
          Pick the diagrams you want in the Generate panel, then press Generate. Progress shows here, and the diagram opens
          when it's done.
        </p>
      </div>
    </div>
  )
}
