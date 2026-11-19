import { ArrowDownIcon, ArrowUpIcon, PlusIcon, XIcon } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import type { DesignDecomposition, DesignDecompositionDerived } from '@/api/client'
import { useDiagramImage, useDiagrams, useItems } from '@/api/queries'
import { RefTag } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input, Label, Textarea } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { useWorkspace } from '@/routes/workspace-layout'
import type { EditorProps } from './design-page'

type Subsystem = DesignDecomposition['subsystems'][number]
const ARCHITECTURES = [
  ['closed', 'Closed', 'A layer calls only the layer directly below it.'],
  ['open', 'Open', 'A layer may call any layer below it.'],
] as const

/** A unique id from the name, in the API's slug form; kept when the name changes so depends_on stays valid. */
function slugFor(name: string, taken: string[]) {
  const base = name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 36) || 'subsystem'
  let id = base
  for (let n = 2; taken.includes(id); n++) id = `${base}-${n}`
  return id
}

const score = (n: number | null | undefined) => (n == null ? '—' : String(n))

/** 4.2 Subsystem decomposition: subsystems grouped by layer (top first), with their services, classes, dependencies
 *  and requirements; the saved version's cohesion, coupling and warnings; the package diagram once confirmed. */
export function DecompositionEditor({ content, derived, dirty, disabled, confirmed, requirements, onChange }: EditorProps) {
  const { project } = useWorkspace()
  const { architecture, subsystems } = content as DesignDecomposition
  const summary = derived as DesignDecompositionDerived | null
  // shortcut: only the first page (200) of entities is offered; page through them if a project ever has more.
  const entities = useItems(project.id, 'entity', 1)
  const classNames = [...new Set(entities.data?.items.map((i) => i.name))]
  const [adding, setAdding] = useState('')
  const [open, setOpen] = useState<string | null>(null)
  const refOf = new Map(requirements.map((r) => [r.id, r.ref]))
  const nameOf = new Map(subsystems.map((s) => [s.id, s.name]))
  const layers = [...new Set(subsystems.map((s) => s.layer))].sort((a, b) => a - b)

  const update = (next: Subsystem[], arch = architecture) => onChange({ architecture: arch, subsystems: next })
  const change = (id: string, patch: Partial<Subsystem>) => update(subsystems.map((s) => (s.id === id ? { ...s, ...patch } : s)))
  const toggle = (list: string[], value: string, on: boolean) => (on ? [...list, value] : list.filter((v) => v !== value))
  const remove = (id: string) =>
    update(subsystems.filter((s) => s.id !== id).map((s) => ({ ...s, depends_on: s.depends_on.filter((d) => d !== id) })))

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_18rem]">
      <div className="space-y-4">
        <fieldset className="flex flex-wrap gap-x-6 gap-y-2" disabled={disabled}>
          <legend className="mb-1 text-sm font-medium">Architecture</legend>
          {ARCHITECTURES.map(([value, label, meaning]) => (
            <label key={value} className="flex items-start gap-2 text-sm">
              <input
                type="radio"
                name="architecture"
                className="mt-1 accent-[var(--accent)]"
                checked={architecture === value}
                onChange={() => update(subsystems, value)}
              />
              <span>
                <span className="font-medium">{label}</span> <span className="text-slate">{meaning}</span>
              </span>
            </label>
          ))}
        </fieldset>

        {subsystems.length === 0 && (
          <p className="rounded-lg border border-dashed border-rule-strong p-6 text-center text-sm text-slate">
            No subsystems yet. Draft them with AI or add them below.
          </p>
        )}
        {layers.map((layer) => (
          <section key={layer} aria-label={layer === 1 ? 'Layer 1 (top)' : `Layer ${layer}`} className="space-y-2">
            <h4 className="text-sm font-semibold">{layer === 1 ? 'Layer 1 (top)' : `Layer ${layer}`}</h4>
            {/* Subsystems side by side in a layer are its partitions. */}
            <ul className="grid gap-3 xl:grid-cols-2">
              {subsystems
                .filter((s) => s.layer === layer)
                .map((s) => {
                  const others = subsystems.filter((o) => o.id !== s.id)
                  const ownedElsewhere = new Set(others.flatMap((o) => o.classes))
                  const offered = [...new Set([...s.classes, ...classNames.filter((c) => !ownedElsewhere.has(c))])]
                  const warnings = summary?.warnings.filter((w) => w.subsystem_ids.includes(s.id)) ?? []
                  return (
                    <li key={s.id} data-subsystem={s.id} className="space-y-3 rounded-xl border border-rule bg-field p-3">
                      <div className="flex items-center gap-2">
                        <h5 className="min-w-0 flex-1 truncate font-medium">{s.name || 'Unnamed subsystem'}</h5>
                        <Button variant="ghost" size="icon" aria-label={`Move ${s.name} to the layer above`} disabled={disabled || s.layer === 1} onClick={() => change(s.id, { layer: s.layer - 1 })}>
                          <ArrowUpIcon />
                        </Button>
                        <Button variant="ghost" size="icon" aria-label={`Move ${s.name} to the layer below`} disabled={disabled} onClick={() => change(s.id, { layer: s.layer + 1 })}>
                          <ArrowDownIcon />
                        </Button>
                        <Button variant="ghost" size="icon" aria-label={`Remove ${s.name}`} disabled={disabled} onClick={() => remove(s.id)}>
                          <XIcon />
                        </Button>
                      </div>
                      {warnings.length > 0 && (
                        <ul className="space-y-1 rounded-md bg-amber-wash px-2.5 py-1.5 text-xs">
                          {warnings.map((w) => (
                            <li key={w.code + w.subsystem_ids.join()}>{w.message}</li>
                          ))}
                        </ul>
                      )}
                      <div className="space-y-1">
                        <Label htmlFor={`sub-name-${s.id}`}>Name</Label>
                        <Input id={`sub-name-${s.id}`} maxLength={80} value={s.name} disabled={disabled} onChange={(e) => change(s.id, { name: e.target.value })} />
                      </div>
                      <div className="space-y-1">
                        <Label htmlFor={`sub-description-${s.id}`}>Description</Label>
                        <Textarea
                          id={`sub-description-${s.id}`}
                          className="min-h-14"
                          maxLength={500}
                          value={s.description}
                          disabled={disabled}
                          onChange={(e) => change(s.id, { description: e.target.value })}
                        />
                      </div>

                      <fieldset className="space-y-2" disabled={disabled}>
                        <legend className="text-sm font-medium">Services</legend>
                        {s.services.map((v, i) => {
                          const setService = (patch: Partial<typeof v>) =>
                            change(s.id, { services: s.services.map((x, j) => (j === i ? { ...x, ...patch } : x)) })
                          return (
                            <div key={i} className="space-y-1 rounded-md border border-rule p-2">
                              <div className="flex items-end gap-2">
                                <div className="flex-1 space-y-1">
                                  <Label htmlFor={`sub-service-${s.id}-${i}`}>Service name</Label>
                                  <Input id={`sub-service-${s.id}-${i}`} maxLength={120} value={v.name} onChange={(e) => setService({ name: e.target.value })} />
                                </div>
                                <Button variant="ghost" size="icon" aria-label={`Remove service ${v.name}`} onClick={() => change(s.id, { services: s.services.filter((_, j) => j !== i) })}>
                                  <XIcon />
                                </Button>
                              </div>
                              <Label htmlFor={`sub-ops-${s.id}-${i}`}>Operations, one per line</Label>
                              <Textarea
                                id={`sub-ops-${s.id}-${i}`}
                                className="min-h-14"
                                value={v.operations.join('\n')}
                                // Blank lines are dropped as you type, except the one being started at the end.
                                onChange={(e) => setService({ operations: e.target.value.split('\n').filter((o, j, all) => o.trim() || j === all.length - 1) })}
                              />
                            </div>
                          )
                        })}
                        <Button variant="secondary" size="sm" onClick={() => change(s.id, { services: [...s.services, { name: '', operations: [] }] })}>
                          <PlusIcon /> Add service
                        </Button>
                      </fieldset>

                      {classNames.length > 0 ? (
                        <fieldset className="flex max-h-40 flex-wrap gap-x-4 gap-y-1.5 overflow-y-auto" disabled={disabled}>
                          <legend className="mb-1 text-sm font-medium">Classes it owns</legend>
                          {offered.map((c) => (
                            <label key={c} className="flex items-center gap-2 text-sm">
                              <Checkbox aria-label={`${s.name} owns ${c}`} checked={s.classes.includes(c)} onCheckedChange={(on) => change(s.id, { classes: toggle(s.classes, c, on === true) })} />
                              {c}
                            </label>
                          ))}
                        </fieldset>
                      ) : (
                        entities.data && <p className="text-xs text-slate">No classes were extracted for this project, so there are none to assign.</p>
                      )}

                      {others.length > 0 && (
                        <fieldset className="flex flex-wrap gap-x-4 gap-y-1.5" disabled={disabled}>
                          <legend className="mb-1 text-sm font-medium">Depends on</legend>
                          {others.map((o) => (
                            <label key={o.id} className="flex items-center gap-2 text-sm">
                              <Checkbox
                                aria-label={`${s.name} depends on ${o.name}`}
                                checked={s.depends_on.includes(o.id)}
                                onCheckedChange={(on) => change(s.id, { depends_on: toggle(s.depends_on, o.id, on === true) })}
                              />
                              {o.name} <span className="text-xs text-slate">(layer {o.layer})</span>
                            </label>
                          ))}
                        </fieldset>
                      )}

                      <div className="flex flex-wrap items-center gap-1.5">
                        {s.statement_ids.map((id) => (
                          <RefTag key={id}>{refOf.get(id) ?? 'Deleted requirement'}</RefTag>
                        ))}
                        {!s.statement_ids.length && <span className="text-xs text-amber">Cites no requirement yet</span>}
                        <Button variant="link" size="sm" className="ml-1" aria-expanded={open === s.id} disabled={disabled} onClick={() => setOpen(open === s.id ? null : s.id)}>
                          Requirements for {s.name}
                        </Button>
                      </div>
                      {open === s.id && (
                        // Scrolls on its own so a project with many requirements stays usable.
                        <fieldset className="max-h-48 space-y-1.5 overflow-y-auto rounded-md border border-rule p-2">
                          <legend className="sr-only">Requirements {s.name} cites</legend>
                          {requirements.map((r) => (
                            <label key={r.id} className="flex items-start gap-2 text-sm">
                              <Checkbox
                                className="mt-0.5"
                                aria-label={`${s.name} cites ${r.ref}`}
                                checked={s.statement_ids.includes(r.id)}
                                onCheckedChange={(on) => change(s.id, { statement_ids: toggle(s.statement_ids, r.id, on === true) })}
                              />
                              <span>
                                <span className="font-mono text-[12px]">{r.ref}</span> {r.text}
                              </span>
                            </label>
                          ))}
                        </fieldset>
                      )}
                    </li>
                  )
                })}
            </ul>
          </section>
        ))}

        {!disabled && (
          <div className="flex items-end gap-2">
            <div className="flex-1 space-y-1">
              <Label htmlFor="add-subsystem">New subsystem name</Label>
              <Input id="add-subsystem" maxLength={80} value={adding} onChange={(e) => setAdding(e.target.value)} />
            </div>
            <Button
              variant="secondary"
              disabled={!adding.trim() || subsystems.some((s) => s.name === adding.trim())}
              onClick={() => {
                const id = slugFor(adding, subsystems.map((s) => s.id))
                update([...subsystems, { id, name: adding.trim(), description: '', layer: 1, services: [], classes: [], depends_on: [], statement_ids: [] }])
                setAdding('')
              }}
            >
              <PlusIcon /> Add subsystem
            </Button>
          </div>
        )}
      </div>

      <aside className="space-y-4">
        {summary && (
          <section aria-label="Cohesion and coupling" className="rounded-xl border border-rule bg-field p-3">
            <h4 className="text-sm font-semibold">Cohesion and coupling</h4>
            {dirty && <p className="mt-1 text-xs text-slate">These values reflect the last saved version. Save to update them.</p>}
            <p className="mt-2 text-sm">
              Overall cohesion <span className="font-medium tabular-nums">{score(summary.cohesion)}</span>
            </p>
            <table className="mt-2 w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-slate">
                  <th className="font-medium">Subsystem</th>
                  <th className="font-medium">Cohesion</th>
                  <th className="font-medium">Coupling</th>
                </tr>
              </thead>
              <tbody>
                {summary.subsystems.map((m) => (
                  <tr key={m.id}>
                    <th scope="row" className="py-0.5 text-left font-normal">
                      {nameOf.get(m.id) ?? m.id}
                    </th>
                    <td className="tabular-nums">{score(m.cohesion)}</td>
                    <td className="tabular-nums">{m.coupling}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-xs text-slate">
              Cohesion: the share of the class relations a subsystem touches that stay inside it (higher is better). Coupling:
              how many other subsystems it is linked to (lower is better). A dash: no relations between extracted classes to
              measure.
            </p>
          </section>
        )}
        <section aria-label="Hints" className="rounded-xl border border-rule bg-field p-3">
          <h4 className="text-sm font-semibold">Hints</h4>
          <p className="mt-1 text-xs text-slate">
            Keep to about 7 ± 2 subsystems and 4 ± 2 layers (3 is a good default). A layer should depend only on layers below
            it. These never block confirming.
          </p>
          {summary && summary.warnings.length > 0 && (
            <ul className="mt-2 list-disc space-y-1 pl-4 text-sm">
              {summary.warnings.map((w) => (
                <li key={w.code + w.message}>{w.message}</li>
              ))}
            </ul>
          )}
        </section>
        <section aria-label="Package diagram" className="rounded-xl border border-rule bg-field p-3">
          <h4 className="text-sm font-semibold">Package diagram</h4>
          {confirmed ? (
            <PackageDiagram projectId={project.id} />
          ) : (
            <p className="mt-1 text-xs text-slate">The package diagram is drawn when you confirm this section.</p>
          )}
        </section>
      </aside>
    </div>
  )
}

/** The newest stored package diagram, drawn by the server when the section was confirmed. */
function PackageDiagram({ projectId }: { projectId: string }) {
  const diagrams = useDiagrams(projectId)
  const latest = diagrams.data?.filter((d) => d.type === 'package').sort((a, b) => b.created_at.localeCompare(a.created_at))[0]
  if (!latest) return diagrams.isPending ? <Spinner label="Loading the package diagram" /> : null
  return (
    <div className="mt-2 space-y-2">
      <DiagramImage id={latest.id} alt={latest.title} />
      <Link to={`/projects/${projectId}/diagrams/${latest.id}`} className="text-sm font-medium text-accent hover:underline">
        Open in the viewer
      </Link>
    </div>
  )
}

function DiagramImage({ id, alt }: { id: string; alt: string }) {
  const image = useDiagramImage(id)
  const [src, setSrc] = useState<string | null>(null)
  useEffect(() => {
    if (!image.data) return setSrc(null)
    const url = URL.createObjectURL(image.data)
    setSrc(url)
    return () => URL.revokeObjectURL(url)
  }, [image.data])
  if (image.isError) return <p className="text-xs text-slate">Couldn't load the diagram image.</p>
  return src ? <img src={src} alt={alt} className="w-full rounded-md border border-rule bg-white" /> : <Spinner label="Loading the package diagram" />
}
