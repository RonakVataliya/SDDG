/** Comments and issue reports (FR32, FR27a-b): a comment button for a requirement row or a diagram version, and the
 * side panel it opens. Any member, a Viewer too, can post; an Editor or Owner resolves any thread, anyone their own. */
import { CheckIcon, MessageSquareIcon } from 'lucide-react'
import { type FormEvent, useRef, useState } from 'react'
import type { Schemas } from '@/api/client'
import { errorMessage } from '@/api/errors'
import { useComments, useMembers, usePostComment, useResolveComment } from '@/api/queries'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { FieldError, Textarea } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { cn, formatRelative } from '@/lib/utils'
import { useWorkspace } from '@/routes/workspace-layout'

type Comment = Schemas['Comment']
type Member = Schemas['Member']
export type CommentTarget = {
  type: Schemas['CommentTargetType']
  id: string
  /** R-006, "Use Case diagram v3" or "Project". */
  label: string
  /** The requirement's text, shown in the panel only (never sent anywhere with the comment). */
  text?: string
}

const MAX = 2000
/** "priya@acme.test" -> "Priya" */
export const nameOf = (email: string | null | undefined) => {
  const local = (email ?? '').split('@')[0]
  return local ? local[0].toUpperCase() + local.slice(1) : 'Someone'
}

/** The comment icon with the number of open comments, if there are any. Opens the side panel. */
export function CommentsButton({ projectId, target, className }: { projectId: string; target: CommentTarget; className?: string }) {
  const [open, setOpen] = useState(false)
  const all = useComments(projectId, target.type) // one request for every row of this kind
  const openCount = (all.data ?? []).filter((c) => c.target_id === target.id && c.status === 'open').length
  return (
    <>
      <Button
        variant="ghost"
        size="sm"
        className={cn('h-7 shrink-0 gap-1 px-1.5 text-slate', className)}
        aria-label={`Comments on ${target.label}${openCount ? ` (${openCount} open)` : ''}`}
        onClick={() => setOpen(true)}
      >
        <MessageSquareIcon className="size-3.5" />
        {openCount > 0 && <span className="font-mono text-[11px]">{openCount}</span>}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        {open && <CommentsPanel projectId={projectId} target={target} />}
      </Dialog>
    </>
  )
}

function CommentsPanel({ projectId, target }: { projectId: string; target: CommentTarget }) {
  const { project } = useWorkspace()
  const thread = useComments(projectId, target.type, target.id)
  const members = useMembers(projectId).data ?? []
  const me = members.find((m) => m.is_you)?.user_id
  const comments = thread.data ?? []
  return (
    <DialogContent
      className="top-0 right-0 left-auto flex h-full max-h-none w-full max-w-md translate-x-0 translate-y-0 flex-col rounded-none rounded-l-2xl"
      aria-describedby={target.text ? 'comments-target-text' : undefined}
    >
      <DialogTitle>Comments {target.label}</DialogTitle>
      {target.text ? (
        <DialogDescription id="comments-target-text" className="line-clamp-3">
          {target.text}
        </DialogDescription>
      ) : (
        <DialogDescription className="sr-only">Comments on {target.label}</DialogDescription>
      )}

      <div className="mt-5 min-h-0 flex-1 overflow-y-auto">
        {thread.isPending ? (
          <Spinner label="Loading comments" />
        ) : thread.error ? (
          <FieldError>{errorMessage(thread.error)}</FieldError>
        ) : comments.length === 0 ? (
          <p className="text-sm text-slate">No comments yet.</p>
        ) : (
          <ol aria-label="Comments" className="flex flex-col gap-3">
            {comments.map((c) => (
              <CommentItem key={c.id} projectId={projectId} comment={c} canResolve={project.role !== 'viewer' || c.author.id === me} />
            ))}
          </ol>
        )}
      </div>

      <CommentForm projectId={projectId} target={target} members={members} />
    </DialogContent>
  )
}

function CommentItem({ projectId, comment: c, canResolve }: { projectId: string; comment: Comment; canResolve: boolean }) {
  const resolve = useResolveComment(projectId)
  return (
    <li className={cn('rounded-xl border border-rule p-3', c.status === 'resolved' && 'bg-field')}>
      <div className="flex flex-wrap items-center gap-2 text-[12px] text-slate">
        <span className="font-medium text-ink">{nameOf(c.author.email)}</span>
        <span>{formatRelative(c.created_at)}</span>
        {c.is_issue_report && <Badge tone="amber">Issue report</Badge>}
        {c.status === 'resolved' ? (
          <Badge tone="success" className="ml-auto">
            <CheckIcon /> Resolved by {c.resolved_by ?? 'someone'}
          </Badge>
        ) : (
          canResolve && (
            <Button size="sm" variant="ghost" className="ml-auto h-6 px-2" disabled={resolve.isPending} onClick={() => resolve.mutate(c.id)}>
              Resolve
            </Button>
          )
        )}
      </div>
      <p className="mt-1.5 text-[13.5px] leading-[21px] whitespace-pre-wrap">{c.body}</p>
      {resolve.error && <FieldError>{errorMessage(resolve.error)}</FieldError>}
    </li>
  )
}

/** The text box, with @ suggesting project members: picking one inserts @Name and remembers the person's id. */
function CommentForm({ projectId, target, members }: { projectId: string; target: CommentTarget; members: Member[] }) {
  const post = usePostComment(projectId)
  const [text, setText] = useState('')
  const [issue, setIssue] = useState(false)
  const [mentions, setMentions] = useState<Record<string, string>>({}) // @Name -> user id
  const [query, setQuery] = useState<string | null>(null) // the word after @ being typed, or null
  const box = useRef<HTMLTextAreaElement>(null)
  const trimmed = text.trim()
  const suggestions =
    query === null ? [] : members.filter((m) => !m.is_you && nameOf(m.email).toLowerCase().startsWith(query.toLowerCase())).slice(0, 5)

  function change(value: string, caret: number) {
    setText(value)
    const typed = /(?:^|\s)@([\w.-]*)$/.exec(value.slice(0, caret))
    setQuery(typed ? typed[1] : null)
  }

  function pick(m: Member) {
    const caret = box.current?.selectionStart ?? text.length
    const before = text.slice(0, caret).replace(/@[\w.-]*$/, `@${nameOf(m.email)} `)
    setText(before + text.slice(caret))
    setMentions((all) => ({ ...all, [`@${nameOf(m.email)}`]: m.user_id }))
    setQuery(null)
    box.current?.focus()
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!trimmed || trimmed.length > MAX || post.isPending) return
    const ids = Object.entries(mentions).filter(([name]) => trimmed.includes(name)).map(([, id]) => id)
    const ok = await post
      .mutateAsync({ target_type: target.type, target_id: target.id, body: trimmed, is_issue_report: issue, mentions: [...new Set(ids)] })
      .then(() => true)
      .catch(() => false)
    if (!ok) return // the error shows under the box; the text stays to fix and resend
    setText('')
    setIssue(false)
    setMentions({})
  }

  return (
    <form onSubmit={submit} className="mt-4 border-t border-rule pt-4">
      <div className="relative">
        <Textarea
          ref={box}
          aria-label="Comment"
          placeholder="Write a comment. Type @ to mention someone."
          value={text}
          maxLength={MAX + 200}
          onChange={(e) => change(e.target.value, e.target.selectionStart)}
          className="min-h-20"
        />
        {suggestions.length > 0 && (
          <ul role="listbox" aria-label="Mention a member" className="absolute bottom-full left-0 z-10 mb-1 w-64 rounded-lg border border-rule bg-surface p-1 shadow-[var(--shadow)]">
            {suggestions.map((m) => (
              <li key={m.user_id} role="none">
                <button type="button" role="option" aria-selected={false} className="w-full rounded-md px-2 py-1.5 text-left text-[13px] hover:bg-ink/5" onClick={() => pick(m)}>
                  <span className="font-medium">{nameOf(m.email)}</span> <span className="text-slate">{m.email}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      {trimmed.length > MAX && <FieldError>A comment can be at most {MAX} characters.</FieldError>}
      {post.error && <FieldError>{errorMessage(post.error)}</FieldError>}
      <div className="mt-3 flex items-center gap-2">
        <label className="flex items-center gap-2 text-[13px]">
          <Checkbox checked={issue} onCheckedChange={(v) => setIssue(v === true)} aria-label="Send as an issue report" />
          Send as an issue report
        </label>
        <Button type="submit" size="sm" className="ml-auto" disabled={!trimmed || trimmed.length > MAX || post.isPending}>
          {post.isPending && <Spinner className="text-on-ink" label="Posting" />}
          Post
        </Button>
      </div>
    </form>
  )
}
