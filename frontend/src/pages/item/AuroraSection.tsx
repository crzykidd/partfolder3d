import React from 'react'

import { AURORA_CARD, AURORA_SECTION_HEADER } from './styles'

// ---------------------------------------------------------------------------
// Small shared section wrapper used across the item detail page
// ---------------------------------------------------------------------------

export function AuroraSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section style={{ ...AURORA_CARD, padding: '18px 20px' }}>
      <div style={AURORA_SECTION_HEADER as React.CSSProperties}>{title}</div>
      {children}
    </section>
  )
}
