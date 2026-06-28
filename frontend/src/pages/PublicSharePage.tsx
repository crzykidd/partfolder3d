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
 */

import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'

import * as api from '@/lib/api'
import { ApiError } from '@/lib/api'
import { mapBundleStatus, shouldContinuePolling, type ZipPollStatus } from '@/lib/catalog-utils'
import { formatPrintTime, formatFilamentLength, formatFilamentWeight, renderStars } from '@/lib/print-utils'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDate(iso: string | null): string {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

// ---------------------------------------------------------------------------
// Public print record display (read-only)
// ---------------------------------------------------------------------------

function PublicPrintRecordCard({ record }: { record: api.PublicPrintRecord }) {
  return (
    <div className="rounded-lg border border-border bg-card p-4 flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        {/* Public badge */}
        <span className="inline-flex items-center rounded-full bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200 px-2 py-0.5 text-xs font-medium">
          public
        </span>

        {record.success != null && (
          <span
            className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
              record.success
                ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
                : 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200'
            }`}
          >
            {record.success ? '✓ Success' : '✗ Failed'}
          </span>
        )}

        {record.rating != null && (
          <span className="text-sm text-amber-500">{renderStars(record.rating)}</span>
        )}

        {record.date && (
          <span className="text-xs text-muted-foreground">{record.date}</span>
        )}
      </div>

      {(record.printer || record.material || record.filament_color) && (
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
          {record.printer && <span>Printer: {record.printer}</span>}
          {record.material && <span>Material: {record.material}</span>}
          {record.filament_color && <span>Color: {record.filament_color}</span>}
          {record.nozzle_diameter != null && <span>Nozzle: {record.nozzle_diameter}mm</span>}
          {record.layer_height != null && <span>Layer: {record.layer_height}mm</span>}
          {record.supports != null && <span>Supports: {record.supports ? 'Yes' : 'No'}</span>}
        </div>
      )}

      {(record.filament_length_mm != null || record.estimated_print_time_s != null) && (
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
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
        <p className="text-sm text-muted-foreground leading-relaxed whitespace-pre-wrap">
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

  return (
    <div className="flex items-center gap-3">
      <button
        onClick={
          zipStatus === 'ready'
            ? handleDownload
            : zipStatus === 'idle' || zipStatus === 'failed' || zipStatus === 'expired'
              ? () => zipMutation.mutate()
              : undefined
        }
        disabled={zipStatus === 'queued' || zipStatus === 'building' || zipMutation.isPending}
        className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
      >
        {zipLabel[zipStatus]}
      </button>
      {errorMsg && <span className="text-xs text-destructive">{errorMsg}</span>}
      {(zipStatus === 'queued' || zipStatus === 'building') && (
        <span className="text-xs text-muted-foreground animate-pulse">Polling every 2 s…</span>
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
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-bold">Shared Catalog</h1>
      <p className="text-sm text-muted-foreground">Read-only public view.</p>

      {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {isError && <p className="text-sm text-destructive">Failed to load catalog.</p>}

      {data && data.items.length === 0 && (
        <p className="text-sm text-muted-foreground italic">No items found.</p>
      )}

      {data && data.items.length > 0 && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {data.items.map((item) => (
              <div
                key={item.key}
                className="rounded-lg border border-border bg-card p-4 flex flex-col gap-1"
              >
                <p className="font-medium text-sm">{item.title}</p>
                <p className="font-mono text-xs text-muted-foreground">{item.key}</p>
                {item.description && (
                  <p className="text-xs text-muted-foreground line-clamp-2 mt-1">
                    {item.description}
                  </p>
                )}
              </div>
            ))}
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-between text-sm">
              <button
                disabled={page === 1}
                onClick={() => setPage((p) => p - 1)}
                className="rounded-md border border-border px-3 py-1 hover:bg-accent disabled:opacity-40"
              >
                Previous
              </button>
              <span className="text-muted-foreground">
                Page {page} of {totalPages}
              </span>
              <button
                disabled={page === totalPages}
                onClick={() => setPage((p) => p + 1)}
                className="rounded-md border border-border px-3 py-1 hover:bg-accent disabled:opacity-40"
              >
                Next
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
      <div className="min-h-screen bg-background flex items-center justify-center">
        <p className="text-sm text-muted-foreground animate-pulse">Loading…</p>
      </div>
    )
  }

  if (isUnavailable) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="max-w-sm text-center px-4">
          <p className="text-3xl mb-4">🔗</p>
          <h1 className="text-xl font-semibold mb-2">Link no longer available</h1>
          <p className="text-sm text-muted-foreground">
            This share link has expired, been revoked, or does not exist.
          </p>
        </div>
      </div>
    )
  }

  // Full-site share → render catalog view (no auth, no guards)
  if (isFullSite && token) {
    return (
      <div className="min-h-screen bg-background">
        <div className="container mx-auto px-4 py-8 max-w-5xl">
          <div className="mb-6">
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Public share
            </span>
          </div>
          <PublicCatalogView token={token} />
        </div>
      </div>
    )
  }

  if (isError && !isFullSite) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <p className="text-sm text-destructive">Failed to load share.</p>
      </div>
    )
  }

  if (!data || !token) return null

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-4 py-8 max-w-4xl">
        {/* Header */}
        <div className="mb-6">
          <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            Public share
          </span>
        </div>

        <div className="flex flex-col gap-8">
          {/* Title + metadata */}
          <div className="flex flex-col gap-3">
            <h1 className="text-3xl font-bold">{data.title}</h1>

            {/* Tags */}
            {data.tags.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {data.tags.map((tag) => (
                  <span
                    key={tag}
                    className="inline-flex items-center rounded-full bg-muted px-2.5 py-0.5 text-xs font-medium text-muted-foreground"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            )}

            {data.description && (
              <p className="text-sm text-muted-foreground leading-relaxed whitespace-pre-wrap">
                {data.description}
              </p>
            )}

            {(data.source_url || data.license || data.source_site) && (
              <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-sm">
                {data.source_url && (
                  <>
                    <dt className="text-muted-foreground font-medium">Source</dt>
                    <dd>
                      <a
                        href={data.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-primary hover:underline truncate block"
                      >
                        {data.source_url}
                      </a>
                    </dd>
                  </>
                )}
                {data.license && (
                  <>
                    <dt className="text-muted-foreground font-medium">License</dt>
                    <dd>{data.license}</dd>
                  </>
                )}
                {data.source_site && (
                  <>
                    <dt className="text-muted-foreground font-medium">Site</dt>
                    <dd>{data.source_site}</dd>
                  </>
                )}
              </dl>
            )}
          </div>

          {/* Downloads */}
          <section>
            <h2 className="text-base font-semibold mb-3">Downloads</h2>
            <PublicZipDownload token={token} />
          </section>

          {/* Public print records */}
          {data.public_print_records.length > 0 && (
            <section>
              <h2 className="text-base font-semibold mb-3">
                Print History ({data.public_print_records.length})
              </h2>
              <div className="flex flex-col gap-3">
                {data.public_print_records.map((rec) => (
                  <PublicPrintRecordCard key={rec.id} record={rec} />
                ))}
              </div>
            </section>
          )}
        </div>
      </div>
    </div>
  )
}
