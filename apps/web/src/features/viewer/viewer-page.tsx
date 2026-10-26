import { ArrowUpIcon, DownloadIcon, MaximizeIcon, SparklesIcon, ZoomInIcon, ZoomOutIcon } from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { TransformComponent, TransformWrapper, useControls } from 'react-zoom-pan-pinch'
import type { Diagram } from '@/api/client'
import { ApiError, errorMessage } from '@/api/errors'
import { saveBlob, useDiagram, useDiagramImage, useDiagrams, useReviseDiagram } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { Notice } from '@/components/ui/notice'
import { PageLoading, Spinner } from '@/components/ui/spinner'
import { typeLabel } from '@/features/generate/diagram-types'
import { formatRelative } from '@/lib/utils'
import { NotFoundPage } from '@/routes/not-found-page'
import { useWorkspace } from '@/routes/workspace-layout'

const MAX_INSTRUCTION = 500

/** Every version from the first generation to the newest edit that passes through `currentId`. */
function lineage(all: Diagram[], current: Diagram): Diagram[] {
  const byId = new Map(all.map((d) => [d.id, d]))
  const seen = new Set<string>()
  const path: Diagram[] = []
  for (let d: Diagram | undefined = byId.get(current.id) ?? current; d && !seen.has(d.id); d = byId.get(d.parent_id ?? '')) {
    seen.add(d.id)
    path.unshift(d)
  }
  for (let tail = path.at(-1); tail; ) {
    const child = all.filter((d) => d.parent_id === tail!.id && !seen.has(d.id)).sort((a, b) => b.created_at.localeCompare(a.created_at))[0]
    if (child) {
      seen.add(child.id)
      path.push(child)
    }
    tail = child
  }
  return path
}

export function ViewerPage() {
  const { project } = useWorkspace()
  const { diagramId = '' } = useParams()
  const navigate = useNavigate()
  const { data: diagram, isPending, error } = useDiagram(diagramId)
  const { data: all } = useDiagrams(project.id)
  const image = useDiagramImage(diagramId)
  const revise = useReviseDiagram(project.id)
  const [draft, setDraft] = useState('')
  const [src, setSrc] = useState<string | null>(null)
  const threadRef = useRef<HTMLOListElement>(null)

  useEffect(() => {
    if (!image.data) return setSrc(null)
    const url = URL.createObjectURL(image.data)
    setSrc(url)
    return () => URL.revokeObjectURL(url)
  }, [image.data])

  const versions = useMemo(() => (diagram ? lineage(all ?? [], diagram) : []), [all, diagram])
  const edits = versions.filter((v) => v.instruction)

  useEffect(() => {
    const el = threadRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [edits.length, revise.isPending, revise.isError])

  if (isPending) return <PageLoading label="Loading diagram" />
  if (error instanceof ApiError && error.status === 404) return <NotFoundPage message="This diagram does not exist, or you do not have access to it." />
  if (!diagram)
    return (
      <Notice tone="error" title="Couldn't load the diagram">
        {errorMessage(error)}
      </Notice>
    )

  const index = versions.findIndex((v) => v.id === diagram.id)
  const latest = versions.at(-1)

  async function send(e: FormEvent) {
    e.preventDefault()
    const instruction = draft.trim()
    if (!instruction || revise.isPending) return
    const next = await revise.mutateAsync({ diagramId: diagram!.id, instruction }).catch(() => null)
    if (!next) return // the error shows in the thread; the text stays in the box to fix and resend
    setDraft('')
    navigate(`../diagrams/${next.id}`)
  }

  function exportPng() {
    if (!image.data) return
    const slug = diagram!.title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
    saveBlob(image.data, `${slug || 'diagram'}${index > 0 ? `-v${index + 1}` : ''}.png`)
  }

  return (
    <div className="-m-5 flex min-h-0 flex-1 flex-col">
      <div className="flex flex-wrap items-start justify-between gap-3 px-5 pt-4">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">{typeLabel[diagram.type]} diagram</h2>
          <p className="text-sm text-slate">
            {versions.length > 1 && `Version ${index + 1} of ${versions.length} · `}
            {diagram.instruction ? 'Edited' : 'Generated'} {formatRelative(diagram.created_at)}.{' '}
            <Link to="../generate" className="text-teal hover:underline">
              Generate again
            </Link>
          </p>
        </div>
        <Button variant="secondary" onClick={exportPng} disabled={!image.data}>
          <DownloadIcon /> Export PNG
        </Button>
      </div>

      {latest && latest.id !== diagram.id && (
        <p className="mx-5 mt-3 rounded-md bg-amber-wash px-3 py-2 text-sm">
          You're looking at an earlier version. A change you type here starts from this one.{' '}
          <Link to={`../diagrams/${latest.id}`} className="font-medium text-teal hover:underline">
            Go to the latest
          </Link>
        </p>
      )}

      <div className="relative mx-5 mt-3 h-[min(60vh,560px)] overflow-hidden rounded-lg border border-rule bg-white xl:h-auto xl:min-h-72 xl:flex-1">
        {src ? (
          <TransformWrapper key={diagram.id} minScale={0.3} maxScale={6} centerOnInit limitToBounds={false} doubleClick={{ disabled: true }}>
            <ZoomControls />
            <TransformComponent wrapperClass="!h-full !w-full" contentClass="!h-full !w-full">
              <img src={src} alt={`${diagram.title}, version ${index + 1}`} className="m-auto block h-full w-full object-contain p-4" draggable={false} />
            </TransformComponent>
          </TransformWrapper>
        ) : image.isError ? (
          <div className="grid h-full place-items-center p-6">
            <Notice tone="error" title="Couldn't load the diagram image">
              {errorMessage(image.error)}
            </Notice>
          </div>
        ) : (
          <div className="grid h-full place-items-center">
            <Spinner label="Loading the diagram image" />
          </div>
        )}
        {revise.isPending && (
          <div className="absolute inset-0 z-20 grid place-items-center bg-white/70 backdrop-blur-[1px]">
            <p className="flex items-center gap-2 rounded-full border border-rule bg-surface px-4 py-2 text-sm shadow-sm">
              <Spinner label="" /> Updating the diagram…
            </p>
          </div>
        )}
        {src && <p className="pointer-events-none absolute bottom-2 left-3 text-xs text-slate">Drag to pan, scroll or pinch to zoom</p>}
      </div>

      {(edits.length > 0 || revise.isPending || revise.isError) && (
        <ol ref={threadRef} aria-label="Changes to this diagram" aria-live="polite" className="mx-5 mt-3 max-h-48 space-y-2.5 overflow-y-auto pr-1 text-sm">
          {edits.map((v) => {
            const n = versions.indexOf(v) + 1
            return (
              <li key={v.id} className="space-y-1">
                <p className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-sm bg-teal-wash px-3 py-1.5 text-ink">{v.instruction}</p>
                <p className="flex items-center gap-1.5 text-xs text-slate">
                  <SparklesIcon className="size-3.5 text-teal" aria-hidden />
                  {v.id === diagram.id ? (
                    <span className="font-medium text-teal-deep">Version {n}, showing now</span>
                  ) : (
                    <Link to={`../diagrams/${v.id}`} className="font-medium text-teal hover:underline">
                      View version {n}
                    </Link>
                  )}
                </p>
              </li>
            )
          })}
          {(revise.isPending || revise.isError) && revise.variables && (
            <li className="space-y-1">
              <p className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-sm bg-teal-wash px-3 py-1.5 text-ink">{revise.variables.instruction}</p>
              {revise.isPending ? (
                <p className="flex items-center gap-1.5 text-xs text-slate">
                  <Spinner className="size-3" label="" /> Updating the diagram…
                </p>
              ) : (
                <p role="alert" className="max-w-[85%] rounded-2xl rounded-bl-sm bg-danger-wash px-3 py-1.5 text-danger">
                  {errorMessage(revise.error, 'That change did not go through. Try again.')}
                </p>
              )}
            </li>
          )}
        </ol>
      )}

      <form onSubmit={send} className="px-5 pt-3 pb-4">
        <div className="flex items-center gap-2 rounded-full border border-rule-strong bg-surface py-1.5 pr-1.5 pl-4 focus-within:border-teal focus-within:ring-2 focus-within:ring-teal/20">
          <label htmlFor="diagram-edit" className="sr-only">
            Describe a change to the diagram
          </label>
          <input
            id="diagram-edit"
            value={draft}
            maxLength={MAX_INSTRUCTION}
            autoComplete="off"
            placeholder="Describe a change, e.g. rename Browse canteen menu to Browse menu card"
            className="min-w-0 flex-1 bg-transparent text-[15px] placeholder:text-slate/70 focus:outline-none"
            onChange={(e) => {
              setDraft(e.target.value)
              if (revise.isError) revise.reset()
            }}
            disabled={revise.isPending}
          />
          <Button type="submit" size="icon" className="size-8 rounded-full" aria-label="Apply change" disabled={!draft.trim() || revise.isPending}>
            {revise.isPending ? <Spinner className="text-white" label="" /> : <ArrowUpIcon />}
          </Button>
        </div>
        <div className="mt-1.5 flex items-center justify-between gap-2 px-4">
          <p className="text-xs text-slate">Each change makes a new version. Earlier versions stay under Your diagrams.</p>
          {draft.length > 0 && (
            <p className={cn('shrink-0 text-xs tabular-nums', draft.length >= MAX_INSTRUCTION - 20 ? 'text-danger' : draft.length >= MAX_INSTRUCTION - 100 ? 'text-amber-600' : 'text-slate')}>
              {draft.length} / {MAX_INSTRUCTION}
            </p>
          )}
        </div>
      </form>
    </div>
  )
}

function ZoomControls() {
  const { zoomIn, zoomOut, resetTransform } = useControls()
  return (
    <div className="absolute top-2 right-2 z-10 flex gap-1 rounded-md border border-rule bg-surface p-1">
      <Button variant="ghost" size="icon" className="size-8" aria-label="Zoom in" onClick={() => zoomIn()}>
        <ZoomInIcon />
      </Button>
      <Button variant="ghost" size="icon" className="size-8" aria-label="Zoom out" onClick={() => zoomOut()}>
        <ZoomOutIcon />
      </Button>
      <Button variant="ghost" size="icon" className="size-8" aria-label="Reset view" onClick={() => resetTransform()}>
        <MaximizeIcon />
      </Button>
    </div>
  )
}
