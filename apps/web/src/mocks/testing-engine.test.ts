import { describe, expect, it } from 'vitest'
import { boundariesFor, buildDrafts, classesFor, fakeCriteria, type EngineCondition } from './testing-engine'

// The booking requirement from the walkthrough (R-004); services/ai-extraction/tests/test_testgen_blackbox.py checks the same numbers.
const days: EngineCondition = { name: 'days_ahead', kind: 'range', min: 1, max: 30, values: [], invalid_values: [] }
const held: EngineCondition = { name: 'held', kind: 'count', min: 0, max: 2, values: [], invalid_values: [] }
const type: EngineCondition = { name: 'type', kind: 'set', min: null, max: null, values: ['Consultation', 'Follow-up', 'Test'], invalid_values: ['Surgery'] }

describe('mock black-box engine', () => {
  it('builds the classes from the walkthrough', () => {
    expect(classesFor(days).map((c) => [c.label, c.valid])).toEqual([['1–30', true], ['< 1', false], ['> 30', false]])
    expect(classesFor(held).map((c) => [c.label, c.valid])).toEqual([['0–2', true], ['> 2', false]])
    expect(classesFor(type).filter((c) => !c.valid).map((c) => c.label)).toEqual(['Surgery'])
  })

  it('builds the boundaries from the walkthrough', () => {
    expect(boundariesFor(days).map((b) => b.value)).toEqual([0, 1, 2, 29, 30, 31])
    expect(boundariesFor(days).filter((b) => !b.valid).map((b) => b.value)).toEqual([0, 31])
    expect(boundariesFor(held).map((b) => b.value)).toEqual([0, 2, 3])
  })

  it('makes 13 drafts from the conditions and 2 more from the flows', () => {
    const fromConditions = buildDrafts([days, held, type], [], [], [])
    expect(fromConditions).toHaveLength(13)
    expect(fromConditions.filter((d) => d.kind === 'positive')).toHaveLength(3)
    expect(fromConditions[0].test_data).toEqual({ days_ahead: 15, held: 1, type: 'Consultation' })
    expect(fromConditions.map((d) => d.title)).toContain('days_ahead = 31 (above 30) → rejected')
    const withFlows = buildDrafts([days, held, type], [{ kind: 'basic', text: 'book' }, { kind: 'alternate', text: 'slot taken' }], [], [])
    expect(withFlows).toHaveLength(15)
  })

  it('turns vague wording into a question instead of tests', () => {
    const design = fakeCriteria('The appointment list must load fast for receptionists.')
    expect(design.testable).toBe(false)
    expect(design.suggestion_template).toContain('{answer}')
  })
})
