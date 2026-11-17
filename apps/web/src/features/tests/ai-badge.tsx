import { SparklesIcon } from 'lucide-react'
import { Badge } from '@/components/ui/badge'

/** Marks what came from one of the feature's two AI requests; everything without it is plain code. */
export function AiBadge({ n }: { n: 1 | 2 }) {
  return (
    <Badge tone="violet">
      <SparklesIcon className="size-3" /> AI request {n}
    </Badge>
  )
}
