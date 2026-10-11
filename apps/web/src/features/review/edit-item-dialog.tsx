import { useState, type FormEvent } from 'react'
import type { ExtractedItem } from '@/api/client'
import { errorMessage } from '@/api/errors'
import { useUpdateItem } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogTitle } from '@/components/ui/dialog'
import { FieldError, Input, Label, Textarea } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { categoryLabel } from './labels'

export function EditItemDialog({
  projectId,
  item,
  confirmed,
  onClose,
}: {
  projectId: string
  item: ExtractedItem | null
  confirmed: boolean
  onClose: () => void
}) {
  return (
    <Dialog open={!!item} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        {item && <EditForm key={item.id} projectId={projectId} item={item} confirmed={confirmed} onClose={onClose} />}
      </DialogContent>
    </Dialog>
  )
}

function EditForm({ projectId, item, confirmed, onClose }: { projectId: string; item: ExtractedItem; confirmed: boolean; onClose: () => void }) {
  const [name, setName] = useState(item.name)
  const [description, setDescription] = useState(item.description ?? '')
  const update = useUpdateItem(projectId)
  const changed = name.trim() !== item.name || description.trim() !== (item.description ?? '')

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    const ok = await update
      .mutateAsync({ itemId: item.id, name: name.trim(), description: description.trim() || null })
      .catch(() => null)
    if (ok) onClose()
  }

  return (
    <form onSubmit={onSubmit}>
      <DialogTitle>Edit {categoryLabel[item.category].toLowerCase()}</DialogTitle>
      <DialogDescription>
        Saving marks this item as edited by you, so re-extraction will never overwrite it.
        {confirmed && ' It also clears your confirmation; confirm again before generating.'}
      </DialogDescription>
      <div className="mt-5 space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="item-name">Name</Label>
          <Input id="item-name" value={name} onChange={(e) => setName(e.target.value)} aria-invalid={!name.trim()} />
          {!name.trim() && <FieldError>Name cannot be empty.</FieldError>}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="item-description">Description</Label>
          <Textarea id="item-description" value={description} onChange={(e) => setDescription(e.target.value)} />
        </div>
        {update.isError && <FieldError>{errorMessage(update.error)}</FieldError>}
      </div>
      <DialogFooter>
        <Button type="button" variant="secondary" onClick={onClose}>
          Cancel
        </Button>
        <Button type="submit" disabled={!changed || !name.trim() || update.isPending}>
          {update.isPending && <Spinner className="text-white" label="Saving" />}
          Save changes
        </Button>
      </DialogFooter>
    </form>
  )
}
