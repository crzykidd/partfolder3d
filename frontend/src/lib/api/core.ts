/**
 * api/core.ts — Shared infrastructure: error type, CSRF helpers, fetch wrappers.
 *
 * All domain modules import from here; nothing here imports from domain modules.
 */

// ---------------------------------------------------------------------------
// Error type
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly detail?: unknown,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

// ---------------------------------------------------------------------------
// CSRF helpers
// ---------------------------------------------------------------------------

const CSRF_COOKIE = 'pf3d_csrf'
const CSRF_HEADER = 'X-CSRF-Token'
const CSRF_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

export function getCsrfToken(): string | null {
  const entry = document.cookie
    .split(';')
    .map((c) => c.trim())
    .find((c) => c.startsWith(`${CSRF_COOKIE}=`))
  return entry ? decodeURIComponent(entry.slice(CSRF_COOKIE.length + 1)) : null
}

// ---------------------------------------------------------------------------
// Core fetch wrapper
// ---------------------------------------------------------------------------

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const method = (options.method ?? 'GET').toUpperCase()
  const headers = new Headers(options.headers)

  if (!headers.has('Content-Type') && options.body) {
    headers.set('Content-Type', 'application/json')
  }

  if (CSRF_METHODS.has(method)) {
    const csrf = getCsrfToken()
    if (csrf) {
      headers.set(CSRF_HEADER, csrf)
    }
  }

  const res = await fetch(path, { ...options, headers })

  if (!res.ok) {
    let detail: unknown
    try {
      detail = await res.json()
    } catch {
      detail = res.statusText
    }
    const message =
      typeof detail === 'object' && detail !== null && 'detail' in detail
        ? String((detail as Record<string, unknown>)['detail'])
        : res.statusText
    throw new ApiError(res.status, message, detail)
  }

  // 204 No Content — return undefined cast to T
  if (res.status === 204) {
    return undefined as T
  }

  return res.json() as Promise<T>
}

// ---------------------------------------------------------------------------
// Internal helper: multipart/form-data fetch (for file uploads)
// ---------------------------------------------------------------------------

export async function apiFetchForm<T>(path: string, body: FormData): Promise<T> {
  // Do NOT set Content-Type — browser sets it (with boundary) for FormData
  const headers = new Headers()
  const csrf = getCsrfToken()
  if (csrf) {
    headers.set(CSRF_HEADER, csrf)
  }

  const res = await fetch(path, { method: 'POST', headers, body })

  if (!res.ok) {
    let detail: unknown
    try {
      detail = await res.json()
    } catch {
      detail = res.statusText
    }
    const message =
      typeof detail === 'object' && detail !== null && 'detail' in detail
        ? String((detail as Record<string, unknown>)['detail'])
        : res.statusText
    throw new ApiError(res.status, message, detail)
  }

  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}
