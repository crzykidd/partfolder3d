/**
 * Tests for lib/reconcile-utils.ts
 *
 * Covers the reconcile mode default-fallback logic, setting key derivation,
 * and the RECONCILE_DEFAULTS constant (which must match the backend's
 * DEFAULT_MODES in backend/app/worker/reconcile.py).
 */

import { describe, it, expect } from 'vitest'
import {
  getReconcileMode,
  reconcileSettingKey,
  RECONCILE_DEFAULTS,
} from '@/lib/reconcile-utils'
import type { SettingOut } from '@/lib/api'

// ---------------------------------------------------------------------------
// reconcileSettingKey
// ---------------------------------------------------------------------------

describe('reconcileSettingKey', () => {
  it('builds the correct key for sidecar_sync', () => {
    expect(reconcileSettingKey('sidecar_sync')).toBe('scan.sidecar_sync.mode')
  })

  it('builds the correct key for re_render', () => {
    expect(reconcileSettingKey('re_render')).toBe('scan.re_render.mode')
  })

  it('builds the correct key for file_changes', () => {
    expect(reconcileSettingKey('file_changes')).toBe('scan.file_changes.mode')
  })
})

// ---------------------------------------------------------------------------
// RECONCILE_DEFAULTS — must match backend DEFAULT_MODES
// ---------------------------------------------------------------------------

describe('RECONCILE_DEFAULTS', () => {
  it('sidecar_sync defaults to review (conservative)', () => {
    expect(RECONCILE_DEFAULTS.sidecar_sync).toBe('review')
  })

  it('re_render defaults to auto (non-destructive)', () => {
    expect(RECONCILE_DEFAULTS.re_render).toBe('auto')
  })

  it('file_changes defaults to review (conservative)', () => {
    expect(RECONCILE_DEFAULTS.file_changes).toBe('review')
  })
})

// ---------------------------------------------------------------------------
// getReconcileMode
// ---------------------------------------------------------------------------

const makeSettings = (overrides: Record<string, unknown>): SettingOut[] =>
  Object.entries(overrides).map(([key, value]) => ({ key, value }))

describe('getReconcileMode', () => {
  it('returns "auto" from settings when set to auto', () => {
    const settings = makeSettings({ 'scan.sidecar_sync.mode': 'auto' })
    expect(getReconcileMode(settings, 'sidecar_sync')).toBe('auto')
  })

  it('returns "review" from settings when set to review', () => {
    const settings = makeSettings({ 'scan.re_render.mode': 'review' })
    expect(getReconcileMode(settings, 're_render')).toBe('review')
  })

  it('falls back to documented default when key is absent — sidecar_sync', () => {
    expect(getReconcileMode([], 'sidecar_sync')).toBe('review')
  })

  it('falls back to documented default when key is absent — re_render', () => {
    expect(getReconcileMode([], 're_render')).toBe('auto')
  })

  it('falls back to documented default when key is absent — file_changes', () => {
    expect(getReconcileMode([], 'file_changes')).toBe('review')
  })

  it('falls back to default when value is an unexpected string', () => {
    const settings = makeSettings({ 'scan.sidecar_sync.mode': 'invalid-mode' })
    // invalid-mode is not 'auto' or 'review' → fall back to default 'review'
    expect(getReconcileMode(settings, 'sidecar_sync')).toBe('review')
  })

  it('ignores unrelated settings keys', () => {
    const settings = makeSettings({
      'instance.name': 'My Server',
      'instance.timezone': 'UTC',
    })
    // Only scan.*.mode keys are relevant; all absent → all defaults
    expect(getReconcileMode(settings, 'sidecar_sync')).toBe('review')
    expect(getReconcileMode(settings, 're_render')).toBe('auto')
  })

  it('returns the correct value when multiple mode settings are present', () => {
    const settings = makeSettings({
      'scan.sidecar_sync.mode': 'auto',
      'scan.re_render.mode': 'review',
      'scan.file_changes.mode': 'auto',
    })
    expect(getReconcileMode(settings, 'sidecar_sync')).toBe('auto')
    expect(getReconcileMode(settings, 're_render')).toBe('review')
    expect(getReconcileMode(settings, 'file_changes')).toBe('auto')
  })
})
