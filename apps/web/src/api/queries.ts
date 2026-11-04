import { keepPreviousData, useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, unwrap, type Diagram, type DiagramType, type ItemCategory, type Job, type Point, type Schemas } from './client'
import type { paths } from './schema'

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
  diagramStyle: (id: string) => ['diagrams', id, 'style'] as const,
  stylePreview: (id: string, style: Schemas['DiagramStyle'] | null) => ['diagrams', id, 'preview', style] as const,
  diagramLayout: (id: string) => ['diagrams', id, 'layout'] as const,
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

/** The single-diagram response also lists the labelled elements drawn in the diagram (used by search). */
export type DiagramDetail = Diagram & { elements?: { label: string }[] }

const fetchDiagram = (diagramId: string) =>
  unwrap(api.GET('/diagrams/{diagram_id}', { params: { path: { diagram_id: diagramId } } })) as Promise<DiagramDetail>

export function useDiagram(diagramId: string) {
  return useQuery({
    queryKey: keys.diagram(diagramId),
    queryFn: () => fetchDiagram(diagramId),
    staleTime: Infinity, // a version never changes; edits create a new one
  })
}

/** Loads every given diagram (cached, same keys as useDiagram), in the same order. */
export function useDiagramDetails(diagrams: Diagram[]) {
  return useQueries({
    queries: diagrams.map((d) => ({ queryKey: keys.diagram(d.id), queryFn: () => fetchDiagram(d.id), staleTime: Infinity })),
  })
}

export type ExportFormat = paths['/diagrams/{diagram_id}/export']['get']['parameters']['query']['format']

/**
 * FR18a: the backend renders each version from its stored source via Kroki. PNG (2x, capped at 8,000 px) is shown in
 * the viewer and downloaded as-is; SVG, PDF and the source code are fetched only when picked from the Export menu.
 */
export function fetchDiagramExport(diagramId: string, format: ExportFormat) {
  return unwrap(
    api.GET('/diagrams/{diagram_id}/export', {
      params: { path: { diagram_id: diagramId }, query: { format } },
      parseAs: 'blob',
    }),
  ) as Promise<Blob>
}

/** A project's diagrams as one ZIP (PNG, SVG, PDF and source code for each, plus README.txt): every version, or only the
 *  latest version of each diagram. */
export function fetchProjectDiagramsZip(projectId: string, versions: 'all' | 'latest') {
  return unwrap(
    api.GET('/projects/{project_id}/diagrams/export', {
      params: { path: { project_id: projectId }, query: { versions } },
      parseAs: 'blob',
    }),
  ) as Promise<Blob>
}

export function useDiagramImage(diagramId: string) {
  return useQuery({ queryKey: keys.diagramImage(diagramId), queryFn: () => fetchDiagramExport(diagramId, 'png'), staleTime: Infinity })
}

/* ---------- visual customisation (#38) ---------- */

/** The diagram's saved look. A version with no style of its own uses the nearest earlier version's, else the default. */
export function useDiagramStyle(diagramId: string) {
  return useQuery({
    queryKey: keys.diagramStyle(diagramId),
    queryFn: () => unwrap(api.GET('/diagrams/{diagram_id}/style', { params: { path: { diagram_id: diagramId } } })),
  })
}

/** Saves the look. The picture changes, and so may later versions that inherit it, so their cached images are dropped. */
export function useSaveDiagramStyle(diagramId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (style: Schemas['DiagramStyle']) =>
      unwrap(api.PUT('/diagrams/{diagram_id}/style', { params: { path: { diagram_id: diagramId } }, body: style })),
    onSuccess: (style) => {
      qc.setQueryData(keys.diagramStyle(diagramId), style)
      void qc.invalidateQueries({
        // Later versions may inherit this style; this version's style was just set above.
        predicate: ({ queryKey: [scope, id, kind] }) =>
          scope === 'diagrams' && (kind === 'png' || (kind === 'style' && id !== diagramId)),
      })
    },
  })
}

/** The diagram drawn with a style that is not saved yet. Pass null to skip; the last picture stays while the next loads. */
export function useStylePreview(diagramId: string, style: Schemas['DiagramStyle'] | null) {
  return useQuery({
    queryKey: keys.stylePreview(diagramId, style),
    queryFn: () =>
      unwrap(
        api.POST('/diagrams/{diagram_id}/preview', {
          params: { path: { diagram_id: diagramId } },
          body: style!,
          parseAs: 'blob',
        }),
      ) as Promise<Blob>,
    enabled: style !== null,
    placeholderData: keepPreviousData,
    staleTime: Infinity,
  })
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

/** #37: element positions (centres) and the lines between them, for drawing the diagram in the browser. */
export function useDiagramLayout(diagramId: string) {
  return useQuery({
    queryKey: keys.diagramLayout(diagramId),
    queryFn: () => unwrap(api.GET('/diagrams/{diagram_id}/layout', { params: { path: { diagram_id: diagramId } } })),
    staleTime: Infinity, // positions belong to a version; moving elements creates a new one
  })
}

/** Saves moved elements. Like an edit, the server returns a new version and keeps the one it came from. */
export function useSaveLayout(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ diagramId, positions }: { diagramId: string; positions: Record<string, Point> }) =>
      unwrap(
        api.POST('/diagrams/{diagram_id}/layout', {
          params: { path: { diagram_id: diagramId } },
          body: { positions },
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
