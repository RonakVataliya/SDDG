import { useState } from 'react'
import { errorMessage } from '@/api/errors'
import { useAdminFeedback, useCloseFeedback } from '@/api/queries'
import { Badge, RefTag } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { fieldClass } from '@/components/ui/input'
import { Notice } from '@/components/ui/notice'
import { PageLoading } from '@/components/ui/spinner'
import { ago } from './time'

const STATUSES = { open: 'Open', resolved: 'Resolved' } as const

/** FR27c (Raj): the issue reports members sent from any project. Only what they ticked "Send as an issue report" for,
 * and "On" names the requirement by its ref only, never its text. */
export function FeedbackPage() {
  const [status, setStatus] = useState<keyof typeof STATUSES | ''>('open')
  const [page, setPage] = useState(1)
  const feedback = useAdminFeedback(status, page)
  const close = useCloseFeedback()
  const data = feedback.data
  const first = data && data.total ? (data.page - 1) * data.page_size + 1 : 0
  const last = data ? Math.min(data.page * data.page_size, data.total) : 0

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">Feedback</h1>
        <p className="text-[13px] text-slate">Issue reports sent by members, newest first. Plain comments stay in their project.</p>
      </div>
      <select
        aria-label="Status"
        className={`${fieldClass} h-9 w-auto text-sm`}
        value={status}
        onChange={(e) => {
          setStatus(e.target.value as keyof typeof STATUSES | '')
          setPage(1)
        }}
      >
        <option value="">All</option>
        {Object.entries(STATUSES).map(([k, label]) => (
          <option key={k} value={k}>
            {label}
          </option>
        ))}
      </select>
      {close.error && <Notice tone="error" title="Couldn't close the report">{errorMessage(close.error)}</Notice>}
      {feedback.isPending ? (
        <PageLoading label="Loading feedback" />
      ) : feedback.isError ? (
        <Notice tone="error" title="Couldn't load feedback">
          {errorMessage(feedback.error)}
        </Notice>
      ) : (
        <>
          <div className="overflow-x-auto rounded-xl border border-rule">
            <table className="w-full text-left text-[13px]">
              <thead className="border-b border-rule bg-field text-[12px] text-slate">
                <tr>
                  {['Report', 'On', 'Project', 'From', 'Status', ''].map((h, i) => (
                    <th key={i} className="px-3 py-2 font-medium">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data!.reports.map((r) => (
                  <tr key={r.id} className="border-b border-rule align-top last:border-0">
                    <td className="max-w-md px-3 py-2">
                      <p className="whitespace-pre-wrap">{r.report}</p>
                      <p className="text-[12px] text-slate">{ago(r.at)}</p>
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap">{r.target_type === 'statement' && r.on ? <RefTag>{r.on}</RefTag> : r.on}</td>
                    <td className="px-3 py-2">{r.project_name}</td>
                    <td className="px-3 py-2">{r.from}</td>
                    <td className="px-3 py-2 whitespace-nowrap">
                      {r.status === 'open' ? <Badge tone="amber">Open</Badge> : <Badge tone="success">Resolved{r.resolved_by ? ` by ${r.resolved_by}` : ''}</Badge>}
                    </td>
                    <td className="px-3 py-2 text-right">
                      {r.status === 'open' && (
                        <Button size="sm" variant="secondary" aria-label={`Close the report on ${r.on ?? 'this'}`} disabled={close.isPending} onClick={() => close.mutate(r.id)}>
                          Close
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
                {!data!.reports.length && (
                  <tr>
                    <td colSpan={6} className="px-3 py-6 text-center text-slate">
                      {status === 'open' ? 'No open reports.' : status === 'resolved' ? 'No resolved reports.' : 'No reports yet.'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <div className="flex items-center justify-between text-[13px] text-slate">
            <span>
              {first}–{last} of {data!.total}
            </span>
            <div className="flex gap-2">
              <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                Previous
              </Button>
              <Button size="sm" variant="secondary" disabled={last >= data!.total} onClick={() => setPage(page + 1)}>
                Next
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
