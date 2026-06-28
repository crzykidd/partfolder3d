/**
 * EmptyState — Aurora empty state component.
 *
 * Displays an optional icon, title, and description when a list or table
 * has no items. Used inside or outside DataTable.
 *
 * Reusable by B3b.
 */

import React from 'react'

interface EmptyStateProps {
  icon?: React.ReactNode
  title: string
  description?: string
}

export function EmptyState({ icon, title, description }: EmptyStateProps) {
  return (
    <div
      style={{
        padding: '48px 24px',
        textAlign: 'center',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 10,
      }}
    >
      {icon && (
        <div style={{ color: 'var(--aurora-muted)', marginBottom: 4 }}>
          {icon}
        </div>
      )}
      <p style={{ fontSize: 14, fontWeight: 600, color: 'var(--aurora-text)', margin: 0 }}>
        {title}
      </p>
      {description && (
        <p style={{ fontSize: 12, color: 'var(--aurora-muted)', margin: 0, maxWidth: 360, lineHeight: 1.6 }}>
          {description}
        </p>
      )}
    </div>
  )
}
