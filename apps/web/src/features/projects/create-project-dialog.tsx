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
  const [client, setClient] = useState('')
  const [contact, setContact] = useState('')
  const create = useCreateProject()
  const navigate = useNavigate()
  const trimmed = name.trim()
  const tooLong = trimmed.length > MAX_NAME

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!trimmed || tooLong) return
    const project = await create.mutateAsync({ name: trimmed, client_name: client, contact_email: contact }).catch(() => null)
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
          setClient('')
          setContact('')
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
            aria-invalid={tooLong}
            aria-describedby="project-name-hint"
            onChange={(e) => {
              setName(e.target.value)
              create.reset()
            }}
          />
          <p id="project-name-hint" className={tooLong ? 'text-sm text-danger' : 'text-xs text-slate'}>
            {trimmed.length}/{MAX_NAME} characters
          </p>
          <Label htmlFor="project-client" className="mt-3 block">
            Client name <span className="font-normal text-slate">(optional)</span>
          </Label>
          <Input id="project-client" placeholder="e.g. Acme Retail" maxLength={100} value={client} onChange={(e) => setClient(e.target.value)} />
          <Label htmlFor="project-contact" className="mt-3 block">
            Client contact email <span className="font-normal text-slate">(optional)</span>
          </Label>
          <Input
            id="project-contact"
            type="email"
            placeholder="name@client.com"
            maxLength={254}
            value={contact}
            onChange={(e) => {
              setContact(e.target.value)
              create.reset()
            }}
          />
          {create.isError && <FieldError>{errorMessage(create.error)}</FieldError>}
          <DialogFooter>
            <Button type="button" variant="secondary" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!trimmed || tooLong || create.isPending}>
              {create.isPending && <Spinner className="text-on-ink" label="Creating" />}
              Create project
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
