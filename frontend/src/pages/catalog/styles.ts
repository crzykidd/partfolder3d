/**
 * Shared Aurora style constants used across catalog/* subcomponents.
 * JSX-free — pure TypeScript. Mirrors the pages/item/styles.ts pattern.
 */

import type React from 'react'

export const CARD_STYLE: React.CSSProperties = {
  background: 'var(--aurora-card)',
  border: '1px solid var(--aurora-card-border)',
  borderRadius: 12,
  backdropFilter: 'blur(16px)',
  WebkitBackdropFilter: 'blur(16px)',
}

export const INPUT_STYLE: React.CSSProperties = {
  background: 'var(--aurora-input-bg)',
  border: '1px solid var(--aurora-input-border)',
  borderRadius: 10,
  color: 'var(--aurora-text)',
  padding: '7px 12px',
  fontSize: 13,
  outline: 'none',
  width: '100%',
  transition: 'border-color 0.15s, box-shadow 0.15s',
}
