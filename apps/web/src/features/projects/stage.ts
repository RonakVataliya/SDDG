import type { Project } from '@/api/client'

export type Stage = 'input' | 'extracting' | 'review' | 'generate' | 'done' | 'failed'

/** Where a project is in the pipeline, used by the project list and to pick the workspace's landing step. */
export function projectStage(p: Project): Stage {
  const x = p.extraction
  if (!x) return 'input'
  if (x.status === 'queued' || x.status === 'running') return 'extracting'
  if (x.status === 'failed') return 'failed'
  if (!p.confirmed) return 'review'
  return p.diagram_count > 0 ? 'done' : 'generate'
}

export const stageLabel: Record<Stage, string> = {
  input: 'Add requirements',
  extracting: 'Extracting…',
  review: 'Review extracted items',
  generate: 'Ready to generate',
  done: 'Diagram ready',
  failed: 'Extraction failed',
}
