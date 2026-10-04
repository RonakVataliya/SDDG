import { LoaderCircleIcon } from 'lucide-react'
import { cn } from '@/lib/utils'

export function Spinner({ className, label = 'Loading' }: { className?: string; label?: string }) {
  return <LoaderCircleIcon role="status" aria-label={label} className={cn('size-4 animate-spin text-slate', className)} />
}

export function PageLoading({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="flex min-h-40 items-center justify-center gap-2 text-sm text-slate">
      <Spinner label={label} /> {label}…
    </div>
  )
}
