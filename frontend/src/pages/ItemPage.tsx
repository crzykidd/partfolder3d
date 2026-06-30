/**
 * ItemPage — detail view for a single catalog item.
 *
 * Sections:
 * - Image carousel (click → full-size, set default, default shown first + badged)
 * - Metadata (title, creator linked, source URL, license, description, timestamps)
 * - Tags as chips (click → /catalog?tags={name})
 * - Dir path + prefix rewrite + copy button (PRD §3.3)
 * - Downloads: individual files + queued ZIP with 2-second poll + include-history checkbox (PRD §11)
 * - Print History: log, view, edit, delete records; gcode + photo upload (PRD §9)
 * - Share controls: mint / list / revoke per-item share links (PRD §10)
 *
 * Styling: Aurora aesthetic — glass cards, teal accent (#0FA4AB), --aurora-* CSS vars.
 */

import React, { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Check, Copy, Download, Trash2, Upload, X as XIcon } from 'lucide-react'

import * as api from '@/lib/api'
import { detectOS, mapBundleStatus, rewriteLocalPath, shouldContinuePolling, type ZipPollStatus } from '@/lib/catalog-utils'
import { formatPrintTime, formatFilamentLength, formatFilamentWeight, renderStars } from '@/lib/print-utils'
import { useAuth } from '@/context/AuthContext'

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

function formatExpiry(iso: string | null): string {
  if (!iso) return 'Never'
  const d = new Date(iso)
  const now = Date.now()
  const diff = d.getTime() - now
  if (diff < 0) return 'Expired'
  const days = Math.ceil(diff / (1000 * 60 * 60 * 24))
  if (days === 1) return 'Expires in 1 day'
  return `Expires in ${days} days`
}

// ---------------------------------------------------------------------------
// Aurora style constants
// ---------------------------------------------------------------------------

const AURORA_CARD: React.CSSProperties = {
  background: 'var(--aurora-card)',
  border: '1px solid var(--aurora-card-border)',
  borderRadius: 14,
  backdropFilter: 'blur(16px)',
  WebkitBackdropFilter: 'blur(16px)',
}

const AURORA_SECTION_HEADER: React.CSSProperties = {
  fontSize: 10,
  fontWeight: 700,
  color: 'var(--aurora-muted)',
  letterSpacing: '0.1em',
  textTransform: 'uppercase',
  marginBottom: 14,
}

const AURORA_INPUT: React.CSSProperties = {
  background: 'var(--aurora-input-bg)',
  border: '1px solid var(--aurora-input-border)',
  borderRadius: 8,
  color: 'var(--aurora-text)',
  padding: '6px 10px',
  fontSize: 13,
  outline: 'none',
  width: '100%',
  transition: 'border-color 0.15s',
  boxSizing: 'border-box',
}

const AURORA_BTN_PRIMARY: React.CSSProperties = {
  background: 'var(--aurora-accent)',
  border: 'none',
  borderRadius: 20,
  color: 'var(--aurora-accent-fg)',
  fontSize: 12,
  fontWeight: 700,
  padding: '6px 16px',
  cursor: 'pointer',
  boxShadow: '0 4px 14px var(--aurora-accent-glow)',
  transition: 'opacity 0.15s',
}

const AURORA_BTN_GHOST: React.CSSProperties = {
  background: 'var(--aurora-glass)',
  border: '1px solid var(--aurora-glass-border)',
  borderRadius: 20,
  color: 'var(--aurora-text-dim)',
  fontSize: 12,
  padding: '5px 14px',
  cursor: 'pointer',
  transition: 'all 0.15s',
}

// ---------------------------------------------------------------------------
// Small shared section wrapper
// ---------------------------------------------------------------------------

function AuroraSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section style={{ ...AURORA_CARD, padding: '18px 20px' }}>
      <div style={AURORA_SECTION_HEADER as React.CSSProperties}>{title}</div>
      {children}
    </section>
  )
}

// ---------------------------------------------------------------------------
// Image carousel
// ---------------------------------------------------------------------------

interface ImageCarouselProps {
  images: api.ImageOut[]
  itemKey: string
  onSetDefault: (imageId: number) => void
  onDeleteImage: (imageId: number) => void
  isSettingDefault: boolean
  isDeletingImage: boolean
  isOwner: boolean
}

function ImageCarousel({
  images,
  itemKey,
  onSetDefault,
  onDeleteImage,
  isSettingDefault,
  isDeletingImage,
  isOwner,
}: ImageCarouselProps) {
  const [activeIdx, setActiveIdx] = useState(0)
  const [lightbox, setLightbox] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null)

  // Keep activeIdx in bounds when images list changes
  const clampedIdx = Math.min(activeIdx, Math.max(0, images.length - 1))

  if (!images.length) {
    return (
      <div
        style={{
          ...AURORA_CARD,
          height: 200,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <p style={{ fontSize: 12, color: 'var(--aurora-muted)', fontStyle: 'italic' }}>No images</p>
      </div>
    )
  }

  const active = images[clampedIdx]

  function handleDeleteConfirm(imageId: number) {
    setConfirmDelete(null)
    onDeleteImage(imageId)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {/* Main image */}
      <div
        style={{
          ...AURORA_CARD,
          position: 'relative',
          overflow: 'hidden',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          aspectRatio: '16/9',
          minHeight: 200,
        }}
      >
        <img
          src={`/api/items/${itemKey}/files/${active.path}`}
          alt={`Image ${clampedIdx + 1}`}
          style={{ maxHeight: 320, maxWidth: '100%', objectFit: 'contain', cursor: 'zoom-in' }}
          onClick={() => setLightbox(true)}
          loading="lazy"
        />

        {/* Top-left: Default badge + Rendered badge */}
        <div
          style={{
            position: 'absolute',
            top: 8,
            left: 8,
            display: 'flex',
            flexDirection: 'column',
            gap: 4,
          }}
        >
          {active.is_default && (
            <span
              style={{
                background: 'var(--aurora-accent)',
                color: 'var(--aurora-accent-fg)',
                borderRadius: 20,
                fontSize: 10,
                fontWeight: 700,
                padding: '3px 8px',
                boxShadow: '0 0 8px var(--aurora-accent-glow)',
              }}
            >
              Default
            </span>
          )}
          {active.source === 'render' && (
            <span
              style={{
                background: 'rgba(139,92,246,0.20)',
                color: '#A78BFA',
                border: '1px solid rgba(139,92,246,0.4)',
                borderRadius: 20,
                fontSize: 10,
                fontWeight: 700,
                padding: '3px 8px',
              }}
            >
              Rendered
            </span>
          )}
        </div>

        {/* Top-right: Set-default + Delete buttons (owner only) */}
        {isOwner && (
          <div
            style={{
              position: 'absolute',
              top: 8,
              right: 8,
              display: 'flex',
              gap: 4,
              flexDirection: 'column',
              alignItems: 'flex-end',
            }}
          >
            {!active.is_default && (
              <button
                onClick={() => onSetDefault(active.id)}
                disabled={isSettingDefault}
                style={{
                  ...AURORA_BTN_GHOST,
                  fontSize: 11,
                  padding: '3px 9px',
                  opacity: isSettingDefault ? 0.5 : 1,
                }}
              >
                Set as default
              </button>
            )}
            {confirmDelete === active.id ? (
              <div style={{ display: 'flex', gap: 4 }}>
                <button
                  onClick={() => handleDeleteConfirm(active.id)}
                  disabled={isDeletingImage}
                  style={{
                    background: '#EF4444',
                    border: 'none',
                    borderRadius: 20,
                    color: '#FFF',
                    fontSize: 11,
                    padding: '3px 9px',
                    cursor: 'pointer',
                    opacity: isDeletingImage ? 0.5 : 1,
                  }}
                >
                  {isDeletingImage ? '…' : 'Delete?'}
                </button>
                <button
                  onClick={() => setConfirmDelete(null)}
                  style={{ ...AURORA_BTN_GHOST, fontSize: 11, padding: '3px 9px' }}
                >
                  Cancel
                </button>
              </div>
            ) : (
              <button
                onClick={() => setConfirmDelete(active.id)}
                disabled={isDeletingImage}
                style={{
                  ...AURORA_BTN_GHOST,
                  fontSize: 11,
                  padding: '3px 9px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                  opacity: isDeletingImage ? 0.5 : 1,
                }}
                title="Delete image"
              >
                <Trash2 size={11} />
              </button>
            )}
          </div>
        )}
      </div>

      {/* Thumbnail strip */}
      {images.length > 1 && (
        <div style={{ display: 'flex', gap: 8, overflowX: 'auto', paddingBottom: 4 }}>
          {images.map((img, idx) => (
            <button
              key={img.id}
              onClick={() => setActiveIdx(idx)}
              style={{
                flexShrink: 0,
                height: 56,
                width: 56,
                borderRadius: 8,
                overflow: 'hidden',
                border: `2px solid ${idx === clampedIdx ? 'var(--aurora-accent)' : 'var(--aurora-glass-border)'}`,
                boxShadow: idx === clampedIdx ? 'var(--aurora-glow)' : 'none',
                cursor: 'pointer',
                padding: 0,
                transition: 'all 0.15s',
                position: 'relative',
              }}
            >
              <img
                src={`/api/items/${itemKey}/files/${img.path}`}
                alt={`Thumbnail ${idx + 1}`}
                style={{ height: '100%', width: '100%', objectFit: 'cover', display: 'block' }}
                loading="lazy"
              />
              {img.source === 'render' && (
                <span
                  style={{
                    position: 'absolute',
                    bottom: 2,
                    right: 2,
                    background: 'rgba(139,92,246,0.85)',
                    color: '#fff',
                    borderRadius: 4,
                    fontSize: 8,
                    fontWeight: 700,
                    padding: '1px 3px',
                    lineHeight: 1.2,
                  }}
                >
                  R
                </span>
              )}
            </button>
          ))}
        </div>
      )}

      {/* Lightbox */}
      {lightbox && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 50,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'rgba(5,13,28,0.88)',
            backdropFilter: 'blur(12px)',
            WebkitBackdropFilter: 'blur(12px)',
            padding: 16,
          } as React.CSSProperties}
          onClick={() => setLightbox(false)}
        >
          <img
            src={`/api/items/${itemKey}/files/${active.path}`}
            alt={`Full size ${clampedIdx + 1}`}
            style={{ maxHeight: '100%', maxWidth: '100%', objectFit: 'contain' }}
            onClick={(e) => e.stopPropagation()}
          />
          <button
            onClick={() => setLightbox(false)}
            style={{
              position: 'absolute',
              top: 16,
              right: 16,
              background: 'var(--aurora-glass)',
              border: '1px solid var(--aurora-glass-border)',
              borderRadius: '50%',
              width: 32,
              height: 32,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
              color: 'var(--aurora-text)',
            }}
          >
            <XIcon size={16} />
          </button>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Path display + copy
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// OS override (localStorage) — read/write helper used by PathDisplay
// ---------------------------------------------------------------------------

const _OS_OVERRIDE_KEY = 'pf3d_os_override'

function _readOSOverride(): 'windows' | 'posix' | 'auto' {
  try {
    const v = localStorage.getItem(_OS_OVERRIDE_KEY)
    if (v === 'windows' || v === 'posix' || v === 'auto') return v
  } catch { /* ignore */ }
  return 'auto'
}

function _effectiveOS(): 'windows' | 'posix' {
  const override = _readOSOverride()
  return override === 'auto' ? detectOS() : override
}

// ---------------------------------------------------------------------------
// PathDisplay — per-library × per-OS path rewrite
// ---------------------------------------------------------------------------

interface PathDisplayProps {
  dirPath: string
  itemKey: string
  libraryId: number
}

function PathDisplay({ dirPath, itemKey, libraryId }: PathDisplayProps) {
  const [copied, setCopied] = useState(false)

  const librariesQ = useQuery({
    queryKey: ['libraries'],
    queryFn: api.listLibraries,
    staleTime: 5 * 60_000,
  })

  const prefixesQ = useQuery({
    queryKey: ['path-prefixes'],
    queryFn: api.getPathPrefixes,
    staleTime: 60_000,
  })

  // Resolve: find library mount_path + user's prefix entry for this library + OS.
  const library = librariesQ.data?.find((l) => l.id === libraryId)
  const prefixMap = prefixesQ.data?.path_prefixes ?? {}
  const libEntry = prefixMap[String(libraryId)]
  const os = _effectiveOS()
  const localPrefix = libEntry?.[os] ?? null

  const displayPath = library
    ? rewriteLocalPath(dirPath, library.mount_path, localPrefix, os)
    : dirPath  // fallback: library not loaded yet, show raw

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
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        background: 'var(--aurora-input-bg)',
        border: '1px solid var(--aurora-input-border)',
        borderRadius: 10,
        padding: '8px 12px',
      }}
    >
      <code style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: 12, fontFamily: 'monospace', color: 'var(--aurora-text-dim)' }}>
        {displayPath}
      </code>
      <button
        onClick={handleCopy}
        style={{
          ...AURORA_BTN_GHOST,
          display: 'flex',
          alignItems: 'center',
          gap: 5,
          padding: '4px 10px',
          flexShrink: 0,
        }}
        title="Copy path"
      >
        {copied ? <Check size={12} style={{ color: '#22C55E' }} /> : <Copy size={12} />}
        {copied ? 'Copied' : 'Copy'}
      </button>
      <Link
        to={`/settings?from=/items/${itemKey}`}
        style={{ flexShrink: 0, fontSize: 11, color: 'var(--aurora-muted)', textDecoration: 'none', transition: 'color 0.15s' }}
        onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.color = 'var(--aurora-accent)' }}
        onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.color = 'var(--aurora-muted)' }}
        title="Configure path prefixes"
      >
        Edit prefixes
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
  const [includeHistory, setIncludeHistory] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const stopPoll = useCallback(() => {
    if (pollRef.current !== null) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  const zipMutation = useMutation({
    mutationFn: () => api.queueZip(itemKey, { includeHistory }),
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

  // Reset zip state when includeHistory changes
  const prevIncludeHistory = useRef(includeHistory)
  useEffect(() => {
    if (prevIncludeHistory.current !== includeHistory) {
      prevIncludeHistory.current = includeHistory
      setZipStatus('idle')
      setBundleId(null)
      setErrorMsg(null)
      stopPoll()
    }
  }, [includeHistory, stopPoll])

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
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* Individual files */}
      {files.length === 0 ? (
        <p style={{ fontSize: 12, color: 'var(--aurora-muted)', fontStyle: 'italic', margin: 0 }}>
          No files catalogued yet.
        </p>
      ) : (
        <div
          style={{
            background: 'var(--aurora-glass)',
            border: '1px solid var(--aurora-glass-border)',
            borderRadius: 10,
            overflow: 'hidden',
          }}
        >
          {files.map((file, idx) => (
            <div
              key={file.id}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '10px 14px',
                borderTop: idx > 0 ? '1px solid var(--aurora-divider)' : 'none',
                transition: 'background 0.1s',
              }}
              onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.background = 'var(--aurora-glass-hover)' }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.background = 'transparent' }}
            >
              <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                <span style={{ fontSize: 12, fontWeight: 500, fontFamily: 'monospace', color: 'var(--aurora-text)' }}>
                  {file.path}
                </span>
                <span style={{ fontSize: 11, color: 'var(--aurora-muted)' }}>
                  {file.role} · {formatBytes(file.size)}
                </span>
              </div>
              <a
                href={api.fileDownloadUrl(itemKey, file.path)}
                download
                style={{
                  ...AURORA_BTN_GHOST,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 5,
                  textDecoration: 'none',
                  flexShrink: 0,
                }}
              >
                <Download size={12} />
                Download
              </a>
            </div>
          ))}
        </div>
      )}

      {/* ZIP download */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {/* Include history checkbox */}
        <label
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            fontSize: 12,
            cursor: 'pointer',
            userSelect: 'none',
            color: 'var(--aurora-text-dim)',
          }}
        >
          <input
            type="checkbox"
            checked={includeHistory}
            onChange={(e) => setIncludeHistory(e.target.checked)}
            style={{ accentColor: 'var(--aurora-accent)', width: 14, height: 14 }}
          />
          <span>Include print history</span>
          <span
            style={{ fontSize: 11, color: 'var(--aurora-muted)', cursor: 'help' }}
            title="Adds a print-history.json to the ZIP. Public records always included; private records included only for your own download."
          >
            (?)
          </span>
        </label>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button
            onClick={
              zipStatus === 'ready'
                ? handleDownloadZip
                : zipStatus === 'idle' || zipStatus === 'failed' || zipStatus === 'expired'
                  ? () => zipMutation.mutate()
                  : undefined
            }
            disabled={zipStatus === 'queued' || zipStatus === 'building' || zipMutation.isPending}
            style={{
              ...AURORA_BTN_PRIMARY,
              opacity: zipStatus === 'queued' || zipStatus === 'building' || zipMutation.isPending ? 0.5 : 1,
            }}
          >
            {zipLabel[zipStatus]}
          </button>
          {errorMsg && (
            <span style={{ fontSize: 11, color: 'var(--aurora-danger)' }}>{errorMsg}</span>
          )}
          {(zipStatus === 'queued' || zipStatus === 'building') && (
            <span style={{ fontSize: 11, color: 'var(--aurora-muted)' }}>
              Polling every 2 s…
            </span>
          )}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Print record form (inline modal overlay)
// ---------------------------------------------------------------------------

interface PrintRecordFormProps {
  itemKey: string
  existing?: api.PrintRecord
  onClose: () => void
  onSaved: (rec: api.PrintRecord) => void
}

function PrintRecordForm({ itemKey, existing, onClose, onSaved }: PrintRecordFormProps) {
  const today = new Date().toISOString().split('T')[0]
  const [form, setForm] = useState<api.PrintRecordIn>({
    note: existing?.note ?? '',
    visibility: existing?.visibility ?? 'private',
    date: existing?.date ?? today,
    printer: existing?.printer ?? '',
    material: existing?.material ?? '',
    filament_color: existing?.filament_color ?? '',
    nozzle_diameter: existing?.nozzle_diameter ?? null,
    layer_height: existing?.layer_height ?? null,
    supports: existing?.supports ?? null,
    success: existing?.success ?? null,
    rating: existing?.rating ?? null,
  })
  const [submitError, setSubmitError] = useState<string | null>(null)

  const createMutation = useMutation({
    mutationFn: (body: api.PrintRecordIn) => api.createPrintRecord(itemKey, body),
    onSuccess: (rec) => { onSaved(rec) },
    onError: (e) => setSubmitError(e instanceof Error ? e.message : 'Failed to save.'),
  })

  const updateMutation = useMutation({
    mutationFn: (body: api.PrintRecordPatch) =>
      api.updatePrintRecord(itemKey, existing!.id, body),
    onSuccess: (rec) => { onSaved(rec) },
    onError: (e) => setSubmitError(e instanceof Error ? e.message : 'Failed to save.'),
  })

  const isPending = createMutation.isPending || updateMutation.isPending

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setSubmitError(null)
    const body: api.PrintRecordIn = {
      ...form,
      printer: form.printer || null,
      material: form.material || null,
      filament_color: form.filament_color || null,
      note: form.note || null,
    }
    if (existing) {
      updateMutation.mutate(body)
    } else {
      createMutation.mutate(body)
    }
  }

  const labelStyle: React.CSSProperties = {
    fontSize: 10,
    fontWeight: 700,
    color: 'var(--aurora-muted)',
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
    display: 'block',
    marginBottom: 5,
  }

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 50,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'rgba(5,13,28,0.82)',
        backdropFilter: 'blur(12px)',
        WebkitBackdropFilter: 'blur(12px)',
        padding: 16,
      } as React.CSSProperties}
      onClick={onClose}
    >
      <div
        style={{
          background: 'var(--aurora-palette-bg)',
          border: '1px solid var(--aurora-palette-border)',
          borderRadius: 16,
          boxShadow: '0 24px 60px rgba(0,0,0,0.5)',
          backdropFilter: 'blur(40px)',
          WebkitBackdropFilter: 'blur(40px)',
          width: '100%',
          maxWidth: 520,
          maxHeight: '90vh',
          overflowY: 'auto',
        } as React.CSSProperties}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '14px 18px',
            borderBottom: '1px solid var(--aurora-divider)',
          }}
        >
          <h2 style={{ fontSize: 14, fontWeight: 700, color: 'var(--aurora-text)', margin: 0 }}>
            {existing ? 'Edit Print Record' : 'Log a Print'}
          </h2>
          <button
            onClick={onClose}
            style={{
              background: 'var(--aurora-glass)',
              border: '1px solid var(--aurora-glass-border)',
              borderRadius: '50%',
              width: 28,
              height: 28,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
              color: 'var(--aurora-muted)',
            }}
          >
            <XIcon size={14} />
          </button>
        </div>

        <form onSubmit={handleSubmit} style={{ padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 14 }}>
          {/* Visibility + Date */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <label style={labelStyle}>Visibility</label>
              <select
                value={form.visibility}
                onChange={(e) => setForm((f) => ({ ...f, visibility: e.target.value }))}
                style={AURORA_INPUT}
              >
                <option value="private">Private</option>
                <option value="public">Public</option>
              </select>
            </div>
            <div>
              <label style={labelStyle}>Date</label>
              <input
                type="date"
                value={form.date ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, date: e.target.value || null }))}
                style={AURORA_INPUT}
              />
            </div>
          </div>

          {/* Outcome + Rating */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <label style={labelStyle}>Outcome</label>
              <select
                value={form.success == null ? '' : form.success ? 'true' : 'false'}
                onChange={(e) => {
                  const v = e.target.value
                  setForm((f) => ({
                    ...f,
                    success: v === '' ? null : v === 'true',
                  }))
                }}
                style={AURORA_INPUT}
              >
                <option value="">Not recorded</option>
                <option value="true">Success</option>
                <option value="false">Failed</option>
              </select>
            </div>
            <div>
              <label style={labelStyle}>Rating (1–5)</label>
              <select
                value={form.rating ?? ''}
                onChange={(e) => {
                  const v = e.target.value
                  setForm((f) => ({ ...f, rating: v === '' ? null : Number(v) }))
                }}
                style={AURORA_INPUT}
              >
                <option value="">None</option>
                {[1, 2, 3, 4, 5].map((n) => (
                  <option key={n} value={n}>{n} — {renderStars(n)}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Printer + Material */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <label style={labelStyle}>Printer</label>
              <input
                type="text"
                value={form.printer ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, printer: e.target.value }))}
                placeholder="e.g. Bambu X1C"
                style={AURORA_INPUT}
              />
            </div>
            <div>
              <label style={labelStyle}>Material</label>
              <input
                type="text"
                value={form.material ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, material: e.target.value }))}
                placeholder="e.g. PLA"
                style={AURORA_INPUT}
              />
            </div>
          </div>

          {/* Filament color + Supports */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <label style={labelStyle}>Filament color</label>
              <input
                type="text"
                value={form.filament_color ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, filament_color: e.target.value }))}
                placeholder="e.g. Black"
                style={AURORA_INPUT}
              />
            </div>
            <div>
              <label style={labelStyle}>Supports</label>
              <select
                value={form.supports == null ? '' : form.supports ? 'true' : 'false'}
                onChange={(e) => {
                  const v = e.target.value
                  setForm((f) => ({
                    ...f,
                    supports: v === '' ? null : v === 'true',
                  }))
                }}
                style={AURORA_INPUT}
              >
                <option value="">Not recorded</option>
                <option value="true">Yes</option>
                <option value="false">No</option>
              </select>
            </div>
          </div>

          {/* Nozzle + Layer height */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <label style={labelStyle}>Nozzle (mm)</label>
              <input
                type="number"
                step="0.1"
                min="0"
                value={form.nozzle_diameter ?? ''}
                onChange={(e) => {
                  const v = e.target.value
                  setForm((f) => ({ ...f, nozzle_diameter: v === '' ? null : Number(v) }))
                }}
                placeholder="0.4"
                style={AURORA_INPUT}
              />
            </div>
            <div>
              <label style={labelStyle}>Layer height (mm)</label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={form.layer_height ?? ''}
                onChange={(e) => {
                  const v = e.target.value
                  setForm((f) => ({ ...f, layer_height: v === '' ? null : Number(v) }))
                }}
                placeholder="0.20"
                style={AURORA_INPUT}
              />
            </div>
          </div>

          {/* Note */}
          <div>
            <label style={labelStyle}>Note</label>
            <textarea
              rows={3}
              value={form.note ?? ''}
              onChange={(e) => setForm((f) => ({ ...f, note: e.target.value }))}
              placeholder="Any notes about this print…"
              style={{ ...AURORA_INPUT, resize: 'none', lineHeight: 1.5 }}
            />
          </div>

          {submitError && (
            <p style={{ fontSize: 12, color: 'var(--aurora-danger)', margin: 0 }}>{submitError}</p>
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, paddingTop: 4 }}>
            <button
              type="button"
              onClick={onClose}
              style={AURORA_BTN_GHOST}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isPending}
              style={{ ...AURORA_BTN_PRIMARY, opacity: isPending ? 0.5 : 1 }}
            >
              {isPending ? 'Saving…' : existing ? 'Save changes' : 'Log print'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Print record card
// ---------------------------------------------------------------------------

interface PrintRecordCardProps {
  record: api.PrintRecord
  itemKey: string
  onUpdated: (rec: api.PrintRecord) => void
  onDeleted: (id: number) => void
}

function PrintRecordCard({ record, itemKey, onUpdated, onDeleted }: PrintRecordCardProps) {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [gcodeInput, setGcodeInput] = useState<HTMLInputElement | null>(null)
  const [photoInput, setPhotoInput] = useState<HTMLInputElement | null>(null)
  const [uploadingGcode, setUploadingGcode] = useState(false)
  const [uploadingPhoto, setUploadingPhoto] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)

  const deleteMutation = useMutation({
    mutationFn: () => api.deletePrintRecord(itemKey, record.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['print-records', itemKey] })
      onDeleted(record.id)
    },
  })

  async function handleGcodeUpload(file: File) {
    setUploadingGcode(true)
    setUploadError(null)
    try {
      const updated = await api.uploadGcode(itemKey, record.id, file)
      onUpdated(updated)
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : 'Upload failed.')
    } finally {
      setUploadingGcode(false)
    }
  }

  async function handlePhotoUpload(file: File) {
    setUploadingPhoto(true)
    setUploadError(null)
    try {
      const updated = await api.uploadPrintPhoto(itemKey, record.id, file)
      onUpdated(updated)
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : 'Upload failed.')
    } finally {
      setUploadingPhoto(false)
    }
  }

  return (
    <>
      {editing && (
        <PrintRecordForm
          itemKey={itemKey}
          existing={record}
          onClose={() => setEditing(false)}
          onSaved={(rec) => {
            setEditing(false)
            onUpdated(rec)
          }}
        />
      )}

      <div
        style={{
          background: 'var(--aurora-glass)',
          border: '1px solid var(--aurora-card-border)',
          borderRadius: 10,
          padding: '12px 14px',
          display: 'flex',
          flexDirection: 'column',
          gap: 10,
        }}
      >
        {/* Header row */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8 }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 6 }}>
            {/* Visibility badge */}
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                padding: '2px 8px',
                borderRadius: 20,
                fontSize: 10,
                fontWeight: 700,
                background: record.visibility === 'public' ? 'rgba(34,197,94,0.15)' : 'var(--aurora-glass)',
                color: record.visibility === 'public' ? '#22C55E' : 'var(--aurora-muted)',
                border: `1px solid ${record.visibility === 'public' ? 'rgba(34,197,94,0.3)' : 'var(--aurora-glass-border)'}`,
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
              }}
            >
              {record.visibility}
            </span>

            {/* Outcome chip */}
            {record.success != null && (
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  padding: '2px 8px',
                  borderRadius: 20,
                  fontSize: 10,
                  fontWeight: 700,
                  background: record.success ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)',
                  color: record.success ? '#22C55E' : '#EF4444',
                  border: `1px solid ${record.success ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)'}`,
                }}
              >
                {record.success ? '✓ Success' : '✗ Failed'}
              </span>
            )}

            {/* Rating */}
            {record.rating != null && (
              <span style={{ fontSize: 13, color: '#F59E0B' }} title={`Rating: ${record.rating}/5`}>
                {renderStars(record.rating)}
              </span>
            )}

            {/* Date */}
            {record.date && (
              <span style={{ fontSize: 11, color: 'var(--aurora-muted)' }}>{record.date}</span>
            )}
          </div>

          {/* Actions */}
          <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
            <button
              onClick={() => setEditing(true)}
              style={{
                ...AURORA_BTN_GHOST,
                fontSize: 11,
                padding: '3px 9px',
              }}
            >
              Edit
            </button>
            {!confirmDelete ? (
              <button
                onClick={() => setConfirmDelete(true)}
                style={{
                  ...AURORA_BTN_GHOST,
                  fontSize: 11,
                  padding: '3px 9px',
                }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLButtonElement).style.background = 'rgba(239,68,68,0.12)'
                  ;(e.currentTarget as HTMLButtonElement).style.color = '#EF4444'
                  ;(e.currentTarget as HTMLButtonElement).style.borderColor = 'rgba(239,68,68,0.3)'
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass)'
                  ;(e.currentTarget as HTMLButtonElement).style.color = 'var(--aurora-text-dim)'
                  ;(e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--aurora-glass-border)'
                }}
              >
                Delete
              </button>
            ) : (
              <div style={{ display: 'flex', gap: 4 }}>
                <button
                  onClick={() => deleteMutation.mutate()}
                  disabled={deleteMutation.isPending}
                  style={{
                    background: '#EF4444',
                    border: 'none',
                    borderRadius: 20,
                    color: '#FFF',
                    fontSize: 11,
                    padding: '3px 9px',
                    cursor: 'pointer',
                    opacity: deleteMutation.isPending ? 0.5 : 1,
                  }}
                >
                  {deleteMutation.isPending ? '…' : 'Confirm'}
                </button>
                <button
                  onClick={() => setConfirmDelete(false)}
                  style={{ ...AURORA_BTN_GHOST, fontSize: 11, padding: '3px 9px' }}
                >
                  Cancel
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Settings row */}
        {(record.printer || record.material || record.filament_color ||
          record.nozzle_diameter != null || record.layer_height != null) && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 16px', fontSize: 11, color: 'var(--aurora-text-dim)' }}>
            {record.printer && <span>Printer: {record.printer}</span>}
            {record.material && <span>Material: {record.material}</span>}
            {record.filament_color && <span>Color: {record.filament_color}</span>}
            {record.nozzle_diameter != null && <span>Nozzle: {record.nozzle_diameter}mm</span>}
            {record.layer_height != null && <span>Layer: {record.layer_height}mm</span>}
            {record.supports != null && <span>Supports: {record.supports ? 'Yes' : 'No'}</span>}
          </div>
        )}

        {/* Gcode stats (parsed) */}
        {(record.filament_length_mm != null || record.filament_weight_g != null ||
          record.estimated_print_time_s != null) && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 16px', fontSize: 11, color: 'var(--aurora-text-dim)' }}>
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

        {/* Note */}
        {record.note && (
          <p style={{ fontSize: 12, color: 'var(--aurora-text-dim)', lineHeight: 1.6, whiteSpace: 'pre-wrap', margin: 0 }}>
            {record.note}
          </p>
        )}

        {/* File uploads */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, paddingTop: 2 }}>
          <button
            onClick={() => gcodeInput?.click()}
            disabled={uploadingGcode}
            style={{ ...AURORA_BTN_GHOST, fontSize: 11, padding: '3px 10px', opacity: uploadingGcode ? 0.5 : 1 }}
          >
            {uploadingGcode ? 'Uploading…' : record.gcode_file_path ? 'Replace gcode' : 'Upload gcode'}
          </button>
          <input
            ref={setGcodeInput}
            type="file"
            accept=".gcode,.bgcode,.gco"
            style={{ display: 'none' }}
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) void handleGcodeUpload(file)
              e.target.value = ''
            }}
          />

          <button
            onClick={() => photoInput?.click()}
            disabled={uploadingPhoto}
            style={{ ...AURORA_BTN_GHOST, fontSize: 11, padding: '3px 10px', opacity: uploadingPhoto ? 0.5 : 1 }}
          >
            {uploadingPhoto ? 'Uploading…' : record.print_photo_path ? 'Replace photo' : 'Upload photo'}
          </button>
          <input
            ref={setPhotoInput}
            type="file"
            accept="image/*"
            style={{ display: 'none' }}
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) void handlePhotoUpload(file)
              e.target.value = ''
            }}
          />
        </div>

        {uploadError && (
          <p style={{ fontSize: 11, color: 'var(--aurora-danger)', margin: 0 }}>{uploadError}</p>
        )}
      </div>
    </>
  )
}

// ---------------------------------------------------------------------------
// Print History section
// ---------------------------------------------------------------------------

interface PrintHistorySectionProps {
  itemKey: string
}

function PrintHistorySection({ itemKey }: PrintHistorySectionProps) {
  const queryClient = useQueryClient()
  const [addingRecord, setAddingRecord] = useState(false)
  const [records, setRecords] = useState<api.PrintRecord[]>([])

  const { data, isLoading, isError } = useQuery({
    queryKey: ['print-records', itemKey],
    queryFn: () => api.listPrintRecords(itemKey),
    staleTime: 30_000,
  })

  useEffect(() => {
    if (data) setRecords(data)
  }, [data])

  function handleUpdated(updated: api.PrintRecord) {
    setRecords((prev) =>
      prev.map((r) => (r.id === updated.id ? updated : r)),
    )
    void queryClient.invalidateQueries({ queryKey: ['print-records', itemKey] })
  }

  function handleDeleted(id: number) {
    setRecords((prev) => prev.filter((r) => r.id !== id))
  }

  function handleSaved(rec: api.PrintRecord) {
    setAddingRecord(false)
    setRecords((prev) => [rec, ...prev])
    void queryClient.invalidateQueries({ queryKey: ['print-records', itemKey] })
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {addingRecord && (
        <PrintRecordForm
          itemKey={itemKey}
          onClose={() => setAddingRecord(false)}
          onSaved={handleSaved}
        />
      )}

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: 11, color: 'var(--aurora-muted)' }}>
          {records.length > 0 ? `${records.length} record(s)` : ''}
        </span>
        <button
          onClick={() => setAddingRecord(true)}
          style={AURORA_BTN_PRIMARY}
        >
          + Log a print
        </button>
      </div>

      {isLoading && (
        <p style={{ fontSize: 12, color: 'var(--aurora-muted)', margin: 0 }}>Loading…</p>
      )}

      {isError && (
        <p style={{ fontSize: 12, color: 'var(--aurora-danger)', margin: 0 }}>Failed to load print records.</p>
      )}

      {!isLoading && !isError && records.length === 0 && (
        <p style={{ fontSize: 12, color: 'var(--aurora-muted)', fontStyle: 'italic', margin: 0 }}>
          No print records yet. Log your first print above.
        </p>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {records.map((rec) => (
          <PrintRecordCard
            key={rec.id}
            record={rec}
            itemKey={itemKey}
            onUpdated={handleUpdated}
            onDeleted={handleDeleted}
          />
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Object breakdown section (Phase 16)
// ---------------------------------------------------------------------------

interface ObjectBreakdownProps {
  item: api.ItemDetail
}

/** Small color swatch when a hex code is available. */
function ColorSwatch({ hex, size = 12 }: { hex: string; size?: number }) {
  const valid = /^#[0-9A-Fa-f]{3,8}$/.test(hex)
  if (!valid) return null
  return (
    <span
      title={hex}
      style={{
        display: 'inline-block',
        width: size,
        height: size,
        borderRadius: 3,
        border: '1px solid var(--aurora-glass-border)',
        background: hex,
        flexShrink: 0,
      }}
    />
  )
}

function ObjectBreakdownSection({ item }: ObjectBreakdownProps) {
  // Collect analyzed model files
  const analyzedFiles = item.files.filter(
    (f) => f.role === 'model' && f.object_analysis != null,
  )
  const pendingFiles = item.files.filter(
    (f) => f.role === 'model' && f.object_analysis == null,
  )

  if (analyzedFiles.length === 0 && pendingFiles.length === 0) {
    return (
      <p style={{ fontSize: 12, color: 'var(--aurora-muted)', fontStyle: 'italic', margin: 0 }}>
        No model files.
      </p>
    )
  }

  if (analyzedFiles.length === 0) {
    return (
      <p style={{ fontSize: 12, color: 'var(--aurora-muted)', fontStyle: 'italic', margin: 0 }}>
        Analysis pending — will appear after the background worker runs.
      </p>
    )
  }

  const densityNote = 'Grams = volume × 1.24 g/cm³ (PLA default) × infill % — configurable in admin settings. Real values require slicing.'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {/* Item-level summary bar */}
      {(item.analysis_total_objects != null) && (
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '6px 20px',
            background: 'var(--aurora-glass)',
            border: '1px solid var(--aurora-glass-border)',
            borderRadius: 10,
            padding: '10px 14px',
            fontSize: 12,
          }}
        >
          <span style={{ color: 'var(--aurora-text-dim)' }}>
            <span style={{ fontWeight: 700, color: 'var(--aurora-text)' }}>
              {item.analysis_total_objects}
            </span>
            {' '}object{item.analysis_total_objects !== 1 ? 's' : ''}
          </span>
          <span style={{ color: 'var(--aurora-text-dim)' }}>
            <span style={{ fontWeight: 700, color: 'var(--aurora-text)' }}>
              {item.analysis_total_colors}
            </span>
            {' '}color{item.analysis_total_colors !== 1 ? 's' : ''}
          </span>
          {item.analysis_total_est_grams != null && (
            <span style={{ color: 'var(--aurora-text-dim)' }}>
              <span style={{ fontWeight: 700, color: 'var(--aurora-text)' }}>
                ~{item.analysis_total_est_grams.toFixed(1)}g
              </span>
              {' '}est.
              <span
                style={{ cursor: 'help', marginLeft: 4, fontSize: 10, color: 'var(--aurora-muted)' }}
                title={densityNote}
              >
                (?)
              </span>
            </span>
          )}
          {pendingFiles.length > 0 && (
            <span style={{ fontSize: 11, color: 'var(--aurora-muted)' }}>
              ({pendingFiles.length} file{pendingFiles.length > 1 ? 's' : ''} pending)
            </span>
          )}
        </div>
      )}

      {/* Per-file breakdown */}
      {analyzedFiles.map((file) => {
        const a = file.object_analysis!
        return (
          <div key={file.id} style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {/* File header */}
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--aurora-muted)', fontFamily: 'monospace' }}>
              {file.path}
            </div>

            {/* Object rows */}
            <div
              style={{
                background: 'var(--aurora-glass)',
                border: '1px solid var(--aurora-glass-border)',
                borderRadius: 10,
                overflow: 'hidden',
              }}
            >
              {a.objects.map((obj, idx) => (
                <div
                  key={idx}
                  style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    justifyContent: 'space-between',
                    gap: 12,
                    padding: '10px 14px',
                    borderTop: idx > 0 ? '1px solid var(--aurora-divider)' : 'none',
                    flexWrap: 'wrap',
                  }}
                >
                  {/* Left: name + dims + low-confidence badge */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                      <span style={{ fontSize: 12, fontWeight: 500, fontFamily: 'monospace', color: 'var(--aurora-text)' }}>
                        {obj.name}
                      </span>
                      {obj.low_confidence && (
                        <span
                          title="Non-watertight mesh — convex hull used for volume. Estimate may be significantly off."
                          style={{
                            fontSize: 9,
                            fontWeight: 700,
                            padding: '1px 6px',
                            borderRadius: 20,
                            background: 'rgba(245,158,11,0.15)',
                            color: '#D97706',
                            border: '1px solid rgba(245,158,11,0.3)',
                            cursor: 'help',
                          }}
                        >
                          LOW CONF
                        </span>
                      )}
                    </div>
                    {obj.dims_mm && (
                      <span style={{ fontSize: 10, color: 'var(--aurora-muted)' }}>
                        {obj.dims_mm[0]}×{obj.dims_mm[1]}×{obj.dims_mm[2]} mm
                      </span>
                    )}
                  </div>

                  {/* Right: colors + grams */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0, flexWrap: 'wrap' }}>
                    {/* Color swatches */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      {obj.colors.filter(Boolean).slice(0, 8).map((hex, ci) => (
                        <ColorSwatch key={ci} hex={hex} />
                      ))}
                      {obj.colors.filter(Boolean).length > 8 && (
                        <span style={{ fontSize: 10, color: 'var(--aurora-muted)' }}>
                          +{obj.colors.filter(Boolean).length - 8}
                        </span>
                      )}
                      <span style={{ fontSize: 11, color: 'var(--aurora-text-dim)' }}>
                        {obj.color_count} color{obj.color_count !== 1 ? 's' : ''}
                      </span>
                    </div>

                    {/* Estimated grams */}
                    {obj.est_grams != null && (
                      <span
                        style={{ fontSize: 11, color: 'var(--aurora-text-dim)' }}
                        title={densityNote}
                      >
                        ~{obj.est_grams.toFixed(2)}g
                        <span style={{ fontSize: 10, color: 'var(--aurora-muted)', marginLeft: 2 }}>est.</span>
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {/* File totals row */}
            {a.objects.length > 1 && (
              <div
                style={{
                  display: 'flex',
                  gap: 12,
                  fontSize: 11,
                  color: 'var(--aurora-muted)',
                  paddingLeft: 14,
                  flexWrap: 'wrap',
                }}
              >
                <span>File total: {a.total_objects} objects</span>
                <span>{a.total_colors} distinct color{a.total_colors !== 1 ? 's' : ''}</span>
                {a.total_est_grams != null && (
                  <span>~{a.total_est_grams.toFixed(1)}g est.</span>
                )}
              </div>
            )}
          </div>
        )
      })}

      {/* Footnote */}
      <p style={{ fontSize: 10, color: 'var(--aurora-muted)', margin: 0, lineHeight: 1.5 }}>
        Grams are a rough volume-based estimate (can be 2–5× off without real slicing).{' '}
        Assumptions: density and infill % from admin settings.
        LOW CONF = non-watertight mesh; convex hull used for volume.
      </p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Share controls section
// ---------------------------------------------------------------------------

interface ShareSectionProps {
  itemKey: string
}

function ShareSection({ itemKey }: ShareSectionProps) {
  const queryClient = useQueryClient()
  const [mintOpen, setMintOpen] = useState(false)
  const [mintLabel, setMintLabel] = useState('')
  const [mintExpiry, setMintExpiry] = useState('')
  const [mintError, setMintError] = useState<string | null>(null)
  const [copiedToken, setCopiedToken] = useState<string | null>(null)
  const [confirmRevoke, setConfirmRevoke] = useState<number | null>(null)

  const { data: links = [], isLoading, isError } = useQuery({
    queryKey: ['item-shares', itemKey],
    queryFn: () => api.listItemShares(itemKey),
    staleTime: 30_000,
  })

  const mintMutation = useMutation({
    mutationFn: () =>
      api.mintItemShare(itemKey, {
        label: mintLabel || null,
        expires_days: mintExpiry ? Number(mintExpiry) : null,
      }),
    onSuccess: async (link) => {
      setMintOpen(false)
      setMintLabel('')
      setMintExpiry('')
      setMintError(null)
      void queryClient.invalidateQueries({ queryKey: ['item-shares', itemKey] })
      // Auto-copy the new link
      const url = `${window.location.origin}/share/${link.token}`
      try {
        await navigator.clipboard.writeText(url)
        setCopiedToken(link.token)
        setTimeout(() => setCopiedToken(null), 3000)
      } catch {
        // ignore clipboard failure
      }
    },
    onError: (e) => {
      setMintError(e instanceof Error ? e.message : 'Failed to mint share link.')
    },
  })

  const revokeMutation = useMutation({
    mutationFn: (shareId: number) => api.revokeShare(shareId),
    onSuccess: () => {
      setConfirmRevoke(null)
      void queryClient.invalidateQueries({ queryKey: ['item-shares', itemKey] })
    },
  })

  async function handleCopy(token: string) {
    const url = `${window.location.origin}/share/${token}`
    try {
      await navigator.clipboard.writeText(url)
      setCopiedToken(token)
      setTimeout(() => setCopiedToken(null), 2000)
    } catch {
      // ignore
    }
  }

  const labelStyle: React.CSSProperties = {
    fontSize: 10,
    fontWeight: 700,
    color: 'var(--aurora-muted)',
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
    display: 'block',
    marginBottom: 5,
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {isLoading && <p style={{ fontSize: 12, color: 'var(--aurora-muted)', margin: 0 }}>Loading…</p>}
      {isError && <p style={{ fontSize: 12, color: 'var(--aurora-danger)', margin: 0 }}>Failed to load share links.</p>}

      {!isLoading && links.length === 0 && (
        <p style={{ fontSize: 12, color: 'var(--aurora-muted)', fontStyle: 'italic', margin: 0 }}>No share links yet.</p>
      )}

      {links.length > 0 && (
        <div
          style={{
            background: 'var(--aurora-glass)',
            border: '1px solid var(--aurora-glass-border)',
            borderRadius: 10,
            overflow: 'hidden',
          }}
        >
          {links.map((link, idx) => (
            <div
              key={link.id}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '10px 14px',
                borderTop: idx > 0 ? '1px solid var(--aurora-divider)' : 'none',
                transition: 'background 0.1s',
              }}
              onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.background = 'var(--aurora-glass-hover)' }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.background = 'transparent' }}
            >
              <div style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <span style={{ fontSize: 12, fontFamily: 'monospace', color: 'var(--aurora-muted)' }}>
                    {link.token.slice(0, 8)}…
                  </span>
                  {link.label && (
                    <span style={{ fontSize: 12, fontWeight: 500, color: 'var(--aurora-text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {link.label}
                    </span>
                  )}
                  {link.revoked && (
                    <span style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      padding: '2px 7px',
                      borderRadius: 20,
                      fontSize: 10,
                      fontWeight: 700,
                      background: 'rgba(239,68,68,0.15)',
                      color: '#EF4444',
                      border: '1px solid rgba(239,68,68,0.3)',
                    }}>
                      Revoked
                    </span>
                  )}
                  {copiedToken === link.token && (
                    <span style={{ fontSize: 11, color: '#22C55E', display: 'flex', alignItems: 'center', gap: 3 }}>
                      <Check size={11} /> Copied!
                    </span>
                  )}
                </div>
                <span style={{ fontSize: 11, color: 'var(--aurora-muted)' }}>
                  {formatExpiry(link.expires_at)}
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0, marginLeft: 8 }}>
                {!link.revoked && (
                  <button
                    onClick={() => void handleCopy(link.token)}
                    style={{ ...AURORA_BTN_GHOST, fontSize: 11, padding: '3px 9px', display: 'flex', alignItems: 'center', gap: 4 }}
                  >
                    <Copy size={11} />
                    Copy link
                  </button>
                )}
                {!link.revoked && confirmRevoke !== link.id && (
                  <button
                    onClick={() => setConfirmRevoke(link.id)}
                    style={{ ...AURORA_BTN_GHOST, fontSize: 11, padding: '3px 9px' }}
                    onMouseEnter={(e) => {
                      (e.currentTarget as HTMLButtonElement).style.background = 'rgba(239,68,68,0.12)'
                      ;(e.currentTarget as HTMLButtonElement).style.color = '#EF4444'
                      ;(e.currentTarget as HTMLButtonElement).style.borderColor = 'rgba(239,68,68,0.3)'
                    }}
                    onMouseLeave={(e) => {
                      (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass)'
                      ;(e.currentTarget as HTMLButtonElement).style.color = 'var(--aurora-text-dim)'
                      ;(e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--aurora-glass-border)'
                    }}
                  >
                    Revoke
                  </button>
                )}
                {confirmRevoke === link.id && (
                  <div style={{ display: 'flex', gap: 4 }}>
                    <button
                      onClick={() => revokeMutation.mutate(link.id)}
                      disabled={revokeMutation.isPending}
                      style={{
                        background: '#EF4444',
                        border: 'none',
                        borderRadius: 20,
                        color: '#FFF',
                        fontSize: 11,
                        padding: '3px 9px',
                        cursor: 'pointer',
                        opacity: revokeMutation.isPending ? 0.5 : 1,
                      }}
                    >
                      {revokeMutation.isPending ? '…' : 'Confirm'}
                    </button>
                    <button
                      onClick={() => setConfirmRevoke(null)}
                      style={{ ...AURORA_BTN_GHOST, fontSize: 11, padding: '3px 9px' }}
                    >
                      Cancel
                    </button>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Mint button */}
      {!mintOpen && (
        <button
          onClick={() => setMintOpen(true)}
          style={{ ...AURORA_BTN_GHOST, alignSelf: 'flex-start' }}
        >
          + Create share link
        </button>
      )}

      {/* Mint form */}
      {mintOpen && (
        <div
          style={{
            background: 'var(--aurora-glass)',
            border: '1px solid var(--aurora-glass-border)',
            borderRadius: 10,
            padding: '14px',
            display: 'flex',
            flexDirection: 'column',
            gap: 12,
          }}
        >
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <label style={labelStyle}>Label (optional)</label>
              <input
                type="text"
                value={mintLabel}
                onChange={(e) => setMintLabel(e.target.value)}
                placeholder="e.g. Public gallery"
                style={AURORA_INPUT}
              />
            </div>
            <div>
              <label style={labelStyle}>Expires in (days)</label>
              <input
                type="number"
                min="0"
                value={mintExpiry}
                onChange={(e) => setMintExpiry(e.target.value)}
                placeholder="30 (blank = instance default)"
                style={AURORA_INPUT}
              />
            </div>
          </div>
          {mintError && <p style={{ fontSize: 11, color: 'var(--aurora-danger)', margin: 0 }}>{mintError}</p>}
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={() => mintMutation.mutate()}
              disabled={mintMutation.isPending}
              style={{ ...AURORA_BTN_PRIMARY, opacity: mintMutation.isPending ? 0.5 : 1 }}
            >
              {mintMutation.isPending ? 'Creating…' : 'Create & copy link'}
            </button>
            <button
              onClick={() => { setMintOpen(false); setMintError(null) }}
              style={AURORA_BTN_GHOST}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
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
  const { user } = useAuth()
  const isOwnerOrAdmin = !!user  // all authenticated users can manage their items
  const uploadInputRef = useRef<HTMLInputElement | null>(null)
  const [uploadError, setUploadError] = useState<string | null>(null)

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

  const uploadImageMutation = useMutation({
    mutationFn: (file: File) => api.uploadItemImage(key!, file),
    onSuccess: () => {
      setUploadError(null)
      void queryClient.invalidateQueries({ queryKey: ['item', key] })
    },
    onError: (e) => {
      setUploadError(e instanceof Error ? e.message : 'Upload failed.')
    },
  })

  const deleteImageMutation = useMutation({
    mutationFn: (imageId: number) => api.deleteItemImage(key!, imageId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['item', key] })
    },
  })

  // Phase 15: manual modified-override mutation
  const overrideMutation = useMutation({
    mutationFn: (override: 'modified' | 'original' | null) =>
      api.patchModifiedOverride(key!, override),
    onSuccess: (updatedItem) => {
      queryClient.setQueryData(['item', key], updatedItem)
    },
  })

  // Delete item (moves the directory to trash server-side, removes the DB row)
  const [confirmDeleteItem, setConfirmDeleteItem] = useState(false)
  const deleteItemMutation = useMutation({
    mutationFn: () => api.deleteItem(key!),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['items'] })
      navigate('/catalog', { replace: true })
    },
  })

  if (isLoading) {
    return (
      <div style={{ padding: '96px 0', textAlign: 'center', fontSize: 13, color: 'var(--aurora-muted)' }}>
        Loading…
      </div>
    )
  }

  if (isError || !item) {
    return (
      <div style={{ padding: '96px 0', textAlign: 'center' }}>
        <p style={{ fontSize: 13, color: 'var(--aurora-danger)', marginBottom: 12 }}>Item not found.</p>
        <button
          onClick={() => navigate(-1)}
          style={{ ...AURORA_BTN_GHOST, cursor: 'pointer' }}
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
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 16,
        maxWidth: 900,
        margin: '0 auto',
        color: 'var(--aurora-text)',
      }}
    >
      {/* Breadcrumb */}
      <nav style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
        <Link
          to="/catalog"
          style={{ color: 'var(--aurora-muted)', textDecoration: 'none', transition: 'color 0.15s' }}
          onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.color = 'var(--aurora-accent)' }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.color = 'var(--aurora-muted)' }}
        >
          Catalog
        </Link>
        <span style={{ color: 'var(--aurora-muted)' }}>›</span>
        <span
          style={{
            color: 'var(--aurora-text-dim)',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            fontWeight: 500,
          }}
        >
          {item.title}
        </span>

        {/* Delete item (moves to trash) */}
        {isOwnerOrAdmin && (
          <span style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6 }}>
            {deleteItemMutation.isError && (
              <span style={{ fontSize: 11, color: 'var(--aurora-danger)' }}>Delete failed</span>
            )}
            {!confirmDeleteItem ? (
              <button
                onClick={() => setConfirmDeleteItem(true)}
                title="Move this item to trash"
                style={{
                  ...AURORA_BTN_GHOST,
                  fontSize: 11,
                  padding: '4px 10px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 5,
                  color: 'var(--aurora-danger)',
                  cursor: 'pointer',
                }}
              >
                <Trash2 size={12} />
                Delete
              </button>
            ) : (
              <>
                <span style={{ fontSize: 11, color: 'var(--aurora-muted)' }}>Move to trash?</span>
                <button
                  onClick={() => deleteItemMutation.mutate()}
                  disabled={deleteItemMutation.isPending}
                  style={{
                    ...AURORA_BTN_PRIMARY,
                    fontSize: 11,
                    padding: '4px 10px',
                    background: 'var(--aurora-danger)',
                    opacity: deleteItemMutation.isPending ? 0.6 : 1,
                    cursor: deleteItemMutation.isPending ? 'not-allowed' : 'pointer',
                  }}
                >
                  {deleteItemMutation.isPending ? 'Deleting…' : 'Confirm delete'}
                </button>
                <button
                  onClick={() => setConfirmDeleteItem(false)}
                  disabled={deleteItemMutation.isPending}
                  style={{ ...AURORA_BTN_GHOST, fontSize: 11, padding: '4px 10px', cursor: 'pointer' }}
                >
                  Cancel
                </button>
              </>
            )}
          </span>
        )}
      </nav>

      {/* Hero: images + metadata side by side */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        {/* Left: images */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <ImageCarousel
            images={sortedImages}
            itemKey={item.key}
            onSetDefault={(imageId) => setDefaultMutation.mutate(imageId)}
            onDeleteImage={(imageId) => deleteImageMutation.mutate(imageId)}
            isSettingDefault={setDefaultMutation.isPending}
            isDeletingImage={deleteImageMutation.isPending}
            isOwner={isOwnerOrAdmin}
          />
          {/* Upload control (authenticated users only) */}
          {isOwnerOrAdmin && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <button
                onClick={() => uploadInputRef.current?.click()}
                disabled={uploadImageMutation.isPending}
                style={{
                  ...AURORA_BTN_GHOST,
                  fontSize: 12,
                  padding: '6px 14px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  opacity: uploadImageMutation.isPending ? 0.5 : 1,
                  alignSelf: 'flex-start',
                }}
              >
                <Upload size={13} />
                {uploadImageMutation.isPending ? 'Uploading…' : 'Upload image'}
              </button>
              <input
                ref={uploadInputRef}
                type="file"
                accept="image/png,image/jpeg,image/webp,image/gif,.png,.jpg,.jpeg,.webp,.gif"
                style={{ display: 'none' }}
                onChange={(e) => {
                  const f = e.target.files?.[0]
                  if (f) uploadImageMutation.mutate(f)
                  e.target.value = ''
                }}
              />
              {uploadError && (
                <span style={{ fontSize: 11, color: 'var(--aurora-danger)' }}>{uploadError}</span>
              )}
            </div>
          )}
        </div>

        {/* Right: metadata card */}
        <div
          style={{
            ...AURORA_CARD,
            padding: '18px 20px',
            display: 'flex',
            flexDirection: 'column',
            gap: 14,
          }}
        >
          {/* Title + creator */}
          <div>
            <h1 style={{ fontSize: 20, fontWeight: 800, lineHeight: 1.2, color: 'var(--aurora-text)', letterSpacing: '-0.02em', margin: '0 0 6px' }}>
              {item.title}
            </h1>
            {item.creator && (
              <p style={{ fontSize: 12, color: 'var(--aurora-muted)', margin: 0 }}>
                By{' '}
                <Link
                  to={`/catalog?creator_id=${item.creator.id}`}
                  style={{ color: 'var(--aurora-accent)', textDecoration: 'none' }}
                  onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.textDecoration = 'underline' }}
                  onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.textDecoration = 'none' }}
                >
                  {item.creator.name}
                </Link>
                {item.creator.source_site && (
                  <span style={{ marginLeft: 4, fontSize: 11, color: 'var(--aurora-muted)' }}>
                    ({item.creator.source_site})
                  </span>
                )}
              </p>
            )}
          </div>

          {/* Tags */}
          {item.tags.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {item.tags.map((tag) => (
                <Link
                  key={tag.id}
                  to={`/catalog?tags=${encodeURIComponent(tag.name)}`}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    padding: '3px 9px',
                    borderRadius: 20,
                    fontSize: 11,
                    fontWeight: 500,
                    background: 'var(--aurora-glass)',
                    border: '1px solid var(--aurora-glass-border)',
                    color: 'var(--aurora-text-dim)',
                    textDecoration: 'none',
                    transition: 'all 0.15s',
                  }}
                  onMouseEnter={(e) => {
                    (e.currentTarget as HTMLElement).style.background = 'var(--aurora-pill)'
                    ;(e.currentTarget as HTMLElement).style.borderColor = 'var(--aurora-pill-border)'
                    ;(e.currentTarget as HTMLElement).style.color = 'var(--aurora-accent)'
                  }}
                  onMouseLeave={(e) => {
                    (e.currentTarget as HTMLElement).style.background = 'var(--aurora-glass)'
                    ;(e.currentTarget as HTMLElement).style.borderColor = 'var(--aurora-glass-border)'
                    ;(e.currentTarget as HTMLElement).style.color = 'var(--aurora-text-dim)'
                  }}
                >
                  #{tag.name}
                </Link>
              ))}
            </div>
          )}

          {/* Source + license */}
          {(item.source_url || item.license) && (
            <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', columnGap: 10, rowGap: 6, alignItems: 'baseline', fontSize: 12 }}>
              {item.source_url && (
                <>
                  <span style={{ color: 'var(--aurora-muted)', fontWeight: 600, fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.06em', whiteSpace: 'nowrap' }}>Source</span>
                  <a
                    href={item.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ color: 'var(--aurora-accent)', textDecoration: 'none', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'block' }}
                    onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.textDecoration = 'underline' }}
                    onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.textDecoration = 'none' }}
                  >
                    {item.source_url}
                  </a>
                </>
              )}
              {item.license && (
                <>
                  <span style={{ color: 'var(--aurora-muted)', fontWeight: 600, fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.06em', whiteSpace: 'nowrap' }}>License</span>
                  <span style={{ color: 'var(--aurora-text-dim)' }}>{item.license}</span>
                </>
              )}
            </div>
          )}

          {/* Phase 15: Local-modification badge (only when source_url present) */}
          {item.source_url && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {/* Badge */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                {item.is_modified ? (
                  <span
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 5,
                      fontSize: 11,
                      fontWeight: 700,
                      background: 'rgba(220,38,38,0.10)',
                      color: 'var(--aurora-danger)',
                      border: '1px solid rgba(220,38,38,0.30)',
                      borderRadius: 20,
                      padding: '3px 10px',
                    }}
                  >
                    ⚠ Modified from original
                  </span>
                ) : (
                  <span
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 5,
                      fontSize: 11,
                      fontWeight: 700,
                      background: 'rgba(22,163,74,0.10)',
                      color: '#16a34a',
                      border: '1px solid rgba(22,163,74,0.25)',
                      borderRadius: 20,
                      padding: '3px 10px',
                    }}
                    className="dark:text-green-300"
                  >
                    ✓ Matches original
                  </span>
                )}
                {item.locally_modified_at && (
                  <span style={{ fontSize: 11, color: 'var(--aurora-muted)' }}>
                    Last changed {formatDate(item.locally_modified_at)}
                  </span>
                )}
                {item.modified_override && (
                  <span
                    style={{
                      fontSize: 10,
                      fontWeight: 600,
                      background: 'var(--aurora-glass)',
                      border: '1px solid var(--aurora-glass-border)',
                      borderRadius: 20,
                      padding: '2px 8px',
                      color: 'var(--aurora-muted)',
                    }}
                  >
                    manual
                  </span>
                )}
              </div>

              {/* Override control (owner/admin only) */}
              {isOwnerOrAdmin && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                  <span style={{ fontSize: 10, color: 'var(--aurora-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                    Override:
                  </span>
                  {(['modified', 'original', null] as const).map((val) => {
                    const label = val === null ? 'Auto' : val === 'modified' ? 'Modified' : 'Original'
                    const isActive = item.modified_override === val
                    return (
                      <button
                        key={String(val)}
                        onClick={() => overrideMutation.mutate(val)}
                        disabled={overrideMutation.isPending}
                        style={{
                          fontSize: 11,
                          fontWeight: isActive ? 700 : 500,
                          padding: '3px 10px',
                          borderRadius: 20,
                          border: isActive
                            ? '1px solid var(--aurora-accent)'
                            : '1px solid var(--aurora-glass-border)',
                          background: isActive ? 'rgba(15,164,171,0.12)' : 'var(--aurora-glass)',
                          color: isActive ? 'var(--aurora-accent)' : 'var(--aurora-text-dim)',
                          cursor: overrideMutation.isPending ? 'not-allowed' : 'pointer',
                          opacity: overrideMutation.isPending ? 0.6 : 1,
                          transition: 'all 0.15s',
                        }}
                      >
                        {label}
                      </button>
                    )
                  })}
                </div>
              )}
            </div>
          )}

          {/* Description */}
          {item.description && (
            <p style={{ fontSize: 12, color: 'var(--aurora-text-dim)', lineHeight: 1.6, whiteSpace: 'pre-wrap', margin: 0 }}>
              {item.description}
            </p>
          )}

          {/* Timestamps */}
          <div style={{ fontSize: 11, color: 'var(--aurora-muted)', marginTop: 'auto' }}>
            Added {formatDate(item.created_at)}
            {item.updated_at !== item.created_at && (
              <> · Updated {formatDate(item.updated_at)}</>
            )}
          </div>
        </div>
      </div>

      {/* Location */}
      <AuroraSection title="Location">
        <PathDisplay dirPath={item.dir_path} itemKey={item.key} libraryId={item.library_id} />
      </AuroraSection>

      {/* Downloads */}
      <AuroraSection title="Files &amp; Downloads">
        <DownloadsSection itemKey={item.key} files={item.files} />
      </AuroraSection>

      {/* Object breakdown (Phase 16) — show when item has model files */}
      {item.files.some((f) => f.role === 'model') && (
        <AuroraSection title="Object Breakdown">
          <ObjectBreakdownSection item={item} />
        </AuroraSection>
      )}

      {/* Print History */}
      <AuroraSection title="Print History">
        {isOwnerOrAdmin ? (
          <PrintHistorySection itemKey={item.key} />
        ) : (
          <p style={{ fontSize: 12, color: 'var(--aurora-muted)', fontStyle: 'italic', margin: 0 }}>
            Sign in to view print history.
          </p>
        )}
      </AuroraSection>

      {/* Share */}
      <AuroraSection title="Share">
        {isOwnerOrAdmin ? (
          <ShareSection itemKey={item.key} />
        ) : (
          <p style={{ fontSize: 12, color: 'var(--aurora-muted)', fontStyle: 'italic', margin: 0 }}>
            Sign in to manage share links.
          </p>
        )}
      </AuroraSection>
    </div>
  )
}
