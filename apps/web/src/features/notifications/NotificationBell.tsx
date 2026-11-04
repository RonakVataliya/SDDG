import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'
import { Bell } from 'lucide-react'
import { useNotificationStore, type AppNotification } from './store'

function timeAgo(ts: number): string {
  const secs = Math.floor((Date.now() - ts) / 1000)
  if (secs < 60) return 'just now'
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`
  return `${Math.floor(secs / 86400)}d ago`
}

function NotificationItem({ n, onRead }: { n: AppNotification; onRead: (id: string) => void }) {
  const isSuccess = n.kind === 'success'
  return (
    <li className={`flex gap-2 px-4 py-3 border-b border-gray-100 last:border-0 ${!n.read ? 'bg-blue-50' : ''}`}>
      <span className={`mt-1 shrink-0 w-2 h-2 rounded-full ${isSuccess ? 'bg-green-500' : 'bg-red-500'}`} aria-hidden="true" />
      <div className="flex-1 min-w-0">
        <p className={`text-sm font-medium leading-snug ${isSuccess ? 'text-green-800' : 'text-red-700'}`}>{n.title}</p>
        <p className="text-xs text-gray-600 mt-0.5 break-words">{n.message}</p>
        <div className="flex items-center gap-3 mt-1">
          <span className="text-[11px] text-gray-400">{timeAgo(n.createdAt)}</span>
          {isSuccess && n.diagramId ? (
            <Link to={`/projects/${n.projectId}/diagrams/${n.diagramId}`} className="text-[11px] text-blue-600 hover:underline" onClick={() => onRead(n.id)}>
              View diagram →
            </Link>
          ) : !isSuccess ? (
            <Link to={`/projects/${n.projectId}/generate`} className="text-[11px] text-blue-600 hover:underline" onClick={() => onRead(n.id)}>
              Retry →
            </Link>
          ) : null}
        </div>
      </div>
      {!n.read && (
        <button className="shrink-0 self-start text-[11px] text-gray-400 hover:text-gray-700 px-1 pt-0.5" onClick={() => onRead(n.id)} aria-label="Mark as read">
          ✓
        </button>
      )}
    </li>
  )
}

export function NotificationBell() {
  const [open, setOpen] = useState(false)
  const [liveText, setLiveText] = useState('')
  const panelRef = useRef<HTMLDivElement>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const prevCountRef = useRef(0)
  const { notifications, unreadCount, markRead, markAllRead } = useNotificationStore()

  useEffect(() => {
    if (!open) return
    function handle(e: MouseEvent) {
      if (panelRef.current?.contains(e.target as Node) === false && buttonRef.current?.contains(e.target as Node) === false) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handle)
    return () => document.removeEventListener('mousedown', handle)
  }, [open])

  useEffect(() => {
    function handle(e: KeyboardEvent) { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('keydown', handle)
    return () => document.removeEventListener('keydown', handle)
  }, [])

  useEffect(() => {
    if (unreadCount > prevCountRef.current && notifications[0]) {
      const n = notifications[0]
      setLiveText(`New notification: ${n.title}. ${n.message}`)
    }
    prevCountRef.current = unreadCount
  }, [unreadCount, notifications])

  return (
    <div className="relative">
      <div role="status" aria-live="polite" aria-atomic="true" className="sr-only">{liveText}</div>
      <button
        ref={buttonRef}
        onClick={() => setOpen(v => !v)}
        className="relative p-2 rounded-full hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
        aria-label={`Notifications${unreadCount ? `, ${unreadCount} unread` : ''}`}
        aria-haspopup="dialog"
        aria-expanded={open}
      >
        <Bell className="w-5 h-5 text-gray-600" aria-hidden="true" />
        {unreadCount > 0 && (
          <span className="absolute top-0.5 right-0.5 flex items-center justify-center w-4 h-4 text-[10px] font-bold text-white bg-red-500 rounded-full" aria-hidden="true">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>
      {open && (
        <div ref={panelRef} role="dialog" aria-label="Notifications" className="absolute right-0 mt-2 w-80 bg-white rounded-xl shadow-lg border border-gray-200 z-50 flex flex-col max-h-[480px]">
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 shrink-0">
            <h2 className="text-sm font-semibold text-gray-900">Notifications</h2>
            {unreadCount > 0 && <button onClick={markAllRead} className="text-xs text-blue-600 hover:underline">Mark all read</button>}
          </div>
          {notifications.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-gray-400 select-none">
              <Bell className="w-8 h-8 mb-2 opacity-40" aria-hidden="true" />
              <p className="text-sm">No notifications yet</p>
            </div>
          ) : (
            <ul className="overflow-y-auto flex-1" role="list" aria-label="Notification list">
              {notifications.map(n => <NotificationItem key={n.id} n={n} onRead={markRead} />)}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}