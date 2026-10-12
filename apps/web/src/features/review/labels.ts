import type { ItemCategory, Schemas } from '@/api/client'

export const CATEGORIES: { value: ItemCategory; label: string; plural: string }[] = [
  { value: 'actor', label: 'Actor', plural: 'Actors' },
  { value: 'entity', label: 'Entity', plural: 'Entities' },
  { value: 'process', label: 'Process', plural: 'Processes' },
  { value: 'data_flow', label: 'Data flow', plural: 'Data flows' },
  { value: 'data_store', label: 'Data store', plural: 'Data stores' },
  { value: 'interaction', label: 'Interaction', plural: 'Interactions' },
  { value: 'relationship', label: 'Relationship', plural: 'Relationships' },
]
export const categoryLabel = Object.fromEntries(CATEGORIES.map((c) => [c.value, c.label])) as Record<ItemCategory, string>

/** Plain-language explanation for each qualifier the extractor can attach (FR4b–f). */
export const QUALIFIERS: Record<Schemas['ItemQualifier'], { label: string; hint: string }> = {
  minimal: { label: 'Minimal', hint: 'Mentioned but never described in the requirements.' },
  'low-confidence': { label: 'Low confidence', hint: 'This may not be a real process. Check the wording.' },
  incomplete: { label: 'Incomplete', hint: 'No clear source or destination was found.' },
  'order-uncertain': { label: 'Order uncertain', hint: 'The order of this interaction could not be inferred.' },
  'needs-review': { label: 'Needs review', hint: 'Relationship type unknown; defaulted to association.' },
}
