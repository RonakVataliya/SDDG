import type * as React from 'react'
import { cn } from '@/lib/utils'

export const fieldClass =
  'w-full rounded-md border border-rule-strong bg-surface px-3 text-[15px] text-ink placeholder:text-slate/70 focus-visible:border-teal focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-teal/30 aria-invalid:border-danger disabled:opacity-60'

export function Input({ className, ...props }: React.ComponentProps<'input'>) {
  return <input className={cn(fieldClass, 'h-10', className)} {...props} />
}

export function Textarea({ className, ...props }: React.ComponentProps<'textarea'>) {
  return <textarea className={cn(fieldClass, 'min-h-24 py-2.5 leading-6', className)} {...props} />
}

export function Label({ className, ...props }: React.ComponentProps<'label'>) {
  return <label className={cn('text-sm font-medium text-ink', className)} {...props} />
}

export function FieldError({ children, id }: { children?: React.ReactNode; id?: string }) {
  if (!children) return null
  return (
    <p id={id} role="alert" className="text-sm text-danger">
      {children}
    </p>
  )
}
