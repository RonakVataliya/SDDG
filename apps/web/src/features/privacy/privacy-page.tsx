import { ArrowLeftIcon, ShieldCheckIcon } from 'lucide-react'
import { Link } from 'react-router'
import { useConsent } from '@/api/queries'
import { ThemeSwitch } from '@/components/appearance'
import { Wordmark } from '@/components/wordmark'
import { useAuth } from '@/features/auth/auth-context'
import { cn, formatDate } from '@/lib/utils'
import { AI_SECTION_VERSION, aiSection, POLICY_DATE, POLICY_VERSION, sections } from './policy'

export function PrivacyPage() {
  const { session } = useAuth()
  return (
    <div className="min-h-dvh">
      <header className="flex h-14 items-center gap-3 border-b border-rule bg-surface px-4 sm:px-6">
        <Link to="/" aria-label="SDDG">
          <Wordmark />
        </Link>
        <Link to="/" className="ml-4 hidden items-center gap-1.5 text-[13px] text-slate hover:text-ink sm:inline-flex">
          <ArrowLeftIcon className="size-3.5" /> Back to SDDG
        </Link>
        <ThemeSwitch className="ml-auto" />
      </header>
      <div className="mx-auto grid max-w-6xl gap-12 px-4 py-12 sm:px-6 lg:grid-cols-[220px_minmax(0,1fr)]">
        <nav aria-label="On this page" className="hidden self-start lg:sticky lg:top-8 lg:block">
          <p className="mb-2 font-mono text-[11px] tracking-[0.08em] text-slate uppercase">On this page</p>
          <ol className="space-y-1 text-[13px]">
            {sections.map((s, i) => (
              <li key={s.id}>
                <a href={`#${s.id}`} className="block rounded-md px-2.5 py-1.5 text-slate hover:bg-ink/5 hover:text-ink">
                  {String(i + 1).padStart(2, '0')} · {s.heading}
                </a>
              </li>
            ))}
          </ol>
        </nav>
        <article className="max-w-[680px]">
          <p className="font-mono text-[11px] tracking-[0.08em] text-slate uppercase">
            Version {POLICY_VERSION} · effective {formatDate(POLICY_DATE)}
          </p>
          <h1 className="mt-2 text-[38px] font-semibold">Privacy Policy</h1>
          <p className="mt-3 rounded-lg bg-amber-wash px-3 py-2 text-[13px] text-amber">Draft wording. The final text is being written by the team (task N3).</p>
          <div className="mt-8 space-y-8">
            {sections.map((s, i) => (
              <section
                key={s.id}
                id={s.id}
                className={cn('scroll-mt-6', s.id === aiSection.id && 'ticks rounded-xl border border-rule bg-field p-6')}
              >
                <h2 className="text-xl font-semibold">
                  {String(i + 1).padStart(2, '0')} · {s.heading}
                </h2>
                {s.body.map((p, j) => (
                  <p key={j} className="mt-2 text-ink-2">
                    {p}
                  </p>
                ))}
                {s.id === aiSection.id && session && <ConsentLine />}
              </section>
            ))}
          </div>
        </article>
      </div>
    </div>
  )
}

function ConsentLine() {
  const { data } = useConsent()
  if (!data?.consented || !data.consented_at) return null
  return (
    <p className="mt-4 flex items-center gap-2 text-[13px] text-success">
      <ShieldCheckIcon className="size-4" /> You agreed to this section (v{AI_SECTION_VERSION}) on {formatDate(data.consented_at)}. If it changes, we ask
      again before sending anything.
    </p>
  )
}
