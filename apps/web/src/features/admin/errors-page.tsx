import { useState } from 'react'
import type { AdminErrorSeverity, AdminErrorType } from '@/api/client'
import { errorMessage } from '@/api/errors'
import { useAdminErrors } from '@/api/queries'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { fieldClass } from '@/components/ui/input'
import { Notice } from '@/components/ui/notice'
import { PageLoading } from '@/components/ui/spinner'
import { ago } from './time'

const TYPES = { api: 'API crash', job: 'Failed job', ai: 'AI error', rate_limit: 'Rate limit' } as const
const SEVERITIES = { error: { label: 'Error', tone: 'danger' }, warning: { label: 'Warning', tone: 'amber' } } as const
const when = (iso: string) => new Date(iso).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit' })

/** FR25d: what went wrong recently. The server records kinds and IDs only, never document or requirement text. */
export function ErrorsPage() {
  const [type, setType] = useState<AdminErrorType | ''>('')
  const [severity, setSeverity] = useState<AdminErrorSeverity | ''>('')
  const [page, setPage] = useState(1)
  const errors = useAdminErrors(type, severity, page)
  const data = errors.data
  const first = data && data.total ? (data.page - 1) * data.page_size + 1 : 0
  const last = data ? Math.min(data.page * data.page_size, data.total) : 0
  const select = `${fieldClass} h-9 w-auto text-sm`

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">Errors</h1>
        <p className="text-[13px] text-slate">Newest first. Only kinds and IDs are recorded, never the text of a document or requirement.</p>
      </div>
      <div className="flex flex-wrap gap-3">
        <select aria-label="Type" className={select} value={type} onChange={(e) => { setType(e.target.value as AdminErrorType | ''); setPage(1) }}>
          <option value="">All types</option>
          {Object.entries(TYPES).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
        </select>
        <select aria-label="Severity" className={select} value={severity} onChange={(e) => { setSeverity(e.target.value as AdminErrorSeverity | ''); setPage(1) }}>
          <option value="">All severities</option>
          {Object.entries(SEVERITIES).map(([k, s]) => <option key={k} value={k}>{s.label}</option>)}
        </select>
      </div>
      {errors.isPending ? (
        <PageLoading label="Loading errors" />
      ) : errors.isError ? (
        <Notice tone="error" title="Couldn't load errors">{errorMessage(errors.error)}</Notice>
      ) : (
        <>
          <div className="overflow-x-auto rounded-xl border border-rule">
            <table className="w-full text-left text-[13px]">
              <thead className="border-b border-rule bg-field text-[12px] text-slate">
                <tr>{['When', 'Type', 'Severity', 'Description'].map((h) => <th key={h} className="px-3 py-2 font-medium">{h}</th>)}</tr>
              </thead>
              <tbody>
                {data!.errors.map((e) => (
                  <tr key={e.id} className="border-b border-rule last:border-0">
                    <td className="whitespace-nowrap px-3 py-2">{when(e.at)} <span className="text-slate">({ago(e.at)})</span></td>
                    <td className="px-3 py-2"><Badge tone="neutral">{TYPES[e.type]}</Badge></td>
                    <td className="px-3 py-2"><Badge tone={SEVERITIES[e.severity].tone}>{SEVERITIES[e.severity].label}</Badge></td>
                    <td className="px-3 py-2">{e.message}</td>
                  </tr>
                ))}
                {!data!.errors.length && <tr><td colSpan={4} className="px-3 py-6 text-center text-slate">No errors recorded{type || severity ? ' for this filter' : ''}.</td></tr>}
              </tbody>
            </table>
          </div>
          <div className="flex items-center justify-between text-[13px] text-slate">
            <span>{first}–{last} of {data!.total}</span>
            <div className="flex gap-2">
              <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button>
              <Button size="sm" variant="secondary" disabled={last >= data!.total} onClick={() => setPage(page + 1)}>Next</Button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
