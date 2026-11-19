import { cva, type VariantProps } from 'class-variance-authority'
import type * as React from 'react'
import { cn } from '@/lib/utils'

const badgeVariants = cva('inline-flex h-[22px] items-center gap-1 rounded-full px-2 text-[11.5px] font-medium whitespace-nowrap [&_svg]:size-3', {
  variants: {
    tone: {
      neutral: 'bg-rule text-ink-2',
      accent: 'bg-accent-wash text-accent-deep',
      amber: 'bg-amber-wash text-amber',
      violet: 'bg-violet-wash text-violet',
      danger: 'bg-danger-wash text-danger',
      success: 'bg-success-wash text-success',
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
      className={cn('inline-flex h-5 items-center rounded-[4px] border border-rule-strong bg-field px-1.5 font-mono text-[11px] text-ink-2', className)}
      {...props}
    />
  )
}
