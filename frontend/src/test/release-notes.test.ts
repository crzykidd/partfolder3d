/**
 * Tests for the release-notes popup feature.
 *
 * Covers:
 *  - compareSemver: numeric semver comparison (not lexicographic)
 *  - Show-once logic: modal shows when lastSeen < current, not when equal
 *  - Not-on-first-use: no modal when lastSeen was never stored
 *  - dismiss(): persists current version so modal won't re-appear
 *  - Pre-release suffix stripping
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'

import { compareSemver, getReleaseNote, RELEASE_NOTES } from '@/lib/releaseNotes'
import { useReleaseNotesPopup } from '@/hooks/useReleaseNotesPopup'

// ---------------------------------------------------------------------------
// compareSemver — pure function, no mocks needed
// ---------------------------------------------------------------------------

describe('compareSemver', () => {
  it('returns 0 for equal versions', () => {
    expect(compareSemver('1.2.3', '1.2.3')).toBe(0)
    expect(compareSemver('0.0.0', '0.0.0')).toBe(0)
  })

  it('returns positive when a is newer (patch)', () => {
    expect(compareSemver('1.2.4', '1.2.3')).toBeGreaterThan(0)
  })

  it('returns negative when a is older (patch)', () => {
    expect(compareSemver('1.2.2', '1.2.3')).toBeLessThan(0)
  })

  it('compares minor version correctly (numeric, not lexicographic)', () => {
    // Lexicographic: "10" < "9"; numeric: 10 > 9
    expect(compareSemver('1.10.0', '1.9.0')).toBeGreaterThan(0)
    expect(compareSemver('0.10.0', '0.9.0')).toBeGreaterThan(0)
  })

  it('compares major version correctly', () => {
    expect(compareSemver('2.0.0', '1.9.9')).toBeGreaterThan(0)
    expect(compareSemver('1.0.0', '2.0.0')).toBeLessThan(0)
  })

  it('strips pre-release suffixes before comparing', () => {
    expect(compareSemver('1.2.3-alpha', '1.2.3')).toBe(0)
    expect(compareSemver('1.2.4-rc1', '1.2.3')).toBeGreaterThan(0)
  })

  it('handles missing patch segment (defaults to 0)', () => {
    expect(compareSemver('1.2', '1.2.0')).toBe(0)
    expect(compareSemver('1.3', '1.2.9')).toBeGreaterThan(0)
  })

  it('key upgrade scenario: 0.2.5 → 0.3.0', () => {
    expect(compareSemver('0.3.0', '0.2.5')).toBeGreaterThan(0)
    expect(compareSemver('0.2.5', '0.3.0')).toBeLessThan(0)
  })
})

// ---------------------------------------------------------------------------
// getReleaseNote
// ---------------------------------------------------------------------------

describe('getReleaseNote', () => {
  it('returns null for unknown versions', () => {
    expect(getReleaseNote('99.99.99')).toBeNull()
    expect(getReleaseNote('')).toBeNull()
  })

  it('returns a note for every key in RELEASE_NOTES', () => {
    for (const version of Object.keys(RELEASE_NOTES)) {
      const note = getReleaseNote(version)
      expect(note).not.toBeNull()
      expect(note?.bullets.length).toBeGreaterThan(0)
      expect(note?.githubReleaseUrl).toMatch(/^https:\/\//)
    }
  })
})

// ---------------------------------------------------------------------------
// useReleaseNotesPopup — hook logic
// ---------------------------------------------------------------------------

// Wrapper providing QueryClient
function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(QueryClientProvider, { client: qc }, children)
  }
}

function mockVersionFetch(version: string) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ version }),
    }),
  )
}

describe('useReleaseNotesPopup', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('does NOT show modal on first-ever use (no lastSeen stored)', async () => {
    mockVersionFetch('0.3.0')

    const { result } = renderHook(() => useReleaseNotesPopup(), {
      wrapper: makeWrapper(),
    })

    // Wait for version to load
    await waitFor(() => expect(result.current.currentVersion).toBe('0.3.0'))

    // shouldShow is false on first use
    expect(result.current.shouldShow).toBe(false)
  })

  it('records current version in localStorage on first use (so future upgrades can compare)', async () => {
    mockVersionFetch('0.3.0')

    const { result } = renderHook(() => useReleaseNotesPopup(), {
      wrapper: makeWrapper(),
    })

    await waitFor(() => expect(result.current.currentVersion).toBe('0.3.0'))

    // After first load, seen-version should be written to localStorage
    const stored = localStorage.getItem('partfolder3d-seen-version')
    expect(stored).toBe(JSON.stringify('0.3.0'))
  })

  it('shows modal when seen-version is set and current version is newer', async () => {
    // Simulate a user who last saw 0.2.5, now running 0.3.0
    localStorage.setItem('partfolder3d-seen-version', JSON.stringify('0.2.5'))
    mockVersionFetch('0.3.0')

    const { result } = renderHook(() => useReleaseNotesPopup(), {
      wrapper: makeWrapper(),
    })

    await waitFor(() => expect(result.current.shouldShow).toBe(true))
    expect(result.current.currentVersion).toBe('0.3.0')
  })

  it('does NOT show modal when seen-version matches current version', async () => {
    localStorage.setItem('partfolder3d-seen-version', JSON.stringify('0.3.0'))
    mockVersionFetch('0.3.0')

    const { result } = renderHook(() => useReleaseNotesPopup(), {
      wrapper: makeWrapper(),
    })

    await waitFor(() => expect(result.current.currentVersion).toBe('0.3.0'))
    expect(result.current.shouldShow).toBe(false)
  })

  it('dismiss() persists current version to localStorage', async () => {
    localStorage.setItem('partfolder3d-seen-version', JSON.stringify('0.2.5'))
    mockVersionFetch('0.3.0')

    const { result } = renderHook(() => useReleaseNotesPopup(), {
      wrapper: makeWrapper(),
    })

    await waitFor(() => expect(result.current.shouldShow).toBe(true))

    act(() => {
      result.current.dismiss()
    })

    const stored = localStorage.getItem('partfolder3d-seen-version')
    expect(stored).toBe(JSON.stringify('0.3.0'))
  })

  it('shouldShow becomes false after dismiss()', async () => {
    localStorage.setItem('partfolder3d-seen-version', JSON.stringify('0.2.5'))
    mockVersionFetch('0.3.0')

    const { result } = renderHook(() => useReleaseNotesPopup(), {
      wrapper: makeWrapper(),
    })

    await waitFor(() => expect(result.current.shouldShow).toBe(true))

    act(() => {
      result.current.dismiss()
    })

    await waitFor(() => expect(result.current.shouldShow).toBe(false))
  })
})
