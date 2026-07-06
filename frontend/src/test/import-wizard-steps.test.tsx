/**
 * Component-level tests for two import-wizard steps (GitHub #27, steps 3 & 5).
 *
 * Covers:
 *  - TagsStep renders existing catalog tags (GET /api/tags) immediately, even
 *    when the AI provider is unavailable — the existing-tags query is decoupled
 *    from the AI suggest-tags call so a slow/unconfigured AI can't stall the step.
 *  - SummaryStep surfaces a zero-file commit: the Files row shows "0 file(s)"
 *    with a metadata-only warning note.
 *  - SummaryStep mid-wizard file attach UI (#27 fix): staged file list renders,
 *    attach calls uploadSessionFiles and refetches, remove calls deleteSessionFile,
 *    url sessions get a source-site-specific zero-file warning.
 *  - SummaryStep attach-or-create modal: shown once per wizard visit for url+0-file
 *    sessions; dismissed via sessionStorage; "Attach files" closes modal; "Create
 *    without objects" triggers the same commit handler as the main button.
 *
 * Hermetic: the @/lib/api module is mocked — no real network is touched.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { TagsStep } from '@/pages/import-wizard/TagsStep'
import { SummaryStep } from '@/pages/import-wizard/SummaryStep'
import type { ImportSession } from '@/lib/api'

// ---------------------------------------------------------------------------
// Module-level api mock
// ---------------------------------------------------------------------------

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api')
  return {
    ...actual,
    getAiStatus: vi.fn(),
    aiSuggestTags: vi.fn(),
    listTags: vi.fn(),
    listLibraries: vi.fn(),
    uploadSessionFiles: vi.fn(),
    deleteSessionFile: vi.fn(),
    commitImportSession: vi.fn(),
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
    source_url: 'https://example.com/model',
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

function renderWithProviders(ui: React.ReactElement) {
  return render(
    <QueryClientProvider client={makeQC()}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('TagsStep — existing tags decoupled from AI (#27 step 3)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // AI provider unavailable: the step must still be fully usable.
    vi.mocked(api.getAiStatus).mockResolvedValue({ provider_available: false })
  })

  it('renders existing catalog tags even when the AI provider is unavailable', async () => {
    vi.mocked(api.listTags).mockResolvedValue({
      total: 2,
      page: 1,
      per_page: 24,
      tags: [
        { id: 1, name: 'gridfinity', category: null, popularity_count: 9, item_count: 9 },
        { id: 2, name: 'organizer', category: null, popularity_count: 5, item_count: 5 },
      ],
    })

    renderWithProviders(
      <TagsStep session={makeSession()} onNext={() => {}} onPrev={() => {}} />,
    )

    // Existing catalog tags render from the independent listTags query.
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /gridfinity/ })).toBeInTheDocument()
    })
    expect(screen.getByRole('button', { name: /organizer/ })).toBeInTheDocument()

    // AI suggest-tags is never invoked when the provider is unavailable.
    expect(vi.mocked(api.aiSuggestTags)).not.toHaveBeenCalled()
  })
})

describe('SummaryStep — Files row surfaces zero-file commit (#27 step 5)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Dismiss modal for all url sessions in this suite so tests focus on the inline row.
    sessionStorage.setItem('pf3d-attach-modal-dismissed-sess-1', '1')
    vi.mocked(api.listLibraries).mockResolvedValue([])
  })

  it('shows url-specific zero-file warning for url sessions with no files', async () => {
    renderWithProviders(
      <SummaryStep
        session={makeSession({ files: [], source_type: 'url' })}
        onPrev={() => {}}
        onCancelled={() => {}}
      />,
    )

    await waitFor(() => {
      expect(screen.getByText('Files')).toBeInTheDocument()
    })
    expect(screen.getByText('0 file(s)')).toBeInTheDocument()
    expect(
      screen.getByText(
        'No model files attached — attach the file you downloaded from the source site, or commit metadata-only.',
      ),
    ).toBeInTheDocument()
  })

  it('shows generic zero-file warning for upload sessions with no files', async () => {
    renderWithProviders(
      <SummaryStep
        session={makeSession({ files: [], source_type: 'upload' })}
        onPrev={() => {}}
        onCancelled={() => {}}
      />,
    )

    await waitFor(() => {
      expect(screen.getByText('Files')).toBeInTheDocument()
    })
    expect(screen.getByText('0 file(s)')).toBeInTheDocument()
    expect(
      screen.getByText('No model file attached — this will be a metadata-only entry.'),
    ).toBeInTheDocument()
  })

  it('shows the file count without a warning note when a file is attached', async () => {
    renderWithProviders(
      <SummaryStep
        session={makeSession({
          files: [
            { id: 1, staged_path: '/x/a.stl', original_name: 'a.stl', role: 'model', size: 123 },
          ],
        })}
        onPrev={() => {}}
        onCancelled={() => {}}
      />,
    )

    await waitFor(() => {
      expect(screen.getByText('1 file(s)')).toBeInTheDocument()
    })
    expect(
      screen.queryByText('No model file attached — this will be a metadata-only entry.'),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByText(
        'No model files attached — attach the file you downloaded from the source site, or commit metadata-only.',
      ),
    ).not.toBeInTheDocument()
  })
})

describe('SummaryStep — mid-wizard file attach UI (#27 fix)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Dismiss modal so these tests focus on the inline attach section.
    sessionStorage.setItem('pf3d-attach-modal-dismissed-sess-1', '1')
    vi.mocked(api.listLibraries).mockResolvedValue([])
  })

  it('renders the "Attach files" affordance for url sessions', async () => {
    renderWithProviders(
      <SummaryStep
        session={makeSession({ source_type: 'url', files: [] })}
        onPrev={() => {}}
        onCancelled={() => {}}
      />,
    )

    await waitFor(() => {
      expect(screen.getByText('Attach Model Files')).toBeInTheDocument()
    })
    // The inline button text is '+ Attach files' — distinct from the modal's 'Attach files'.
    expect(screen.getByRole('button', { name: '+ Attach files' })).toBeInTheDocument()
  })

  it('renders the "Attach files" affordance for upload sessions', async () => {
    renderWithProviders(
      <SummaryStep
        session={makeSession({ source_type: 'upload', files: [] })}
        onPrev={() => {}}
        onCancelled={() => {}}
      />,
    )

    await waitFor(() => {
      expect(screen.getByText('Attach Model Files')).toBeInTheDocument()
    })
  })

  it('renders staged file names and roles in the attach section', async () => {
    renderWithProviders(
      <SummaryStep
        session={makeSession({
          source_type: 'url',
          files: [
            { id: 1, staged_path: '/s/a.stl', original_name: 'a.stl', role: 'model', size: 42 },
            { id: 2, staged_path: '/s/b.zip', original_name: 'b.zip', role: 'zip', size: 100 },
          ],
        })}
        onPrev={() => {}}
        onCancelled={() => {}}
      />,
    )

    await waitFor(() => {
      expect(screen.getByText('a.stl')).toBeInTheDocument()
    })
    expect(screen.getByText('b.zip')).toBeInTheDocument()
    // Role labels are shown
    expect(screen.getByText('model')).toBeInTheDocument()
    expect(screen.getByText('zip')).toBeInTheDocument()
  })

  it('calls deleteSessionFile when the remove button is clicked', async () => {
    const updatedSession = makeSession({ source_type: 'url', files: [] })
    vi.mocked(api.deleteSessionFile).mockResolvedValue(updatedSession)

    renderWithProviders(
      <SummaryStep
        session={makeSession({
          source_type: 'url',
          files: [
            { id: 7, staged_path: '/s/x.stl', original_name: 'x.stl', role: 'model', size: 10 },
          ],
        })}
        onPrev={() => {}}
        onCancelled={() => {}}
      />,
    )

    await waitFor(() => {
      expect(screen.getByText('x.stl')).toBeInTheDocument()
    })

    // Click the remove button (✕)
    const removeBtn = screen.getByRole('button', { name: /remove file/i })
    fireEvent.click(removeBtn)

    await waitFor(() => {
      expect(vi.mocked(api.deleteSessionFile)).toHaveBeenCalledWith('sess-1', 7)
    })
  })

  it('calls uploadSessionFiles when files are selected', async () => {
    const updatedSession = makeSession({
      source_type: 'url',
      files: [{ id: 5, staged_path: '/s/new.stl', original_name: 'new.stl', role: 'model', size: 99 }],
    })
    vi.mocked(api.uploadSessionFiles).mockResolvedValue(updatedSession)

    renderWithProviders(
      <SummaryStep
        session={makeSession({ source_type: 'url', files: [] })}
        onPrev={() => {}}
        onCancelled={() => {}}
      />,
    )

    await waitFor(() => {
      expect(screen.getByText('Attach Model Files')).toBeInTheDocument()
    })

    // Simulate file selection on the hidden input
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    expect(fileInput).not.toBeNull()

    const testFile = new File(['stl data'], 'new.stl', { type: 'application/octet-stream' })
    Object.defineProperty(fileInput, 'files', { value: [testFile], configurable: true })
    fireEvent.change(fileInput)

    await waitFor(() => {
      expect(vi.mocked(api.uploadSessionFiles)).toHaveBeenCalledWith('sess-1', [testFile])
    })
  })

  it('does not show the attach affordance for inbox sessions', async () => {
    renderWithProviders(
      <SummaryStep
        session={makeSession({ source_type: 'inbox', files: [] })}
        onPrev={() => {}}
        onCancelled={() => {}}
      />,
    )

    // Wait for the component to stabilize (library query)
    await waitFor(() => {
      expect(screen.getByText('Files')).toBeInTheDocument()
    })
    expect(screen.queryByText('Attach Model Files')).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Modal tests — attach-or-create modal for url+0-file sessions
// ---------------------------------------------------------------------------

describe('SummaryStep — attach-or-create modal for url+0-file sessions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Clear sessionStorage so prior dismissals don't leak between tests.
    sessionStorage.clear()
    vi.mocked(api.listLibraries).mockResolvedValue([])
    vi.mocked(api.commitImportSession).mockResolvedValue({
      item_key: 'test-key',
      item_id: 1,
      session_id: 'sess-1',
    })
  })

  it('shows the modal for url sessions with 0 files, with the domain in the copy', async () => {
    renderWithProviders(
      <SummaryStep
        session={makeSession({
          source_type: 'url',
          files: [],
          source_url: 'https://www.makerworld.com/thing/123',
        })}
        onPrev={() => {}}
        onCancelled={() => {}}
      />,
    )

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })
    expect(screen.getByText('No model files attached')).toBeInTheDocument()
    // Domain with www. stripped
    expect(
      screen.getByText(/Site "makerworld\.com" needs auth to download print assets/),
    ).toBeInTheDocument()
  })

  it('shows generic copy when the session has no source_url', async () => {
    renderWithProviders(
      <SummaryStep
        session={makeSession({ source_type: 'url', files: [], source_url: null })}
        onPrev={() => {}}
        onCancelled={() => {}}
      />,
    )

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })
    expect(
      screen.getByText('This import has no model files attached.'),
    ).toBeInTheDocument()
  })

  it('does not show the modal for upload sessions', async () => {
    renderWithProviders(
      <SummaryStep
        session={makeSession({ source_type: 'upload', files: [] })}
        onPrev={() => {}}
        onCancelled={() => {}}
      />,
    )

    await waitFor(() => {
      expect(screen.getByText('Files')).toBeInTheDocument()
    })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('does not show the modal when files are already attached', async () => {
    renderWithProviders(
      <SummaryStep
        session={makeSession({
          source_type: 'url',
          files: [
            { id: 1, staged_path: '/s/a.stl', original_name: 'a.stl', role: 'model', size: 42 },
          ],
        })}
        onPrev={() => {}}
        onCancelled={() => {}}
      />,
    )

    await waitFor(() => {
      expect(screen.getByText('1 file(s)')).toBeInTheDocument()
    })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('"Attach files" button closes the modal', async () => {
    renderWithProviders(
      <SummaryStep
        session={makeSession({ source_type: 'url', files: [] })}
        onPrev={() => {}}
        onCancelled={() => {}}
      />,
    )

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Attach files' }))

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })
  })

  it('"Create without objects" calls the same commit handler as the main button', async () => {
    renderWithProviders(
      <SummaryStep
        session={makeSession({ source_type: 'url', files: [], library_id: 1 })}
        onPrev={() => {}}
        onCancelled={() => {}}
      />,
    )

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /create without objects/i }))

    await waitFor(() => {
      expect(vi.mocked(api.commitImportSession)).toHaveBeenCalledWith('sess-1')
    })
  })

  it('"Create without objects" is disabled when no library is set', async () => {
    renderWithProviders(
      <SummaryStep
        session={makeSession({ source_type: 'url', files: [], library_id: null })}
        onPrev={() => {}}
        onCancelled={() => {}}
      />,
    )

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })

    const createBtn = screen.getByRole('button', { name: /create without objects/i })
    expect(createBtn).toBeDisabled()
  })

  it('clicking outside the modal dismisses it', async () => {
    renderWithProviders(
      <SummaryStep
        session={makeSession({ source_type: 'url', files: [] })}
        onPrev={() => {}}
        onCancelled={() => {}}
      />,
    )

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })

    // The backdrop is the dialog's parent — click it (not the dialog itself)
    const backdrop = screen.getByRole('dialog').parentElement!
    fireEvent.click(backdrop)

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })
  })

  it('dismissed modal does not re-show when the step re-mounts (sessionStorage)', async () => {
    // Simulate a previously dismissed modal by setting the key before mount.
    sessionStorage.setItem('pf3d-attach-modal-dismissed-sess-1', '1')

    renderWithProviders(
      <SummaryStep
        session={makeSession({ source_type: 'url', files: [] })}
        onPrev={() => {}}
        onCancelled={() => {}}
      />,
    )

    await waitFor(() => {
      expect(screen.getByText('Files')).toBeInTheDocument()
    })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
