import { useState } from 'react'
import { Link } from 'react-router'
import { errorMessage } from '@/api/errors'
import { useGiveConsent } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogTitle } from '@/components/ui/dialog'
import { Notice } from '@/components/ui/notice'
import { Spinner } from '@/components/ui/spinner'
import { formatDate } from '@/lib/utils'
import { AI_SECTION_VERSION, aiSection, POLICY_DATE, POLICY_VERSION } from './policy'

/**
 * NFR5d. Shown before requirement text is sent to the AI provider for the first time, and again whenever the
 * AI section of the policy changes. The server also refuses submissions without consent (X8), so this is not
 * the only gate.
 */
export function ConsentDialog({
  open,
  onOpenChange,
  onConsented,
  renewal,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onConsented: () => void
  renewal?: boolean
}) {
  const [agreed, setAgreed] = useState(false)
  const give = useGiveConsent()

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        onOpenChange(o)
        if (!o) setAgreed(false)
      }}
    >
      <DialogContent className="max-w-xl">
        <DialogTitle>{renewal ? 'Our AI processing terms changed' : 'Before we process your requirements'}</DialogTitle>
        <DialogDescription>
          Privacy Policy v{POLICY_VERSION}, {formatDate(POLICY_DATE)}. Nothing is sent until you agree.
        </DialogDescription>
        <div className="mt-5 space-y-3 rounded-md border border-rule bg-paper p-4 text-sm leading-6 text-ink/85">
          {aiSection.body.map((p, i) => (
            <p key={i}>{p}</p>
          ))}
          <Link to="/privacy" target="_blank" className="inline-block font-medium text-teal hover:underline">
            Read the full Privacy Policy
          </Link>
        </div>
        <label className="mt-5 flex items-start gap-3 text-sm">
          <Checkbox checked={agreed} onCheckedChange={(v) => setAgreed(v === true)} className="mt-0.5" />
          <span>
            I agree that my requirement text is sent to Groq and diagram descriptions are sent to Kroki, as
            described above.
          </span>
        </label>
        {give.isError && (
          <Notice tone="error" className="mt-4" title="Couldn't record your consent">
            {errorMessage(give.error)}
          </Notice>
        )}
        <DialogFooter>
          <Button variant="secondary" onClick={() => onOpenChange(false)}>
            Don&rsquo;t send
          </Button>
          <Button
            disabled={!agreed || give.isPending}
            onClick={async () => {
              const ok = await give.mutateAsync(AI_SECTION_VERSION).catch(() => null)
              if (!ok) return
              onOpenChange(false)
              setAgreed(false)
              onConsented()
            }}
          >
            {give.isPending && <Spinner className="text-white" label="Saving" />}
            Agree and extract
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
