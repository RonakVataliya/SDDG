import { XIcon } from 'lucide-react'
import { Dialog as D } from 'radix-ui'
import type * as React from 'react'
import { cn } from '@/lib/utils'

export const Dialog = D.Root
export const DialogTrigger = D.Trigger
export const DialogClose = D.Close

export function DialogContent({
  className,
  children,
  ...props
}: React.ComponentProps<typeof D.Content>) {
  return (
    <D.Portal>
      <D.Overlay className="fixed inset-0 z-40 bg-ink/40" />
      <D.Content
        className={cn(
          'fixed top-1/2 left-1/2 z-50 max-h-[90vh] w-[calc(100%-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-lg border border-rule bg-surface p-6 shadow-[0_24px_48px_-12px_rgb(26_34_51/0.25)]',
          className,
        )}
        {...props}
      >
        {children}
        <D.Close className="absolute top-4 right-4 rounded-sm p-1 text-slate hover:text-ink" aria-label="Close">
          <XIcon className="size-4" />
        </D.Close>
      </D.Content>
    </D.Portal>
  )
}

export function DialogTitle({ className, ...props }: React.ComponentProps<typeof D.Title>) {
  return <D.Title className={cn('pr-8 text-lg font-semibold tracking-tight', className)} {...props} />
}

export function DialogDescription({ className, ...props }: React.ComponentProps<typeof D.Description>) {
  return <D.Description className={cn('mt-1.5 text-sm text-slate', className)} {...props} />
}

export function DialogFooter({ className, ...props }: React.ComponentProps<'div'>) {
  return <div className={cn('mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end', className)} {...props} />
}
