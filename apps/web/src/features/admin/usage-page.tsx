import { CircleCheckIcon, TriangleAlertIcon } from 'lucide-react'
import type { AdminUsage } from '@/api/client'
import { errorMessage } from '@/api/errors'
import { useAdminUsage } from '@/api/queries'
import { Badge } from '@/components/ui/badge'
import { Notice } from '@/components/ui/notice'
import { PageLoading } from '@/components/ui/spinner'
import { cn } from '@/lib/utils'
import { ago } from './time'

const MB = 1048576
const mb = (bytes: number) => `${Math.round(bytes / MB)} MB`
const duration = (s: number | null) => (s == null ? '' : s < 60 ? `${s.toFixed(1)} s` : `${(s / 60).toFixed(1)} min`)
const EVENT = { slow: { label: 'Slow run', tone: 'amber' }, error: { label: 'Error', tone: 'danger' }, rate_limit: { label: 'Rate limit', tone: 'violet' } } as const

function Tile({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section aria-label={title} className="rounded-xl border border-rule p-4">
      <h2 className="text-[11px] font-semibold tracking-wider text-slate">{title}</h2>
      {children}
    </section>
  )
}

/** A bar for a value against its target, with a marker where the target is. */
function Bar({ value, max, mark, label, warn }: { value: number; max: number; mark?: number; label: string; warn?: boolean }) {
  const pct = (n: number) => `${Math.min(100, (n / max) * 100)}%`
  return (
    <div role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={max} aria-valuenow={Math.min(value, max)} className="relative mt-3 h-2 rounded-full bg-rule">
      <div className={cn('h-full rounded-full', warn ? 'bg-amber' : 'bg-accent')} style={{ width: pct(value) }} />
      {mark != null && <div className="absolute -top-1 h-4 w-0.5 bg-ink" style={{ left: pct(mark) }} />}
    </div>
  )
}

function Percentile({ title, seconds, target, ok }: { title: string; seconds: number | null; target: number; ok: boolean | null }) {
  return (
    <Tile title={title}>
      {seconds == null ? (
        <p className="mt-2 text-sm text-slate">No finished runs yet.</p>
      ) : (
        <>
          <p className="mt-1 text-3xl font-semibold">{Math.round(seconds)} s</p>
          <Bar value={seconds} max={Math.max(seconds, target) * 1.25} mark={target} label={`${title} against the ${target} s target`} warn={!ok} />
          <p className="mt-2 flex items-center gap-1.5 text-[13px] text-ink-2">
            Target {target} s
            {ok ? (
              <span className="inline-flex items-center gap-1 text-success"><CircleCheckIcon className="size-4" /> Within NFR1</span>
            ) : (
              <span className="inline-flex items-center gap-1 text-amber"><TriangleAlertIcon className="size-4" /> Over the target</span>
            )}
          </p>
        </>
      )}
    </Tile>
  )
}

function Body({ u }: { u: AdminUsage }) {
  const g = u.generation
  const pctStored = Math.round((u.storage_bytes / u.storage_limit_bytes) * 100)
  return (
    <>
      <div className="grid gap-4 md:grid-cols-3">
        <Tile title="ACTIVE USERS">
          <p className="mt-1 text-3xl font-semibold">{u.active_users} <span className="text-base font-normal text-slate">of {u.accounts} accounts</span></p>
          <p className="mt-2 text-[13px] text-slate">Signed in within the last {u.active_window_minutes} minutes</p>
        </Tile>
        <Tile title="PROJECTS">
          <p className="mt-1 text-3xl font-semibold">{u.projects}</p>
          <p className="mt-2 text-[13px] text-slate">{u.archived_projects} archived. Deleted projects are not counted.</p>
        </Tile>
        <Tile title="STORAGE">
          <p className="mt-1 text-3xl font-semibold">{mb(u.storage_bytes)}</p>
          <Bar value={u.storage_bytes} max={u.storage_limit_bytes} label="Storage used" warn={u.storage_warning} />
          <p className="mt-2 flex flex-wrap items-center gap-2 text-[13px] text-slate">
            {pctStored}% of the {mb(u.storage_limit_bytes)} limit
            {u.storage_warning && <Badge tone="amber">80% or more</Badge>}
          </p>
          <p className="mt-1 text-[12px] text-slate">
            Per project: {mb(u.limits.max_document_bytes)} per file, {u.limits.max_documents_per_project} documents, {u.limits.max_pages_per_project} pages
          </p>
        </Tile>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <Percentile title="GENERATION TIME: MEDIAN" seconds={g.median_seconds} target={g.median_target_seconds} ok={g.median_ok} />
        <Percentile title="GENERATION TIME: 95TH PERCENTILE" seconds={g.p95_seconds} target={g.p95_target_seconds} ok={g.p95_ok} />
      </div>
      <section aria-label="Slow runs and recent errors" className="space-y-2">
        <h2 className="text-[15px] font-semibold">Slow runs and recent errors</h2>
        <div className="overflow-x-auto rounded-xl border border-rule">
          <table className="w-full text-left text-[13px]">
            <thead className="border-b border-rule bg-field text-[12px] text-slate">
              <tr>
                {['Type', 'Description', 'Duration', 'When'].map((h) => <th key={h} className="px-3 py-2 font-medium">{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {u.events.map((e, i) => (
                <tr key={i} className="border-b border-rule last:border-0">
                  <td className="px-3 py-2"><Badge tone={EVENT[e.type].tone}>{EVENT[e.type].label}</Badge></td>
                  <td className="px-3 py-2">{e.description}</td>
                  <td className="px-3 py-2 text-ink-2">{duration(e.duration_seconds ?? null)}</td>
                  <td className="px-3 py-2 text-ink-2">{ago(e.at)}</td>
                </tr>
              ))}
              {!u.events.length && <tr><td colSpan={4} className="px-3 py-6 text-center text-slate">Nothing to report in the last {u.window_days} days.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </>
  )
}

/** FR25a-c, NFR1: how much the service is used and whether generation meets its time targets. */
export function UsagePage() {
  const usage = useAdminUsage()
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold">Usage</h1>
        <p className="text-[13px] text-slate">Last 7 days</p>
      </div>
      {usage.isPending ? (
        <PageLoading label="Loading usage" />
      ) : usage.isError ? (
        <Notice tone="error" title="Couldn't load usage">{errorMessage(usage.error)}</Notice>
      ) : (
        <Body u={usage.data} />
      )}
    </div>
  )
}
