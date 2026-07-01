/**
 * Tests for lib/utils.ts — shared utility helpers.
 *
 * Covers:
 *  - isSafeHttpUrl: XSS guard for user-supplied profile URLs
 */

import { describe, it, expect } from 'vitest'
import { isSafeHttpUrl } from '@/lib/utils'

describe('isSafeHttpUrl', () => {
  it('accepts http URLs', () => {
    expect(isSafeHttpUrl('http://example.com')).toBe(true)
    expect(isSafeHttpUrl('http://www.thingiverse.com/thing:12345')).toBe(true)
  })

  it('accepts https URLs', () => {
    expect(isSafeHttpUrl('https://example.com')).toBe(true)
    expect(isSafeHttpUrl('https://makerworld.com/en/@designer')).toBe(true)
  })

  it('rejects javascript: scheme', () => {
    expect(isSafeHttpUrl('javascript:alert(1)')).toBe(false)
    expect(isSafeHttpUrl('javascript:void(0)')).toBe(false)
  })

  it('rejects data: scheme', () => {
    expect(isSafeHttpUrl('data:text/html,<script>alert(1)</script>')).toBe(false)
    expect(isSafeHttpUrl('data:image/png;base64,abc')).toBe(false)
  })

  it('rejects vbscript: and other dangerous schemes', () => {
    expect(isSafeHttpUrl('vbscript:MsgBox(1)')).toBe(false)
    expect(isSafeHttpUrl('ftp://example.com/file')).toBe(false)
    expect(isSafeHttpUrl('file:///etc/passwd')).toBe(false)
  })

  it('rejects empty string', () => {
    expect(isSafeHttpUrl('')).toBe(false)
  })

  it('rejects non-URL strings', () => {
    expect(isSafeHttpUrl('not-a-url')).toBe(false)
    expect(isSafeHttpUrl('just some text')).toBe(false)
  })

  it('rejects protocol-relative URLs', () => {
    // //example.com is not a valid URL without a scheme
    expect(isSafeHttpUrl('//example.com')).toBe(false)
  })
})
