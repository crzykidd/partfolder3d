/**
 * Tests for pages/item/ThreeMfPanel — collapsed/expanded rendering.
 *
 * Covers:
 *  - formatDuration helper (seconds → "Xh Ym" / "Ym")
 *  - Collapsed state: shows filename, Sliced/Unsliced badge, summary stats
 *  - Expanded state (sliced): filament rows, plate breakdown, object list
 *  - Expanded state (unsliced): volume-estimate warning, objects list
 *  - Per-file embedded thumbnail shown when analysis.thumbnail_path is set
 */

import React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

import { ThreeMfPanel, formatDuration } from '@/pages/item/ThreeMfPanel'
import type { FileObjectAnalysis } from '@/lib/api/items'

// Mock the api module so fileDownloadUrl is deterministic in tests
vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    fileDownloadUrl: (key: string, path: string) => `/api/items/${key}/files/${path}`,
  }
})

// ---------------------------------------------------------------------------
// formatDuration
// ---------------------------------------------------------------------------

describe('formatDuration', () => {
  it('formats sub-hour durations as "Ym"', () => {
    expect(formatDuration(0)).toBe('0m')
    expect(formatDuration(60)).toBe('1m')
    expect(formatDuration(2700)).toBe('45m')
    expect(formatDuration(3599)).toBe('59m')
  })

  it('formats hour+ durations as "Xh Ym"', () => {
    expect(formatDuration(3600)).toBe('1h 0m')
    expect(formatDuration(5400)).toBe('1h 30m')
    expect(formatDuration(7260)).toBe('2h 1m')
  })
})

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const SLICED_ANALYSIS: FileObjectAnalysis = {
  analyzed_at: '2026-07-01T00:00:00Z',
  source_hash: 'abc123',
  objects: [
    {
      name: 'Filament 1 (PLA)',
      color_count: 1,
      colors: ['#FF0000'],
      volume_cm3: null,
      est_grams: 12.5,
      est_method: 'sliced',
      watertight: null as unknown as boolean,
      low_confidence: false,
      dims_mm: null,
    },
    {
      name: 'Filament 2 (PETG)',
      color_count: 1,
      colors: ['#0000FF'],
      volume_cm3: null,
      est_grams: 8.3,
      est_method: 'sliced',
      watertight: null as unknown as boolean,
      low_confidence: false,
      dims_mm: null,
    },
  ],
  total_objects: 2,
  total_colors: 2,
  total_est_grams: 20.8,
  est_method: 'sliced',
  sliced: true,
  slicer: 'BambuStudio 01.09.00.57',
  printer_model: 'P1S',
  print_time_s: 5400,
  plate_count: 2,
  filament: [
    { slot: 1, type: 'PLA', color_hex: '#FF0000', used_g: 12.5, used_m: 4.2 },
    { slot: 2, type: 'PETG', color_hex: '#0000FF', used_g: 8.3, used_m: 2.8 },
  ],
  plates: [
    { index: 1, print_time_s: 3000, weight_g: 15.0 },
    { index: 2, print_time_s: 2400, weight_g: 5.8 },
  ],
}

const UNSLICED_ANALYSIS: FileObjectAnalysis = {
  analyzed_at: '2026-07-01T00:00:00Z',
  source_hash: 'def456',
  objects: [
    {
      name: 'body',
      color_count: 1,
      colors: [],
      volume_cm3: 10.5,
      est_grams: 13.0,
      est_method: 'volume',
      watertight: true,
      low_confidence: false,
      dims_mm: [50, 30, 20],
    },
  ],
  total_objects: 1,
  total_colors: 1,
  total_est_grams: 13.0,
  est_method: 'volume',
  sliced: false,
}

// ---------------------------------------------------------------------------
// Collapsed rendering
// ---------------------------------------------------------------------------

describe('ThreeMfPanel — collapsed (default)', () => {
  it('shows the filename in the collapsed header', () => {
    render(
      <ThreeMfPanel
        fileName="model.3mf"
        analysis={SLICED_ANALYSIS}
        itemKey="testkey"
      />,
    )
    expect(screen.getByText('model.3mf')).toBeInTheDocument()
  })

  it('shows "Sliced" badge for sliced analysis', () => {
    render(
      <ThreeMfPanel
        fileName="model.3mf"
        analysis={SLICED_ANALYSIS}
        itemKey="testkey"
      />,
    )
    expect(screen.getByText('Sliced')).toBeInTheDocument()
  })

  it('shows "Unsliced" badge for unsliced analysis', () => {
    render(
      <ThreeMfPanel
        fileName="unsliced.3mf"
        analysis={UNSLICED_ANALYSIS}
        itemKey="testkey"
      />,
    )
    expect(screen.getByText('Unsliced')).toBeInTheDocument()
  })

  it('shows formatted print time for sliced analysis', () => {
    render(
      <ThreeMfPanel
        fileName="model.3mf"
        analysis={SLICED_ANALYSIS}
        itemKey="testkey"
      />,
    )
    expect(screen.getByText('1h 30m')).toBeInTheDocument()
  })

  it('shows total filament weight', () => {
    render(
      <ThreeMfPanel
        fileName="model.3mf"
        analysis={SLICED_ANALYSIS}
        itemKey="testkey"
      />,
    )
    expect(screen.getByText('20.8g')).toBeInTheDocument()
  })

  it('does not show expanded detail when collapsed', () => {
    render(
      <ThreeMfPanel
        fileName="model.3mf"
        analysis={SLICED_ANALYSIS}
        itemKey="testkey"
      />,
    )
    // Filament table not visible in collapsed state
    expect(screen.queryByText('Filaments')).not.toBeInTheDocument()
    expect(screen.queryByText('Plates')).not.toBeInTheDocument()
  })

  it('shows per-file thumbnail when analysis.thumbnail_path is set', () => {
    const analysisWithThumb: FileObjectAnalysis = {
      ...SLICED_ANALYSIS,
      thumbnail_path: 'thumbs/embedded/abc.png',
    }
    render(
      <ThreeMfPanel
        fileName="model.3mf"
        analysis={analysisWithThumb}
        itemKey="testkey"
      />,
    )
    const img = screen.getByAltText('3MF thumbnail') as HTMLImageElement
    expect(img).toBeInTheDocument()
    expect(img.src).toContain('thumbs/embedded/abc.png')
  })

  it('does not show thumbnail when analysis.thumbnail_path is absent', () => {
    render(
      <ThreeMfPanel
        fileName="model.3mf"
        analysis={SLICED_ANALYSIS}
        itemKey="testkey"
      />,
    )
    expect(screen.queryByAltText('3MF thumbnail')).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Expanded rendering — sliced
// ---------------------------------------------------------------------------

describe('ThreeMfPanel — expanded (sliced)', () => {
  function renderExpanded() {
    render(
      <ThreeMfPanel
        fileName="model.3mf"
        analysis={SLICED_ANALYSIS}
        itemKey="testkey"
        defaultExpanded
      />,
    )
  }

  it('shows filament section header', () => {
    renderExpanded()
    expect(screen.getByText('Filaments')).toBeInTheDocument()
  })

  it('shows filament type labels', () => {
    renderExpanded()
    expect(screen.getByText('PLA')).toBeInTheDocument()
    expect(screen.getByText('PETG')).toBeInTheDocument()
  })

  it('shows plate section header', () => {
    renderExpanded()
    expect(screen.getByText('Plates')).toBeInTheDocument()
  })

  it('shows individual plates', () => {
    renderExpanded()
    expect(screen.getByText('Plate 1')).toBeInTheDocument()
    expect(screen.getByText('Plate 2')).toBeInTheDocument()
  })

  it('shows slicer metadata', () => {
    renderExpanded()
    expect(screen.getByText(/BambuStudio/)).toBeInTheDocument()
    expect(screen.getByText(/P1S/)).toBeInTheDocument()
  })

  it('shows "Real slicer data" badge', () => {
    renderExpanded()
    expect(screen.getByText('Real slicer data')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Expanded rendering — unsliced
// ---------------------------------------------------------------------------

describe('ThreeMfPanel — expanded (unsliced)', () => {
  function renderExpanded() {
    render(
      <ThreeMfPanel
        fileName="unsliced.3mf"
        analysis={UNSLICED_ANALYSIS}
        itemKey="testkey"
        defaultExpanded
      />,
    )
  }

  it('shows volume-estimate warning', () => {
    renderExpanded()
    expect(screen.getByText(/Volume estimate/)).toBeInTheDocument()
  })

  it('shows objects section header', () => {
    renderExpanded()
    expect(screen.getByText('Objects')).toBeInTheDocument()
  })

  it('shows object name and dimensions', () => {
    renderExpanded()
    expect(screen.getByText('body')).toBeInTheDocument()
    expect(screen.getByText('50×30×20 mm')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Toggle behaviour
// ---------------------------------------------------------------------------

describe('ThreeMfPanel — expand/collapse toggle', () => {
  it('expands when the summary row is clicked', () => {
    render(
      <ThreeMfPanel
        fileName="model.3mf"
        analysis={SLICED_ANALYSIS}
        itemKey="testkey"
      />,
    )
    // Initially collapsed
    expect(screen.queryByText('Filaments')).not.toBeInTheDocument()

    // Click the summary button
    fireEvent.click(screen.getByRole('button', { name: /model\.3mf/i }))

    // Now expanded
    expect(screen.getByText('Filaments')).toBeInTheDocument()
  })

  it('collapses again when clicked a second time', () => {
    render(
      <ThreeMfPanel
        fileName="model.3mf"
        analysis={SLICED_ANALYSIS}
        itemKey="testkey"
        defaultExpanded
      />,
    )
    // Initially expanded
    expect(screen.getByText('Filaments')).toBeInTheDocument()

    // Click to collapse
    fireEvent.click(screen.getByRole('button', { name: /model\.3mf/i }))

    // Collapsed
    expect(screen.queryByText('Filaments')).not.toBeInTheDocument()
  })
})
