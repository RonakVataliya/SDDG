import { ServerIcon } from 'lucide-react'
import { useEffect, useState } from 'react'
import { serverStatus, useServerWaking } from '@/lib/server-status'

/** FR30c. Shown only while requests fail because the free-tier API is asleep (502/503/504 or no answer). */
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
      <div className="flex items-center gap-3 px-5 py-2 text-[13px] text-amber">
        <ServerIcon className="size-4 shrink-0" aria-hidden />
        <p>
          <span className="font-semibold">The server is waking up.</span>{' '}
          <span className="text-ink/75">Free hosting sleeps when idle; this takes about a minute. Nothing is lost, and the page fills in by itself.</span>
        </p>
        {seconds >= 5 && <span className="ml-auto font-mono text-[11.5px]">retrying · {seconds}s</span>}
      </div>
    </div>
  )
}
