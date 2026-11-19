import { CircleHelpIcon } from 'lucide-react'
import { useState } from 'react'
import type { TestDesign } from '@/api/client'
import { errorMessage } from '@/api/errors'
import { useAnswerFlag, useUpdateStatement } from '@/api/queries'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input, Textarea } from '@/components/ui/input'
import { AiBadge } from './ai-badge'

/**
 * AI request 1 could not test the requirement and asked a question, saved as an `untestable` flag (the existing flag
 * flow). Answering fills in the AI's rewrite; the user can adjust it and use it as the new requirement text, which
 * marks the requirement as changed so it can be regenerated.
 */
export function QuestionCard({ projectId, design, canEdit }: { projectId: string; design: TestDesign; canEdit: boolean }) {
  const q = design.question!
  const answer = useAnswerFlag(projectId)
  const rewrite = useUpdateStatement(projectId)
  const [text, setText] = useState('')
  const [suggestion, setSuggestion] = useState(q.has_suggestion ? q.suggestion : design.text)
  const applied = q.status === 'resolved' && q.has_suggestion && design.text === q.suggestion

  if (applied) return null
  return (
    <section className="rounded-xl border-2 border-violet/30 bg-field p-4" aria-label="Testability question">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="amber">
          <CircleHelpIcon className="size-3" /> Not testable yet
        </Badge>
        <span className="text-xs text-slate">question from AI request 1 · saved as an untestable flag</span>
        <span className="ml-auto">
          <AiBadge n={1} />
        </span>
      </div>
      <p className="mt-3 font-medium">{q.question}</p>

      {q.status === 'open' ? (
        canEdit && (
          <form
            className="mt-3 flex gap-2"
            onSubmit={(e) => {
              e.preventDefault()
              if (!text.trim()) return
              answer.mutate(
                { flagId: q.id, answer: text.trim() },
                { onSuccess: (flag) => setSuggestion(flag.has_suggestion ? flag.suggestion : design.text) },
              )
            }}
          >
            <Input aria-label="Your answer" placeholder="Type your answer" value={text} onChange={(e) => setText(e.target.value)} />
            <Button type="submit" disabled={!text.trim() || answer.isPending}>
              Save answer
            </Button>
          </form>
        )
      ) : (
        <div className="mt-3 space-y-2">
          <p className="text-sm text-slate">
            Your answer: <span className="text-ink">{q.answer}</span>
          </p>
          {canEdit && (
            <>
              <label htmlFor={`suggestion-${q.id}`} className="block text-sm font-medium">
                Suggested requirement
              </label>
              <Textarea
                id={`suggestion-${q.id}`}
                className="min-h-16"
                value={suggestion}
                onChange={(e) => setSuggestion(e.target.value)}
              />
              <div className="flex justify-end">
                <Button
                  disabled={!suggestion.trim() || suggestion.trim() === design.text || rewrite.isPending}
                  onClick={() => rewrite.mutate({ id: design.statement_id, text: suggestion.trim() })}
                >
                  Use this requirement
                </Button>
              </div>
            </>
          )}
        </div>
      )}
      {(answer.isError || rewrite.isError) && (
        <p className="mt-2 text-sm text-danger">{errorMessage(answer.error ?? rewrite.error)}</p>
      )}
    </section>
  )
}
