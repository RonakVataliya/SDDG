import { useEffect } from 'react'
import { useQueries } from '@tanstack/react-query'
import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { api, unwrap } from '@/api/client'
import { keys } from '@/api/queries'
import { useNotificationStore } from './store'

export interface PendingJob {
  runId: string
  projectId: string
  projectName: string
}

interface JobStoreState {
  pending: PendingJob[]
  register: (job: PendingJob) => void
  remove: (runId: string) => void
}

export const useJobStore = create<JobStoreState>()(
  persist(
    (set) => ({
      pending: [],
      register(job) {
        set(state => ({
          pending: state.pending.find(j => j.runId === job.runId)
            ? state.pending
            : [...state.pending, job],
        }))
      },
      remove(runId) {
        set(state => ({ pending: state.pending.filter(j => j.runId !== runId) }))
      },
    }),
    { name: 'sddg-pending-jobs' },
  ),
)

const isActive = (status: string) => status === 'queued' || status === 'running'

export function useJobWatcher() {
  const pending = useJobStore(s => s.pending)
  const remove = useJobStore(s => s.remove)
  const { addNotification, hasRunId } = useNotificationStore()

  const results = useQueries({
    queries: pending.map(job => ({
      queryKey: keys.job(job.runId),
      queryFn: () =>
        unwrap(api.GET('/jobs/{job_id}', { params: { path: { job_id: job.runId } } })),
      refetchInterval: (q: any) =>
        q.state.data && !isActive(q.state.data.status) ? false : 1500,
      enabled: !hasRunId(job.runId),
    })),
  })

  useEffect(() => {
    pending.forEach((job, i) => {
      const data = results[i]?.data
      if (!data || isActive(data.status)) return
      if (hasRunId(job.runId)) return

      remove(job.runId)
      addNotification({
        kind: data.status === 'succeeded' ? 'success' : 'failure',
        title: data.status === 'succeeded' ? 'Diagram ready' : 'Generation failed',
        message:
          data.status === 'succeeded'
            ? `"${job.projectName}" finished successfully.`
            : `"${job.projectName}" could not be generated. Try again.`,
        diagramId: data.diagram_ids?.[0],
        projectId: job.projectId,
        runId: job.runId,
      })
    })
  }, [results, pending, addNotification, hasRunId, remove])
}