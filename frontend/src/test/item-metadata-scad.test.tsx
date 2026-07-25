/**
 * Component tests for ItemMetadata's "Show SCAD" action (2026-07-25-scad-source-view.md).
 *
 * Covers:
 *  - The button renders only when the item has a source/.scad file, hidden otherwise.
 *  - Opening the modal fetches the file's text via api.fetchFileText and displays it.
 *  - Copy calls navigator.clipboard.writeText with the fetched code.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { ItemMetadata } from '@/pages/item/ItemMetadata'
import type { ItemDetail, FileOut } from '@/lib/api'

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api')
  return {
    ...actual,
    fetchFileText: vi.fn(),
    patchModifiedOverride: vi.fn(),
  }
})

import * as api from '@/lib/api'

function makeFile(overrides: Partial<FileOut> = {}): FileOut {
  return {
    id: 1,
    path: 'part.scad',
    role: 'source',
    size: 1024,
    sha256: null,
    object_analysis: null,
    preview_3d: false,
    ...overrides,
  }
}

function makeItem(overrides: Partial<ItemDetail> = {}): ItemDetail {
  return {
    id: 1,
    key: 'ab12cd34',
    title: 'Widget',
    slug: 'widget-ab12cd34',
    library_id: 1,
    dir_path: '/library/widget',
    created_at: '2026-07-01T00:00:00Z',
    updated_at: '2026-07-01T00:00:00Z',
    description: null,
    source_url: null,
    source_site: null,
    license: null,
    schema_version: 1,
    creator: null,
    tags: [],
    files: [],
    images: [],
    is_modified: false,
    locally_modified_at: null,
    modified_override: null,
    analysis_total_objects: null,
    analysis_total_colors: null,
    analysis_total_est_grams: null,
    ...overrides,
  }
}

function renderMetadata(item: ItemDetail) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <ItemMetadata item={item} itemKey={item.key} isOwnerOrAdmin={false} />
    </QueryClientProvider>,
  )
}

describe('ItemMetadata — Show SCAD', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
      configurable: true,
    })
  })

  it('hides the Show SCAD button when the item has no source/.scad file', () => {
    renderMetadata(makeItem({ files: [makeFile({ role: 'model', path: 'widget.stl' })] }))
    expect(screen.queryByText('Show SCAD')).toBeNull()
  })

  it('shows the Show SCAD button when the item has a source-role file', () => {
    renderMetadata(makeItem({ files: [makeFile()] }))
    expect(screen.getByText('Show SCAD')).toBeTruthy()
  })

  it('opens the modal, fetches and displays the code, and copies it', async () => {
    const code = 'cube([10, 10, 10]);\n'
    vi.mocked(api.fetchFileText).mockResolvedValue(code)

    renderMetadata(makeItem({ files: [makeFile()] }))
    fireEvent.click(screen.getByText('Show SCAD'))

    await waitFor(() => {
      expect(vi.mocked(api.fetchFileText)).toHaveBeenCalledWith('ab12cd34', 'part.scad')
    })
    expect(await screen.findByText(code.trim(), { exact: false })).toBeTruthy()

    fireEvent.click(screen.getByText('Copy'))
    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith(code)
    })
    expect(await screen.findByText('Copied')).toBeTruthy()
  })

  it('skips the fetch and shows a size warning above the preview cap', () => {
    const bigFile = makeFile({ size: 10 * 1024 * 1024 }) // 10 MB > 5 MB cap
    renderMetadata(makeItem({ files: [bigFile] }))
    fireEvent.click(screen.getByText('Show SCAD'))

    expect(screen.getByText(/too large to preview inline/i)).toBeTruthy()
    expect(vi.mocked(api.fetchFileText)).not.toHaveBeenCalled()
  })
})
