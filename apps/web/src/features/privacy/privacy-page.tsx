import { Link } from 'react-router'
import { formatDate } from '@/lib/utils'
import { POLICY_DATE, POLICY_VERSION, sections } from './policy'

export function PrivacyPage() {
  return (
    <div className="mx-auto max-w-2xl px-4 py-12 sm:px-6">
      <Link to="/" className="text-sm text-teal hover:underline">
        Back to SDDG
      </Link>
      <h1 className="mt-6 text-3xl font-semibold tracking-tight">Privacy Policy</h1>
      <p className="mt-2 text-sm text-slate">
        Version {POLICY_VERSION}, effective {formatDate(POLICY_DATE)}
      </p>
      <p className="mt-4 rounded-md border border-amber/30 bg-amber-wash px-3 py-2 text-sm text-amber">
        Draft wording. The final text is being written by the team (task N3).
      </p>
      <div className="mt-8 space-y-8">
        {sections.map((s) => (
          <section key={s.id} id={s.id} className="scroll-mt-6">
            <h2 className="text-lg font-semibold">{s.heading}</h2>
            {s.body.map((p, i) => (
              <p key={i} className="mt-2 max-w-[68ch] text-ink/85">
                {p}
              </p>
            ))}
          </section>
        ))}
      </div>
    </div>
  )
}
