import { ArrowLeftIcon } from 'lucide-react'
import { Link } from 'react-router'
import { Button } from '@/components/ui/button'

export function NotFoundPage({ message = 'The link may be old, or the project was deleted or never shared with you.' }: { message?: string }) {
  return (
    <div className="grid-bg grid flex-1 place-items-center px-4 py-20">
      <div className="grid items-center gap-12 md:grid-cols-[auto_minmax(0,400px)]">
        <svg viewBox="0 0 380 220" className="mx-auto w-72 md:w-96" aria-hidden>
          <rect x="10" y="80" width="130" height="60" rx="30" fill="var(--field)" stroke="var(--ink)" strokeWidth="1.6" />
          <text x="75" y="115" textAnchor="middle" fontSize="13" fill="var(--ink)" fontFamily="var(--font-sans)">You are here</text>
          <path d="M140 110h70" stroke="var(--ink)" strokeWidth="1.6" />
          <path d="M222 104l10 12M232 104l-10 12" stroke="var(--danger)" strokeWidth="2" strokeLinecap="round" />
          <path d="M244 110h30" stroke="var(--rule-strong)" strokeWidth="1.6" strokeDasharray="4 4" />
          <rect x="276" y="80" width="96" height="60" rx="30" fill="none" stroke="var(--rule-strong)" strokeWidth="1.6" strokeDasharray="5 4" />
          <text x="324" y="117" textAnchor="middle" fontSize="18" fill="var(--slate)" fontFamily="var(--font-mono)">?</text>
        </svg>
        <div>
          <p className="font-mono text-[11px] tracking-[0.08em] text-danger uppercase">Error 404</p>
          <h1 className="mt-2 text-[30px] leading-tight font-semibold">This page has no incoming edges.</h1>
          <p className="mt-2 text-slate">{message}</p>
          <Button asChild className="mt-6">
            <Link to="/projects">
              <ArrowLeftIcon /> Back to projects
            </Link>
          </Button>
        </div>
      </div>
    </div>
  )
}
