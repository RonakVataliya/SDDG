import { CheckIcon, MonitorIcon, MoonIcon, SunIcon } from 'lucide-react'
import { Popover } from 'radix-ui'
import { ACCENTS, useTheme, type ThemeMode } from '@/lib/theme'
import { cn } from '@/lib/utils'

const MODES: { id: ThemeMode; label: string; Icon: typeof SunIcon }[] = [
  { id: 'system', label: 'System', Icon: MonitorIcon },
  { id: 'light', label: 'Light', Icon: SunIcon },
  { id: 'dark', label: 'Dark', Icon: MoonIcon },
]

/** Compact System / Light / Dark switch (login footer). */
export function ThemeSwitch({ className }: { className?: string }) {
  const { mode, setMode } = useTheme()
  return (
    <div role="radiogroup" aria-label="Theme" className={cn('inline-flex rounded-[9px] bg-rule p-0.5', className)}>
      {MODES.map(({ id, label, Icon }) => (
        <button
          key={id}
          type="button"
          role="radio"
          aria-checked={mode === id}
          aria-label={label}
          title={label}
          onClick={() => setMode(id)}
          className={cn('grid size-7 place-items-center rounded-[7px] text-slate', mode === id && 'bg-field text-ink shadow-sm')}
        >
          <Icon className="size-3.5" />
        </button>
      ))}
    </div>
  )
}

const preview: Record<ThemeMode, string> = {
  light: 'bg-[#f2f0ea]',
  dark: 'bg-[#0f1115]',
  system: 'bg-[linear-gradient(135deg,#f2f0ea_50%,#0f1115_50%)]',
}

/** Top-bar Appearance menu: theme + accent colour. */
export function AppearanceMenu() {
  const { mode, accent, resolved, setMode, setAccent } = useTheme()
  const Icon = resolved === 'dark' ? MoonIcon : SunIcon
  return (
    <Popover.Root>
      <Popover.Trigger className="grid size-9 place-items-center rounded-md text-ink-2 hover:bg-ink/5" aria-label="Appearance">
        <Icon className="size-4" />
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content align="end" sideOffset={8} className="z-50 w-[360px] rounded-2xl border border-rule bg-surface p-5 shadow-[var(--shadow)]">
          <p className="text-sm font-semibold">Appearance</p>
          <div role="radiogroup" aria-label="Theme" className="mt-3 grid grid-cols-3 gap-3">
            {MODES.map(({ id, label, Icon: I }) => (
              <button key={id} type="button" role="radio" aria-checked={mode === id} onClick={() => setMode(id)} className="text-center">
                <span className={cn('block h-16 rounded-[10px] border p-2', preview[id], mode === id ? 'border-2 border-accent' : 'border-rule')}>
                  <span className={cn('block h-1.5 w-1/2 rounded', id === 'dark' ? 'bg-[#eceef2]' : 'bg-[#15171c]', id === 'system' && 'bg-[#888]')} />
                  <span className={cn('mt-1.5 block h-6 rounded-md', id === 'dark' ? 'bg-[#1b1f27]' : id === 'system' ? 'bg-[#8888884d]' : 'bg-white')} />
                </span>
                <span className={cn('mt-1.5 inline-flex items-center gap-1 text-[13px]', mode === id && 'font-semibold')}>
                  <I className="size-3.5" /> {label}
                </span>
              </button>
            ))}
          </div>
          <p className="mt-5 text-sm font-semibold">Accent colour</p>
          <div role="radiogroup" aria-label="Accent colour" className="mt-3 flex gap-3">
            {ACCENTS.map((a) => (
              <button key={a.id} type="button" role="radio" aria-checked={accent === a.id} aria-label={a.label} onClick={() => setAccent(a.id)} className="text-center">
                <span
                  className="grid size-9 place-items-center rounded-full text-white"
                  style={{ background: a.swatch, boxShadow: accent === a.id ? `0 0 0 3px var(--surface), 0 0 0 5px ${a.swatch}` : undefined }}
                >
                  {accent === a.id && <CheckIcon className="size-4" />}
                </span>
                <span className="mt-1.5 block text-[11.5px] text-slate">{a.label}</span>
              </button>
            ))}
          </div>
          <p className="mt-4 border-t border-rule pt-3 text-[11.5px] text-slate">
            Used for buttons, selection and trace lines. Flag colours never change, so they always mean the same thing. Saved on this device.
          </p>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}
