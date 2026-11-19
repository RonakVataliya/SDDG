import { contrastRatio, isHexColour, luminance } from './contrast'

describe('WCAG contrast ratio (#38)', () => {
  it('is 21:1 for black on white and 1:1 for a colour on itself, in either order', () => {
    expect(contrastRatio('#000000', '#FFFFFF')).toBeCloseTo(21, 5)
    expect(contrastRatio('#FFFFFF', '#000000')).toBeCloseTo(21, 5)
    expect(contrastRatio('#3B2F1E', '#3B2F1E')).toBe(1)
  })

  it('puts mid grey on white just under the 4.5:1 line and a slightly darker grey just over it', () => {
    expect(contrastRatio('#777777', '#FFFFFF')).toBeLessThan(4.5)
    expect(contrastRatio('#767676', '#FFFFFF')).toBeGreaterThanOrEqual(4.5)
  })

  it('accepts only #RRGGBB, in either case', () => {
    expect(isHexColour('#a1B2c3')).toBe(true)
    for (const bad of ['#fff', 'a1b2c3', '#a1b2c3ff', 'red', '']) expect(isHexColour(bad)).toBe(false)
    expect(() => luminance('red')).toThrow()
  })
})
