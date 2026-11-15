/**
 * CSV and Gherkin export of the Tests feature (stream 6, section 11).
 *
 * STUB from the API contract commit: the signatures are fixed so the Tests page can wire its Export buttons now.
 * The real implementation replaces the bodies below and sets EXPORTS_READY to true.
 */
import type { TestCase, TestRequirementSummary } from '@/api/client'

/** False until the export commit lands; the Export buttons stay disabled while it is false. */
export const EXPORTS_READY: boolean = false

/** One row per test case. */
export function testsToCsv(_cases: TestCase[], _requirements: TestRequirementSummary[]): string {
  return ''
}

/** One Feature per requirement; a condition's boundary cases become one Scenario Outline with an Examples table. */
export function testsToGherkin(_cases: TestCase[], _requirements: TestRequirementSummary[]): string {
  return ''
}
