import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MOCK_SETTINGS, makeAdmin, resetAdminMock } from '@/mocks/admin'
import { server } from '@/mocks/node'
import { renderApp } from '@/test/render'

beforeEach(() => {
  resetAdminMock()
  makeAdmin('dev@sddg.test')
})

const value = (label: string) => within(screen.getByText(label).parentElement!).getAllByText(/./)[1]

describe('Admin Settings page', () => {
  it('is reached from the sidebar and shows the read-only values, never a key', async () => {
    const user = userEvent.setup()
    renderApp('/admin/users')
    await user.click(await screen.findByRole('link', { name: 'Settings' }))

    expect(await screen.findByRole('heading', { name: 'Settings' })).toBeInTheDocument()
    expect(screen.getByText('Read only')).toBeInTheDocument()
    expect(await screen.findByText('Groq - openai/gpt-oss-120b, fallback: Gemini')).toBeInTheDocument()
    expect(value('AI provider key')).toHaveTextContent('set - never sent to the browser')
    expect(value('AI wait on rate limit')).toHaveTextContent('A job waits up to 10 minutes for AI capacity')
    expect(value('Storage limit')).toHaveTextContent('500 MB')
    expect(value('Invitation expiry')).toHaveTextContent('7 days')
    expect(value('Session timeout')).toHaveTextContent('24 hours of inactivity')
    expect(value('Failed logins before lock')).toHaveTextContent('5, 15 minute lock')
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument() // nothing to edit
  })

  it('says so when the AI service is down or a value is owned by Supabase Auth', async () => {
    server.use(
      http.get('*/admin/settings', () =>
        HttpResponse.json({
          ...MOCK_SETTINGS, ai: { reachable: false, providers: [], job_deadline_seconds: 600 }, ai_key_set: null,
          session_timeout_hours: null, failed_logins_before_lock: null, lock_minutes: null,
        }),
      ),
    )
    renderApp('/admin/settings')
    expect(await screen.findByText("Couldn't reach the AI service")).toBeInTheDocument()
    expect(value('AI provider key')).toHaveTextContent('Unknown')
    expect(value('Session timeout')).toHaveTextContent('Set in Supabase Auth')
    expect(value('Failed logins before lock')).toHaveTextContent('Set in Supabase Auth')
  })

  it('refuses a user who is not an administrator', async () => {
    resetAdminMock()
    renderApp('/admin/settings')
    expect(await screen.findByText('Administrators only')).toBeInTheDocument()
  })
})
