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

describe('addNotification — failure', () => {
  it('words failure differently from success', () => {
    act(() => useNotificationStore.getState().addNotification(FAILURE_JOB))
    const n = useNotificationStore.getState().notifications[0]
    expect(n.kind).toBe('failure')
    expect(n.title).not.toBe('Diagram ready')
    expect(n.message).toMatch(/could not be generated/i)
  })

  it('does not set diagramId on failure', () => {
    act(() => useNotificationStore.getState().addNotification(FAILURE_JOB))
    expect(useNotificationStore.getState().notifications[0].diagramId).toBeUndefined()
  })
})

describe('hasRunId', () => {
  it('returns true after a notification for that runId is stored', () => {
    act(() => useNotificationStore.getState().addNotification(SUCCESS_JOB))
    expect(useNotificationStore.getState().hasRunId('run-1')).toBe(true)
  })

  it('returns false for an unseen runId', () => {
    expect(useNotificationStore.getState().hasRunId('run-99')).toBe(false)
  })
})

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
