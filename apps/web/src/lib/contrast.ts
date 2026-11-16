/** WCAG 2.x contrast (issue #38): text must reach 4.5:1 against what it sits on (AA, normal text). */
export const MIN_TEXT_CONTRAST = 4.5

const HEX = /^#[0-9a-f]{6}$/i

export const isHexColour = (value: string) => HEX.test(value)

function channel(v: number) {
  const s = v / 255
  return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
}

/** Relative luminance of a #RRGGBB colour, 0 (black) to 1 (white). */
export function luminance(hex: string) {
  if (!isHexColour(hex)) throw new Error(`Not a #RRGGBB colour: ${hex}`)
  const [r, g, b] = [1, 3, 5].map((i) => channel(parseInt(hex.slice(i, i + 2), 16)))
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

/** Contrast ratio between two colours, 1 (identical) to 21 (black on white). Order does not matter. */
export function contrastRatio(a: string, b: string) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}
