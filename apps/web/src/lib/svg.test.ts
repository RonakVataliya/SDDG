import { sanitizeSvg } from './svg'

describe('sanitizeSvg', () => {
  it('keeps drawing markup and element ids but drops scripts, handlers and javascript: links', () => {
    const out = sanitizeSvg(
      '<svg xmlns="http://www.w3.org/2000/svg" onload="x()"><script>alert(1)</script><g data-element-id="UC-1"><text onclick="y()">Issue</text></g><a href="javascript:z()"><rect/></a><foreignObject><div/></foreignObject></svg>',
    )
    expect(out).toContain('data-element-id="UC-1"')
    expect(out).toContain('<text>Issue</text>')
    expect(out).not.toMatch(/script|onload|onclick|javascript:|foreignObject/i)
  })

  it('rejects input that is not an SVG', () => {
    expect(sanitizeSvg('<html><body>hi</body></html>')).toBe('')
  })

  const NS = 'xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"'

  it.each([
    ['a tab inside javascript:', `<svg ${NS}><a href="java&#9;script:alert(1)"><text>x</text></a></svg>`],
    ['a newline inside javascript:', `<svg ${NS}><a xlink:href="java&#10;script:alert(1)"><text>x</text></a></svg>`],
    ['an <animate> that rewrites href', `<svg ${NS}><a href="#"><animate attributeName="href" values="javascript:alert(1)"/></a></svg>`],
    ['a <set> that rewrites href', `<svg ${NS}><a href="#"><set attributeName="href" to="javascript:alert(1)"/></a></svg>`],
  ])('blocks %s', (_name, svg) => {
    expect(sanitizeSvg(svg)).not.toMatch(/script:|java&#|<set|<animate/i)
  })

  it('keeps same-document references and inline raster images', () => {
    const out = sanitizeSvg(`<svg ${NS}><use href="#a"/><image href="data:image/png;base64,AAAA"/></svg>`)
    expect(out).toContain('href="#a"')
    expect(out).toContain('data:image/png;base64,AAAA')
  })
})
