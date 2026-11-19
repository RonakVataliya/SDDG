import { CheckIcon, LockIcon, SaveIcon, SparklesIcon } from 'lucide-react'
import { type ComponentType, useState } from 'react'
import { useSearchParams } from 'react-router'
import type { DesignKind, DesignSection, RequirementStatement } from '@/api/client'
import { errorMessage } from '@/api/errors'
import { useConfirmDesignSection, useDesign, useDesignJob, useSaveDesignSection, useStartDesignDraft, useStatements } from '@/api/queries'
import { JobProgress } from '@/components/job-progress'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogTitle } from '@/components/ui/dialog'
import { Notice } from '@/components/ui/notice'
import { PageLoading } from '@/components/ui/spinner'
import { StepHeading } from '@/features/input/input-page'
import { isConsentError, useConsentRetry } from '@/features/tests/consent-retry'
import { cn } from '@/lib/utils'
import { useWorkspace } from '@/routes/workspace-layout'
import { GoalsEditor } from './goals-editor'

type Content = Record<string, unknown>
/** What every section editor gets: the content being edited and the server's derived values for the saved version. */
export type EditorProps = {
  content: Content
  derived: Content | null
  dirty: boolean
  disabled: boolean
  confirmed: boolean
  requirements: RequirementStatement[]
  onChange: (content: Content) => void
}

/** One editor per section kind; a new kind is one entry here (and in the API's KINDS). */
const EDITORS: Record<DesignKind, { Editor: ComponentType<EditorProps>; empty: Content }> = {
  goals: { Editor: GoalsEditor, empty: { goals: [] } },
}

const STATUS = {
  empty: { label: 'Empty', tone: 'neutral' },
  draft: { label: 'Draft', tone: 'amber' },
  confirmed: { label: 'Confirmed', tone: 'accent' },
} as const

const isActive = (status?: string) => status === 'queued' || status === 'running' || status === 'waiting'

/** System Design (Feature 4): one tab per design section, each drafted with AI, edited, saved and confirmed in order. */
export function DesignPage() {
  const { project } = useWorkspace()
  const design = useDesign(project.id)
  const [params, setParams] = useSearchParams()

  if (design.isPending) return <PageLoading label="Loading the design" />
  if (design.isError)
    return (
      <Notice tone="error" title="Couldn't load the design">
        {errorMessage(design.error)}
      </Notice>
    )

  const sections = design.data.sections
  const current = sections.find((s) => s.kind === params.get('tab')) ?? sections[0]
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      <StepHeading
        title="Design"
        description="Turn the confirmed requirements into a system design, one section at a time. Each section unlocks when the one before it is confirmed."
      />
      <div role="tablist" aria-label="Design sections" className="flex gap-1 border-b border-rule">
        {sections.map((s, i) => (
          <button
            key={s.kind}
            type="button"
            role="tab"
            id={`design-tab-${s.kind}`}
            aria-selected={current.kind === s.kind}
            aria-controls={`design-panel-${s.kind}`}
            disabled={s.locked}
            onClick={() => setParams(i === 0 ? {} : { tab: s.kind }, { replace: true })}
            className={cn(
              '-mb-px border-b-2 px-3 py-2 text-left text-sm font-medium disabled:cursor-not-allowed',
              current.kind === s.kind ? 'border-accent text-accent-deep' : 'border-transparent text-slate hover:text-ink',
            )}
          >
            {s.locked && <LockIcon className="mr-1 inline size-3" aria-hidden />}
            {s.title}
            {s.locked && <span className="block text-xs font-normal">Confirm {sections[i - 1].title} first.</span>}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`design-panel-${current.kind}`} aria-labelledby={`design-tab-${current.kind}`} className="min-h-0 flex-1 overflow-y-auto">
        {/* A new saved version (a save, a confirm or a finished AI draft) starts the editor again from the server's copy. */}
        <SectionPanel key={`${current.kind}:${current.version}:${current.status}`} projectId={project.id} section={current} />
      </div>
    </div>
  )
}

function SectionPanel({ projectId, section }: { projectId: string; section: DesignSection }) {
  const { project } = useWorkspace()
  const canEdit = project.role !== 'viewer'
  const statements = useStatements(projectId)
  const job = useDesignJob(projectId, section.job?.id)
  const start = useStartDesignDraft(projectId)
  const saveSection = useSaveDesignSection(projectId)
  const confirm = useConfirmDesignSection(projectId)
  const consent = useConsentRetry()
  const [draft, setDraft] = useState<Content | null>(null)
  const [asking, setAsking] = useState(false)

  const entry = EDITORS[section.kind]
  if (!entry) return <Notice tone="warning" title={section.title}>This version of the app cannot edit this section yet.</Notice>
  const { Editor, empty } = entry
  const dirty = draft !== null
  const busy = isActive(job.data?.status ?? section.job?.status)
  const title = section.title.toLowerCase()
  // An old failure stays on the section's job until the next draft; show it only if nothing was saved since.
  const failed = job.data?.status === 'failed' && (!section.updated_at || new Date(job.data.created_at!) > new Date(section.updated_at))
  const status = STATUS[section.status]

  const startDraft = () =>
    consent.run(() => start.mutateAsync(section.kind)).catch(() => undefined)

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h3 className="font-semibold">{section.title}</h3>
        <Badge tone={status.tone}>{status.label}</Badge>
        {canEdit && (
          <Button
            size="sm"
            variant="secondary"
            className="ml-auto"
            disabled={busy || start.isPending}
            onClick={() => (section.content || dirty ? setAsking(true) : void startDraft())}
          >
            <SparklesIcon /> Draft with AI
          </Button>
        )}
      </div>

      {section.stale && (
        <Notice tone="warning" title="Out of date">
          A requirement this section cites has changed since it was saved. Review the section and save it again before
          confirming.
        </Notice>
      )}
      {busy && job.data && <JobProgress job={job.data} title={`Drafting the ${title}`} />}
      {failed && (
        <Notice tone="error" title="The AI draft failed">
          {job.data?.error ?? 'Try again in a moment.'}
        </Notice>
      )}
      {[start, saveSection, confirm].map(
        (m, i) =>
          m.isError &&
          !isConsentError(m.error) && (
            <Notice key={i} tone="error">
              {errorMessage(m.error)}
            </Notice>
          ),
      )}

      <Editor
        content={draft ?? section.content ?? empty}
        derived={section.derived}
        dirty={dirty}
        disabled={!canEdit || busy}
        confirmed={section.status === 'confirmed'}
        requirements={statements.data ?? []}
        onChange={setDraft}
      />

      {canEdit && (
        <div className="flex flex-wrap items-center justify-end gap-3 border-t border-rule pt-4">
          {dirty && <span className="mr-auto text-sm text-slate">Save your changes before confirming, so what you confirm is what was saved.</span>}
          <Button
            variant="secondary"
            disabled={!dirty || busy || saveSection.isPending}
            onClick={() => saveSection.mutate({ kind: section.kind, content: draft! })}
          >
            <SaveIcon /> Save
          </Button>
          <Button
            disabled={dirty || busy || section.status === 'confirmed' || confirm.isPending}
            onClick={() => confirm.mutate(section.kind)}
          >
            <CheckIcon /> Confirm
          </Button>
        </div>
      )}

      <Dialog open={asking} onOpenChange={setAsking}>
        <DialogContent>
          <DialogTitle>Replace the {title}?</DialogTitle>
          <DialogDescription>
            The AI draft replaces what is in this section now{dirty && ', including your unsaved changes'}. It is saved
            as a draft for you to review.
          </DialogDescription>
          <DialogFooter>
            <Button variant="secondary" onClick={() => setAsking(false)}>
              Keep mine
            </Button>
            <Button
              onClick={() => {
                setAsking(false)
                void startDraft()
              }}
            >
              Replace
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      {consent.dialog}
    </div>
  )
}
