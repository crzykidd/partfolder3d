/**
 * Button — Aurora button primitive with primary / ghost / danger variants.
 *
 * Follows the inline-style + aurora-var pattern established in LibrariesPage.tsx.
 * Sizes: sm (compact tables), md (page actions).
 *
 * Reusable by B3b.
 */

import React from 'react'

// ---------------------------------------------------------------------------
// Style constants (mirror LibrariesPage BTN_* constants)
// ---------------------------------------------------------------------------

const BASE: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 6,
  borderRadius: 8,
  fontWeight: 600,
  cursor: 'pointer',
  transition: 'opacity 0.15s, background 0.15s, color 0.15s',
  border: 'none',
}

type BtnVariant = 'primary' | 'ghost' | 'danger' | 'ghost-sm'

const VARIANT_STYLE: Record<BtnVariant, React.CSSProperties> = {
  primary: {
    background: 'var(--aurora-accent)',
    color: '#fff',
    border: 'none',
  },
  ghost: {
    background: 'var(--aurora-glass)',
    border: '1px solid var(--aurora-glass-border)',
    color: 'var(--aurora-text-dim)',
  },
  danger: {
    background: 'rgba(239,68,68,0.10)',
    border: '1px solid rgba(239,68,68,0.3)',
    color: 'var(--aurora-danger)',
  },
  'ghost-sm': {
    background: 'var(--aurora-glass)',
    border: '1px solid var(--aurora-glass-border)',
    color: 'var(--aurora-text-dim)',
  },
}

type BtnSize = 'sm' | 'md'

const SIZE_STYLE: Record<BtnSize, React.CSSProperties> = {
  sm: { padding: '5px 10px', fontSize: 12 },
  md: { padding: '8px 16px', fontSize: 13 },
}

// ---------------------------------------------------------------------------
// Button
// ---------------------------------------------------------------------------

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: BtnVariant
  size?: BtnSize
  /** Extra style overrides */
  extraStyle?: React.CSSProperties
}

export function Button({
  variant = 'primary',
  size = 'md',
  disabled,
  extraStyle,
  style,
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      disabled={disabled}
      style={{
        ...BASE,
        ...VARIANT_STYLE[variant],
        ...SIZE_STYLE[size],
        opacity: disabled ? 0.5 : 1,
        cursor: disabled ? 'not-allowed' : 'pointer',
        ...extraStyle,
        ...style,
      }}
      {...rest}
    >
      {children}
    </button>
  )
}

// ---------------------------------------------------------------------------
// FilterPill — toggleable filter button (active/inactive)
// ---------------------------------------------------------------------------

interface FilterPillProps {
  active: boolean
  onClick: () => void
  children: React.ReactNode
  disabled?: boolean
}

export function FilterPill({ active, onClick, children, disabled }: FilterPillProps) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        padding: '4px 12px',
        borderRadius: 20,
        fontSize: 12,
        fontWeight: active ? 600 : 500,
        cursor: disabled ? 'not-allowed' : 'pointer',
        transition: 'background 0.15s, color 0.15s, border-color 0.15s',
        background: active ? 'var(--aurora-accent)' : 'var(--aurora-glass)',
        color: active ? '#fff' : 'var(--aurora-text-dim)',
        border: active
          ? '1px solid var(--aurora-accent)'
          : '1px solid var(--aurora-glass-border)',
        opacity: disabled ? 0.5 : 1,
      }}
    >
      {children}
    </button>
  )
}

// ---------------------------------------------------------------------------
// AuroraToggle — visual on/off switch for boolean settings
// ---------------------------------------------------------------------------

interface AuroraToggleProps {
  checked: boolean
  onChange: (checked: boolean) => void
  disabled?: boolean
  ariaLabel?: string
}

export function AuroraToggle({ checked, onChange, disabled, ariaLabel }: AuroraToggleProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel ?? (checked ? 'Enabled' : 'Disabled')}
      disabled={disabled}
      onClick={() => !disabled && onChange(!checked)}
      style={{
        position: 'relative',
        display: 'inline-flex',
        width: 36,
        height: 20,
        borderRadius: 10,
        background: checked ? 'var(--aurora-accent)' : 'var(--aurora-glass)',
        border: checked ? '1px solid var(--aurora-accent)' : '1px solid var(--aurora-glass-border)',
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.5 : 1,
        transition: 'background 0.2s, border-color 0.2s',
        flexShrink: 0,
      }}
    >
      <span
        style={{
          position: 'absolute',
          top: 2,
          left: checked ? 16 : 2,
          width: 14,
          height: 14,
          borderRadius: '50%',
          background: '#fff',
          transition: 'left 0.2s',
          boxShadow: '0 1px 3px rgba(0,0,0,0.25)',
        }}
      />
    </button>
  )
}
