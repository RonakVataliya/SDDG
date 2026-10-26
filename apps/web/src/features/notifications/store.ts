import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type NotifKind = 'success' | 'failure'

export interface AppNotification {
  id: string
  kind: NotifKind
  title: string
  message: string
  diagramId?: string
  projectId: string
  runId: string
  read: boolean
  createdAt: number
}

interface NotificationState {
  notifications: AppNotification[]
  unreadCount: number
  addNotification: (n: Omit<AppNotification, 'id' | 'read' | 'createdAt'>) => void
  markRead: (id: string) => void
  markAllRead: () => void
  hasRunId: (runId: string) => boolean
}

export const useNotificationStore = create<NotificationState>()(
  persist(
    (set, get) => ({
      notifications: [],
      unreadCount: 0,

      addNotification(payload) {
        const notification: AppNotification = {
          ...payload,
          id: crypto.randomUUID(),
          read: false,
          createdAt: Date.now(),
        }
        set(state => ({
          notifications: [notification, ...state.notifications],
          unreadCount: state.unreadCount + 1,
        }))
      },

      markRead(id) {
        set(state => {
          const updated = state.notifications.map(n =>
            n.id === id && !n.read ? { ...n, read: true } : n,
          )
          return {
            notifications: updated,
            unreadCount: updated.filter(n => !n.read).length,
          }
        })
      },

      markAllRead() {
        set(state => ({
          notifications: state.notifications.map(n => ({ ...n, read: true })),
          unreadCount: 0,
        }))
      },

      hasRunId(runId) {
        return get().notifications.some(n => n.runId === runId)
      },
    }),
    { name: 'sddg-notifications' },
  ),
)