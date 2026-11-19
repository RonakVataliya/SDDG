import type { Project } from '@/api/client'

export type Stage = 'input' | 'extracting' | 'review' | 'generate' | 'done' | 'failed'

/**
 * Requirements-first: 1 add requirements → 2 review & confirm them → 3 choose diagrams (building blocks are
 * extracted then) → 4 diagrams. Used by the project list and to pick the workspace's landing step.
 */
export function projectStage(p: Project): Stage {
  const x = p.extraction
  if (x?.status === 'queued' || x?.status === 'running' || x?.status === 'waiting') return 'extracting'
  if (p.statement_count === 0) return x?.status === 'failed' ? 'failed' : 'input'
  if (!p.confirmed) return 'review'
  return p.diagram_count > 0 ? 'done' : 'generate'
}

export const stageLabel: Record<Stage, string> = {
  input: 'Add requirements',
  extracting: 'Finding requirements…',
  review: 'Review requirements',
  generate: 'Choose diagrams',
  done: 'Diagrams ready',
  failed: 'Finding requirements failed',
}

export const stageStep: Record<Stage, number> = { input: 1, extracting: 1, failed: 1, review: 2, generate: 3, done: 4 }
