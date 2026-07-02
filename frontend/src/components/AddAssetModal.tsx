/**
 * AddAssetModal — two-tab dialog for starting an import session.
 *
 * Tab 1: Upload files — drag-and-drop zone + file input; optional source URL
 *         + title; library selector.
 *         Flow: create draft session → upload files → call /process → redirect
 *         to wizard.
 *
 * Tab 2: From URL — source URL input; library selector.
 *         Flow: create URL session (auto-enqueues processing) → redirect to
 *         wizard.
 *
 * No @radix-ui/react-dialog available — uses a custom Tailwind overlay modal.
 *
 * Styling: Aurora aesthetic — glass cards, teal accent (#0FA4AB), --aurora-* CSS vars.
 */

import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { X as XIcon } from 'lucide-react'
import * as api from '@/lib/api'

// ---------------------------------------------------------------------------
// Aurora style constants
// ---------------------------------------------------------------------------

const AURORA_INPUT: React.CSSProperties = {
  background: 'var(--aurora-input-bg)',
  border: '1px solid var(--aurora-input-border)',
  borderRadius: 8,
  color: 'var(--aurora-text)',
  padding: '7px 11px',
  fontSize: 13,
  outline: 'none',
  width: '100%',
  transition: 'border-color 0.15s, box-shadow 0.15s',
  boxSizing: 'border-box',
  display: 'block',
}

const AURORA_BTN_PRIMARY: React.CSSProperties = {
  background: 'var(--aurora-accent)',
  border: 'none',
  borderRadius: 20,
  color: 'var(--aurora-accent-fg)',
  fontSize: 13,
  fontWeight: 700,
  padding: '8px 20px',
  cursor: 'pointer',
  boxShadow: '0 4px 14px var(--aurora-accent-glow)',
  transition: 'opacity 0.15s',
  display: 'inline-flex',
  alignItems: 'center',
  gap: 6,
}

const AURORA_BTN_GHOST: React.CSSProperties = {
  background: 'var(--aurora-glass)',
  border: '1px solid var(--aurora-glass-border)',
  borderRadius: 20,
  color: 'var(--aurora-text-dim)',
  fontSize: 13,
  padding: '7px 18px',
  cursor: 'pointer',
  transition: 'all 0.15s',
  display: 'inline-flex',
  alignItems: 'center',
}

const SECTION_LABEL: React.CSSProperties = {
  fontSize: 10,
  fontWeight: 700,
  color: 'var(--aurora-muted)',
  letterSpacing: '0.08em',
  textTransform: 'uppercase',
  display: 'block',
  marginBottom: 5,
}

function onAuroraFocus(e: React.FocusEvent<HTMLInputElement | HTMLSelectElement>) {
  e.currentTarget.style.borderColor = 'var(--aurora-pill-border)'
  e.currentTarget.style.boxShadow = '0 0 0 3px var(--aurora-pill)'
}
function onAuroraBlur(e: React.FocusEvent<HTMLInputElement | HTMLSelectElement>) {
  e.currentTarget.style.borderColor = 'var(--aurora-input-border)'
  e.currentTarget.style.boxShadow = 'none'
}

// ---------------------------------------------------------------------------
// Tab: Upload Files
// ---------------------------------------------------------------------------

interface UploadTabProps {
  libraries: api.LibraryOut[]
  onClose: () => void
}

function UploadTab({ libraries, onClose }: UploadTabProps) {
  const navigate = useNavigate()
  const [files, setFiles] = useState<File[]>([])
  const [sourceUrl, setSourceUrl] = useState('')
  const [title, setTitle] = useState('')
  const [libraryId, setLibraryId] = useState<number | ''>(
    libraries[0]?.id ?? '',
  )
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const createMutation = useMutation({
    mutationFn: () =>
      api.createImportSession({
        source_type: 'upload',
        library_id: libraryId !== '' ? libraryId : null,
        title: title.trim() || null,
        source_url: sourceUrl.trim() || null,
      }),
  })

  const uploadMutation = useMutation({
    mutationFn: ({ id, fs }: { id: string; fs: File[] }) =>
      api.uploadSessionFiles(id, fs),
  })

  const processMutation = useMutation({
    mutationFn: (id: string) => api.processImportSession(id),
  })

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)

    if (files.length === 0) {
      setError('Please select at least one file.')
      return
    }
    if (libraryId === '') {
      setError('Please select a library.')
      return
    }

    try {
      const session = await createMutation.mutateAsync()
      await uploadMutation.mutateAsync({ id: session.id, fs: files })
      await processMutation.mutateAsync(session.id)
      onClose()
      navigate(`/import/${session.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed.')
    }
  }

  const addFiles = useCallback((incoming: FileList | File[]) => {
    const arr = Array.from(incoming)
    setFiles((prev) => {
      const existing = new Set(prev.map((f) => f.name))
      return [...prev, ...arr.filter((f) => !existing.has(f.name))]
    })
  }, [])

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setDragging(false)
      addFiles(e.dataTransfer.files)
    },
    [addFiles],
  )

  const isLoading =
    createMutation.isPending ||
    uploadMutation.isPending ||
    processMutation.isPending

  return (
    <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Drop zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          borderRadius: 12,
          border: `2px dashed ${dragging ? 'var(--aurora-accent)' : 'var(--aurora-glass-border)'}`,
          background: dragging ? 'var(--aurora-pill)' : 'var(--aurora-glass)',
          padding: '36px 20px',
          cursor: 'pointer',
          transition: 'all 0.15s',
          boxShadow: dragging ? 'var(--aurora-glow)' : 'none',
          gap: 8,
        }}
        role="button"
        tabIndex={0}
        aria-label="Drop files here or click to browse"
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); inputRef.current?.click() } }}
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.5}
          style={{ width: 32, height: 32, color: dragging ? 'var(--aurora-accent)' : 'var(--aurora-muted)', transition: 'color 0.15s' }}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
        </svg>
        <p style={{ fontSize: 13, fontWeight: 600, color: 'var(--aurora-text)', margin: 0, textAlign: 'center' }}>
          Drag files here or{' '}
          <span style={{ color: 'var(--aurora-accent)' }}>click to browse</span>
        </p>
        <p style={{ fontSize: 11, color: 'var(--aurora-muted)', margin: 0, textAlign: 'center' }}>
          STL, 3MF, OBJ, PLY, STEP, GCODE, images…
        </p>
        <input
          ref={inputRef}
          type="file"
          multiple
          className="sr-only"
          onChange={(e) => e.target.files && addFiles(e.target.files)}
        />
      </div>

      {/* File list */}
      {files.length > 0 && (
        <div
          style={{
            background: 'var(--aurora-glass)',
            border: '1px solid var(--aurora-glass-border)',
            borderRadius: 10,
            overflow: 'hidden',
          }}
        >
          {files.map((f, i) => (
            <div
              key={i}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '8px 12px',
                borderTop: i > 0 ? '1px solid var(--aurora-divider)' : 'none',
                transition: 'background 0.1s',
              }}
              onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.background = 'var(--aurora-glass-hover)' }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.background = 'transparent' }}
            >
              <span
                style={{
                  fontSize: 12,
                  fontFamily: 'monospace',
                  color: 'var(--aurora-text)',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                  flex: 1,
                }}
              >
                {f.name}
              </span>
              <button
                type="button"
                style={{
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  color: 'var(--aurora-muted)',
                  marginLeft: 8,
                  flexShrink: 0,
                  display: 'flex',
                  alignItems: 'center',
                  padding: 4,
                  transition: 'color 0.15s',
                }}
                onClick={() => setFiles((prev) => prev.filter((_, j) => j !== i))}
                aria-label={`Remove file ${f.name}`}
                onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.color = 'var(--aurora-danger)' }}
                onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.color = 'var(--aurora-muted)' }}
              >
                <XIcon size={13} />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Source URL */}
      <div>
        <label style={SECTION_LABEL}>
          Source URL
          <span style={{ fontWeight: 400, marginLeft: 4, textTransform: 'none', letterSpacing: 0, fontSize: 11 }}>(optional)</span>
        </label>
        <input
          type="url"
          value={sourceUrl}
          onChange={(e) => setSourceUrl(e.target.value)}
          placeholder="https://www.thingiverse.com/thing:…"
          style={AURORA_INPUT}
          onFocus={onAuroraFocus}
          onBlur={onAuroraBlur}
        />
      </div>

      {/* Title */}
      <div>
        <label style={SECTION_LABEL}>
          Title
          <span style={{ fontWeight: 400, marginLeft: 4, textTransform: 'none', letterSpacing: 0, fontSize: 11 }}>(optional — wizard will suggest one)</span>
        </label>
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="My awesome model"
          style={AURORA_INPUT}
          onFocus={onAuroraFocus}
          onBlur={onAuroraBlur}
        />
      </div>

      {/* Library */}
      <div>
        <label style={SECTION_LABEL}>Library</label>
        <select
          value={libraryId}
          onChange={(e) => setLibraryId(e.target.value !== '' ? Number(e.target.value) : '')}
          style={AURORA_INPUT}
          onFocus={onAuroraFocus}
          onBlur={onAuroraBlur}
        >
          <option value="">— select a library —</option>
          {libraries.map((lib) => (
            <option key={lib.id} value={lib.id}>
              {lib.name}
            </option>
          ))}
        </select>
      </div>

      {error && (
        <p style={{ fontSize: 13, color: 'var(--aurora-danger)', margin: 0 }}>{error}</p>
      )}

      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, paddingTop: 4 }}>
        <button
          type="button"
          onClick={onClose}
          style={AURORA_BTN_GHOST}
          onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass-hover)' }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass)' }}
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={isLoading}
          style={{ ...AURORA_BTN_PRIMARY, opacity: isLoading ? 0.6 : 1, cursor: isLoading ? 'not-allowed' : 'pointer' }}
          onMouseEnter={(e) => { if (!isLoading) (e.currentTarget as HTMLButtonElement).style.opacity = '0.85' }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.opacity = isLoading ? '0.6' : '1' }}
        >
          {isLoading ? 'Uploading…' : 'Upload & Start Wizard'}
        </button>
      </div>
    </form>
  )
}

// ---------------------------------------------------------------------------
// Tab: From URL
// ---------------------------------------------------------------------------

interface UrlTabProps {
  libraries: api.LibraryOut[]
  onClose: () => void
}

function UrlTab({ libraries, onClose }: UrlTabProps) {
  const navigate = useNavigate()
  const [sourceUrl, setSourceUrl] = useState('')
  const [libraryId, setLibraryId] = useState<number | ''>(
    libraries[0]?.id ?? '',
  )
  const [error, setError] = useState<string | null>(null)

  const createMutation = useMutation({
    mutationFn: () =>
      api.createImportSession({
        source_type: 'url',
        source_url: sourceUrl.trim(),
        library_id: libraryId !== '' ? libraryId : null,
      }),
  })

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)

    if (!sourceUrl.trim()) {
      setError('Please enter a source URL.')
      return
    }
    if (libraryId === '') {
      setError('Please select a library.')
      return
    }

    try {
      const session = await createMutation.mutateAsync()
      onClose()
      navigate(`/import/${session.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start import.')
    }
  }

  return (
    <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div>
        <label style={SECTION_LABEL}>Source URL</label>
        <input
          type="url"
          value={sourceUrl}
          onChange={(e) => setSourceUrl(e.target.value)}
          placeholder="https://www.thingiverse.com/thing:…"
          style={AURORA_INPUT}
          autoFocus
          onFocus={onAuroraFocus}
          onBlur={onAuroraBlur}
        />
        <p style={{ marginTop: 5, fontSize: 11, color: 'var(--aurora-muted)' }}>
          The backend will scrape metadata, images, and tags automatically.
        </p>
      </div>

      <div>
        <label style={SECTION_LABEL}>Library</label>
        <select
          value={libraryId}
          onChange={(e) => setLibraryId(e.target.value !== '' ? Number(e.target.value) : '')}
          style={AURORA_INPUT}
          onFocus={onAuroraFocus}
          onBlur={onAuroraBlur}
        >
          <option value="">— select a library —</option>
          {libraries.map((lib) => (
            <option key={lib.id} value={lib.id}>
              {lib.name}
            </option>
          ))}
        </select>
      </div>

      {error && (
        <p style={{ fontSize: 13, color: 'var(--aurora-danger)', margin: 0 }}>{error}</p>
      )}

      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, paddingTop: 4 }}>
        <button
          type="button"
          onClick={onClose}
          style={AURORA_BTN_GHOST}
          onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass-hover)' }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass)' }}
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={createMutation.isPending}
          style={{ ...AURORA_BTN_PRIMARY, opacity: createMutation.isPending ? 0.6 : 1, cursor: createMutation.isPending ? 'not-allowed' : 'pointer' }}
          onMouseEnter={(e) => { if (!createMutation.isPending) (e.currentTarget as HTMLButtonElement).style.opacity = '0.85' }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.opacity = createMutation.isPending ? '0.6' : '1' }}
        >
          {createMutation.isPending ? 'Starting…' : 'Start Import'}
        </button>
      </div>
    </form>
  )
}

// ---------------------------------------------------------------------------
// Modal shell
// ---------------------------------------------------------------------------

interface AddAssetModalProps {
  open: boolean
  onClose: () => void
}

type TabId = 'upload' | 'url'

export function AddAssetModal({ open, onClose }: AddAssetModalProps) {
  const [activeTab, setActiveTab] = useState<TabId>('upload')

  const { data: libraries, isLoading: libsLoading } = useQuery({
    queryKey: ['libraries'],
    queryFn: () => api.listLibraries(),
    enabled: open,
    staleTime: 60_000,
  })

  // Close on Escape
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, onClose])

  if (!open) return null

  const libs = libraries ?? []

  const TABS: [TabId, string][] = [
    ['upload', 'Upload Files'],
    ['url', 'From URL'],
  ]

  return (
    /* Backdrop — aurora dark blur */
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
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      {/* Dialog panel — aurora palette card */}
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Add Asset"
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
          color: 'var(--aurora-text)',
        } as React.CSSProperties}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '16px 20px',
            borderBottom: '1px solid var(--aurora-divider)',
          }}
        >
          <h2 style={{ fontSize: 15, fontWeight: 700, color: 'var(--aurora-text)', margin: 0 }}>
            Add Asset
          </h2>
          <button
            onClick={onClose}
            aria-label="Close"
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
              transition: 'all 0.15s',
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass-hover)'
              ;(e.currentTarget as HTMLButtonElement).style.color = 'var(--aurora-text)'
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass)'
              ;(e.currentTarget as HTMLButtonElement).style.color = 'var(--aurora-muted)'
            }}
          >
            <XIcon size={14} />
          </button>
        </div>

        {/* Tab bar */}
        <div
          style={{
            display: 'flex',
            borderBottom: '1px solid var(--aurora-divider)',
            padding: '0 20px',
          }}
        >
          {TABS.map(([id, label]) => (
            <button
              key={id}
              onClick={() => setActiveTab(id)}
              style={{
                background: 'none',
                border: 'none',
                borderBottom: `2px solid ${activeTab === id ? 'var(--aurora-accent)' : 'transparent'}`,
                color: activeTab === id ? 'var(--aurora-accent)' : 'var(--aurora-muted)',
                fontSize: 13,
                fontWeight: activeTab === id ? 700 : 400,
                padding: '12px 16px 10px',
                cursor: 'pointer',
                transition: 'all 0.15s',
                marginBottom: -1,
              }}
              onMouseEnter={(e) => {
                if (activeTab !== id) {
                  (e.currentTarget as HTMLButtonElement).style.color = 'var(--aurora-text-dim)'
                }
              }}
              onMouseLeave={(e) => {
                if (activeTab !== id) {
                  (e.currentTarget as HTMLButtonElement).style.color = 'var(--aurora-muted)'
                }
              }}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Tab body */}
        <div style={{ padding: '20px' }}>
          {libsLoading ? (
            <p style={{ padding: '24px 0', textAlign: 'center', fontSize: 13, color: 'var(--aurora-muted)' }}>
              Loading libraries…
            </p>
          ) : libs.length === 0 ? (
            <div
              style={{
                padding: '24px 0',
                textAlign: 'center',
                background: 'rgba(245,158,11,0.08)',
                border: '1px solid rgba(245,158,11,0.25)',
                borderRadius: 10,
              }}
            >
              <p style={{ fontSize: 13, color: '#D97706', margin: 0 }}>
                No libraries configured. Ask an admin to add one before importing.
              </p>
            </div>
          ) : activeTab === 'upload' ? (
            <UploadTab libraries={libs} onClose={onClose} />
          ) : (
            <UrlTab libraries={libs} onClose={onClose} />
          )}
        </div>
      </div>
    </div>
  )
}
