import { ArrowUpIcon, LayersIcon, LinkIcon, MaximizeIcon, MoveIcon, PlusIcon, SparklesIcon, ZoomInIcon, ZoomOutIcon } from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type FormEvent, type MouseEvent } from 'react'
import { Link, NavLink, useNavigate, useParams } from 'react-router'
import { TransformComponent, TransformWrapper, useControls } from 'react-zoom-pan-pinch'
import type { Diagram, DiagramType } from '@/api/client'
import { ApiError, errorMessage } from '@/api/errors'
import { useDiagram, useDiagramImage, useDiagramLayout, useDiagrams, useDiagramStyle, useReviseDiagram } from '@/api/queries'
import { Badge, RefTag } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Notice } from '@/components/ui/notice'
import { PageLoading, Spinner } from '@/components/ui/spinner'
import { typeLabel } from '@/features/generate/diagram-types'
import { DriftBanner } from '@/features/traceability/drift-banner'
import { LayoutCanvas } from '@/features/viewer/layout-canvas'
import { LayoutEditor } from '@/features/viewer/layout-editor'
import { sameStyle, StylePanel } from '@/features/viewer/style-panel'
import { DEFAULT_STYLE } from '@/features/viewer/style'
import { sanitizeSvg } from '@/lib/svg'
import { cn, formatRelative } from '@/lib/utils'
import { NotFoundPage } from '@/routes/not-found-page'
import { useWorkspace } from '@/routes/workspace-layout'
import { ExportMenu } from './export-menu'

const MAX_INSTRUCTION = 500
type Summary = Pick<Diagram, 'id' | 'type' | 'created_at' | 'parent_id' | 'instruction' | 'title' | 'out_of_date'>

/** Every version from the first generation to the newest edit that passes through `current`. */
function lineage(all: Summary[], current: Summary): Summary[] {
  const byId = new Map(all.map((d) => [d.id, d]))
  const seen = new Set<string>()
  const path: Summary[] = []
  for (let d: Summary | undefined = byId.get(current.id) ?? current; d && !seen.has(d.id); d = byId.get(d.parent_id ?? '')) {
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

/** PNG export goes through the Kroki renderer. 424 means the renderer is down: never the "server waking" state. */
function exportMessage(e: unknown) {
  if (e instanceof ApiError && e.status === 424) return 'Diagram renderer unavailable, try again in a minute.'
  return errorMessage(e, 'The PNG export failed. Try again.')
}

export function ViewerPage() {
  const { project } = useWorkspace()
  const { diagramId = '' } = useParams()
  const navigate = useNavigate()
  const { data: diagram, isPending, error } = useDiagram(diagramId)
  const { data: all } = useDiagrams(project.id)
  const revise = useReviseDiagram(project.id)
  const [draft, setDraft] = useState('')
  const [selected, setSelected] = useState<string | null>(null)
  const layout = useDiagramLayout(diagramId)
  const [arrangeFor, setArrangeFor] = useState<string | null>(null)
  const style = useDiagramStyle(diagramId)
  const [stylePreviewUrl, setStylePreviewUrl] = useState<string | null>(null)
  const threadRef = useRef<HTMLOListElement>(null)
  const canvasRef = useRef<HTMLDivElement>(null)

  const versions = useMemo(() => (diagram ? lineage(all ?? [], diagram) : []), [all, diagram])
  const edits = versions.filter((v) => v.instruction)
  const svg = useMemo(() => (diagram?.svg ? sanitizeSvg(diagram.svg) : ''), [diagram?.svg])

  useEffect(() => {
    const el = threadRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [edits.length, revise.isPending, revise.isError])

  useEffect(() => {
    setSelected(null)
  }, [diagramId])

  useEffect(() => {
    const root = canvasRef.current
    if (!root) return
    root.querySelectorAll('[data-selected]').forEach((n) => n.removeAttribute('data-selected'))
    if (selected) root.querySelectorAll(`[data-element-id="${CSS.escape(selected)}"]`).forEach((n) => n.setAttribute('data-selected', ''))
  }, [selected, svg])

  if (isPending) return <PageLoading label="Loading diagram" />
  if (error instanceof ApiError && error.status === 404) return <NotFoundPage message="This diagram does not exist, or you do not have access to it." />
  if (!diagram)
    return (
      <Notice className="m-7" tone="error" title="Couldn't load the diagram">
        {errorMessage(error)}
      </Notice>
    )

  const index = versions.findIndex((v) => v.id === diagram.id)
  const latest = versions.at(-1)
  const element = diagram.elements?.find((e) => e.element_id === selected)
  const traced = element ? (diagram.statements ?? []).filter((s) => element.statement_ids.includes(s.id)) : []
  const arranging = arrangeFor === diagram.id && !!layout.data
  // Kroki draws from the source and knows nothing of moved positions, so a moved version is drawn here instead.
  const moved = layout.data?.saved ? layout.data : null
  // A package diagram is drawn from the confirmed subsystem decomposition: it changes there, not here.
  const fromDesign = diagram.type === 'package'
  // The stored SVG has the standard look; a saved look (#38) is drawn by Kroki, so that version shows its PNG.
  const styled = !!style.data && !sameStyle(style.data, DEFAULT_STYLE)

  async function send(e: FormEvent) {
    e.preventDefault()
    const instruction = draft.trim()
    if (!instruction || revise.isPending) return
    const next = await revise.mutateAsync({ diagramId: diagram!.id, instruction }).catch(() => null)
    if (!next) return // the error shows in the thread; the text stays in the box to fix and resend
    setDraft('')
    navigate(`../diagrams/${next.id}`)
  }

  function pick(e: MouseEvent) {
    const id = (e.target as Element).closest?.('[data-element-id]')?.getAttribute('data-element-id')
    setSelected(id ?? null)
  }

  return (
    <div className="grid min-h-0 flex-1 lg:grid-cols-[250px_minmax(0,1fr)_330px]">
      <DiagramList all={all ?? []} currentId={diagram.id} />

      <section aria-label="Diagram" className="grid-bg relative flex min-h-[560px] flex-col">
        <div className="flex flex-wrap items-center gap-2 p-4">
          <div>
            <h2 className="flex items-center gap-2 text-lg leading-tight font-semibold">
              {typeLabel[diagram.type]} diagram
              {all?.find((d) => d.id === diagram.id)?.out_of_date && <Badge tone="amber">Out of date</Badge>}
            </h2>
            <p className="text-[12px] text-slate">
              {versions.length > 1 && `Version ${index + 1} of ${versions.length} · `}
              {diagram.instruction ? 'Edited' : fromDesign ? 'Drawn' : 'Generated'} {formatRelative(diagram.created_at)}
              {!fromDesign && (
                <>
                  {' · '}
                  <Link to="../generate" className="text-accent hover:underline">
                    Generate again
                  </Link>
                </>
              )}
            </p>
          </div>
          <div className="ml-auto flex items-start gap-2">
            <Button variant="secondary" onClick={() => setArrangeFor(diagram.id)} disabled={!layout.data || arranging || revise.isPending}>
              <MoveIcon /> Move elements
            </Button>
            {/* A moved version is exported as drawn on screen; otherwise the API renders it. */}
            <ExportMenu
              diagramId={diagram.id}
              title={diagram.title}
              versionIndex={index}
              projectId={project.id}
              projectName={project.name}
              drawn={moved ? () => canvasRef.current?.querySelector<SVGSVGElement>('svg[data-layout-canvas]') ?? null : undefined}
              disabled={moved ? arranging : false}
            />
          </div>
        </div>

        {latest && latest.id !== diagram.id && (
          <p className="mx-4 rounded-lg bg-amber-wash px-3 py-2 text-[13px]">
            You&rsquo;re looking at an earlier version. A change you type here starts from this one.{' '}
            <Link to={`../diagrams/${latest.id}`} className="font-medium text-accent hover:underline">
              Go to the latest
            </Link>
          </p>
        )}
        {arranging ? (
          <div className="mb-4 flex min-h-0 flex-1 flex-col">
            <LayoutEditor key={diagram.id} projectId={project.id} layout={layout.data!} title={diagram.title} onClose={() => setArrangeFor(null)} />
          </div>
        ) : (
          <div ref={canvasRef} className="relative mx-4 mb-4 min-h-0 flex-1 overflow-hidden rounded-xl" onClick={pick}>
            {moved ? (
              <TransformWrapper key={diagram.id} minScale={0.3} maxScale={6} centerOnInit limitToBounds={false} doubleClick={{ disabled: true }}>
                <ZoomControls />
                <TransformComponent wrapperClass="!h-full !w-full" contentClass="!h-full !w-full">
                  <LayoutCanvas elements={moved.elements} lines={moved.lines} positions={{}} label={`${diagram.title}, version ${index + 1}`} className="p-2" />
                </TransformComponent>
              </TransformWrapper>
            ) : stylePreviewUrl ? (
              <img src={stylePreviewUrl} alt={`${diagram.title}, version ${index + 1}, style preview`} className="m-auto block h-full w-full object-contain p-4" draggable={false} />
            ) : svg && !styled ? (
              <TransformWrapper key={diagram.id} minScale={0.3} maxScale={6} centerOnInit limitToBounds={false} doubleClick={{ disabled: true }}>
                <ZoomControls />
                <TransformComponent wrapperClass="!h-full !w-full" contentClass="!h-full !w-full">
                  <div className="diagram-svg grid size-full place-items-center p-6" role="img" aria-label={`${diagram.title}, version ${index + 1}`} dangerouslySetInnerHTML={{ __html: svg }} />
                </TransformComponent>
              </TransformWrapper>
            ) : (
              <PngFallback diagram={diagram} />
            )}
            {revise.isPending && (
              <div className="absolute inset-0 z-20 grid place-items-center bg-paper/70 backdrop-blur-[1px]">
                <p className="flex items-center gap-2 rounded-full border border-rule bg-surface px-4 py-2 text-[13px] shadow-sm">
                  <Spinner label="" /> Updating the diagram…
                </p>
              </div>
            )}
            <p className="pointer-events-none absolute bottom-2 left-3 text-[11.5px] text-slate">
              Drag to pan · scroll to zoom{svg && !moved && !styled ? ' · click a shape to see its source' : ''}
            </p>
          </div>
        )}
        {/* The look is applied where Kroki draws the diagram; a moved version is drawn in the browser, so it keeps the standard look. */}
        {!arranging &&
          (moved ? (
            <p className="mx-4 mb-4 text-[13px] text-slate">
              Elements in this version were moved by hand, so it keeps the standard look. To change colours, direction or font size, open the version
              before the move.
            </p>
          ) : (
            <StylePanel key={diagram.id} diagramId={diagram.id} diagramType={diagram.type} onPreviewChange={setStylePreviewUrl} />
          ))}
      </section>

      <aside className="flex min-h-0 flex-col border-l border-rule bg-surface">
        <DriftBanner diagramId={diagram.id} />
        <div className="border-b border-rule p-4">
          {element ? (
            <>
              <p className="font-mono text-[11px] tracking-[0.08em] text-slate uppercase">Selected · {element.kind.replace('_', ' ')}</p>
              <p className="mt-1 font-display text-xl font-semibold">{element.label}</p>
              <p className="mt-3 flex items-center gap-1.5 text-[13px] font-semibold">
                <LinkIcon className="size-3.5" /> Traced to
              </p>
              {traced.length ? (
                <ul className="mt-2 space-y-2">
                  {traced.map((s) => (
                    <li key={s.id} className="rounded-[9px] border border-accent bg-accent-wash p-2.5">
                      <RefTag className="border-accent text-accent">{s.ref}</RefTag>
                      <p className="mt-1.5 text-[13px]">{s.text}</p>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1 text-[12.5px] text-amber">No source requirement: this one was assumed by the generator.</p>
              )}
            </>
          ) : (
            <p className="text-[13px] text-slate">
              <LinkIcon className="mr-1 inline size-3.5" />
              Click a shape in the diagram to see the requirement it came from.
            </p>
          )}
        </div>

        <div className="flex min-h-0 flex-1 flex-col p-4">
          <div className="flex items-center justify-between">
            <p className="flex items-center gap-1.5 text-[14px] font-semibold">
              <SparklesIcon className="size-4 text-accent" /> Edit with AI
            </p>
            <span className="text-[11px] text-slate">each change = new version</span>
          </div>
          <ol ref={threadRef} aria-label="Changes to this diagram" aria-live="polite" className="mt-3 min-h-0 flex-1 space-y-2.5 overflow-y-auto pr-1 text-[13px]">
            {edits.map((v) => {
              const n = versions.indexOf(v) + 1
              return (
                <li key={v.id} className="space-y-1">
                  <p className="ml-auto w-fit max-w-[88%] rounded-2xl rounded-br-sm bg-ink px-3 py-1.5 text-on-ink">{v.instruction}</p>
                  <p className="flex items-center gap-1.5 text-[11.5px] text-slate">
                    <LayersIcon className="size-3.5" aria-hidden />
                    {v.id === diagram.id ? (
                      <span className="font-medium text-accent">Version {n}, showing now</span>
                    ) : (
                      <Link to={`../diagrams/${v.id}`} className="font-medium text-accent hover:underline">
                        View version {n}
                      </Link>
                    )}
                  </p>
                </li>
              )
            })}
            {(revise.isPending || revise.isError) && revise.variables && (
              <li className="space-y-1">
                <p className="ml-auto w-fit max-w-[88%] rounded-2xl rounded-br-sm bg-ink px-3 py-1.5 text-on-ink">{revise.variables.instruction}</p>
                {revise.isPending ? (
                  <p className="flex items-center gap-1.5 text-[11.5px] text-slate">
                    <Spinner className="size-3" label="" /> Updating the diagram…
                  </p>
                ) : (
                  <p role="alert" className="max-w-[88%] rounded-2xl rounded-bl-sm bg-danger-wash px-3 py-1.5 text-danger">
                    {errorMessage(revise.error, 'That change did not go through. Try again.')}
                  </p>
                )}
              </li>
            )}
            {edits.length === 0 && !revise.isPending && !revise.isError && (
              <li className="text-[12.5px] text-slate">Try “rename Issue book to Lend a book” or “add an Admin who manages accounts”.</li>
            )}
          </ol>
          {fromDesign ? (
            <p className="mt-3 rounded-[10px] bg-paper px-3 py-2.5 text-[12.5px] text-slate">
              This diagram is drawn from the confirmed subsystem decomposition.{' '}
              <Link to="../design?tab=decomposition" className="font-medium text-accent hover:underline">
                Change it in the Design step
              </Link>
            </p>
          ) : (
            <form onSubmit={send} className="mt-3">
              <div className="flex items-center gap-2 rounded-[10px] border border-rule-strong bg-field py-1.5 pr-1.5 pl-3 focus-within:border-accent focus-within:ring-3 focus-within:ring-accent/20">
                <label htmlFor="diagram-edit" className="sr-only">
                  Describe a change to the diagram
                </label>
                <input
                  id="diagram-edit"
                  value={draft}
                  maxLength={MAX_INSTRUCTION}
                  autoComplete="off"
                  placeholder="Describe a change…"
                  className="min-w-0 flex-1 bg-transparent text-[14px] placeholder:text-slate/70 focus:outline-none"
                  onChange={(e) => {
                    setDraft(e.target.value)
                    if (revise.isError) revise.reset()
                  }}
                  disabled={revise.isPending || arranging}
                />
                <Button type="submit" variant="accent" size="icon" className="size-8" aria-label="Apply change" disabled={!draft.trim() || revise.isPending}>
                  {revise.isPending ? <Spinner className="text-on-ink" label="" /> : <ArrowUpIcon />}
                </Button>
              </div>
              {draft.length > 0 && (
                <p className={cn('mt-1 text-right text-[11px] tabular-nums', draft.length >= MAX_INSTRUCTION - 20 ? 'text-danger' : draft.length >= MAX_INSTRUCTION - 100 ? 'text-amber' : 'text-slate')}>
                  {draft.length} / {MAX_INSTRUCTION}
                </p>
              )}
            </form>
          )}
        </div>
      </aside>
    </div>
  )
}

/** Older diagrams without stored SVG: show the rendered PNG instead. */
function PngFallback({ diagram }: { diagram: Diagram }) {
  const image = useDiagramImage(diagram.id)
  const [src, setSrc] = useState<string | null>(null)
  useEffect(() => {
    if (!image.data) return setSrc(null)
    const url = URL.createObjectURL(image.data)
    setSrc(url)
    return () => URL.revokeObjectURL(url)
  }, [image.data])
  if (src) return <img src={src} alt={diagram.title} className="m-auto block h-full w-full object-contain p-4" draggable={false} />
  if (image.isError)
    return (
      <div className="grid h-full place-items-center p-6">
        <Notice tone="error" title="Couldn't load the diagram image">
          {exportMessage(image.error)}
        </Notice>
      </div>
    )
  return (
    <div className="grid h-full place-items-center">
      <Spinner label="Loading the diagram image" />
    </div>
  )
}

function DiagramList({ all, currentId }: { all: Summary[]; currentId: string }) {
  const groups = new Map<DiagramType, Summary[]>()
  for (const d of [...all].sort((a, b) => b.created_at.localeCompare(a.created_at))) groups.set(d.type, [...(groups.get(d.type) ?? []), d])
  return (
    <nav aria-label="Your diagrams" className="border-r border-rule bg-surface p-4">
      <div className="flex items-center justify-between">
        <p className="text-[14px] font-semibold">Diagrams</p>
        <Button asChild variant="secondary" size="sm">
          <Link to="../generate">
            <PlusIcon /> More
          </Link>
        </Button>
      </div>
      <Link to="../items" className="mt-4 block rounded-[10px] border border-dashed border-rule-strong p-3 text-[12px] hover:border-ink-2">
        <span className="block font-semibold">Building blocks</span>
        <span className="text-accent">Review items (optional)</span>
      </Link>
      {[...groups].map(([type, list]) => (
        <div key={type}>
          <p className="mt-5 mb-1.5 font-mono text-[11px] tracking-[0.08em] text-slate uppercase">{typeLabel[type]}</p>
          <ul className="space-y-0.5">
            {list.map((d, i) => (
              <li key={d.id}>
                <NavLink
                  to={`../diagrams/${d.id}`}
                  className={({ isActive }) => cn('flex items-center gap-2 rounded-lg px-2.5 py-2 text-[13px] hover:bg-ink/4', isActive && 'border border-rule bg-field')}
                >
                  <span className={cn('w-6 font-mono text-[11px]', d.id === currentId ? 'font-semibold text-accent' : 'text-slate')}>v{list.length - i}</span>
                  <span className="min-w-0 flex-1 truncate">{d.instruction ?? (d.type === 'package' ? 'Drawn' : 'Generated')}</span>
                  {d.out_of_date && <Badge tone="amber">Out of date</Badge>}
                  <span className="text-[11px] text-slate">{formatRelative(d.created_at)}</span>
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  )
}

function ZoomControls() {
  const { zoomIn, zoomOut, resetTransform } = useControls()
  return (
    <div className="absolute top-2 right-2 z-10 flex gap-0.5 rounded-[9px] border border-rule bg-field p-0.5">
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
