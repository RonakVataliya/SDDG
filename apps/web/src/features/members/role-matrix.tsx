/** "What each role can do" (FR24c): the same rules require_role enforces on the server, in plain words. */
const ROWS: { label: string; viewer: boolean; editor: boolean; owner: boolean }[] = [
  { label: 'Read requirements and diagrams', viewer: true, editor: true, owner: true },
  { label: 'Comment and export', viewer: true, editor: true, owner: true },
  { label: 'Edit requirements and diagrams', viewer: false, editor: true, owner: true },
  { label: 'Generate with AI', viewer: false, editor: true, owner: true },
  { label: 'Invite people and change roles', viewer: false, editor: false, owner: true },
  { label: 'Rename, archive or delete the project', viewer: false, editor: false, owner: true },
]

export function RoleMatrix() {
  return (
    <aside aria-labelledby="role-matrix-title" className="self-start rounded-lg border border-rule bg-paper p-4">
      <h3 id="role-matrix-title" className="text-[13.5px] font-semibold">
        What each role can do
      </h3>
      <table className="mt-3 w-full text-[12.5px]">
        <thead className="text-slate">
          <tr>
            <th className="pb-1.5 text-left font-medium">
              <span className="sr-only">Action</span>
            </th>
            <th className="pb-1.5 font-medium">Viewer</th>
            <th className="pb-1.5 font-medium">Editor</th>
            <th className="pb-1.5 font-medium">Owner</th>
          </tr>
        </thead>
        <tbody>
          {ROWS.map((r) => (
            <tr key={r.label} className="border-t border-rule">
              <th scope="row" className="py-1.5 pr-2 text-left font-normal">
                {r.label}
              </th>
              {([r.viewer, r.editor, r.owner] as const).map((yes, i) => (
                <td key={i} className="py-1.5 text-center">
                  {yes ? <span aria-label="Yes">✓</span> : <span aria-label="No" className="text-slate">–</span>}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </aside>
  )
}
