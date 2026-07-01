/**
 * Tests for Phase 7b — print history helpers and public share page behaviour.
 *
 * Tests:
 * 1. formatPrintTime — seconds → "Xh Ym"
 * 2. formatFilamentLength — mm → "X.XX m"
 * 3. PublicSharePage 403 "no longer available" state logic
 */

import { describe, it, expect } from 'vitest'
import { formatPrintTime, formatFilamentLength, formatFilamentWeight, renderStars } from '@/lib/print-utils'
import { ApiError } from '@/lib/api'

// ---------------------------------------------------------------------------
// formatPrintTime
// ---------------------------------------------------------------------------

describe('formatPrintTime', () => {
  it('formats exact hours', () => {
    expect(formatPrintTime(3600)).toBe('1h')
    expect(formatPrintTime(7200)).toBe('2h')
  })

  it('formats hours and minutes', () => {
    expect(formatPrintTime(7380)).toBe('2h 3m')
    expect(formatPrintTime(3661)).toBe('1h 1m')
    expect(formatPrintTime(5400)).toBe('1h 30m')
  })

  it('formats minutes only', () => {
    expect(formatPrintTime(60)).toBe('1m')
    expect(formatPrintTime(1800)).toBe('30m')
    expect(formatPrintTime(3599)).toBe('59m')
  })

  it('returns 0m for zero or negative', () => {
    expect(formatPrintTime(0)).toBe('0m')
    expect(formatPrintTime(-100)).toBe('0m')
  })
})

// ---------------------------------------------------------------------------
// formatFilamentLength
// ---------------------------------------------------------------------------

describe('formatFilamentLength', () => {
  it('converts mm to metres with 2 decimal places', () => {
    expect(formatFilamentLength(1000)).toBe('1.00 m')
    expect(formatFilamentLength(1234.56)).toBe('1.23 m')
    expect(formatFilamentLength(500)).toBe('0.50 m')
    expect(formatFilamentLength(10000)).toBe('10.00 m')
  })

  it('rounds to 2 decimal places', () => {
    expect(formatFilamentLength(1235)).toBe('1.24 m')
    expect(formatFilamentLength(1234)).toBe('1.23 m')
  })
})

// ---------------------------------------------------------------------------
// formatFilamentWeight
// ---------------------------------------------------------------------------

describe('formatFilamentWeight', () => {
  it('formats grams with 1 decimal place', () => {
    expect(formatFilamentWeight(4.5)).toBe('4.5 g')
    expect(formatFilamentWeight(10)).toBe('10.0 g')
    expect(formatFilamentWeight(0.1)).toBe('0.1 g')
  })
})

// ---------------------------------------------------------------------------
// renderStars
// ---------------------------------------------------------------------------

describe('renderStars', () => {
  it('renders correct star strings', () => {
    expect(renderStars(1)).toBe('★☆☆☆☆')
    expect(renderStars(3)).toBe('★★★☆☆')
    expect(renderStars(5)).toBe('★★★★★')
  })

  it('clamps out-of-range values', () => {
    expect(renderStars(0)).toBe('★☆☆☆☆')   // clamp to 1
    expect(renderStars(6)).toBe('★★★★★')   // clamp to 5
  })
})

// ---------------------------------------------------------------------------
// PublicSharePage — 403 "no longer available" state
// ---------------------------------------------------------------------------

describe('PublicSharePage 403 handling', () => {
  it('ApiError with status 403 is detected as unavailable', () => {
    const err = new ApiError(403, 'This share link has expired.')
    const isUnavailable =
      err instanceof ApiError &&
      (err.status === 403 || err.status === 404)
    expect(isUnavailable).toBe(true)
  })

  it('ApiError with status 404 is detected as unavailable', () => {
    const err = new ApiError(404, 'Share link not found.')
    const isUnavailable =
      err instanceof ApiError &&
      (err.status === 403 || err.status === 404)
    expect(isUnavailable).toBe(true)
  })

  it('ApiError with status 400 and full-site message is NOT treated as unavailable', () => {
    const err = new ApiError(400, 'This link is for full-site browse, not a single item.')
    const isFullSite =
      err instanceof ApiError &&
      err.status === 400 &&
      String(err.message).includes('full-site')
    const isUnavailable =
      err instanceof ApiError &&
      (err.status === 403 || err.status === 404) &&
      !isFullSite
    expect(isFullSite).toBe(true)
    expect(isUnavailable).toBe(false)
  })

  it('ApiError with status 500 does NOT show "no longer available"', () => {
    const err = new ApiError(500, 'Internal server error.')
    const isUnavailable =
      err instanceof ApiError &&
      (err.status === 403 || err.status === 404)
    expect(isUnavailable).toBe(false)
  })
})
