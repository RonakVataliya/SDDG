import {
  AlertTriangleIcon,
  ArrowRightIcon,
  CheckIcon,
  FileTextIcon,
  FlagIcon,
  RefreshCwIcon,
  ShieldCheckIcon,
  Trash2Icon,
  UploadIcon,
} from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router'
import { useQueryClient } from '@tanstack/react-query'
import type { ProjectDocument } from '@/api/client'
import { ApiError, errorMessage } from '@/api/errors'
import { keys, useConsent, useDeleteDocument, useDocuments, useJob, useSubmitInput, useUploadDocument } from '@/api/queries'
import { JobProgress } from '@/components/job-progress'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogTitle } from '@/components/ui/dialog'
import { Label, Textarea } from '@/components/ui/input'
import { Notice } from '@/components/ui/notice'
import { Spinner } from '@/components/ui/spinner'
import { ConsentDialog } from '@/features/privacy/consent-dialog'
import { useWorkspace } from '@/routes/workspace-layout'
import { cn, formatBytes, MAX_DOCUMENTS_PER_PROJECT, MAX_FILE_BYTES, MAX_PROJECT_PAGES, pastedPageCount, plural } from '@/lib/utils'
import { SAMPLE_REQUIREMENTS, SAMPLE_USER_STORIES } from './sample'

/** Server limit for one submission (the API answers 422 above it). */
export const MAX_CHARS = 300_000

const HOW = [
  ['Find requirements', 'The AI splits your text or document into numbered requirements and flags vague ones. Takes a few seconds.'],
  ['You review and confirm', 'Edit, add or delete anything. Nothing is drawn until you confirm.'],
  ['Pick diagrams', 'The AI then extracts only what those diagrams need, and draws them.'],
]

export function InputPage() {
  const { project } = useWorkspace()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [activeTab, setActiveTab] = useState<'paste' | 'upload'>('paste')
  const [text, setText] = useState('')
  const [consentOpen, setConsentOpen] = useState(false)
  const [renewal, setRenewal] = useState(false)
  const [pendingFile, setPendingFile] = useState<File | null>(null)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const [deletingDoc, setDeletingDoc] = useState<ProjectDocument | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const consent = useConsent()
  const submit = useSubmitInput(project.id)
  const documentsQuery = useDocuments(project.id)
  const uploadDoc = useUploadDocument(project.id)
  const deleteDoc = useDeleteDocument(project.id)

  const documents = documentsQuery.data ?? []
  const totalDocumentPages = documents.reduce((acc, d) => acc + d.page_count, 0)

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

  // When the pasted-text extraction we are watching finishes, refresh the project and move on to review.
  // A document extraction stays on this page so the document list shows its result.
  useEffect(() => {
    if (activeTab === 'paste' && job?.status === 'succeeded') {
      setText('')
      void qc.invalidateQueries({ queryKey: keys.project(project.id) }).then(() => navigate('../review'))
    } else if (job?.status === 'succeeded' || job?.status === 'failed') {
      void qc.invalidateQueries({ queryKey: keys.project(project.id) })
    }
  }, [activeTab, job?.status, navigate, project.id, qc])

  const overLimit = text.length > MAX_CHARS
  const pages = pastedPageCount(text)
  // FR3: uploaded documents use up part of the project's 100 pages.
  const remainingProjectPages = Math.max(0, MAX_PROJECT_PAGES - totalDocumentPages)
  const overProject = pages > remainingProjectPages
  const formatWarning = checkFormatWarnings(text)

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

  async function performUpload(file: File) {
    setUploadError(null)
    const err = validateFile(file, documents.length, totalDocumentPages)
    if (err) {
      setUploadError(err)
      return
    }
    try {
      const res = await uploadDoc.mutateAsync(file)
      if (res?.job?.id) setWatchedJobId(res.job.id)
      if (fileInputRef.current) fileInputRef.current.value = ''
    } catch (e: unknown) {
      if (e instanceof ApiError && e.code === 'consent_required') {
        setPendingFile(file)
        setRenewal(true)
        setConsentOpen(true)
        void consent.refetch()
      } else {
        setUploadError(errorMessage(e))
      }
    }
  }

  function pickFile(file: File | undefined) {
    if (!file) return
    setUploadError(null)
    const err = validateFile(file, documents.length, totalDocumentPages)
    if (err) {
      setUploadError(err)
      return
    }
    if (consent.data && !consent.data.consented) {
      setPendingFile(file)
      setRenewal(!!consent.data.policy_version)
      setConsentOpen(true)
      return
    }
    void performUpload(file)
  }

  function onConsented() {
    if (pendingFile) {
      const f = pendingFile
      setPendingFile(null)
      void performUpload(f)
    } else {
      void send()
    }
  }

  async function handleDeleteConfirm() {
    if (!deletingDoc) return
    const id = deletingDoc.id
    setDeletingDoc(null)
    await deleteDoc.mutateAsync(id).catch(() => null)
  }

  if (activeTab === 'paste' && (running || (job && job.status !== 'failed')) && liveJob) {
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

  const failed = extraction?.status === 'failed' || job?.status === 'failed'
  const tabClass = (tab: 'paste' | 'upload') =>
    cn(
      'border-b-2 px-4 py-2 text-[13px] font-medium transition-colors',
      activeTab === tab ? 'border-accent text-accent' : 'border-transparent text-slate hover:border-rule-strong hover:text-ink',
    )

  return (
    <div className="mx-auto grid w-full max-w-[1400px] flex-1 gap-6 p-4 sm:p-7 lg:grid-cols-[minmax(0,1fr)_380px]">
      <div className="flex min-h-0 flex-col gap-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold">Add requirements</h2>
            <p className="mt-1 text-[13px] text-slate">
              Paste functional and non-functional requirements, user stories or SRS text, or upload an SRS document (PDF/DOCX).
            </p>
          </div>
        </div>

        {failed && (
          <Notice tone="error" title="Finding requirements stopped">
            {job?.error ?? extraction?.error ?? 'Try submitting the text or document again.'} {text ? 'Your text is still below.' : ''}
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

        {/* FR3: project document and page capacity */}
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-rule bg-surface px-4 py-2.5 text-[12px] text-slate">
          <span>
            Project documents: <strong className="font-semibold text-ink">{documents.length}</strong> of {MAX_DOCUMENTS_PER_PROJECT} max
          </span>
          <span>
            Project pages: <strong className="font-semibold text-ink">{totalDocumentPages}</strong> of {MAX_PROJECT_PAGES} max (
            {remainingProjectPages} pages remaining)
          </span>
        </div>

        <div className="flex border-b border-rule" role="tablist" aria-label="Input methods">
          <button type="button" role="tab" aria-selected={activeTab === 'paste'} onClick={() => setActiveTab('paste')} className={tabClass('paste')}>
            Paste requirements
          </button>
          <button type="button" role="tab" aria-selected={activeTab === 'upload'} onClick={() => setActiveTab('upload')} className={tabClass('upload')}>
            Upload SRS document (PDF / DOCX)
          </button>
        </div>

        {activeTab === 'paste' && (
          <>
            {overLimit && (
              <Notice tone="error" title={`This is ${(text.length - MAX_CHARS).toLocaleString()} characters over the ${MAX_CHARS.toLocaleString()} limit.`}>
                Split it into two submissions; the second one adds to the first.
              </Notice>
            )}
            {!overLimit && overProject && (
              <Notice tone="error" title="Over the page limit">
                This text counts as {plural(pages, 'page')}; the project has {plural(remainingProjectPages, 'page')} left of{' '}
                {MAX_PROJECT_PAGES}.
              </Notice>
            )}
            {formatWarning.warning && (
              <Notice tone="warning" title="Input format notice">
                {formatWarning.warning}
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
                  <span className="flex items-center gap-3">
                    <button type="button" className="text-[13px] font-medium text-accent hover:underline" onClick={() => setText(SAMPLE_REQUIREMENTS)}>
                      Paste sample requirements
                    </button>
                    <span className="text-rule-strong">·</span>
                    <button type="button" className="text-[13px] font-medium text-accent hover:underline" onClick={() => setText(SAMPLE_USER_STORIES)}>
                      Paste user stories sample
                    </button>
                  </span>
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
                  {text.length > 0 && !overLimit && !overProject && ` · ${plural(remainingProjectPages - pages, 'page')} remaining`}
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
          </>
        )}

        {activeTab === 'upload' && (
          <div className="space-y-4">
            <div
              onDragOver={(e) => {
                e.preventDefault()
                setDragOver(true)
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault()
                setDragOver(false)
                pickFile(e.dataTransfer.files?.[0])
              }}
              className={cn(
                'flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-8 text-center transition-colors',
                dragOver ? 'border-accent bg-accent-wash' : 'border-rule-strong bg-surface hover:border-accent',
              )}
            >
              <div className="grid size-12 place-items-center rounded-full bg-paper text-accent">
                <UploadIcon className="size-6" />
              </div>
              <h3 className="mt-3 font-sans text-[15px] font-medium tracking-normal">Choose a file or drag and drop it here</h3>
              <p className="mt-1 text-[12px] text-slate">
                Supported file types: <strong>PDF (.pdf)</strong> and <strong>Word DOCX (.docx)</strong>
              </p>
              <p className="mt-0.5 text-[12px] text-slate">
                Maximum file size: <strong>10 MiB (10 × 1,048,576 bytes)</strong>
              </p>
              <div className="mt-4">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                  onChange={(e) => pickFile(e.target.files?.[0])}
                  className="hidden"
                  id="file-upload"
                />
                <Button
                  variant="secondary"
                  disabled={uploadDoc.isPending || documents.length >= MAX_DOCUMENTS_PER_PROJECT || totalDocumentPages >= MAX_PROJECT_PAGES}
                  onClick={() => fileInputRef.current?.click()}
                >
                  {uploadDoc.isPending && <Spinner label="Uploading" />}
                  Select document
                </Button>
              </div>
              {documents.length >= MAX_DOCUMENTS_PER_PROJECT && (
                <p className="mt-2 text-[12px] text-danger">Project limit reached: {MAX_DOCUMENTS_PER_PROJECT} documents maximum.</p>
              )}
              {totalDocumentPages >= MAX_PROJECT_PAGES && (
                <p className="mt-2 text-[12px] text-danger">Project limit reached: {MAX_PROJECT_PAGES} total pages maximum.</p>
              )}
              {consent.data?.consented && (
                <p className="mt-3 flex items-center gap-1.5 text-[11.5px] text-slate">
                  <ShieldCheckIcon className="size-3.5" /> AI consent given
                </p>
              )}
            </div>

            {uploadError && (
              <Notice tone="error" title="Upload rejected">
                {uploadError}
              </Notice>
            )}
            {uploadDoc.isError && !(uploadDoc.error instanceof ApiError && uploadDoc.error.code === 'consent_required') && (
              <Notice tone="error" title="Document upload failed">
                {errorMessage(uploadDoc.error)}
              </Notice>
            )}
            {liveJob && (running || (job && (job.status === 'queued' || job.status === 'running' || job.status === 'waiting'))) && (
              <div className="rounded-xl border border-rule bg-surface p-4">
                <JobProgress job={liveJob} title="Finding requirements in your document" />
                <p className="mt-2 text-[12px] text-slate">You can leave this page; extraction keeps running.</p>
              </div>
            )}
          </div>
        )}

        {documents.length > 0 && (
          <div className="space-y-3 pt-1">
            <div className="flex items-center justify-between">
              <h3 className="font-sans text-[14px] font-semibold tracking-normal">Uploaded project documents</h3>
              <span className="text-[12px] text-slate">
                {plural(documents.length, 'document')} · {plural(totalDocumentPages, 'page')}
              </span>
            </div>
            <div className="divide-y divide-rule rounded-xl border border-rule bg-surface">
              {documents.map((doc) => (
                <div key={doc.id} className="p-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <div className="grid size-9 shrink-0 place-items-center rounded-md bg-paper text-slate">
                        <FileTextIcon className="size-5" />
                      </div>
                      <div>
                        <p className="text-[13.5px] font-medium">{doc.filename}</p>
                        <p className="text-[12px] text-slate">
                          {plural(doc.page_count, 'page')} · {formatBytes(doc.size_bytes)}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <StatusBadge status={doc.status} />
                      <Button
                        variant="ghost"
                        size="icon"
                        className="size-7 text-slate hover:text-danger"
                        onClick={() => setDeletingDoc(doc)}
                        aria-label={`Delete ${doc.filename}`}
                      >
                        <Trash2Icon className="size-3.5" />
                      </Button>
                    </div>
                  </div>
                  {doc.warning && (
                    <div className="mt-2 flex items-start gap-2 rounded-md bg-amber-wash p-2 text-[12px] text-amber">
                      <AlertTriangleIcon className="mt-0.5 size-3.5 shrink-0" />
                      <span>{doc.warning}</span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
      <Side />

      <Dialog open={Boolean(deletingDoc)} onOpenChange={(open) => !open && setDeletingDoc(null)}>
        <DialogContent>
          <DialogTitle>Delete document</DialogTitle>
          <DialogDescription>
            Are you sure you want to delete &ldquo;{deletingDoc?.filename}&rdquo;? This removes the file and its record.
            Requirements already found in it stay in the project.
          </DialogDescription>
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="secondary">Cancel</Button>
            </DialogClose>
            <Button variant="danger" onClick={handleDeleteConfirm} disabled={deleteDoc.isPending}>
              {deleteDoc.isPending && <Spinner label="Deleting" className="text-on-ink" />}
              Delete document
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConsentDialog open={consentOpen} onOpenChange={setConsentOpen} onConsented={onConsented} renewal={renewal} />
    </div>
  )
}

function StatusBadge({ status }: { status: ProjectDocument['status'] }) {
  if (status === 'processing') {
    return (
      <Badge tone="amber">
        <Spinner className="size-3 text-amber" />
        Processing
      </Badge>
    )
  }
  if (status === 'processed') {
    return <Badge tone="success">Extracted</Badge>
  }
  if (status === 'failed') {
    return <Badge tone="danger">Failed</Badge>
  }
  return <Badge tone="neutral">Uploaded</Badge>
}

function validateFile(
  file: File,
  currentDocCount: number,
  currentTotalPages: number,
): string | null {
  const name = file.name || ''
  const ext = name.slice(name.lastIndexOf('.')).toLowerCase()
  if (ext !== '.pdf' && ext !== '.docx') {
    return 'Unsupported file type. Supported file types are PDF (.pdf) and DOCX (.docx).'
  }

  if (file.size > MAX_FILE_BYTES) {
    return `File size is ${(file.size / (1024 * 1024)).toFixed(2)} MB (${file.size.toLocaleString()} bytes); the maximum allowed size is 10 MB (10 × 1,048,576 bytes).`
  }

  if (currentDocCount >= MAX_DOCUMENTS_PER_PROJECT) {
    return `This project has reached the maximum limit of ${MAX_DOCUMENTS_PER_PROJECT} documents. Delete an existing document before uploading a new one.`
  }

  if (currentTotalPages >= MAX_PROJECT_PAGES) {
    return `This project has reached the maximum limit of ${MAX_PROJECT_PAGES} document pages. Delete existing documents before uploading more.`
  }

  return null
}

function checkFormatWarnings(text: string): { warning: string | null } {
  if (!text.trim()) return { warning: null }
  const lines = text
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)
  if (lines.length === 0) return { warning: null }

  // Same patterns as FR_NFR_RE / USER_STORY_RE in apps/api/core/input_processing.py.
  const frNfr = /^(?:FR|NFR)[-_\s]*\d+/i
  const hasFrNfr = lines.some((l) => frNfr.test(l))
  if (hasFrNfr) {
    const unnumbered = lines.filter((l) => !frNfr.test(l))
    if (unnumbered.length > 0) {
      return {
        warning: `Some lines do not have numbered FR/NFR IDs. The input will be accepted as free text; IDs could not be preserved for those lines.`,
      }
    }
    return { warning: null }
  }

  const hasStory = lines.some((l) => /^As\s+an?\s+/i.test(l))
  if (hasStory) {
    const storyRegex = /^As\s+an?\s+.+?,?\s+I\s+want\s+.+?,?\s+so\s+that\s+.+?[.!]?$/i
    const malformed = lines.filter((l) => !storyRegex.test(l))
    if (malformed.length > 0) {
      return {
        warning: `Some user stories did not match the 'As a … I want … so that …' pattern. They were retained as unstructured free-text requirements.`,
      }
    }
    return { warning: null }
  }

  return { warning: null }
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
