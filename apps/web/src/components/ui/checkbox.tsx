import { CheckIcon } from 'lucide-react'
import { Checkbox as C } from 'radix-ui'
import type * as React from 'react'
import { cn } from '@/lib/utils'

export function Checkbox({ className, ...props }: React.ComponentProps<typeof C.Root>) {
  return (
    <C.Root
      className={cn(
        'peer grid size-[18px] shrink-0 place-items-center rounded-sm border border-rule-strong bg-surface data-[state=checked]:border-teal data-[state=checked]:bg-teal data-[state=checked]:text-white',
        className,
      )}
      {...props}
    >
      <C.Indicator>
        <CheckIcon className="size-3.5" strokeWidth={3} />
      </C.Indicator>
    </C.Root>
  )
}
