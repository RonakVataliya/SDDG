/**
 * MOCK ONLY. A crude stand-in for the AI stream's LangGraph pipeline (X10, FR4a–g) so the review screen has
 * realistic-looking data. It is deliberately simple; do not "improve" it, replace it with the real API.
 */
import type { ExtractedItem, RequirementStatement } from '@/api/client'

type Draft = Omit<ExtractedItem, 'id'> & { key: string }

const MODAL = /\b(shall|must|should|can|will|may)\b/i
const PREP = /\b(to|for|from|with|in|on|by|when|if|after|before|via|into|within|and)\b/i
const ARTICLE = /^(the|a|an|each|every|all|any|their|its|his|her)\s+/i
const STORE_WORDS = /\b(store|save|record|persist|keep|database|archive|log)\b/i
const FLOW_WORDS = /\b(send|receive|submit|upload|download|email|notify|export|import|forward)\b/i

const title = (s: string) => s.trim().replace(/\s+/g, ' ').replace(/^./, (c) => c.toUpperCase())
const stripArticles = (s: string) => s.replace(ARTICLE, '').replace(/\b(a|an|the)\s+/gi, '')

export function splitStatements(text: string): Omit<RequirementStatement, 'id'>[] {
  const out: Omit<RequirementStatement, 'id'>[] = []
  text
    .split(/\n\s*\n|\n(?=\s*(?:[-*•]|\d+[.)]|[A-Z]{1,4}\d+[a-z]?[:.)]))/)
    .forEach((para, pIdx) => {
      para
        .split(/(?<=[.!?])\s+(?=[A-Z])/)
        .map((s) => s.replace(/^\s*(?:[-*•]|\d+[.)])\s*/, '').trim())
        .filter((s) => s.length > 3)
        .forEach((s) => {
          const labelMatch = s.match(/^([A-Z]{1,4}\d+[a-z]?)[:.)]\s*/)
          out.push({
            ref: `R-${String(out.length + 1).padStart(3, '0')}`,
            text: labelMatch ? s.slice(labelMatch[0].length) : s,
            label: labelMatch?.[1] ?? null,
            source: { document: 'Pasted text', page: null, paragraph: pIdx + 1 },
          })
        })
    })
  return out
}

export function extractItems(statements: RequirementStatement[]): Draft[] {
  const drafts = new Map<string, Draft>()
  const add = (d: Omit<Draft, 'key' | 'origin' | 'statement_ids'> & { statement: string }) => {
    const key = `${d.category}:${d.name.toLowerCase()}`
    const existing = drafts.get(key)
    if (existing) {
      if (!existing.statement_ids.includes(d.statement)) existing.statement_ids.push(d.statement)
      existing.qualifiers = existing.qualifiers.filter((q) => q !== 'minimal')
      return key
    }
    drafts.set(key, {
      key,
      category: d.category,
      name: d.name,
      description: d.description ?? null,
      qualifiers: d.qualifiers,
      origin: 'system-extracted',
      statement_ids: [d.statement],
      source_item_id: d.source_item_id ?? null,
      target_item_id: d.target_item_id ?? null,
      relation_type: d.relation_type ?? null,
    })
    return key
  }

  for (const st of statements) {
    if (st.label?.startsWith('NFR')) continue // quality attributes don't yield actors or use cases
    const modal = st.text.match(MODAL)
    if (!modal || modal.index === undefined) continue
    const subjectRaw = st.text.slice(0, modal.index)
    const predicateRaw = st.text.slice(modal.index + modal[0].length)
    const subject = stripArticles(subjectRaw).trim()
    const predicate = predicateRaw.replace(/^\s*be able to\s+/i, '').replace(/[.!?]+$/, '').trim()
    const isSystem = /\bsystem\b|\bapplication\b|\bapp\b/i.test(subject)

    const [head] = predicate.split(PREP)
    const words = stripArticles(head).split(/\s+/).filter(Boolean)
    if (words.length === 0) continue
    const verb = words[0]
    const object = words.slice(1).join(' ')

    const processKey = add({
      category: 'process',
      name: title(words.slice(0, 4).join(' ')),
      qualifiers: /^(be|have|do|get)$/i.test(verb) || words.length === 1 ? ['low-confidence'] : [],
      statement: st.id,
    })

    let entityKey: string | undefined
    if (object) {
      entityKey = add({
        category: 'entity',
        name: title(object.split(/\s+/).slice(-2).join(' ')),
        qualifiers: ['minimal'],
        statement: st.id,
      })
    }

    let actorKey: string | undefined
    if (subject && !isSystem && subject.split(/\s+/).length <= 3) {
      actorKey = add({ category: 'actor', name: title(subject), qualifiers: [], statement: st.id })
      add({
        category: 'relationship',
        name: `${title(subject)} — ${title(words.slice(0, 4).join(' '))}`,
        qualifiers: [],
        statement: st.id,
        source_item_id: actorKey,
        target_item_id: processKey,
        relation_type: 'association',
      })
      if (entityKey) {
        add({
          category: 'interaction',
          name: `${title(subject)} ${verb.toLowerCase()}s ${object}`,
          qualifiers: ['order-uncertain'],
          statement: st.id,
          source_item_id: actorKey,
          target_item_id: entityKey,
        })
      }
    }

    if (STORE_WORDS.test(st.text) && object) {
      add({ category: 'data_store', name: `${title(object.split(/\s+/).slice(-1)[0])} records`, qualifiers: [], statement: st.id })
    }
    if (FLOW_WORDS.test(st.text)) {
      const hasTarget = /\bto\s+\w+/i.test(predicate)
      add({
        category: 'data_flow',
        name: title(object || verb),
        qualifiers: hasTarget ? [] : ['incomplete'],
        description: hasTarget ? null : 'No clear destination in the requirement.',
        statement: st.id,
        source_item_id: actorKey,
      })
    }
  }

  return [...drafts.values()]
}
