import { ago } from './time'

const now = Date.parse('2026-11-20T12:00:00Z')
const before = (min: number) => new Date(now - min * 60_000).toISOString()

describe('ago', () => {
  it('words the Last active column', () => {
    expect(ago(null, now)).toBe('never')
    expect(ago(before(0), now)).toBe('now')
    expect(ago(before(2), now)).toBe('2 min ago')
    expect(ago(before(60), now)).toBe('1 h ago')
    expect(ago(before(25 * 60), now)).toBe('yesterday')
    expect(ago(before(41 * 24 * 60), now)).toBe('41 days ago')
  })
})
