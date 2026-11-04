import { ChevronDownIcon, DownloadIcon } from 'lucide-react'
import { DropdownMenu as M } from 'radix-ui'
import { useState } from 'react'
import { errorMessage } from '@/api/errors'
import { fetchDiagramExport, fetchProjectDiagramsZip, saveBlob } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { markExported } from '@/features/search/exported'
import { exportDrawn } from './export-drawn'
import { EXPORT_FORMATS, exportFilename, extensionFor, zipFilename, type ExportFormat } from './export-formats'

type Props = {
  diagramId: string
  title: string
  /** 0-based position in the version list; versions after the first get a -v2, -v3 ... suffix. */
  versionIndex: number
  /** The PNG the viewer already loaded, reused so PNG export needs no second request. */
  png?: Blob
  /** For "All diagrams (ZIP)": the project this diagram belongs to. */
  projectId: string
  projectName: string
  /** Set for a version whose elements were moved: returns the canvas on screen, so PNG/SVG/PDF are made from what the
   *  user sees (Kroki would draw the default layout). The source still comes from the API. */
  drawn?: () => SVGSVGElement | null
  /** Disables the menu, e.g. while elements are being moved. */
  disabled?: boolean
}

type ZipVersions = 'latest' | 'all'
type Busy = ExportFormat | `zip-${ZipVersions}` | null

const itemClass =
  'flex cursor-pointer flex-col items-start rounded-sm px-3 py-2 text-sm outline-none data-[highlighted]:bg-teal-wash'

/** FR18: Export ▾ menu. One diagram version in any EXPORT_FORMATS format, or every diagram of the project as a ZIP.
 *  Errors show under the button; the page keeps working. */
export function ExportMenu({ diagramId, title, versionIndex, png, projectId, projectName, drawn, disabled = false }: Props) {
  const [busy, setBusy] = useState<Busy>(null)
  const [error, setError] = useState<string | null>(null)

  async function run(what: Exclude<Busy, null>, task: () => Promise<void>) {
    setBusy(what)
    setError(null)
    try {
      await task()
    } catch (e) {
      const name = what.startsWith('zip') ? 'ZIP' : what === 'source' ? 'source' : what.toUpperCase()
      setError(errorMessage(e, `The ${name} export did not work. Try again.`))
    } finally {
      setBusy(null)
    }
  }

  const downloadOne = (format: ExportFormat) =>
    run(format, async () => {
      const svg = drawn?.()
      if (drawn && !svg) throw new Error('The diagram is still loading. Try again in a moment.')
      const local = svg ? exportDrawn(svg, format) : null
      const blob = local ? await local : format === 'png' && png ? png : await fetchDiagramExport(diagramId, format)
      saveBlob(blob, exportFilename(title, versionIndex, extensionFor(format, blob.type)))
      markExported(diagramId) // the Search page's "Exported" filter reads this
    })

  const downloadZip = (versions: ZipVersions) =>
    run(`zip-${versions}`, async () => {
      saveBlob(await fetchProjectDiagramsZip(projectId, versions), zipFilename(projectName, versions))
    })

  const busyLabel = busy?.startsWith('zip') ? 'Preparing ZIP…' : busy === 'source' ? 'Exporting source…' : `Exporting ${busy?.toUpperCase()}…`

  return (
    <div className="flex flex-col items-end gap-1.5">
      <M.Root>
        <M.Trigger asChild>
          <Button variant="secondary" disabled={disabled || busy !== null}>
            {busy ? <Spinner label="" /> : <DownloadIcon />}
            {busy ? busyLabel : 'Export'}
            <ChevronDownIcon aria-hidden />
          </Button>
        </M.Trigger>
        <M.Portal>
          <M.Content
            align="end"
            sideOffset={6}
            className="z-50 min-w-64 rounded-md border border-rule bg-surface p-1 shadow-[0_12px_32px_-12px_rgb(26_34_51/0.3)]"
          >
            <M.Label className="px-3 pt-1.5 pb-1 text-xs font-medium text-slate">This version</M.Label>
            {EXPORT_FORMATS.map((f) => (
              <M.Item key={f.id} onSelect={() => void downloadOne(f.id)} className={itemClass}>
                <span className="font-medium text-ink">{f.label}</span>
                <span className="text-xs text-slate">
                  {drawn && f.id === 'source' ? 'The code only; moved positions are not part of it' : f.hint}
                </span>
              </M.Item>
            ))}
            <M.Separator className="my-1 h-px bg-rule" />
            <M.Label className="px-3 pt-1.5 pb-1 text-xs font-medium text-slate">This project</M.Label>
            <M.Item onSelect={() => void downloadZip('latest')} className={itemClass}>
              <span className="font-medium text-ink">Latest diagrams (ZIP)</span>
              <span className="text-xs text-slate">Latest version of every diagram: PNG, SVG, PDF and source</span>
            </M.Item>
            <M.Item onSelect={() => void downloadZip('all')} className={itemClass}>
              <span className="font-medium text-ink">All versions (ZIP)</span>
              <span className="text-xs text-slate">Every version of every diagram, a folder per version</span>
            </M.Item>
            <p className="max-w-64 px-3 pt-1 pb-1.5 text-xs text-slate">
              ZIP pictures use the default layout. For moved elements, export that version above.
            </p>
          </M.Content>
        </M.Portal>
      </M.Root>
      {error && (
        <p role="alert" className="max-w-72 text-right text-xs text-danger">
          {error}
        </p>
      )}
    </div>
  )
}
