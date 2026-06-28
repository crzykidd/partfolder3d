/**
 * Tests for import-utils.ts — pure helper functions for the import wizard.
 *
 * Covers:
 *  - Wizard step navigation (nextStep, prevStep, stepIndex, isFirstStep, isLastStep)
 *  - Tag state manipulation (acceptPendingTag, rejectPendingTag, removeConfirmedTag, addConfirmedTag)
 *  - Session status helpers (isProcessing, isEditable)
 *  - Domain extraction (extractDomain)
 */

import { describe, it, expect } from 'vitest'
import {
  WIZARD_STEPS,
  nextStep,
  prevStep,
  stepIndex,
  isFirstStep,
  isLastStep,
  acceptPendingTag,
  rejectPendingTag,
  removeConfirmedTag,
  addConfirmedTag,
  isProcessing,
  isEditable,
  extractDomain,
} from '@/lib/import-utils'

// ---------------------------------------------------------------------------
// Wizard step navigation
// ---------------------------------------------------------------------------

describe('nextStep', () => {
  it('advances from title to images', () => {
    expect(nextStep('title')).toBe('images')
  })

  it('advances through all steps', () => {
    expect(nextStep('images')).toBe('tags')
    expect(nextStep('tags')).toBe('creator')
    expect(nextStep('creator')).toBe('summary')
  })

  it('clamps at the last step', () => {
    expect(nextStep('summary')).toBe('summary')
  })
})

describe('prevStep', () => {
  it('goes back from summary to creator', () => {
    expect(prevStep('summary')).toBe('creator')
  })

  it('goes back through all steps', () => {
    expect(prevStep('creator')).toBe('tags')
    expect(prevStep('tags')).toBe('images')
    expect(prevStep('images')).toBe('title')
  })

  it('clamps at the first step', () => {
    expect(prevStep('title')).toBe('title')
  })
})

describe('stepIndex', () => {
  it('returns 0 for title', () => {
    expect(stepIndex('title')).toBe(0)
  })

  it('returns the correct index for each step', () => {
    expect(stepIndex('images')).toBe(1)
    expect(stepIndex('tags')).toBe(2)
    expect(stepIndex('creator')).toBe(3)
    expect(stepIndex('summary')).toBe(4)
  })

  it('total steps count is 5', () => {
    expect(WIZARD_STEPS.length).toBe(5)
  })
})

describe('isFirstStep', () => {
  it('returns true for title', () => {
    expect(isFirstStep('title')).toBe(true)
  })

  it('returns false for other steps', () => {
    expect(isFirstStep('images')).toBe(false)
    expect(isFirstStep('summary')).toBe(false)
  })
})

describe('isLastStep', () => {
  it('returns true for summary', () => {
    expect(isLastStep('summary')).toBe(true)
  })

  it('returns false for other steps', () => {
    expect(isLastStep('creator')).toBe(false)
    expect(isLastStep('title')).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// Tag state manipulation
// ---------------------------------------------------------------------------

describe('acceptPendingTag', () => {
  it('moves tag from pending to confirmed', () => {
    const [confirmed, pending] = acceptPendingTag([], ['fdm', 'resin'], 'fdm')
    expect(confirmed).toContain('fdm')
    expect(pending).not.toContain('fdm')
    expect(pending).toContain('resin')
  })

  it('does not duplicate if already confirmed', () => {
    const [confirmed, pending] = acceptPendingTag(['fdm'], ['fdm'], 'fdm')
    expect(confirmed.filter((t) => t === 'fdm').length).toBe(1)
    expect(pending).not.toContain('fdm')
  })

  it('does not mutate input arrays', () => {
    const orig = ['resin']
    const origPending = ['fdm']
    acceptPendingTag(orig, origPending, 'fdm')
    expect(orig).toEqual(['resin'])
    expect(origPending).toEqual(['fdm'])
  })
})

describe('rejectPendingTag', () => {
  it('removes tag from pending', () => {
    const [confirmed, pending] = rejectPendingTag(['active'], ['fdm', 'resin'], 'fdm')
    expect(pending).not.toContain('fdm')
    expect(pending).toContain('resin')
    expect(confirmed).toEqual(['active'])
  })

  it('does not affect confirmed tags', () => {
    const [confirmed] = rejectPendingTag(['fdm'], ['fdm'], 'fdm')
    expect(confirmed).toContain('fdm')
  })
})

describe('removeConfirmedTag', () => {
  it('removes the specified tag', () => {
    const result = removeConfirmedTag(['fdm', 'resin', 'miniature'], 'resin')
    expect(result).not.toContain('resin')
    expect(result).toContain('fdm')
    expect(result).toContain('miniature')
  })

  it('returns same array if tag not present', () => {
    const result = removeConfirmedTag(['fdm'], 'resin')
    expect(result).toEqual(['fdm'])
  })
})

describe('addConfirmedTag', () => {
  it('adds a new tag', () => {
    const result = addConfirmedTag(['fdm'], 'resin')
    expect(result).toContain('resin')
    expect(result).toContain('fdm')
  })

  it('does not add duplicates', () => {
    const result = addConfirmedTag(['fdm', 'resin'], 'fdm')
    expect(result.filter((t) => t === 'fdm').length).toBe(1)
  })

  it('trims whitespace', () => {
    const result = addConfirmedTag([], '  resin  ')
    expect(result).toContain('resin')
  })

  it('ignores empty strings', () => {
    const result = addConfirmedTag(['fdm'], '')
    expect(result).toEqual(['fdm'])
  })

  it('ignores whitespace-only strings', () => {
    const result = addConfirmedTag(['fdm'], '   ')
    expect(result).toEqual(['fdm'])
  })
})

// ---------------------------------------------------------------------------
// Session status helpers
// ---------------------------------------------------------------------------

describe('isProcessing', () => {
  it('returns true for "processing"', () => {
    expect(isProcessing('processing')).toBe(true)
  })

  it('returns false for other statuses', () => {
    expect(isProcessing('pending_wizard')).toBe(false)
    expect(isProcessing('draft')).toBe(false)
    expect(isProcessing('committed')).toBe(false)
    expect(isProcessing('failed')).toBe(false)
  })
})

describe('isEditable', () => {
  it('returns true for pending_wizard, draft, failed', () => {
    expect(isEditable('pending_wizard')).toBe(true)
    expect(isEditable('draft')).toBe(true)
    expect(isEditable('failed')).toBe(true)
  })

  it('returns false for committed, cancelled, processing', () => {
    expect(isEditable('committed')).toBe(false)
    expect(isEditable('cancelled')).toBe(false)
    expect(isEditable('processing')).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// Domain extraction
// ---------------------------------------------------------------------------

describe('extractDomain', () => {
  it('extracts hostname from a standard URL', () => {
    expect(extractDomain('https://www.thingiverse.com/thing:12345')).toBe(
      'www.thingiverse.com',
    )
  })

  it('extracts hostname from URL with path', () => {
    expect(extractDomain('https://printables.com/model/123')).toBe(
      'printables.com',
    )
  })

  it('returns null for invalid URLs', () => {
    expect(extractDomain('not-a-url')).toBe(null)
    expect(extractDomain('')).toBe(null)
  })
})
