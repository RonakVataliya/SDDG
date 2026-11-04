/**
 * Turns the drawn layout canvas into a PNG, so Export PNG gives the arrangement on screen (issue #37).
 * The canvas is styled with CSS classes, which a standalone image does not have, so the computed styles are
 * copied onto a clone first.
 */
const STYLE_PROPS = [
  'fill',
  'fill-opacity',
  'stroke',
  'stroke-width',
  'stroke-dasharray',
  'stroke-linecap',
  'stroke-linejoin',
  'stroke-opacity',
  'paint-order',
  'opacity',
  'font-family',
  'font-size',
  'font-weight',
] as const

const SVG_NS = 'http://www.w3.org/2000/svg'

export function svgMarkup(svg: SVGSVGElement): { markup: string; width: number; height: number } {
  const clone = svg.cloneNode(true) as SVGSVGElement
  const copyStyle = (from: Element, to: Element) => {
    const cs = getComputedStyle(from)
    const style = STYLE_PROPS.map((p) => [p, cs.getPropertyValue(p)] as const)
      .filter(([, v]) => v)
      .map(([p, v]) => `${p}:${v}`)
      .join(';')
    if (style) to.setAttribute('style', style)
  }
  copyStyle(svg, clone)
  const from = svg.querySelectorAll('*')
  const to = clone.querySelectorAll('*')
  from.forEach((el, i) => copyStyle(el, to[i]))

  const vb = svg.viewBox.baseVal
  const width = Math.max(1, Math.ceil(vb?.width || svg.clientWidth || 800))
  const height = Math.max(1, Math.ceil(vb?.height || svg.clientHeight || 600))
  clone.setAttribute('width', String(width))
  clone.setAttribute('height', String(height))
  clone.removeAttribute('class')

  const bg = document.createElementNS(SVG_NS, 'rect') // a white sheet, like the Kroki PNG
  bg.setAttribute('x', String(vb?.x ?? 0))
  bg.setAttribute('y', String(vb?.y ?? 0))
  bg.setAttribute('width', String(width))
  bg.setAttribute('height', String(height))
  bg.setAttribute('fill', '#ffffff')
  clone.insertBefore(bg, clone.firstChild)
  return { markup: new XMLSerializer().serializeToString(clone), width, height }
}

export async function svgToPng(svg: SVGSVGElement, scale = 2): Promise<Blob> {
  const { markup, width, height } = svgMarkup(svg)
  const url = URL.createObjectURL(new Blob([markup], { type: 'image/svg+xml' }))
  try {
    const img = new Image()
    img.src = url
    await img.decode()
    const canvas = document.createElement('canvas')
    canvas.width = width * scale
    canvas.height = height * scale
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('This browser cannot draw the PNG.')
    ctx.scale(scale, scale)
    ctx.drawImage(img, 0, 0, width, height)
    return await new Promise<Blob>((resolve, reject) =>
      canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('This browser cannot draw the PNG.'))), 'image/png'),
    )
  } finally {
    URL.revokeObjectURL(url)
  }
}
