/**
 * Card — Aurora glass card / panel primitive.
 *
 * Matches the visual style established in LibrariesPage.tsx.
 * Use `accent` for a teal-tinted card (info/callout boxes).
 */

import React from 'react'

// Shared style constant — can be spread into custom elements if needed
export const CARD_STYLE: React.CSSProperties = {
  background: 'var(--aurora-card)',
  border: '1px solid var(--aurora-card-border)',
  borderRadius: 12,
  backdropFilter: 'blur(16px)',
  WebkitBackdropFilter: 'blur(16px)',
}

export const CARD_ACCENT_STYLE: React.CSSProperties = {
  background: 'rgba(15,164,171,0.04)',
  border: '1px solid rgba(15,164,171,0.2)',
  borderRadius: 12,
  backdropFilter: 'blur(16px)',
  WebkitBackdropFilter: 'blur(16px)',
}

// ---------------------------------------------------------------------------
// Card component
// ---------------------------------------------------------------------------

interface CardProps {
  children: React.ReactNode
  className?: string
  /** Extra inline overrides (spread on top of CARD_STYLE) */
  style?: React.CSSProperties
  /** Teal-tinted accent card (info / callout) */
  accent?: boolean
  /** Padding — defaults to '20px 22px' */
  padding?: string | number
}

export function Card({ children, className, style, accent = false, padding = '20px 22px' }: CardProps) {
  return (
    <div
      className={className}
      style={{
        ...(accent ? CARD_ACCENT_STYLE : CARD_STYLE),
        padding,
        ...style,
      }}
    >
      {children}
    </div>
  )
}

// ---------------------------------------------------------------------------
// SectionHeader — small uppercase label inside a card section
// ---------------------------------------------------------------------------

export function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        fontSize: 11,
        fontWeight: 700,
        color: 'var(--aurora-muted)',
        textTransform: 'uppercase',
        letterSpacing: '0.07em',
        marginBottom: 12,
      }}
    >
      {children}
    </div>
  )
}
