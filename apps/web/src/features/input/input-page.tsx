import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router'
import { useQueryClient } from '@tanstack/react-query'
import { AlertTriangleIcon, FileTextIcon, Trash2Icon, UploadIcon } from 'lucide-react'
import type { ProjectDocument } from '@/api/client'
import { ApiError, errorMessage } from '@/api/errors'
import {
  keys,
  useConsent,
  useDeleteDocument,
  useDocuments,
  useJob,
  useSubmitInput,
  useUploadDocument,
} from '@/api/queries'
import { JobProgress } from '@/components/job-progress'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label, Textarea } from '@/components/ui/input'
import { Notice } from '@/components/ui/notice'
import { Spinner } from '@/components/ui/spinner'
import { ConsentDialog } from '@/features/privacy/consent-dialog'
import {
  CHARS_PER_PAGE,
  MAX_DOCUMENTS_PER_PROJECT,
  MAX_FILE_BYTES,
  MAX_PROJECT_PAGES,
  formatBytes,
  pastedPageCount,
  plural,
} from '@/lib/utils'
import { useWorkspace } from '@/routes/workspace-layout'
import { SAMPLE_REQUIREMENTS, SAMPLE_USER_STORIES } from './sample'

const MAX_CHARS = CHARS_PER_PAGE * MAX_PROJECT_PAGES

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
  const running = extraction?.status === 'queued' || extraction?.status === 'running'
  const [watchedJobId, setWatchedJobId] = useState<string | null>(() => (running ? extraction.id : null))

  useEffect(() => {
    if (running && extraction?.id) {
      setWatchedJobId(extraction.id)
    }
  }, [running, extraction?.id])

  const activeJobId = watchedJobId || (running ? extraction?.id : null)
  const { data: job } = useJob(activeJobId)
  const liveJob = job ?? extraction

  useEffect(() => {
    if (activeTab === 'paste' && job?.status === 'succeeded') {
      void qc.invalidateQueries({ queryKey: keys.project(project.id) }).then(() => navigate('../review'))
    } else if (job?.status === 'failed') {
      void qc.invalidateQueries({ queryKey: keys.project(project.id) })
    }
  }, [activeTab, job?.status, navigate, project.id, qc])

  const pages = pastedPageCount(text)
  const overTextLimit = text.length > MAX_CHARS
  const remainingProjectPages = Math.max(0, MAX_PROJECT_PAGES - totalDocumentPages)
  const overProjectLimit = pages > remainingProjectPages

  // Format checks for User Stories and FR/NFR
  const formatWarning = checkFormatWarnings(text)

  async function sendText() {
    const job = await submit.mutateAsync(text).catch((e: unknown) => {
      if (e instanceof ApiError && e.code === 'consent_required') {
        setRenewal(true)
        setConsentOpen(true)
        void consent.refetch()
      }
      return null
    })
    if (job) {
      setText('')
      setWatchedJobId(job.id)
    }
  }

  function onExtract() {
    if (!text.trim()) return
    if (!consent.data?.consented) {
      setRenewal(!!consent.data?.policy_version)
      setConsentOpen(true)
      return
    }
    void sendText()
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
      if (res?.job?.id) {
        setWatchedJobId(res.job.id)
      }
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
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

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploadError(null)
    const err = validateFile(file, documents.length, totalDocumentPages)
    if (err) {
      setUploadError(err)
      return
    }
    if (consent.data && !consent.data.consented) {
      setPendingFile(file)
      setRenewal(!!consent.data?.policy_version)
      setConsentOpen(true)
      return
    }
    void performUpload(file)
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files?.[0]
    if (!file) return
    setUploadError(null)
    const err = validateFile(file, documents.length, totalDocumentPages)
    if (err) {
      setUploadError(err)
      return
    }
    if (consent.data && !consent.data.consented) {
      setPendingFile(file)
      setRenewal(!!consent.data?.policy_version)
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
      void sendText()
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
      <div className="space-y-4">
        <StepHeading title="Extracting modelling items" />
        <JobProgress job={liveJob} title="Reading your requirements" />
        <p className="text-sm text-slate">You can leave this page; extraction keeps running.</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <StepHeading
        title="Requirements"
        description="Provide functional and non-functional requirements, user stories, or upload SRS documents (PDF/DOCX). Each requirement is analyzed and extracted into modelling statements."
      />

      {(extraction?.status === 'failed' || job?.status === 'failed') && (
        <Notice tone="error" title="The last extraction failed">
          {job?.error ?? extraction?.error ?? 'Try submitting the requirements or document again.'}
        </Notice>
      )}

      {extraction?.status === 'succeeded' && project.item_count === 0 && (
        <Notice tone="warning" title="No modelling items were found">
          Nothing in the input named an actor or an action. Add requirements written like &ldquo;The librarian shall
          issue a book to a member.&rdquo;
        </Notice>
      )}

      {project.statement_count > 0 && (
        <Notice title={`This project has ${plural(project.statement_count, 'requirement statement')}`}>
          Requirements you submit now are added as new statements. Your confirmation will be cleared, so you&rsquo;ll review the
          items again.
        </Notice>
      )}

      {/* Project Document & Page Capacity Tracker (FR3) */}
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-rule bg-surface px-4 py-2.5 text-xs text-slate">
        <span>
          Project documents: <strong className="font-semibold text-ink">{documents.length}</strong> of{' '}
          {MAX_DOCUMENTS_PER_PROJECT} max
        </span>
        <span>
          Project pages: <strong className="font-semibold text-ink">{totalDocumentPages}</strong> of{' '}
          {MAX_PROJECT_PAGES} max ({remainingProjectPages} pages remaining)
        </span>
      </div>

      {/* Mode Switcher Tabs */}
      <div className="flex border-b border-rule" role="tablist" aria-label="Input methods">
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'paste'}
          onClick={() => setActiveTab('paste')}
          className={`border-b-2 px-4 py-2 text-sm font-medium transition-colors ${
            activeTab === 'paste'
              ? 'border-teal text-teal'
              : 'border-transparent text-slate hover:border-rule-strong hover:text-ink'
          }`}
        >
          Paste requirements
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'upload'}
          onClick={() => setActiveTab('upload')}
          className={`border-b-2 px-4 py-2 text-sm font-medium transition-colors ${
            activeTab === 'upload'
              ? 'border-teal text-teal'
              : 'border-transparent text-slate hover:border-rule-strong hover:text-ink'
          }`}
        >
          Upload SRS document (PDF / DOCX)
        </button>
      </div>

      {/* TAB 1: PASTE REQUIREMENTS */}
      {activeTab === 'paste' && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-baseline justify-between gap-3">
            <Label htmlFor="requirements">Requirement text</Label>
            <div className="flex items-center gap-3 text-xs">
              <button
                type="button"
                className="text-teal hover:underline"
                onClick={() => setText(SAMPLE_REQUIREMENTS)}
              >
                Paste FR/NFR sample
              </button>
              <span className="text-rule-strong">·</span>
              <button
                type="button"
                className="text-teal hover:underline"
                onClick={() => setText(SAMPLE_USER_STORIES)}
              >
                Paste user stories sample
              </button>
            </div>
          </div>

          <Textarea
            id="requirements"
            value={text}
            onChange={(e) => setText(e.target.value)}
            aria-invalid={overTextLimit || overProjectLimit}
            aria-describedby="requirements-count"
            placeholder={
              'FR1: The librarian shall be able to register a new member.\n' +
              'FR2: A member can search the catalogue by title.\n\n' +
              '— or user stories —\n' +
              'As a librarian, I want to register a new member, so that they can borrow books.'
            }
            className="min-h-64 font-sans"
          />

          <p
            id="requirements-count"
            className={
              overTextLimit || overProjectLimit ? 'text-sm text-danger' : 'text-xs text-slate tabular-nums'
            }
          >
            {text.length.toLocaleString()} characters · counts as {pages} of {MAX_PROJECT_PAGES} pages
            {overTextLimit && '. Input exceeds 100 pages (300,000 characters); shorten the text.'}
            {!overTextLimit &&
              overProjectLimit &&
              `. Adding this text (${pages} pages) exceeds the remaining project capacity (${remainingProjectPages} pages available).`}
          </p>

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

          <div className="flex flex-wrap items-center gap-3 pt-1">
            <Button
              size="lg"
              disabled={!text.trim() || overTextLimit || overProjectLimit || submit.isPending || consent.isPending}
              onClick={onExtract}
            >
              {submit.isPending && <Spinner className="text-white" label="Submitting" />}
              Extract items
            </Button>
            {consent.data?.consented && (
              <span className="text-xs text-slate">Requirements are sent to Groq for extraction.</span>
            )}
          </div>
        </div>
      )}

      {/* TAB 2: UPLOAD SRS DOCUMENT */}
      {activeTab === 'upload' && (
        <div className="space-y-4">
          <div
            onDragOver={(e) => {
              e.preventDefault()
              setDragOver(true)
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            className={`flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 text-center transition-colors ${
              dragOver
                ? 'border-teal bg-teal-wash/30'
                : 'border-rule-strong bg-surface hover:border-teal/60'
            }`}
          >
            <div className="grid size-12 place-items-center rounded-full bg-paper text-teal">
              <UploadIcon className="size-6" />
            </div>
            <h3 className="mt-3 text-base font-medium text-ink">Choose a file or drag and drop it here</h3>
            <p className="mt-1 text-xs text-slate">
              Supported file types: <strong>PDF (.pdf)</strong> and <strong>Word DOCX (.docx)</strong>
            </p>
            <p className="mt-0.5 text-xs text-slate">
              Maximum file size: <strong>10 MiB (10 × 1,048,576 bytes)</strong>
            </p>

            <div className="mt-4">
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                onChange={handleFileSelect}
                className="hidden"
                id="file-upload"
              />
              <Button
                variant="secondary"
                size="md"
                disabled={
                  uploadDoc.isPending ||
                  documents.length >= MAX_DOCUMENTS_PER_PROJECT ||
                  totalDocumentPages >= MAX_PROJECT_PAGES
                }
                onClick={() => fileInputRef.current?.click()}
              >
                {uploadDoc.isPending && <Spinner label="Uploading" />}
                Select document
              </Button>
            </div>

            {documents.length >= MAX_DOCUMENTS_PER_PROJECT && (
              <p className="mt-2 text-xs text-danger">Project limit reached: 15 documents maximum.</p>
            )}
            {totalDocumentPages >= MAX_PROJECT_PAGES && (
              <p className="mt-2 text-xs text-danger">Project limit reached: 100 total pages maximum.</p>
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

          {liveJob && (running || (job && (job.status === 'queued' || job.status === 'running'))) && (
            <div className="rounded-md border border-rule bg-surface p-4">
              <JobProgress job={liveJob} title="Processing uploaded document requirements" />
              <p className="mt-2 text-xs text-slate">You can leave this page; extraction keeps running.</p>
            </div>
          )}
        </div>
      )}

      {/* UPLOADED DOCUMENTS LIST */}
      {documents.length > 0 && (
        <div className="space-y-3 pt-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold tracking-tight text-ink">Uploaded project documents</h3>
            <span className="text-xs text-slate">
              {plural(documents.length, 'document')} · {plural(totalDocumentPages, 'page')}
            </span>
          </div>

          <div className="divide-y divide-rule rounded-md border border-rule bg-surface">
            {documents.map((doc) => (
              <div key={doc.id} className="p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div className="grid size-9 shrink-0 place-items-center rounded bg-paper text-slate">
                      <FileTextIcon className="size-5" />
                    </div>
                    <div>
                      <p className="font-medium text-ink">{doc.filename}</p>
                      <p className="text-xs text-slate">
                        {plural(doc.page_count, 'page')} · {formatBytes(doc.size_bytes)}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-3">
                    <StatusBadge status={doc.status} />
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setDeletingDoc(doc)}
                      aria-label={`Delete ${doc.filename}`}
                      className="text-slate hover:text-danger"
                    >
                      <Trash2Icon className="size-4" />
                    </Button>
                  </div>
                </div>

                {doc.warning && (
                  <div className="mt-2 flex items-start gap-2 rounded bg-amber-wash/50 p-2 text-xs text-amber">
                    <AlertTriangleIcon className="mt-0.5 size-3.5 shrink-0" />
                    <span>{doc.warning}</span>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* DELETE CONFIRMATION DIALOG */}
      <Dialog open={Boolean(deletingDoc)} onOpenChange={(open) => !open && setDeletingDoc(null)}>
        <DialogContent>
          <DialogTitle>Delete document</DialogTitle>
          <DialogDescription>
            Are you sure you want to delete &ldquo;{deletingDoc?.filename}&rdquo;? This will remove the document,
            its file storage, and its processing state.
          </DialogDescription>
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="secondary">Cancel</Button>
            </DialogClose>
            <Button variant="primary" onClick={handleDeleteConfirm} disabled={deleteDoc.isPending}>
              {deleteDoc.isPending && <Spinner label="Deleting" className="text-white" />}
              Delete document
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* CONSENT DIALOG */}
      <ConsentDialog
        open={consentOpen}
        onOpenChange={setConsentOpen}
        onConsented={onConsented}
        renewal={renewal}
      />
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
    return <Badge tone="teal">Extracted</Badge>
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

  const hasFrNfr = lines.some((l) => /^(?:FR|NFR)\s*\d+/i.test(l))
  if (hasFrNfr) {
    const unnumbered = lines.filter((l) => !/^(?:FR|NFR)\s*\d+/i.test(l))
    if (unnumbered.length > 0) {
      return {
        warning: `Some lines do not have numbered FR/NFR IDs. The input will be accepted as free text; IDs could not be preserved for those lines.`,
      }
    }
    return { warning: null }
  }

  const hasStory = lines.some((l) => /^As\s+an?\s+/i.test(l))
  if (hasStory) {
    const storyRegex = /^As\s+an?\s+.+?,\s*I\s+want\s+.+?,\s*so\s+that\s+.+?[.!]?$/i
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

export function StepHeading({
  title,
  description,
  actions,
}: {
  title: string
  description?: string
  actions?: ReactNode
}) {
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
