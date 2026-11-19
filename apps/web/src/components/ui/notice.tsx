import { CircleAlertIcon, InfoIcon, TriangleAlertIcon } from 'lucide-react'
import type * as React from 'react'
import { cn } from '@/lib/utils'

const tones = {
  info: { cls: 'bg-accent-wash text-accent-deep', Icon: InfoIcon },
  warning: { cls: 'bg-amber-wash text-amber', Icon: TriangleAlertIcon },
  error: { cls: 'bg-danger-wash text-danger', Icon: CircleAlertIcon },
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
    <div role={tone === 'error' ? 'alert' : 'status'} className={cn('flex gap-3 rounded-[10px] px-4 py-3 text-[13px]', cls, className)}>
      <Icon className="mt-0.5 size-4 shrink-0" />
      <div className="min-w-0 flex-1">
        {title && <p className="font-semibold">{title}</p>}
        {children && <div className={cn(title && 'mt-0.5', 'text-ink/80')}>{children}</div>}
      </div>
      {action}
    </div>
  )
}
