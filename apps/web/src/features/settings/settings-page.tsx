import { useState, type FormEvent, type ReactNode } from 'react'
import { useNavigate } from 'react-router'
import { errorMessage } from '@/api/errors'
import { useArchiveProject, useDeleteProject, useRenameProject, useSetProjectClient } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { FieldError, Input, Label } from '@/components/ui/input'
import { Notice } from '@/components/ui/notice'
import { Spinner } from '@/components/ui/spinner'
import { StepHeading } from '@/features/input/input-page'
import { formatDate } from '@/lib/utils'
import { useWorkspace } from '@/routes/workspace-layout'

export function SettingsPage() {
  const { project } = useWorkspace()
  return (
    <div className="space-y-6">
      <StepHeading title="Project settings" />
      {project.is_owner ? (
        <>
          <RenameSection />
          <ClientSection />
          <ArchiveSection />
          <DeleteSection />
        </>
      ) : (
        <Notice title="Only the project owner can change these settings." />
      )}
    </div>
  )
}

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section aria-labelledby={id} className="max-w-xl space-y-3 border-t border-rule pt-5">
      <h3 id={id} className="font-medium">
        {title}
      </h3>
      {children}
    </section>
  )
}

function RenameSection() {
  const { project } = useWorkspace()
  const rename = useRenameProject(project.id)
  const [name, setName] = useState(project.name)
  const trimmed = name.trim()

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (trimmed && trimmed !== project.name) rename.mutate(trimmed)
  }

  return (
    <Section id="settings-name" title="Name">
      <form onSubmit={onSubmit} className="space-y-1.5">
        <Label htmlFor="settings-project-name">Project name</Label>
        <div className="flex gap-2">
          <Input
            id="settings-project-name"
            value={name}
            maxLength={100}
            aria-invalid={rename.isError}
            onChange={(e) => {
              setName(e.target.value)
              rename.reset()
            }}
          />
          <Button type="submit" variant="secondary" className="h-10" disabled={!trimmed || trimmed === project.name || rename.isPending}>
            {rename.isPending && <Spinner label="Renaming" />}
            Rename
          </Button>
        </div>
        <FieldError>{rename.isError && errorMessage(rename.error)}</FieldError>
      </form>
    </Section>
  )
}

function ClientSection() {
  const { project } = useWorkspace()
  const save = useSetProjectClient(project.id)
  const [client, setClient] = useState(project.client_name ?? '')
  const [contact, setContact] = useState(project.contact_email ?? '')

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    // Blank fields clear the value; the server returns the e-mail lowercased, so show what it stored.
    save.mutate(
      { client_name: client, contact_email: contact },
      {
        onSuccess: (p) => {
          setClient(p.client_name ?? '')
          setContact(p.contact_email ?? '')
        },
      },
    )
  }

  return (
    <Section id="settings-client" title="Client">
      <form onSubmit={onSubmit} className="space-y-3">
        <div className="space-y-1.5">
          <Label htmlFor="settings-client-name">Client name</Label>
          <Input id="settings-client-name" value={client} maxLength={100} onChange={(e) => setClient(e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="settings-contact-email">Contact e-mail</Label>
          <Input
            id="settings-contact-email"
            type="email"
            value={contact}
            maxLength={254}
            onChange={(e) => setContact(e.target.value)}
          />
        </div>
        <FieldError>{save.isError && errorMessage(save.error)}</FieldError>
        <Button type="submit" variant="secondary" disabled={save.isPending}>
          {save.isPending && <Spinner label="Saving" />}
          Save client
        </Button>
      </form>
    </Section>
  )
}

function ArchiveSection() {
  const { project } = useWorkspace()
  const archive = useArchiveProject(project.id)
  const archived = !!project.archived_at

  return (
    <Section id="settings-archive" title="Archive">
      <p className="text-sm text-slate">
        {project.archived_at
          ? `Archived ${formatDate(project.archived_at)}${project.archived_by ? ` by ${project.archived_by}` : ''}.`
          : 'Archived projects are listed apart on the Projects page. You can reopen them at any time.'}
      </p>
      <FieldError>{archive.isError && errorMessage(archive.error)}</FieldError>
      <Button variant="secondary" disabled={archive.isPending} onClick={() => archive.mutate(!archived)}>
        {archive.isPending && <Spinner label="Saving" />}
        {archived ? 'Reopen project' : 'Archive project'}
      </Button>
    </Section>
  )
}

function DeleteSection() {
  const { project } = useWorkspace()
  const del = useDeleteProject(project.id)
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [confirm, setConfirm] = useState('')
  const matches = confirm.trim() === project.name // the API trims confirm_name too

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (matches) del.mutate(confirm, { onSuccess: () => navigate('/projects', { replace: true }) })
  }

  return (
    <Section id="settings-delete" title="Delete">
      <p className="text-sm text-slate">Deletes the project and everything in it: requirements, diagrams and tests. This cannot be undone.</p>
      <Dialog
        open={open}
        onOpenChange={(o) => {
          setOpen(o)
          if (!o) {
            setConfirm('')
            del.reset()
          }
        }}
      >
        <DialogTrigger asChild>
          <Button variant="danger">Delete project…</Button>
        </DialogTrigger>
        <DialogContent>
          <DialogTitle>Delete this project?</DialogTitle>
          <DialogDescription>
            <strong className="text-ink">{project.name}</strong> and everything in it will be deleted for good.
          </DialogDescription>
          <form onSubmit={onSubmit} className="mt-5 space-y-1.5">
            <Label htmlFor="settings-delete-confirm">Type the project name to confirm</Label>
            <Input
              id="settings-delete-confirm"
              autoFocus
              autoComplete="off"
              value={confirm}
              onChange={(e) => {
                setConfirm(e.target.value)
                del.reset()
              }}
            />
            <FieldError>{del.isError && errorMessage(del.error)}</FieldError>
            <DialogFooter>
              <Button type="button" variant="secondary" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" variant="danger" disabled={!matches || del.isPending}>
                {del.isPending && <Spinner className="text-white" label="Deleting" />}
                Delete project
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </Section>
  )
}
