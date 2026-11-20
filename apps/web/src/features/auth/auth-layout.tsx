import { FlagIcon, LayersIcon, LinkIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { ThemeSwitch } from '@/components/appearance'
import { LogoMark } from '@/components/wordmark'
import { cn } from '@/lib/utils'
import { BACKGROUNDS, pickBackground, type BackgroundId } from './backgrounds'

// Picked once per page load, so moving between log in / sign up / verify keeps the same background.
// ?bg=<id> pins one (handy for demos and screenshots).
const pinned = typeof location !== 'undefined' ? new URLSearchParams(location.search).get('bg') : null
const Background = BACKGROUNDS[pinned && pinned in BACKGROUNDS ? (pinned as BackgroundId) : pickBackground()]

const POINTS = [
  { Icon: FlagIcon, text: 'Flags vague or conflicting requirements' },
  { Icon: LayersIcon, text: '7 diagram types from one set of requirements' },
  { Icon: LinkIcon, text: 'Every shape traces back to its requirement' },
]
const delay = (ms: number) => ({ animationDelay: `${ms}ms` })

/**
 * Shared shell for log in, sign up and verify: a random diagram background, a short message beside the card
 * (wide screens only) and a centred card. Things appear one after another: logo, message, card, fields, points.
 */
export function AuthLayout({
  title,
  subtitle,
  tab,
  children,
}: {
  title: string
  subtitle?: ReactNode
  tab?: 'login' | 'signup'
  children: ReactNode
}) {
  return (
    <div className="relative flex min-h-dvh flex-col overflow-hidden bg-paper">
      <div className="pointer-events-none absolute inset-0">
        <Background />
        {/* Keeps the middle calm and readable whatever the background draws. */}
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_42%_52%_at_50%_50%,var(--paper)_30%,transparent_100%)]" />
      </div>

      <main className="relative flex flex-1 items-center justify-center px-4 py-10">
        <div className="grid w-full max-w-[1040px] items-center gap-16 lg:grid-cols-[minmax(0,1fr)_420px]">
          <section className="-m-8 hidden rounded-3xl bg-paper/75 p-8 backdrop-blur-[6px] lg:block" aria-label="About SDDG">
            <span className="rise inline-flex items-center gap-2 rounded-full border border-rule bg-surface px-3 py-1 text-[12px] font-medium" style={delay(150)}>
              <span className="size-1.5 rounded-full bg-accent" /> New: requirement flags
            </span>
            <h2 className="rise mt-5 text-[44px] leading-[1.05] font-semibold text-balance" style={delay(250)}>
              Requirements in.
              <br />
              <span className="text-accent">Design diagrams</span> out.
            </h2>
            <p className="rise mt-4 max-w-md text-[16px] text-ink-2" style={delay(350)}>
              Paste your SRS or user stories, check what SDDG understood, and get diagrams you can trust and edit.
            </p>
            <ul className="mt-7 space-y-3">
              {POINTS.map(({ Icon, text }, i) => (
                <li key={text} className="rise flex items-center gap-3 text-[14px]" style={delay(1000 + i * 120)}>
                  <span className="grid size-8 place-items-center rounded-[9px] border border-rule bg-surface text-accent">
                    <Icon className="size-4" />
                  </span>
                  {text}
                </li>
              ))}
            </ul>
          </section>

          <div className="mx-auto w-full max-w-[420px]">
            <div className="rise flex justify-center" style={delay(0)}>
              <LogoMark className="size-11" />
            </div>
            <div className="rise mt-5 rounded-[22px] border border-rule bg-surface/90 px-8 pt-7 pb-8 shadow-[var(--shadow)] backdrop-blur-md" style={delay(400)}>
              <h1 className="text-center text-[28px] leading-tight font-semibold">{title}</h1>
              {subtitle && <p className="mt-1.5 text-center text-[13.5px] text-slate">{subtitle}</p>}
              {tab && (
                <nav aria-label="Log in or sign up" className="mt-6 flex rounded-[9px] bg-rule p-[3px] text-[13px] font-medium">
                  {(['login', 'signup'] as const).map((t) => (
                    <Link
                      key={t}
                      to={`/${t}`}
                      aria-current={tab === t ? 'page' : undefined}
                      className={cn('flex-1 rounded-[7px] py-1.5 text-center text-ink-2', tab === t && 'bg-field text-ink shadow-sm')}
                    >
                      {t === 'login' ? 'Log in' : 'Sign up'}
                    </Link>
                  ))}
                </nav>
              )}
              <div className="rise mt-6" style={delay(650)}>
                {children}
              </div>
            </div>
            <ol className="rise mt-5 hidden items-center justify-center gap-2 text-[11.5px] text-slate sm:flex" style={delay(900)}>
              {['Paste requirements', 'Review them', 'Get diagrams'].map((s, i) => (
                <li key={s} className="flex items-center gap-2">
                  <span className="grid size-5 place-items-center rounded-full border border-rule-strong font-mono text-[10px]">{i + 1}</span>
                  {s}
                  {i < 2 && <span aria-hidden className="h-px w-4 bg-rule-strong" />}
                </li>
              ))}
            </ol>
          </div>
        </div>
      </main>

      <footer className="rise relative flex items-center justify-between gap-3 px-6 py-4 text-[12px] text-slate sm:px-8" style={delay(1100)}>
        <span>SDDG · IT314 Group 27</span>
        <div className="flex items-center gap-3">
          <Link to="/privacy" className="hover:text-ink hover:underline">
            Privacy Policy
          </Link>
          <ThemeSwitch />
        </div>
      </footer>
    </div>
  )
}
