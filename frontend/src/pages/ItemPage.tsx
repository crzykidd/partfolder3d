/**
 * ItemPage — detail view for a single catalog item.
 *
 * Sections:
 * - Image carousel (click → full-size, set default, default shown first + badged)
 * - Metadata (title, creator linked, source URL, license, description, timestamps)
 * - Tags as chips (click → /catalog?tags={name})
 * - Dir path + prefix rewrite + copy button (PRD §3.3)
 * - Downloads: individual files + queued ZIP with 2-second poll (PRD §11)
 * - Placeholders: Print History (Phase 7), Sharing (Phase 7)
 */

import React, { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'

import * as api from '@/lib/api'
import { mapBundleStatus, rewritePath, shouldContinuePolling, type ZipPollStatus } from '@/lib/catalog-utils'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

// ---------------------------------------------------------------------------
// Image carousel
// ---------------------------------------------------------------------------

interface ImageCarouselProps {
  images: api.ImageOut[]
  itemKey: string
  onSetDefault: (imageId: number) => void
  isSettingDefault: boolean
}

function ImageCarousel({ images, itemKey, onSetDefault, isSettingDefault }: ImageCarouselProps) {
  const [activeIdx, setActiveIdx] = useState(0)
  const [lightbox, setLightbox] = useState(false)

  if (!images.length) {
    return (
      <div className="flex h-64 items-center justify-center rounded-lg border border-border bg-muted/40">
        <p className="text-sm text-muted-foreground">No images</p>
      </div>
    )
  }

  const active = images[activeIdx]

  return (
    <div className="flex flex-col gap-3">
      {/* Main image */}
      <div className="relative rounded-lg overflow-hidden bg-muted/40 aspect-video flex items-center justify-center">
        <img
          src={`/api/items/${itemKey}/files/${active.path}`}
          alt={`Image ${activeIdx + 1}`}
          className="max-h-80 max-w-full object-contain cursor-zoom-in"
          onClick={() => setLightbox(true)}
          loading="lazy"
        />
        {active.is_default && (
          <span className="absolute top-2 left-2 rounded-full bg-primary px-2 py-0.5 text-xs font-medium text-primary-foreground">
            Default
          </span>
        )}
        {!active.is_default && (
          <button
            onClick={() => onSetDefault(active.id)}
            disabled={isSettingDefault}
            className="absolute top-2 right-2 rounded-full bg-background/80 px-2 py-0.5 text-xs font-medium hover:bg-background transition-colors disabled:opacity-50 border border-border"
          >
            Set as default
          </button>
        )}
      </div>

      {/* Thumbnail strip */}
      {images.length > 1 && (
        <div className="flex gap-2 overflow-x-auto py-1">
          {images.map((img, idx) => (
            <button
              key={img.id}
              onClick={() => setActiveIdx(idx)}
              className={`shrink-0 h-16 w-16 rounded overflow-hidden border-2 transition-colors ${
                idx === activeIdx ? 'border-primary' : 'border-border hover:border-muted-foreground'
              }`}
            >
              <img
                src={`/api/items/${itemKey}/files/${img.path}`}
                alt={`Thumbnail ${idx + 1}`}
                className="h-full w-full object-cover"
                loading="lazy"
              />
            </button>
          ))}
        </div>
      )}

      {/* Lightbox */}
      {lightbox && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
          onClick={() => setLightbox(false)}
        >
          <img
            src={`/api/items/${itemKey}/files/${active.path}`}
            alt={`Full size ${activeIdx + 1}`}
            className="max-h-full max-w-full object-contain"
            onClick={(e) => e.stopPropagation()}
          />
          <button
            onClick={() => setLightbox(false)}
            className="absolute top-4 right-4 text-white/80 hover:text-white text-2xl"
          >
            ✕
          </button>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Path display + copy
// ---------------------------------------------------------------------------

interface PathDisplayProps {
  dirPath: string
  itemKey: string
}

function PathDisplay({ dirPath, itemKey }: PathDisplayProps) {
  const [copied, setCopied] = useState(false)

  const { data: prefixData } = useQuery({
    queryKey: ['path-prefix'],
    queryFn: api.getPathPrefix,
    staleTime: 60_000,
  })

  const displayPath = rewritePath(dirPath, prefixData?.path_prefix)

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(displayPath)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Clipboard API unavailable (non-HTTPS in dev)
    }
  }, [displayPath])

  return (
    <div className="flex items-center gap-2 rounded-md border border-border bg-muted/40 px-3 py-2">
      <code className="flex-1 truncate text-xs font-mono text-muted-foreground">
        {displayPath}
      </code>
      <button
        onClick={handleCopy}
        className="shrink-0 rounded px-2 py-1 text-xs hover:bg-accent transition-colors"
        title="Copy path"
      >
        {copied ? '✓ Copied' : 'Copy'}
      </button>
      <Link
        to={`/settings?focus=path-prefix&from=/items/${itemKey}`}
        className="shrink-0 text-xs text-muted-foreground hover:text-primary"
        title="Configure path prefix"
      >
        Edit prefix
      </Link>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Downloads section
// ---------------------------------------------------------------------------

interface DownloadsSectionProps {
  itemKey: string
  files: api.FileOut[]
}

function DownloadsSection({ itemKey, files }: DownloadsSectionProps) {
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
    mutationFn: () => api.queueZip(itemKey),
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

  // Poll when we have a bundleId and status is queued/building
  useEffect(() => {
    if (!bundleId || !shouldContinuePolling(zipStatus)) {
      stopPoll()
      return
    }

    stopPoll()
    pollRef.current = setInterval(async () => {
      try {
        const bundle = await api.pollZip(itemKey, bundleId)
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
  }, [bundleId, zipStatus, itemKey, stopPoll])

  const handleDownloadZip = useCallback(() => {
    if (bundleId && zipStatus === 'ready') {
      window.open(api.zipDownloadUrl(itemKey, bundleId))
    }
  }, [bundleId, zipStatus, itemKey])

  const zipLabel: Record<ZipPollStatus, string> = {
    idle: 'Download all as ZIP',
    queued: 'Queued…',
    building: 'Building ZIP…',
    ready: 'Download ZIP',
    failed: 'ZIP failed — retry?',
    expired: 'ZIP expired — retry?',
  }

  return (
    <div className="flex flex-col gap-3">
      {/* Individual files */}
      {files.length === 0 ? (
        <p className="text-sm text-muted-foreground italic">No files catalogued yet.</p>
      ) : (
        <ul className="divide-y divide-border rounded-lg border border-border overflow-hidden">
          {files.map((file) => (
            <li key={file.id} className="flex items-center justify-between px-4 py-2.5 hover:bg-muted/30">
              <div className="flex flex-col gap-0.5">
                <span className="text-sm font-medium font-mono">{file.path}</span>
                <span className="text-xs text-muted-foreground">
                  {file.role} · {formatBytes(file.size)}
                </span>
              </div>
              <a
                href={api.fileDownloadUrl(itemKey, file.path)}
                download
                className="shrink-0 rounded border border-border px-3 py-1 text-xs font-medium hover:bg-accent transition-colors"
              >
                Download
              </a>
            </li>
          ))}
        </ul>
      )}

      {/* ZIP download */}
      <div className="flex items-center gap-3">
        <button
          onClick={
            zipStatus === 'ready'
              ? handleDownloadZip
              : zipStatus === 'idle' || zipStatus === 'failed' || zipStatus === 'expired'
                ? () => zipMutation.mutate()
                : undefined
          }
          disabled={zipStatus === 'queued' || zipStatus === 'building' || zipMutation.isPending}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
        >
          {zipLabel[zipStatus]}
        </button>
        {errorMsg && (
          <span className="text-xs text-destructive">{errorMsg}</span>
        )}
        {(zipStatus === 'queued' || zipStatus === 'building') && (
          <span className="text-xs text-muted-foreground animate-pulse">
            Polling every 2 s…
          </span>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function ItemPage() {
  const { key } = useParams<{ key: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const { data: item, isLoading, isError } = useQuery({
    queryKey: ['item', key],
    queryFn: () => api.getItem(key!),
    enabled: !!key,
  })

  const setDefaultMutation = useMutation({
    mutationFn: (imageId: number) => api.setDefaultImage(key!, imageId),
    onSuccess: (updatedItem) => {
      queryClient.setQueryData(['item', key], updatedItem)
    },
  })

  if (isLoading) {
    return (
      <div className="py-24 text-center text-sm text-muted-foreground">Loading…</div>
    )
  }

  if (isError || !item) {
    return (
      <div className="py-24 text-center">
        <p className="text-sm text-destructive mb-3">Item not found.</p>
        <button
          onClick={() => navigate(-1)}
          className="text-sm text-primary hover:underline"
        >
          Go back
        </button>
      </div>
    )
  }

  // Sort images: default first, then by order
  const sortedImages = [...item.images].sort((a, b) => {
    if (a.is_default && !b.is_default) return -1
    if (!a.is_default && b.is_default) return 1
    return a.order - b.order
  })

  return (
    <div className="flex flex-col gap-8 max-w-4xl mx-auto">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-2 text-sm text-muted-foreground">
        <Link to="/catalog" className="hover:text-primary">Catalog</Link>
        <span>›</span>
        <span className="text-foreground font-medium truncate">{item.title}</span>
      </nav>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        {/* Left: images */}
        <div>
          <ImageCarousel
            images={sortedImages}
            itemKey={item.key}
            onSetDefault={(imageId) => setDefaultMutation.mutate(imageId)}
            isSettingDefault={setDefaultMutation.isPending}
          />
        </div>

        {/* Right: metadata */}
        <div className="flex flex-col gap-4">
          <div>
            <h1 className="text-2xl font-bold leading-tight">{item.title}</h1>
            {item.creator && (
              <p className="mt-1 text-sm text-muted-foreground">
                By{' '}
                <Link
                  to={`/catalog?creator_id=${item.creator.id}`}
                  className="text-primary hover:underline"
                >
                  {item.creator.name}
                </Link>
                {item.creator.source_site && (
                  <span className="ml-1 text-xs text-muted-foreground">
                    ({item.creator.source_site})
                  </span>
                )}
              </p>
            )}
          </div>

          {/* Tags */}
          {item.tags.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {item.tags.map((tag) => (
                <Link
                  key={tag.id}
                  to={`/catalog?tags=${encodeURIComponent(tag.name)}`}
                  className="inline-flex items-center rounded-full bg-muted px-2.5 py-0.5 text-xs font-medium text-muted-foreground hover:bg-primary/10 hover:text-primary transition-colors"
                >
                  {tag.name}
                </Link>
              ))}
            </div>
          )}

          {/* Source + license */}
          {(item.source_url || item.license) && (
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-sm">
              {item.source_url && (
                <>
                  <dt className="text-muted-foreground font-medium">Source</dt>
                  <dd>
                    <a
                      href={item.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-primary hover:underline truncate block"
                    >
                      {item.source_url}
                    </a>
                  </dd>
                </>
              )}
              {item.license && (
                <>
                  <dt className="text-muted-foreground font-medium">License</dt>
                  <dd>{item.license}</dd>
                </>
              )}
            </dl>
          )}

          {/* Description */}
          {item.description && (
            <p className="text-sm text-muted-foreground leading-relaxed whitespace-pre-wrap">
              {item.description}
            </p>
          )}

          {/* Timestamps */}
          <div className="text-xs text-muted-foreground">
            Added {formatDate(item.created_at)}
            {item.updated_at !== item.created_at && (
              <> · Updated {formatDate(item.updated_at)}</>
            )}
          </div>
        </div>
      </div>

      {/* Dir path */}
      <section>
        <h2 className="text-base font-semibold mb-2">Location</h2>
        <PathDisplay dirPath={item.dir_path} itemKey={item.key} />
      </section>

      {/* Downloads */}
      <section>
        <h2 className="text-base font-semibold mb-3">Files &amp; Downloads</h2>
        <DownloadsSection itemKey={item.key} files={item.files} />
      </section>

      {/* Phase 7 placeholders */}
      <section className="rounded-lg border border-dashed border-border p-4 text-sm text-muted-foreground">
        <span className="font-medium text-foreground">Print History</span>
        &nbsp;— Coming in Phase 7.
      </section>

      <section className="rounded-lg border border-dashed border-border p-4 text-sm text-muted-foreground">
        <span className="font-medium text-foreground">Sharing</span>
        &nbsp;— Share links and public pages coming in Phase 7.
      </section>
    </div>
  )
}
