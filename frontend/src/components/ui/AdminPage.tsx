/**
 * AdminPage + PageHeader — shared Aurora admin page wrapper.
 *
 * Usage:
 *   <AdminPage>
 *     <PageHeader title="Jobs" meta="42 jobs" actions={<Button variant="primary">…</Button>} />
 *     …content…
 *   </AdminPage>
 */

import React from 'react'

// ---------------------------------------------------------------------------
// PageHeader
// ---------------------------------------------------------------------------

interface PageHeaderProps {
  title: string
  /** Subtitle shown below the title in muted text */
  description?: string
  /** Short metadata line (e.g. count) shown below title/description */
  meta?: string
  /** Right-aligned slot — buttons, badges, refresh links */
  actions?: React.ReactNode
}

export function PageHeader({ title, description, meta, actions }: PageHeaderProps) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        <h1
          style={{
            fontSize: 22,
            fontWeight: 800,
            color: 'var(--aurora-text)',
            letterSpacing: '-0.02em',
            margin: 0,
          }}
        >
          {title}
        </h1>
        {description && (
          <p
            style={{
              marginTop: 4,
              fontSize: 13,
              color: 'var(--aurora-muted)',
              margin: '4px 0 0',
              lineHeight: 1.5,
            }}
          >
            {description}
          </p>
        )}
        {meta && (
          <p
            style={{
              marginTop: description ? 2 : 4,
              fontSize: 12,
              color: 'var(--aurora-muted)',
              margin: `${description ? 2 : 4}px 0 0`,
            }}
          >
            {meta}
          </p>
        )}
      </div>
      {actions && (
        <div className="flex items-center gap-2 shrink-0">{actions}</div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// AdminPage
// ---------------------------------------------------------------------------

interface AdminPageProps {
  children: React.ReactNode
  /** Extra gap override; defaults to gap-6 */
  gap?: number
}

export function AdminPage({ children, gap = 24 }: AdminPageProps) {
  return (
    <div
      className="flex flex-col"
      style={{ gap, color: 'var(--aurora-text)' }}
    >
      {children}
    </div>
  )
}
