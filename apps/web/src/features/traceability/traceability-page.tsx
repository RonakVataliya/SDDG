import { useWorkspace } from '@/routes/workspace-layout'
import { NamingFlag } from './naming-flag'
import { UnrepresentedList } from './unrepresented-list'

/** FR17b and FR17e in one place: what is not drawn yet, and what the diagrams disagree about naming. */
export function TraceabilityPage() {
  const { project } = useWorkspace()
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold tracking-tight">Traceability</h2>
        <p className="mt-0.5 text-sm text-slate">Which requirements the diagrams cover, and where they disagree.</p>
      </div>
      <NamingFlag projectId={project.id} />
      <UnrepresentedList projectId={project.id} />
    </div>
  )
}
