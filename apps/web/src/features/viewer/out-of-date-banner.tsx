import { useState } from 'react'
import { Link } from 'react-router'
import type { DiagramType } from '@/api/client'
import { useDiagrams } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { Notice } from '@/components/ui/notice'
import { typeLabel } from '@/features/generate/diagram-types'

/** FR17c: after a requirement changes, says which diagrams no longer match and offers to draw them again. "Later" hides
 * it until the next change; the Out of date badges stay on the diagrams, and only a new generation clears them. */
export function OutOfDateBanner({ projectId, confirmed, canGenerate }: { projectId: string; confirmed: boolean; canGenerate: boolean }) {
  const { data } = useDiagrams(projectId)
  const [later, setLater] = useState('')
  const types = [...new Set((data ?? []).filter((d) => d.out_of_date).map((d) => d.type))] as DiagramType[]
  const key = types.join(',')
  if (!canGenerate || !types.length || later === key) return null
  return (
    <Notice tone="warning" title="Requirements changed" className="mx-4 mt-3 sm:mx-6">
      <span>
        {types.map((t) => typeLabel[t]).join(', ')} {types.length === 1 ? 'diagram is' : 'diagrams are'} out of date.
        {!confirmed && ' Confirm the changed requirements first, then draw them again.'}
      </span>
      <span className="mt-2 flex gap-2">
        <Button asChild size="sm">
          <Link to={`/projects/${projectId}/${confirmed ? 'generate' : 'review'}`}>Regenerate now</Link>
        </Button>
        <Button size="sm" variant="secondary" onClick={() => setLater(key)}>
          Later
        </Button>
      </span>
    </Notice>
  )
}
