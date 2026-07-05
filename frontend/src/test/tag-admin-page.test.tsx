/**
 * Render-level tests for TagAdminPage — auto-approve toggle + approve-all (#31).
 *
 * Hermetic: the @/lib/api module is fully mocked — no real network.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { TagAdminPage } from '@/pages/admin/TagAdminPage'
import type { SettingOut, TagAdminOut } from '@/lib/api'

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api')
  return {
    ...actual,
    listSettings: vi.fn(),
    setTagsAutoApprove: vi.fn(),
    listAdminPendingTags: vi.fn(),
    adminApproveAllTags: vi.fn(),
    listAllTags: vi.fn(),
  }
})

import * as api from '@/lib/api'

function makePendingTag(name: string, id: number): TagAdminOut {
  return { id, name, category: null, popularity_count: 0, item_count: 0, status: 'pending' }
}

function makeQC() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function renderPage() {
  return render(
    <QueryClientProvider client={makeQC()}>
      <MemoryRouter>
        <TagAdminPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('TagAdminPage — auto-approve (#31)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(api.listAllTags).mockResolvedValue({ total: 0, page: 1, per_page: 50, tags: [] })
  })

  it('renders the auto-approve toggle reflecting the stored setting', async () => {
    const settings: SettingOut[] = [{ key: 'tags.auto_approve', value: true }]
    vi.mocked(api.listSettings).mockResolvedValue(settings)
    vi.mocked(api.listAdminPendingTags).mockResolvedValue([])

    renderPage()

    const toggle = await screen.findByRole('switch', { name: /Auto-approve new tags/i }, { timeout: 3000 })
    await waitFor(() => expect(toggle).toHaveAttribute('aria-checked', 'true'))
  })

  it('toggling the switch persists the new value', async () => {
    vi.mocked(api.listSettings).mockResolvedValue([{ key: 'tags.auto_approve', value: false }])
    vi.mocked(api.listAdminPendingTags).mockResolvedValue([])
    vi.mocked(api.setTagsAutoApprove).mockResolvedValue({ key: 'tags.auto_approve', value: true })

    renderPage()

    const toggle = await screen.findByRole('switch', { name: /Auto-approve new tags/i }, { timeout: 3000 })
    expect(toggle).toHaveAttribute('aria-checked', 'false')
    fireEvent.click(toggle)

    await waitFor(() => expect(api.setTagsAutoApprove).toHaveBeenCalledWith(true))
  })

  it('shows an Approve all button that calls the endpoint when tags are pending', async () => {
    vi.mocked(api.listSettings).mockResolvedValue([])
    vi.mocked(api.listAdminPendingTags).mockResolvedValue([
      makePendingTag('alpha', 1),
      makePendingTag('beta', 2),
    ])
    vi.mocked(api.adminApproveAllTags).mockResolvedValue({ approved: 2 })

    renderPage()

    const btn = await screen.findByRole('button', { name: /Approve all \(2\)/i }, { timeout: 3000 })
    fireEvent.click(btn)

    await waitFor(() => expect(api.adminApproveAllTags).toHaveBeenCalledTimes(1))
  })

  it('hides the Approve all button when there are no pending tags', async () => {
    vi.mocked(api.listSettings).mockResolvedValue([])
    vi.mocked(api.listAdminPendingTags).mockResolvedValue([])

    renderPage()

    // Wait for the pending section to settle (empty state message renders).
    await screen.findByText('No pending tags.')
    expect(screen.queryByRole('button', { name: /Approve all/i })).not.toBeInTheDocument()
  })
})
