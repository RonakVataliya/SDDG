/** "Last active" as the admin Users page shows it: now / 2 min ago / 1 h ago / yesterday / 41 days ago. */
export function ago(iso: string | null, now = Date.now()): string {
  if (!iso) return 'never'
  const min = Math.max(0, Math.floor((now - new Date(iso).getTime()) / 60_000))
  if (min < 1) return 'now'
  if (min < 60) return `${min} min ago`
  if (min < 24 * 60) return `${Math.floor(min / 60)} h ago`
  const days = Math.floor(min / (24 * 60))
  return days === 1 ? 'yesterday' : `${days} days ago`
}
