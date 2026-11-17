/** Shared wording and badge tones for the Tests feature, so every tab names things the same way. */
import type { CaseKind, CasePriority, CaseTechnique, ResultStatus, RunMode } from '@/api/client'

type Tone = 'neutral' | 'teal' | 'amber' | 'violet' | 'danger'

export const KIND: Record<CaseKind, { label: string; tone: Tone }> = {
  positive: { label: 'Positive', tone: 'teal' },
  negative: { label: 'Negative', tone: 'danger' },
  edge: { label: 'Edge', tone: 'amber' },
}

export const PRIORITY: Record<CasePriority, string> = { high: 'High', medium: 'Medium', low: 'Low' }

export const TECHNIQUE: Record<CaseTechnique, string> = {
  EC: 'Equivalence class',
  BVA: 'Boundary value',
  'BVA+EC': 'Boundary value outside the valid class',
  Flow: 'Use-case flow',
  NFR: 'Non-functional target',
  AC: 'Acceptance criterion',
  Manual: 'Written by hand',
}

export const RESULT: Record<ResultStatus, { label: string; tone: Tone; dot: string }> = {
  pass: { label: 'Pass', tone: 'teal', dot: 'bg-teal' },
  fail: { label: 'Fail', tone: 'danger', dot: 'bg-danger' },
  blocked: { label: 'Blocked', tone: 'amber', dot: 'bg-amber' },
  skipped: { label: 'Skipped', tone: 'neutral', dot: 'bg-slate' },
}

export const RUN_MODE: Record<RunMode, { label: string; hint: string }> = {
  all: { label: 'All ready cases', hint: 'Every case with steps' },
  failed: { label: 'Failed or blocked last time', hint: 'Cases that failed or were blocked in the last finished run' },
  regression: { label: 'Regression', hint: 'Cases linked to changed requirements, failed ones first' },
  minimal: { label: 'Minimal set', hint: 'One positive, one negative and one edge case per requirement' },
  pick: { label: 'Pick cases', hint: 'Choose by hand' },
}

/** "days_ahead = 31 · held = 1 · Consultation" style summary of a case's test data. */
export function testDataLine(data: Record<string, string | number>) {
  return Object.entries(data)
    .map(([k, v]) => `${k} ${v}`)
    .join(' · ')
}
