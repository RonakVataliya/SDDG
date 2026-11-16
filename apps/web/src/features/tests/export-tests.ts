/**
 * CSV and Gherkin export of the Tests feature (stream 6, section 11). Plain functions over data the page already
 * loaded: no AI and no extra request.
 *
 * - CSV: one row per test case, every case (drafts included), with steps and test data in one cell each.
 * - Gherkin: one Feature per requirement. Cases with steps become Scenarios; the boundary cases of one condition
 *   become a single Scenario Outline whose Examples table lists each boundary value and the expected outcome.
 */
import type { TestCase, TestRequirementSummary } from '@/api/client'

/** True now that the export is implemented; the Export buttons are enabled. */
export const EXPORTS_READY: boolean = true

const CSV_HEADER = [
  'Case', 'Requirement', 'Title', 'Technique', 'Kind', 'Priority', 'Status', 'Freshness',
  'Preconditions', 'Steps', 'Test data', 'Expected result', 'Last result',
]

/** RFC 4180: quote a field that holds a comma, quote or line break, doubling any quotes inside it. */
export function csvField(value: string) {
  return /[",\r\n]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value
}

const numbered = (lines: string[]) => lines.map((l, i) => `${i + 1}. ${l}`).join('\n')
const dataText = (data: Record<string, string | number>) =>
  Object.entries(data)
    .map(([k, v]) => `${k} = ${v}`)
    .join('; ')

/** One row per test case. Starts with a byte-order mark so Excel reads the dashes and arrows correctly. */
export function testsToCsv(cases: TestCase[], _requirements: TestRequirementSummary[]): string {
  const rows = cases.map((c) => [
    c.number,
    c.statement_ref,
    c.title,
    c.technique,
    c.kind,
    c.priority,
    c.status,
    c.freshness === 'out_of_date' ? 'out of date' : 'current',
    c.preconditions.join('\n'),
    numbered(c.steps),
    dataText(c.test_data),
    c.expected ?? '',
    c.last_result ?? '',
  ])
  return '\uFEFF' + [CSV_HEADER, ...rows].map((r) => r.map(csvField).join(',')).join('\r\n') + '\r\n'
}

/* ---------- Gherkin ---------- */

const cell = (v: string | number) => String(v).replace(/\\/g, '\\\\').replace(/\|/g, '\\|')
const oneLine = (s: string) => s.replace(/\s+/g, ' ').trim()

/** The condition a boundary case varies, from its covers tag "BVA:<condition>:<value>". */
export function boundaryCondition(c: TestCase): string | null {
  const tag = c.covers.find((t) => t.startsWith('BVA:'))
  return tag ? tag.split(':')[1] : null
}

function table(rows: string[][]) {
  const widths = rows[0].map((_, i) => Math.max(...rows.map((r) => r[i].length)))
  return rows.map((r) => `      | ${r.map((v, i) => v.padEnd(widths[i])).join(' | ')} |`).join('\n')
}

function steps(keyword: 'Given' | 'When' | 'Then', lines: string[]) {
  return lines.map((l, i) => `    ${i === 0 ? keyword : 'And'} ${oneLine(l)}`)
}

function scenario(c: TestCase) {
  return [
    `  # ${c.technique} · ${c.kind} · ${c.priority}${c.freshness === 'out_of_date' ? ' · out of date' : ''}`,
    `  Scenario: ${c.number} ${oneLine(c.title)}`,
    ...steps('Given', c.preconditions.length ? c.preconditions : ['the system is ready for testing']),
    ...steps('When', c.steps),
    ...steps('Then', [c.expected ?? 'the result matches the requirement']),
  ].join('\n')
}

function outline(ref: string, condition: string, group: TestCase[]) {
  const keys = [...new Set(group.flatMap((c) => Object.keys(c.test_data)))]
  const first = group.find((c) => c.preconditions.length) ?? group[0]
  return [
    `  # Boundary value analysis: one example per boundary of ${condition}`,
    `  Scenario Outline: ${ref} ${condition} boundaries`,
    ...steps('Given', first.preconditions.length ? first.preconditions : ['the system is ready for testing']),
    `    When the tester submits ${keys.map((k) => `${k} = <${k}>`).join(', ')}`,
    `    Then the input is <outcome>`,
    '',
    '    Examples:',
    table([
      ['case', ...keys, 'outcome'],
      ...group.map((c) => [c.number, ...keys.map((k) => cell(c.test_data[k] ?? '')), c.outcome ?? '']),
    ]),
  ].join('\n')
}

/** One Feature per requirement that has kept cases. Drafts without steps appear only in boundary outlines,
 *  which need just their test data. Discarded drafts are left out. */
export function testsToGherkin(cases: TestCase[], requirements: TestRequirementSummary[]): string {
  const features: string[] = []
  for (const r of requirements) {
    const mine = cases.filter((c) => c.statement_id === r.statement_id && c.kept)
    if (!mine.length) continue
    const groups = new Map<string, TestCase[]>()
    const singles: TestCase[] = []
    for (const c of mine) {
      const condition = boundaryCondition(c)
      if (condition) groups.set(condition, [...(groups.get(condition) ?? []), c])
      else if (c.steps.length) singles.push(c)
    }
    const blocks = [...singles.map(scenario), ...[...groups].map(([condition, g]) => outline(r.ref, condition, g))]
    if (!blocks.length) continue
    features.push([`Feature: ${r.ref} ${oneLine(r.text)}`, '', blocks.join('\n\n')].join('\n'))
  }
  return `# Exported from SDDG: ${cases.length} test cases\n\n${features.join('\n\n')}\n`
}
