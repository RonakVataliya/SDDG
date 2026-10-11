import { Link } from 'react-router'
import { POLICY_VERSION, POLICY_DATE } from '@/features/privacy/policy'
import { formatDate } from '@/lib/utils'

export function Footer() {
  return (
    <footer className="border-t border-rule px-4 py-5 text-xs text-slate sm:px-6">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-2">
        <span>SDDG, IT314 Group 27</span>
        <Link to="/privacy" className="hover:text-ink hover:underline">
          Privacy Policy (v{POLICY_VERSION}, {formatDate(POLICY_DATE)})
        </Link>
      </div>
    </footer>
  )
}
