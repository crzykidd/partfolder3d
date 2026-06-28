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
 * UI: Tailwind + CSS-variable theme. No TanStack Query needed (direct link).
 */

export function ExportPage() {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold">Export</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Download a full snapshot of your catalog as a JSON file.
        </p>
      </div>

      {/* Export card */}
      <div className="rounded-lg border border-border bg-card p-6 space-y-4 max-w-lg">
        <div>
          <h2 className="text-base font-semibold">Catalog JSON export</h2>
          <p className="mt-1.5 text-sm text-muted-foreground">
            Downloads the complete catalog metadata as a single JSON file —
            items, tags, creators, tag aliases, and print records. The export
            is generated on demand and may take a moment for large catalogs.
          </p>
          <p className="mt-2 text-sm text-muted-foreground">
            <strong>Binary files are not included.</strong> STL files, images,
            and other library assets are not part of this export.
          </p>
        </div>

        <a
          href="/api/admin/export/catalog"
          download
          className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 transition-colors"
        >
          Download Catalog JSON
        </a>
      </div>
    </div>
  )
}
