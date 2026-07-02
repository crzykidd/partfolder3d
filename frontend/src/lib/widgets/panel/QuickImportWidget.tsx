/**
 * QuickImportWidget — panel widget containing the Quick Import flow.
 *
 * Reuses the AddAssetModal (upload or URL → /import/:sessionId).
 * This is the default panel widget for all roles.
 */

import { useState } from 'react'
import { PlusCircle, Upload, Link } from 'lucide-react'

import { AddAssetModal } from '@/components/AddAssetModal'

export function QuickImportWidget() {
  const [modalOpen, setModalOpen] = useState(false)

  return (
    <>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
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
            boxShadow: '0 4px 16px var(--aurora-accent-glow)',
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
        {[
          {
            icon: <Upload size={14} style={{ color: 'var(--aurora-accent)', flexShrink: 0 }} />,
            label: 'Upload Files',
            sub: 'STL, 3MF, OBJ, STEP…',
          },
          {
            icon: <Link size={14} style={{ color: 'var(--aurora-accent)', flexShrink: 0 }} />,
            label: 'From URL',
            sub: 'Thingiverse, Printables…',
          },
        ].map(({ icon, label, sub }) => (
          <button
            key={label}
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
              const el = e.currentTarget as HTMLButtonElement
              el.style.background = 'var(--aurora-glass-hover)'
              el.style.borderColor = 'var(--aurora-pill-border)'
              el.style.color = 'var(--aurora-text)'
            }}
            onMouseLeave={(e) => {
              const el = e.currentTarget as HTMLButtonElement
              el.style.background = 'var(--aurora-card)'
              el.style.borderColor = 'var(--aurora-card-border)'
              el.style.color = 'var(--aurora-text-dim)'
            }}
          >
            {icon}
            <div>
              <div style={{ fontWeight: 600, fontSize: 12, marginBottom: 1 }}>{label}</div>
              <div style={{ fontSize: 11, color: 'var(--aurora-muted)' }}>{sub}</div>
            </div>
          </button>
        ))}

        {/* Divider */}
        <div style={{ height: 1, background: 'var(--aurora-divider)', marginTop: 4 }} />

        {/* Tip */}
        <p style={{ fontSize: 11, color: 'var(--aurora-muted)', lineHeight: 1.5, margin: 0 }}>
          After upload, the import wizard walks you through metadata, tags, and file
          classification.
        </p>
      </div>

      <AddAssetModal open={modalOpen} onClose={() => setModalOpen(false)} />
    </>
  )
}
