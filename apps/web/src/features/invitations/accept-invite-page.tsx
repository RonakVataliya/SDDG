import { useEffect, useRef } from 'react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router'
import { errorMessage } from '@/api/errors'
import { useAcceptInvitationLink } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { Notice } from '@/components/ui/notice'
import { PageLoading } from '@/components/ui/spinner'
import { withArticle } from '@/lib/people'
import { toast } from '@/lib/toast'

/** /invite?token=… — the "Copy link" fallback, used when the invitee never sees the bell (FR24a). */
export function AcceptInvitePage() {
  const [params] = useSearchParams()
  const token = params.get('token') ?? ''
  const accept = useAcceptInvitationLink()
  const navigate = useNavigate()
  const sent = useRef(false)

  useEffect(() => {
    if (!token || sent.current) return
    sent.current = true
    accept.mutate(token, {
      onSuccess: (project) => {
        toast(`You joined ${project.name} as ${withArticle(project.role)}.`)
        navigate(`/projects/${project.id}`, { replace: true })
      },
    })
  }, [token, accept, navigate])

  if (!token) return <Navigate to="/projects" replace />
  if (accept.isError)
    return (
      <div className="mx-auto max-w-lg px-4 py-16">
        <Notice tone="error" title="This invitation can't be used">
          {errorMessage(accept.error)}
          <span className="mt-3 block">
            <Button asChild size="sm" variant="secondary">
              <Link to="/projects">Go to your projects</Link>
            </Button>
          </span>
        </Notice>
      </div>
    )
  return <PageLoading label="Opening your invitation" />
}
