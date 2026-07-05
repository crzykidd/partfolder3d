/**
 * LibraryFilter — catalog toolbar control to filter items by one or more libraries.
 *
 * Default state = "All" (nothing selected → no library_ids sent → every library).
 * Multi-select: pick one or more enabled libraries via checkboxes in a small popover.
 * The parent hides this control entirely when only one enabled library exists.
 *
 * Styling matches the sibling sort / per-page selects (INPUT_STYLE). No new deps —
 * a lightweight self-managed popover (open state + click-outside) keeps it testable
 * in jsdom without relying on Radix pointer-capture behaviour.
 */

import { useEffect, useRef, useState } from 'react'
import type React from 'react'
import { Check, ChevronDown, HardDrive } from 'lucide-react'

import type { LibraryOut } from '@/lib/api'
import { INPUT_STYLE } from './styles'

interface LibraryFilterProps {
  /** Enabled libraries only. */
  libraries: LibraryOut[]
  /** Currently selected library ids (empty = All). */
  selected: number[]
  /** Toggle a single library id in/out of the selection. */
  onToggle: (id: number) => void
  /** Clear the selection back to All. */
  onClear: () => void
  /** Effective dark-mode flag — matches the sibling native selects' color-scheme. */
  isDark: boolean
}

export function LibraryFilter({ libraries, selected, onToggle, onClear, isDark }: LibraryFilterProps) {
  const [open, setOpen] = useState(false)
  const wrapRef = useRef<HTMLDivElement>(null)
  const selectedSet = new Set(selected)

  // Close on outside click or Escape.
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const label =
    selected.length === 0
      ? 'All libraries'
      : selected.length === 1
        ? (libraries.find((l) => l.id === selected[0])?.name ?? '1 library')
        : `${selected.length} libraries`

  const rowStyle: React.CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    width: '100%',
    padding: '7px 10px',
    borderRadius: 8,
    border: 'none',
    background: 'transparent',
    color: 'var(--aurora-text)',
    fontSize: 13,
    textAlign: 'left',
    cursor: 'pointer',
    transition: 'background 0.1s',
  }

  const renderRow = (checked: boolean, onClick: () => void, text: string, key: string | number) => (
    <button
      key={key}
      type="button"
      role="menuitemcheckbox"
      aria-checked={checked}
      onClick={onClick}
      style={rowStyle}
      onMouseEnter={(e) => {
        (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass-hover)'
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLButtonElement).style.background = 'transparent'
      }}
    >
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: 16,
          height: 16,
          flexShrink: 0,
          color: 'var(--aurora-accent)',
        }}
      >
        {checked && <Check size={14} />}
      </span>
      <span style={{ flex: 1, whiteSpace: 'nowrap' }}>{text}</span>
    </button>
  )

  return (
    <div ref={wrapRef} style={{ position: 'relative' }}>
      <button
        type="button"
        title="Filter by library"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        style={{
          ...INPUT_STYLE,
          width: 'auto',
          display: 'inline-flex',
          alignItems: 'center',
          gap: 6,
          padding: '5px 10px',
          cursor: 'pointer',
          colorScheme: isDark ? 'dark' : 'light',
        }}
      >
        <HardDrive size={13} style={{ color: 'var(--aurora-muted)', flexShrink: 0 }} />
        <span style={{ whiteSpace: 'nowrap' }}>{label}</span>
        <ChevronDown size={12} style={{ opacity: 0.6, flexShrink: 0 }} />
      </button>

      {open && (
        <div
          role="menu"
          style={{
            position: 'absolute',
            top: 'calc(100% + 6px)',
            left: 0,
            zIndex: 9999,
            minWidth: 200,
            maxHeight: 320,
            overflowY: 'auto',
            display: 'flex',
            flexDirection: 'column',
            gap: 2,
            padding: 6,
            background: 'var(--aurora-palette-bg)',
            border: '1px solid var(--aurora-palette-border)',
            borderRadius: 12,
            boxShadow: '0 8px 30px rgba(0,0,0,0.25), 0 0 0 1px var(--aurora-glass-border)',
            backdropFilter: 'blur(30px)',
            WebkitBackdropFilter: 'blur(30px)',
            colorScheme: isDark ? 'dark' : 'light',
          }}
        >
          {renderRow(selected.length === 0, onClear, 'All libraries', '__all__')}
          <div style={{ height: 1, background: 'var(--aurora-glass-border)', margin: '2px 0' }} />
          {libraries.map((lib) =>
            renderRow(selectedSet.has(lib.id), () => onToggle(lib.id), lib.name, lib.id),
          )}
        </div>
      )}
    </div>
  )
}
