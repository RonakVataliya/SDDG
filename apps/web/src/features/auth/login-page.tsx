import { ArrowRightIcon, EyeIcon, EyeOffIcon } from 'lucide-react'
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
  const [show, setShow] = useState(false)
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
    <AuthLayout title="Welcome back" subtitle="Log in to keep designing." tab="login">
      <form onSubmit={onSubmit} className="space-y-4" noValidate>
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
          <div className="relative">
            <Input
              id="password"
              type={show ? 'text' : 'password'}
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="pr-10"
            />
            <button
              type="button"
              onClick={() => setShow((s) => !s)}
              aria-label={show ? 'Hide password' : 'Show password'}
              className="absolute inset-y-0 right-0 grid w-10 place-items-center text-slate hover:text-ink"
            >
              {show ? <EyeOffIcon className="size-4" /> : <EyeIcon className="size-4" />}
            </button>
          </div>
        </div>
        <Button type="submit" size="lg" className="w-full" disabled={pending || !email || !password}>
          {pending && <Spinner className="text-on-ink" label="Logging in" />}
          Log in
          {!pending && <ArrowRightIcon />}
        </Button>
      </form>
    </AuthLayout>
  )
}
