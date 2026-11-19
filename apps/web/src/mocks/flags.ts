/** MOCK ONLY. A crude stand-in for the AI service's requirement quality checker (issue #34). */
import type { Flag, RequirementStatement } from '@/api/client'

export type FlagRow = Omit<Flag, 'statement_ref' | 'statement_text' | 'has_suggestion' | 'suggestion'> & { suggestion: string | null }

const VAGUE: [RegExp, string][] = [
  [/\b(quickly|fast|promptly)\b/i, 'within 2 seconds for 95% of requests'],
  [/\buser[- ]friendly\b/i, 'so that a first-time user completes it without help'],
  [/\b(easy|simple|intuitive)\b/i, 'in at most 3 steps'],
  [/\b(efficient|scalable|robust)\b/i, 'for up to 500 concurrent users'],
]
const QUESTIONS = {
  ambiguous: 'What measurable value should replace the vague word?',
  incomplete: 'What detail is missing (how much, when, by which channel)?',
  conflict: 'Which of the two requirements is correct?',
}

/** Flags for `statements`, checked against the whole project (`all`) for conflicts. */
export function detectFlags(statements: RequirementStatement[], all: RequirementStatement[], uid: (p: string) => string): FlagRow[] {
  const out: FlagRow[] = []
  const base = { answer: null, status: 'open' as const, resolved_by: null, resolved_at: null, related_statement_id: null }
  for (const s of statements) {
    for (const [re, fix] of VAGUE) {
      const m = s.text.match(re)
      if (m) {
        out.push({ ...base, id: uid('fl'), statement_id: s.id, type: 'ambiguous', trigger_text: m[0], reason: `“${m[0]}” has no measurable target, so it can’t be tested.`, question: QUESTIONS.ambiguous, suggestion: s.text.replace(re, fix).replace(/\bshould\b/i, 'shall') })
        break
      }
    }
    const before = s.text.match(/\b(before|after|regularly|periodically)\b[^.]*/i)
    if (before && !/\d/.test(s.text)) {
      out.push({ ...base, id: uid('fl'), statement_id: s.id, type: 'incomplete', trigger_text: before[0].trim(), reason: 'How long, how often or through which channel is not stated.', question: QUESTIONS.incomplete, suggestion: null })
    }
    const limit = s.text.match(/^(.*?\bup to )(\d+)( \w+.*)$/i)
    if (limit) {
      const other = all.find((o) => o.id !== s.id && o.text.toLowerCase().startsWith(limit[1].toLowerCase()) && !o.text.includes(` ${limit[2]} `))
      if (other) {
        const n = other.text.match(/up to (\d+)/i)?.[1]
        out.push({ ...base, id: uid('fl'), statement_id: s.id, type: 'conflict', trigger_text: `up to ${limit[2]}`, related_statement_id: other.id, reason: `Contradicts ${other.ref}, which allows ${n}.`, question: QUESTIONS.conflict, suggestion: other.text })
      }
    }
  }
  return out
}
