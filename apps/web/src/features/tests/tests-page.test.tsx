/**
 * The Tests feature end to end in the browser, against the mock API (src/mocks/testing.ts): design, steps, cases,
 * runs and regression. Coverage and export have their own unit tests (coverage.test.ts, export-tests.test.ts).
 */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { getDb, save } from '@/mocks/db'
import { renderApp } from '@/test/render'
import { seedProject } from '@/test/seed'

const BOOKING =
  'A patient books an appointment 1 to 30 days ahead, may already hold at most 2 upcoming appointments, and picks Consultation, Follow-up or Test.'
const SLOW = 'The appointment list must load fast for receptionists.'
const JOB = { timeout: 10000 }

function seedClinic() {
  seedProject({ confirmed: true, consent: true })
  const source = { document: 'Pasted text', page: null, paragraph: 1 }
  getDb().statements.pr_1 = [
    { id: 'st_4', ref: 'R-004', text: BOOKING, label: 'FR', source },
    { id: 'st_6', ref: 'R-006', text: SLOW, label: 'NFR', source },
  ]
  getDb().items.pr_1 = [
    { id: 'it_a', category: 'entity', name: 'Appointment', description: null, origin: 'system-extracted', qualifiers: [], statement_ids: ['st_4', 'st_6'] },
  ]
  save()
}

async function generate(user: ReturnType<typeof userEvent.setup>, refs: string[]) {
  for (const ref of refs) await user.click(await screen.findByRole('checkbox', { name: `Select ${ref}` }))
  await user.click(screen.getByRole('button', { name: /Generate criteria/ }))
}

describe('Tests page', () => {
  it('is step 5 of the project and opens on the Design tab', async () => {
    seedClinic()
    renderApp('/projects/pr_1/tests')
    expect(await screen.findByRole('link', { name: /Tests/ })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Design', selected: true })).toBeInTheDocument()
    expect(screen.queryByRole('complementary', { name: 'Generate' })).not.toBeInTheDocument()
    expect(await screen.findByText('Pick requirements and generate')).toBeInTheDocument()
  })

  it('designs a requirement: criteria, classes, boundaries and drafts, and edits a limit with no AI call', async () => {
    seedClinic()
    const user = userEvent.setup()
    renderApp('/projects/pr_1/tests')
    await generate(user, ['R-004'])
    await waitFor(() => expect(screen.getByTestId('draft-summary')).toHaveTextContent('13 from conditions + 2 from flows'), JOB)
    const conditions = screen.getByRole('region', { name: 'Conditions' })
    expect(within(conditions).getByText('invalid > 30')).toBeInTheDocument()
    expect(within(conditions).getByText('31')).toBeInTheDocument()

    const upper = within(conditions).getByLabelText('days_ahead upper limit')
    await user.clear(upper)
    await user.type(upper, '60{Enter}')
    await waitFor(() => expect(within(screen.getByRole('region', { name: 'Conditions' })).getByText('61')).toBeInTheDocument())
    expect(getDb().jobs.filter((j) => j.kind === 'test_criteria')).toHaveLength(1)
    // Unchanged drafts keep their numbers; the three changed ones reuse the numbers they replace.
    const numbers = within(screen.getByRole('region', { name: 'Draft test cases' }))
      .getAllByRole('checkbox')
      .map((b) => b.getAttribute('aria-label'))
    expect(numbers).toEqual(Array.from({ length: 15 }, (_, i) => `Keep TC-${String(i + 1).padStart(3, '0')}`))
  }, 30000)

  it('asks a question for a vague requirement and regenerates it once the requirement is clearer', async () => {
    seedClinic()
    const user = userEvent.setup()
    renderApp('/projects/pr_1/tests')
    await generate(user, ['R-006'])
    expect(screen.getByText(/R-006 has an open Ambiguous flag/)).toBeInTheDocument()
    const answer = await screen.findByLabelText('Your answer', {}, JOB)
    await user.type(answer, 'under 2 seconds with 50 receptionists at once')
    await user.click(screen.getByRole('button', { name: 'Save answer' }))
    const suggestion = await screen.findByLabelText('Suggested requirement')
    await user.clear(suggestion)
    await user.type(suggestion, 'The appointment list loads in under 2 seconds with 50 receptionists at once.')
    await user.click(screen.getByRole('button', { name: 'Use this requirement' }))
    await user.click(await screen.findByRole('button', { name: 'Regenerate R-006' }))
    await waitFor(() => expect(screen.getByText(/Performance: response time < 2 s/)).toBeInTheDocument(), JOB)
  }, 30000)

  it('writes steps only for kept drafts, then lists them on the Cases tab', async () => {
    seedClinic()
    const user = userEvent.setup()
    renderApp('/projects/pr_1/tests')
    await generate(user, ['R-004'])
    await screen.findByRole('checkbox', { name: 'Keep TC-005' }, JOB)
    for (const n of ['005', '006', '007', '008']) { // days_ahead = 1, 2, 29, 30
      const keep = screen.getByRole('checkbox', { name: `Keep TC-${n}` })
      await waitFor(() => expect(keep).toBeEnabled())
      await user.click(keep)
      await waitFor(() => expect(keep).not.toBeChecked())
    }
    await user.click(await screen.findByRole('button', { name: 'Write steps for 11' }))
    await waitFor(() => expect(getDb().tests.cases.filter((c) => (c as { status: string }).status === 'ready')).toHaveLength(11), JOB)

    await user.click(screen.getByRole('tab', { name: 'Cases' }))
    const table = await screen.findByRole('region', { name: 'Test cases' })
    await user.click(await within(table).findByRole('button', { name: /ready 11/i }, JOB))
    expect(within(table).getAllByRole('row')).toHaveLength(12)
    await user.click(within(table).getByText('days_ahead = 31 (above 30) → rejected'))
    const detail = screen.getByRole('complementary', { name: /Case TC-0/ })
    expect(within(detail).getByText(/Enter days_ahead = 31/)).toBeInTheDocument()
    expect(within(detail).getByText(/refuses the input/)).toBeInTheDocument()
  }, 30000)

  it('runs cases by hand, keeps the record, and builds a regression run after a requirement changes', async () => {
    seedClinic()
    const user = userEvent.setup()
    renderApp('/projects/pr_1/tests')
    await generate(user, ['R-004'])
    await user.click(await screen.findByRole('button', { name: 'Write steps for 15' }, JOB))
    await waitFor(() => expect(getDb().tests.cases.every((c) => (c as { status: string }).status === 'ready')).toBe(true), JOB)

    await user.click(screen.getByRole('tab', { name: 'Runs' }))
    await user.click(await screen.findByRole('button', { name: /Start run/ }))
    const dialog = await screen.findByRole('dialog')
    expect(await within(dialog).findByText(/15 cases · every case with steps/)).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Start run' }))

    expect(await screen.findByText('0 of 15 marked')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Pass/ }))
    await waitFor(() => expect(screen.getByText('1 of 15 marked')).toBeInTheDocument())
    await user.type(screen.getByLabelText('Note'), 'Calendar still lets me pick day 31.')
    await user.click(screen.getByRole('button', { name: /Fail/ }))
    await waitFor(() => expect(screen.getByText('2 of 15 marked')).toBeInTheDocument())
    expect(screen.getByText(/Marked Fail by dev@sddg.test|Not marked yet/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Finish run' }))

    const runs = await screen.findByRole('region', { name: 'Runs' })
    expect(within(runs).getByText(/1 pass · 1 fail/)).toBeInTheDocument()
    expect(await screen.findByRole('region', { name: 'Notes from the last run' })).toHaveTextContent('Calendar still lets me pick day 31.')

    // A change request on R-004: every case linked to it is now out of date and in the regression run.
    const st = getDb().statements.pr_1.find((s) => s.id === 'st_4')!
    st.text = BOOKING.replace('30 days', '45 days')
    save()
    await user.click(screen.getByRole('button', { name: /Start run/ }))
    const next = await screen.findByRole('dialog')
    await user.click(within(next).getByRole('radio', { name: /Regression/ }))
    expect(await within(next).findByText('failed last run · R-004 changed')).toBeInTheDocument()
    await user.click(within(next).getByRole('radio', { name: /Minimal set/ }))
    expect(within(next).getByText(/can miss faults/)).toBeInTheDocument()
  }, 40000)
})
