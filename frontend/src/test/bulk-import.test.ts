/**
 * Tests for bulk-import feature (issue #15):
 * - bulkCommitImportSessions API function (request/response shape, CSRF)
 * - BulkCommitResponse shape parsing
 * - setDefaultImportLibrary API function
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeResponse(status: number, body: unknown, ok = status >= 200 && status < 300) {
  return {
    ok,
    status,
    statusText: 'Test',
    json: async () => body,
  } as unknown as Response
}

let originalFetch: typeof globalThis.fetch
let lastRequest: { url: string; method: string; body?: string; headers: Headers } | null = null

function mockFetch(responseBody: unknown, status = 200) {
  globalThis.fetch = vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
    lastRequest = {
      url: String(url),
      method: init?.method ?? 'GET',
      body: init?.body as string | undefined,
      headers: new Headers(init?.headers),
    }
    return makeResponse(status, responseBody, status >= 200 && status < 300)
  })
}

function setCsrfCookie(token: string) {
  Object.defineProperty(document, 'cookie', {
    writable: true,
    value: `pf3d_csrf=${token}; path=/`,
  })
}

function clearCsrfCookie() {
  Object.defineProperty(document, 'cookie', {
    writable: true,
    value: '',
  })
}

beforeEach(() => {
  originalFetch = globalThis.fetch
  lastRequest = null
  clearCsrfCookie()
})

afterEach(() => {
  globalThis.fetch = originalFetch
  clearCsrfCookie()
})

// ---------------------------------------------------------------------------
// bulkCommitImportSessions
// ---------------------------------------------------------------------------

describe('bulkCommitImportSessions', () => {
  it('posts to /api/import-sessions/bulk-commit', async () => {
    const response = { total: 0, committed: 0, skipped: [], errors: [] }
    mockFetch(response)

    const { bulkCommitImportSessions } = await import('@/lib/api')
    const result = await bulkCommitImportSessions({ session_ids: [] })

    expect(lastRequest?.url).toContain('/api/import-sessions/bulk-commit')
    expect(lastRequest?.method).toBe('POST')
    expect(result.total).toBe(0)
    expect(result.committed).toBe(0)
  })

  it('sends session_ids=null to target all pending sessions', async () => {
    const response = { total: 3, committed: 3, skipped: [], errors: [] }
    mockFetch(response)

    const { bulkCommitImportSessions } = await import('@/lib/api')
    await bulkCommitImportSessions({ session_ids: null })

    const body = JSON.parse(lastRequest?.body ?? '{}')
    expect(body.session_ids).toBeNull()
  })

  it('sends library_id override when provided', async () => {
    const response = { total: 1, committed: 1, skipped: [], errors: [] }
    mockFetch(response)

    const { bulkCommitImportSessions } = await import('@/lib/api')
    await bulkCommitImportSessions({ session_ids: ['abc'], library_id: 42 })

    const body = JSON.parse(lastRequest?.body ?? '{}')
    expect(body.library_id).toBe(42)
    expect(body.session_ids).toEqual(['abc'])
  })

  it('includes CSRF token from cookie', async () => {
    const response = { total: 0, committed: 0, skipped: [], errors: [] }
    mockFetch(response)
    setCsrfCookie('my-csrf-token')

    const { bulkCommitImportSessions } = await import('@/lib/api')
    await bulkCommitImportSessions({})

    expect(lastRequest?.headers.get('X-CSRF-Token')).toBe('my-csrf-token')
  })

  it('returns skipped and error lists from response', async () => {
    const response = {
      total: 3,
      committed: 1,
      skipped: [
        { session_id: 'abc', reason: 'no_title' },
        { session_id: 'def', reason: 'no_library' },
      ],
      errors: [],
    }
    mockFetch(response)

    const { bulkCommitImportSessions } = await import('@/lib/api')
    const result = await bulkCommitImportSessions({ session_ids: ['abc', 'def', 'ghi'] })

    expect(result.total).toBe(3)
    expect(result.committed).toBe(1)
    expect(result.skipped).toHaveLength(2)
    expect(result.skipped[0].reason).toBe('no_title')
    expect(result.errors).toHaveLength(0)
  })

  it('errors list contains sessions that failed during commit', async () => {
    const response = {
      total: 2,
      committed: 1,
      skipped: [],
      errors: [{ session_id: 'fail-id', reason: 'Commit failed: disk full' }],
    }
    mockFetch(response)

    const { bulkCommitImportSessions } = await import('@/lib/api')
    const result = await bulkCommitImportSessions({ session_ids: ['ok-id', 'fail-id'] })

    expect(result.errors).toHaveLength(1)
    expect(result.errors[0].session_id).toBe('fail-id')
    expect(result.errors[0].reason).toContain('Commit failed')
  })
})

// ---------------------------------------------------------------------------
// setDefaultImportLibrary
// ---------------------------------------------------------------------------

describe('setDefaultImportLibrary', () => {
  it('puts to /api/settings/import.default_library_id', async () => {
    mockFetch({ key: 'import.default_library_id', value: 5 })

    const { setDefaultImportLibrary } = await import('@/lib/api/settings')
    const result = await setDefaultImportLibrary(5)

    expect(lastRequest?.url).toContain('/api/settings/import.default_library_id')
    expect(lastRequest?.method).toBe('PUT')
    expect(result.key).toBe('import.default_library_id')
    expect(result.value).toBe(5)
  })

  it('sends null to clear the default library', async () => {
    mockFetch({ key: 'import.default_library_id', value: null })

    const { setDefaultImportLibrary } = await import('@/lib/api/settings')
    await setDefaultImportLibrary(null)

    const body = JSON.parse(lastRequest?.body ?? '{}')
    expect(body.value).toBeNull()
  })
})
