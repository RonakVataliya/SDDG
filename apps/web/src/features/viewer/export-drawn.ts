/**
 * Export of a MOVED diagram version. Kroki draws pictures from the diagram source and knows nothing of positions the user
 * moved (issue #37), so a moved version's PNG, SVG and PDF are made in the browser from the canvas on screen instead.
 * svgMarkup/svgToPng (export-svg.ts) already turn that canvas into a standalone, styled picture.
 */
import { svgMarkup, svgToPng } from './export-svg'
import type { ExportFormat } from './export-formats'
import { jpegToPdf } from './pdf'

/** A one-page PDF of the drawn canvas: a 2x JPEG on a page the size of the diagram. */
async function svgToPdf(svg: SVGSVGElement, scale = 2): Promise<Blob> {
  const { markup, width, height } = svgMarkup(svg)
  const url = URL.createObjectURL(new Blob([markup], { type: 'image/svg+xml' }))
  try {
    const img = new Image()
    img.src = url
    await img.decode()
    const canvas = Object.assign(document.createElement('canvas'), { width: width * scale, height: height * scale })
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('This browser cannot draw the PDF.')
    ctx.fillStyle = '#ffffff' // JPEG has no transparency
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.scale(scale, scale)
    ctx.drawImage(img, 0, 0, width, height)
    const jpeg = await new Promise<Blob>((resolve, reject) =>
      canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('This browser cannot draw the PDF.'))), 'image/jpeg', 0.95),
    )
    return jpegToPdf(new Uint8Array(await jpeg.arrayBuffer()), canvas.width, canvas.height, width, height)
  } finally {
    URL.revokeObjectURL(url)
  }
}

/** The moved version as drawn, or null for `source` (the code has no positions; it comes from the API). */
export function exportDrawn(svg: SVGSVGElement, format: ExportFormat): Promise<Blob> | null {
  if (format === 'png') return svgToPng(svg)
  if (format === 'svg') return Promise.resolve(new Blob([svgMarkup(svg).markup], { type: 'image/svg+xml' }))
  if (format === 'pdf') return svgToPdf(svg)
  return null
}
