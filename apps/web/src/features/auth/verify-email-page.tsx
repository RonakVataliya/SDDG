import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router'
import { Button } from '@/components/ui/button'
import { Input, Label } from '@/components/ui/input'
import { Notice } from '@/components/ui/notice'
import { auth, AuthError, isMockAuth, mockVerifyEmail } from './auth'
import { useAuth } from './auth-context'
import { AuthLayout } from './auth-layout'

/**
 * Two jobs:
 * 1. After sign-up: "check your inbox" with a resend button (the link is valid for 24 h, FR28a).
 * 2. Landing page for the emailed link: Supabase reads the token from the URL and signs the user in.
 */
export function VerifyEmailPage() {
  const { session } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const initialEmail = (location.state as { email?: string } | null)?.email ?? ''
  const [email, setEmail] = useState(initialEmail)
  const [status, setStatus] = useState<{ tone: 'info' | 'error'; text: string } | null>(null)
  const [cooldown, setCooldown] = useState(0)
  const linkError = new URLSearchParams(location.hash.slice(1) || location.search).get('error_description')

  useEffect(() => {
    if (cooldown <= 0) return
    const t = setTimeout(() => setCooldown((c) => c - 1), 1000)
    return () => clearTimeout(t)
  }, [cooldown])

  if (session) {
    return (
      <AuthLayout title="Email verified" subtitle={`You're logged in as ${session.email}.`}>
        <Button size="lg" className="w-full" onClick={() => navigate('/projects', { replace: true })}>
          Go to your projects
        </Button>
      </AuthLayout>
    )
  }

  async function resend() {
    setStatus(null)
    try {
      await auth.resendVerification(email)
      setStatus({ tone: 'info', text: `We sent a new link to ${email}.` })
      setCooldown(60)
    } catch (err) {
      setStatus({ tone: 'error', text: err instanceof AuthError ? err.message : 'Could not resend the link.' })
    }
  }

  return (
    <AuthLayout
      title="Check your inbox"
      subtitle={
        initialEmail ? (
          <>
            We sent a verification link to <strong className="text-ink">{initialEmail}</strong>. Open it within 24 hours
            to activate your account.
          </>
        ) : (
          'Open the verification link we emailed you. It stays valid for 24 hours.'
        )
      }
    >
      <div className="space-y-5">
        {linkError && (
          <Notice tone="error" title="This verification link didn't work">
            {linkError}. Request a new one below.
          </Notice>
        )}
        {status && <Notice tone={status.tone} title={status.text} />}
        <div className="space-y-1.5">
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <Button variant="secondary" className="w-full" disabled={!email || cooldown > 0} onClick={resend}>
          {cooldown > 0 ? `Resend available in ${cooldown}s` : 'Resend verification link'}
        </Button>
        {isMockAuth && email && (
          <Notice tone="warning" title="Mock auth (no Supabase keys set)">
            No email is sent in mock mode.{' '}
            <button
              type="button"
              className="font-medium underline"
              onClick={() => {
                mockVerifyEmail(email)
                navigate('/login', { state: { verified: true, email } })
              }}
            >
              Simulate clicking the link
            </button>
          </Notice>
        )}
        <p className="text-sm text-slate">
          Already verified?{' '}
          <Link to="/login" className="font-medium text-teal hover:underline">
            Log in
          </Link>
        </p>
      </div>
    </AuthLayout>
  )
}
