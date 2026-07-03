import React from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'

import { useLocalStorage } from '@/hooks/useLocalStorage'
import { AURORA_CARD, AURORA_SECTION_HEADER } from './styles'

// ---------------------------------------------------------------------------
// Small shared section wrapper used across the item detail page.
// Optionally collapsible, with the collapsed state remembered in localStorage
// (keyed by `storageKey`) so it persists across item pages / reloads.
// ---------------------------------------------------------------------------

interface AuroraSectionProps {
  title: string
  children: React.ReactNode
  /** When true, the header toggles the body open/closed. */
  collapsible?: boolean
  /** localStorage key used to remember the collapsed state across page views. */
  storageKey?: string
  /** Collapsed state when nothing is stored yet. */
  defaultCollapsed?: boolean
}

export function AuroraSection({
  title,
  children,
  collapsible = false,
  storageKey,
  defaultCollapsed = false,
}: AuroraSectionProps) {
  const [collapsed, setCollapsed] = useLocalStorage<boolean>(
    storageKey ?? `partfolder3d-section:${title}`,
    defaultCollapsed,
  )

  if (!collapsible) {
    return (
      <section style={{ ...AURORA_CARD, padding: '18px 20px' }}>
        <div style={AURORA_SECTION_HEADER as React.CSSProperties}>{title}</div>
        {children}
      </section>
    )
  }

  return (
    <section style={{ ...AURORA_CARD, padding: '18px 20px' }}>
      <button
        type="button"
        onClick={() => setCollapsed(!collapsed)}
        aria-expanded={!collapsed}
        style={{
          ...(AURORA_SECTION_HEADER as React.CSSProperties),
          marginBottom: collapsed ? 0 : (AURORA_SECTION_HEADER.marginBottom as number),
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          width: '100%',
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          textAlign: 'left',
          padding: 0,
          fontFamily: 'inherit',
        }}
      >
        {collapsed ? <ChevronRight size={13} /> : <ChevronDown size={13} />}
        {title}
      </button>
      {!collapsed && children}
    </section>
  )
}
