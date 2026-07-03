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
})
