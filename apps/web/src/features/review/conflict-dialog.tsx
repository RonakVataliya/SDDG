/** Raj: edit conflict check (FR24f). Someone saved the requirement after you opened it, so your save was refused and
 * nothing was overwritten. Their version and your change side by side, changed words highlighted; you keep theirs,
 * go back, or copy your change on top of theirs and save the result as the next revision. */
import { useState, type ReactNode } from 'react'
import type { StatementConflict } from '@/api/client'
import { RefTag } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogTitle } from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { changedWords, mergeOnTop } from '@/lib/merge'
import { cn, formatRelative } from '@/lib/utils'

export function ConflictDialog({
  conflict,
  base,
  mine,
  saving,
  onCancel,
  onUseTheirs,
  onSave,
}: {
  conflict: StatementConflict
  /** The text the editor opened (revision conflict.base_revision). */
  base: string
  mine: string
  saving: boolean
  onCancel: () => void
  onUseTheirs: () => void
  /** Save this text on top of their revision. */
  onSave: (text: string) => void
}) {
  const theirs = conflict.current
  const revision = theirs.revision ?? conflict.base_revision + 1
  const who = conflict.changed_by
  const [result, setResult] = useState<string | null>(null)

  return (
    <Dialog open onOpenChange={(open) => !open && onCancel()}>
      <DialogContent className="max-w-4xl">
        <DialogTitle>Someone else changed {theirs.ref}</DialogTitle>
        <DialogDescription>
          {who} saved revision {revision} while you were editing revision {conflict.base_revision}. Nothing was overwritten.
        </DialogDescription>
        <div className={cn('mt-4 grid gap-3', result === null ? 'sm:grid-cols-2' : 'sm:grid-cols-3')}>
          <Card
            title={`${who}'s version · rev ${revision}${conflict.changed_at ? ` · ${formatRelative(conflict.changed_at)}` : ''}`}
            refTag={theirs.ref}
          >
            <Marked base={base} text={theirs.text} />
          </Card>
          <Card title={`Your change · based on rev ${conflict.base_revision}`} refTag={theirs.ref} accent>
            <Marked base={base} text={mine} />
          </Card>
          {result !== null && (
            <Card title={`Result · will be saved as rev ${revision + 1}`} refTag={theirs.ref} accent>
              <label htmlFor="conflict-result" className="sr-only">
                Result text
              </label>
              <Textarea id="conflict-result" value={result} onChange={(e) => setResult(e.target.value)} className="min-h-24 text-[13.5px]" />
            </Card>
          )}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
          <Button variant="secondary" onClick={onUseTheirs} disabled={saving}>
            Use {who}'s version
          </Button>
          {result === null ? (
            <Button onClick={() => setResult(mergeOnTop(base, mine, theirs.text))}>Copy my change on top</Button>
          ) : (
            <Button onClick={() => onSave(result.trim())} disabled={saving || !result.trim()}>
              {saving && <Spinner className="text-on-ink" label="Saving" />}
              Save as rev {revision + 1}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Card({ title, refTag, accent = false, children }: { title: string; refTag: string; accent?: boolean; children: ReactNode }) {
  return (
    <section aria-label={title} className={cn('rounded-lg border p-3', accent ? 'border-accent bg-accent-wash' : 'border-rule bg-paper')}>
      <h3 className="mb-2 flex flex-wrap items-center gap-2 text-[12.5px] font-semibold">
        <RefTag>{refTag}</RefTag> {title}
      </h3>
      {children}
    </section>
  )
}

/** The text with the words that differ from the base highlighted. */
function Marked({ base, text }: { base: string; text: string }) {
  return (
    <p className="text-[13.5px] whitespace-pre-wrap">
      {changedWords(base, text).map((t, i) =>
        t.changed ? (
          <mark key={i} className="rounded-[3px] bg-amber-wash px-0.5 text-ink">
            {t.text}
          </mark>
        ) : (
          <span key={i}>{t.text}</span>
        ),
      )}
    </p>
  )
}
