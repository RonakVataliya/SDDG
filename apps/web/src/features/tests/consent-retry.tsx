import { useRef, useState } from 'react'
import { ApiError } from '@/api/errors'
import { ConsentDialog } from '@/features/privacy/consent-dialog'

/**
 * X8: the server refuses AI requests without current consent (403, code consent_required). Wrap the request in
 * run(): if it is refused for that reason, the consent dialog opens and the request is sent again once the user
 * agrees. Render `dialog` once in the component.
 */
export function useConsentRetry() {
  const [open, setOpen] = useState(false)
  const retry = useRef<(() => Promise<unknown>) | null>(null)

  async function run(request: () => Promise<unknown>) {
    try {
      await request()
    } catch (e) {
      if (e instanceof ApiError && e.code === 'consent_required') {
        retry.current = request
        setOpen(true)
        return
      }
      throw e
    }
  }

  const dialog = (
    <ConsentDialog
      open={open}
      onOpenChange={setOpen}
      onConsented={() => {
        setOpen(false)
        void retry.current?.().catch(() => undefined)
      }}
    />
  )
  return { run, dialog }
}

export const isConsentError = (e: unknown) => e instanceof ApiError && e.code === 'consent_required'
