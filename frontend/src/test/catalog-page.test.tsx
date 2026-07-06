/**
 * Render-level tests for CatalogPage (audit §E — page-level coverage gap).
 *
 * Covers:
 *  - Renders items returned by a mocked listItems response (table view).
 *  - Shows the "No items yet" empty state when the catalog is empty.
 *  - Tag-cloud interaction: clicking a tag activates a filter chip and
 *    re-queries listItems with that tag.
 *
 * Hermetic: the @/lib/api module is fully mocked — no real network. The
 * AuthProvider is driven by a mocked getMe so useAuth() resolves to an admin.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { ThemeProvider } from '@/components/ThemeProvider'
import { AuthProvider } from '@/context/AuthContext'
import { CatalogPage } from '@/pages/CatalogPage'
import type { MeResponse, PaginatedItems, PaginatedTags, LibraryOut } from '@/lib/api'

// ---------------------------------------------------------------------------
// jsdom polyfill — VirtualGrid observes its container size.
// ---------------------------------------------------------------------------

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver =
  globalThis.ResizeObserver ?? (ResizeObserverStub as unknown as typeof ResizeObserver)

// ---------------------------------------------------------------------------
// Module-level mock of the api layer (individual tests set return values).
// ---------------------------------------------------------------------------

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api')
  return {
    ...actual,
    getMe: vi.fn(),
    getSetupStatus: vi.fn(),
    logout: vi.fn().mockResolvedValue({ ok: true }),
    updateTheme: vi.fn().mockResolvedValue({ theme_pref: 'system' }),
    listItems: vi.fn(),
    listTags: vi.fn(),
    listLibraries: vi.fn(),
  }
})

import * as api from '@/lib/api'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const MOCK_USER: MeResponse = {
  user_id: 1,
  email: 'admin@test.com',
  name: 'Admin',
  role: 'admin',
  theme_pref: 'system',
  is_active: true,
}

function makeItem(overrides: Partial<api.ItemSummary> & { key: string; title: string }): api.ItemSummary {
  return {
    id: Math.floor(Math.random() * 100000),
    slug: 'slug',
    library_id: 1,
    dir_path: '/data/items/x',
    created_at: '2026-07-01T00:00:00Z',
    updated_at: '2026-07-01T00:00:00Z',
    default_image_path: null,
    creator_name: null,
    tag_names: [],
    favorited: false,
    has_asset: false,
    ...overrides,
  }
}

function itemsResponse(items: api.ItemSummary[]): PaginatedItems {
  return { total: items.length, page: 1, per_page: 20, items }
}

function tagsResponse(tags: api.TagSummary[]): PaginatedTags {
  return { total: tags.length, page: 1, per_page: 200, tags }
}

const ONE_LIBRARY: LibraryOut[] = [
  { id: 1, name: 'Main', mount_path: '/data/library', enabled: true, item_count: 0 },
]

const TWO_LIBRARIES: LibraryOut[] = [
  { id: 1, name: 'Main', mount_path: '/data/main', enabled: true, item_count: 0 },
  { id: 2, name: 'Minis', mount_path: '/data/minis', enabled: true, item_count: 0 },
]

// ---------------------------------------------------------------------------
// Helper — render CatalogPage with all required providers.
// ---------------------------------------------------------------------------

function makeQC() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function renderCatalog(initialPath = '/catalog') {
  return render(
    <ThemeProvider defaultTheme="system" storageKey="test-catalog-theme">
      <QueryClientProvider client={makeQC()}>
        <MemoryRouter initialEntries={[initialPath]}>
          <AuthProvider>
            <CatalogPage />
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>
    </ThemeProvider>,
  )
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('CatalogPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    vi.mocked(api.getMe).mockResolvedValue(MOCK_USER)
    vi.mocked(api.getSetupStatus).mockResolvedValue({ initialized: true })
    vi.mocked(api.listTags).mockResolvedValue(tagsResponse([]))
    vi.mocked(api.listLibraries).mockResolvedValue(ONE_LIBRARY)
  })

  it('renders items from the mocked list response', async () => {
    vi.mocked(api.listItems).mockResolvedValue(
      itemsResponse([
        makeItem({ key: 'aaa1111', title: 'Benchy Boat' }),
        makeItem({ key: 'bbb2222', title: 'Calibration Cube' }),
      ]),
    )

    // Table view avoids the virtualizer, which renders nothing at zero height in jsdom.
    renderCatalog('/catalog?view=table')

    await waitFor(() => {
      expect(screen.getByText('Benchy Boat')).toBeInTheDocument()
      expect(screen.getByText('Calibration Cube')).toBeInTheDocument()
    })
    // Header item count reflects the response total.
    expect(screen.getByText('2 items')).toBeInTheDocument()
  })

  it('shows the empty state when the catalog has no items', async () => {
    vi.mocked(api.listItems).mockResolvedValue(itemsResponse([]))

    renderCatalog('/catalog?view=table')

    await waitFor(() => {
      expect(screen.getByText('No items yet')).toBeInTheDocument()
    })
    expect(screen.getByText('Browse your 3D print library.')).toBeInTheDocument()
  })

  it('stays on the selected page when paginating (does not bounce back to page 1)', async () => {
    // total 50 @ per_page 20 → 3 pages, so the Pagination control renders.
    vi.mocked(api.listItems).mockResolvedValue({
      total: 50,
      page: 1,
      per_page: 20,
      items: [makeItem({ key: 'aaa1111', title: 'Benchy Boat' })],
    })

    renderCatalog('/catalog?view=table')

    const next = await screen.findByRole('button', { name: /Next/i })
    expect(screen.getByText('1 / 3')).toBeInTheDocument()

    fireEvent.click(next)

    // Advances to page 2 and re-queries with page: 2.
    await waitFor(() => {
      expect(screen.getByText('2 / 3')).toBeInTheDocument()
      expect(vi.mocked(api.listItems)).toHaveBeenCalledWith(
        expect.objectContaining({ page: 2 }),
      )
    })

    // Regression guard: the search-debounce effect must NOT strip ?page and bounce
    // back to page 1. Wait past DEBOUNCE_MS (300) and confirm we're still on page 2.
    await new Promise((resolve) => setTimeout(resolve, 500))
    expect(screen.getByText('2 / 3')).toBeInTheDocument()
    expect(vi.mocked(api.listItems)).not.toHaveBeenLastCalledWith(
      expect.objectContaining({ page: 1 }),
    )
  })

  it('activates a tag filter when a tag-cloud pill is clicked', async () => {
    vi.mocked(api.listItems).mockResolvedValue(
      itemsResponse([makeItem({ key: 'aaa1111', title: 'Benchy Boat' })]),
    )
    vi.mocked(api.listTags).mockResolvedValue(
      tagsResponse([
        { id: 5, name: 'miniature', category: null, popularity_count: 3, item_count: 3 },
      ]),
    )

    renderCatalog('/catalog?view=table')

    // Tag pill appears in the cloud.
    const pill = await screen.findByRole('button', { name: /#miniature \(3\)/i })
    fireEvent.click(pill)

    // Active-filter chip appears and listItems is re-queried with the tag.
    await waitFor(() => {
      expect(screen.getByText('Filtering by:')).toBeInTheDocument()
      expect(vi.mocked(api.listItems)).toHaveBeenCalledWith(
        expect.objectContaining({ tags: ['miniature'] }),
      )
    })
  })

  it('hides the library filter when only one enabled library exists', async () => {
    vi.mocked(api.listItems).mockResolvedValue(
      itemsResponse([makeItem({ key: 'aaa1111', title: 'Benchy Boat' })]),
    )
    // Default beforeEach mock returns ONE_LIBRARY.

    renderCatalog('/catalog?view=table')

    await waitFor(() => {
      expect(screen.getByText('Benchy Boat')).toBeInTheDocument()
    })
    expect(screen.queryByTitle('Filter by library')).not.toBeInTheDocument()
  })

  it('lists enabled libraries and re-queries listItems when one is selected', async () => {
    vi.mocked(api.listItems).mockResolvedValue(
      itemsResponse([makeItem({ key: 'aaa1111', title: 'Benchy Boat' })]),
    )
    vi.mocked(api.listLibraries).mockResolvedValue(TWO_LIBRARIES)

    renderCatalog('/catalog?view=table')

    // With >1 enabled library the control is visible; opening it lists the libraries.
    const trigger = await screen.findByTitle('Filter by library')
    fireEvent.click(trigger)

    const miniOption = await screen.findByRole('menuitemcheckbox', { name: 'Minis' })
    fireEvent.click(miniOption)

    // listItems is re-queried with the selected library id, and the chip shows up.
    await waitFor(() => {
      expect(vi.mocked(api.listItems)).toHaveBeenCalledWith(
        expect.objectContaining({ library_ids: [2] }),
      )
      expect(screen.getByText('Library:')).toBeInTheDocument()
    })
  })

  // ---------------------------------------------------------------------------
  // Asset filter
  // ---------------------------------------------------------------------------

  it('renders the asset filter with All / With files / Without files options', async () => {
    vi.mocked(api.listItems).mockResolvedValue(itemsResponse([]))

    renderCatalog('/catalog?view=table')

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /^All$/ })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /With files/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Without files/i })).toBeInTheDocument()
    })
  })

  it('selecting "With files" re-queries listItems with has_asset=true', async () => {
    vi.mocked(api.listItems).mockResolvedValue(
      itemsResponse([makeItem({ key: 'aaa1111', title: 'Benchy Boat', has_asset: true })]),
    )

    renderCatalog('/catalog?view=table')

    const withFilesBtn = await screen.findByRole('button', { name: /With files/i })
    fireEvent.click(withFilesBtn)

    await waitFor(() => {
      expect(vi.mocked(api.listItems)).toHaveBeenCalledWith(
        expect.objectContaining({ has_asset: true }),
      )
    })
  })

  it('selecting "Without files" re-queries listItems with has_asset=false', async () => {
    vi.mocked(api.listItems).mockResolvedValue(itemsResponse([]))

    renderCatalog('/catalog?view=table')

    const withoutBtn = await screen.findByRole('button', { name: /Without files/i })
    fireEvent.click(withoutBtn)

    await waitFor(() => {
      expect(vi.mocked(api.listItems)).toHaveBeenCalledWith(
        expect.objectContaining({ has_asset: false }),
      )
    })
  })

  it('selecting "All" clears has_asset from the query', async () => {
    vi.mocked(api.listItems).mockResolvedValue(itemsResponse([]))

    // Start with asset=true active.
    renderCatalog('/catalog?view=table&asset=true')

    // Click "All" to reset.
    const allBtn = await screen.findByRole('button', { name: /^All$/ })
    fireEvent.click(allBtn)

    await waitFor(() => {
      // has_asset should be absent (undefined) in the last call.
      const lastArgs = vi.mocked(api.listItems).mock.lastCall?.[0]
      expect(lastArgs?.has_asset).toBeUndefined()
    })
  })

  // ---------------------------------------------------------------------------
  // Card icon (table view resolves items but we can check the API call shape here;
  // the Box icon is only rendered in the VirtualGrid/ItemCard — TableView has its own layout)
  // ---------------------------------------------------------------------------

  it('shows "Print files attached" icon for has_asset=true items and hides it for has_asset=false', async () => {
    vi.mocked(api.listItems).mockResolvedValue(
      itemsResponse([
        makeItem({ key: 'aaa1111', title: 'With Asset', has_asset: true }),
        makeItem({ key: 'bbb2222', title: 'No Asset', has_asset: false }),
      ]),
    )

    renderCatalog('/catalog?view=table')

    await waitFor(() => {
      expect(screen.getByText('With Asset')).toBeInTheDocument()
      expect(screen.getByText('No Asset')).toBeInTheDocument()
    })

    // Exactly one "Print files attached" icon should appear (for the has_asset=true item only).
    expect(screen.getAllByTitle('Print files attached')).toHaveLength(1)
  })
})
