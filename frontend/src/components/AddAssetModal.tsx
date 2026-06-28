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
 */

import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import * as api from '@/lib/api'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const MODEL_EXTS = new Set([
  '.stl', '.3mf', '.obj', '.ply', '.step', '.stp', '.gcode',
  '.jpg', '.jpeg', '.png', '.webp', '.gif',
])

function isValidFile(file: File): boolean {
  const name = file.name.toLowerCase()
  return MODEL_EXTS.has(`.${name.split('.').pop() ?? ''}`)
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
    <form onSubmit={handleSubmit} className="space-y-4">
      {/* Drop zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        className={`flex flex-col items-center justify-center rounded-lg border-2 border-dashed px-4 py-8 cursor-pointer transition-colors
          ${dragging
            ? 'border-primary bg-primary/5'
            : 'border-border hover:border-primary/50 hover:bg-muted/30'
          }`}
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.5}
          className="mb-2 h-8 w-8 text-muted-foreground"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5"
          />
        </svg>
        <p className="text-sm font-medium">
          Drag files here or <span className="text-primary">click to browse</span>
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
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
        <ul className="space-y-1 text-sm">
          {files.map((f, i) => (
            <li key={i} className="flex items-center justify-between rounded bg-muted/40 px-3 py-1">
              <span className="truncate">{f.name}</span>
              <button
                type="button"
                className="ml-2 shrink-0 text-muted-foreground hover:text-foreground"
                onClick={() => setFiles((prev) => prev.filter((_, j) => j !== i))}
              >
                ✕
              </button>
            </li>
          ))}
        </ul>
      )}

      {/* Source URL (optional) */}
      <div>
        <label className="mb-1 block text-sm font-medium">
          Source URL <span className="text-muted-foreground font-normal">(optional)</span>
        </label>
        <input
          type="url"
          value={sourceUrl}
          onChange={(e) => setSourceUrl(e.target.value)}
          placeholder="https://www.thingiverse.com/thing:…"
          className="input-base w-full"
        />
      </div>

      {/* Title (optional) */}
      <div>
        <label className="mb-1 block text-sm font-medium">
          Title <span className="text-muted-foreground font-normal">(optional — wizard will suggest one)</span>
        </label>
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="My awesome model"
          className="input-base w-full"
        />
      </div>

      {/* Library */}
      <div>
        <label className="mb-1 block text-sm font-medium">Library</label>
        <select
          value={libraryId}
          onChange={(e) => setLibraryId(e.target.value !== '' ? Number(e.target.value) : '')}
          className="input-base w-full"
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
        <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
      )}

      <div className="flex justify-end gap-2 pt-2">
        <button
          type="button"
          onClick={onClose}
          className="rounded-md border border-border px-4 py-2 text-sm hover:bg-accent transition-colors"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={isLoading}
          className="rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground hover:opacity-90 disabled:opacity-50 transition-colors"
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
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="mb-1 block text-sm font-medium">Source URL</label>
        <input
          type="url"
          value={sourceUrl}
          onChange={(e) => setSourceUrl(e.target.value)}
          placeholder="https://www.thingiverse.com/thing:…"
          className="input-base w-full"
          autoFocus
        />
        <p className="mt-1 text-xs text-muted-foreground">
          The backend will scrape metadata, images, and tags automatically.
        </p>
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium">Library</label>
        <select
          value={libraryId}
          onChange={(e) => setLibraryId(e.target.value !== '' ? Number(e.target.value) : '')}
          className="input-base w-full"
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
        <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
      )}

      <div className="flex justify-end gap-2 pt-2">
        <button
          type="button"
          onClick={onClose}
          className="rounded-md border border-border px-4 py-2 text-sm hover:bg-accent transition-colors"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={createMutation.isPending}
          className="rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground hover:opacity-90 disabled:opacity-50 transition-colors"
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

  return (
    /* Backdrop */
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      {/* Dialog panel */}
      <div
        className="w-full max-w-lg rounded-lg border border-border bg-background shadow-lg"
        role="dialog"
        aria-modal="true"
        aria-label="Add Asset"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <h2 className="text-lg font-semibold">Add Asset</h2>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground transition-colors"
            aria-label="Close"
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="h-5 w-5">
              <path d="M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z" />
            </svg>
          </button>
        </div>

        {/* Tab bar */}
        <div className="flex border-b border-border px-6">
          {([['upload', 'Upload Files'], ['url', 'From URL']] as [TabId, string][]).map(
            ([id, label]) => (
              <button
                key={id}
                onClick={() => setActiveTab(id)}
                className={`mr-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === id
                    ? 'border-primary text-primary'
                    : 'border-transparent text-muted-foreground hover:text-foreground'
                }`}
              >
                {label}
              </button>
            ),
          )}
        </div>

        {/* Tab body */}
        <div className="px-6 py-4">
          {libsLoading ? (
            <p className="py-4 text-center text-sm text-muted-foreground">
              Loading libraries…
            </p>
          ) : libs.length === 0 ? (
            <p className="py-4 text-center text-sm text-amber-600 dark:text-amber-400">
              No libraries configured. Ask an admin to add one before importing.
            </p>
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
