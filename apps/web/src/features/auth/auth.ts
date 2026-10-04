import { createClient, type SupabaseClient } from '@supabase/supabase-js'
import { env, hasSupabase } from '@/lib/env'

export type Session = { email: string; accessToken: string }

export type SignUpResult = { needsVerification: boolean }

export class AuthError extends Error {
  code?: 'email_not_confirmed' | 'invalid_credentials' | 'user_exists' | 'rate_limited'
  constructor(message: string, code?: AuthError['code']) {
    super(message)
    this.code = code
  }
}

export interface AuthAdapter {
  getSession(): Promise<Session | null>
  getAccessToken(): Promise<string | null>
  onChange(cb: (session: Session | null) => void): () => void
  signUp(email: string, password: string): Promise<SignUpResult>
  signIn(email: string, password: string): Promise<Session>
  signOut(): Promise<void>
  resendVerification(email: string): Promise<void>
  handleUnauthorized(): Promise<void>
}

export const verifyRedirectUrl = () => `${window.location.origin}/verify-email`

/* ---------------- Supabase (real) ---------------- */

function supabaseAdapter(client: SupabaseClient): AuthAdapter {
  const toSession = (s: { access_token: string; user: { email?: string } } | null): Session | null =>
    s ? { email: s.user.email ?? '', accessToken: s.access_token } : null

  const mapError = (e: { message: string; code?: string; status?: number }) => {
    if (e.code === 'email_not_confirmed') return new AuthError('Verify your email before logging in.', 'email_not_confirmed')
    if (e.code === 'invalid_credentials') return new AuthError('Email or password is incorrect.', 'invalid_credentials')
    if (e.code === 'user_already_exists') return new AuthError('An account with this email already exists.', 'user_exists')
    if (e.status === 429) return new AuthError('Too many attempts. Wait a few minutes, then try again.', 'rate_limited')
    return new AuthError(e.message)
  }

  return {
    async getSession() {
      const { data } = await client.auth.getSession()
      return toSession(data.session)
    },
    async getAccessToken() {
      const { data } = await client.auth.getSession()
      return data.session?.access_token ?? null
    },
    onChange(cb) {
      const { data } = client.auth.onAuthStateChange((_event, s) => cb(toSession(s)))
      return () => data.subscription.unsubscribe()
    },
    async signUp(email, password) {
      const { data, error } = await client.auth.signUp({
        email,
        password,
        options: { emailRedirectTo: verifyRedirectUrl() },
      })
      if (error) throw mapError(error)
      // Supabase returns a user with no identities when the email is already registered.
      if (data.user && data.user.identities?.length === 0)
        throw new AuthError('An account with this email already exists.', 'user_exists')
      return { needsVerification: !data.session }
    },
    async signIn(email, password) {
      const { data, error } = await client.auth.signInWithPassword({ email, password })
      if (error) throw mapError(error)
      return toSession(data.session)!
    },
    async signOut() {
      // FR28d: 'global' revokes the refresh token on the server, not just the local copy.
      await client.auth.signOut({ scope: 'global' })
    },
    async resendVerification(email) {
      const { error } = await client.auth.resend({
        type: 'signup',
        email,
        options: { emailRedirectTo: verifyRedirectUrl() },
      })
      if (error) throw mapError(error)
    },
    async handleUnauthorized() {
      await client.auth.signOut({ scope: 'local' })
    },
  }
}

/* ---------------- Mock (until BE hand-off H4) ---------------- */

type MockUser = { email: string; password: string; verified: boolean }
const USERS_KEY = 'sddg.mock.users'
const SESSION_KEY = 'sddg.mock.session'

function read<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : fallback
  } catch {
    return fallback
  }
}
function write(key: string, value: unknown) {
  try {
    if (value === null) localStorage.removeItem(key)
    else localStorage.setItem(key, JSON.stringify(value))
  } catch {
    /* storage unavailable: mock state lives for this page only */
  }
}

export function mockAdapter(): AuthAdapter {
  const listeners = new Set<(s: Session | null) => void>()
  const emit = (s: Session | null) => listeners.forEach((l) => l(s))
  const users = () => read<MockUser[]>(USERS_KEY, [])
  const norm = (e: string) => e.trim().toLowerCase()

  return {
    async getSession() {
      return read<Session | null>(SESSION_KEY, null)
    },
    async getAccessToken() {
      return read<Session | null>(SESSION_KEY, null)?.accessToken ?? null
    },
    onChange(cb) {
      listeners.add(cb)
      return () => listeners.delete(cb)
    },
    async signUp(email, password) {
      const all = users()
      if (all.some((u) => u.email === norm(email)))
        throw new AuthError('An account with this email already exists.', 'user_exists')
      write(USERS_KEY, [...all, { email: norm(email), password, verified: false }])
      return { needsVerification: true }
    },
    async signIn(email, password) {
      const user = users().find((u) => u.email === norm(email))
      if (!user || user.password !== password) throw new AuthError('Email or password is incorrect.', 'invalid_credentials')
      if (!user.verified) throw new AuthError('Verify your email before logging in.', 'email_not_confirmed')
      const session = { email: user.email, accessToken: `mock-token:${user.email}` }
      write(SESSION_KEY, session)
      emit(session)
      return session
    },
    async signOut() {
      write(SESSION_KEY, null)
      emit(null)
    },
    async resendVerification() {},
    async handleUnauthorized() {
      write(SESSION_KEY, null)
      emit(null)
    },
  }
}

/** Mock-only: what clicking the emailed link would do. Used by the verify-email screen's dev shortcut. */
export function mockVerifyEmail(email: string) {
  const all = read<MockUser[]>(USERS_KEY, [])
  write(
    USERS_KEY,
    all.map((u) => (u.email === email.trim().toLowerCase() ? { ...u, verified: true } : u)),
  )
}

export const isMockAuth = !hasSupabase

export const auth: AuthAdapter = hasSupabase
  ? supabaseAdapter(createClient(env.supabaseUrl, env.supabaseAnonKey))
  : mockAdapter()
