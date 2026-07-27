/**
 * Render-level tests for JobsPage — always-available "Clear failed" button.
 *
 * Today the clear button is contextual (keyed to the active status filter) and
 * only shows "Clear all failed" once the user selects the failed pill. These
 * tests cover the new one-click "Clear failed" affordance that is reachable
 * without selecting any filter first, and that it de-dupes when the failed
 * filter is already active.
 *
 * Hermetic: the @/lib/api module is fully mocked — no real network.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { JobsPage } from '@/pages/admin/JobsPage'
import type { PaginatedJobs } from '@/lib/api'

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api')
  return {
    ...actual,
    listJobs: vi.fn(),
    clearJobsByStatus: vi.fn(),
  }
})

import * as api from '@/lib/api'

function emptyJobs(): PaginatedJobs {
  return { total: 0, page: 1, per_page: 50, jobs: [] }
}

function makeQC() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function renderPage() {
  return render(
    <QueryClientProvider client={makeQC()}>
      <MemoryRouter>
        <JobsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('JobsPage — always-available Clear failed', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(api.listJobs).mockResolvedValue(emptyJobs())
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('shows "Clear failed" without selecting the failed status filter', async () => {
    renderPage()

    // Default filter is 'all' — the contextual button reads "Clear succeeded",
    // but "Clear failed" must also be present without any filter interaction.
    await screen.findByRole('button', { name: /Clear succeeded/i }, { timeout: 3000 })
    expect(screen.getByRole('button', { name: /^Clear failed$/i })).toBeInTheDocument()
  })

  it('clicking "Clear failed" confirms and calls clearJobsByStatus with failed', async () => {
    vi.mocked(api.clearJobsByStatus).mockResolvedValue({ archived: 3 })
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)

    renderPage()

    const btn = await screen.findByRole('button', { name: /^Clear failed$/i }, { timeout: 3000 })
    fireEvent.click(btn)

    expect(confirmSpy).toHaveBeenCalled()
    await waitFor(() => expect(api.clearJobsByStatus).toHaveBeenCalledWith('failed'))
    await screen.findByText(/Archived 3 jobs/i)
  })

  it('does not call clearJobsByStatus when the confirm dialog is dismissed', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)

    renderPage()

    const btn = await screen.findByRole('button', { name: /^Clear failed$/i }, { timeout: 3000 })
    fireEvent.click(btn)

    expect(api.clearJobsByStatus).not.toHaveBeenCalled()
  })

  it('de-dupes: hides the dedicated "Clear failed" button when the failed filter is already active', async () => {
    renderPage()

    const failedPill = await screen.findByRole('button', { name: /^failed$/ })
    fireEvent.click(failedPill)

    // Contextual button now reads "Clear all failed"; the dedicated always-on
    // button (bare "Clear failed") must not also be rendered.
    await screen.findByRole('button', { name: /Clear all failed/i })
    expect(screen.queryByRole('button', { name: /^Clear failed$/i })).not.toBeInTheDocument()
  })
})
