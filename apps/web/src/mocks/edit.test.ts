import { applyInstruction, type EditResult } from './edit'
import type { UseCaseModel } from './render'

const model: UseCaseModel = {
  system: 'Canteen',
  actors: [
    { id: 'a1', name: 'Student' },
    { id: 'a2', name: 'Canteen staff' },
  ],
  cases: [
    { id: 'c1', name: 'Browse canteen menu', assumed: false },
    { id: 'c2', name: 'Add to cart', assumed: false },
    { id: 'c3', name: 'Log in', assumed: true },
  ],
  links: [
    { actor: 'a1', case: 'c1' },
    { actor: 'a1', case: 'c2' },
  ],
}

const ok = (r: EditResult) => {
  if (!r.ok) throw new Error(r.detail)
  return r.model
}

describe('mock diagram edits', () => {
  it('renames a use case, ignoring "the" and letter case', () => {
    const next = ok(applyInstruction(model, 'edit the browse canteen menu to browse menu card'))
    expect(next.cases[0].name).toBe('Browse menu card')
    expect(model.cases[0].name).toBe('Browse canteen menu') // the old version is untouched
  })

  it('renames a name that contains the word "to"', () => {
    expect(ok(applyInstruction(model, 'rename Add to cart to Add to basket')).cases[1].name).toBe('Add to basket')
  })

  it('removes an element and its lines', () => {
    const next = ok(applyInstruction(model, 'remove the Student actor'))
    expect(next.actors.map((a) => a.name)).toEqual(['Canteen staff'])
    expect(next.links).toEqual([])
  })

  it('adds a use case linked to an actor', () => {
    const next = ok(applyInstruction(model, 'add use case rate a dish for student'))
    const added = next.cases.at(-1)!
    expect(added.name).toBe('Rate a dish')
    expect(next.links).toContainEqual({ actor: 'a1', case: added.id })
  })

  it('connects an actor to a use case', () => {
    expect(ok(applyInstruction(model, 'connect Canteen staff to Log in')).links).toContainEqual({ actor: 'a2', case: 'c3' })
  })

  it('explains what it can do when it does not understand', () => {
    const r = applyInstruction(model, 'make it prettier')
    expect(r.ok).toBe(false)
    expect(!r.ok && r.detail).toMatch(/Try something like/)
  })

  it('says when the element is not in the diagram', () => {
    const r = applyInstruction(model, 'remove Pay bill')
    expect(!r.ok && r.detail).toMatch(/couldn.t find “Pay bill”/)
  })
})
