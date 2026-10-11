import type { ReactNode } from 'react'
import { Footer } from '@/components/footer'
import { Wordmark } from '@/components/wordmark'
import { TraceHero } from './trace-hero'

export function AuthLayout({ title, subtitle, children }: { title: string; subtitle?: ReactNode; children: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col">
      <div className="grid flex-1 lg:grid-cols-[1fr_minmax(0,34rem)]">
        <aside className="hidden flex-col border-r border-rule bg-surface px-12 py-10 lg:flex">
          <Wordmark />
          <div className="flex flex-1 items-center py-12">
            <TraceHero />
          </div>
          <div className="max-w-md">
            <p className="text-[26px] leading-tight font-semibold tracking-tight text-balance">
              Every shape traces back to a line of your requirements.
            </p>
            <p className="mt-3 text-slate">Anything the generator had to guess is marked as an assumption, never passed off as fact.</p>
          </div>
        </aside>
        <main className="flex flex-col justify-center px-4 py-10 sm:px-12">
          <Wordmark className="mb-10 lg:hidden" />
          <div className="w-full max-w-sm">
            <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
            {subtitle && <p className="mt-2 text-sm text-slate">{subtitle}</p>}
            <div className="mt-8">{children}</div>
          </div>
        </main>
      </div>
      <Footer />
    </div>
  )
}
