import { useEffect, useState } from 'react'
import { Spinner } from '@/components/ui/spinner'
import { serverStatus, useServerWaking } from '@/lib/server-status'

/** FR30c. Shown while requests fail because the free-tier API is asleep; retries happen automatically. */
export function ServerWakingBanner() {
  const waking = useServerWaking()
  const [seconds, setSeconds] = useState(0)

  useEffect(() => {
    if (!waking) return
    const tick = () => setSeconds(Math.round((Date.now() - (serverStatus.since() ?? Date.now())) / 1000))
    tick()
    const t = setInterval(tick, 1000)
    return () => clearInterval(t)
  }, [waking])

  if (!waking) return null
  return (
    <div role="status" aria-live="polite" className="border-t border-amber/30 bg-amber-wash">
      <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-2 text-sm text-ink sm:px-6">
        <Spinner className="text-amber" label="Waiting for the server" />
        <p>
          <span className="font-medium">The server is starting.</span>{' '}
          <span className="text-ink/75">
            This takes up to a minute after a quiet period. We&rsquo;ll retry automatically
            {seconds >= 5 ? ` (${seconds}s)` : ''}.
          </span>
        </p>
      </div>
    </div>
  )
}
