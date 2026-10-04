import { CircleAlertIcon, InfoIcon, TriangleAlertIcon } from 'lucide-react'
import type * as React from 'react'
import { cn } from '@/lib/utils'

const tones = {
  info: { cls: 'border-teal/25 bg-teal-wash text-teal-deep', Icon: InfoIcon },
  warning: { cls: 'border-amber/30 bg-amber-wash text-amber', Icon: TriangleAlertIcon },
  error: { cls: 'border-danger/25 bg-danger-wash text-danger', Icon: CircleAlertIcon },
}

export function Notice({
  tone = 'info',
  title,
  children,
  className,
  action,
}: {
  tone?: keyof typeof tones
  title?: React.ReactNode
  children?: React.ReactNode
  className?: string
  action?: React.ReactNode
}) {
  const { cls, Icon } = tones[tone]
  return (
    <div role={tone === 'error' ? 'alert' : 'status'} className={cn('flex gap-3 rounded-md border px-4 py-3 text-sm', cls, className)}>
      <Icon className="mt-0.5 size-4 shrink-0" />
      <div className="min-w-0 flex-1">
        {title && <p className="font-medium">{title}</p>}
        {children && <div className={cn(title && 'mt-0.5', 'text-ink/80')}>{children}</div>}
      </div>
      {action}
    </div>
  )
}
