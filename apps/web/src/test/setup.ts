import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterAll, afterEach, beforeAll } from 'vitest'
import { resetDb } from '@/mocks/db'
import { server } from '@/mocks/node'

// Polyfill for Vitest 5 makeCompatBlob in Node 25 / jsdom environments where implSymbol is undefined
if (typeof Blob !== 'undefined') {
  Object.defineProperty(Blob.prototype, 'undefined', {
    get() {
      const g = globalThis as unknown as { Buffer?: { from: (s: string) => unknown } }
      return { _buffer: (this as { _buffer?: unknown })._buffer ?? (g.Buffer ? g.Buffer.from('') : new Uint8Array(0)) }
    },
    configurable: true,
  })
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => {
  cleanup()
  server.resetHandlers()
  resetDb()
  localStorage.clear()
})
afterAll(() => server.close())
