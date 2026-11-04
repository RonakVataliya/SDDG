/**
 * Writes the smallest valid PDF 1.4 file from a JPEG. Used for a moved diagram's PDF (drawn in the browser, since Kroki
 * does not know the moved positions) and by the mock API's PDF export. The file is one page holding the JPEG as a
 * DCT-encoded XObject. The page is `pageWidthPx` x `pageHeightPx` CSS pixels (1 px = 0.75 pt, i.e. 96 dpi); a 2x JPEG on a 1x page stays sharp when zoomed.
 */
export function jpegToPdf(jpeg: Uint8Array, widthPx: number, heightPx: number, pageWidthPx = widthPx, pageHeightPx = heightPx): Blob {
  const w = +(pageWidthPx * 0.75).toFixed(2)
  const h = +(pageHeightPx * 0.75).toFixed(2)
  const draw = `q ${w} 0 0 ${h} 0 0 cm /Im0 Do Q`
  const enc = new TextEncoder()

  // Each object is [text before the stream bytes, optional binary stream, text after].
  const objects: [string, Uint8Array?, string?][] = [
    ['<< /Type /Catalog /Pages 2 0 R >>'],
    ['<< /Type /Pages /Kids [3 0 R] /Count 1 >>'],
    [`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${w} ${h}] /Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>`],
    [
      `<< /Type /XObject /Subtype /Image /Width ${widthPx} /Height ${heightPx} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${jpeg.length} >>\nstream\n`,
      jpeg,
      '\nendstream',
    ],
    [`<< /Length ${draw.length} >>\nstream\n${draw}\nendstream`],
  ]

  const parts: Uint8Array[] = []
  let offset = 0
  const push = (chunk: string | Uint8Array) => {
    const bytes = typeof chunk === 'string' ? enc.encode(chunk) : chunk
    parts.push(bytes)
    offset += bytes.length
  }

  push('%PDF-1.4\n')
  const offsets: number[] = []
  objects.forEach(([head, stream, tail], i) => {
    offsets.push(offset)
    push(`${i + 1} 0 obj\n${head}`)
    if (stream) push(stream)
    push(`${tail ?? ''}\nendobj\n`)
  })
  const xref = offset
  push(`xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`)
  offsets.forEach((o) => push(`${String(o).padStart(10, '0')} 00000 n \n`))
  push(`trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`)

  return new Blob(parts as BlobPart[], { type: 'application/pdf' })
}
