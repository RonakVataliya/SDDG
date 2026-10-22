import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import type { DiagramLayout, Point } from '@/api/client'
import { errorMessage } from '@/api/errors'
import { useSaveLayout } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { Notice } from '@/components/ui/notice'
import { Spinner } from '@/components/ui/spinner'
import { LayoutCanvas } from './layout-canvas'

const startPositions = (layout: DiagramLayout) => Object.fromEntries(layout.elements.map((e) => [e.id, { x: e.x, y: e.y }]))

/**
 * Move and reposition elements (issue #37). Moves stay in the browser until Save, which sends only the elements
 * that moved and opens the new version. A failed save keeps the moves on screen to try again.
 */
export function LayoutEditor({ projectId, layout, title, onClose }: { projectId: string; layout: DiagramLayout; title: string; onClose: () => void }) {
  const navigate = useNavigate()
  const save = useSaveLayout(projectId)
  const [positions, setPositions] = useState<Record<string, Point>>(() => startPositions(layout))

  const moved = layout.elements.filter((e) => positions[e.id].x !== e.x || positions[e.id].y !== e.y)

  useEffect(() => {
    if (!moved.length) return
    const warn = (e: BeforeUnloadEvent) => e.preventDefault() // the browser asks before throwing the moves away
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [moved.length])

  function move(ids: string[], dx: number, dy: number) {
    if (save.isPending) return
    if (save.isError) save.reset()
    setPositions((prev) => {
      const next = { ...prev }
      for (const id of ids) next[id] = { x: prev[id].x + dx, y: prev[id].y + dy }
      return next
    })
  }

  async function saveMoves() {
    if (!moved.length || save.isPending) return
    const body = Object.fromEntries(moved.map((e) => [e.id, { x: Math.round(positions[e.id].x), y: Math.round(positions[e.id].y) }]))
    const next = await save.mutateAsync({ diagramId: layout.diagram_id, positions: body }).catch(() => null)
    if (next) navigate(`../diagrams/${next.id}`)
  }

  return (
    <>
      <div className="relative mx-5 mt-3 h-[min(60vh,560px)] overflow-hidden rounded-lg border-2 border-teal/40 bg-white xl:h-auto xl:min-h-72 xl:flex-1">
        <LayoutCanvas
          elements={layout.elements}
          lines={layout.lines}
          positions={positions}
          onMove={move}
          label={`${title}: move elements`}
          className="p-2"
        />
        {save.isPending && (
          <div className="absolute inset-0 grid place-items-center bg-white/70 backdrop-blur-[1px]">
            <p className="flex items-center gap-2 rounded-full border border-rule bg-surface px-4 py-2 text-sm shadow-sm">
              <Spinner label="" /> Saving the new positions…
            </p>
          </div>
        )}
      </div>

      {save.isError && (
        <Notice tone="error" title="The new positions were not saved" className="mx-5 mt-3">
          {errorMessage(save.error)} Your moves are still here: try again, or cancel to put everything back.
        </Notice>
      )}

      <div className="mx-5 mt-3 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-slate" aria-live="polite">
          {moved.length
            ? `${moved.length} ${moved.length === 1 ? 'element' : 'elements'} moved, not saved yet.`
            : 'Drag an element to move it. Shift-click to pick several. Arrow keys move the picked ones (Shift for bigger steps).'}
        </p>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={onClose} disabled={save.isPending}>
            Cancel
          </Button>
          <Button onClick={saveMoves} disabled={!moved.length || save.isPending}>
            Save positions
          </Button>
        </div>
      </div>
    </>
  )
}
