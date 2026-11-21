/** Raj: project roles in the UI (FR24e). A Viewer sees a notice and the change buttons are disabled; the API refuses with 403 too. */
import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { getDb, projectView } from '@/mocks/db'
import { server } from '@/mocks/node'
import { renderApp } from '@/test/render'
import { seedProject } from '@/test/seed'

/** The mock only has Owners, so this answers GET /projects/pr_1 as if the signed-in user were a Viewer. */
function asViewer() {
  server.use(
    http.get('*/projects/:project_id', () =>
      HttpResponse.json({ ...projectView(getDb().projects[0]), role: 'viewer', is_owner: false }),
    ),
  )
}

describe('Viewer role', () => {
  it('shows the Viewer notice and disables New story', async () => {
    seedProject()
    asViewer()
    renderApp('/projects/pr_1/backlog')
    expect(await screen.findByText("You're a Viewer")).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: /New story/ })).toBeDisabled()
  })

  it('shows no notice to an Owner and keeps New story enabled', async () => {
    seedProject()
    renderApp('/projects/pr_1/backlog')
    expect(await screen.findByRole('button', { name: /New story/ })).toBeEnabled()
    expect(screen.queryByText("You're a Viewer")).not.toBeInTheDocument()
  })
})
