/**
 * PublicSharePage — unauthenticated public view for a shared item or catalog.
 *
 * Route: /share/:token  (registered OUTSIDE AuthGuard)
 *
 * Security:
 * - Never imports AuthGuard, AuthContext, or any authenticated endpoint.
 * - Only calls /api/public/share/... endpoints.
 * - 403 (expired/revoked) → friendly "no longer available" message, no raw error.
 *
 * Scope behaviour:
 * - scope = "item_design"  → show item: title, description, tags, public print records,
 *   files list (via /files/{path}), ZIP download.
 * - scope = "full_site"    → show read-only catalog browse via /catalog.
 *   (The /api/public/share/{token} endpoint returns 400 for full_site; we detect
 *    this and fall back to the catalog view instead.)
 *
 * Styling: standalone Aurora screen (gradient bg + glass card, dark+light).
 * Public-facing — first impression matters.
 */

import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'

import * as api from '@/lib/api'
import { ApiError } from '@/lib/api'
import { mapBundleStatus, shouldContinuePolling, type ZipPollStatus } from '@/lib/catalog-utils'
import { formatPrintTime, formatFilamentLength, formatFilamentWeight, renderStars } from '@/lib/print-utils'
import { safeHref } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Style constants
// ---------------------------------------------------------------------------

const PAGE_STYLE: React.CSSProperties = {
  minHeight: '100vh',
  background: 'linear-gradient(135deg, var(--aurora-bg-from) 0%, var(--aurora-bg-to) 100%)',
}

const CARD_STYLE: React.CSSProperties = {
  background: 'var(--aurora-card)',
  border: '1px solid var(--aurora-card-border)',
  borderRadius: 12,
  backdropFilter: 'blur(16px)',
  WebkitBackdropFilter: 'blur(16px)',
}

const BTN_PRIMARY: React.CSSProperties = {
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
  transition: 'opacity 0.15s',
}

const BTN_GHOST: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 5,
  background: 'var(--aurora-glass)',
  border: '1px solid var(--aurora-glass-border)',
  borderRadius: 8,
  color: 'var(--aurora-text-dim)',
  padding: '6px 14px',
  fontSize: 12,
  fontWeight: 500,
  cursor: 'pointer',
  transition: 'opacity 0.15s',
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Public page header / brand bar
// ---------------------------------------------------------------------------

function PublicBar() {
  return (
    <div
      style={{
        borderBottom: '1px solid var(--aurora-divider)',
        background: 'var(--aurora-card)',
        backdropFilter: 'blur(16px)',
        WebkitBackdropFilter: 'blur(16px)',
        padding: '10px 24px',
        display: 'flex',
        alignItems: 'center',
        gap: 10,
      }}
    >
      <div
        aria-hidden="true"
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: 28,
          height: 28,
          borderRadius: 8,
          background: 'var(--aurora-accent)',
        }}
      >
        <span style={{ color: '#fff', fontWeight: 900, fontSize: 11, letterSpacing: '-0.03em' }}>PF</span>
      </div>
      <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--aurora-text)', letterSpacing: '-0.01em' }}>
        PartFolder 3D
      </span>
      <span
        style={{
          marginLeft: 4,
          fontSize: 11,
          fontWeight: 600,
          color: 'var(--aurora-accent)',
          background: 'rgba(15,164,171,0.10)',
          border: '1px solid rgba(15,164,171,0.25)',
          borderRadius: 20,
          padding: '2px 8px',
          letterSpacing: '0.04em',
          textTransform: 'uppercase',
        }}
      >
        Public Share
      </span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Public print record display (read-only)
// ---------------------------------------------------------------------------

function PublicPrintRecordCard({ record }: { record: api.PublicPrintRecord }) {
  return (
    <div style={{ ...CARD_STYLE, padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 6 }}>
        {/* Public badge */}
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            fontSize: 11,
            fontWeight: 600,
            background: 'rgba(22,163,74,0.10)',
            color: '#16a34a',
            border: '1px solid rgba(22,163,74,0.25)',
            borderRadius: 20,
            padding: '2px 8px',
          }}
          className="dark:text-green-300"
        >
          public
        </span>

        {record.success != null && (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              fontSize: 11,
              fontWeight: 600,
              borderRadius: 20,
              padding: '2px 8px',
              background: record.success ? 'rgba(22,163,74,0.10)' : 'rgba(220,38,38,0.10)',
              color: record.success ? '#16a34a' : 'var(--aurora-danger)',
              border: record.success ? '1px solid rgba(22,163,74,0.25)' : '1px solid rgba(220,38,38,0.25)',
            }}
          >
            {record.success ? '✓ Success' : '✗ Failed'}
          </span>
        )}

        {record.rating != null && (
          <span style={{ fontSize: 13, color: '#d97706' }}>{renderStars(record.rating)}</span>
        )}

        {record.date && (
          <span style={{ fontSize: 11, color: 'var(--aurora-muted)' }}>{record.date}</span>
        )}
      </div>

      {(record.printer || record.material || record.filament_color) && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 16px', fontSize: 12, color: 'var(--aurora-muted)' }}>
          {record.printer && <span>Printer: {record.printer}</span>}
          {record.material && <span>Material: {record.material}</span>}
          {record.filament_color && <span>Color: {record.filament_color}</span>}
          {record.nozzle_diameter != null && <span>Nozzle: {record.nozzle_diameter}mm</span>}
          {record.layer_height != null && <span>Layer: {record.layer_height}mm</span>}
          {record.supports != null && <span>Supports: {record.supports ? 'Yes' : 'No'}</span>}
        </div>
      )}

      {(record.filament_length_mm != null || record.estimated_print_time_s != null) && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 16px', fontSize: 12, color: 'var(--aurora-muted)' }}>
          {record.filament_length_mm != null && (
            <span>Filament: {formatFilamentLength(record.filament_length_mm)}</span>
          )}
          {record.filament_weight_g != null && (
            <span>Weight: {formatFilamentWeight(record.filament_weight_g)}</span>
          )}
          {record.estimated_print_time_s != null && (
            <span>Time: {formatPrintTime(record.estimated_print_time_s)}</span>
          )}
        </div>
      )}

      {record.note && (
        <p style={{ margin: 0, fontSize: 13, color: 'var(--aurora-text-dim)', lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
          {record.note}
        </p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Public ZIP download (same poll pattern as ItemPage)
// ---------------------------------------------------------------------------

interface PublicZipDownloadProps {
  token: string
}

function PublicZipDownload({ token }: PublicZipDownloadProps) {
  const [bundleId, setBundleId] = useState<string | null>(null)
  const [zipStatus, setZipStatus] = useState<ZipPollStatus>('idle')
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const stopPoll = useCallback(() => {
    if (pollRef.current !== null) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  const zipMutation = useMutation({
    mutationFn: () => api.queuePublicZip(token),
    onMutate: () => {
      setZipStatus('queued')
      setErrorMsg(null)
    },
    onSuccess: (bundle) => {
      setBundleId(bundle.id)
      setZipStatus(mapBundleStatus(bundle.status))
    },
    onError: () => {
      setZipStatus('failed')
      setErrorMsg('Failed to request ZIP.')
    },
  })

  useEffect(() => {
    if (!bundleId || !shouldContinuePolling(zipStatus)) {
      stopPoll()
      return
    }
    stopPoll()
    pollRef.current = setInterval(async () => {
      try {
        const bundle = await api.pollPublicZip(token, bundleId)
        const status = mapBundleStatus(bundle.status)
        setZipStatus(status)
        if (bundle.error_message) setErrorMsg(bundle.error_message)
        if (!shouldContinuePolling(status)) stopPoll()
      } catch {
        setZipStatus('failed')
        setErrorMsg('Polling failed.')
        stopPoll()
      }
    }, 2000)
    return stopPoll
  }, [bundleId, zipStatus, token, stopPoll])

  const handleDownload = useCallback(() => {
    if (bundleId && zipStatus === 'ready') {
      window.open(api.publicZipDownloadUrl(token, bundleId))
    }
  }, [bundleId, zipStatus, token])

  const zipLabel: Record<ZipPollStatus, string> = {
    idle: 'Download all as ZIP',
    queued: 'Queued…',
    building: 'Building ZIP…',
    ready: 'Download ZIP',
    failed: 'ZIP failed — retry?',
    expired: 'ZIP expired — retry?',
  }

  const isActive = zipStatus === 'queued' || zipStatus === 'building' || zipMutation.isPending
  const isClickable =
    zipStatus === 'ready'
      ? handleDownload
      : zipStatus === 'idle' || zipStatus === 'failed' || zipStatus === 'expired'
        ? () => zipMutation.mutate()
        : undefined

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
      <button
        onClick={isClickable}
        disabled={isActive}
        style={{ ...BTN_PRIMARY, opacity: isActive ? 0.6 : 1, cursor: isActive ? 'not-allowed' : 'pointer' }}
      >
        {zipLabel[zipStatus]}
      </button>
      {errorMsg && (
        <span style={{ fontSize: 12, color: 'var(--aurora-danger)' }}>{errorMsg}</span>
      )}
      {(zipStatus === 'queued' || zipStatus === 'building') && (
        <span style={{ fontSize: 12, color: 'var(--aurora-muted)' }} className="animate-pulse">
          Polling every 2 s…
        </span>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Public catalog view (full_site scope)
// ---------------------------------------------------------------------------

function PublicCatalogView({ token }: { token: string }) {
  const [page, setPage] = useState(1)
  const PER_PAGE = 20

  const { data, isLoading, isError } = useQuery({
    queryKey: ['public-catalog', token, page],
    queryFn: () => api.getPublicCatalog(token, { page, per_page: PER_PAGE }),
    staleTime: 60_000,
  })

  const totalPages = data ? Math.ceil(data.total / PER_PAGE) : 1

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div>
        <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800, color: 'var(--aurora-text)', letterSpacing: '-0.02em' }}>
          Shared Catalog
        </h1>
        <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--aurora-muted)' }}>Read-only public view.</p>
      </div>

      {isLoading && (
        <p style={{ fontSize: 13, color: 'var(--aurora-muted)' }} className="animate-pulse">Loading…</p>
      )}
      {isError && (
        <p style={{ fontSize: 13, color: 'var(--aurora-danger)' }}>Failed to load catalog.</p>
      )}

      {data && data.items.length === 0 && (
        <p style={{ fontSize: 13, color: 'var(--aurora-muted)', fontStyle: 'italic' }}>No items found.</p>
      )}

      {data && data.items.length > 0 && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {data.items.map((item) => (
              <div key={item.key} style={{ ...CARD_STYLE, padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 4 }}>
                <p style={{ margin: 0, fontSize: 13, fontWeight: 600, color: 'var(--aurora-text)' }}>{item.title}</p>
                <p style={{ margin: 0, fontFamily: 'monospace', fontSize: 11, color: 'var(--aurora-muted)' }}>{item.key}</p>
                {item.description && (
                  <p
                    style={{ margin: '4px 0 0', fontSize: 12, color: 'var(--aurora-muted)', overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}
                  >
                    {item.description}
                  </p>
                )}
              </div>
            ))}
          </div>

          {totalPages > 1 && (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <button
                disabled={page === 1}
                onClick={() => setPage((p) => p - 1)}
                style={{ ...BTN_GHOST, opacity: page === 1 ? 0.4 : 1, cursor: page === 1 ? 'not-allowed' : 'pointer' }}
              >
                ← Previous
              </button>
              <span style={{ fontSize: 12, color: 'var(--aurora-muted)' }}>
                Page {page} of {totalPages}
              </span>
              <button
                disabled={page === totalPages}
                onClick={() => setPage((p) => p + 1)}
                style={{ ...BTN_GHOST, opacity: page === totalPages ? 0.4 : 1, cursor: page === totalPages ? 'not-allowed' : 'pointer' }}
              >
                Next →
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function PublicSharePage() {
  const { token } = useParams<{ token: string }>()

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['public-share', token],
    queryFn: () => api.getPublicShare(token!),
    enabled: !!token,
    retry: (failureCount, err) => {
      // Don't retry on 403 or 404 — those are definitive
      if (err instanceof ApiError && (err.status === 403 || err.status === 404)) {
        return false
      }
      return failureCount < 1
    },
  })

  // Detect full_site scope: backend returns 400 "This link is for full-site browse"
  const isFullSite =
    isError &&
    error instanceof ApiError &&
    error.status === 400 &&
    String(error.message).includes('full-site')

  // Expired / revoked
  const isUnavailable =
    isError &&
    error instanceof ApiError &&
    (error.status === 403 || error.status === 404) &&
    !isFullSite

  if (isLoading) {
    return (
      <div style={PAGE_STYLE}>
        <PublicBar />
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 'calc(100vh - 52px)' }}>
          <p style={{ fontSize: 14, color: 'var(--aurora-muted)' }} className="animate-pulse">Loading…</p>
        </div>
      </div>
    )
  }

  if (isUnavailable) {
    return (
      <div style={PAGE_STYLE}>
        <PublicBar />
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 'calc(100vh - 52px)', padding: '32px 16px' }}>
          <div style={{ ...CARD_STYLE, padding: '40px 32px', maxWidth: 400, textAlign: 'center' }}>
            <div style={{ fontSize: 40, marginBottom: 16 }}>🔗</div>
            <h1 style={{ margin: '0 0 8px', fontSize: 18, fontWeight: 700, color: 'var(--aurora-text)' }}>
              Link no longer available
            </h1>
            <p style={{ margin: 0, fontSize: 13, color: 'var(--aurora-muted)', lineHeight: 1.6 }}>
              This share link has expired, been revoked, or does not exist.
            </p>
          </div>
        </div>
      </div>
    )
  }

  // Full-site share → render catalog view (no auth, no guards)
  if (isFullSite && token) {
    return (
      <div style={PAGE_STYLE}>
        <PublicBar />
        <div style={{ maxWidth: 1100, margin: '0 auto', padding: '28px 24px' }}>
          <PublicCatalogView token={token} />
        </div>
      </div>
    )
  }

  if (isError && !isFullSite) {
    return (
      <div style={PAGE_STYLE}>
        <PublicBar />
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 'calc(100vh - 52px)' }}>
          <p style={{ fontSize: 13, color: 'var(--aurora-danger)' }}>Failed to load share.</p>
        </div>
      </div>
    )
  }

  if (!data || !token) return null

  return (
    <div style={PAGE_STYLE}>
      <PublicBar />

      <div style={{ maxWidth: 860, margin: '0 auto', padding: '28px 24px', display: 'flex', flexDirection: 'column', gap: 24 }}>
        {/* Phase 15: Prominent modified-copy notice (only when modified + has source) */}
        {data.is_modified && data.source_url && (
          <div
            role="alert"
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: 12,
              padding: '14px 18px',
              borderRadius: 10,
              background: 'rgba(220,38,38,0.08)',
              border: '1.5px solid rgba(220,38,38,0.30)',
            }}
          >
            <span style={{ fontSize: 18, lineHeight: 1, flexShrink: 0 }} aria-hidden="true">⚠</span>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--aurora-danger)' }}>
                This is a modified copy — it differs from the original at{' '}
                <a
                  href={safeHref(data.source_url)}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ color: 'var(--aurora-accent)', textDecoration: 'underline', wordBreak: 'break-all' }}
                >
                  {data.source_site || data.source_url}
                </a>
              </span>
              <span style={{ fontSize: 11, color: 'var(--aurora-muted)' }}>
                The files shared here may have been altered from the version originally downloaded from that source.
              </span>
            </div>
          </div>
        )}

        {/* Title card */}
        <div style={{ ...CARD_STYLE, padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: 14 }}>
          <h1 style={{ margin: 0, fontSize: 24, fontWeight: 800, color: 'var(--aurora-text)', letterSpacing: '-0.02em' }}>
            {data.title}
          </h1>

          {/* Tags */}
          {data.tags.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 6px' }}>
              {data.tags.map((tag) => (
                <span
                  key={tag}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    fontSize: 11,
                    fontWeight: 600,
                    background: 'var(--aurora-pill)',
                    border: '1px solid var(--aurora-pill-border)',
                    color: 'var(--aurora-accent)',
                    borderRadius: 20,
                    padding: '2px 10px',
                  }}
                >
                  {tag}
                </span>
              ))}
            </div>
          )}

          {data.description && (
            <p style={{ margin: 0, fontSize: 14, color: 'var(--aurora-text-dim)', lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>
              {data.description}
            </p>
          )}

          {(data.source_url || data.license || data.source_site) && (
            <dl
              style={{
                display: 'grid',
                gridTemplateColumns: 'auto 1fr',
                gap: '6px 12px',
                fontSize: 13,
                margin: 0,
              }}
            >
              {data.source_url && (
                <>
                  <dt style={{ color: 'var(--aurora-muted)', fontWeight: 600 }}>Source</dt>
                  <dd style={{ margin: 0 }}>
                    <a
                      href={safeHref(data.source_url)}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ color: 'var(--aurora-accent)', textDecoration: 'none', wordBreak: 'break-all' }}
                    >
                      {data.source_url}
                    </a>
                  </dd>
                </>
              )}
              {data.license && (
                <>
                  <dt style={{ color: 'var(--aurora-muted)', fontWeight: 600 }}>License</dt>
                  <dd style={{ margin: 0, color: 'var(--aurora-text)' }}>{data.license}</dd>
                </>
              )}
              {data.source_site && (
                <>
                  <dt style={{ color: 'var(--aurora-muted)', fontWeight: 600 }}>Site</dt>
                  <dd style={{ margin: 0, color: 'var(--aurora-text)' }}>{data.source_site}</dd>
                </>
              )}
            </dl>
          )}
        </div>

        {/* Downloads */}
        <div style={{ ...CARD_STYLE, padding: '20px 24px' }}>
          <h2 style={{ margin: '0 0 14px', fontSize: 14, fontWeight: 700, color: 'var(--aurora-text)', textTransform: 'uppercase', letterSpacing: '0.07em' }}>
            Downloads
          </h2>
          <PublicZipDownload token={token} />
        </div>

        {/* Public print records */}
        {data.public_print_records.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <h2 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: 'var(--aurora-text)', textTransform: 'uppercase', letterSpacing: '0.07em' }}>
              Print History ({data.public_print_records.length})
            </h2>
            {data.public_print_records.map((rec) => (
              <PublicPrintRecordCard key={rec.id} record={rec} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
