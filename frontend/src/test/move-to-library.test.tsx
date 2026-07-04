/**
 * Tests for the MoveToLibrary control (issue #25).
 *
 * Covers:
 *  - Hidden when fewer than two enabled libraries exist.
 *  - Renders the "Move to library" trigger when ≥2 enabled libraries exist;
 *    the current library is excluded from the target options.
 *  - Selecting a target and clicking Move calls api.moveItem with the target id.
 *
 * Hermetic: @/lib/api is mocked — no real network.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import type { LibraryOut, ItemDetail } from '@/lib/api'

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api')
  return {
    ...actual,
    listLibraries: vi.fn(),
    moveItem: vi.fn(),
  }
})

import * as api from '@/lib/api'
import { MoveToLibrary } from '@/pages/item/MoveToLibrary'

function lib(id: number, name: string, enabled = true): LibraryOut {
  return { id, name, mount_path: `/lib/${id}`, enabled, item_count: 0 }
}

function renderControl(currentLibraryId = 1) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MoveToLibrary itemKey="abc123" currentLibraryId={currentLibraryId} />
    </QueryClientProvider>,
  )
}

describe('MoveToLibrary', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('is hidden when only one enabled library exists', async () => {
    vi.mocked(api.listLibraries).mockResolvedValue([lib(1, 'Main'), lib(2, 'Old', false)])
    renderControl(1)
    // Give the query a tick to resolve, then assert nothing rendered.
    await waitFor(() => expect(api.listLibraries).toHaveBeenCalled())
    expect(screen.queryByText('Move to library')).not.toBeInTheDocument()
  })

  it('shows the trigger and excludes the current library from targets', async () => {
    vi.mocked(api.listLibraries).mockResolvedValue([
      lib(1, 'Main'),
      lib(2, 'Archive'),
      lib(3, 'Prints'),
    ])
    renderControl(1)

    const trigger = await screen.findByText('Move to library')
    fireEvent.click(trigger)

    const select = screen.getByLabelText('Target library') as HTMLSelectElement
    const optionNames = Array.from(select.options).map((o) => o.textContent)
    expect(optionNames).toContain('Archive')
    expect(optionNames).toContain('Prints')
    expect(optionNames).not.toContain('Main') // current library excluded
  })

  it('calls moveItem with the selected target library id', async () => {
    vi.mocked(api.listLibraries).mockResolvedValue([lib(1, 'Main'), lib(2, 'Archive')])
    vi.mocked(api.moveItem).mockResolvedValue({ key: 'abc123' } as unknown as ItemDetail)
    renderControl(1)

    fireEvent.click(await screen.findByText('Move to library'))
    fireEvent.change(screen.getByLabelText('Target library'), { target: { value: '2' } })
    fireEvent.click(screen.getByText('Move'))

    await waitFor(() => expect(api.moveItem).toHaveBeenCalledWith('abc123', 2))
  })
})
