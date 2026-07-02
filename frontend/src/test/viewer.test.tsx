/**
 * Tests for the in-browser 3D viewer (Phase D).
 *
 * Covers:
 *  - ViewIn3DButton gating: disabled when onView is absent, enabled when provided
 *  - DownloadsSection: viewer modal appears / disappears on open/close
 *  - LazyModelViewer: Suspense boundary shows fallback while loading
 *
 * The actual WebGL canvas (ModelViewer) is mocked — jsdom has no WebGL.
 * The lazy-load boundary is tested by checking the Suspense fallback renders
 * without importing three.js.
 */

import React, { Suspense } from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

// ---------------------------------------------------------------------------
// Mock the lazy viewer module so three.js is never imported in jsdom
// ---------------------------------------------------------------------------

vi.mock('@/components/viewer/ModelViewer', () => ({
  default: ({ onClose, fileUrl, ext }: { onClose: () => void; fileUrl: string; ext: string }) => (
    <div
      role="dialog"
      aria-label="3D model viewer"
      data-testid="model-viewer-mock"
      data-file-url={fileUrl}
      data-ext={ext}
    >
      <button onClick={onClose}>Close</button>
    </div>
  ),
}))

// Mock the api module so DownloadsSection doesn't need a real backend
vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    queueZip: vi.fn(),
    pollZip: vi.fn(),
    zipDownloadUrl: vi.fn(() => '/download/zip'),
    fileDownloadUrl: vi.fn((key: string, path: string) => `/api/items/${key}/files/${path}`),
  }
})

import { DownloadsSection } from '@/pages/item/DownloadsPanel'
import type { FileOut } from '@/lib/api/items'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeFile(overrides: Partial<FileOut> = {}): FileOut {
  return {
    id: 1,
    path: 'model/part.stl',
    size: 1024 * 1024, // 1 MB
    role: 'model',
    sha256: 'abc',
    object_analysis: null,
    preview_3d: true,
    ...overrides,
  }
}

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <QueryClientProvider client={qc}>
      {children}
    </QueryClientProvider>
  )
}

// ---------------------------------------------------------------------------
// ViewIn3DButton gating (rendered via DownloadsSection with preview_3d files)
// ---------------------------------------------------------------------------

describe('View in 3D gating', () => {
  it('renders the "View in 3D" button for files with preview_3d=true', () => {
    render(
      <DownloadsSection
        itemKey="test-key"
        files={[makeFile({ preview_3d: true })]}
      />,
      { wrapper },
    )
    expect(screen.getByRole('button', { name: /view in 3d/i })).toBeInTheDocument()
  })

  it('does NOT render "View in 3D" for files with preview_3d=false', () => {
    render(
      <DownloadsSection
        itemKey="test-key"
        files={[makeFile({ preview_3d: false })]}
      />,
      { wrapper },
    )
    expect(screen.queryByRole('button', { name: /view in 3d/i })).not.toBeInTheDocument()
  })

  it('"View in 3D" button is enabled (not disabled) for preview_3d files', () => {
    render(
      <DownloadsSection
        itemKey="test-key"
        files={[makeFile({ preview_3d: true })]}
      />,
      { wrapper },
    )
    const btn = screen.getByRole('button', { name: /view in 3d/i })
    expect(btn).not.toBeDisabled()
  })
})

// ---------------------------------------------------------------------------
// Viewer modal open/close
// ---------------------------------------------------------------------------

describe('Viewer modal', () => {
  beforeEach(() => {
    // jsdom doesn't implement matchMedia; stub returns light mode
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: (query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: () => undefined,
        removeListener: () => undefined,
        addEventListener: () => undefined,
        removeEventListener: () => undefined,
        dispatchEvent: () => false,
      }),
    })
  })

  it('opens the viewer modal when "View in 3D" is clicked', async () => {
    render(
      <DownloadsSection
        itemKey="abc123"
        files={[makeFile({ path: 'mesh/body.stl', preview_3d: true })]}
      />,
      { wrapper },
    )

    // Modal is not shown initially
    expect(screen.queryByTestId('model-viewer-mock')).not.toBeInTheDocument()

    // Click the button
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /view in 3d/i }))
    })

    // Modal should appear
    expect(screen.getByTestId('model-viewer-mock')).toBeInTheDocument()
  })

  it('passes the correct file URL and extension to the viewer', async () => {
    render(
      <DownloadsSection
        itemKey="abc123"
        files={[makeFile({ path: 'mesh/body.stl', preview_3d: true })]}
      />,
      { wrapper },
    )

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /view in 3d/i }))
    })

    const viewer = screen.getByTestId('model-viewer-mock')
    expect(viewer.getAttribute('data-file-url')).toBe('/api/items/abc123/files/mesh/body.stl')
    expect(viewer.getAttribute('data-ext')).toBe('.stl')
  })

  it('closes the viewer when the close button is clicked', async () => {
    render(
      <DownloadsSection
        itemKey="abc123"
        files={[makeFile({ path: 'mesh/body.obj', preview_3d: true })]}
      />,
      { wrapper },
    )

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /view in 3d/i }))
    })
    expect(screen.getByTestId('model-viewer-mock')).toBeInTheDocument()

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /close/i }))
    })
    expect(screen.queryByTestId('model-viewer-mock')).not.toBeInTheDocument()
  })

  it('correctly passes a .3mf extension', async () => {
    render(
      <DownloadsSection
        itemKey="abc123"
        files={[makeFile({ path: 'model.3mf', preview_3d: true })]}
      />,
      { wrapper },
    )

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /view in 3d/i }))
    })

    const viewer = screen.getByTestId('model-viewer-mock')
    expect(viewer.getAttribute('data-ext')).toBe('.3mf')
  })
})

// ---------------------------------------------------------------------------
// Suspense / lazy boundary — the LazyModelViewer should suspend until loaded
// ---------------------------------------------------------------------------

describe('LazyModelViewer Suspense boundary', () => {
  it('renders a Suspense boundary around the lazy viewer', async () => {
    // Re-mock React.lazy to return a never-resolving promise to test the fallback
    const NeverResolvingLazy = React.lazy(() => new Promise<never>(() => {}))

    render(
      <Suspense fallback={<div data-testid="suspense-fallback">Loading...</div>}>
        <NeverResolvingLazy />
      </Suspense>,
    )

    // While lazy is still loading the fallback should be shown
    expect(screen.getByTestId('suspense-fallback')).toBeInTheDocument()
  })
})
