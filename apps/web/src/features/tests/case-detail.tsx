import { PencilIcon, XIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import type { TestCase } from '@/api/client'
import { Badge, RefTag } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { KIND, PRIORITY, RESULT, TECHNIQUE } from './labels'

/** Everything a tester needs to run one case. Also used by the Runs tab's runner. */
export function CaseBody({ c }: { c: TestCase }) {
  const data = Object.entries(c.test_data)
  return (
    <div className="space-y-4 text-sm">
      {c.preconditions.length > 0 && (
        <Block title="Preconditions">
          <ul className="list-disc space-y-0.5 pl-5">
            {c.preconditions.map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        </Block>
      )}
      <Block title="Steps">
        {c.steps.length ? (
          <ol className="list-decimal space-y-0.5 pl-5">
            {c.steps.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ol>
        ) : (
          <p className="text-slate">Not written yet. Keep this draft and click Write steps on the Design tab.</p>
        )}
      </Block>
      {data.length > 0 && (
        <Block title="Test data">
          <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-0.5 font-mono text-[13px]">
            {data.map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="text-slate">{k}</dt>
                <dd>{v}</dd>
              </div>
            ))}
          </dl>
        </Block>
      )}
      <Block title="Expected result">
        <p className="font-medium">{c.expected ?? '—'}</p>
      </Block>
    </div>
  )
}

function Block({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h5 className="mb-1 text-xs font-semibold tracking-wide text-slate uppercase">{title}</h5>
      {children}
    </section>
  )
}

export function CaseDetail({ c, canEdit, onEdit, onClose }: { c: TestCase; canEdit: boolean; onEdit: () => void; onClose: () => void }) {
  return (
    <aside aria-label={`Case ${c.number}`} className="min-w-0 space-y-4 overflow-y-auto rounded-lg border border-rule bg-surface p-4">
      <div className="flex flex-wrap items-center gap-1.5">
        <RefTag>{c.number}</RefTag>
        <Badge title={TECHNIQUE[c.technique]}>{c.technique}</Badge>
        <Badge tone={KIND[c.kind].tone}>{KIND[c.kind].label}</Badge>
        <Badge>{PRIORITY[c.priority]}</Badge>
        <Badge tone={c.status === 'ready' ? 'teal' : 'neutral'} className="ml-auto">
          {c.status === 'ready' ? 'Ready' : 'Draft'}
        </Badge>
        <Button variant="ghost" size="icon" className="size-7" aria-label="Close case" onClick={onClose}>
          <XIcon />
        </Button>
      </div>
      <h4 className="font-semibold">
        {c.statement_ref} · {c.title}
      </h4>
      {c.freshness === 'out_of_date' && (
        <p className="rounded-md bg-amber-wash px-3 py-2 text-sm text-amber">
          Out of date: {c.statement_ref} changed after this case was written. Check it or regenerate the requirement.
        </p>
      )}
      <CaseBody c={c} />
      {c.covers.length > 0 && (
        <div className="flex flex-wrap gap-1">
          <span className="text-xs text-slate">Covers</span>
          {c.covers.map((t) => (
            <span key={t} className="rounded-sm bg-ink/6 px-1.5 font-mono text-[11px]">
              {t}
            </span>
          ))}
        </div>
      )}
      <div className="flex items-center justify-between border-t border-rule pt-3 text-xs text-slate">
        <span>
          {c.origin === 'manual' ? 'Written by hand' : c.status === 'ready' ? 'Steps written by AI request 2' : 'Draft built by code'}
          {c.last_result && ` · last result ${RESULT[c.last_result].label}`}
        </span>
        {canEdit && c.status === 'ready' && (
          <Button variant="secondary" size="sm" onClick={onEdit}>
            <PencilIcon /> Edit
          </Button>
        )}
      </div>
    </aside>
  )
}
