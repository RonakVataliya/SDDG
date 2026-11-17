import { CircleAlertIcon, CircleCheckIcon, InfoIcon, XIcon } from 'lucide-react'
import { dismissToast, useToasts } from '@/lib/toast'
import { cn } from '@/lib/utils'

const tones = {
  success: { cls: 'border-teal/30', Icon: CircleCheckIcon, icon: 'text-teal' },
  info: { cls: 'border-rule-strong', Icon: InfoIcon, icon: 'text-slate' },
  error: { cls: 'border-danger/30', Icon: CircleAlertIcon, icon: 'text-danger' },
}

/** Mounted once in the app layout; toast() in lib/toast.ts puts messages here. */
export function Toaster() {
  const toasts = useToasts()
  return (
    <div className="pointer-events-none fixed right-4 bottom-4 z-[60] flex w-[min(24rem,calc(100vw-2rem))] flex-col gap-2" aria-live="polite">
      {toasts.map((t) => {
        const { cls, Icon, icon } = tones[t.tone]
        return (
          <div
            key={t.id}
            role={t.tone === 'error' ? 'alert' : 'status'}
            className={cn('pointer-events-auto flex items-start gap-2.5 rounded-md border bg-surface px-3.5 py-3 text-sm shadow-lg', cls)}
          >
            <Icon className={cn('mt-0.5 size-4 shrink-0', icon)} aria-hidden />
            <p className="min-w-0 flex-1">{t.message}</p>
            <button type="button" className="rounded-sm p-0.5 text-slate hover:text-ink" aria-label="Dismiss" onClick={() => dismissToast(t.id)}>
              <XIcon className="size-3.5" />
            </button>
          </div>
        )
      })}
    </div>
  )
}
