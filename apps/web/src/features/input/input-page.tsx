import { ArrowRightIcon, CheckIcon, FlagIcon, RefreshCwIcon, ShieldCheckIcon } from 'lucide-react'
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
import { cn, MAX_PROJECT_PAGES, pastedPageCount, plural } from '@/lib/utils'
import { SAMPLE_REQUIREMENTS } from './sample'

/** Server limit for one submission (the API answers 422 above it). */
export const MAX_CHARS = 300_000

const HOW = [
  ['Find requirements', 'The AI splits your text into numbered requirements and flags vague ones. Takes a few seconds.'],
  ['You review and confirm', 'Edit, add or delete anything. Nothing is drawn until you confirm.'],
  ['Pick diagrams', 'The AI then extracts only what those diagrams need, and draws them.'],
]

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
  const running = extraction?.status === 'queued' || extraction?.status === 'running' || extraction?.status === 'waiting'
  // Remember the job once seen running: the project summary may report it finished before our own job poll
  // does, and we still want to see that finish to move on to review.
  const [watchedJobId, setWatchedJobId] = useState<string | null>(() => (running ? extraction.id : null))

  useEffect(() => {
    if (running && extraction?.id) setWatchedJobId(extraction.id)
  }, [running, extraction?.id])

  const activeJobId = watchedJobId || (running ? extraction?.id : null)
  const { data: job } = useJob(activeJobId)
  const liveJob = job ?? extraction

  // When the extraction we are watching finishes, refresh the project and move on to review.
  useEffect(() => {
    if (job?.status === 'succeeded') {
      setText('')
      void qc.invalidateQueries({ queryKey: keys.project(project.id) }).then(() => navigate('../review'))
    } else if (job?.status === 'failed') {
      void qc.invalidateQueries({ queryKey: keys.project(project.id) })
    }
  }, [job?.status, navigate, project.id, qc])

  const overLimit = text.length > MAX_CHARS
  const pages = pastedPageCount(text)
  const overProject = pages > MAX_PROJECT_PAGES

  async function send() {
    setWatchedJobId(null)
    await submit.mutateAsync(text).catch((e: unknown) => {
      // The server is the real gate (X8): if it says consent is missing or outdated, ask again, then retry.
      if (e instanceof ApiError && e.code === 'consent_required') {
        setRenewal(true)
        setConsentOpen(true)
        void consent.refetch()
      }
      return null
    })
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
      <div className="mx-auto grid w-full max-w-[1400px] gap-6 p-4 sm:p-7 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div className="self-start">
          <JobProgress job={liveJob} title="Finding your requirements" />
        </div>
        <Side>
          <p className="text-[13px] text-slate">You can leave this page; it keeps running, and your requirements will be ready to review when you come back.</p>
        </Side>
      </div>
    )
  }

  const failed = extraction?.status === 'failed'
  return (
    <div className="mx-auto grid w-full max-w-[1400px] flex-1 gap-6 p-4 sm:p-7 lg:grid-cols-[minmax(0,1fr)_380px]">
      <div className="flex min-h-0 flex-col gap-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold">Add requirements</h2>
            <p className="mt-1 text-[13px] text-slate">Paste functional and non-functional requirements, user stories or SRS text.</p>
          </div>
        </div>

        {failed && (
          <Notice tone="error" title="Finding requirements stopped">
            {extraction.error ?? 'Try submitting the text again.'} {text ? 'Your text is still below.' : ''}
          </Notice>
        )}
        {extraction?.status === 'succeeded' && project.statement_count === 0 && (
          <Notice tone="warning" title="No requirements were found">
            Write them as sentences, one per line, like &ldquo;The librarian shall issue a book to a member.&rdquo;
          </Notice>
        )}
        {project.statement_count > 0 && (
          <Notice title={`This project already has ${plural(project.statement_count, 'requirement')}`}>
            New text is added to them as new requirements; nothing is replaced. You&rsquo;ll review and confirm the list again
            afterwards.
          </Notice>
        )}

            {overLimit && (
              <Notice tone="error" title={`This is ${(text.length - MAX_CHARS).toLocaleString()} characters over the ${MAX_CHARS.toLocaleString()} limit.`}>
                Split it into two submissions; the second one adds to the first.
              </Notice>
            )}
            {!overLimit && overProject && (
              <Notice tone="error" title="Over the page limit">
                This text counts as {plural(pages, 'page')}; one submission can be at most {MAX_PROJECT_PAGES} pages.
              </Notice>
            )}
            {submit.isError && !(submit.error instanceof ApiError && submit.error.code === 'consent_required') && (
              <Notice tone="error" title="Couldn't submit the requirements">
                {errorMessage(submit.error)}
              </Notice>
            )}

            <div className={cn('ticks flex min-h-[420px] flex-1 flex-col rounded-xl border border-rule bg-field', (overLimit || overProject) && 'border-danger')}>
              <div className="flex items-center justify-between gap-3 border-b border-rule px-4 py-2.5">
                <Label htmlFor="requirements">Requirement text</Label>
                {!text && (
                  <button type="button" className="text-[13px] font-medium text-accent hover:underline" onClick={() => setText(SAMPLE_REQUIREMENTS)}>
                    Paste sample requirements
                  </button>
                )}
              </div>
              <Textarea
                id="requirements"
                value={text}
                onChange={(e) => setText(e.target.value)}
                aria-invalid={overLimit || overProject}
                aria-describedby="requirements-count"
                placeholder={'FR1: The librarian shall be able to register a new member.\nUS-2: As a member, I want to search the catalogue so that I can find a book.'}
                className="min-h-0 flex-1 resize-none rounded-none border-0 bg-transparent px-5 py-4 leading-7 focus-visible:ring-0"
              />
              <div className="flex flex-wrap items-center gap-3 border-t border-rule px-4 py-3">
                <span id="requirements-count" className={cn('font-mono text-[11.5px]', overLimit || overProject ? 'text-danger' : 'text-slate')}>
                  {text.length.toLocaleString()} / {MAX_CHARS.toLocaleString()} characters · counts as {pages} of {MAX_PROJECT_PAGES} pages
                  {text.length > 0 && !overLimit && !overProject && ` · ${plural(MAX_PROJECT_PAGES - pages, 'page')} remaining`}
                </span>
                {consent.data?.consented && (
                  <span className="ml-auto flex items-center gap-1.5 text-[11.5px] text-slate">
                    <ShieldCheckIcon className="size-3.5" /> AI consent given
                  </span>
                )}
                <Button
                  className={cn(!consent.data?.consented && 'ml-auto')}
                  disabled={!text.trim() || overLimit || overProject || submit.isPending || consent.isPending}
                  onClick={onExtract}
                >
                  {submit.isPending ? <Spinner className="text-on-ink" label="Submitting" /> : failed && text ? <RefreshCwIcon /> : null}
                  {failed && text ? 'Try again' : 'Extract requirements'}
                  {!submit.isPending && !(failed && text) && <ArrowRightIcon />}
                </Button>
              </div>
            </div>
      </div>
      <Side />
      <ConsentDialog open={consentOpen} onOpenChange={setConsentOpen} onConsented={() => void send()} renewal={renewal} />
    </div>
  )
}

function Side({ children }: { children?: ReactNode }) {
  return (
    <aside className="space-y-4 self-start">
      <div className="rounded-xl border border-rule bg-surface p-5">
        <h3 className="font-sans text-[15px] font-semibold tracking-normal">How this works</h3>
        <ol className="mt-3 space-y-3">
          {HOW.map(([t, d], i) => (
            <li key={t} className="flex gap-3">
              <span className={cn('grid size-6 shrink-0 place-items-center rounded-full border-[1.5px] border-rule-strong font-mono text-[11px]', i === 0 && 'border-accent bg-accent text-on-ink')}>
                {i + 1}
              </span>
              <span>
                <span className="block text-[13px] font-semibold">{t}</span>
                <span className="block text-[12px] text-slate">{d}</span>
              </span>
            </li>
          ))}
        </ol>
        {children && <div className="mt-4 border-t border-rule pt-4">{children}</div>}
      </div>
      <div className="rounded-xl border border-rule bg-surface p-5">
        <h3 className="font-sans text-[15px] font-semibold tracking-normal">Write requirements that extract well</h3>
        <ul className="mt-3 space-y-2 text-[13px] text-ink-2">
          <li className="flex gap-2"><CheckIcon className="mt-0.5 size-3.5 shrink-0" /> <span>Name who does what: <i>“The librarian shall issue a book.”</i></span></li>
          <li className="flex gap-2"><CheckIcon className="mt-0.5 size-3.5 shrink-0" /> One requirement per line or sentence.</li>
          <li className="flex gap-2"><FlagIcon className="mt-0.5 size-3.5 shrink-0" /> Vague words like “quickly” get flagged so you can fix them in Review.</li>
        </ul>
      </div>
    </aside>
  )
}

export function StepHeading({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div className="max-w-2xl">
        <h2 className="text-xl font-semibold">{title}</h2>
        {description && <p className="mt-1 text-[13px] text-slate">{description}</p>}
      </div>
      {actions}
    </div>
  )
}
