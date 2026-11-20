import { act, renderHook } from '@testing-library/react'
import { pickBackground } from '@/features/auth/backgrounds'
import { useTheme } from './theme'

describe('appearance', () => {
  it('defaults to System, and a chosen theme and accent are applied and remembered', () => {
    const { result } = renderHook(() => useTheme())
    expect(result.current.mode).toBe('system')
    act(() => result.current.setMode('dark'))
    act(() => result.current.setAccent('violet'))
    expect(document.documentElement.dataset).toMatchObject({ theme: 'dark', accent: 'violet' })
    expect(localStorage.getItem('sddg.theme')).toBe('dark')
    act(() => result.current.setMode('system'))
  })
})

describe('login background', () => {
  it('never shows the same background twice in a row', () => {
    let last = pickBackground(() => 0)
    for (let i = 0; i < 20; i++) {
      const next = pickBackground(Math.random)
      expect(next).not.toBe(last)
      last = next
    }
  })
})
