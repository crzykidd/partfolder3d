/**
 * Tests for Phase 8b additions to import-utils.ts:
 *  - levenshtein: edit distance between two strings
 *  - fuzzyMatchTags: closest canonical tag within a distance threshold
 *
 * Also exercises TypeScript types for AiProviderOut / AiTagSuggestionOut /
 * AiTextOut (compile-time only — no runtime assertions needed for shape tests).
 */

import { describe, it, expect } from 'vitest'
import { levenshtein, fuzzyMatchTags } from '@/lib/import-utils'
import type { AiProviderOut, AiTagSuggestionOut, AiTextOut } from '@/lib/api'

// ---------------------------------------------------------------------------
// levenshtein
// ---------------------------------------------------------------------------

describe('levenshtein', () => {
  it('returns 0 for identical strings', () => {
    expect(levenshtein('fdm', 'fdm')).toBe(0)
    expect(levenshtein('', '')).toBe(0)
  })

  it('returns string length for empty-vs-non-empty', () => {
    expect(levenshtein('', 'abc')).toBe(3)
    expect(levenshtein('abc', '')).toBe(3)
  })

  it('computes single-char differences correctly', () => {
    expect(levenshtein('cat', 'car')).toBe(1) // substitution
    expect(levenshtein('cat', 'cats')).toBe(1) // insertion
    expect(levenshtein('cats', 'cat')).toBe(1) // deletion
  })

  it('handles transpositions', () => {
    // "resin" → "resni": 2 edits (not a transposition in Levenshtein, not Damerau)
    expect(levenshtein('resin', 'resni')).toBe(2)
  })

  it('handles unrelated strings', () => {
    expect(levenshtein('fdm', 'xyz')).toBe(3)
    expect(levenshtein('miniature', 'xyz')).toBeGreaterThan(3)
  })

  it('gives realistic distances for tag typos', () => {
    // Common 1-char typos
    expect(levenshtein('miniature', 'minature')).toBe(1)  // missing i
    expect(levenshtein('miniature', 'miniture')).toBe(1)  // a→i
    // 2-char difference
    expect(levenshtein('fdm', 'ffd')).toBe(2)
  })

  it('is NOT symmetric in edge cases (should be for strings)', () => {
    // Levenshtein is symmetric
    expect(levenshtein('abc', 'xyz')).toBe(levenshtein('xyz', 'abc'))
  })
})

// ---------------------------------------------------------------------------
// fuzzyMatchTags
// ---------------------------------------------------------------------------

describe('fuzzyMatchTags', () => {
  const canonicals = ['fdm', 'resin', 'miniature', 'terrain', 'tabletop']

  it('returns exact match at distance 0', () => {
    expect(fuzzyMatchTags('fdm', canonicals)).toBe('fdm')
  })

  it('returns closest match for 1-edit typo', () => {
    expect(fuzzyMatchTags('resim', canonicals)).toBe('resin') // n→m
    expect(fuzzyMatchTags('minature', canonicals)).toBe('miniature') // missing i
  })

  it('returns closest match for 2-edit typo', () => {
    expect(fuzzyMatchTags('terrian', canonicals)).toBe('terrain') // transposed + edit
  })

  it('returns null when no match within threshold (default 3)', () => {
    // 'zzzzzzzzz' (9 z's) vs shortest canonical 'fdm' (3 chars) → ≥ 6 edits
    expect(fuzzyMatchTags('zzzzzzzzz', canonicals)).toBeNull()
    // A long word with no overlap: at least 4 edits from every canonical
    expect(fuzzyMatchTags('qqqqqqqqq', canonicals)).toBeNull()
  })

  it('respects custom maxDistance', () => {
    // 'minature' is 1 edit from 'miniature' — within 1 and within 2
    expect(fuzzyMatchTags('minature', canonicals, 1)).toBe('miniature')
    expect(fuzzyMatchTags('minature', canonicals, 0)).toBeNull() // 0 = exact only
  })

  it('is case-insensitive', () => {
    expect(fuzzyMatchTags('FDM', canonicals)).toBe('fdm')
    expect(fuzzyMatchTags('Resin', canonicals)).toBe('resin')
  })

  it('returns null for empty canonical list', () => {
    expect(fuzzyMatchTags('fdm', [])).toBeNull()
  })

  it('empty pending tag matches short canonicals within threshold', () => {
    // '' → 'fdm' costs 3 edits (insert f, d, m), which equals the default maxDistance.
    // This IS within threshold, so 'fdm' (shortest canonical) is returned.
    expect(fuzzyMatchTags('', canonicals)).toBe('fdm')
    // With stricter threshold of 2, the empty string does NOT match any canonical
    // (all canonicals have ≥ 3 chars, so distance from '' is ≥ 3 > 2).
    expect(fuzzyMatchTags('', canonicals, 2)).toBeNull()
  })

  it('finds best (closest) match among multiple candidates', () => {
    // 'fdmm' is 1 edit from 'fdm' and many edits from everything else
    expect(fuzzyMatchTags('fdmm', canonicals)).toBe('fdm')
  })
})

// ---------------------------------------------------------------------------
// TypeScript shape tests (compile-time only)
// ---------------------------------------------------------------------------
// These assignments confirm the type shapes are correct at compile time.
// No runtime assertions — the test passes if it compiles.

describe('AiProviderOut shape', () => {
  it('is assignable from a valid object', () => {
    const p: AiProviderOut = {
      id: 1,
      provider: 'claude',
      endpoint: null,
      model: 'claude-opus-4-8',
      has_key: true,
      enabled: true,
    }
    expect(p.id).toBe(1)
    expect(p.has_key).toBe(true)
  })

  it('accepts all provider types', () => {
    const providers: AiProviderOut['provider'][] = ['claude', 'openai', 'ollama']
    expect(providers).toHaveLength(3)
  })
})

describe('AiTagSuggestionOut shape', () => {
  it('is assignable with all fields', () => {
    const r: AiTagSuggestionOut = {
      canonical: ['fdm', 'resin'],
      new_suggestions: ['terrain-builder'],
      provider_available: true,
      error: null,
    }
    expect(r.canonical).toHaveLength(2)
    expect(r.new_suggestions).toHaveLength(1)
    expect(r.provider_available).toBe(true)
  })

  it('accepts provider_available=false (no provider configured)', () => {
    const r: AiTagSuggestionOut = {
      canonical: [],
      new_suggestions: [],
      provider_available: false,
      error: null,
    }
    expect(r.provider_available).toBe(false)
  })
})

describe('AiTextOut shape', () => {
  it('is assignable with text', () => {
    const r: AiTextOut = {
      text: 'A cleaned-up description.',
      provider_available: true,
      error: null,
    }
    expect(r.text).toBeTruthy()
  })

  it('accepts null text (no provider / error)', () => {
    const r: AiTextOut = {
      text: null,
      provider_available: false,
      error: null,
    }
    expect(r.text).toBeNull()
  })
})
