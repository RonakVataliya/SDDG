import { pastedPageCount } from './utils'

describe('pastedPageCount (1 page per 3,000 characters, rounded up)', () => {
  it.each([
    [0, 0],
    [1, 1],
    [3000, 1],
    [3001, 2],
    [300_000, 100],
  ])('%i characters → %i pages', (chars, pages) => {
    expect(pastedPageCount('x'.repeat(chars))).toBe(pages)
  })
})
