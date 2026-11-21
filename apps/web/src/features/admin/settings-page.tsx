import type { AdminSettings } from '@/api/client'
import { errorMessage } from '@/api/errors'
import { useAdminSettings } from '@/api/queries'
import { Badge } from '@/components/ui/badge'
import { Notice } from '@/components/ui/notice'
import { PageLoading } from '@/components/ui/spinner'
import { plural } from '@/lib/utils'

const cap = (s: string) => s[0].toUpperCase() + s.slice(1)
const MB = 1048576
const MANAGED = 'Set in Supabase Auth'

function rows(s: AdminSettings): [string, string][] {
  const [main, ...fallbacks] = s.ai.providers
  const provider = !s.ai.reachable
    ? "Couldn't reach the AI service"
    : !main
      ? 'None configured'
      : `${cap(main.name)} - ${main.model}${fallbacks.length ? `, fallback: ${fallbacks.map((p) => cap(p.name)).join(', ')}` : ''}`
  const key = s.ai_key_set == null ? 'Unknown' : s.ai_key_set ? 'set - never sent to the browser' : 'not set'
  const minutes = Math.round(s.ai.job_deadline_seconds / 60)
  return [
    ['AI provider', provider],
    ['AI provider key', key],
    ['AI wait on rate limit', `A job waits up to ${plural(minutes, 'minute')} for AI capacity, then fails with a Retry button`],
    ['Storage limit', `${Math.round(s.storage_limit_bytes / MB)} MB`],
    ['Invitation expiry', plural(s.invitation_expiry_days, 'day')],
    ['Session timeout', s.session_timeout_hours == null ? MANAGED : `${plural(s.session_timeout_hours, 'hour')} of inactivity`],
    ['Failed logins before lock', s.failed_logins_before_lock == null ? MANAGED : `${s.failed_logins_before_lock}${s.lock_minutes ? `, ${s.lock_minutes} minute lock` : ''}`],
  ]
}

/** Read-only: what the server is configured with. A secret never reaches the browser, only whether it is set. */
export function AdminSettingsPage() {
  const settings = useAdminSettings()
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">Settings</h1>
        <Badge tone="neutral">Read only</Badge>
      </div>
      {settings.isPending ? (
        <PageLoading label="Loading settings" />
      ) : settings.isError ? (
        <Notice tone="error" title="Couldn't load settings">{errorMessage(settings.error)}</Notice>
      ) : (
        <dl className="divide-y divide-rule rounded-xl border border-rule">
          {rows(settings.data).map(([label, value]) => (
            <div key={label} className="grid gap-1 px-4 py-3 text-[13px] sm:grid-cols-[220px_1fr]">
              <dt className="font-medium text-ink-2">{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  )
}
