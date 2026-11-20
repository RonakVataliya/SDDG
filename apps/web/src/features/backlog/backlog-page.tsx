import { PencilIcon, PlusIcon, Trash2Icon } from 'lucide-react'
import { useState } from 'react'
import { useSearchParams } from 'react-router'
import type { RequirementStatement, Story, StoryStatus } from '@/api/client'
import { errorMessage } from '@/api/errors'
import { useDeleteStory, useStatements, useStories, useUpdateStory } from '@/api/queries'
import { Badge, RefTag } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { FieldError, fieldClass, Label } from '@/components/ui/input'
import { Notice } from '@/components/ui/notice'
import { PageLoading, Spinner } from '@/components/ui/spinner'
import { StepHeading } from '@/features/input/input-page'
import { cn } from '@/lib/utils'
import { useWorkspace } from '@/routes/workspace-layout'
import { PRIORITY, STATUS } from './labels'
import { StoryDialog } from './story-dialog'

const selectClass = cn(fieldClass, 'h-9 text-sm')

/** 3.4: the project's user stories, each written against one or more requirements. */
export function BacklogPage() {
  const { project } = useWorkspace()
  const stories = useStories(project.id)
  const statements = useStatements(project.id)
  const [params, setParams] = useSearchParams()
  const requirement = params.get('requirement') ?? '' // set by the review page: stories of this requirement
  const [status, setStatus] = useState('')
  const [priority, setPriority] = useState('')
  const [assignee, setAssignee] = useState('')
  const [dialog, setDialog] = useState<{ story?: Story } | null>(null)

  if (stories.isPending || statements.isPending) return <PageLoading label="Loading the backlog" />
  if (!stories.data || !statements.data)
    return (
      <Notice tone="error" title="Couldn't load the backlog">
        {errorMessage(stories.error ?? statements.error)}
      </Notice>
    )

  const { members } = stories.data
  const requirements = statements.data
  const shown = stories.data.stories.filter(
    (s) =>
      (!status || s.status === status) &&
      (!priority || s.priority === priority) &&
      (!assignee || (s.assignee_id ?? 'none') === assignee) &&
      (!requirement || s.statement_ids.includes(requirement)),
  )

  return (
    <div className="space-y-5">
      <StepHeading
        title="Backlog"
        description="User stories: As a [user role] I want to [goal] so I can [reason]. Each one links to the requirements it delivers."
        actions={
          <div className="flex flex-col items-end gap-1">
            <Button size="sm" disabled={!requirements.length} onClick={() => setDialog({})}>
              <PlusIcon /> New story
            </Button>
            {!requirements.length && <span className="text-xs text-slate">Add requirements first.</span>}
          </div>
        }
      />

      {stories.data.stories.length === 0 ? (
        <Notice title="No stories yet">Stories are written against requirements: each one links to at least one requirement it delivers.</Notice>
      ) : (
        <>
          <div className="flex flex-wrap gap-3">
            <Filter label="Filter by status" value={status} onChange={setStatus} options={Object.entries(STATUS)} all="Any status" />
            <Filter label="Filter by priority" value={priority} onChange={setPriority} options={Object.entries(PRIORITY)} all="Any priority" />
            <Filter
              label="Filter by assignee"
              value={assignee}
              onChange={setAssignee}
              options={[['none', 'Unassigned'], ...members.map((m) => [m.id, m.email] as [string, string])]}
              all="Anyone"
            />
            <Filter
              label="Filter by requirement"
              value={requirement}
              onChange={(v) => setParams(v ? { requirement: v } : {}, { replace: true })}
              options={requirements.map((r) => [r.id, `${r.ref} · ${r.text.slice(0, 50)}`] as [string, string])}
              all="Any requirement"
            />
          </div>
          {shown.length === 0 ? (
            <p className="text-sm text-slate">No story matches these filters.</p>
          ) : (
            <ul aria-label="Stories" className="divide-y divide-rule rounded-xl border border-rule bg-field">
              {shown.map((s) => (
                <StoryRow key={s.id} projectId={project.id} story={s} requirements={requirements} onEdit={() => setDialog({ story: s })} />
              ))}
            </ul>
          )}
        </>
      )}

      {dialog && (
        <StoryDialog
          projectId={project.id}
          onOpenChange={(o) => !o && setDialog(null)}
          requirements={requirements}
          members={members}
          existing={dialog.story}
        />
      )}
    </div>
  )
}

function Filter({
  label,
  value,
  onChange,
  options,
  all,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  options: [string, string][]
  all: string
}) {
  const id = `filter-${label.split(' ').at(-1)}`
  return (
    <div className="w-44 space-y-1">
      <Label htmlFor={id} className="sr-only">
        {label}
      </Label>
      <select id={id} className={selectClass} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{all}</option>
        {options.map(([k, v]) => (
          <option key={k} value={k}>
            {v}
          </option>
        ))}
      </select>
    </div>
  )
}

function StoryRow({ projectId, story: s, requirements, onEdit }: { projectId: string; story: Story; requirements: RequirementStatement[]; onEdit: () => void }) {
  const update = useUpdateStory(projectId)
  const remove = useDeleteStory(projectId)
  const [confirming, setConfirming] = useState(false)
  const refs = requirements.filter((r) => s.statement_ids.includes(r.id)).map((r) => r.ref)
  return (
    <li data-story={s.ref} className="space-y-2 px-4 py-3 text-sm">
      <div className="flex flex-wrap items-start gap-3">
        <RefTag className="h-fit shrink-0">{s.ref}</RefTag>
        <p className="min-w-0 flex-1">
          As a <strong className="font-medium">{s.role}</strong> I want to <strong className="font-medium">{s.goal}</strong> so I can{' '}
          <strong className="font-medium">{s.reason}</strong>
        </p>
        <label htmlFor={`status-${s.id}`} className="sr-only">
          Status of {s.ref}
        </label>
        <select
          id={`status-${s.id}`}
          className={cn(selectClass, 'w-32')}
          value={s.status}
          disabled={update.isPending}
          onChange={(e) => update.mutate({ storyId: s.id, body: { status: e.target.value as StoryStatus } })}
        >
          {Object.entries(STATUS).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
        {confirming ? (
          <span className="flex shrink-0 items-center gap-1">
            <Button size="sm" variant="danger" disabled={remove.isPending} onClick={() => remove.mutate(s.id)}>
              {remove.isPending && <Spinner className="text-white" label="Deleting" />}
              Delete {s.ref}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setConfirming(false)}>
              Keep
            </Button>
          </span>
        ) : (
          <span className="flex shrink-0 gap-0.5">
            <Button variant="ghost" size="icon" className="size-8" aria-label={`Edit ${s.ref}`} onClick={onEdit}>
              <PencilIcon />
            </Button>
            <Button variant="ghost" size="icon" className="size-8" aria-label={`Delete ${s.ref}`} onClick={() => setConfirming(true)}>
              <Trash2Icon />
            </Button>
          </span>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-2 text-slate">
        <Badge tone={s.priority === 'must' ? 'accent' : 'neutral'}>{PRIORITY[s.priority]}</Badge>
        {s.estimate != null && <span>{s.estimate} pts</span>}
        <span>{s.assignee_email ?? 'Unassigned'}</span>
        {refs.length ? refs.map((r) => <RefTag key={r}>{r}</RefTag>) : <Badge tone="danger">Needs a requirement</Badge>}
      </div>
      {s.confirmations.length > 0 && (
        <ul aria-label={`Confirmations of ${s.ref}`} className="list-disc space-y-0.5 pl-5 text-slate">
          {s.confirmations.map((c, i) => (
            <li key={i}>{c}</li>
          ))}
        </ul>
      )}
      <FieldError>{update.isError ? errorMessage(update.error) : remove.isError ? errorMessage(remove.error) : null}</FieldError>
    </li>
  )
}
