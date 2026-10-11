import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { auth, type Session } from './auth'

type AuthState = { session: Session | null; ready: boolean; signOut: () => Promise<void> }

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [session, setSession] = useState<Session | null>(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    let active = true
    void auth.getSession().then((s) => {
      if (!active) return
      setSession(s)
      setReady(true)
    })
    const off = auth.onChange((s) => {
      setSession(s)
      if (!s) queryClient.clear() // never show the previous user's data after logout
    })
    return () => {
      active = false
      off()
    }
  }, [queryClient])

  const value: AuthState = {
    session,
    ready,
    signOut: async () => {
      await auth.signOut()
      setSession(null)
      queryClient.clear()
    },
  }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
