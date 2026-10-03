import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** Pasted text counts as 1 page per 3,000 characters, rounded up (FR3 page definition, A21). */
export const CHARS_PER_PAGE = 3000
export const MAX_PROJECT_PAGES = 100

export function pastedPageCount(text: string) {
  return text.length === 0 ? 0 : Math.ceil(text.length / CHARS_PER_PAGE)
}

export function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}

export function formatRelative(iso: string, now = Date.now()) {
  const secs = Math.round((now - new Date(iso).getTime()) / 1000)
  if (secs < 60) return 'just now'
  const mins = Math.round(secs / 60)
  if (mins < 60) return `${mins} min ago`
  const hours = Math.round(mins / 60)
  if (hours < 24) return `${hours} h ago`
  return formatDate(iso)
}

export function plural(n: number, one: string, many = `${one}s`) {
  return `${n} ${n === 1 ? one : many}`
}
