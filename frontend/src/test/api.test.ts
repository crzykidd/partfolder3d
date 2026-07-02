/**
 * Tests for lib/api.ts
 *
 * Tests CSRF header injection and ApiError shape.
 * Uses vitest with jsdom (set in vitest.config.ts).
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ApiError } from '@/lib/api'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Build a minimal Response-like object. */
function makeResponse(status: number, body: unknown, ok = status >= 200 && status < 300) {
  return {
    ok,
    status,
    statusText: 'Test',
    json: async () => body,
  } as unknown as Response
}

// ---------------------------------------------------------------------------
// ApiError
// ---------------------------------------------------------------------------

describe('ApiError', () => {
  it('stores status and message', () => {
    const err = new ApiError(404, 'Not found')
    expect(err.status).toBe(404)
    expect(err.message).toBe('Not found')
    expect(err.name).toBe('ApiError')
    expect(err instanceof Error).toBe(true)
    expect(err instanceof ApiError).toBe(true)
  })

  it('stores optional detail', () => {
    const detail = { detail: 'User not found' }
    const err = new ApiError(404, 'Not found', detail)
    expect(err.detail).toEqual(detail)
  })
})

// ---------------------------------------------------------------------------
// CSRF header injection
// ---------------------------------------------------------------------------

describe('CSRF header injection', () => {
  let originalFetch: typeof globalThis.fetch
  let capturedHeaders: Headers | null = null
  let capturedMethod: string | null = null

  beforeEach(() => {
    capturedHeaders = null
    capturedMethod = null
    originalFetch = globalThis.fetch

    globalThis.fetch = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
      capturedHeaders = new Headers(init?.headers)
      capturedMethod = init?.method ?? 'GET'
      return makeResponse(200, { ok: true })
    })
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    // Reset cookies
    Object.defineProperty(document, 'cookie', {
      writable: true,
      value: '',
    })
  })

  /** Set pf3d_csrf cookie for the test. */
  function setCsrfCookie(token: string) {
    Object.defineProperty(document, 'cookie', {
      writable: true,
      value: `pf3d_csrf=${token}; path=/`,
    })
  }

  it('adds X-CSRF-Token on POST when cookie is set', async () => {
    setCsrfCookie('test-csrf-token')
    const { login } = await import('@/lib/api')
    await login({ email: 'a@b.com', password: 'pass' })
    expect(capturedMethod).toBe('POST')
    expect(capturedHeaders?.get('X-CSRF-Token')).toBe('test-csrf-token')
  })

  it('adds X-CSRF-Token on DELETE when cookie is set', async () => {
    setCsrfCookie('csrf-abc')
    const { revokeApiKey } = await import('@/lib/api')
    await revokeApiKey(42)
    expect(capturedMethod).toBe('DELETE')
    expect(capturedHeaders?.get('X-CSRF-Token')).toBe('csrf-abc')
  })

  it('does NOT add X-CSRF-Token on GET', async () => {
    setCsrfCookie('csrf-xyz')
    const { getMe } = await import('@/lib/api')
    await getMe()
    expect(capturedMethod).toBe('GET')
    expect(capturedHeaders?.get('X-CSRF-Token')).toBeNull()
  })

  it('does NOT add X-CSRF-Token when cookie is absent', async () => {
    // No cookie set; test a mutation without cookie
    const { createApiKey } = await import('@/lib/api')
    await createApiKey('test-label')
    expect(capturedMethod).toBe('POST')
    expect(capturedHeaders?.get('X-CSRF-Token')).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// Error handling
// ---------------------------------------------------------------------------

describe('apiFetch error handling', () => {
  let originalFetch: typeof globalThis.fetch

  beforeEach(() => {
    originalFetch = globalThis.fetch
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  it('throws ApiError with status and detail message on non-2xx', async () => {
    globalThis.fetch = vi.fn(async () =>
      makeResponse(401, { detail: 'Invalid email or password' }, false),
    )
    const { login } = await import('@/lib/api')
    await expect(login({ email: 'x@y.com', password: 'wrong' })).rejects.toSatisfy(
      (e: unknown) =>
        e instanceof ApiError && e.status === 401 && e.message === 'Invalid email or password',
    )
  })

  it('throws ApiError on 404 with fallback message', async () => {
    globalThis.fetch = vi.fn(async () =>
      makeResponse(404, 'Not Found', false),
    )
    const { getMe } = await import('@/lib/api')
    await expect(getMe()).rejects.toSatisfy(
      (e: unknown) => e instanceof ApiError && e.status === 404,
    )
  })

  it('returns undefined for 204 No Content', async () => {
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      status: 204,
      statusText: 'No Content',
      json: async () => { throw new Error('no body') },
    }) as unknown as Response)
    const { revokeApiKey } = await import('@/lib/api')
    const result = await revokeApiKey(1)
    expect(result).toBeUndefined()
  })
})
