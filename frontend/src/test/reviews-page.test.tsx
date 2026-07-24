/**
 * Render-level tests for ReviewsPage — bulk Approve all / Reject all
 * (2026-07-23-reviews-bulk-approve-reject).
 *
 * Hermetic: the @/lib/api module is fully mocked — no real network.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { ReviewsPage } from '@/pages/admin/ReviewsPage'
import type { PaginatedReviews, ReviewItemOut } from '@/lib/api'

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api')
  return {
    ...actual,
    listReviews: vi.fn(),
    approveAllReviews: vi.fn(),
    rejectAllReviews: vi.fn(),
    listSettings: vi.fn(),
    upsertSetting: vi.fn(),
  }
})

import * as api from '@/lib/api'

function makeReview(id: number): ReviewItemOut {
  return {
    id,
    behavior: 'sidecar_sync',
    change_type: 'sidecar_pulled_to_db',
    item_id: null,
    summary: `Pending change ${id}`,
    proposed_action: {},
    status: 'pending',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    resolved_at: null,
    resolved_by_id: null,
  }
}

function makePage(items: ReviewItemOut[]): PaginatedReviews {
  return { total: items.length, page: 1, per_page: 50, items }
}

function makeQC() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function renderPage() {
  return render(
    <QueryClientProvider client={makeQC()}>
      <MemoryRouter>
        <ReviewsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('ReviewsPage — bulk approve/reject all', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(api.listSettings).mockResolvedValue([])
  })

  it('shows Approve all / Reject all buttons with the pending count', async () => {
    vi.mocked(api.listReviews).mockResolvedValue(makePage([makeReview(1), makeReview(2)]))

    renderPage()

    await screen.findByRole('button', { name: /Approve all \(2\)/i }, { timeout: 3000 })
    await screen.findByRole('button', { name: /Reject all \(2\)/i }, { timeout: 3000 })
  })

  it('disables both bulk buttons when there are no pending items', async () => {
    vi.mocked(api.listReviews).mockResolvedValue(makePage([]))

    renderPage()

    const approveBtn = await screen.findByRole('button', { name: /^Approve all$/i }, { timeout: 3000 })
    const rejectBtn = await screen.findByRole('button', { name: /^Reject all$/i }, { timeout: 3000 })
    expect(approveBtn).toBeDisabled()
    expect(rejectBtn).toBeDisabled()
  })

  it('Approve all requires a confirm step, then calls the endpoint and refreshes the list', async () => {
    vi.mocked(api.listReviews)
      .mockResolvedValueOnce(makePage([makeReview(1), makeReview(2)]))
      .mockResolvedValue(makePage([]))
    vi.mocked(api.approveAllReviews).mockResolvedValue({ approved: 2 })

    renderPage()

    const approveBtn = await screen.findByRole('button', { name: /Approve all \(2\)/i }, { timeout: 3000 })
    fireEvent.click(approveBtn)

    // Confirm copy explains the replay behaviour before calling anything.
    await screen.findByText(/applies each change to your library/i)
    expect(api.approveAllReviews).not.toHaveBeenCalled()

    const confirmBtn = await screen.findByRole('button', { name: /Confirm approve all/i })
    fireEvent.click(confirmBtn)

    await waitFor(() => expect(api.approveAllReviews).toHaveBeenCalledTimes(1))

    // List refetches and empties out; the bulk buttons reflect zero pending.
    await waitFor(() => expect(api.listReviews).toHaveBeenCalledTimes(2))
    await screen.findByText('No pending review items. The queue is clear.')
  })

  it('Reject all requires a confirm step, then calls the endpoint', async () => {
    vi.mocked(api.listReviews).mockResolvedValue(makePage([makeReview(1)]))
    vi.mocked(api.rejectAllReviews).mockResolvedValue({ rejected: 1 })

    renderPage()

    const rejectBtn = await screen.findByRole('button', { name: /Reject all \(1\)/i }, { timeout: 3000 })
    fireEvent.click(rejectBtn)

    const confirmBtn = await screen.findByRole('button', { name: /Confirm reject all/i })
    fireEvent.click(confirmBtn)

    await waitFor(() => expect(api.rejectAllReviews).toHaveBeenCalledTimes(1))
    expect(api.approveAllReviews).not.toHaveBeenCalled()
  })

  it('Cancel on the Approve-all confirm step does not call the endpoint', async () => {
    vi.mocked(api.listReviews).mockResolvedValue(makePage([makeReview(1)]))

    renderPage()

    const approveBtn = await screen.findByRole('button', { name: /Approve all \(1\)/i }, { timeout: 3000 })
    fireEvent.click(approveBtn)

    const cancelBtn = await screen.findByRole('button', { name: /^Cancel$/i })
    fireEvent.click(cancelBtn)

    expect(screen.queryByRole('button', { name: /Confirm approve all/i })).not.toBeInTheDocument()
    expect(api.approveAllReviews).not.toHaveBeenCalled()
  })
})
