import { cva, type VariantProps } from 'class-variance-authority'
import type * as React from 'react'
import { cn } from '@/lib/utils'

const badgeVariants = cva('inline-flex items-center gap-1 rounded-sm px-1.5 py-px text-xs font-medium whitespace-nowrap', {
  variants: {
    tone: {
      neutral: 'bg-ink/6 text-slate',
      teal: 'bg-teal-wash text-teal-deep',
      amber: 'bg-amber-wash text-amber',
      violet: 'bg-violet-wash text-violet',
      danger: 'bg-danger-wash text-danger',
    },
  },
  defaultVariants: { tone: 'neutral' },
})

export function Badge({ className, tone, ...props }: React.ComponentProps<'span'> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />
}

/** Requirement statement / element identifiers are real IDs, so they get the mono face. */
export function RefTag({ className, ...props }: React.ComponentProps<'span'>) {
  return (
    <span
      className={cn('rounded-sm border border-rule bg-paper px-1 font-mono text-[12px] leading-5 text-ink', className)}
      {...props}
    />
  )
}
