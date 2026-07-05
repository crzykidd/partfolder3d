/**
 * ImagesStep — Step 2 of the import wizard.
 *
 * Shows a scrollable strip of session images. Supports set-as-default,
 * remove (✕), and upload of additional images.
 */

import { type ChangeEvent, Suspense, lazy, useCallback, useMemo, useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Box } from 'lucide-react'
import * as api from '@/lib/api'
import { AURORA_BTN_GHOST, AURORA_BTN_PRIMARY } from './styles'

// Lazy-load the 3D viewer so three.js stays out of the wizard's main bundle.
const LazyModelViewer = lazy(() => import('@/components/viewer/ModelViewer'))

// Extensions the in-browser ModelViewer can actually render (mirrors #21).
const RENDERABLE_EXTS = new Set(['.stl', '.obj', '.3mf'])

function fileExt(name: string): string {
  const dot = name.lastIndexOf('.')
  return dot === -1 ? '' : name.slice(dot).toLowerCase()
}

export interface ImagesStepProps {
  session: api.ImportSession
  onNext: () => void
  onPrev: () => void
}

export function ImagesStep({ session, onNext, onPrev }: ImagesStepProps) {
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Staged model files the viewer can render (upload imports only; URL imports
  // have no staged files, so the control simply doesn't appear).
  const renderableFiles = useMemo(
    () => session.files.filter((f) => RENDERABLE_EXTS.has(fileExt(f.original_name))),
    [session.files],
  )

  // Viewer state: which staged model is open (or null), and whether the
  // multi-file picker is showing.
  const [viewerFile, setViewerFile] = useState<{ name: string; ext: string } | null>(null)
  const [pickerOpen, setPickerOpen] = useState(false)

  const captureMutation = useMutation({
    mutationFn: (blob: Blob) => {
      const file = new File([blob], 'capture.png', { type: 'image/png' })
      return api.uploadSessionImage(session.id, file, 'captured')
    },
    onSuccess: (updated) => {
      queryClient.setQueryData(['import-session', session.id], updated)
      void queryClient.invalidateQueries({ queryKey: ['import-session', session.id] })
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : 'Failed to save captured image.'),
  })

  const handleCapture = useCallback((blob: Blob) => {
    setError(null)
    captureMutation.mutate(blob)
  }, [captureMutation])

  const openViewerFor = useCallback((name: string) => {
    setViewerFile({ name, ext: fileExt(name) })
    setPickerOpen(false)
  }, [])

  const handleTryRender = useCallback(() => {
    setError(null)
    if (renderableFiles.length === 1) {
      openViewerFor(renderableFiles[0].original_name)
    } else {
      setPickerOpen((v) => !v)
    }
  }, [renderableFiles, openViewerFor])

  const setDefaultMutation = useMutation({
    mutationFn: (path: string) =>
      api.patchImportSession(session.id, { default_image_path: path }),
    onSuccess: (updated) =>
      queryClient.setQueryData(['import-session', session.id], updated),
    onError: (err) =>
      setError(err instanceof Error ? err.message : 'Failed to set default image.'),
  })

  const removeImageMutation = useMutation({
    mutationFn: (imageId: number) =>
      api.deleteImportSessionImage(session.id, imageId),
    onSuccess: (updated) => {
      queryClient.setQueryData(['import-session', session.id], updated)
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : 'Failed to remove image.'),
  })

  const uploadMutation = useMutation({
    mutationFn: (files: File[]) => api.uploadSessionFiles(session.id, files),
    onSuccess: (updated) => {
      queryClient.setQueryData(['import-session', session.id], updated)
      void queryClient.invalidateQueries({ queryKey: ['import-session', session.id] })
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : 'Failed to upload images.'),
  })

  const handleUpload = (e: ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files) return
    const files = Array.from(e.target.files)
    uploadMutation.mutate(files)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <p style={{ fontSize: 13, color: 'var(--aurora-muted)', margin: 0 }}>
        {session.images.length === 0
          ? 'No images yet. You can upload some below.'
          : `${session.images.length} image(s). Click "Set as default" to choose the cover image.`}
      </p>

      {/* Horizontal scrollable strip */}
      {session.images.length > 0 && (
        <div style={{ display: 'flex', gap: 12, overflowX: 'auto', paddingBottom: 8 }}>
          {[...session.images]
            .sort((a, b) => a.order - b.order)
            .map((img) => (
              <div key={img.id} style={{ position: 'relative', flexShrink: 0 }}>
                {/* Remove (✕) button — top-right corner */}
                <button
                  type="button"
                  aria-label="Remove image"
                  disabled={removeImageMutation.isPending}
                  onClick={() => { setError(null); removeImageMutation.mutate(img.id) }}
                  style={{
                    position: 'absolute',
                    top: 4,
                    right: 4,
                    zIndex: 10,
                    width: 22,
                    height: 22,
                    borderRadius: '50%',
                    background: 'rgba(0,0,0,0.55)',
                    border: 'none',
                    color: '#fff',
                    fontSize: 12,
                    lineHeight: 1,
                    cursor: removeImageMutation.isPending ? 'not-allowed' : 'pointer',
                    opacity: removeImageMutation.isPending ? 0.5 : 1,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    transition: 'background 0.15s',
                    padding: 0,
                  }}
                  onMouseEnter={(e) => {
                    if (!removeImageMutation.isPending)
                      (e.currentTarget as HTMLButtonElement).style.background = 'rgba(220,38,38,0.85)'
                  }}
                  onMouseLeave={(e) => {
                    (e.currentTarget as HTMLButtonElement).style.background = 'rgba(0,0,0,0.55)'
                  }}
                >
                  ✕
                </button>

                <div
                  style={{
                    width: 160,
                    height: 160,
                    overflow: 'hidden',
                    borderRadius: 10,
                    border: img.is_default
                      ? '2px solid var(--aurora-accent)'
                      : '2px solid var(--aurora-glass-border)',
                    boxShadow: img.is_default ? 'var(--aurora-glow)' : 'none',
                    transition: 'border-color 0.15s, box-shadow 0.15s',
                  }}
                >
                  {img.is_url || img.source === 'capture' || img.source === 'upload' ? (
                    <img
                      src={
                        img.is_url
                          ? img.path
                          : api.sessionFileUrl(session.id, img.path.split('/').pop() ?? img.path)
                      }
                      alt=""
                      style={{ height: '100%', width: '100%', objectFit: 'cover', display: 'block' }}
                      onError={(e) => {
                        ;(e.currentTarget as HTMLImageElement).style.display = 'none'
                      }}
                    />
                  ) : (
                    <div
                      style={{
                        height: '100%',
                        width: '100%',
                        background: 'var(--aurora-glass)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        padding: 12,
                        boxSizing: 'border-box',
                      }}
                    >
                      <span
                        style={{
                          fontSize: 10,
                          color: 'var(--aurora-muted)',
                          textAlign: 'center',
                          lineHeight: 1.4,
                          wordBreak: 'break-all',
                          fontFamily: 'monospace',
                        }}
                      >
                        {img.path.split('/').pop()}
                        <br />
                        <span style={{ fontSize: 9, color: 'var(--aurora-muted)', fontFamily: 'sans-serif' }}>
                          (preview after commit)
                        </span>
                      </span>
                    </div>
                  )}
                </div>
                {img.is_default && (
                  <span
                    style={{
                      position: 'absolute',
                      top: 6,
                      left: 6,
                      background: 'var(--aurora-accent)',
                      color: 'var(--aurora-accent-fg)',
                      borderRadius: 20,
                      fontSize: 9,
                      fontWeight: 700,
                      padding: '2px 8px',
                      boxShadow: '0 0 8px var(--aurora-accent-glow)',
                      letterSpacing: '0.05em',
                      textTransform: 'uppercase',
                    }}
                  >
                    Default
                  </span>
                )}
                {!img.is_default && (
                  <button
                    type="button"
                    disabled={setDefaultMutation.isPending}
                    onClick={() => { setError(null); setDefaultMutation.mutate(img.path) }}
                    style={{
                      marginTop: 6,
                      width: '100%',
                      background: 'none',
                      border: 'none',
                      fontSize: 11,
                      color: 'var(--aurora-muted)',
                      cursor: 'pointer',
                      textDecoration: 'underline',
                      opacity: setDefaultMutation.isPending ? 0.5 : 1,
                      transition: 'color 0.15s',
                      padding: 0,
                    }}
                    onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.color = 'var(--aurora-accent)' }}
                    onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.color = 'var(--aurora-muted)' }}
                  >
                    Set as default
                  </button>
                )}
              </div>
            ))}
        </div>
      )}

      {/* Try to render a staged model file → capture a viewport image (#26).
          Shown only when the session has ≥1 browser-renderable staged model. */}
      {renderableFiles.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'flex-start' }}>
          <button
            type="button"
            onClick={handleTryRender}
            aria-expanded={renderableFiles.length > 1 ? pickerOpen : undefined}
            style={{ ...AURORA_BTN_GHOST, display: 'flex', alignItems: 'center', gap: 6 }}
            onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass-hover)' }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass)' }}
          >
            <Box size={14} />
            Try to render file
          </button>
          <p style={{ fontSize: 11, color: 'var(--aurora-muted)', margin: 0 }}>
            Open a staged model in the 3D viewer and capture the current view as an image.
          </p>

          {/* Model picker — shown when multiple renderable files exist */}
          {pickerOpen && renderableFiles.length > 1 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4, width: '100%' }}>
              {renderableFiles.map((f) => (
                <button
                  key={f.id}
                  type="button"
                  onClick={() => openViewerFor(f.original_name)}
                  style={{
                    ...AURORA_BTN_GHOST,
                    textAlign: 'left',
                    fontFamily: 'monospace',
                    fontSize: 12,
                    padding: '6px 12px',
                  }}
                  onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass-hover)' }}
                  onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass)' }}
                >
                  {f.original_name}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Lazy-loaded 3D viewer modal — capture uploads via uploadSessionImage */}
      {viewerFile && (
        <Suspense fallback={null}>
          <LazyModelViewer
            fileUrl={api.sessionFileUrl(session.id, viewerFile.name)}
            ext={viewerFile.ext}
            onClose={() => setViewerFile(null)}
            isOwner
            onCapture={handleCapture}
            isCapturing={captureMutation.isPending}
          />
        </Suspense>
      )}

      {/* Upload images */}
      <div>
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={uploadMutation.isPending}
          style={{
            ...AURORA_BTN_GHOST,
            opacity: uploadMutation.isPending ? 0.5 : 1,
            cursor: uploadMutation.isPending ? 'not-allowed' : 'pointer',
          }}
          onMouseEnter={(e) => { if (!uploadMutation.isPending) (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass-hover)' }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass)' }}
        >
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" style={{ width: 14, height: 14 }}>
            <path d="M9.25 13.25a.75.75 0 0 0 1.5 0V4.636l2.955 3.129a.75.75 0 0 0 1.09-1.03l-4.25-4.5a.75.75 0 0 0-1.09 0l-4.25 4.5a.75.75 0 1 0 1.09 1.03L9.25 4.636v8.614Z" />
            <path d="M3.5 12.75a.75.75 0 0 0-1.5 0v2.5A2.75 2.75 0 0 0 4.75 18h10.5A2.75 2.75 0 0 0 18 15.25v-2.5a.75.75 0 0 0-1.5 0v2.5c0 .69-.56 1.25-1.25 1.25H4.75c-.69 0-1.25-.56-1.25-1.25v-2.5Z" />
          </svg>
          {uploadMutation.isPending ? 'Uploading…' : 'Upload Images'}
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          multiple
          className="sr-only"
          onChange={handleUpload}
        />
      </div>

      {error && (
        <p style={{ fontSize: 13, color: 'var(--aurora-danger)', margin: 0 }}>{error}</p>
      )}

      <div style={{ display: 'flex', justifyContent: 'space-between', paddingTop: 4 }}>
        <button
          type="button"
          onClick={onPrev}
          style={AURORA_BTN_GHOST}
          onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass-hover)' }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass)' }}
        >
          ← Back
        </button>
        <button
          type="button"
          onClick={onNext}
          style={AURORA_BTN_PRIMARY}
          onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.opacity = '0.85' }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.opacity = '1' }}
        >
          Next →
        </button>
      </div>
    </div>
  )
}
