/**
 * QuickImportRail — collapsible right-side panel with a functional Quick Import widget.
 *
 * Uses the real AddAssetModal (upload or URL → /import/:sessionId flow).
 * Collapsed state persisted via the parent shell (localStorage key: 'aurora-rail-collapsed').
 *
 * Hidden on narrow viewports (< 900px) via a responsive CSS class.
 * In collapsed mode it shows a thin toggle strip.
 */

import React, { useState } from 'react'
import { PlusCircle, ChevronsRight, ChevronsLeft, Upload, Link } from 'lucide-react'

import { AddAssetModal } from '@/components/AddAssetModal'

interface QuickImportRailProps {
  collapsed: boolean
  onToggle: () => void
}

export function QuickImportRail({ collapsed, onToggle }: QuickImportRailProps) {
  const [modalOpen, setModalOpen] = useState(false)

  return (
    <>
      {/* Rail panel — hidden on narrow screens via media query via className */}
      <aside
        className="aurora-rail"
        style={{
          width: collapsed ? 36 : 260,
          minWidth: collapsed ? 36 : 260,
          background: 'var(--aurora-glass)',
          backdropFilter: 'blur(24px)',
          WebkitBackdropFilter: 'blur(24px)',
          borderLeft: '1px solid var(--aurora-divider)',
          display: 'flex',
          flexDirection: 'column',
          transition: 'width 0.22s cubic-bezier(0.4,0,0.2,1), min-width 0.22s cubic-bezier(0.4,0,0.2,1)',
          overflow: 'hidden',
          flexShrink: 0,
        } as React.CSSProperties}
      >
        {/* Toggle strip */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: collapsed ? 'center' : 'space-between',
            padding: collapsed ? '12px 0' : '10px 14px',
            borderBottom: '1px solid var(--aurora-divider)',
            flexShrink: 0,
          }}
        >
          {!collapsed && (
            <span
              style={{
                fontSize: 10,
                fontWeight: 700,
                color: 'var(--aurora-muted)',
                letterSpacing: '0.1em',
                textTransform: 'uppercase',
              }}
            >
              Quick Import
            </span>
          )}
          <button
            onClick={onToggle}
            title={collapsed ? 'Expand panel' : 'Collapse panel'}
            style={{
              background: 'var(--aurora-glass)',
              border: '1px solid var(--aurora-glass-border)',
              borderRadius: 8,
              cursor: 'pointer',
              color: 'var(--aurora-muted)',
              display: 'flex',
              padding: '4px 5px',
              transition: 'all 0.15s',
            }}
            onMouseEnter={(e) => {
              ;(e.currentTarget as HTMLButtonElement).style.borderColor =
                'var(--aurora-pill-border)'
              ;(e.currentTarget as HTMLButtonElement).style.color = 'var(--aurora-accent)'
            }}
            onMouseLeave={(e) => {
              ;(e.currentTarget as HTMLButtonElement).style.borderColor =
                'var(--aurora-glass-border)'
              ;(e.currentTarget as HTMLButtonElement).style.color = 'var(--aurora-muted)'
            }}
          >
            {collapsed ? <ChevronsLeft size={13} /> : <ChevronsRight size={13} />}
          </button>
        </div>

        {/* Content (only when expanded) */}
        {!collapsed && (
          <div style={{ padding: '14px', overflowY: 'auto', flex: 1 }}>
            {/* Primary CTA */}
            <button
              onClick={() => setModalOpen(true)}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 8,
                width: '100%',
                padding: '10px 14px',
                background: 'var(--aurora-accent)',
                color: 'var(--aurora-accent-fg)',
                border: 'none',
                borderRadius: 10,
                fontSize: 13,
                fontWeight: 700,
                cursor: 'pointer',
                boxShadow: `0 4px 16px var(--aurora-accent-glow)`,
                marginBottom: 12,
                transition: 'opacity 0.15s',
              }}
              onMouseEnter={(e) => {
                ;(e.currentTarget as HTMLButtonElement).style.opacity = '0.9'
              }}
              onMouseLeave={(e) => {
                ;(e.currentTarget as HTMLButtonElement).style.opacity = '1'
              }}
            >
              <PlusCircle size={15} />
              Add Asset
            </button>

            {/* Quick-access tiles */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <button
                onClick={() => setModalOpen(true)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  width: '100%',
                  padding: '10px 12px',
                  background: 'var(--aurora-card)',
                  border: '1px solid var(--aurora-card-border)',
                  borderRadius: 10,
                  cursor: 'pointer',
                  fontSize: 13,
                  color: 'var(--aurora-text-dim)',
                  textAlign: 'left',
                  transition: 'all 0.15s',
                }}
                onMouseEnter={(e) => {
                  ;(e.currentTarget as HTMLButtonElement).style.background =
                    'var(--aurora-glass-hover)'
                  ;(e.currentTarget as HTMLButtonElement).style.borderColor =
                    'var(--aurora-pill-border)'
                  ;(e.currentTarget as HTMLButtonElement).style.color = 'var(--aurora-text)'
                }}
                onMouseLeave={(e) => {
                  ;(e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-card)'
                  ;(e.currentTarget as HTMLButtonElement).style.borderColor =
                    'var(--aurora-card-border)'
                  ;(e.currentTarget as HTMLButtonElement).style.color = 'var(--aurora-text-dim)'
                }}
              >
                <Upload size={14} style={{ color: 'var(--aurora-accent)', flexShrink: 0 }} />
                <div>
                  <div style={{ fontWeight: 600, fontSize: 12, marginBottom: 1 }}>Upload Files</div>
                  <div style={{ fontSize: 11, color: 'var(--aurora-muted)' }}>
                    STL, 3MF, OBJ, STEP…
                  </div>
                </div>
              </button>

              <button
                onClick={() => setModalOpen(true)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  width: '100%',
                  padding: '10px 12px',
                  background: 'var(--aurora-card)',
                  border: '1px solid var(--aurora-card-border)',
                  borderRadius: 10,
                  cursor: 'pointer',
                  fontSize: 13,
                  color: 'var(--aurora-text-dim)',
                  textAlign: 'left',
                  transition: 'all 0.15s',
                }}
                onMouseEnter={(e) => {
                  ;(e.currentTarget as HTMLButtonElement).style.background =
                    'var(--aurora-glass-hover)'
                  ;(e.currentTarget as HTMLButtonElement).style.borderColor =
                    'var(--aurora-pill-border)'
                  ;(e.currentTarget as HTMLButtonElement).style.color = 'var(--aurora-text)'
                }}
                onMouseLeave={(e) => {
                  ;(e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-card)'
                  ;(e.currentTarget as HTMLButtonElement).style.borderColor =
                    'var(--aurora-card-border)'
                  ;(e.currentTarget as HTMLButtonElement).style.color = 'var(--aurora-text-dim)'
                }}
              >
                <Link size={14} style={{ color: 'var(--aurora-accent)', flexShrink: 0 }} />
                <div>
                  <div style={{ fontWeight: 600, fontSize: 12, marginBottom: 1 }}>From URL</div>
                  <div style={{ fontSize: 11, color: 'var(--aurora-muted)' }}>
                    Thingiverse, Printables…
                  </div>
                </div>
              </button>
            </div>

            {/* Divider */}
            <div
              style={{
                margin: '14px 0',
                height: 1,
                background: 'var(--aurora-divider)',
              }}
            />

            {/* Tip */}
            <p
              style={{
                fontSize: 11,
                color: 'var(--aurora-muted)',
                lineHeight: 1.5,
                margin: 0,
              }}
            >
              After upload, the import wizard walks you through metadata, tags, and file
              classification.
            </p>
          </div>
        )}
      </aside>

      {/* The real modal — handles upload + URL flows → navigates to /import/:sessionId */}
      <AddAssetModal open={modalOpen} onClose={() => setModalOpen(false)} />
    </>
  )
}
