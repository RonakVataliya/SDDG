/** Shared wording for the backlog, so the list, filters and dialog name things the same way. */
import type { StoryPriority, StoryStatus } from '@/api/client'

export const PRIORITY: Record<StoryPriority, string> = { must: 'Must', should: 'Should', could: 'Could', wont: 'Won’t' }

export const STATUS: Record<StoryStatus, string> = { todo: 'To do', in_progress: 'In progress', done: 'Done' }
