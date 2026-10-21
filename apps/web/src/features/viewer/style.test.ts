import { contrastRatio } from '@/lib/contrast'
import { DEFAULT_STYLE, directionSupported, lowContrastPairs, STYLE_PRESETS, styleProblems, withPreset } from './style'

describe('diagram style (#38)', () => {
  it('has a valid default that uses the default preset', () => {
    expect(styleProblems(DEFAULT_STYLE)).toEqual([])
    expect(withPreset(DEFAULT_STYLE, 'default')).toEqual(DEFAULT_STYLE)
  })

  it.each(STYLE_PRESETS.map((p) => [p.id, p.colours] as const))('preset %s passes 4.5:1 for text on fill and on background', (_, c) => {
    expect(contrastRatio(c.text, c.fill)).toBeGreaterThanOrEqual(4.5)
    expect(contrastRatio(c.text, c.background)).toBeGreaterThanOrEqual(4.5)
    expect(lowContrastPairs(c)).toEqual([])
  })

  it.each([
    [7, false],
    [8, true],
    [24, true],
    [25, false],
    [12.5, false],
  ])('font size %d pt is allowed: %s', (size, ok) => {
    expect(styleProblems({ ...DEFAULT_STYLE, font_size: size })).toHaveLength(ok ? 0 : 1)
  })

  it('rejects colours that are not #RRGGBB and an unknown direction', () => {
    const problems = styleProblems({ ...DEFAULT_STYLE, fill: 'yellow', direction: 'RL' as never })
    expect(problems).toEqual(['The fill colour must look like #1A2B3C.', 'Choose a layout direction.'])
  })

  it('names each low-contrast pair with its ratio', () => {
    const pale = { ...DEFAULT_STYLE, text: '#CCCCCC' }
    expect(lowContrastPairs(pale).map((p) => p.pair)).toEqual(['text on fill', 'text on background'])
    expect(lowContrastPairs({ ...DEFAULT_STYLE, background: '#333333' }).map((p) => p.pair)).toEqual(['text on background'])
  })

  it('switching preset changes only the colours', () => {
    const dark = withPreset({ ...DEFAULT_STYLE, direction: 'TB', font_size: 18 }, 'dark')
    expect(dark).toMatchObject({ preset: 'dark', background: '#1E1E24', direction: 'TB', font_size: 18 })
    expect(withPreset(DEFAULT_STYLE, 'nope')).toBe(DEFAULT_STYLE)
  })

  it('offers direction for every type except sequence', () => {
    expect(directionSupported('sequence')).toBe(false)
    expect(directionSupported('use_case')).toBe(true)
    expect(directionSupported('dfd')).toBe(true)
  })
})
