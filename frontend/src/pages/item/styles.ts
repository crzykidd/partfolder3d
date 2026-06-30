/**
 * Shared Aurora style constants and small helpers used across item/* subcomponents.
 * JSX-free — pure TypeScript. See AuroraSection.tsx for the section wrapper component.
 */

import type React from 'react'

// ---------------------------------------------------------------------------
// Formatters
// ---------------------------------------------------------------------------

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

export function formatExpiry(iso: string | null): string {
  if (!iso) return 'Never'
  const d = new Date(iso)
  const now = Date.now()
  const diff = d.getTime() - now
  if (diff < 0) return 'Expired'
  const days = Math.ceil(diff / (1000 * 60 * 60 * 24))
  if (days === 1) return 'Expires in 1 day'
  return `Expires in ${days} days`
}

// ---------------------------------------------------------------------------
// Aurora style constants
// ---------------------------------------------------------------------------

export const AURORA_CARD: React.CSSProperties = {
  background: 'var(--aurora-card)',
  border: '1px solid var(--aurora-card-border)',
  borderRadius: 14,
  backdropFilter: 'blur(16px)',
  WebkitBackdropFilter: 'blur(16px)',
}

export const AURORA_SECTION_HEADER: React.CSSProperties = {
  fontSize: 10,
  fontWeight: 700,
  color: 'var(--aurora-muted)',
  letterSpacing: '0.1em',
  textTransform: 'uppercase',
  marginBottom: 14,
}

export const AURORA_INPUT: React.CSSProperties = {
  background: 'var(--aurora-input-bg)',
  border: '1px solid var(--aurora-input-border)',
  borderRadius: 8,
  color: 'var(--aurora-text)',
  padding: '6px 10px',
  fontSize: 13,
  outline: 'none',
  width: '100%',
  transition: 'border-color 0.15s',
  boxSizing: 'border-box',
}

export const AURORA_BTN_PRIMARY: React.CSSProperties = {
  background: 'var(--aurora-accent)',
  border: 'none',
  borderRadius: 20,
  color: 'var(--aurora-accent-fg)',
  fontSize: 12,
  fontWeight: 700,
  padding: '6px 16px',
  cursor: 'pointer',
  boxShadow: '0 4px 14px var(--aurora-accent-glow)',
  transition: 'opacity 0.15s',
}

export const AURORA_BTN_GHOST: React.CSSProperties = {
  background: 'var(--aurora-glass)',
  border: '1px solid var(--aurora-glass-border)',
  borderRadius: 20,
  color: 'var(--aurora-text-dim)',
  fontSize: 12,
  padding: '5px 14px',
  cursor: 'pointer',
  transition: 'all 0.15s',
}
