/**
 * import-wizard/styles.ts — Aurora style constants shared across wizard step components.
 *
 * JSX-FREE. esbuild rejects JSX in .ts files.
 */

import type { CSSProperties, FocusEvent } from 'react'

// ---------------------------------------------------------------------------
// Aurora style constants
// ---------------------------------------------------------------------------

export const AURORA_CARD: CSSProperties = {
  background: 'var(--aurora-card)',
  border: '1px solid var(--aurora-card-border)',
  borderRadius: 14,
  backdropFilter: 'blur(16px)',
  WebkitBackdropFilter: 'blur(16px)',
}

export const AURORA_INPUT: CSSProperties = {
  background: 'var(--aurora-input-bg)',
  border: '1px solid var(--aurora-input-border)',
  borderRadius: 8,
  color: 'var(--aurora-text)',
  padding: '7px 11px',
  fontSize: 13,
  outline: 'none',
  width: '100%',
  transition: 'border-color 0.15s, box-shadow 0.15s',
  boxSizing: 'border-box',
  display: 'block',
}

export const AURORA_BTN_PRIMARY: CSSProperties = {
  background: 'var(--aurora-accent)',
  border: 'none',
  borderRadius: 20,
  color: 'var(--aurora-accent-fg)',
  fontSize: 13,
  fontWeight: 700,
  padding: '8px 22px',
  cursor: 'pointer',
  boxShadow: '0 4px 14px var(--aurora-accent-glow)',
  transition: 'opacity 0.15s',
  display: 'inline-flex',
  alignItems: 'center',
  gap: 6,
}

export const AURORA_BTN_GHOST: CSSProperties = {
  background: 'var(--aurora-glass)',
  border: '1px solid var(--aurora-glass-border)',
  borderRadius: 20,
  color: 'var(--aurora-text-dim)',
  fontSize: 13,
  padding: '7px 18px',
  cursor: 'pointer',
  transition: 'all 0.15s',
  display: 'inline-flex',
  alignItems: 'center',
  gap: 6,
}

export const AURORA_BTN_GHOST_SM: CSSProperties = {
  background: 'var(--aurora-glass)',
  border: '1px solid var(--aurora-glass-border)',
  borderRadius: 20,
  color: 'var(--aurora-text-dim)',
  fontSize: 11,
  padding: '4px 12px',
  cursor: 'pointer',
  transition: 'all 0.15s',
  display: 'inline-flex',
  alignItems: 'center',
  gap: 4,
}

export const SECTION_LABEL: CSSProperties = {
  fontSize: 10,
  fontWeight: 700,
  color: 'var(--aurora-muted)',
  letterSpacing: '0.1em',
  textTransform: 'uppercase',
  display: 'block',
  marginBottom: 6,
}

// ---------------------------------------------------------------------------
// Focus/blur handlers for aurora inputs
// ---------------------------------------------------------------------------

export function onAuroraFocus(e: FocusEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) {
  e.currentTarget.style.borderColor = 'var(--aurora-pill-border)'
  e.currentTarget.style.boxShadow = '0 0 0 3px var(--aurora-pill)'
}

export function onAuroraBlur(e: FocusEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) {
  e.currentTarget.style.borderColor = 'var(--aurora-input-border)'
  e.currentTarget.style.boxShadow = 'none'
}
