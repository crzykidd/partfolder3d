/**
 * Tests for pages/item/ObjectBreakdown — per-state pending messages.
 *
 * Covers:
 *  - 3MF-only pending files → 3MF message shown (NOT "Analysis pending")
 *  - Mesh pending with a running job → shows progress %
 *  - Mesh pending with a failed job → shows error text
 *  - Mesh pending with no job → "run Rescan disk" message
 *  - Mesh pending with a queued job → "Analysis queued"
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import { ObjectBreakdownSection } from '@/pages/item/ObjectBreakdown'
import type { ItemDetail, FileOut, ItemJobSummary } from '@/lib/api/items'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeFile(overrides: Partial<FileOut> & { path: string }): FileOut {
  return {
    id: Math.floor(Math.random() * 10000),
    role: 'model',
    size: 1024,
    sha256: null,
    object_analysis: null,
    preview_3d: false,
    ...overrides,
  }
}

function makeItem(files: FileOut[]): ItemDetail {
  return {
    id: 1,
    key: 'abc1234',
    title: 'Test Item',
    slug: 'test-item-abc1234',
    library_id: 1,
    dir_path: '/data/items/test',
    created_at: '2026-07-01T00:00:00Z',
    updated_at: '2026-07-01T00:00:00Z',
    description: null,
    source_url: null,
    source_site: null,
    license: null,
    schema_version: 1,
    creator: null,
    tags: [],
    files,
    images: [],
    is_modified: false,
    locally_modified_at: null,
    modified_override: null,
    analysis_total_objects: null,
    analysis_total_colors: null,
    analysis_total_est_grams: null,
  }
}

function makeJob(overrides: Partial<ItemJobSummary> = {}): ItemJobSummary {
  return {
    id: 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
    type: 'analyze_item',
    status: 'running',
    progress: 0,
    error: null,
    created_at: '2026-07-03T00:00:00Z',
    started_at: null,
    finished_at: null,
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Wrapper to provide router context (needed for <Link> in ObjectBreakdown)
// ---------------------------------------------------------------------------

function renderWithRouter(ui: React.ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>)
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ObjectBreakdownSection — 3MF-only pending', () => {
  it('shows 3MF message, not "Analysis pending"', () => {
    const item = makeItem([makeFile({ path: 'model.3mf' })])
    renderWithRouter(<ObjectBreakdownSection item={item} jobs={[]} />)

    // Should NOT say "pending"
    expect(screen.queryByText(/Analysis pending/i)).toBeNull()
    // Should mention 3MF are read, not mesh-analyzed
    expect(screen.getByText(/read, not mesh-analyzed/i)).toBeTruthy()
  })

  it('shows the filename when there is exactly one 3MF', () => {
    const item = makeItem([makeFile({ path: 'parts/arm.3mf' })])
    renderWithRouter(<ObjectBreakdownSection item={item} jobs={[]} />)
    expect(screen.getByText(/parts\/arm\.3mf/i)).toBeTruthy()
  })

  it('shows count when multiple 3MF files are pending', () => {
    const item = makeItem([
      makeFile({ path: 'a.3mf' }),
      makeFile({ path: 'b.3mf' }),
    ])
    renderWithRouter(<ObjectBreakdownSection item={item} jobs={[]} />)
    expect(screen.getByText(/2 \.3mf files are/i)).toBeTruthy()
  })
})

describe('ObjectBreakdownSection — mesh pending with running job', () => {
  it('shows progress percentage', () => {
    const item = makeItem([makeFile({ path: 'model.stl' })])
    const jobs = [makeJob({ status: 'running', progress: 55 })]
    renderWithRouter(<ObjectBreakdownSection item={item} jobs={jobs} />)
    expect(screen.getByText(/Analyzing.*55%/i)).toBeTruthy()
  })

  it('renders a "View in Jobs" link', () => {
    const item = makeItem([makeFile({ path: 'model.stl' })])
    const jobs = [makeJob({ status: 'running', progress: 30 })]
    renderWithRouter(<ObjectBreakdownSection item={item} jobs={jobs} />)
    expect(screen.getByText(/View in Jobs/i)).toBeTruthy()
  })
})

describe('ObjectBreakdownSection — mesh pending with queued job', () => {
  it('shows "Analysis queued"', () => {
    const item = makeItem([makeFile({ path: 'model.obj' })])
    const jobs = [makeJob({ status: 'queued', progress: 0 })]
    renderWithRouter(<ObjectBreakdownSection item={item} jobs={jobs} />)
    expect(screen.getByText(/Analysis queued/i)).toBeTruthy()
  })
})

describe('ObjectBreakdownSection — mesh pending with failed job', () => {
  it('shows the error message', () => {
    const item = makeItem([makeFile({ path: 'model.stl' })])
    const jobs = [makeJob({ status: 'failed', error: 'Trimesh: bad geometry' })]
    renderWithRouter(<ObjectBreakdownSection item={item} jobs={jobs} />)
    expect(screen.getByText(/Analysis failed/i)).toBeTruthy()
    expect(screen.getByText(/Trimesh: bad geometry/i)).toBeTruthy()
  })

  it('shows a "Rescan disk" hint', () => {
    const item = makeItem([makeFile({ path: 'model.ply' })])
    const jobs = [makeJob({ status: 'failed', error: 'error' })]
    renderWithRouter(<ObjectBreakdownSection item={item} jobs={jobs} />)
    expect(screen.getByText(/Rescan disk/i)).toBeTruthy()
  })

  it('renders a "View in Jobs" link', () => {
    const item = makeItem([makeFile({ path: 'model.stl' })])
    const jobs = [makeJob({ status: 'failed', error: 'error' })]
    renderWithRouter(<ObjectBreakdownSection item={item} jobs={jobs} />)
    expect(screen.getByText(/View in Jobs/i)).toBeTruthy()
  })
})

describe('ObjectBreakdownSection — mesh pending with no job', () => {
  it('shows "Analysis hasn\'t run yet" and Rescan hint', () => {
    const item = makeItem([makeFile({ path: 'model.stl' })])
    renderWithRouter(<ObjectBreakdownSection item={item} jobs={[]} />)
    expect(screen.getByText(/hasn.t run yet/i)).toBeTruthy()
    expect(screen.getByText(/Rescan disk/i)).toBeTruthy()
  })

  it('does NOT show "Analysis pending" (old message)', () => {
    const item = makeItem([makeFile({ path: 'model.stl' })])
    renderWithRouter(<ObjectBreakdownSection item={item} jobs={[]} />)
    expect(screen.queryByText(/Analysis pending/i)).toBeNull()
  })
})

describe('ObjectBreakdownSection — mixed 3MF + mesh pending', () => {
  it('shows both the 3MF message and the mesh pending status', () => {
    const item = makeItem([
      makeFile({ path: 'model.3mf' }),
      makeFile({ path: 'support.stl' }),
    ])
    renderWithRouter(<ObjectBreakdownSection item={item} jobs={[]} />)
    expect(screen.getByText(/read, not mesh-analyzed/i)).toBeTruthy()
    // mesh has no job
    expect(screen.getByText(/hasn.t run yet/i)).toBeTruthy()
  })
})
