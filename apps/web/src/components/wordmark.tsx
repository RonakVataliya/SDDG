import { cn } from '@/lib/utils'

/** A use-case ellipse beside an actor: the product's own first diagram type as its mark. */
export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn('inline-flex items-center gap-2 font-semibold tracking-tight text-ink', className)}>
      <svg viewBox="0 0 32 32" className="size-6" aria-hidden>
        <rect width="32" height="32" rx="7" fill="var(--color-teal)" />
        <ellipse cx="19.5" cy="16" rx="8" ry="5" fill="none" stroke="#fff" strokeWidth="2" />
        <circle cx="7" cy="10" r="2.4" fill="#fff" />
        <path d="M7 13v6M4 15h6M7 19l-2.5 4M7 19l2.5 4" stroke="#fff" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
      SDDG
    </span>
  )
}
