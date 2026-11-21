/** Word-level text merging for the edit conflict dialog (FR24f). Text is split into words, punctuation marks and the
 * spaces between them, so joining the tokens back gives the exact text. */

export type Token = { text: string; changed: boolean }

export const tokenize = (text: string) => text.match(/\s+|[\p{L}\p{N}'’_-]+|[^\s\p{L}\p{N}'’_-]/gu) ?? []

/** Pairs of indexes (in a, in b) of a longest common subsequence of tokens. */
function lcs(a: string[], b: string[]): [number, number][] {
  const n = a.length
  const m = b.length
  const len = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0))
  for (let i = n - 1; i >= 0; i--)
    for (let j = m - 1; j >= 0; j--) len[i][j] = a[i] === b[j] ? len[i + 1][j + 1] + 1 : Math.max(len[i + 1][j], len[i][j + 1])
  const pairs: [number, number][] = []
  let i = 0
  let j = 0
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      pairs.push([i, j])
      i++
      j++
    } else if (len[i + 1][j] >= len[i][j + 1]) i++
    else j++
  }
  return pairs
}

/** `text` as tokens, each marked changed if it is not part of `base` (the words someone added or replaced). */
export function changedWords(base: string, text: string): Token[] {
  const tokens = tokenize(text)
  const kept = new Set(lcs(tokenize(base), tokens).map(([, j]) => j))
  return tokens.map((t, j) => ({ text: t, changed: !kept.has(j) && t.trim() !== '' }))
}

/** Applies my change (base -> mine) on top of theirs (base -> theirs), word by word (a diff3 merge). Where we both
 * changed the same words differently, their words come first, then mine; the result is shown for editing, so the
 * person can tidy that up before saving. */
export function mergeOnTop(base: string, mine: string, theirs: string): string {
  if (mine === base) return theirs
  if (theirs === base || theirs === mine) return mine
  const b = tokenize(base)
  const m = tokenize(mine)
  const t = tokenize(theirs)
  const inMine = new Map(lcs(b, m))
  const inTheirs = new Map(lcs(b, t))
  // Anchors: base tokens both versions kept, in order in all three.
  const anchors: [number, number, number][] = []
  let lastM = -1
  let lastT = -1
  for (let i = 0; i < b.length; i++) {
    const mi = inMine.get(i)
    const ti = inTheirs.get(i)
    if (mi !== undefined && ti !== undefined && mi > lastM && ti > lastT) {
      anchors.push([i, mi, ti])
      lastM = mi
      lastT = ti
    }
  }
  anchors.push([b.length, m.length, t.length])
  const out: string[] = []
  let [pb, pm, pt] = [0, 0, 0]
  for (const [ab, am, at] of anchors) {
    const cb = b.slice(pb, ab).join('')
    const cm = m.slice(pm, am).join('')
    const ct = t.slice(pt, at).join('')
    if (cm === cb) out.push(ct)
    else if (ct === cb || ct === cm) out.push(cm)
    else out.push(ct, ct && cm && !/\s$/.test(ct) && !/^\s/.test(cm) ? ' ' : '', cm)
    if (ab < b.length) out.push(b[ab])
    ;[pb, pm, pt] = [ab + 1, am + 1, at + 1]
  }
  return out.join('')
}
