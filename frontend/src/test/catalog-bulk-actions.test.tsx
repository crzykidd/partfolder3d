/**
 * Render-level tests for catalog multi-select + the bulk action bar/dialogs.
 * Hermetic: @/lib/api is mocked. Table view is used (the virtualizer renders
 * nothing at zero height in jsdom).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { ThemeProvider } from '@/components/ThemeProvider'
import { AuthProvider } from '@/context/AuthContext'
import { CatalogPage } from '@/pages/CatalogPage'
import type { MeResponse, LibraryOut } from '@/lib/api'

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver =
  globalThis.ResizeObserver ?? (ResizeObserverStub as unknown as typeof ResizeObserver)

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
    bulkCreatePrintRecords: vi.fn(),
    bulkTagItems: vi.fn(),
    bulkMoveItems: vi.fn(),
    bulkRescanItems: vi.fn(),
    bulkDeleteItems: vi.fn(),
  }
})

import * as api from '@/lib/api'

const MOCK_USER: MeResponse = {
  user_id: 1,
  email: 'admin@test.com',
  name: 'Admin',
  role: 'admin',
  theme_pref: 'system',
  is_active: true,
}

const LIBS: LibraryOut[] = [
  { id: 1, name: 'Main', mount_path: '/a', enabled: true, item_count: 0 },
  { id: 2, name: 'Minis', mount_path: '/b', enabled: true, item_count: 0 },
]

function makeItem(key: string, title: string): api.ItemSummary {
  return {
    id: 1,
    key,
    title,
    slug: 's',
    library_id: 1,
    dir_path: '/x',
    created_at: '2026-07-01T00:00:00Z',
    updated_at: '2026-07-01T00:00:00Z',
    default_image_path: null,
    creator_name: null,
    tag_names: [],
    favorited: false,
    has_asset: false,
  }
}

const PAGE1 = ['a', 'b', 'c', 'd'].map((k) => makeItem(k, `Model ${k.toUpperCase()}`))
const PAGE2 = [makeItem('z', 'Model Z')]

function LocationProbe() {
  const loc = useLocation()
  return <div data-testid="loc">{loc.pathname + loc.search}</div>
}

function renderCatalog() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <ThemeProvider defaultTheme="system" storageKey="test-bulk-theme">
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={['/catalog?view=table']}>
          <AuthProvider>
            <CatalogPage />
            <LocationProbe />
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>
    </ThemeProvider>,
  )
}

async function enterSelectMode() {
  await screen.findByText('Model A')
  fireEvent.click(screen.getByRole('button', { name: /^Select$/ }))
}

const row = (k: string) => screen.getByTestId(`select-row-${k}`)
const checkbox = (title: string) => screen.getByRole('checkbox', { name: `Select ${title}` })

describe('CatalogPage bulk selection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    vi.mocked(api.getMe).mockResolvedValue(MOCK_USER)
    vi.mocked(api.getSetupStatus).mockResolvedValue({ initialized: true })
    vi.mocked(api.listTags).mockResolvedValue({ total: 0, page: 1, per_page: 200, tags: [] })
    vi.mocked(api.listLibraries).mockResolvedValue(LIBS)
    vi.mocked(api.listItems).mockImplementation(async (p) => {
      const page = (p as { page?: number }).page ?? 1
      return page === 2
        ? { total: 25, page: 2, per_page: 20, items: PAGE2 }
        : { total: 25, page: 1, per_page: 20, items: PAGE1 }
    })
  })

  it('has no checkboxes or bar until select mode is entered; toggle shows/hides them', async () => {
    renderCatalog()
    await screen.findByText('Model A')
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0)
    expect(screen.queryByRole('toolbar', { name: 'Bulk actions' })).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: /^Select$/ }))
    expect(screen.getAllByRole('checkbox')).toHaveLength(4)
    expect(screen.getByRole('toolbar', { name: 'Bulk actions' })).toBeInTheDocument()
    expect(screen.getByText('0 selected')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Exit select mode' }))
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0)
  })

  it('clicking the checkbox itself toggles selection without cancelling the native toggle', async () => {
    renderCatalog()
    await enterSelectMode()
    // fireEvent.click returns false if any handler called preventDefault — which in a
    // real browser reverts the checkbox visually (the original bug: box never ticks).
    expect(fireEvent.click(checkbox('Model B'))).toBe(true)
    expect(checkbox('Model B')).toBeChecked()
    expect(screen.getByText('1 selected')).toBeInTheDocument()
    expect(fireEvent.click(checkbox('Model B'))).toBe(true)
    expect(checkbox('Model B')).not.toBeChecked()
    expect(screen.getByText('0 selected')).toBeInTheDocument()
  })

  it('clicking a row toggles selection and does NOT navigate; outside the mode it still navigates', async () => {
    renderCatalog()
    await enterSelectMode()
    fireEvent.click(row('b'))
    expect(checkbox('Model B')).toBeChecked()
    expect(screen.getByText('1 selected')).toBeInTheDocument()
    // Clicking the title link inside select mode must not navigate either.
    fireEvent.click(screen.getByText('Model C'))
    expect(screen.getByText('2 selected')).toBeInTheDocument()
    expect(screen.getByTestId('loc').textContent).toBe('/catalog?view=table')

    fireEvent.click(row('b'))
    expect(checkbox('Model B')).not.toBeChecked()

    // Exit mode: clicking a row navigates again.
    fireEvent.click(screen.getByRole('button', { name: 'Exit select mode' }))
    fireEvent.click(screen.getByText('Model A'))
    await waitFor(() => expect(screen.getByTestId('loc').textContent).toBe('/items/a'))
  })

  it('shift-click selects a range', async () => {
    renderCatalog()
    await enterSelectMode()
    fireEvent.click(row('a'))
    fireEvent.click(row('c'), { shiftKey: true })
    expect(checkbox('Model A')).toBeChecked()
    expect(checkbox('Model B')).toBeChecked()
    expect(checkbox('Model C')).toBeChecked()
    expect(checkbox('Model D')).not.toBeChecked()
    expect(screen.getByText('3 selected')).toBeInTheDocument()
  })

  it('select-all-on-page and Clear', async () => {
    renderCatalog()
    await enterSelectMode()
    fireEvent.click(screen.getByRole('button', { name: 'Select all on this page' }))
    expect(screen.getByText('4 selected')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Clear' }))
    expect(screen.getByText('0 selected')).toBeInTheDocument()
  })

  it('selection persists across pagination', async () => {
    renderCatalog()
    await enterSelectMode()
    fireEvent.click(row('a'))
    fireEvent.click(screen.getByRole('button', { name: /Next/ }))
    await screen.findByText('Model Z')
    fireEvent.click(row('z'))
    expect(screen.getByText('2 selected')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Prev/ }))
    await screen.findByText('Model A')
    expect(checkbox('Model A')).toBeChecked()
    expect(screen.getByText('2 selected')).toBeInTheDocument()
  })

  it('Esc exits select mode', async () => {
    renderCatalog()
    await enterSelectMode()
    fireEvent.click(row('a'))
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('toolbar', { name: 'Bulk actions' })).toBeNull()
  })
})

describe('bulk dialogs', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    vi.mocked(api.getMe).mockResolvedValue(MOCK_USER)
    vi.mocked(api.getSetupStatus).mockResolvedValue({ initialized: true })
    vi.mocked(api.listTags).mockResolvedValue({ total: 0, page: 1, per_page: 200, tags: [] })
    vi.mocked(api.listLibraries).mockResolvedValue(LIBS)
    vi.mocked(api.listItems).mockResolvedValue({ total: 4, page: 1, per_page: 20, items: PAGE1 })
  })

  async function selectTwo() {
    renderCatalog()
    await enterSelectMode()
    fireEvent.click(row('a'))
    fireEvent.click(row('b'))
  }

  it('Log print posts one shared record for the selected keys', async () => {
    vi.mocked(api.bulkCreatePrintRecords).mockResolvedValue({ created: 2, records: [] })
    await selectTwo()
    fireEvent.click(screen.getByRole('button', { name: /Log print/ }))
    const dlg = await screen.findByRole('dialog', { name: 'Log print for 2 items' })
    expect(within(dlg).getByText('Model A')).toBeInTheDocument()
    fireEvent.change(within(dlg).getByPlaceholderText('e.g. PLA'), { target: { value: 'PETG' } })
    fireEvent.click(within(dlg).getByRole('button', { name: 'Log print' }))
    await waitFor(() =>
      expect(api.bulkCreatePrintRecords).toHaveBeenCalledWith(
        ['a', 'b'],
        expect.objectContaining({ material: 'PETG', visibility: 'private' }),
      ),
    )
    expect(await within(dlg).findByText('Logged 2 print records.')).toBeInTheDocument()
  })

  it('Tags posts add/remove lists', async () => {
    vi.mocked(api.bulkTagItems).mockResolvedValue({ succeeded: ['a', 'b'], failed: [] })
    await selectTwo()
    fireEvent.click(screen.getByRole('button', { name: /Tags/ }))
    const dlg = await screen.findByRole('dialog')
    const apply = within(dlg).getByRole('button', { name: 'Apply' })
    expect(apply).toBeDisabled()
    const addInput = within(dlg).getAllByPlaceholderText('Type a tag, press Enter')[0]
    fireEvent.change(addInput, { target: { value: 'dragon' } })
    fireEvent.keyDown(addInput, { key: 'Enter' })
    const rmInput = within(dlg).getAllByPlaceholderText('Type a tag, press Enter')[1]
    fireEvent.change(rmInput, { target: { value: 'old' } })
    fireEvent.keyDown(rmInput, { key: 'Enter' })
    fireEvent.click(apply)
    await waitFor(() =>
      expect(api.bulkTagItems).toHaveBeenCalledWith(['a', 'b'], ['dragon'], ['old']),
    )
  })

  it('Move calls the bulk move endpoint and drops moved items; failures stay selected', async () => {
    vi.mocked(api.bulkMoveItems).mockResolvedValue({
      total: 2,
      moved: 1,
      skipped: [],
      errors: [{ key: 'b', reason: 'disk full' }],
    })
    await selectTwo()
    fireEvent.click(screen.getByRole('button', { name: /Move/ }))
    const dlg = await screen.findByRole('dialog')
    const go = within(dlg).getByRole('button', { name: 'Move' })
    expect(go).toBeDisabled()
    fireEvent.change(within(dlg).getByLabelText('Target library'), { target: { value: '2' } })
    fireEvent.click(go)
    await waitFor(() => expect(api.bulkMoveItems).toHaveBeenCalledWith(['a', 'b'], 2))
    // Partial failure rendering: title + error inline.
    expect(await within(dlg).findByText(/1 moved, 1 failed/)).toBeInTheDocument()
    expect(within(dlg).getByText(/Model B: disk full/)).toBeInTheDocument()
    fireEvent.click(within(dlg).getByRole('button', { name: 'Done' }))
    expect(screen.getByText('1 selected')).toBeInTheDocument()
    expect(checkbox('Model B')).toBeChecked()
    expect(checkbox('Model A')).not.toBeChecked()
  })

  it('Rescan (via More menu) confirms then posts keys', async () => {
    vi.mocked(api.bulkRescanItems).mockResolvedValue({ succeeded: ['a', 'b'], failed: [] })
    await selectTwo()
    fireEvent.click(screen.getByRole('button', { name: /More/ }))
    fireEvent.click(screen.getByRole('menuitem', { name: /Rescan/ }))
    const dlg = await screen.findByRole('dialog')
    expect(api.bulkRescanItems).not.toHaveBeenCalled()
    fireEvent.click(within(dlg).getByRole('button', { name: 'Rescan' }))
    await waitFor(() => expect(api.bulkRescanItems).toHaveBeenCalledWith(['a', 'b']))
    expect(await within(dlg).findByText(/2 rescanned/)).toBeInTheDocument()
  })

  it('Delete is gated by typing the count or "delete"; drops succeeded from selection', async () => {
    vi.mocked(api.bulkDeleteItems).mockResolvedValue({
      succeeded: ['a'],
      failed: [{ key: 'b', error: 'locked' }],
    })
    await selectTwo()
    fireEvent.click(screen.getByRole('button', { name: /More/ }))
    fireEvent.click(screen.getByRole('menuitem', { name: /Delete/ }))
    const dlg = await screen.findByRole('dialog')
    expect(within(dlg).getByText(/30 days/)).toBeInTheDocument()
    const btn = within(dlg).getByRole('button', { name: 'Delete items' })
    expect(btn).toBeDisabled()
    const input = within(dlg).getByLabelText(/to confirm/)
    fireEvent.change(input, { target: { value: '5' } })
    expect(btn).toBeDisabled()
    fireEvent.change(input, { target: { value: '2' } })
    expect(btn).toBeEnabled()
    fireEvent.change(input, { target: { value: 'delete' } })
    expect(btn).toBeEnabled()
    fireEvent.click(btn)
    await waitFor(() => expect(api.bulkDeleteItems).toHaveBeenCalledWith(['a', 'b']))
    expect(await within(dlg).findByText(/Model B: locked/)).toBeInTheDocument()
    fireEvent.click(within(dlg).getByRole('button', { name: 'Done' }))
    expect(screen.getByText('1 selected')).toBeInTheDocument()
  })
})
