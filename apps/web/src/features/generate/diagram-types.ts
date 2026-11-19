import type { DiagramType } from '@/api/client'

export const DIAGRAM_TYPES: { value: DiagramType; label: string; shows: string; available: boolean }[] = [
  { value: 'use_case', label: 'Use Case', shows: 'Actors and what they can do in the system', available: true },
  { value: 'class', label: 'Class', shows: 'Entities, their attributes and relationships', available: false },
  { value: 'activity', label: 'Activity', shows: 'Process flow with decisions', available: false },
  { value: 'sequence', label: 'Sequence', shows: 'Who talks to whom, in order', available: false },
  { value: 'dfd', label: 'Data Flow (DFD)', shows: 'Processes, flows, stores and external entities', available: false },
  { value: 'component', label: 'Component', shows: 'System parts and their interfaces', available: false },
  // Drawn when the subsystem decomposition is confirmed in the Design step; never generated here.
  { value: 'package', label: 'Package', shows: 'Subsystems by layer, from the Design step', available: false },
]

export const typeLabel = Object.fromEntries(DIAGRAM_TYPES.map((t) => [t.value, t.label])) as Record<DiagramType, string>

/** Extraction nodes each diagram needs (mirrors services/ai-extraction/app/graph/node_sets.py DIAGRAM_NODES + hard prerequisites). */
export const NODE_LABEL: Record<string, string> = { actors: 'actors', entities: 'entities', processes: 'processes', dataflows: 'data flows', interactions: 'interactions', relationships: 'relationships' }
export const NEEDS: Record<DiagramType, string[]> = {
  use_case: ['actors', 'processes', 'interactions'],
  dfd: ['actors', 'processes', 'dataflows'],
  class: ['entities', 'relationships'],
  sequence: ['actors', 'entities', 'processes', 'interactions'],
  activity: ['processes'],
  component: ['processes', 'entities', 'relationships'],
  package: [],
}
export const ALL_NODES = Object.keys(NODE_LABEL)
