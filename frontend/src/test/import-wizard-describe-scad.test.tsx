/**
 * Component tests for TitleStep's "Describe from SCAD" AI action
 * (2026-07-25-scad-ai-describe.md).
 *
 * Covers:
 *  - The button renders only when the session has a source/.scad file AND
 *    an AI provider is available (hidden otherwise).
 *  - Clicking it calls aiDescribeScad and renders the result in AiTextPreview;
 *    "Use this" fills the description field.
 *
 * Hermetic: the @/lib/api module is mocked — no real network is touched.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { TitleStep } from '@/pages/import-wizard/TitleStep'
import type { ImportSession } from '@/lib/api'

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api')
  return {
    ...actual,
    getAiStatus: vi.fn(),
    aiDescribeScad: vi.fn(),
    getSiteCapability: vi.fn(),
  }
})

import * as api from '@/lib/api'

function makeSession(overrides: Partial<ImportSession> = {}): ImportSession {
  return {
    id: 'sess-1',
    status: 'pending_wizard',
    source_type: 'upload',
    source_url: null,
    inbox_folder: null,
    staging_dir: null,
    suggested_title: null,
    confirmed_title: 'My Widget',
    description: null,
    license: null,
    source_site: null,
    creator_name: null,
    creator_profile_url: null,
    creator_source_site: null,
    creator_is_own_design: true,
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

function makeScadFile(): ImportSession['files'][number] {
  return {
    id: 1,
    staged_path: '/staging/widget.scad',
    original_name: 'widget.scad',
    role: 'source',
    size: 512,
    selected: true,
  }
}

function renderWithProviders(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('TitleStep — Describe from SCAD', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('hides the button when the session has no .scad/source file, even if AI is available', async () => {
    vi.mocked(api.getAiStatus).mockResolvedValue({ provider_available: true })

    renderWithProviders(<TitleStep session={makeSession({ files: [] })} onNext={() => {}} />)

    await waitFor(() => {
      expect(vi.mocked(api.getAiStatus)).toHaveBeenCalled()
    })
    expect(screen.queryByText('Describe from SCAD')).not.toBeInTheDocument()
  })

  it('hides the button when a .scad file is present but no AI provider is configured', async () => {
    vi.mocked(api.getAiStatus).mockResolvedValue({ provider_available: false })

    renderWithProviders(
      <TitleStep session={makeSession({ files: [makeScadFile()] })} onNext={() => {}} />,
    )

    await waitFor(() => {
      expect(vi.mocked(api.getAiStatus)).toHaveBeenCalled()
    })
    expect(screen.queryByText('Describe from SCAD')).not.toBeInTheDocument()
  })

  it('shows the button when a .scad file is present and AI is available', async () => {
    vi.mocked(api.getAiStatus).mockResolvedValue({ provider_available: true })

    renderWithProviders(
      <TitleStep session={makeSession({ files: [makeScadFile()] })} onNext={() => {}} />,
    )

    expect(await screen.findByText('Describe from SCAD')).toBeInTheDocument()
  })

  it('calls aiDescribeScad and "Use this" fills the description field', async () => {
    vi.mocked(api.getAiStatus).mockResolvedValue({ provider_available: true })
    vi.mocked(api.aiDescribeScad).mockResolvedValue({
      text: 'A clamp that secures a silica gel sock inside a dust hose.',
      provider_available: true,
      error: null,
    })

    renderWithProviders(
      <TitleStep session={makeSession({ files: [makeScadFile()] })} onNext={() => {}} />,
    )

    const button = await screen.findByText('Describe from SCAD')
    fireEvent.click(button)

    await waitFor(() => {
      expect(vi.mocked(api.aiDescribeScad)).toHaveBeenCalledWith(
        'sess-1',
        expect.objectContaining({ title: 'My Widget' }),
      )
    })

    expect(
      await screen.findByText('A clamp that secures a silica gel sock inside a dust hose.'),
    ).toBeInTheDocument()

    fireEvent.click(screen.getByText('Use this'))

    const textarea = screen.getByPlaceholderText('Describe this item…') as HTMLTextAreaElement
    await waitFor(() => {
      expect(textarea.value).toBe('A clamp that secures a silica gel sock inside a dust hose.')
    })
  })
})
