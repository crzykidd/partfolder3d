/**
 * Component tests for ItemMetadata's inline description/tags editor (issue #47,
 * prompts/2026-07-25-edit-item-description-tags.md).
 *
 * Covers:
 *  - The "Edit description & tags" trigger only renders for isOwnerOrAdmin.
 *  - Entering edit mode shows a description textarea + removable tag chips +
 *    an add-tag input.
 *  - Remove / add-tag interactions update the local draft.
 *  - Save calls api.updateItem with the full description + tag draft, applies
 *    the response to the item-detail cache, and exits edit mode.
 *  - Cancel discards the draft without calling api.updateItem.
 *  - A pending tag is badged in read (non-editing) mode.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import { ItemMetadata } from '@/pages/item/ItemMetadata'
import type { ItemDetail, TagOut } from '@/lib/api'

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api')
  return {
    ...actual,
    fetchFileText: vi.fn(),
    patchModifiedOverride: vi.fn(),
    updateItem: vi.fn(),
    listTags: vi.fn().mockResolvedValue({ total: 0, page: 1, per_page: 24, tags: [] }),
  }
})

import * as api from '@/lib/api'

function makeTag(overrides: Partial<TagOut> = {}): TagOut {
  return { id: 1, name: 'articulated', category: null, status: 'active', ...overrides }
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
    description: 'Original description',
    source_url: null,
    source_site: null,
    license: null,
    schema_version: 1,
    creator: null,
    tags: [makeTag()],
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

function renderMetadata(item: ItemDetail, isOwnerOrAdmin = true) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ItemMetadata item={item} itemKey={item.key} isOwnerOrAdmin={isOwnerOrAdmin} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('ItemMetadata — edit description & tags', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(api.listTags).mockResolvedValue({ total: 0, page: 1, per_page: 24, tags: [] })
  })

  it('hides the edit trigger for non-owner/admin viewers', () => {
    renderMetadata(makeItem(), false)
    expect(screen.queryByText('Edit description & tags')).toBeNull()
  })

  it('shows the edit trigger for owner/admin viewers', () => {
    renderMetadata(makeItem(), true)
    expect(screen.getByText('Edit description & tags')).toBeTruthy()
  })

  it('entering edit mode shows a description textarea and removable tag chips', () => {
    renderMetadata(makeItem({ tags: [makeTag({ id: 1, name: 'keychain' })] }))
    fireEvent.click(screen.getByText('Edit description & tags'))

    expect(screen.getByPlaceholderText('Add a description…')).toBeTruthy()
    expect(screen.getByDisplayValue('Original description')).toBeTruthy()
    expect(screen.getByLabelText('Remove tag keychain')).toBeTruthy()
  })

  it('removes a tag chip from the draft', () => {
    renderMetadata(makeItem({ tags: [makeTag({ id: 1, name: 'keychain' })] }))
    fireEvent.click(screen.getByText('Edit description & tags'))

    fireEvent.click(screen.getByLabelText('Remove tag keychain'))
    expect(screen.queryByLabelText('Remove tag keychain')).toBeNull()
  })

  it('adds a tag from the input via the Add button', () => {
    renderMetadata(makeItem({ tags: [] }))
    fireEvent.click(screen.getByText('Edit description & tags'))

    fireEvent.change(screen.getByPlaceholderText('Add a tag'), { target: { value: 'new-tag' } })
    fireEvent.click(screen.getByText('Add'))

    expect(screen.getByLabelText('Remove tag new-tag')).toBeTruthy()
  })

  it('Save calls api.updateItem with the edited description and tags', async () => {
    const updated = makeItem({
      description: 'Edited description',
      tags: [makeTag({ id: 1, name: 'keychain' })],
    })
    vi.mocked(api.updateItem).mockResolvedValue(updated)

    renderMetadata(makeItem({ description: 'Original description', tags: [makeTag({ id: 1, name: 'keychain' })] }))
    fireEvent.click(screen.getByText('Edit description & tags'))

    const textarea = screen.getByPlaceholderText('Add a description…')
    fireEvent.change(textarea, { target: { value: 'Edited description' } })

    fireEvent.click(screen.getByText('Save'))

    await waitFor(() => {
      expect(vi.mocked(api.updateItem)).toHaveBeenCalledWith('ab12cd34', {
        description: 'Edited description',
        tags: ['keychain'],
      })
    })

    // Exits edit mode back to the read-only view.
    await waitFor(() => {
      expect(screen.queryByPlaceholderText('Add a description…')).toBeNull()
    })
  })

  it('Cancel discards the draft without calling api.updateItem', () => {
    renderMetadata(makeItem({ description: 'Original description', tags: [makeTag({ id: 1, name: 'keychain' })] }))
    fireEvent.click(screen.getByText('Edit description & tags'))

    fireEvent.change(screen.getByPlaceholderText('Add a description…'), {
      target: { value: 'Discarded edit' },
    })
    fireEvent.click(screen.getByLabelText('Remove tag keychain'))

    fireEvent.click(screen.getByText('Cancel'))

    expect(vi.mocked(api.updateItem)).not.toHaveBeenCalled()
    expect(screen.queryByPlaceholderText('Add a description…')).toBeNull()
    // Back to read-only view with the original tag intact.
    expect(screen.getByText('#keychain')).toBeTruthy()
  })

  it('badges a pending tag in the read-only view', () => {
    renderMetadata(
      makeItem({ tags: [makeTag({ id: 1, name: 'brand-new', status: 'pending' })] }),
    )
    expect(screen.getByText('pending')).toBeTruthy()
  })
})
