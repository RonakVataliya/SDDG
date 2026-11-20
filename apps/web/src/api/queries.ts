import { useEffect } from 'react'
import { keepPreviousData, useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  api,
  unwrap,
  type ConditionUpdate,
  type Diagram,
  type DesignKind,
  type DiagramType,
  type InvitationCreate,
  type ItemCategory,
  type Job,
  type Point,
  type ResultStatus,
  type RunMode,
  type Schemas,
  type StoryCreate,
  type StoryUpdate,
  type TestCaseCreate,
  type TestCaseUpdate,
} from './client'
import type { paths } from './schema'

export const keys = {
  projects: ['projects'] as const,
  project: (id: string) => ['projects', id] as const,
  statements: (id: string) => ['projects', id, 'statements'] as const,
  items: (id: string) => ['projects', id, 'items'] as const,
  itemPage: (id: string, category: ItemCategory | undefined, page: number) =>
    ['projects', id, 'items', category ?? 'all', page] as const,
  diagrams: (id: string) => ['projects', id, 'diagrams'] as const,
  requirementCoverage: (id: string) => ['projects', id, 'coverage'] as const,
  stories: (id: string) => ['projects', id, 'stories'] as const,
  design: (id: string) => ['projects', id, 'design'] as const,
  diagram: (id: string) => ['diagrams', id] as const,
  diagramImage: (id: string) => ['diagrams', id, 'png'] as const,
  diagramStyle: (id: string) => ['diagrams', id, 'style'] as const,
  stylePreview: (id: string, style: Schemas['DiagramStyle'] | null) => ['diagrams', id, 'preview', style] as const,
  diagramLayout: (id: string) => ['diagrams', id, 'layout'] as const,
  job: (id: string) => ['jobs', id] as const,
  consent: ['me', 'consent'] as const,
  // Tests (stream 6): everything under ['projects', id, 'tests'] is refreshed together after a test job or an edit.
  tests: (id: string) => ['projects', id, 'tests'] as const,
  testRequirements: (id: string) => ['projects', id, 'tests', 'requirements'] as const,
  testDesign: (id: string, statementId: string) => ['projects', id, 'tests', 'requirements', statementId] as const,
  testCases: (id: string) => ['projects', id, 'tests', 'cases'] as const,
  testRuns: (id: string) => ['projects', id, 'tests', 'runs'] as const,
  testRun: (id: string, runId: string) => ['projects', id, 'tests', 'runs', runId] as const,
  runSelection: (id: string) => ['projects', id, 'tests', 'selection'] as const,
  flags: (id: string) => ['projects', id, 'flags'] as const,
  documents: (id: string) => ['projects', id, 'documents'] as const,
  // Notifications bell, invitations (FR24a) and traceability (FR17)
  notifications: ['notifications'] as const, // the list and the count below it refresh together
  unread: ['notifications', 'unread'] as const,
  invitations: (id: string) => ['projects', id, 'invitations'] as const,
  naming: (id: string) => ['projects', id, 'naming'] as const,
  drift: (diagramId: string) => ['diagrams', diagramId, 'drift'] as const,
}

export const ITEMS_PAGE_SIZE = 200 // FR5a: paginate only above 200 items

const isActive = (job?: Job | null) => job?.status === 'queued' || job?.status === 'running' || job?.status === 'waiting'

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
    mutationFn: (body: Schemas['ProjectCreate']) => unwrap(api.POST('/projects', { body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.projects }),
  })
}

/** Project settings (owner only): the API answers with the updated project. */
function useProjectChange<V>(projectId: string, fn: (v: V) => Promise<Schemas['Project']>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: (project) => {
      qc.setQueryData(keys.project(projectId), project)
      void qc.invalidateQueries({ queryKey: keys.projects, exact: true })
    },
  })
}

export function useRenameProject(projectId: string) {
  return useProjectChange(projectId, (name: string) =>
    unwrap(api.PATCH('/projects/{project_id}', { params: { path: { project_id: projectId } }, body: { name } })),
  )
}

export function useSetProjectClient(projectId: string) {
  return useProjectChange(projectId, (body: Schemas['ProjectClient']) =>
    unwrap(api.PATCH('/projects/{project_id}/client', { params: { path: { project_id: projectId } }, body })),
  )
}

/** archived=true archives, false reopens. */
export function useArchiveProject(projectId: string) {
  return useProjectChange(projectId, (archived: boolean) => {
    const params = { params: { path: { project_id: projectId } } }
    return unwrap(archived ? api.POST('/projects/{project_id}/archive', params) : api.DELETE('/projects/{project_id}/archive', params))
  })
}

export function useDeleteProject(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (confirmName: string) =>
      unwrap(api.DELETE('/projects/{project_id}', { params: { path: { project_id: projectId } }, body: { confirm_name: confirmName } })),
    onSuccess: () => {
      qc.removeQueries({ queryKey: keys.project(projectId) }) // the project and everything under it
      void qc.invalidateQueries({ queryKey: keys.projects, exact: true })
    },
  })
}

/** FR20: requirement coverage over the latest diagram versions. */
export function useRequirementCoverage(projectId: string) {
  return useQuery({
    queryKey: keys.requirementCoverage(projectId),
    queryFn: () => unwrap(api.GET('/projects/{project_id}/coverage', { params: { path: { project_id: projectId } } })),
    staleTime: 0, // diagram and requirement changes don't invalidate this key; refetch whenever the page opens
  })
}

/* ---------- stories backlog (3.4) ---------- */

export function useStories(projectId: string) {
  return useQuery({
    queryKey: keys.stories(projectId),
    queryFn: () => unwrap(api.GET('/projects/{project_id}/stories', { params: { path: { project_id: projectId } } })),
  })
}

export function useCreateStory(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: StoryCreate) => unwrap(api.POST('/projects/{project_id}/stories', { params: { path: { project_id: projectId } }, body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.stories(projectId) }),
  })
}

export function useUpdateStory(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ storyId, body }: { storyId: string; body: StoryUpdate }) =>
      unwrap(api.PATCH('/projects/{project_id}/stories/{story_id}', { params: { path: { project_id: projectId, story_id: storyId } }, body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.stories(projectId) }),
  })
}

export function useDeleteStory(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (storyId: string) =>
      unwrap(api.DELETE('/projects/{project_id}/stories/{story_id}', { params: { path: { project_id: projectId, story_id: storyId } } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.stories(projectId) }),
  })
}

/* ---------- system design (Feature 4) ---------- */

const sectionPath = (projectId: string, kind: DesignKind) => ({ params: { path: { project_id: projectId, kind } } })

export function useDesign(projectId: string) {
  return useQuery({
    queryKey: keys.design(projectId),
    queryFn: () => unwrap(api.GET('/projects/{project_id}/design', projectPath(projectId))),
  })
}

/** Polls a section's draft job and refreshes the sections once it finishes, so the draft shows up. */
export function useDesignJob(projectId: string, jobId: string | null | undefined) {
  const qc = useQueryClient()
  const job = useJob(jobId)
  const done = job.data && !isActive(job.data)
  useEffect(() => {
    if (done) void qc.invalidateQueries({ queryKey: keys.design(projectId) })
  }, [done, projectId, qc])
  return job
}

export function useStartDesignDraft(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (kind: DesignKind) => unwrap(api.POST('/projects/{project_id}/design/{kind}/draft-jobs', sectionPath(projectId, kind))),
    onSuccess: (job) => {
      qc.setQueryData(keys.job(job.id), job)
      void qc.invalidateQueries({ queryKey: keys.design(projectId) })
    },
  })
}

export function useSaveDesignSection(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ kind, content }: { kind: DesignKind; content: Record<string, unknown> }) =>
      unwrap(api.PUT('/projects/{project_id}/design/{kind}', { ...sectionPath(projectId, kind), body: { content } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.design(projectId) }),
  })
}

export function useConfirmDesignSection(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (kind: DesignKind) => unwrap(api.POST('/projects/{project_id}/design/{kind}/confirm', sectionPath(projectId, kind))),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: keys.diagrams(projectId) }) // confirming the decomposition stores its package diagram
      return qc.invalidateQueries({ queryKey: keys.design(projectId) })
    },
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

/* ---------- documents (FR1b/c, FR2) ---------- */

export function useDocuments(projectId: string) {
  return useQuery({
    queryKey: keys.documents(projectId),
    queryFn: () =>
      unwrap(api.GET('/projects/{project_id}/documents', { params: { path: { project_id: projectId } } })),
    refetchInterval: (q) =>
      q.state.data?.some((d) => d.status === 'uploaded' || d.status === 'processing') ? 1500 : false,
  })
}

export function useUploadDocument(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData()
      formData.append('file', file, file.name)
      return unwrap(
        api.POST('/projects/{project_id}/documents', {
          params: { path: { project_id: projectId } },
          headers: {
            'x-filename': encodeURIComponent(file.name),
            'x-filesize': String(file.size),
          },
          body: formData as unknown as { file: unknown },
          bodySerializer: (body) => body as unknown as FormData,
        }),
      )
    },
    onSuccess: (data) => {
      void qc.invalidateQueries({ queryKey: keys.documents(projectId) })
      void qc.invalidateQueries({ queryKey: keys.project(projectId) })
      if (data?.job) qc.setQueryData(keys.job(data.job.id), data.job)
    },
  })
}

export function useDeleteDocument(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (documentId: string) =>
      unwrap(
        api.DELETE('/projects/{project_id}/documents/{document_id}', {
          params: { path: { project_id: projectId, document_id: documentId } },
        }),
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: keys.documents(projectId) })
      void qc.invalidateQueries({ queryKey: keys.project(projectId) })
    },
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

/** Requirements-first: any requirement change clears the confirmation and the extracted building blocks. */
function useStatementChange<V>(projectId: string, fn: (v: V) => Promise<unknown>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: keys.statements(projectId) })
      void qc.invalidateQueries({ queryKey: keys.flags(projectId) })
      void qc.invalidateQueries({ queryKey: keys.items(projectId) })
      void qc.invalidateQueries({ queryKey: keys.project(projectId), exact: true })
      void qc.invalidateQueries({ queryKey: keys.tests(projectId) }) // their test cases may now be Out of date
      void qc.invalidateQueries({ queryKey: keys.design(projectId) }) // design sections citing it may be Out of date
    },
  })
}

type StatementLabel = Schemas['StatementWrite']['label']

export function useAddStatement(projectId: string) {
  return useStatementChange(projectId, (body: { text: string; label?: StatementLabel }) =>
    unwrap(api.POST('/projects/{project_id}/statements', { params: { path: { project_id: projectId } }, body })),
  )
}

export function useUpdateStatement(projectId: string) {
  return useStatementChange(projectId, ({ id, ...body }: { id: string; text?: string; label?: StatementLabel }) =>
    unwrap(api.PATCH('/projects/{project_id}/statements/{statement_id}', { params: { path: { project_id: projectId, statement_id: id } }, body })),
  )
}

export function useDeleteStatement(projectId: string) {
  return useStatementChange(projectId, (id: string) =>
    unwrap(api.DELETE('/projects/{project_id}/statements/{statement_id}', { params: { path: { project_id: projectId, statement_id: id } } })),
  )
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
      // Requirements-first: an item fix keeps the confirmation; the project's updated_at still changes.
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

/* ---------- requirement flags (issue #34): advisory, never block anything ---------- */

export function useFlags(projectId: string) {
  return useQuery({
    queryKey: keys.flags(projectId),
    queryFn: () => unwrap(api.GET('/projects/{project_id}/flags', { params: { path: { project_id: projectId } } })),
  })
}

export function useFlagSummary(projectId: string) {
  return useQuery({
    queryKey: [...keys.flags(projectId), 'summary'],
    queryFn: () => unwrap(api.GET('/projects/{project_id}/flags/summary', { params: { path: { project_id: projectId } } })),
  })
}

type FlagAction = { flagId: string } & ({ kind: 'answer'; answer: string } | { kind: 'resolve' | 'reopen' | 'apply-fix' })

export function useFlagAction(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (a: FlagAction) => {
      const params = { path: { project_id: projectId, flag_id: a.flagId } }
      if (a.kind === 'answer') return unwrap(api.POST('/projects/{project_id}/flags/{flag_id}/answer', { params, body: { answer: a.answer } }))
      if (a.kind === 'resolve') return unwrap(api.POST('/projects/{project_id}/flags/{flag_id}/resolve', { params }))
      if (a.kind === 'reopen') return unwrap(api.POST('/projects/{project_id}/flags/{flag_id}/reopen', { params }))
      return unwrap(api.POST('/projects/{project_id}/flags/{flag_id}/apply-fix', { params }))
    },
    onSuccess: (_flag, a) => {
      void qc.invalidateQueries({ queryKey: keys.flags(projectId) })
      // Apply fix rewrites the requirement (and can close the related conflict flag): refetch statements too.
      if (a.kind === 'apply-fix') {
        void qc.invalidateQueries({ queryKey: keys.statements(projectId) })
        void qc.invalidateQueries({ queryKey: keys.items(projectId) })
        void qc.invalidateQueries({ queryKey: keys.project(projectId), exact: true })
      }
    },
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

/** The single-diagram response also lists the elements drawn in the diagram and the requirements behind them. */

const fetchDiagram = (diagramId: string) =>
  unwrap(api.GET('/diagrams/{diagram_id}', { params: { path: { diagram_id: diagramId } } }))

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

/** The combined project report: one self-contained, print-styled HTML page (no scripts allowed by its own CSP). */
export function fetchProjectReport(projectId: string) {
  return unwrap(
    api.GET('/projects/{project_id}/report.html', { params: { path: { project_id: projectId } }, parseAs: 'blob' }),
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

/* ---------- tests (Sprint 3, stream 6) ---------- */

const projectPath = (projectId: string) => ({ params: { path: { project_id: projectId } } })

/** Every requirement with its test-design summary. Polls while a test job is queued or running. */
export function useTestRequirements(projectId: string) {
  return useQuery({
    queryKey: keys.testRequirements(projectId),
    queryFn: () => unwrap(api.GET('/projects/{project_id}/tests/requirements', projectPath(projectId))),
    refetchInterval: (q) => (isActive(q.state.data?.active_job) ? 2000 : false),
  })
}

export function useTestDesign(projectId: string, statementId: string | null) {
  return useQuery({
    queryKey: keys.testDesign(projectId, statementId ?? 'none'),
    queryFn: () =>
      unwrap(
        api.GET('/projects/{project_id}/tests/requirements/{statement_id}', {
          params: { path: { project_id: projectId, statement_id: statementId! } },
        }),
      ),
    enabled: !!statementId,
  })
}

/** Polls a test job and refreshes every Tests query once it finishes, so the new design or steps show up. */
export function useTestJob(projectId: string, jobId: string | null | undefined) {
  const qc = useQueryClient()
  const job = useJob(jobId)
  const done = job.data && !isActive(job.data)
  useEffect(() => {
    if (done) void qc.invalidateQueries({ queryKey: keys.tests(projectId) })
  }, [done, projectId, qc])
  return job
}

/** AI request 1 for the chosen requirements (the server sends them 5 at a time). */
export function useStartCriteria(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (statementIds: string[]) =>
      unwrap(api.POST('/projects/{project_id}/tests/criteria-jobs', { ...projectPath(projectId), body: { statement_ids: statementIds } })),
    onSuccess: (job) => {
      qc.setQueryData(keys.job(job.id), job)
      void qc.invalidateQueries({ queryKey: keys.testRequirements(projectId) })
    },
  })
}

/** Editing a condition recomputes classes, boundaries and drafts in code (no AI) and returns the new design. */
export function useUpdateCondition(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ conditionId, body }: { conditionId: string; body: ConditionUpdate }) =>
      unwrap(
        api.PATCH('/projects/{project_id}/tests/conditions/{condition_id}', {
          params: { path: { project_id: projectId, condition_id: conditionId } },
          body,
        }),
      ),
    onSuccess: (design) => {
      qc.setQueryData(keys.testDesign(projectId, design.statement_id), design)
      void qc.invalidateQueries({ queryKey: keys.testRequirements(projectId) })
      void qc.invalidateQueries({ queryKey: keys.testCases(projectId) })
    },
  })
}

export function useUpdateCriterion(projectId: string, statementId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ criterionId, given, when, then }: { criterionId: string; given: string; when: string; then: string }) =>
      unwrap(
        api.PATCH('/projects/{project_id}/tests/criteria/{criterion_id}', {
          params: { path: { project_id: projectId, criterion_id: criterionId } },
          body: { given, when, then },
        }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.testDesign(projectId, statementId) }),
  })
}

/** AI request 2: steps for kept drafts only (all of them when caseIds is omitted). */
export function useStartSteps(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (caseIds?: string[]) =>
      unwrap(api.POST('/projects/{project_id}/tests/step-jobs', { ...projectPath(projectId), body: { case_ids: caseIds } })),
    onSuccess: (job) => {
      qc.setQueryData(keys.job(job.id), job)
      void qc.invalidateQueries({ queryKey: keys.testRequirements(projectId) })
    },
  })
}

export function useTestCases(projectId: string) {
  return useQuery({
    queryKey: keys.testCases(projectId),
    queryFn: () => unwrap(api.GET('/projects/{project_id}/tests/cases', projectPath(projectId))),
  })
}

export function useCreateCase(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: TestCaseCreate) => unwrap(api.POST('/projects/{project_id}/tests/cases', { ...projectPath(projectId), body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.tests(projectId) }),
  })
}

/** Keep/discard a draft or edit a case's text. */
export function useUpdateCase(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ caseId, body }: { caseId: string; body: TestCaseUpdate }) =>
      unwrap(
        api.PATCH('/projects/{project_id}/tests/cases/{case_id}', {
          params: { path: { project_id: projectId, case_id: caseId } },
          body,
        }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.tests(projectId) }),
  })
}

export function useTestRuns(projectId: string) {
  return useQuery({
    queryKey: keys.testRuns(projectId),
    queryFn: () => unwrap(api.GET('/projects/{project_id}/tests/runs', projectPath(projectId))),
  })
}

export function useTestRun(projectId: string, runId: string | null) {
  return useQuery({
    queryKey: keys.testRun(projectId, runId ?? 'none'),
    queryFn: () =>
      unwrap(
        api.GET('/projects/{project_id}/tests/runs/{run_id}', { params: { path: { project_id: projectId, run_id: runId! } } }),
      ),
    enabled: !!runId,
  })
}

/** What each run mode would pick (shown in the Start run dialog). */
export function useRunSelection(projectId: string, enabled = true) {
  return useQuery({
    queryKey: keys.runSelection(projectId),
    queryFn: () => unwrap(api.GET('/projects/{project_id}/tests/runs/selection', projectPath(projectId))),
    enabled,
    // The picks depend on the latest results and requirement texts, so the dialog always asks again when it opens.
    refetchOnMount: 'always',
  })
}

export function useStartRun(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { name: string; mode: RunMode; case_ids?: string[] }) =>
      unwrap(api.POST('/projects/{project_id}/tests/runs', { ...projectPath(projectId), body })),
    onSuccess: (run) => {
      qc.setQueryData(keys.testRun(projectId, run.id), run)
      void qc.invalidateQueries({ queryKey: keys.testRuns(projectId) })
    },
  })
}

export function useMarkResult(projectId: string, runId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ caseId, status, note }: { caseId: string; status: ResultStatus; note?: string | null }) =>
      unwrap(
        api.PUT('/projects/{project_id}/tests/runs/{run_id}/results/{case_id}', {
          params: { path: { project_id: projectId, run_id: runId, case_id: caseId } },
          body: { status, note: note ?? null },
        }),
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: keys.testRun(projectId, runId) })
      void qc.invalidateQueries({ queryKey: keys.testRuns(projectId), exact: true })
    },
  })
}

export function useFinishRun(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (runId: string) =>
      unwrap(
        api.POST('/projects/{project_id}/tests/runs/{run_id}/finish', { params: { path: { project_id: projectId, run_id: runId } } }),
      ),
    onSuccess: (run) => {
      qc.setQueryData(keys.testRun(projectId, run.id), run)
      void qc.invalidateQueries({ queryKey: keys.tests(projectId) })
    },
  })
}

/** Answers a flag's question; for an untestable flag the answer fills in the suggested requirement. */
export function useAnswerFlag(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ flagId, answer }: { flagId: string; answer: string }) =>
      unwrap(
        api.POST('/projects/{project_id}/flags/{flag_id}/answer', {
          params: { path: { project_id: projectId, flag_id: flagId } },
          body: { answer },
        }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.tests(projectId) }),
  })
}

/* ---------- notifications bell (FR24a, FR32) ---------- */

export const BELL_POLL_MS = 30_000

/** The red number on the bell. Polled; the list is only fetched while the dropdown is open. */
export function useUnreadCount() {
  return useQuery({
    queryKey: keys.unread,
    queryFn: () => unwrap(api.GET('/notifications/unread-count')),
    refetchInterval: BELL_POLL_MS,
    staleTime: 0,
  })
}

export function useNotifications(enabled: boolean) {
  return useQuery({
    queryKey: keys.notifications,
    queryFn: () => unwrap(api.GET('/notifications')),
    enabled,
    staleTime: 0,
  })
}

export function useMarkRead() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(api.POST('/notifications/{notification_id}/read', { params: { path: { notification_id: id } } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.notifications }),
  })
}

export function useMarkAllRead() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => unwrap(api.POST('/notifications/read-all')),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.notifications }),
  })
}

/* ---------- invitations (FR24a) ---------- */

function useJoined() {
  const qc = useQueryClient()
  return () => {
    void qc.invalidateQueries({ queryKey: keys.notifications })
    void qc.invalidateQueries({ queryKey: keys.projects }) // the project is in the list straight away
  }
}

/** Accept from the bell. Returns the project, with the invited role. */
export function useAcceptInvitation() {
  const joined = useJoined()
  return useMutation({
    mutationFn: (invitationId: string) =>
      unwrap(api.POST('/invitations/{invitation_id}/accept', { params: { path: { invitation_id: invitationId } } })),
    onSuccess: joined,
  })
}

/** Accept through the invitation's link (the fallback when there is no email service). */
export function useAcceptInvitationLink() {
  const joined = useJoined()
  return useMutation({
    mutationFn: (token: string) => unwrap(api.POST('/invitations/accept', { body: { token } })),
    onSuccess: joined,
  })
}

export function useInvitations(projectId: string) {
  return useQuery({
    queryKey: keys.invitations(projectId),
    queryFn: () => unwrap(api.GET('/projects/{project_id}/invitations', { params: { path: { project_id: projectId } } })),
  })
}

export function useInvite(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: InvitationCreate) =>
      unwrap(api.POST('/projects/{project_id}/invitations', { params: { path: { project_id: projectId } }, body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.invitations(projectId) }),
  })
}

export function useRevokeInvitation(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (invitationId: string) =>
      unwrap(
        api.DELETE('/projects/{project_id}/invitations/{invitation_id}', {
          params: { path: { project_id: projectId, invitation_id: invitationId } },
        }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.invitations(projectId) }),
  })
}

/* ---------- traceability (FR17) ---------- */


/** FR17d: how this version drifted from the requirements. Depends on the requirements too, so never cached for long. */
export function useDrift(diagramId: string) {
  return useQuery({
    queryKey: keys.drift(diagramId),
    queryFn: () => unwrap(api.GET('/diagrams/{diagram_id}/drift', { params: { path: { diagram_id: diagramId } } })),
    staleTime: 0,
    refetchOnMount: 'always',
  })
}

/** FR17e: model items the diagrams name differently. */
export function useNamingIssues(projectId: string) {
  return useQuery({
    queryKey: keys.naming(projectId),
    queryFn: () =>
      unwrap(api.GET('/projects/{project_id}/traceability/naming', { params: { path: { project_id: projectId } } })),
    staleTime: 0,
    refetchOnMount: 'always',
  })
}

/** "Apply this name to all diagrams": new versions of every diagram that named the item differently. */
export function useApplyName(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { model_item_id: string; name: string }) =>
      unwrap(
        api.POST('/projects/{project_id}/traceability/naming/apply', {
          params: { path: { project_id: projectId } },
          body,
        }),
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: keys.naming(projectId) })
      void qc.invalidateQueries({ queryKey: keys.diagrams(projectId) })
      void qc.invalidateQueries({ queryKey: keys.requirementCoverage(projectId) })
      void qc.invalidateQueries({ queryKey: keys.project(projectId), exact: true })
    },
  })
}
