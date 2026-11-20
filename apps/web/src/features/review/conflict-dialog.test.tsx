/** Raj: edit conflict check (FR24f). Priya saves R-001 while it is open in the editor; saving shows both versions,
 * and each of the three buttons does what it says. */
import { configure, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { getDb, save } from '@/mocks/db'
import { renderApp } from '@/test/render'
import { seedProject } from '@/test/seed'

configure({ asyncUtilTimeout: 5000 })
vi.setConfig({ testTimeout: 20000 })

const THEIRS = 'The librarian shall issue up to five books to a member.'
const MINE = 'The librarian shall issue a book to a registered member.'

/** What Priya's save does to the stored requirement while this browser still has revision 1 open. */
function priyaSaves() {
  const db = getDb()
  const st = db.statements.pr_1[0]
  st.text = THEIRS
  st.revision = 2
  ;(db.lastSaved ??= {})[st.id] = { by: 'priya@sddg.test', at: new Date().toISOString() }
  save()
}

async function conflictOpen() {
  seedProject()
  const user = userEvent.setup()
  renderApp('/projects/pr_1/review')
  await user.click(await screen.findByRole('button', { name: 'Edit R-001' }))
  expect(screen.getByText('based on rev 1')).toBeInTheDocument()
  priyaSaves()
  const box = screen.getByLabelText('Requirement text')
  await user.clear(box)
  await user.type(box, MINE)
  await user.click(screen.getByRole('button', { name: 'Save' }))
  return { user, dialog: await screen.findByRole('dialog') }
}

describe('Edit conflict (FR24f)', () => {
  it('shows who saved, both versions with the changed words marked, and saves nothing', async () => {
    const { dialog } = await conflictOpen()
    expect(within(dialog).getByRole('heading', { name: 'Someone else changed R-001' })).toBeInTheDocument()
    expect(within(dialog).getByText('Priya saved revision 2 while you were editing revision 1. Nothing was overwritten.')).toBeInTheDocument()
    const theirs = within(dialog).getByRole('region', { name: /^Priya's version · rev 2/ })
    expect(theirs).toHaveTextContent(THEIRS)
    expect(within(theirs).getAllByText('five').every((el) => el.tagName === 'MARK')).toBe(true)
    const mine = within(dialog).getByRole('region', { name: 'Your change · based on rev 1' })
    expect(within(mine).getByText('registered').tagName).toBe('MARK')
    expect(getDb().statements.pr_1[0]).toMatchObject({ text: THEIRS, revision: 2 }) // nothing overwritten
  })

  it('Cancel goes back to the editor with my text', async () => {
    const { user, dialog } = await conflictOpen()
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Requirement text')).toHaveValue(MINE)
    expect(getDb().statements.pr_1[0].revision).toBe(2)
  })

  it("Use Priya's version drops my change and shows hers", async () => {
    const { user, dialog } = await conflictOpen()
    await user.click(within(dialog).getByRole('button', { name: "Use Priya's version" }))
    expect(await screen.findByText(THEIRS)).toBeInTheDocument()
    expect(screen.queryByLabelText('Requirement text')).not.toBeInTheDocument()
    expect(getDb().statements.pr_1[0].revision).toBe(2)
  })

  it('Copy my change on top shows the editable result and saves it as rev 3', async () => {
    const { user, dialog } = await conflictOpen()
    await user.click(within(dialog).getByRole('button', { name: 'Copy my change on top' }))
    const result = within(dialog).getByRole('region', { name: 'Result · will be saved as rev 3' })
    const box = within(result).getByLabelText('Result text')
    expect(box).toHaveValue('The librarian shall issue up to five books to a registered member.') // her change and mine
    await user.click(within(dialog).getByRole('button', { name: 'Save as rev 3' }))
    await waitFor(() =>
      expect(getDb().statements.pr_1[0]).toMatchObject({ revision: 3, text: 'The librarian shall issue up to five books to a registered member.' }),
    )
    expect(await screen.findByText('Saved R-001 as revision 3')).toBeInTheDocument()
    expect(screen.getByText('rev 3 · Saved')).toBeInTheDocument()
  })
})
