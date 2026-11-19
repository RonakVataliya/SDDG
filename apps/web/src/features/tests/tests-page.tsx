import { useQueryClient } from '@tanstack/react-query'
import { DownloadIcon, FileCodeIcon } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { useSearchParams } from 'react-router'
import { keys, saveBlob, useTestCases, useTestRequirements } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { StepHeading } from '@/features/input/input-page'
import { slugify } from '@/features/viewer/export-formats'
import { cn } from '@/lib/utils'
import { useWorkspace } from '@/routes/workspace-layout'
import { CasesTab } from './cases-tab'
import { CoverageTab } from './coverage-tab'
import { DesignTab } from './design-tab'
import { EXPORTS_READY, testsToCsv, testsToGherkin } from './export-tests'
import { RunsTab } from './runs-tab'

const TABS = [
  { id: 'design', label: 'Design' },
  { id: 'cases', label: 'Cases' },
  { id: 'runs', label: 'Runs' },
  { id: 'coverage', label: 'Coverage' },
] as const
type TabId = (typeof TABS)[number]['id']

/** Tests (Sprint 3, stream 6): design test cases from requirements, run them by hand, track coverage. */
export function TestsPage() {
  const { project } = useWorkspace()
  const [params, setParams] = useSearchParams()
  const tab: TabId = TABS.some((t) => t.id === params.get('tab')) ? (params.get('tab') as TabId) : 'design'
  const cases = useTestCases(project.id)
  const requirements = useTestRequirements(project.id)
  const canExport = EXPORTS_READY && !!cases.data?.length && !!requirements.data

  // A test job keeps running when the user switches tab. The requirements list polls while one is active; when it
  // ends, refresh every Tests query so the Cases, Runs and Coverage tabs show its result too.
  const qc = useQueryClient()
  const activeJobId = requirements.data?.active_job?.id ?? null
  const lastActive = useRef<string | null>(null)
  useEffect(() => {
    if (lastActive.current && !activeJobId) void qc.invalidateQueries({ queryKey: keys.tests(project.id) })
    lastActive.current = activeJobId
  }, [activeJobId, project.id, qc])

  const download = (kind: 'csv' | 'feature') => {
    if (!cases.data || !requirements.data) return
    const reqs = requirements.data.requirements
    const text = kind === 'csv' ? testsToCsv(cases.data, reqs) : testsToGherkin(cases.data, reqs)
    const type = kind === 'csv' ? 'text/csv' : 'text/plain'
    saveBlob(new Blob([text], { type }), `${slugify(project.name)}-tests.${kind}`)
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      <StepHeading
        title="Tests"
        description="Turn requirements into test cases with black-box techniques, run them by hand and keep a record of every run."
        actions={
          <div className="flex gap-2">
            <Button variant="secondary" size="sm" disabled={!canExport} onClick={() => download('csv')}>
              <DownloadIcon /> Export CSV
            </Button>
            <Button variant="secondary" size="sm" disabled={!canExport} onClick={() => download('feature')}>
              <FileCodeIcon /> Export Gherkin
            </Button>
          </div>
        }
      />
      <div role="tablist" aria-label="Tests" className="flex gap-1 border-b border-rule">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            id={`tests-tab-${t.id}`}
            aria-selected={tab === t.id}
            aria-controls={`tests-panel-${t.id}`}
            onClick={() => setParams(t.id === 'design' ? {} : { tab: t.id }, { replace: true })}
            className={cn(
              '-mb-px border-b-2 px-3 py-2 text-sm font-medium',
              tab === t.id ? 'border-accent text-accent-deep' : 'border-transparent text-slate hover:text-ink',
            )}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`tests-panel-${tab}`} aria-labelledby={`tests-tab-${tab}`} className="flex min-h-0 flex-1 flex-col">
        {tab === 'design' && <DesignTab projectId={project.id} />}
        {tab === 'cases' && <CasesTab projectId={project.id} />}
        {tab === 'runs' && <RunsTab projectId={project.id} />}
        {tab === 'coverage' && <CoverageTab projectId={project.id} />}
      </div>
    </div>
  )
}
