/**
 * JobsPage — Cancel on queued rows; Archive/Delete on superseded rows;
 * superseded status filter. Hermetic: @/lib/api is mocked.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { JobsPage } from '@/pages/admin/JobsPage'
import type { JobOut, PaginatedJobs } from '@/lib/api'

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api')
  return { ...actual, listJobs: vi.fn(), clearJobsByStatus: vi.fn() }
})

import * as api from '@/lib/api'

function job(status: string): JobOut {
  return {
    id: 'aaaaaaaa-0000-0000-0000-000000000001',
    type: 'extract_archives',
    status,
    progress: 0,
    payload: {},
    log: null,
    error: null,
    item_id: 1,
    retry_of_job_id: null,
    archived_at: null,
    created_at: '2026-11-24T00:00:00Z',
    started_at: null,
    finished_at: null,
  } as unknown as JobOut
}

function page(jobs: JobOut[]): PaginatedJobs {
  return { total: jobs.length, page: 1, per_page: 50, jobs }
}

function renderPage() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <JobsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('JobsPage — queued cancel / superseded actions', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows Cancel for a queued job', async () => {
    vi.mocked(api.listJobs).mockResolvedValue(page([job('queued')]))
    renderPage()
    expect(await screen.findByRole('button', { name: /^Cancel$/ })).toBeInTheDocument()
  })

  it('shows Archive and Delete for a superseded job', async () => {
    vi.mocked(api.listJobs).mockResolvedValue(page([job('superseded')]))
    renderPage()
    expect(await screen.findByRole('button', { name: /Archive/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Delete/ })).toBeInTheDocument()
  })

  it('has a superseded status filter', async () => {
    vi.mocked(api.listJobs).mockResolvedValue(page([]))
    renderPage()
    expect(await screen.findByRole('button', { name: /^superseded$/ })).toBeInTheDocument()
  })
})
