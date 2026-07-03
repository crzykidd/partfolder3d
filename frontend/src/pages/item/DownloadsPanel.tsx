/**
 * DownloadsPanel — file-tree browser + ZIP download for a catalog item.
 *
 * Renders a recursive folder hierarchy built client-side from `FileOut.path`.
 * Type-aware affordances per file row:
 *  - image → small inline thumbnail
 *  - preview_3d === true → "View in 3D" button (Phase D wired; lazy-loads three.js)
 *  - .3mf → collapsible ThreeMfPanel below the file row
 *
 * Owner affordances (isOwner=true): delete (Trash2 + confirm), rename (Pencil + inline
 * edit), and an upload control below the tree.
 *
 * The "Download all as ZIP" section (with include-print-history toggle and
 * 2-second poll) is kept unchanged below the tree.
 */

import React, { Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, Download, Box, Trash2, Pencil, Upload, RefreshCw } from 'lucide-react'

import * as api from '@/lib/api'
import { mapBundleStatus, shouldContinuePolling, type ZipPollStatus } from '@/lib/catalog-utils'
import { buildFileTree, is3mf, isImagePath, type FileTreeNode, type FileTreeFolder } from '@/lib/file-tree'
import { ThreeMfPanel } from './ThreeMfPanel'
import { AURORA_BTN_GHOST, AURORA_BTN_PRIMARY, formatBytes } from './styles'

// ---------------------------------------------------------------------------
// Lazy-load the 3D viewer so three.js stays out of the entry bundle.
// ---------------------------------------------------------------------------

const LazyModelViewer = React.lazy(
  () => import('@/components/viewer/ModelViewer'),
)

// ---------------------------------------------------------------------------
// Role badge
// ---------------------------------------------------------------------------

const ROLE_BADGE_COLORS: Record<string, { bg: string; color: string }> = {
  model:   { bg: 'rgba(15,164,171,0.12)', color: '#0FA4AB' },
  image:   { bg: 'rgba(139,92,246,0.12)', color: '#A78BFA' },
  project: { bg: 'rgba(245,158,11,0.12)', color: '#D97706' },
  support: { bg: 'rgba(99,102,241,0.12)', color: '#818CF8' },
  history: { bg: 'rgba(16,185,129,0.10)', color: '#10B981' },
}

function RoleBadge({ role }: { role: string }) {
  const c = ROLE_BADGE_COLORS[role] ?? { bg: 'var(--aurora-glass)', color: 'var(--aurora-muted)' }
  return (
    <span
      style={{
        fontSize: 9,
        fontWeight: 700,
        padding: '1px 6px',
        borderRadius: 20,
        background: c.bg,
        color: c.color,
        border: `1px solid ${c.color}33`,
        flexShrink: 0,
        textTransform: 'uppercase',
        letterSpacing: '0.05em',
      }}
    >
      {role}
    </span>
  )
}

// ---------------------------------------------------------------------------
// View-in-3D button
// ---------------------------------------------------------------------------

function ViewIn3DButton({ onView }: { onView?: () => void }) {
  const isStub = onView == null
  return (
    <button
      disabled={isStub}
      title={isStub ? 'In-browser 3D viewer coming in the next update' : 'Open in 3D viewer'}
      onClick={isStub ? undefined : onView}
      style={{
        ...AURORA_BTN_GHOST,
        display: 'flex',
        alignItems: 'center',
        gap: 5,
        opacity: isStub ? 0.45 : 1,
        cursor: isStub ? 'not-allowed' : 'pointer',
        fontSize: 11,
        padding: '4px 10px',
      }}
    >
      <Box size={11} />
      View in 3D
    </button>
  )
}

// ---------------------------------------------------------------------------
// File row — one leaf node in the tree
// ---------------------------------------------------------------------------

interface FileRowProps {
  itemKey: string
  file: api.FileOut
  depth: number
  isLast: boolean
  onOpenViewer: (filePath: string) => void
  isOwner?: boolean
  onDeleteFile?: (fileId: number) => void
  onRenameFile?: (fileId: number, newName: string) => void
  isDeletingId?: number | null
  isRenamingId?: number | null
}

function FileRow({
  itemKey, file, depth, onOpenViewer,
  isOwner, onDeleteFile, onRenameFile, isDeletingId, isRenamingId,
}: FileRowProps) {
  const [threeMfOpen, setThreeMfOpen] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [renaming, setRenaming] = useState(false)
  const [renameValue, setRenameValue] = useState('')
  const renameInputRef = useRef<HTMLInputElement | null>(null)

  const basename = file.path.split('/').pop() ?? file.path
  const isImg = isImagePath(file.path)
  const is3mfFile = is3mf(file.path)
  const hasAnalysis = file.object_analysis != null

  const isThisDeleting = isDeletingId === file.id
  const isThisRenaming = isRenamingId === file.id

  const startRename = () => {
    setRenameValue(basename)
    setRenaming(true)
    // Focus the input on the next tick
    setTimeout(() => renameInputRef.current?.select(), 0)
  }

  const submitRename = () => {
    const trimmed = renameValue.trim()
    if (trimmed && trimmed !== basename && onRenameFile) {
      onRenameFile(file.id, trimmed)
    }
    setRenaming(false)
  }

  const cancelRename = () => {
    setRenaming(false)
    setRenameValue('')
  }

  return (
    <div>
      {/* File row */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '8px 12px',
          paddingLeft: 12 + depth * 20,
          transition: 'background 0.1s',
          opacity: isThisDeleting ? 0.5 : 1,
        }}
        onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.background = 'var(--aurora-glass-hover, rgba(255,255,255,0.04))' }}
        onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.background = '' }}
      >
        {/* Inline thumbnail for image files */}
        {isImg && (
          <img
            src={`/api/items/${itemKey}/files/${file.path}`}
            alt={basename}
            style={{
              width: 32,
              height: 32,
              objectFit: 'cover',
              borderRadius: 5,
              border: '1px solid var(--aurora-glass-border)',
              flexShrink: 0,
            }}
            loading="lazy"
          />
        )}

        {/* Filename + meta */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0, flex: 1 }}>
          {renaming ? (
            <input
              ref={renameInputRef}
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') submitRename()
                if (e.key === 'Escape') cancelRename()
              }}
              onBlur={submitRename}
              autoFocus
              style={{
                fontSize: 12,
                fontFamily: 'monospace',
                background: 'var(--aurora-input-bg, rgba(255,255,255,0.06))',
                border: '1px solid var(--aurora-accent)',
                borderRadius: 5,
                color: 'var(--aurora-text)',
                padding: '2px 6px',
                outline: 'none',
                width: '100%',
              }}
            />
          ) : (
            <span
              style={{
                fontSize: 12,
                fontWeight: 500,
                fontFamily: 'monospace',
                color: 'var(--aurora-text)',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
              title={file.path}
            >
              {isThisRenaming ? '…' : basename}
            </span>
          )}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            <RoleBadge role={file.role} />
            <span style={{ fontSize: 10, color: 'var(--aurora-muted)' }}>{formatBytes(file.size)}</span>
          </div>
        </div>

        {/* Action buttons */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0, flexWrap: 'wrap' }}>
          {/* View in 3D — passes real handler when preview_3d is true */}
          {file.preview_3d && !renaming && (
            <ViewIn3DButton onView={() => onOpenViewer(file.path)} />
          )}

          {/* 3MF expand toggle */}
          {is3mfFile && hasAnalysis && !renaming && (
            <button
              onClick={() => setThreeMfOpen((v) => !v)}
              aria-expanded={threeMfOpen}
              title={threeMfOpen ? 'Collapse 3MF details' : 'Show 3MF details'}
              style={{
                ...AURORA_BTN_GHOST,
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                fontSize: 11,
                padding: '4px 10px',
              }}
            >
              {threeMfOpen ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
              Details
            </button>
          )}

          {/* Download link */}
          {!renaming && (
            <a
              href={api.fileDownloadUrl(itemKey, file.path)}
              download
              style={{
                ...AURORA_BTN_GHOST,
                display: 'flex',
                alignItems: 'center',
                gap: 5,
                textDecoration: 'none',
                fontSize: 11,
                padding: '4px 10px',
              }}
            >
              <Download size={11} />
              Download
            </a>
          )}

          {/* Owner: rename button */}
          {isOwner && !renaming && !confirmDelete && (
            <button
              onClick={startRename}
              title="Rename file"
              disabled={isThisRenaming}
              style={{
                ...AURORA_BTN_GHOST,
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                fontSize: 11,
                padding: '4px 8px',
                opacity: isThisRenaming ? 0.5 : 1,
                cursor: isThisRenaming ? 'not-allowed' : 'pointer',
              }}
            >
              <Pencil size={11} />
            </button>
          )}

          {/* Owner: delete with confirm */}
          {isOwner && !renaming && (
            confirmDelete ? (
              <>
                <span style={{ fontSize: 11, color: 'var(--aurora-muted)' }}>Delete?</span>
                <button
                  onClick={() => { onDeleteFile?.(file.id); setConfirmDelete(false) }}
                  disabled={isThisDeleting}
                  style={{
                    ...AURORA_BTN_GHOST,
                    fontSize: 11,
                    padding: '4px 10px',
                    color: 'var(--aurora-danger)',
                    borderColor: 'var(--aurora-danger)',
                    opacity: isThisDeleting ? 0.5 : 1,
                    cursor: isThisDeleting ? 'not-allowed' : 'pointer',
                  }}
                >
                  {isThisDeleting ? '…' : 'Confirm'}
                </button>
                <button
                  onClick={() => setConfirmDelete(false)}
                  style={{ ...AURORA_BTN_GHOST, fontSize: 11, padding: '4px 8px', cursor: 'pointer' }}
                >
                  Cancel
                </button>
              </>
            ) : (
              <button
                onClick={() => setConfirmDelete(true)}
                title="Delete file"
                disabled={isThisDeleting}
                style={{
                  ...AURORA_BTN_GHOST,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                  fontSize: 11,
                  padding: '4px 8px',
                  color: 'var(--aurora-danger)',
                  opacity: isThisDeleting ? 0.5 : 1,
                  cursor: isThisDeleting ? 'not-allowed' : 'pointer',
                }}
              >
                <Trash2 size={11} />
              </button>
            )
          )}
        </div>
      </div>

      {/* 3MF collapsible panel — inline below the file row */}
      {is3mfFile && hasAnalysis && threeMfOpen && (
        <div style={{ padding: '0 12px 10px', paddingLeft: 12 + depth * 20 }}>
          <ThreeMfPanel
            fileName={basename}
            analysis={file.object_analysis!}
            itemKey={itemKey}
            defaultExpanded
          />
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Folder node — collapsible folder with children
// ---------------------------------------------------------------------------

interface FolderNodeProps {
  folder: FileTreeFolder
  itemKey: string
  depth: number
  defaultExpanded?: boolean
  onOpenViewer: (filePath: string) => void
  isOwner?: boolean
  onDeleteFile?: (fileId: number) => void
  onRenameFile?: (fileId: number, newName: string) => void
  isDeletingId?: number | null
  isRenamingId?: number | null
}

function FolderNode({
  folder, itemKey, depth, defaultExpanded = true, onOpenViewer,
  isOwner, onDeleteFile, onRenameFile, isDeletingId, isRenamingId,
}: FolderNodeProps) {
  const [open, setOpen] = useState(defaultExpanded)

  return (
    <div>
      {/* Folder header row */}
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 7,
          width: '100%',
          padding: '7px 12px',
          paddingLeft: 12 + depth * 20,
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          textAlign: 'left',
          color: 'var(--aurora-text-dim)',
          transition: 'background 0.1s',
        }}
        onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass-hover, rgba(255,255,255,0.04))' }}
        onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = '' }}
      >
        <span style={{ color: 'var(--aurora-muted)' }}>
          {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        </span>
        <span style={{ fontSize: 12, fontWeight: 600, fontFamily: 'monospace' }}>
          {folder.name}/
        </span>
        <span style={{ fontSize: 10, color: 'var(--aurora-muted)', marginLeft: 2 }}>
          {folder.children.length} item{folder.children.length !== 1 ? 's' : ''}
        </span>
      </button>

      {/* Children */}
      {open && (
        <div style={{ borderLeft: '1px solid var(--aurora-divider)', marginLeft: 12 + depth * 20 + 6 }}>
          <TreeNodes
            nodes={folder.children}
            itemKey={itemKey}
            depth={depth + 1}
            onOpenViewer={onOpenViewer}
            isOwner={isOwner}
            onDeleteFile={onDeleteFile}
            onRenameFile={onRenameFile}
            isDeletingId={isDeletingId}
            isRenamingId={isRenamingId}
          />
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// TreeNodes — renders a list of FileTreeNode[]
// ---------------------------------------------------------------------------

interface TreeNodesProps {
  nodes: FileTreeNode[]
  itemKey: string
  depth: number
  onOpenViewer: (filePath: string) => void
  isOwner?: boolean
  onDeleteFile?: (fileId: number) => void
  onRenameFile?: (fileId: number, newName: string) => void
  isDeletingId?: number | null
  isRenamingId?: number | null
}

function TreeNodes({
  nodes, itemKey, depth, onOpenViewer,
  isOwner, onDeleteFile, onRenameFile, isDeletingId, isRenamingId,
}: TreeNodesProps) {
  return (
    <>
      {nodes.map((node, idx) =>
        node.type === 'folder' ? (
          <FolderNode
            key={node.name}
            folder={node}
            itemKey={itemKey}
            depth={depth}
            defaultExpanded={depth === 0}
            onOpenViewer={onOpenViewer}
            isOwner={isOwner}
            onDeleteFile={onDeleteFile}
            onRenameFile={onRenameFile}
            isDeletingId={isDeletingId}
            isRenamingId={isRenamingId}
          />
        ) : (
          <div
            key={node.file.id}
            style={{ borderTop: idx > 0 ? '1px solid var(--aurora-divider)' : 'none' }}
          >
            <FileRow
              itemKey={itemKey}
              file={node.file}
              depth={depth}
              isLast={idx === nodes.length - 1}
              onOpenViewer={onOpenViewer}
              isOwner={isOwner}
              onDeleteFile={onDeleteFile}
              onRenameFile={onRenameFile}
              isDeletingId={isDeletingId}
              isRenamingId={isRenamingId}
            />
          </div>
        ),
      )}
    </>
  )
}

// ---------------------------------------------------------------------------
// Downloads section (public API)
// ---------------------------------------------------------------------------

export interface DownloadsSectionProps {
  itemKey: string
  files: api.FileOut[]
  isOwner?: boolean
  onDeleteFile?: (fileId: number) => void
  onRenameFile?: (fileId: number, newName: string) => void
  onUploadFile?: (file: File) => void
  onRescan?: () => void
  isDeletingFileId?: number | null
  isRenamingFileId?: number | null
  isUploadingFile?: boolean
  isRescanning?: boolean
  uploadFileError?: string | null
}

export function DownloadsSection({
  itemKey, files,
  isOwner, onDeleteFile, onRenameFile, onUploadFile, onRescan,
  isDeletingFileId, isRenamingFileId, isUploadingFile, isRescanning, uploadFileError,
}: DownloadsSectionProps) {
  const queryClient = useQueryClient()
  const [bundleId, setBundleId] = useState<string | null>(null)
  const [zipStatus, setZipStatus] = useState<ZipPollStatus>('idle')
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [includeHistory, setIncludeHistory] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const uploadFileInputRef = useRef<HTMLInputElement | null>(null)

  // Viewer state: {filePath, ext} of the currently-open file, or null
  const [viewerFile, setViewerFile] = useState<{ filePath: string; ext: string } | null>(null)

  // Capture mutation — uploads the viewer blob as a new item image
  const captureMutation = useMutation({
    mutationFn: (blob: Blob) => {
      const file = new File([blob], 'capture.png', { type: 'image/png' })
      return api.uploadItemImage(itemKey, file, 'captured')
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['item', itemKey] })
    },
  })

  const handleCapture = useCallback((blob: Blob) => {
    captureMutation.mutate(blob)
  }, [captureMutation])

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

  const handleOpenViewer = useCallback((filePath: string) => {
    const ext = filePath.slice(filePath.lastIndexOf('.')).toLowerCase()
    setViewerFile({ filePath, ext })
  }, [])

  const handleCloseViewer = useCallback(() => setViewerFile(null), [])

  const zipLabel: Record<ZipPollStatus, string> = {
    idle:     'Download all as ZIP',
    queued:   'Queued…',
    building: 'Building ZIP…',
    ready:    'Download ZIP',
    failed:   'ZIP failed — retry?',
    expired:  'ZIP expired — retry?',
  }

  const tree = buildFileTree(files)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* Lazy-loaded 3D viewer modal */}
      {viewerFile && (
        <Suspense fallback={null}>
          <LazyModelViewer
            fileUrl={`/api/items/${itemKey}/files/${viewerFile.filePath}`}
            ext={viewerFile.ext}
            onClose={handleCloseViewer}
            isOwner={isOwner}
            onCapture={handleCapture}
            isCapturing={captureMutation.isPending}
          />
        </Suspense>
      )}

      {/* File tree */}
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
            overflowX: 'hidden',
            overflowY: 'auto',
            maxHeight: 420,
          }}
        >
          <TreeNodes
            nodes={tree}
            itemKey={itemKey}
            depth={0}
            onOpenViewer={handleOpenViewer}
            isOwner={isOwner}
            onDeleteFile={onDeleteFile}
            onRenameFile={onRenameFile}
            isDeletingId={isDeletingFileId}
            isRenamingId={isRenamingFileId}
          />
        </div>
      )}

      {/* File actions (owners only): Upload + Rescan disk on one row */}
      {isOwner && (onUploadFile || onRescan) && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'flex-start' }}>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {onUploadFile && (
              <button
                onClick={() => uploadFileInputRef.current?.click()}
                disabled={isUploadingFile}
                style={{
                  ...AURORA_BTN_GHOST,
                  fontSize: 12,
                  padding: '6px 14px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  opacity: isUploadingFile ? 0.5 : 1,
                  cursor: isUploadingFile ? 'not-allowed' : 'pointer',
                }}
              >
                <Upload size={13} />
                {isUploadingFile ? 'Uploading…' : 'Upload file'}
              </button>
            )}
            {onRescan && (
              <button
                onClick={onRescan}
                disabled={isRescanning}
                title="Re-scan this item's folder on disk and apply any file/metadata changes"
                style={{
                  ...AURORA_BTN_GHOST,
                  fontSize: 12,
                  padding: '6px 14px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  opacity: isRescanning ? 0.5 : 1,
                  cursor: isRescanning ? 'not-allowed' : 'pointer',
                }}
              >
                <RefreshCw size={13} />
                {isRescanning ? 'Rescanning…' : 'Rescan disk'}
              </button>
            )}
          </div>
          {onUploadFile && (
            <input
              ref={uploadFileInputRef}
              type="file"
              style={{ display: 'none' }}
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) onUploadFile(f)
                e.target.value = ''
              }}
            />
          )}
          {uploadFileError && (
            <span style={{ fontSize: 11, color: 'var(--aurora-danger)' }}>{uploadFileError}</span>
          )}
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
