/**
 * Sign-up password rules, shown to the user as a live checklist.
 * The server (Supabase password policy) should enforce the same rules; this only mirrors them.
 */
export const PASSWORD_RULES: { id: string; label: string; test: (password: string) => boolean }[] = [
  { id: 'length', label: 'At least 8 characters', test: (p) => p.length >= 8 },
  { id: 'case', label: 'An uppercase and a lowercase letter', test: (p) => /[A-Z]/.test(p) && /[a-z]/.test(p) },
  { id: 'digits', label: 'At least 2 numbers', test: (p) => (p.match(/\d/g)?.length ?? 0) >= 2 },
  { id: 'symbol', label: 'At least 1 symbol, such as ! @ # ?', test: (p) => /[^A-Za-z0-9\s]/.test(p) },
]

export const passwordIsValid = (password: string) => PASSWORD_RULES.every((r) => r.test(password))
