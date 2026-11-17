/**
 * MOCK ONLY. Stands in for the PlantUML source the real backend stores with each diagram (served by
 * GET /diagrams/{id}/export?format=source and put in the project ZIP). Built from the mock's use-case model.
 */
import type { UseCaseModel } from './render'

const quote = (s: string) => `"${s.replace(/"/g, "'")}"`

export function useCaseSource(model: UseCaseModel): string {
  const lines = ['@startuml', 'left to right direction', `rectangle ${quote(model.system)} {`]
  model.cases.forEach((c, i) => lines.push(`  usecase ${quote(c.name)} as UC${i + 1}${c.assumed ? ' #FBF1DF' : ''}`))
  lines.push('}')
  model.actors.forEach((a, i) => lines.push(`actor ${quote(a.name)} as A${i + 1}`))
  for (const link of model.links) {
    const a = model.actors.findIndex((x) => x.id === link.actor)
    const c = model.cases.findIndex((x) => x.id === link.case)
    if (a >= 0 && c >= 0) lines.push(`A${a + 1} --> UC${c + 1}`)
  }
  lines.push('@enduml')
  return lines.join('\n') + '\n'
}
