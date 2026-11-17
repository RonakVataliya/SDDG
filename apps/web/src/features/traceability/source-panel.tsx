import { XIcon } from 'lucide-react'
import type { DiagramDetail } from '@/api/client'
import { Button } from '@/components/ui/button'
import { RefTag } from '@/components/ui/badge'

/** Where a requirement came from: "Pasted text · page 2 · paragraph 4". */
export function sourceText(source: { document: string; page?: number | null; paragraph?: number | null }) {
  return [source.document, source.page ? `page ${source.page}` : null, source.paragraph ? `paragraph ${source.paragraph}` : null]
    .filter(Boolean)
    .join(' · ')
}

/**
 * FR17a: the requirements behind the element that is selected in the diagram. An element no requirement mentions
 * says so rather than showing nothing.
 */
export function SourcePanel({ diagram, elementId, onClose }: { diagram: DiagramDetail; elementId: string; onClose: () => void }) {
  const element = diagram.elements.find((e) => e.element_id === elementId)
  if (!element) return null
  const statements = diagram.statements.filter((s) => element.statement_ids.includes(s.id))

  return (
    <aside aria-label={`Sources for ${element.label}`} className="flex max-h-72 flex-col overflow-hidden rounded-lg border border-rule bg-surface xl:max-h-none">
      <div className="flex shrink-0 items-start justify-between gap-2 border-b border-rule px-4 py-3">
        <div className="min-w-0">
          <h3 className="truncate text-sm font-medium">{element.label}</h3>
          <p className="mt-0.5 text-xs text-slate">
            {element.kind.replace(/_/g, ' ')} ·{' '}
            {statements.length ? `${statements.length} source ${statements.length === 1 ? 'requirement' : 'requirements'}` : 'No source requirement'}
          </p>
        </div>
        <Button variant="ghost" size="icon" className="size-7 shrink-0" aria-label="Close sources" onClick={onClose}>
          <XIcon />
        </Button>
      </div>
      {statements.length === 0 ? (
        <p className="px-4 py-4 text-sm text-slate">
          No source requirement – assumption. Nothing in the requirements asks for this element; the generator added it.
        </p>
      ) : (
        <ul className="min-h-0 flex-1 divide-y divide-rule overflow-y-auto">
          {statements.map((s) => (
            <li key={s.id} className="px-4 py-3">
              <RefTag>{s.ref}</RefTag>
              <p className="mt-1.5 text-sm">{s.text}</p>
              <p className="mt-1 text-xs text-slate">{sourceText(s.source)}</p>
            </li>
          ))}
        </ul>
      )}
    </aside>
  )
}
