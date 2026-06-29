/**
 * Tests for catalog-utils.ts — pure helper functions.
 *
 * Covers:
 *  - Tag cloud weighting (getTagFontSize, getTagFontWeight)
 *  - Path prefix rewrite (rewritePath) — prefix set vs unset, trailing-slash,
 *    Windows vs Unix styles
 *  - ZIP poll state machine (mapBundleStatus, shouldContinuePolling)
 */

import { describe, it, expect } from 'vitest'
import {
  getTagFontSize,
  getTagFontWeight,
  toPathStyle,
  rewritePath,
  mapBundleStatus,
  shouldContinuePolling,
} from '@/lib/catalog-utils'

// ---------------------------------------------------------------------------
// Tag cloud weighting
// ---------------------------------------------------------------------------

describe('getTagFontSize', () => {
  it('returns 1rem when min === max (all same count)', () => {
    expect(getTagFontSize(5, 5, 5)).toBe('1rem')
  })

  it('returns smallest size for the minimum count', () => {
    const result = getTagFontSize(1, 1, 100)
    expect(result).toBe('0.75rem')
  })

  it('returns largest size for the maximum count', () => {
    const result = getTagFontSize(100, 1, 100)
    expect(result).toBe('2rem')
  })

  it('scales linearly between min and max', () => {
    // With a 0–100 range, count=50 should be roughly in the middle
    const sizeMin = getTagFontSize(0, 0, 100)
    const sizeMid = getTagFontSize(50, 0, 100)
    const sizeMax = getTagFontSize(100, 0, 100)

    const minVal = parseFloat(sizeMin)
    const midVal = parseFloat(sizeMid)
    const maxVal = parseFloat(sizeMax)

    expect(minVal).toBeLessThan(midVal)
    expect(midVal).toBeLessThan(maxVal)
  })

  it('handles count equal to minCount', () => {
    const size = getTagFontSize(10, 10, 50)
    expect(size).toBe('0.75rem')
  })

  it('handles count equal to maxCount', () => {
    const size = getTagFontSize(50, 10, 50)
    expect(size).toBe('2rem')
  })
})

describe('getTagFontWeight', () => {
  it('returns font-normal when min === max', () => {
    expect(getTagFontWeight(5, 5, 5)).toBe('font-normal')
  })

  it('returns font-normal for the minimum count', () => {
    expect(getTagFontWeight(0, 0, 100)).toBe('font-normal')
  })

  it('returns font-bold for the maximum count', () => {
    expect(getTagFontWeight(100, 0, 100)).toBe('font-bold')
  })

  it('returns increasingly heavy weights for higher counts', () => {
    const w10 = getTagFontWeight(10, 0, 100)
    const w50 = getTagFontWeight(50, 0, 100)
    const w80 = getTagFontWeight(80, 0, 100)

    const weights = ['font-normal', 'font-medium', 'font-semibold', 'font-bold']
    expect(weights.indexOf(w80)).toBeGreaterThan(weights.indexOf(w50))
    expect(weights.indexOf(w50)).toBeGreaterThan(weights.indexOf(w10))
  })
})

// ---------------------------------------------------------------------------
// toPathStyle — separator normalisation
// ---------------------------------------------------------------------------

describe('toPathStyle', () => {
  it('converts all forward slashes to backslashes for windows style', () => {
    expect(toPathStyle('/mnt/nas/3dprints/', 'windows')).toBe('\\mnt\\nas\\3dprints\\')
  })

  it('converts all backslashes to forward slashes for posix style', () => {
    expect(toPathStyle('C:\\prints\\Creator\\', 'posix')).toBe('C:/prints/Creator/')
  })

  it('leaves posix path unchanged when already posix style', () => {
    expect(toPathStyle('/mnt/nas/', 'posix')).toBe('/mnt/nas/')
  })

  it('leaves windows path unchanged when already windows style', () => {
    expect(toPathStyle('Z:\\3dprints\\', 'windows')).toBe('Z:\\3dprints\\')
  })

  it('handles empty string', () => {
    expect(toPathStyle('', 'windows')).toBe('')
    expect(toPathStyle('', 'posix')).toBe('')
  })

  it('converts mixed separators to windows style', () => {
    expect(toPathStyle('C:/prints\\sub/', 'windows')).toBe('C:\\prints\\sub\\')
  })

  it('converts mixed separators to posix style', () => {
    expect(toPathStyle('C:/prints\\sub/', 'posix')).toBe('C:/prints/sub/')
  })
})

// ---------------------------------------------------------------------------
// Path prefix rewrite
// ---------------------------------------------------------------------------

describe('rewritePath', () => {
  it('returns raw path when prefix is null', () => {
    expect(rewritePath('/library/ab/my-item-abc123', null)).toBe(
      '/library/ab/my-item-abc123',
    )
  })

  it('returns raw path when prefix is undefined', () => {
    expect(rewritePath('/library/ab/my-item-abc123', undefined)).toBe(
      '/library/ab/my-item-abc123',
    )
  })

  it('returns raw path when prefix is empty string', () => {
    expect(rewritePath('/library/ab/my-item-abc123', '')).toBe(
      '/library/ab/my-item-abc123',
    )
  })

  it('prepends Unix prefix and normalises leading slash', () => {
    const result = rewritePath('/library/ab/my-item-abc123', '/mnt/nas/')
    expect(result).toBe('/mnt/nas/library/ab/my-item-abc123')
  })

  it('adds trailing slash to Unix prefix if missing', () => {
    const result = rewritePath('/library/ab/my-item', '/mnt/nas')
    expect(result).toBe('/mnt/nas/library/ab/my-item')
  })

  it('prepends Windows prefix with backslash conversion', () => {
    const result = rewritePath('/library/ab/my-item-abc123', 'C:\\prints\\')
    expect(result).toBe('C:\\prints\\library\\ab\\my-item-abc123')
  })

  it('adds trailing backslash to Windows prefix if missing', () => {
    const result = rewritePath('/library/ab/my-item', 'C:\\prints')
    expect(result).toBe('C:\\prints\\library\\ab\\my-item')
  })

  it('handles paths without leading slash', () => {
    const result = rewritePath('library/ab/my-item', '/mnt/nas/')
    expect(result).toBe('/mnt/nas/library/ab/my-item')
  })
})

// ---------------------------------------------------------------------------
// ZIP poll state machine
// ---------------------------------------------------------------------------

describe('mapBundleStatus', () => {
  it('maps "pending" to "building"', () => {
    expect(mapBundleStatus('pending')).toBe('building')
  })

  it('maps "ready" to "ready"', () => {
    expect(mapBundleStatus('ready')).toBe('ready')
  })

  it('maps "failed" to "failed"', () => {
    expect(mapBundleStatus('failed')).toBe('failed')
  })

  it('maps "expired" to "expired"', () => {
    expect(mapBundleStatus('expired')).toBe('expired')
  })

  it('maps unknown status to "queued"', () => {
    expect(mapBundleStatus('unknown')).toBe('queued')
    expect(mapBundleStatus('')).toBe('queued')
  })
})

describe('shouldContinuePolling', () => {
  it('returns true for "queued"', () => {
    expect(shouldContinuePolling('queued')).toBe(true)
  })

  it('returns true for "building"', () => {
    expect(shouldContinuePolling('building')).toBe(true)
  })

  it('returns false for "ready"', () => {
    expect(shouldContinuePolling('ready')).toBe(false)
  })

  it('returns false for "failed"', () => {
    expect(shouldContinuePolling('failed')).toBe(false)
  })

  it('returns false for "expired"', () => {
    expect(shouldContinuePolling('expired')).toBe(false)
  })

  it('returns false for "idle"', () => {
    expect(shouldContinuePolling('idle')).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// ZIP state machine — flow through statuses
// ---------------------------------------------------------------------------

describe('ZIP state machine flow', () => {
  it('queued → building → ready flow terminates polling', () => {
    const statuses = ['pending', 'pending', 'ready']
    const uiStatuses = statuses.map(mapBundleStatus)

    // Simulate poll loop
    let pollCount = 0
    for (const s of uiStatuses) {
      pollCount++
      if (!shouldContinuePolling(s)) break
    }

    expect(uiStatuses[2]).toBe('ready')
    expect(pollCount).toBe(3)
    expect(shouldContinuePolling('ready')).toBe(false)
  })

  it('failed flow terminates polling immediately', () => {
    const backendStatus = 'failed'
    const uiStatus = mapBundleStatus(backendStatus)
    expect(uiStatus).toBe('failed')
    expect(shouldContinuePolling(uiStatus)).toBe(false)
  })
})
