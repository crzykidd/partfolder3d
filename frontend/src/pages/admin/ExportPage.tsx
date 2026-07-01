/**
 * ExportPage — admin catalog JSON export (Phase 9 — PRD §13).
 *
 * Route: /admin/export
 *
 * Provides a one-click download of the full catalog as a JSON file.
 * The export includes: items, tags, creators, print records.
 * Binary files (STL, images, etc.) are NOT included — only metadata.
 *
 * Implementation: a plain anchor tag pointing at GET /api/admin/export/catalog.
 * The backend streams a JSON attachment. No polling or state needed.
 *
 * Styling: Aurora aesthetic (B3b restyle — visual pass, all behavior preserved).
 */

import { Download } from 'lucide-react'
import {
  AdminPage, PageHeader,
  Card, SectionHeader,
} from '@/components/ui'

export function ExportPage() {
  return (
    <AdminPage>
      <PageHeader
        title="Export"
        description="Download a full snapshot of your catalog as a JSON file."
      />

      <Card style={{ maxWidth: 520 }}>
        <SectionHeader>Catalog JSON export</SectionHeader>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <p style={{ fontSize: 13, color: 'var(--aurora-muted)', margin: 0, lineHeight: 1.6 }}>
            Downloads the complete catalog metadata as a single JSON file —
            items, tags, creators, tag aliases, and print records. The export
            is generated on demand and may take a moment for large catalogs.
          </p>
          <p style={{ fontSize: 13, color: 'var(--aurora-muted)', margin: 0, lineHeight: 1.6 }}>
            <strong style={{ color: 'var(--aurora-text-dim)' }}>Binary files are not included.</strong>{' '}
            STL files, images, and other library assets are not part of this export.
          </p>

          <div>
            <a
              href="/api/admin/export/catalog"
              download
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                background: 'var(--aurora-accent)',
                color: '#fff',
                border: 'none',
                borderRadius: 8,
                padding: '8px 16px',
                fontSize: 13,
                fontWeight: 600,
                cursor: 'pointer',
                textDecoration: 'none',
                transition: 'opacity 0.15s',
              }}
              onMouseEnter={(e) => ((e.currentTarget as HTMLAnchorElement).style.opacity = '0.85')}
              onMouseLeave={(e) => ((e.currentTarget as HTMLAnchorElement).style.opacity = '1')}
            >
              <Download size={14} />
              Download Catalog JSON
            </a>
          </div>
        </div>
      </Card>
    </AdminPage>
  )
}
