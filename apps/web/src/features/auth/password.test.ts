import { PASSWORD_RULES, passwordIsValid } from './password'

const failing = (p: string) => PASSWORD_RULES.filter((r) => !r.test(p)).map((r) => r.id)

describe('sign-up password rules', () => {
  it('accepts a password that meets every rule', () => {
    expect(passwordIsValid('Library#42')).toBe(true)
  })

  it('names each rule a password misses', () => {
    expect(failing('Ab#12')).toEqual(['length'])
    expect(failing('library#42')).toEqual(['case'])
    expect(failing('Library#4x')).toEqual(['digits'])
    expect(failing('Library42x')).toEqual(['symbol'])
    expect(failing('')).toEqual(['length', 'case', 'digits', 'symbol'])
  })

  it('does not count spaces as symbols', () => {
    expect(failing('Library 42')).toEqual(['symbol'])
  })
})
