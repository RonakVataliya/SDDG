import { cn } from '@/lib/utils'

/** The mark: a sentence (three lines) wired into a node. Text in, diagram out. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={cn('size-7 shrink-0', className)} aria-hidden>
      <rect width="32" height="32" rx="8" fill="var(--ink)" />
      <path d="M7 10h8M7 15h6M7 20h8" stroke="var(--paper)" strokeWidth="2.2" strokeLinecap="round" />
      <path d="M16 15h3.5a2 2 0 0 1 2 2" stroke="var(--accent)" strokeWidth="2" fill="none" strokeLinecap="round" />
      <circle cx="22" cy="21" r="4" fill="var(--accent)" />
    </svg>
  )
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn('inline-flex items-center gap-2.5 font-display text-[16px] font-bold tracking-tight text-ink', className)}>
      <LogoMark />
      SDDG
    </span>
  )
}
