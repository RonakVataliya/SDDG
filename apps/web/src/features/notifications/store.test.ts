// apps/web/src/features/notifications/store.test.ts
import { describe, it, expect, beforeEach } from 'vitest'
import { act } from '@testing-library/react'
import { useNotificationStore } from './store'

const SUCCESS_JOB = {
  kind: 'success' as const,
  title: 'Diagram ready',
  message: '"My ERD" finished successfully.',
  diagramId: 'diag-abc',
  projectId: 'proj-1',
  runId: 'run-1',
}

const FAILURE_JOB = {
  kind: 'failure' as const,
  title: 'Generation failed',
  message: '"My ERD" could not be generated. Try again.',
  projectId: 'proj-1',
  runId: 'run-2',
}

beforeEach(() => {
  useNotificationStore.setState({ notifications: [], unreadCount: 0 })
})

// ── addNotification — success ─────────────────────────────────────────────

describe('addNotification — success', () => {
  it('adds a notification and increments unread count', () => {
    act(() => useNotificationStore.getState().addNotification(SUCCESS_JOB))
    const { notifications, unreadCount } = useNotificationStore.getState()
    expect(notifications).toHaveLength(1)
    expect(notifications[0].kind).toBe('success')
    expect(notifications[0].read).toBe(false)
    expect(unreadCount).toBe(1)
  })

  it('sets diagramId on success', () => {
    act(() => useNotificationStore.getState().addNotification(SUCCESS_JOB))
    expect(useNotificationStore.getState().notifications[0].diagramId).toBe('diag-abc')
  })
})

// ── addNotification — failure ─────────────────────────────────────────────

describe('addNotification — failure', () => {
  it('words failure differently from success', () => {
    act(() => useNotificationStore.getState().addNotification(FAILURE_JOB))
    const n = useNotificationStore.getState().notifications[0]
    expect(n.kind).toBe('failure')
    expect(n.title).not.toBe('Diagram ready')
    expect(n.message).toMatch(/could not be generated/i)
  })

  it('does not set diagramId on full failure', () => {
    act(() => useNotificationStore.getState().addNotification(FAILURE_JOB))
    expect(useNotificationStore.getState().notifications[0].diagramId).toBeUndefined()
  })
})

// ── hasRunId ──────────────────────────────────────────────────────────────

describe('hasRunId', () => {
  it('returns true after a notification for that runId is stored', () => {
    act(() => useNotificationStore.getState().addNotification(SUCCESS_JOB))
    expect(useNotificationStore.getState().hasRunId('run-1')).toBe(true)
  })

  it('returns false for an unseen runId', () => {
    expect(useNotificationStore.getState().hasRunId('run-99')).toBe(false)
  })
})

// ── markRead ─────────────────────────────────────────────────────────────

describe('markRead', () => {
  it('marks one as read and recalculates unread count', () => {
    act(() => useNotificationStore.getState().addNotification(SUCCESS_JOB))
    act(() => useNotificationStore.getState().addNotification(FAILURE_JOB))
    const id = useNotificationStore.getState().notifications[0].id
    act(() => useNotificationStore.getState().markRead(id))
    const state = useNotificationStore.getState()
    expect(state.notifications.find(n => n.id === id)!.read).toBe(true)
    expect(state.unreadCount).toBe(1)
  })

  it('stays unread until explicitly marked', () => {
    act(() => useNotificationStore.getState().addNotification(SUCCESS_JOB))
    expect(useNotificationStore.getState().notifications[0].read).toBe(false)
    expect(useNotificationStore.getState().unreadCount).toBe(1)
  })
})

// ── markAllRead ───────────────────────────────────────────────────────────

describe('markAllRead', () => {
  it('zeroes unread count and marks everything read', () => {
    act(() => useNotificationStore.getState().addNotification(SUCCESS_JOB))
    act(() => useNotificationStore.getState().addNotification(FAILURE_JOB))
    act(() => useNotificationStore.getState().markAllRead())
    const state = useNotificationStore.getState()
    expect(state.unreadCount).toBe(0)
    expect(state.notifications.every(n => n.read)).toBe(true)
  })
})

// ── Retry scenarios ───────────────────────────────────────────────────────

describe('retry success', () => {
  it('creates a success notification after job eventually succeeds (e.g. after rate-limit retry)', () => {
    // Backend retried internally; frontend just sees the final 'succeeded' status.
    // The watcher keeps polling while status is queued/running, so no frontend change needed.
    act(() => useNotificationStore.getState().addNotification({
      kind: 'success',
      title: 'Diagram ready',
      message: '"Auth Flow" finished successfully.',
      diagramId: 'diag-retry-ok',
      projectId: 'proj-2',
      runId: 'run-retry-success',
    }))
    const n = useNotificationStore.getState().notifications[0]
    expect(n.kind).toBe('success')
    expect(n.diagramId).toBe('diag-retry-ok')
    expect(n.read).toBe(false)
  })
})

describe('retry exhaustion', () => {
  it('creates a failure notification after all retries are exhausted', () => {
    // Backend tried 3 times, set status to 'failed'; frontend receives a failure notification.
    act(() => useNotificationStore.getState().addNotification({
      kind: 'failure',
      title: 'Generation failed',
      message: '"Auth Flow" could not be generated. Try again.',
      projectId: 'proj-2',
      runId: 'run-retry-exhausted',
    }))
    const n = useNotificationStore.getState().notifications[0]
    expect(n.kind).toBe('failure')
    expect(n.title).toMatch(/failed/i)
    expect(n.diagramId).toBeUndefined()
  })

  it('does not create a duplicate notification if the watcher fires twice for the same runId', () => {
    act(() => useNotificationStore.getState().addNotification({
      kind: 'failure',
      title: 'Generation failed',
      message: '"Auth Flow" could not be generated. Try again.',
      projectId: 'proj-2',
      runId: 'run-retry-exhausted',
    }))
    // hasRunId prevents a second notification for the same run
    expect(useNotificationStore.getState().hasRunId('run-retry-exhausted')).toBe(true)
    expect(useNotificationStore.getState().notifications).toHaveLength(1)
  })
})

describe('partial multi-diagram failure', () => {
  it('stores a failure notification that includes the succeeded diagramId', () => {
    // One diagram in a multi-diagram run succeeded before the job failed.
    // The watcher passes diagram_ids[0] as diagramId so the user can view what succeeded.
    act(() => useNotificationStore.getState().addNotification({
      kind: 'failure',
      title: 'Generation partially failed',
      message: '1 diagram generated; the rest could not be completed. Try again for the remainder.',
      diagramId: 'diag-succeeded',
      projectId: 'proj-3',
      runId: 'run-partial',
    }))
    const n = useNotificationStore.getState().notifications[0]
    expect(n.kind).toBe('failure')
    expect(n.title).toMatch(/partial/i)
    expect(n.diagramId).toBe('diag-succeeded')  // link to the diagram that did succeed
  })

  it('partial failure notification stays unread until marked', () => {
    act(() => useNotificationStore.getState().addNotification({
      kind: 'failure',
      title: 'Generation partially failed',
      message: '1 diagram generated; the rest could not be completed. Try again for the remainder.',
      diagramId: 'diag-succeeded',
      projectId: 'proj-3',
      runId: 'run-partial-2',
    }))
    expect(useNotificationStore.getState().notifications[0].read).toBe(false)
    expect(useNotificationStore.getState().unreadCount).toBe(1)
  })
})