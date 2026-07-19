/**
 * Component tests for the ImagesStep "Try to render file" viewport capture (#26).
 *
 * Covers:
 *  - The control is shown only when the session has ≥1 browser-renderable staged
 *    model file (.stl/.obj/.3mf), and hidden otherwise (e.g. URL imports).
 *  - Clicking capture in the viewer uploads the blob via uploadSessionImage.
 *
 * HONEST LIMITATION: the real WebGL `canvas.toBlob` capture cannot run under
 * jsdom (no WebGL context) — the same boundary as #21.  ModelViewer is mocked
 * with a stub that invokes `onCapture(blob)` so we can test the wiring
 * (visibility gating, file selection, upload-on-capture) around a mocked blob;
 * the actual pixel-capture path is intentionally NOT exercised here.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { ImagesStep } from '@/pages/import-wizard/ImagesStep'
import type { ImportSession, ImportSessionFile } from '@/lib/api'

// Mock the api module — no real network.
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api')
  return {
    ...actual,
    uploadSessionImage: vi.fn(),
    uploadSessionFiles: vi.fn(),
    patchImportSession: vi.fn(),
    deleteImportSessionImage: vi.fn(),
  }
})

// Mock the WebGL viewer: render a "Capture" button that fires onCapture(blob).
vi.mock('@/components/viewer/ModelViewer', () => ({
  default: ({ onCapture }: { onCapture?: (b: Blob) => void }) => (
    <button
      type="button"
      onClick={() => onCapture?.(new Blob(['x'], { type: 'image/png' }))}
    >
      mock-capture
    </button>
  ),
}))

import * as api from '@/lib/api'

function makeFile(overrides: Partial<ImportSessionFile>): ImportSessionFile {
  return {
    id: 1,
    staged_path: '/staging/x',
    original_name: 'model.stl',
    role: 'model',
    size: 100,
    selected: true,
    ...overrides,
  }
}

function makeSession(overrides: Partial<ImportSession> = {}): ImportSession {
  return {
    id: 'sess-1',
    status: 'pending_wizard',
    source_type: 'upload',
    source_url: null,
    inbox_folder: null,
    staging_dir: '/staging/sess-1',
    suggested_title: 'Widget',
    confirmed_title: 'Widget',
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

function renderStep(session: ImportSession) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <ImagesStep session={session} onNext={() => {}} onPrev={() => {}} />
    </QueryClientProvider>,
  )
}

describe('ImagesStep — Try to render file (#26)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows the control when a renderable staged model exists', () => {
    renderStep(makeSession({ files: [makeFile({ original_name: 'part.stl' })] }))
    expect(screen.getByText('Try to render file')).toBeTruthy()
  })

  it('hides the control when there are no renderable model files', () => {
    // URL import: no staged files.
    renderStep(makeSession({ source_type: 'url', files: [] }))
    expect(screen.queryByText('Try to render file')).toBeNull()
  })

  it('hides the control when staged files are all non-model (e.g. images)', () => {
    renderStep(makeSession({ files: [makeFile({ original_name: 'photo.jpg', role: 'image' })] }))
    expect(screen.queryByText('Try to render file')).toBeNull()
  })

  it('uploads the captured blob via uploadSessionImage on capture', async () => {
    vi.mocked(api.uploadSessionImage).mockResolvedValue(makeSession())
    renderStep(makeSession({ files: [makeFile({ original_name: 'part.stl' })] }))

    // Single renderable file → clicking opens the viewer directly.
    fireEvent.click(screen.getByText('Try to render file'))
    fireEvent.click(await screen.findByText('mock-capture'))

    await waitFor(() => {
      expect(vi.mocked(api.uploadSessionImage)).toHaveBeenCalledTimes(1)
    })
    const [sid, file, source] = vi.mocked(api.uploadSessionImage).mock.calls[0]
    expect(sid).toBe('sess-1')
    expect(file).toBeInstanceOf(File)
    expect(source).toBe('captured')
  })
})
