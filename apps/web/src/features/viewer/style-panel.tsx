import { useEffect, useState } from 'react'
import type { DiagramType } from '@/api/client'
import { errorMessage } from '@/api/errors'
import { Button } from '@/components/ui/button'
import {
  useDiagramStyle,
  useSaveDiagramStyle,
  useStylePreview,
} from '@/api/queries'
import {
  DEFAULT_STYLE,
  DIRECTION_LABELS,
  FONT_SIZE_MAX,
  FONT_SIZE_MIN,
  STYLE_PRESETS,
  directionSupported,
  lowContrastPairs,
  styleProblems,
  withPreset,
  type DiagramStyle,
  type LayoutDirection,
  type StyleColours,
} from './style'

type StylePanelProps = {
  diagramId: string
  diagramType: DiagramType
  onPreviewChange: (url: string | null) => void
}

const colourFields: { key: keyof StyleColours; label: string }[] = [
  { key: 'background', label: 'Diagram background' },
  { key: 'fill', label: 'Shape fill' },
  { key: 'text', label: 'Text colour' },
  { key: 'line', label: 'Line colour' },
]

export function StylePanel({ diagramId, diagramType, onPreviewChange }: StylePanelProps) {
  const saved = useDiagramStyle(diagramId)
  const save = useSaveDiagramStyle(diagramId)

  const [draft, setDraft] = useState<DiagramStyle>(DEFAULT_STYLE)
  const [previewStyle, setPreviewStyle] = useState<DiagramStyle | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)

  const preview = useStylePreview(diagramId, previewStyle)
  const problems = styleProblems(draft)
  const contrastWarnings = lowContrastPairs(draft)

  useEffect(() => {
    if (saved.data) {
      setDraft(saved.data)
    }
  }, [saved.data])

 useEffect(() => {
  if (!previewStyle || !preview.data) {
    setPreviewUrl(null)
    onPreviewChange(null)
    return
  }

  const url = URL.createObjectURL(preview.data)
  setPreviewUrl(url)
  onPreviewChange(url)

  return () => {
    URL.revokeObjectURL(url)
    onPreviewChange(null)
  }
}, [preview.data, previewStyle, onPreviewChange])

  function changeColour(key: keyof StyleColours, value: string) {
    setDraft((current) => ({
      ...current,
      [key]: value,
      preset: 'custom',
    }))
  }

  async function saveStyle() {
    try {
      const result = await save.mutateAsync(draft)
      setDraft(result)
      setPreviewStyle(null)
    } catch {
      // The mutation error is displayed below.
    }
  }

  if (saved.isPending) {
    return (
      <section className="mx-5 mt-4 rounded-lg border border-rule p-4">
        Loading diagram style...
      </section>
    )
  }

  if (saved.isError) {
    return (
      <section className="mx-5 mt-4 rounded-lg border border-rule p-4">
        <p className="text-sm text-danger">
          Could not load diagram style: {errorMessage(saved.error)}
        </p>
      </section>
    )
  }

  return (
    <section className="mx-5 mt-4 rounded-lg border border-rule bg-surface p-4">
      <div className="mb-4">
        <h2 className="text-lg font-semibold text-ink">
          Customise diagram
        </h2>
        <p className="mt-1 text-sm text-slate">
          Change the appearance without changing the diagram's content.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label
            htmlFor="style-preset"
            className="mb-1 block text-sm font-medium text-ink"
          >
            Colour theme
          </label>
          <select
            id="style-preset"
            className="h-10 w-full rounded-md border border-rule-strong bg-surface px-3 text-sm text-ink"
            value={
              STYLE_PRESETS.some((preset) => preset.id === draft.preset)
                ? draft.preset ?? 'default'
                : 'custom'
            }
            onChange={(event) => {
              if (event.target.value !== 'custom') {
                setDraft((current) =>
                  withPreset(current, event.target.value),
                )
              }
            }}
          >
            {STYLE_PRESETS.map((preset) => (
              <option key={preset.id} value={preset.id}>
                {preset.label}
              </option>
            ))}
            <option value="custom">Custom colours</option>
          </select>
        </div>

        {directionSupported(diagramType) && (
          <div>
            <label
              htmlFor="style-direction"
              className="mb-1 block text-sm font-medium text-ink"
            >
              Layout direction
            </label>
            <select
              id="style-direction"
              className="h-10 w-full rounded-md border border-rule-strong bg-surface px-3 text-sm text-ink"
              value={draft.direction}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  direction: event.target.value as LayoutDirection,
                }))
              }
            >
              {Object.entries(DIRECTION_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      <div className="mt-4">
        <div className="mb-1 flex items-center justify-between">
          <label
            htmlFor="style-font-size"
            className="text-sm font-medium text-ink"
          >
            Font size
          </label>
          <span className="text-sm text-slate">{draft.font_size} pt</span>
        </div>
        <input
          id="style-font-size"
          type="range"
          min={FONT_SIZE_MIN}
          max={FONT_SIZE_MAX}
          step={1}
          value={draft.font_size}
          onChange={(event) =>
            setDraft((current) => ({
              ...current,
              font_size: Number(event.target.value),
            }))
          }
          className="w-full accent-teal"
        />
        <div className="flex justify-between text-xs text-slate">
          <span>{FONT_SIZE_MIN} pt</span>
          <span>{FONT_SIZE_MAX} pt</span>
        </div>
      </div>

      <div className="mt-5">
        <h3 className="mb-3 text-sm font-semibold text-ink">
          Custom colours
        </h3>
        <div className="grid gap-3 sm:grid-cols-2">
          {colourFields.map(({ key, label }) => (
            <div
              key={key}
              className="flex items-center gap-3 rounded-md border border-rule p-3"
            >
              <input
                type="color"
                aria-label={label}
                value={draft[key]}
                onChange={(event) => changeColour(key, event.target.value)}
                className="h-10 w-12 cursor-pointer rounded border-0 bg-transparent"
              />
              <div className="min-w-0">
                <p className="text-sm font-medium text-ink">{label}</p>
                <p className="text-xs text-slate">{draft[key]}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {problems.length > 0 && (
        <div className="mt-4 rounded-md border border-danger p-3">
          <p className="text-sm font-semibold text-danger">
            Please fix these settings:
          </p>
          <ul className="mt-1 list-disc pl-5 text-sm text-danger">
            {problems.map((problem) => (
              <li key={problem}>{problem}</li>
            ))}
          </ul>
        </div>
      )}

      {contrastWarnings.length > 0 && (
        <div className="mt-4 rounded-md border border-amber-500 p-3">
          <p className="text-sm font-semibold text-ink">
            Contrast warning
          </p>
          <p className="mt-1 text-sm text-slate">
            Some text may be difficult to read. A contrast ratio of at least
            4.5:1 is recommended.
          </p>
          <ul className="mt-1 list-disc pl-5 text-sm text-ink">
            {contrastWarnings.map((warning) => (
              <li key={warning.pair}>
                {warning.pair}: {warning.ratio.toFixed(2)}:1
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-5 flex flex-wrap gap-2">
        <Button
          type="button"
          onClick={() => setPreviewStyle({ ...draft })}
          disabled={problems.length > 0 || preview.isFetching}
        >
          {preview.isFetching ? 'Preparing preview...' : 'Preview'}
        </Button>

        <Button
          type="button"
          variant="secondary"
          onClick={saveStyle}
          disabled={problems.length > 0 || save.isPending}
        >
          {save.isPending ? 'Saving...' : 'Save changes'}
        </Button>

        {previewStyle && (
          <Button
  type="button"
  variant="ghost"
  onClick={() => {
    setPreviewStyle(null)
    setPreviewUrl(null)
    onPreviewChange(null)
  }}
>
  Clear preview
</Button>
        )}
      </div>

      {preview.isError && previewStyle && (
        <p className="mt-3 text-sm text-danger">
          Preview failed: {errorMessage(preview.error)}
        </p>
      )}

      {save.isError && (
        <p className="mt-3 text-sm text-danger">
          Save failed: {errorMessage(save.error)}
        </p>
      )}

      {previewUrl && previewStyle && (
        <div className="mt-5">
          <h3 className="mb-2 text-sm font-semibold text-ink">
            Preview image
          </h3>
          <div className="overflow-hidden rounded-md border border-rule bg-white p-2">
            <img
              src={previewUrl}
              alt="Preview of the diagram with your unsaved style"
              className="mx-auto max-h-96 w-full object-contain"
            />
          </div>
        </div>
      )}
    </section>
  )
}