import { CheckIcon } from 'lucide-react'
import { Checkbox as C } from 'radix-ui'
import type * as React from 'react'
import { cn } from '@/lib/utils'

export function Checkbox({ className, ...props }: React.ComponentProps<typeof C.Root>) {
  return (
    <C.Root
      className={cn(
        'peer grid size-[18px] shrink-0 place-items-center rounded-[4px] border-[1.5px] border-rule-strong bg-field data-[state=checked]:border-accent data-[state=checked]:bg-accent data-[state=checked]:text-on-ink',
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
