import { useState, type FormEvent } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router'
import { Button } from '@/components/ui/button'
import { Input, Label } from '@/components/ui/input'
import { Notice } from '@/components/ui/notice'
import { Spinner } from '@/components/ui/spinner'
import { auth, AuthError } from './auth'
import { useAuth } from './auth-context'
import { AuthLayout } from './auth-layout'

export function LoginPage() {
  const { session } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const state = location.state as { from?: string; verified?: boolean; email?: string } | null
  const from = state?.from ?? '/projects'
  const [email, setEmail] = useState(state?.email ?? '')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<AuthError | null>(null)
  const [pending, setPending] = useState(false)

  if (session) return <Navigate to={from} replace />

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setPending(true)
    try {
      await auth.signIn(email, password)
      navigate(from, { replace: true })
    } catch (err) {
      setError(err instanceof AuthError ? err : new AuthError('Could not log in. Try again.'))
    } finally {
      setPending(false)
    }
  }

  return (
    <AuthLayout
      title="Log in"
      subtitle={
        <>
          New to SDDG?{' '}
          <Link to="/signup" className="font-medium text-teal hover:underline">
            Create an account
          </Link>
        </>
      }
    >
      <form onSubmit={onSubmit} className="space-y-5" noValidate>
        {state?.verified && !error && <Notice title="Email verified. Log in to continue." />}
        {error && (
          <Notice
            tone="error"
            title={error.message}
            action={
              error.code === 'email_not_confirmed' ? (
                <Link to="/verify-email" state={{ email }} className="shrink-0 font-medium underline">
                  Resend link
                </Link>
              ) : undefined
            }
          />
        )}
        <div className="space-y-1.5">
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="password">Password</Label>
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        <Button type="submit" size="lg" className="w-full" disabled={pending || !email || !password}>
          {pending && <Spinner className="text-white" label="Logging in" />}
          Log in
        </Button>
      </form>
    </AuthLayout>
  )
}
