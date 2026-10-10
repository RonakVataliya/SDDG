import { useState, type FormEvent, type ReactNode } from 'react'
import { useNavigate } from 'react-router'
import { errorMessage } from '@/api/errors'
import { useCreateProject } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { FieldError, Input, Label } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'

const MAX_NAME = 100

export function CreateProjectDialog({ trigger }: { trigger: ReactNode }) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const create = useCreateProject()
  const navigate = useNavigate()
  const trimmed = name.trim()
  const tooLong = trimmed.length > MAX_NAME

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!trimmed || tooLong) return
    const project = await create.mutateAsync(trimmed).catch(() => null)
    if (!project) return
    setOpen(false)
    navigate(`/projects/${project.id}/input`)
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        setOpen(o)
        if (!o) {
          setName('')
          create.reset()
        }
      }}
    >
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogTitle>New project</DialogTitle>
        <DialogDescription>One project holds one system&rsquo;s requirements and the diagrams made from them.</DialogDescription>
        <form onSubmit={onSubmit} className="mt-5 space-y-1.5">
          <Label htmlFor="project-name">Project name</Label>
          <Input
            id="project-name"
            autoFocus
            placeholder="e.g. Library management system"
            value={name}
            aria-invalid={tooLong || create.isError}
            aria-describedby="project-name-hint"
            onChange={(e) => {
              setName(e.target.value)
              create.reset()
            }}
          />
          {create.isError ? (
            <FieldError id="project-name-hint">{errorMessage(create.error)}</FieldError>
          ) : (
            <p id="project-name-hint" className={tooLong ? 'text-sm text-danger' : 'text-xs text-slate'}>
              {trimmed.length}/{MAX_NAME} characters
            </p>
          )}
          <DialogFooter>
            <Button type="button" variant="secondary" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!trimmed || tooLong || create.isPending}>
              {create.isPending && <Spinner className="text-white" label="Creating" />}
              Create project
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
