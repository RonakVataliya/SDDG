import { CheckIcon, XIcon } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router'
import { Button } from '@/components/ui/button'
import { FieldError, Input, Label } from '@/components/ui/input'
import { Notice } from '@/components/ui/notice'
import { Spinner } from '@/components/ui/spinner'
import { cn } from '@/lib/utils'
import { auth, AuthError } from './auth'
import { useAuth } from './auth-context'
import { AuthLayout } from './auth-layout'
import { PASSWORD_RULES, passwordIsValid } from './password'

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export function SignupPage() {
  const { session } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [touched, setTouched] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  if (session) return <Navigate to="/projects" replace />

  const emailError = touched && !EMAIL_RE.test(email) ? 'Enter a valid email address.' : undefined
  const passwordError = touched && !passwordIsValid(password) ? 'Your password does not meet every rule below.' : undefined
  const matches = confirm.length > 0 && confirm === password
  const confirmError =
    (touched || confirm.length >= password.length) && confirm.length > 0 && !matches
      ? 'Passwords do not match.'
      : touched && !confirm
        ? 'Type your password again.'
        : undefined

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setTouched(true)
    setError(null)
    if (!EMAIL_RE.test(email) || !passwordIsValid(password) || !matches) return
    setPending(true)
    try {
      const { needsVerification } = await auth.signUp(email, password)
      navigate(needsVerification ? '/verify-email' : '/projects', { state: { email, justSignedUp: true } })
    } catch (err) {
      setError(err instanceof AuthError ? err.message : 'Could not create the account. Try again.')
    } finally {
      setPending(false)
    }
  }

  return (
    <AuthLayout
      title="Create your account"
      subtitle={
        <>
          Already have one?{' '}
          <Link to="/login" className="font-medium text-teal hover:underline">
            Log in
          </Link>
        </>
      }
    >
      <form onSubmit={onSubmit} className="space-y-5" noValidate>
        {error && <Notice tone="error" title={error} />}
        <div className="space-y-1.5">
          <Label htmlFor="email">Email</Label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            value={email}
            aria-invalid={!!emailError}
            aria-describedby="email-error"
            onChange={(e) => setEmail(e.target.value)}
          />
          <FieldError id="email-error">{emailError}</FieldError>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="password">Password</Label>
          <Input
            id="password"
            type="password"
            autoComplete="new-password"
            value={password}
            aria-invalid={!!passwordError}
            aria-describedby="password-hint"
            onChange={(e) => setPassword(e.target.value)}
          />
          <FieldError>{passwordError}</FieldError>
          <ul id="password-hint" aria-label="Password rules" className="space-y-0.5 pt-0.5">
            {PASSWORD_RULES.map((r) => {
              const met = r.test(password)
              return (
                <li
                  key={r.id}
                  className={cn('flex items-center gap-1.5 text-xs', met ? 'text-teal-deep' : touched ? 'text-danger' : 'text-slate')}
                >
                  {met ? <CheckIcon className="size-3.5" strokeWidth={3} aria-hidden /> : <XIcon className="size-3.5" aria-hidden />}
                  {r.label}
                  <span className="sr-only">{met ? '(done)' : '(not yet)'}</span>
                </li>
              )
            })}
          </ul>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="confirm">Confirm password</Label>
          <Input
            id="confirm"
            type="password"
            autoComplete="new-password"
            value={confirm}
            aria-invalid={!!confirmError}
            aria-describedby="confirm-error"
            onChange={(e) => setConfirm(e.target.value)}
          />
          {matches ? (
            <p id="confirm-error" className="flex items-center gap-1.5 text-xs text-teal-deep">
              <CheckIcon className="size-3.5" strokeWidth={3} aria-hidden /> Passwords match
            </p>
          ) : (
            <FieldError id="confirm-error">{confirmError}</FieldError>
          )}
        </div>
        <Button type="submit" size="lg" className="w-full" disabled={pending}>
          {pending && <Spinner className="text-white" label="Creating account" />}
          Create account
        </Button>
        <p className="text-xs text-slate">
          By creating an account you agree to the{' '}
          <Link to="/privacy" className="underline hover:text-ink">
            Privacy Policy
          </Link>
          .
        </p>
      </form>
    </AuthLayout>
  )
}
