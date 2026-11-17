/**
 * Formats offered by the viewer's Export menu for one diagram version. The backend renders the pictures from the stored
 * diagram source via Kroki (GET /diagrams/{id}/export?format=...); `source` returns that code itself. To add a format,
 * add an entry here and the matching key in the API's EXPORT_FORMATS; the menu, file names and download code pick it up.
 */
export const EXPORT_FORMATS = [
  { id: 'png', label: 'PNG image', hint: 'For slides and chat', extension: 'png' },
  { id: 'svg', label: 'SVG vector', hint: 'Sharp at any size, for reports', extension: 'svg' },
  { id: 'pdf', label: 'PDF document', hint: 'To attach to an SRS or assignment', extension: 'pdf' },
  // The extension depends on the engine that drew the diagram, so it comes from the response (sourceExtension).
  { id: 'source', label: 'Diagram source', hint: 'PlantUML / Graphviz code to edit in other tools', extension: null },
] as const

export type ExportFormat = (typeof EXPORT_FORMATS)[number]['id']

/** Media type of a `source` export -> file extension (matches the API's SOURCE_TYPES). */
const SOURCE_EXTENSIONS: Record<string, string> = {
  'text/x-plantuml': 'puml',
  'text/vnd.graphviz': 'dot',
  'text/x-mermaid': 'mmd',
}

/** "text/x-plantuml; charset=utf-8" -> "puml". Unknown types fall back to "txt". */
export function sourceExtension(mediaType: string) {
  return SOURCE_EXTENSIONS[mediaType.split(';')[0].trim().toLowerCase()] ?? 'txt'
}

/** The file extension for a downloaded export; `source` needs the response's media type. */
export function extensionFor(format: ExportFormat, mediaType = '') {
  return EXPORT_FORMATS.find((f) => f.id === format)!.extension ?? sourceExtension(mediaType)
}

export function slugify(text: string) {
  return (
    text
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-|-$/g, '') || 'diagram'
  )
}

/** "Library system · Use Case", version 2, "svg" -> "library-system-use-case-v2.svg". Version 1 gets no suffix. */
export function exportFilename(title: string, versionIndex: number, extension: string) {
  return `${slugify(title)}${versionIndex > 0 ? `-v${versionIndex + 1}` : ''}.${extension}`
}

/** "Library system" -> "library-system-diagrams.zip", or "...-diagrams-latest.zip" (the names the API suggests). */
export function zipFilename(projectName: string, versions: 'all' | 'latest' = 'all') {
  return `${slugify(projectName)}-diagrams${versions === 'latest' ? '-latest' : ''}.zip`
}
