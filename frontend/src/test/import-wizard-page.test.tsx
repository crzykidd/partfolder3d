/**
 * Render-level tests for ImportWizardPage (audit §E — page-level coverage gap).
 *
 * Covers:
 *  - Mounts with a mocked session and renders the first (Title) step.
 *  - The Title-step validation runs when advancing with an empty title.
 *
 * Hermetic: the @/lib/api module is mocked — getImportSession feeds the page,
 * getAiStatus answers TitleStep's provider probe. source_url is null so no
 * site-capability query fires and no real network is touched.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { ImportWizardPage } from '@/pages/ImportWizardPage'
import type { ImportSession } from '@/lib/api'

// ---------------------------------------------------------------------------
// Module-level api mock
// ---------------------------------------------------------------------------

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api')
  return {
    ...actual,
    getImportSession: vi.fn(),
    getAiStatus: vi.fn().mockResolvedValue({ provider_available: false }),
    getSiteCapability: vi.fn(),
    patchImportSession: vi.fn(),
  }
})

import * as api from '@/lib/api'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeSession(overrides: Partial<ImportSession> = {}): ImportSession {
  return {
    id: 'sess-1',
    status: 'pending_wizard',
    source_type: 'url',
    source_url: null,
    inbox_folder: null,
    staging_dir: null,
    suggested_title: 'Cool Widget',
    confirmed_title: null,
    description: null,
    license: null,
    source_site: null,
    creator_name: null,
    creator_profile_url: null,
    creator_source_site: null,
    creator_is_own_design: false,
    creator_id: null,
    tag_state: { confirmed: [], pending: [] },
    default_image_path: null,
    library_id: 1,
    job_id: null,
    item_id: null,
    created_by_id: 1,
    created_at: '2026-07-01T00:00:00Z',
    updated_at: '2026-07-01T00:00:00Z',
    error: null,
    scrape_note: null,
    files: [],
    images: [],
    ...overrides,
  }
}

function makeQC() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function renderWizard() {
  return render(
    <QueryClientProvider client={makeQC()}>
      <MemoryRouter initialEntries={['/import/sess-1']}>
        <Routes>
          <Route path="/import/:sessionId" element={<ImportWizardPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ImportWizardPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(api.getAiStatus).mockResolvedValue({ provider_available: false })
  })

  it('mounts and renders the first (Title) step from the mocked session', async () => {
    vi.mocked(api.getImportSession).mockResolvedValue(makeSession())

    renderWizard()

    // Page chrome
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Import Wizard' })).toBeInTheDocument()
    })
    // Title step is populated with the session's suggested title.
    expect(screen.getByDisplayValue('Cool Widget')).toBeInTheDocument()
    // First step's advance control.
    expect(screen.getByRole('button', { name: /Next/i })).toBeInTheDocument()
  })

  it('blocks advancing with a validation error when the title is empty', async () => {
    vi.mocked(api.getImportSession).mockResolvedValue(
      makeSession({ suggested_title: null, confirmed_title: null }),
    )

    renderWizard()

    const next = await screen.findByRole('button', { name: /Next/i })
    fireEvent.click(next)

    await waitFor(() => {
      expect(screen.getByText('Please enter a title.')).toBeInTheDocument()
    })
    // Validation short-circuits before any PATCH is attempted.
    expect(vi.mocked(api.patchImportSession)).not.toHaveBeenCalled()
  })
})
