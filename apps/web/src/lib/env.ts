export const env = {
  apiUrl: import.meta.env.VITE_API_URL ?? '/api/v1',
  supabaseUrl: import.meta.env.VITE_SUPABASE_URL ?? '',
  supabaseAnonKey: import.meta.env.VITE_SUPABASE_ANON_KEY ?? '',
  useMocks: (import.meta.env.VITE_USE_MOCKS ?? 'true') === 'true',
  mockColdStart: import.meta.env.VITE_MOCK_COLD_START === 'true',
}

/** Real Supabase Auth is used only when both keys are set; otherwise the mock auth adapter runs. */
export const hasSupabase = Boolean(env.supabaseUrl && env.supabaseAnonKey)
