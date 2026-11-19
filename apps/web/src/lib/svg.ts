/**
 * Diagram SVGs come from the API (rendered from user text), so strip anything executable before inlining:
 * scripts, foreign HTML, event handlers, animation tags (they can rewrite a link at runtime) and every link that
 * is not a same-document #reference (or an inline PNG/JPEG/GIF on <image>). Returns '' if it isn't an SVG.
 */
export function sanitizeSvg(svg: string): string {
  const doc = new DOMParser().parseFromString(svg, 'image/svg+xml')
  const root = doc.documentElement
  if (root.nodeName.toLowerCase() !== 'svg' || doc.getElementsByTagName('parsererror').length) return ''
  root.querySelectorAll('script, foreignObject, iframe, object, embed, set, animate, animateMotion, animateTransform').forEach((n) => n.remove())
  for (const el of [root, ...Array.from(root.querySelectorAll('*'))]) {
    for (const attr of Array.from(el.attributes)) {
      const name = attr.name.toLowerCase()
      // Diagrams need no outside links; a prefix check on javascript: is bypassed by tabs/newlines inside it.
      const value = attr.value.trim()
      const link = name === 'href' || name.endsWith(':href')
      const rasterImage = el.nodeName === 'image' && /^data:image\/(png|jpe?g|gif);base64,/i.test(value)
      const bad = name.startsWith('on') || (link && !value.startsWith('#') && !rasterImage)
      if (bad) el.removeAttribute(attr.name)
    }
  }
  return new XMLSerializer().serializeToString(root)
}
