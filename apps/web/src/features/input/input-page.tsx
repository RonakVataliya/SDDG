import { useEffect, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router'
import { useQueryClient } from '@tanstack/react-query'
import { ApiError, errorMessage } from '@/api/errors'
import { keys, useConsent, useJob, useSubmitInput } from '@/api/queries'
import { JobProgress } from '@/components/job-progress'
import { Button } from '@/components/ui/button'
import { Label, Textarea } from '@/components/ui/input'
import { Notice } from '@/components/ui/notice'
import { Spinner } from '@/components/ui/spinner'
import { ConsentDialog } from '@/features/privacy/consent-dialog'
import { useWorkspace } from '@/routes/workspace-layout'
import { SAMPLE_REQUIREMENTS } from './sample'
import { CHARS_PER_PAGE, MAX_PROJECT_PAGES, pastedPageCount, plural } from '@/lib/utils'

const MAX_CHARS = CHARS_PER_PAGE * MAX_PROJECT_PAGES

export function InputPage() {
  const { project } = useWorkspace()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [text, setText] = useState('')
  const [consentOpen, setConsentOpen] = useState(false)
  const [renewal, setRenewal] = useState(false)
  const consent = useConsent()
  const submit = useSubmitInput(project.id)

  const extraction = project.extraction
  const running = extraction?.status === 'queued' || extraction?.status === 'running'
  // Remember the job once seen running: the project summary may report it finished before our own job poll
  // does, and we still want to see that finish to move on to review.
  const [watchedJobId, setWatchedJobId] = useState<string | null>(() => (running ? extraction.id : null))

  useEffect(() => {
    if (running && extraction?.id) {
      setWatchedJobId(extraction.id)
    }
  }, [running, extraction?.id])

  const activeJobId = watchedJobId || (running ? extraction?.id : null)
  const { data: job } = useJob(activeJobId)
  const liveJob = job ?? extraction

  // When the extraction we are watching finishes, refresh the project and move on to review.
  useEffect(() => {
    if (job?.status === 'succeeded') {
      void qc.invalidateQueries({ queryKey: keys.project(project.id) }).then(() => navigate('../review'))
    } else if (job?.status === 'failed') {
      void qc.invalidateQueries({ queryKey: keys.project(project.id) })
    }
  }, [job?.status, navigate, project.id, qc])

  const pages = pastedPageCount(text)
  const overLimit = text.length > MAX_CHARS

  async function send() {
    const job = await submit.mutateAsync(text).catch((e: unknown) => {
      // The server is the real gate (X8): if it says consent is missing or outdated, ask again.
      if (e instanceof ApiError && e.code === 'consent_required') {
        setRenewal(true)
        setConsentOpen(true)
        void consent.refetch()
      }
      return null
    })
    if (job) setText('')
  }

  function onExtract() {
    if (!consent.data?.consented) {
      setRenewal(!!consent.data?.policy_version) // agreed before, but to an older AI section
      setConsentOpen(true)
      return
    }
    void send()
  }

  if ((running || (job && job.status !== 'failed')) && liveJob) {
    return (
      <div className="space-y-4">
        <StepHeading title="Extracting modelling items" />
        <JobProgress job={liveJob} title="Reading your requirements" />
        <p className="text-sm text-slate">You can leave this page; extraction keeps running.</p>
      </div>
    )
  }

  return (
    <div className="space-y-5">
      <StepHeading
        title="Requirements"
        description="Type or paste functional and non-functional requirements, user stories, or SRS text. Each sentence becomes a numbered requirement statement."
      />

      {extraction?.status === 'failed' && (
        <Notice tone="error" title="The last extraction failed">
          {extraction.error ?? 'Try submitting the text again.'}
        </Notice>
      )}
      {extraction?.status === 'succeeded' && project.item_count === 0 && (
        <Notice tone="warning" title="No modelling items were found">
          Nothing in the text named an actor or an action. Add requirements written like &ldquo;The librarian shall
          issue a book to a member.&rdquo;
        </Notice>
      )}
      {project.statement_count > 0 && (
        <Notice title={`This project has ${plural(project.statement_count, 'requirement statement')}`}>
          Text you submit now is added as new statements. Your confirmation will be cleared, so you&rsquo;ll review the
          items again.
        </Notice>
      )}

      <div className="space-y-1.5">
        <div className="flex items-baseline justify-between gap-3">
          <Label htmlFor="requirements">Requirement text</Label>
          {!text && (
            <button type="button" className="text-sm text-teal hover:underline" onClick={() => setText(SAMPLE_REQUIREMENTS)}>
              Paste sample requirements
            </button>
          )}
        </div>
        <Textarea
          id="requirements"
          value={text}
          onChange={(e) => setText(e.target.value)}
          aria-invalid={overLimit}
          aria-describedby="requirements-count"
          placeholder={'FR1: The librarian shall be able to register a new member.\nFR2: A member can search the catalogue by title.'}
          className="min-h-72 font-sans"
        />
        <p id="requirements-count" className={overLimit ? 'text-sm text-danger' : 'text-xs text-slate tabular-nums'}>
          {text.length.toLocaleString()} characters · counts as {pages} of {MAX_PROJECT_PAGES} pages
          {overLimit && '. That is over the project limit; shorten the text.'}
        </p>
      </div>

      {submit.isError && !(submit.error instanceof ApiError && submit.error.code === 'consent_required') && (
        <Notice tone="error" title="Couldn't submit the requirements">
          {errorMessage(submit.error)}
        </Notice>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <Button size="lg" disabled={!text.trim() || overLimit || submit.isPending || consent.isPending} onClick={onExtract}>
          {submit.isPending && <Spinner className="text-white" label="Submitting" />}
          Extract items
        </Button>
        {consent.data?.consented && (
          <span className="text-xs text-slate">Text is sent to Google Gemini for extraction.</span>
        )}
      </div>

      <ConsentDialog open={consentOpen} onOpenChange={setConsentOpen} onConsented={send} renewal={renewal} />
    </div>
  )
}

export function StepHeading({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div className="max-w-2xl">
        <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
        {description && <p className="mt-1 text-slate">{description}</p>}
      </div>
      {actions}
    </div>
  )
}
