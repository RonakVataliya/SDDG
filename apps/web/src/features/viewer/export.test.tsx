import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { getExportedIds } from '@/features/search/exported'
import { env } from '@/lib/env'
import { server } from '@/mocks/node'
import { jpegToPdf } from './pdf'
import { useCaseSource } from '@/mocks/source'
import { crc32, makeZip } from '@/mocks/zip'
import { renderApp } from '@/test/render'
import { seedDiagram } from '@/test/seed'
import { ExportMenu } from './export-menu'
import { EXPORT_FORMATS, exportFilename, extensionFor, sourceExtension, zipFilename } from './export-formats'

describe('export file names', () => {
  it.each([
    ['Library system · Use Case', 0, 'svg', 'library-system-use-case.svg'],
    ['Library system · Use Case', 2, 'pdf', 'library-system-use-case-v3.pdf'],
    ['  ATM!!  ', 1, 'png', 'atm-v2.png'],
    ['···', 0, 'puml', 'diagram.puml'],
  ] as const)('%s, version index %i, .%s -> %s', (title, index, extension, expected) => {
    expect(exportFilename(title, index, extension)).toBe(expected)
  })

  it('offers PNG, SVG, PDF and the diagram source in that order', () => {
    expect(EXPORT_FORMATS.map((f) => f.id)).toEqual(['png', 'svg', 'pdf', 'source'])
  })

  it.each([
    ['text/x-plantuml; charset=utf-8', 'puml'],
    ['text/vnd.graphviz', 'dot'],
    ['TEXT/X-MERMAID;charset=UTF-8', 'mmd'],
    ['text/plain', 'txt'],
  ])('source served as %s is saved as .%s', (mediaType, extension) => {
    expect(sourceExtension(mediaType)).toBe(extension)
    expect(extensionFor('source', mediaType)).toBe(extension)
  })

  it('picture formats keep their own extension whatever the response says', () => {
    expect(extensionFor('pdf', 'application/octet-stream')).toBe('pdf')
  })

  it('names the project ZIP after the project', () => {
    expect(zipFilename('Hospital Management')).toBe('hospital-management-diagrams.zip')
    expect(zipFilename('Hospital Management', 'latest')).toBe('hospital-management-diagrams-latest.zip')
  })
})

describe('mock diagram source and ZIP writer', () => {
  it('writes a PlantUML use-case diagram from the mock model', () => {
    const source = useCaseSource({
      system: 'Library',
      actors: [{ id: 'a', name: 'Librarian' }],
      cases: [{ id: 'c', name: 'Issue book', assumed: false }],
      links: [{ actor: 'a', case: 'c' }],
    })
    expect(source.startsWith('@startuml')).toBe(true)
    expect(source.trimEnd().endsWith('@enduml')).toBe(true)
    expect(source).toContain('actor "Librarian" as A1')
    expect(source).toContain('A1 --> UC1')
  })

  it('uses the standard CRC-32', () => {
    expect(crc32(new TextEncoder().encode('123456789')).toString(16)).toBe('cbf43926')
  })

  it('writes a ZIP whose central directory lists every file', async () => {
    const blob = makeZip([
      { name: 'README.txt', data: 'hello\n' },
      { name: 'library-use-case/v1.puml', data: '@startuml\n@enduml\n' },
    ])
    expect(blob.type).toBe('application/zip')
    const view = new DataView(await blob.arrayBuffer())
    expect(view.getUint32(0, true)).toBe(0x04034b50) // starts with a local file header
    const end = view.byteLength - 22
    expect(view.getUint32(end, true)).toBe(0x06054b50) // ends with the end-of-central-directory record
    expect(view.getUint16(end + 10, true)).toBe(2) // two entries
    const centralStart = view.getUint32(end + 16, true)
    expect(view.getUint32(centralStart, true)).toBe(0x02014b50)
  })
})

describe('mock PDF writer', () => {
  it('writes a PDF whose cross-reference table points at every object', async () => {
    const jpeg = new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 1, 2, 3, 0xff, 0xd9])
    const blob = jpegToPdf(jpeg, 200, 100, 100, 50)
    expect(blob.type).toBe('application/pdf')
    const bytes = new Uint8Array(await blob.arrayBuffer())
    const text = new TextDecoder('latin1').decode(bytes)

    expect(text.startsWith('%PDF-1.4\n')).toBe(true)
    expect(text.trimEnd().endsWith('%%EOF')).toBe(true)
    expect(text).toContain('/MediaBox [0 0 75 37.5]') // 100 x 50 px page at 0.75 pt per px
    expect(text).toContain('/Width 200 /Height 100')

    const startxref = Number(/startxref\n(\d+)/.exec(text)![1])
    expect(text.slice(startxref, startxref + 4)).toBe('xref')
    const offsets = [...text.slice(startxref).matchAll(/^(\d{10}) 00000 n $/gm)].map((m) => Number(m[1]))
    expect(offsets).toHaveLength(5)
    offsets.forEach((o, i) => expect(text.slice(o, o + `${i + 1} 0 obj`.length)).toBe(`${i + 1} 0 obj`))
  })
})

describe('FR18 Export menu', () => {
  const saved: { name: string; type: string; blob?: Blob }[] = []
  const originalCreate = URL.createObjectURL
  const originalRevoke = URL.revokeObjectURL

  beforeEach(() => {
    saved.length = 0
    // jsdom has no object URLs or ResizeObserver (used by the menu's positioning); stub just enough for a download.
    let last: Blob | null = null
    URL.createObjectURL = vi.fn((obj: Blob | MediaSource) => {
      last = obj as Blob
      return 'blob:test'
    })
    URL.revokeObjectURL = vi.fn()
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      saved.push({ name: this.download, type: last?.type ?? '', ...(last ? { blob: last } : {}) })
    })
    globalThis.ResizeObserver ??= class {
      observe() {}
      unobserve() {}
      disconnect() {}
    } as unknown as typeof ResizeObserver
  })

  afterEach(() => {
    URL.createObjectURL = originalCreate
    URL.revokeObjectURL = originalRevoke
    vi.restoreAllMocks()
  })

  it('lists every format and downloads the SVG with a file name from the diagram title', async () => {
    seedDiagram()
    const user = userEvent.setup()
    renderApp('/projects/pr_1/diagrams/dg_1')
    await user.click(await screen.findByRole('button', { name: /export/i }))

    expect(await screen.findByRole('menuitem', { name: /PNG image/ })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: /PDF document/ })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: /Diagram source/ })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: /Latest diagrams \(ZIP\)/ })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: /All versions \(ZIP\)/ })).toBeInTheDocument()
    await user.click(screen.getByRole('menuitem', { name: /SVG vector/ }))

    await waitFor(() => expect(saved).toMatchObject([{ name: 'library-system-use-case.svg', type: 'image/svg+xml' }]))
    expect(getExportedIds()).toEqual(['dg_1']) // shows up under the Search page's "Exported" filter
  })

  it('downloads the diagram source as a .puml file', async () => {
    seedDiagram()
    const user = userEvent.setup()
    renderApp('/projects/pr_1/diagrams/dg_1')
    await user.click(await screen.findByRole('button', { name: /export/i }))
    await user.click(await screen.findByRole('menuitem', { name: /Diagram source/ }))

    await waitFor(() => expect(saved).toHaveLength(1))
    expect(saved[0].name).toBe('library-system-use-case.puml')
    expect(saved[0].type).toMatch(/^text\/x-plantuml/)
  })

  it.each([
    [/Latest diagrams \(ZIP\)/, 'library-system-diagrams-latest.zip'],
    [/All versions \(ZIP\)/, 'library-system-diagrams.zip'],
  ])('downloads the project ZIP from "%s" as %s', async (item, filename) => {
    seedDiagram()
    const user = userEvent.setup()
    renderApp('/projects/pr_1/diagrams/dg_1')
    await user.click(await screen.findByRole('button', { name: /export/i }))
    await user.click(await screen.findByRole('menuitem', { name: item }))

    await waitFor(() => expect(saved).toMatchObject([{ name: filename, type: 'application/zip' }]))
  })

  it('shows the server message when an export fails and keeps the page usable', async () => {
    seedDiagram()
    server.use(
      // Only the PDF request fails; anything else falls through to the normal mock handler.
      http.get(`${env.apiUrl.replace(/\/$/, '')}/diagrams/:diagram_id/export`, ({ request }) =>
        new URL(request.url).searchParams.get('format') === 'pdf'
          ? HttpResponse.json({ detail: 'Regenerate the diagram before exporting it.' }, { status: 409 })
          : undefined,
      ),
    )
    const user = userEvent.setup()
    renderApp('/projects/pr_1/diagrams/dg_1')
    await user.click(await screen.findByRole('button', { name: /export/i }))
    await user.click(await screen.findByRole('menuitem', { name: /PDF document/ }))

    expect(await screen.findByText('Regenerate the diagram before exporting it.')).toHaveAttribute('role', 'alert')
    expect(saved).toEqual([])
    expect(getExportedIds()).toEqual([]) // a failed export is not recorded
    expect(screen.getByRole('button', { name: /export/i })).toBeEnabled()
  })

  describe('a version with moved elements', () => {
    // The canvas on screen, with a box the user dragged to x=300. Kroki knows nothing of that position.
    function canvas() {
      const holder = document.createElement('div')
      holder.innerHTML =
        '<svg data-layout-canvas viewBox="0 0 400 200"><rect x="300" y="40" width="60" height="30"/><text x="310" y="60">Patient</text></svg>'
      document.body.append(holder)
      return holder.querySelector('svg')!
    }
    const menu = (drawn: () => SVGSVGElement | null, disabled = false) =>
      render(
        <ExportMenu diagramId="dg_1" title="Hospital · Use Case" versionIndex={1} projectId="pr_1" projectName="Hospital"
          drawn={drawn} disabled={disabled} />,
      )

    it('exports the SVG as drawn on screen, without asking the server', async () => {
      const svg = canvas()
      const requests: string[] = []
      server.events.on('request:start', ({ request }) => void requests.push(request.url))
      const user = userEvent.setup()
      menu(() => svg)
      await user.click(screen.getByRole('button', { name: /export/i }))
      await user.click(await screen.findByRole('menuitem', { name: /SVG vector/ }))

      await waitFor(() => expect(saved).toHaveLength(1))
      expect(saved[0]).toMatchObject({ name: 'hospital-use-case-v2.svg', type: 'image/svg+xml' })
      const markup = new TextDecoder().decode(await saved[0].blob!.arrayBuffer())
      expect(markup).toContain('x="300"') // the moved position
      expect(markup).toContain('Patient')
      expect(requests).toEqual([])
      server.events.removeAllListeners()
    })

    it('says the source has no moved positions', async () => {
      const user = userEvent.setup()
      menu(() => canvas())
      await user.click(screen.getByRole('button', { name: /export/i }))
      expect(await screen.findByRole('menuitem', { name: /Diagram source/ })).toHaveTextContent(/moved positions are not part of it/)
    })

    it('shows an error instead of a default-layout file when the canvas is not there yet', async () => {
      const user = userEvent.setup()
      menu(() => null)
      await user.click(screen.getByRole('button', { name: /export/i }))
      await user.click(await screen.findByRole('menuitem', { name: /SVG vector/ }))
      expect(await screen.findByRole('alert')).toHaveTextContent(/still loading/)
      expect(saved).toEqual([])
    })

    it('is disabled while elements are being moved', () => {
      menu(() => canvas(), true)
      expect(screen.getByRole('button', { name: /export/i })).toBeDisabled()
    })
  })
})
