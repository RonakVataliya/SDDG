import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, unwrap, type DiagramType, type ItemCategory, type Job } from './client'

export const keys = {
  projects: ['projects'] as const,
  project: (id: string) => ['projects', id] as const,
  statements: (id: string) => ['projects', id, 'statements'] as const,
  items: (id: string) => ['projects', id, 'items'] as const,
  itemPage: (id: string, category: ItemCategory | undefined, page: number) =>
    ['projects', id, 'items', category ?? 'all', page] as const,
  diagrams: (id: string) => ['projects', id, 'diagrams'] as const,
  diagram: (id: string) => ['diagrams', id] as const,
  diagramImage: (id: string) => ['diagrams', id, 'png'] as const,
  job: (id: string) => ['jobs', id] as const,
  consent: ['me', 'consent'] as const,
}

export const ITEMS_PAGE_SIZE = 200 // FR5a: paginate only above 200 items

const isActive = (job?: Job | null) => job?.status === 'queued' || job?.status === 'running'

/* ---------- projects ---------- */

export function useProjects() {
  return useQuery({ queryKey: keys.projects, queryFn: () => unwrap(api.GET('/projects')) })
}

export function useProject(projectId: string) {
  return useQuery({
    queryKey: keys.project(projectId),
    queryFn: () => unwrap(api.GET('/projects/{project_id}', { params: { path: { project_id: projectId } } })),
    // While extraction runs, the project summary is the thing that changes; keep it fresh.
    refetchInterval: (q) => (isActive(q.state.data?.extraction) ? 2000 : false),
  })
}

export function useCreateProject() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (name: string) => unwrap(api.POST('/projects', { body: { name } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.projects }),
  })
}

/* ---------- consent (NFR5d) ---------- */

export function useConsent() {
  return useQuery({ queryKey: keys.consent, queryFn: () => unwrap(api.GET('/me/consent')) })
}

export function useGiveConsent() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (policyVersion: string) =>
      unwrap(api.POST('/me/consent', { body: { policy_version: policyVersion } })),
    onSuccess: (consent) => qc.setQueryData(keys.consent, consent),
  })
}

/* ---------- input + extraction ---------- */

export function useSubmitInput(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (text: string) =>
      unwrap(api.POST('/projects/{project_id}/inputs', { params: { path: { project_id: projectId } }, body: { text } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.project(projectId) }),
  })
}

/** FR10g: poll a job until it finishes. */
export function useJob(jobId: string | null | undefined) {
  return useQuery({
    queryKey: keys.job(jobId ?? 'none'),
    queryFn: () => unwrap(api.GET('/jobs/{job_id}', { params: { path: { job_id: jobId! } } })),
    enabled: !!jobId,
    refetchInterval: (q) => (q.state.data && !isActive(q.state.data) ? false : 1500),
  })
}

/* ---------- review (FR5a/b/e) ---------- */

export function useStatements(projectId: string) {
  return useQuery({
    queryKey: keys.statements(projectId),
    queryFn: () =>
      unwrap(api.GET('/projects/{project_id}/statements', { params: { path: { project_id: projectId } } })),
  })
}

export function useItems(projectId: string, category: ItemCategory | undefined, page: number) {
  return useQuery({
    queryKey: keys.itemPage(projectId, category, page),
    queryFn: () =>
      unwrap(
        api.GET('/projects/{project_id}/items', {
          params: { path: { project_id: projectId }, query: { category, page, page_size: ITEMS_PAGE_SIZE } },
        }),
      ),
    placeholderData: keepPreviousData,
  })
}

export function useUpdateItem(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ itemId, name, description }: { itemId: string; name: string; description: string | null }) =>
      unwrap(
        api.PATCH('/projects/{project_id}/items/{item_id}', {
          params: { path: { project_id: projectId, item_id: itemId } },
          body: { name, description },
        }),
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: keys.items(projectId) })
      // FR5e: any change clears the confirmation, so the project summary is stale.
      void qc.invalidateQueries({ queryKey: keys.project(projectId), exact: true })
    },
  })
}

export function useConfirmExtraction(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () =>
      unwrap(api.POST('/projects/{project_id}/confirmation', { params: { path: { project_id: projectId } } })),
    onSuccess: (project) => qc.setQueryData(keys.project(projectId), project),
  })
}

/* ---------- generation + diagrams ---------- */

export function useStartGeneration(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (diagramTypes: DiagramType[]) =>
      unwrap(
        api.POST('/projects/{project_id}/generations', {
          params: { path: { project_id: projectId } },
          body: { diagram_types: diagramTypes },
        }),
      ),
    onSuccess: (job) => qc.setQueryData(keys.job(job.id), job),
  })
}

export function useDiagrams(projectId: string) {
  return useQuery({
    queryKey: keys.diagrams(projectId),
    queryFn: () =>
      unwrap(api.GET('/projects/{project_id}/diagrams', { params: { path: { project_id: projectId } } })),
  })
}

export function useDiagram(diagramId: string) {
  return useQuery({
    queryKey: keys.diagram(diagramId),
    queryFn: () => unwrap(api.GET('/diagrams/{diagram_id}', { params: { path: { diagram_id: diagramId } } })),
    staleTime: Infinity, // a version never changes; edits create a new one
  })
}

/** FR18a: the backend renders each version to a still PNG (2x, capped at 8,000 px). Shown in the viewer and downloaded as-is. */
function fetchDiagramPng(diagramId: string) {
  return unwrap(
    api.GET('/diagrams/{diagram_id}/export', {
      params: { path: { diagram_id: diagramId }, query: { format: 'png' } },
      parseAs: 'blob',
    }),
  ) as Promise<Blob>
}

export function useDiagramImage(diagramId: string) {
  return useQuery({ queryKey: keys.diagramImage(diagramId), queryFn: () => fetchDiagramPng(diagramId), staleTime: Infinity })
}

/** Plain-language edit ("rename X to Y"). The server returns a new version; the one it came from is kept. */
export function useReviseDiagram(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ diagramId, instruction }: { diagramId: string; instruction: string }) =>
      unwrap(
        api.POST('/diagrams/{diagram_id}/revisions', {
          params: { path: { diagram_id: diagramId } },
          body: { instruction },
        }),
      ),
    onSuccess: (diagram) => {
      qc.setQueryData(keys.diagram(diagram.id), diagram)
      void qc.invalidateQueries({ queryKey: keys.diagrams(projectId) })
      void qc.invalidateQueries({ queryKey: keys.project(projectId), exact: true })
    },
  })
}

export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = Object.assign(document.createElement('a'), { href: url, download: filename })
  a.click()
  URL.revokeObjectURL(url)
}
