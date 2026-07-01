/**
 * Phase 0 baseline vitest test — confirms the test runner is working.
 * Component-level tests are added in Phase 3+ as pages land.
 */

import { describe, it, expect } from 'vitest'

describe('smoke', () => {
  it('test runner is operational', () => {
    expect(1 + 1).toBe(2)
  })

  it('cn utility is importable', async () => {
    const { cn } = await import('@/lib/utils')
    expect(cn('foo', 'bar')).toBe('foo bar')
    expect(cn('p-4', 'p-2')).toBe('p-2') // tailwind-merge deduplication
  })
})
