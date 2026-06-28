/**
 * reconcile-utils.ts — helper logic for the Phase 6 reconcile UI.
 *
 * Extracted as pure functions so they can be unit-tested independently
 * of React component rendering.
 */

import type { SettingOut } from './api'

// ---------------------------------------------------------------------------
// Reconcile mode defaults (mirrors backend DEFAULT_MODES in reconcile.py)
// ---------------------------------------------------------------------------

/** Documented defaults: conservative — sidecar and file changes go to review. */
export const RECONCILE_DEFAULTS: Record<string, 'auto' | 'review'> = {
  sidecar_sync: 'review',
  re_render: 'auto',
  file_changes: 'review',
}

// ---------------------------------------------------------------------------
// Setting key helpers
// ---------------------------------------------------------------------------

/** Returns the settings-table key for a given behavior (matches backend _SETTING_KEYS). */
export function reconcileSettingKey(behavior: string): string {
  return `scan.${behavior}.mode`
}

/**
 * Read the current reconcile mode for a behavior from the full settings list.
 *
 * If the key is absent (never set) the engine uses the documented default,
 * so we do the same here rather than showing an empty/unknown state.
 */
export function getReconcileMode(
  settings: SettingOut[],
  behavior: string,
): 'auto' | 'review' {
  const key = reconcileSettingKey(behavior)
  const row = settings.find((s) => s.key === key)
  if (row && (row.value === 'auto' || row.value === 'review')) {
    return row.value as 'auto' | 'review'
  }
  return RECONCILE_DEFAULTS[behavior] ?? 'auto'
}
