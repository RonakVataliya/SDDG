import type { Role } from '@/api/client'

export const roleLabel: Record<Role, string> = { owner: 'Owner', editor: 'Editor', viewer: 'Viewer' }

/** "an Editor", "a Viewer", "an Owner". */
export const withArticle = (role: Role) => `${role === 'viewer' ? 'a' : 'an'} ${roleLabel[role]}`

/** A name to show for someone we only know by email: ronak.vataliya@dau.ac.in becomes "Ronak Vataliya". */
export function displayName(email: string | null | undefined) {
  const words = (email ?? '').split('@')[0].split(/[._+-]+/).filter(Boolean)
  if (!words.length) return email || 'Someone'
  return words.map((w) => w[0].toUpperCase() + w.slice(1)).join(' ')
}
