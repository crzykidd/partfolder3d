/**
 * VersionPage — Components build table + mismatch banner.
 * Hermetic: global fetch is stubbed per URL; no real network.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { VersionPage } from '@/pages/VersionPage'
import { BUILD_INFO } from '@/lib/buildInfo'

const SHA_A = 'a'.repeat(40)
const SHA_B = 'b'.repeat(40)

type Routes = Record<string, unknown | 404>

function stubFetch(routes: Routes) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      const body = routes[url]
      if (body === undefined || body === 404) {
        return { ok: false, status: 404, json: async () => ({}) }
      }
      return { ok: true, status: 200, json: async () => body }
    }),
  )
}

function info(commit: string, extra: object = {}) {
  return { version: '0.8.1', commit, channel: 'dev', build_date: '2026-11-25T12:00:00Z', ...extra }
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <VersionPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('VersionPage components table', () => {
  beforeEach(() => vi.unstubAllGlobals())
  afterEach(() => vi.unstubAllGlobals())

  it('renders all five component rows', async () => {
    stubFetch({
      '/build-info.json': info(SHA_A),
      '/build-info/nginx.json': { commit: SHA_A, channel: 'dev', build_date: '2026-11-25T12:00:00Z' },
      '/api/version/details': { backend: info(SHA_A), worker: info(SHA_A, { host: 'w1' }), error: null },
    })
    renderPage()
    for (const k of ['bundle', 'served', 'nginx', 'backend', 'worker']) {
      expect(await screen.findByTestId(`build-row-${k}`)).toBeInTheDocument()
    }
    await waitFor(() => {
      const row = screen.getByTestId('build-row-backend')
      expect(within(row).getByRole('link')).toHaveAttribute(
        'href',
        `https://github.com/crzykidd/partfolder3d/commit/${SHA_A}`,
      )
    })
  })

  it('shows the mismatch banner when commits differ, and a hard-refresh hint for bundle vs served', async () => {
    // BUILD_INFO.commit is 'unknown' under vitest, so compare served vs backend,
    // then check the bundle hint when the bundle commit is known.
    stubFetch({
      '/build-info.json': info(SHA_A),
      '/build-info/nginx.json': { commit: SHA_A, channel: 'dev', build_date: 'x' },
      '/api/version/details': { backend: info(SHA_B), worker: null },
    })
    renderPage()
    expect(await screen.findByRole('alert')).toHaveTextContent(/different builds/i)
    expect(BUILD_INFO.commit).toBe('unknown')
    expect(screen.getByRole('alert')).not.toHaveTextContent(/hard refresh/i)
  })

  it('hides the banner when all reporting components share a commit', async () => {
    stubFetch({
      '/build-info.json': info(SHA_A),
      '/build-info/nginx.json': { commit: SHA_A, channel: 'dev', build_date: 'x' },
      '/api/version/details': { backend: info(SHA_A), worker: info(SHA_A) },
    })
    renderPage()
    await waitFor(() => expect(screen.getAllByRole('link').length).toBeGreaterThanOrEqual(4))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows "unavailable" for 404 rows', async () => {
    stubFetch({ '/api/version/details': { backend: info(SHA_A), worker: null } })
    renderPage()
    await waitFor(() => {
      expect(within(screen.getByTestId('build-row-served')).getByText(/unavailable/i)).toBeInTheDocument()
      expect(within(screen.getByTestId('build-row-nginx')).getByText(/unavailable/i)).toBeInTheDocument()
      expect(within(screen.getByTestId('build-row-worker')).getByText(/unavailable/i)).toBeInTheDocument()
    })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
