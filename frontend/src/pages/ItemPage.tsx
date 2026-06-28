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
 */

import React, { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'

import * as api from '@/lib/api'
import { mapBundleStatus, rewritePath, shouldContinuePolling, type ZipPollStatus } from '@/lib/catalog-utils'
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

  // Reset zip state when includeHistory changes (so the next click starts fresh)
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
      <div className="flex flex-col gap-2">
        {/* Include history checkbox */}
        <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
          <input
            type="checkbox"
            checked={includeHistory}
            onChange={(e) => setIncludeHistory(e.target.checked)}
            className="h-4 w-4 rounded border-border accent-primary"
          />
          <span>Include print history</span>
          <span
            className="text-xs text-muted-foreground"
            title="Adds a print-history.json to the ZIP. Public records always included; private records included only for your own download."
          >
            (?)
          </span>
        </label>

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

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div
        className="bg-background rounded-lg border border-border shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <h2 className="text-base font-semibold">
            {existing ? 'Edit Print Record' : 'Log a Print'}
          </h2>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground transition-colors"
          >
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-5 flex flex-col gap-4">
          {/* Visibility + Date */}
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-muted-foreground">Visibility</label>
              <select
                value={form.visibility}
                onChange={(e) => setForm((f) => ({ ...f, visibility: e.target.value }))}
                className="input-base py-1.5 text-sm"
              >
                <option value="private">Private</option>
                <option value="public">Public</option>
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-muted-foreground">Date</label>
              <input
                type="date"
                value={form.date ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, date: e.target.value || null }))}
                className="input-base py-1.5 text-sm"
              />
            </div>
          </div>

          {/* Outcome */}
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-muted-foreground">Outcome</label>
              <select
                value={form.success == null ? '' : form.success ? 'true' : 'false'}
                onChange={(e) => {
                  const v = e.target.value
                  setForm((f) => ({
                    ...f,
                    success: v === '' ? null : v === 'true',
                  }))
                }}
                className="input-base py-1.5 text-sm"
              >
                <option value="">Not recorded</option>
                <option value="true">Success</option>
                <option value="false">Failed</option>
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-muted-foreground">Rating (1–5)</label>
              <select
                value={form.rating ?? ''}
                onChange={(e) => {
                  const v = e.target.value
                  setForm((f) => ({ ...f, rating: v === '' ? null : Number(v) }))
                }}
                className="input-base py-1.5 text-sm"
              >
                <option value="">None</option>
                {[1, 2, 3, 4, 5].map((n) => (
                  <option key={n} value={n}>{n} — {renderStars(n)}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Printer + Material */}
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-muted-foreground">Printer</label>
              <input
                type="text"
                value={form.printer ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, printer: e.target.value }))}
                placeholder="e.g. Bambu X1C"
                className="input-base py-1.5 text-sm"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-muted-foreground">Material</label>
              <input
                type="text"
                value={form.material ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, material: e.target.value }))}
                placeholder="e.g. PLA"
                className="input-base py-1.5 text-sm"
              />
            </div>
          </div>

          {/* Filament color + supports */}
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-muted-foreground">Filament color</label>
              <input
                type="text"
                value={form.filament_color ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, filament_color: e.target.value }))}
                placeholder="e.g. Black"
                className="input-base py-1.5 text-sm"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-muted-foreground">Supports</label>
              <select
                value={form.supports == null ? '' : form.supports ? 'true' : 'false'}
                onChange={(e) => {
                  const v = e.target.value
                  setForm((f) => ({
                    ...f,
                    supports: v === '' ? null : v === 'true',
                  }))
                }}
                className="input-base py-1.5 text-sm"
              >
                <option value="">Not recorded</option>
                <option value="true">Yes</option>
                <option value="false">No</option>
              </select>
            </div>
          </div>

          {/* Nozzle + layer height */}
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-muted-foreground">Nozzle (mm)</label>
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
                className="input-base py-1.5 text-sm"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-muted-foreground">Layer height (mm)</label>
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
                className="input-base py-1.5 text-sm"
              />
            </div>
          </div>

          {/* Note */}
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-muted-foreground">Note</label>
            <textarea
              rows={3}
              value={form.note ?? ''}
              onChange={(e) => setForm((f) => ({ ...f, note: e.target.value }))}
              placeholder="Any notes about this print…"
              className="input-base py-1.5 text-sm resize-none"
            />
          </div>

          {submitError && (
            <p className="text-sm text-destructive">{submitError}</p>
          )}

          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-border px-4 py-2 text-sm hover:bg-accent transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isPending}
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
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

      <div className="rounded-lg border border-border bg-card p-4 flex flex-col gap-3">
        {/* Header row */}
        <div className="flex items-start justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            {/* Visibility badge */}
            <span
              className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                record.visibility === 'public'
                  ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
                  : 'bg-muted text-muted-foreground'
              }`}
            >
              {record.visibility}
            </span>

            {/* Outcome chip */}
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

            {/* Rating */}
            {record.rating != null && (
              <span className="text-sm text-amber-500" title={`Rating: ${record.rating}/5`}>
                {renderStars(record.rating)}
              </span>
            )}

            {/* Date */}
            {record.date && (
              <span className="text-xs text-muted-foreground">{record.date}</span>
            )}
          </div>

          {/* Actions */}
          <div className="flex gap-1 shrink-0">
            <button
              onClick={() => setEditing(true)}
              className="rounded px-2 py-1 text-xs text-muted-foreground hover:bg-muted transition-colors"
            >
              Edit
            </button>
            {!confirmDelete ? (
              <button
                onClick={() => setConfirmDelete(true)}
                className="rounded px-2 py-1 text-xs text-muted-foreground hover:bg-red-100 hover:text-red-700 transition-colors"
              >
                Delete
              </button>
            ) : (
              <div className="flex gap-1">
                <button
                  onClick={() => deleteMutation.mutate()}
                  disabled={deleteMutation.isPending}
                  className="rounded px-2 py-1 text-xs bg-red-600 text-white hover:bg-red-700 disabled:opacity-50 transition-colors"
                >
                  {deleteMutation.isPending ? '…' : 'Confirm'}
                </button>
                <button
                  onClick={() => setConfirmDelete(false)}
                  className="rounded px-2 py-1 text-xs text-muted-foreground hover:bg-muted transition-colors"
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
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
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

        {/* Note */}
        {record.note && (
          <p className="text-sm text-muted-foreground leading-relaxed whitespace-pre-wrap">
            {record.note}
          </p>
        )}

        {/* File uploads */}
        <div className="flex flex-wrap gap-2 pt-1">
          {/* Gcode upload */}
          <button
            onClick={() => gcodeInput?.click()}
            disabled={uploadingGcode}
            className="rounded border border-border px-2 py-1 text-xs hover:bg-accent disabled:opacity-50 transition-colors"
          >
            {uploadingGcode ? 'Uploading…' : record.gcode_file_path ? 'Replace gcode' : 'Upload gcode'}
          </button>
          <input
            ref={setGcodeInput}
            type="file"
            accept=".gcode,.bgcode,.gco"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) void handleGcodeUpload(file)
              e.target.value = ''
            }}
          />

          {/* Photo upload */}
          <button
            onClick={() => photoInput?.click()}
            disabled={uploadingPhoto}
            className="rounded border border-border px-2 py-1 text-xs hover:bg-accent disabled:opacity-50 transition-colors"
          >
            {uploadingPhoto ? 'Uploading…' : record.print_photo_path ? 'Replace photo' : 'Upload photo'}
          </button>
          <input
            ref={setPhotoInput}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) void handlePhotoUpload(file)
              e.target.value = ''
            }}
          />
        </div>

        {uploadError && (
          <p className="text-xs text-destructive">{uploadError}</p>
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
    <div className="flex flex-col gap-3">
      {addingRecord && (
        <PrintRecordForm
          itemKey={itemKey}
          onClose={() => setAddingRecord(false)}
          onSaved={handleSaved}
        />
      )}

      <div className="flex items-center justify-between">
        <span className="text-sm text-muted-foreground">
          {records.length > 0 ? `${records.length} record(s)` : ''}
        </span>
        <button
          onClick={() => setAddingRecord(true)}
          className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          + Log a print
        </button>
      </div>

      {isLoading && (
        <p className="text-sm text-muted-foreground">Loading…</p>
      )}

      {isError && (
        <p className="text-sm text-destructive">Failed to load print records.</p>
      )}

      {!isLoading && !isError && records.length === 0 && (
        <p className="text-sm text-muted-foreground italic">
          No print records yet. Log your first print above.
        </p>
      )}

      <div className="flex flex-col gap-3">
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

  return (
    <div className="flex flex-col gap-3">
      {/* Link list */}
      {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {isError && <p className="text-sm text-destructive">Failed to load share links.</p>}

      {!isLoading && links.length === 0 && (
        <p className="text-sm text-muted-foreground italic">No share links yet.</p>
      )}

      {links.length > 0 && (
        <ul className="divide-y divide-border rounded-lg border border-border overflow-hidden">
          {links.map((link) => (
            <li key={link.id} className="flex items-center justify-between px-4 py-3 hover:bg-muted/30">
              <div className="flex flex-col gap-0.5 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono text-muted-foreground">
                    {link.token.slice(0, 8)}…
                  </span>
                  {link.label && (
                    <span className="text-xs font-medium truncate">{link.label}</span>
                  )}
                  {link.revoked && (
                    <span className="inline-flex items-center rounded-full bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300 px-2 py-0.5 text-xs font-medium">
                      Revoked
                    </span>
                  )}
                  {copiedToken === link.token && (
                    <span className="text-xs text-green-600">✓ Copied!</span>
                  )}
                </div>
                <span className="text-xs text-muted-foreground">
                  {formatExpiry(link.expires_at)}
                </span>
              </div>
              <div className="flex items-center gap-1 shrink-0 ml-2">
                {!link.revoked && (
                  <button
                    onClick={() => void handleCopy(link.token)}
                    className="rounded px-2 py-1 text-xs border border-border hover:bg-accent transition-colors"
                  >
                    Copy link
                  </button>
                )}
                {!link.revoked && confirmRevoke !== link.id && (
                  <button
                    onClick={() => setConfirmRevoke(link.id)}
                    className="rounded px-2 py-1 text-xs text-muted-foreground hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950 transition-colors"
                  >
                    Revoke
                  </button>
                )}
                {confirmRevoke === link.id && (
                  <div className="flex gap-1">
                    <button
                      onClick={() => revokeMutation.mutate(link.id)}
                      disabled={revokeMutation.isPending}
                      className="rounded px-2 py-1 text-xs bg-red-600 text-white hover:bg-red-700 disabled:opacity-50 transition-colors"
                    >
                      {revokeMutation.isPending ? '…' : 'Confirm'}
                    </button>
                    <button
                      onClick={() => setConfirmRevoke(null)}
                      className="rounded px-2 py-1 text-xs text-muted-foreground hover:bg-muted transition-colors"
                    >
                      Cancel
                    </button>
                  </div>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      {/* Mint button */}
      {!mintOpen && (
        <button
          onClick={() => setMintOpen(true)}
          className="self-start rounded-md border border-border px-3 py-1.5 text-xs font-medium hover:bg-accent transition-colors"
        >
          + Create share link
        </button>
      )}

      {/* Mint form */}
      {mintOpen && (
        <div className="rounded-lg border border-border bg-muted/20 p-4 flex flex-col gap-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-muted-foreground">Label (optional)</label>
              <input
                type="text"
                value={mintLabel}
                onChange={(e) => setMintLabel(e.target.value)}
                placeholder="e.g. Public gallery"
                className="input-base py-1.5 text-sm"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-muted-foreground">Expires in (days)</label>
              <input
                type="number"
                min="0"
                value={mintExpiry}
                onChange={(e) => setMintExpiry(e.target.value)}
                placeholder="30 (blank = instance default)"
                className="input-base py-1.5 text-sm"
              />
            </div>
          </div>
          {mintError && <p className="text-xs text-destructive">{mintError}</p>}
          <div className="flex gap-2">
            <button
              onClick={() => mintMutation.mutate()}
              disabled={mintMutation.isPending}
              className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
            >
              {mintMutation.isPending ? 'Creating…' : 'Create & copy link'}
            </button>
            <button
              onClick={() => { setMintOpen(false); setMintError(null) }}
              className="rounded-md border border-border px-3 py-1.5 text-xs hover:bg-accent transition-colors"
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

      {/* Print History (Phase 7) */}
      <section>
        <h2 className="text-base font-semibold mb-3">Print History</h2>
        {isOwnerOrAdmin ? (
          <PrintHistorySection itemKey={item.key} />
        ) : (
          <p className="text-sm text-muted-foreground">Sign in to view print history.</p>
        )}
      </section>

      {/* Share (Phase 7) */}
      <section>
        <h2 className="text-base font-semibold mb-3">Share</h2>
        {isOwnerOrAdmin ? (
          <ShareSection itemKey={item.key} />
        ) : (
          <p className="text-sm text-muted-foreground">Sign in to manage share links.</p>
        )}
      </section>
    </div>
  )
}
