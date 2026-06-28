/**
 * Field — Aurora form field: label + aurora-styled input / select.
 *
 * Provides:
 *  - <Field label="…"><input …/></Field>  — wraps any input with a label
 *  - <AuroraInput />   — standalone aurora-styled <input>
 *  - <AuroraSelect>…</AuroraSelect>  — aurora-styled <select>
 *
 * Focus ring is handled via onFocus/onBlur (same pattern as LibrariesPage).
 *
 * Reusable by B3b.
 */

import React, { useRef } from 'react'

// ---------------------------------------------------------------------------
// Shared style constants
// ---------------------------------------------------------------------------

export const INPUT_STYLE: React.CSSProperties = {
  background: 'var(--aurora-input-bg)',
  border: '1px solid var(--aurora-input-border)',
  borderRadius: 8,
  color: 'var(--aurora-text)',
  padding: '7px 12px',
  fontSize: 13,
  outline: 'none',
  width: '100%',
  transition: 'border-color 0.15s, box-shadow 0.15s',
}

export const LABEL_STYLE: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  color: 'var(--aurora-muted)',
  textTransform: 'uppercase',
  letterSpacing: '0.07em',
  display: 'block',
  marginBottom: 4,
}

function focusRing(el: HTMLElement) {
  el.style.borderColor = 'var(--aurora-accent)'
  el.style.boxShadow = '0 0 0 3px var(--aurora-pill)'
}

function blurRing(el: HTMLElement) {
  el.style.borderColor = 'var(--aurora-input-border)'
  el.style.boxShadow = 'none'
}

// ---------------------------------------------------------------------------
// Field wrapper
// ---------------------------------------------------------------------------

interface FieldProps {
  label: string
  children: React.ReactNode
  hint?: string
}

export function Field({ label, children, hint }: FieldProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <label style={LABEL_STYLE}>{label}</label>
      {children}
      {hint && (
        <p style={{ fontSize: 11, color: 'var(--aurora-muted)', margin: 0, lineHeight: 1.5 }}>
          {hint}
        </p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// AuroraInput
// ---------------------------------------------------------------------------

export type AuroraInputProps = React.InputHTMLAttributes<HTMLInputElement>

export function AuroraInput({ style, onFocus, onBlur, ...rest }: AuroraInputProps) {
  const ref = useRef<HTMLInputElement>(null)

  return (
    <input
      ref={ref}
      style={{ ...INPUT_STYLE, ...style }}
      onFocus={(e) => {
        focusRing(e.currentTarget)
        onFocus?.(e)
      }}
      onBlur={(e) => {
        blurRing(e.currentTarget)
        onBlur?.(e)
      }}
      {...rest}
    />
  )
}

// ---------------------------------------------------------------------------
// AuroraSelect
// ---------------------------------------------------------------------------

export type AuroraSelectProps = React.SelectHTMLAttributes<HTMLSelectElement>

export function AuroraSelect({ style, onFocus, onBlur, children, ...rest }: AuroraSelectProps) {
  return (
    <select
      style={{ ...INPUT_STYLE, cursor: 'pointer', ...style }}
      onFocus={(e) => {
        focusRing(e.currentTarget)
        onFocus?.(e)
      }}
      onBlur={(e) => {
        blurRing(e.currentTarget)
        onBlur?.(e)
      }}
      {...rest}
    >
      {children}
    </select>
  )
}
