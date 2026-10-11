import { Link } from 'react-router'
import { Button } from '@/components/ui/button'

export function NotFoundPage({ message = 'This page does not exist, or you do not have access to it.' }: { message?: string }) {
  return (
    <div className="mx-auto max-w-md px-4 py-24 text-center">
      <h1 className="text-xl font-semibold">Not found</h1>
      <p className="mt-2 text-slate">{message}</p>
      <Button asChild variant="secondary" className="mt-6">
        <Link to="/projects">Go to your projects</Link>
      </Button>
    </div>
  )
}
