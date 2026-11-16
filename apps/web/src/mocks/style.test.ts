import { api, unwrap } from '@/api/client'
import { ApiError } from '@/api/errors'
import { DEFAULT_STYLE, withPreset } from '@/features/viewer/style'
import { seedDiagram } from '@/test/seed'
import { getDb, save } from './db'
import { renderUseCase, type UseCaseModel } from './render'

const path = (id: string) => ({ params: { path: { diagram_id: id } } })
const getStyle = (id: string) => unwrap(api.GET('/diagrams/{diagram_id}/style', path(id)))
const putStyle = (id: string, body: typeof DEFAULT_STYLE) => unwrap(api.PUT('/diagrams/{diagram_id}/style', { ...path(id), body }))

beforeEach(() => {
  localStorage.setItem('sddg.mock.session', JSON.stringify({ email: 'dev@sddg.test', accessToken: 'mock-token:dev@sddg.test' }))
  seedDiagram()
})

describe('mock style endpoints (#38)', () => {
  it('returns the default until a style is saved, then the saved one', async () => {
    expect(await getStyle('dg_1')).toEqual(DEFAULT_STYLE)
    const dark = { ...withPreset(DEFAULT_STYLE, 'dark'), direction: 'TB' as const, font_size: 18 }
    expect(await putStyle('dg_1', dark)).toEqual(dark)
    expect(await getStyle('dg_1')).toEqual(dark)
  })

  it('lets a later version inherit the look until it saves its own', async () => {
    const parent = getDb().diagrams[0]
    getDb().diagrams.push({ ...parent, id: 'dg_2', parent_id: 'dg_1', instruction: 'rename', style: undefined })
    save()
    const warm = withPreset(DEFAULT_STYLE, 'warm')
    await putStyle('dg_1', warm)
    expect(await getStyle('dg_2')).toEqual(warm)

    const big = { ...warm, font_size: 20 }
    await putStyle('dg_2', big)
    expect(await getStyle('dg_2')).toEqual(big)
    expect(await getStyle('dg_1')).toEqual(warm) // the earlier version keeps its own
  })

  it('rejects an out-of-range font size with a plain message and keeps the old style', async () => {
    const err = await putStyle('dg_1', { ...DEFAULT_STYLE, font_size: 30 }).catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err).toMatchObject({ status: 422, message: 'Font size must be a whole number from 8 to 24 pt.' })
    expect(await getStyle('dg_1')).toEqual(DEFAULT_STYLE)
  })

  it('does not change the diagram itself', async () => {
    const before = structuredClone(getDb().diagrams[0].model)
    await putStyle('dg_1', { ...withPreset(DEFAULT_STYLE, 'blueprint'), direction: 'TB', font_size: 24 })
    expect(getDb().diagrams[0].model).toEqual(before)
  })

  it('answers 404 for a diagram that does not exist', async () => {
    await expect(getStyle('dg_missing')).rejects.toMatchObject({ status: 404 })
  })
})

describe('mock renderer with a style (#38)', () => {
  const model: UseCaseModel = {
    system: 'Library',
    actors: [{ id: 'a', name: 'Librarian' }],
    cases: [
      { id: 'c', name: 'Issue a book to a registered library member', assumed: false },
      { id: 'd', name: 'Log in', assumed: true },
    ],
    links: [{ actor: 'a', case: 'c' }],
  }
  const count = (svg: string, tag: string) => svg.split(`<${tag} `).length - 1

  it('uses the style colours and keeps the dashed amber outline for assumed use cases', () => {
    const svg = renderUseCase(model, withPreset(DEFAULT_STYLE, 'dark'))
    expect(svg).toContain('fill="#1E1E24"')
    expect(svg).toContain('fill="#2B2D36"')
    expect(svg).toContain('stroke="#b26b00" stroke-dasharray="5 4"')
  })

  it('grows the use-case ellipses with the font so long labels are not clipped', () => {
    const rx = (svg: string) => Number(/<ellipse [^>]*rx="(\d+)"/.exec(svg)![1])
    const small = renderUseCase(model, { ...DEFAULT_STYLE, font_size: 8 })
    const large = renderUseCase(model, { ...DEFAULT_STYLE, font_size: 24 })
    expect(rx(large)).toBeGreaterThan(rx(small))
    expect(rx(large)).toBeGreaterThan((model.cases[0].name.length * 32 * 0.55) / 2) // about half the label width at 24 pt
  })

  it('changes only positions between directions, never what is drawn', () => {
    const lr = renderUseCase(model, { ...DEFAULT_STYLE, direction: 'LR' })
    const tb = renderUseCase(model, { ...DEFAULT_STYLE, direction: 'TB' })
    expect(tb).not.toBe(lr)
    for (const tag of ['ellipse', 'line', 'circle', 'text']) expect(count(tb, tag)).toBe(count(lr, tag))
  })
})
