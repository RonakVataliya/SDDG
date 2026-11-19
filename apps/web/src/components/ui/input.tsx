import type * as React from 'react'
import { cn } from '@/lib/utils'

export const fieldClass =
  'w-full rounded-[9px] border border-rule-strong bg-field px-3 text-[14.5px] text-ink placeholder:text-slate/70 focus-visible:border-accent focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-accent/20 aria-invalid:border-danger aria-invalid:ring-danger/15 disabled:opacity-60'

export function Input({ className, ...props }: React.ComponentProps<'input'>) {
  return <input className={cn(fieldClass, 'h-10', className)} {...props} />
}

export function Textarea({ className, ...props }: React.ComponentProps<'textarea'>) {
  return <textarea className={cn(fieldClass, 'min-h-24 py-2.5 leading-6', className)} {...props} />
}

export function Label({ className, ...props }: React.ComponentProps<'label'>) {
  return <label className={cn('text-[13px] font-medium text-ink', className)} {...props} />
}

export function FieldError({ children, id }: { children?: React.ReactNode; id?: string }) {
  if (!children) return null
  return (
    <p id={id} role="alert" className="text-[12.5px] text-danger">
      {children}
    </p>
  )
}
