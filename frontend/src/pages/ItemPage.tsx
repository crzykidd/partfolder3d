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

import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Trash2, Upload } from 'lucide-react'

import * as api from '@/lib/api'
import { useAuth } from '@/context/AuthContext'

import { AURORA_BTN_GHOST, AURORA_BTN_PRIMARY } from './item/styles'
import { AuroraSection } from './item/AuroraSection'
import { ImageCarousel } from './item/ImageCarousel'
import { ItemMetadata } from './item/ItemMetadata'
import { PathDisplay } from './item/PathDisplay'
import { DownloadsSection } from './item/DownloadsPanel'
import { ObjectBreakdownSection } from './item/ObjectBreakdown'
import { PrintHistorySection } from './item/PrintHistory'
import { ShareSection } from './item/ShareControls'
import { MoveToLibrary } from './item/MoveToLibrary'

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

  // Single source of the item's jobs (active queued/running + recent failed) —
  // drives BOTH the ObjectBreakdown status and the file-list auto-refresh.
  // Poll every 3 s only while there's active work.
  const { data: itemJobs } = useQuery({
    queryKey: ['item-jobs', key],
    queryFn: () => api.listItemJobs(key!),
    enabled: !!key,
    refetchInterval: (query) =>
      query.state.data?.some((j) => j.status === 'queued' || j.status === 'running')
        ? 3000
        : false,
  })
  // Active (in-progress) jobs only — a failed job must not keep this non-empty
  // forever (that would break the "refresh when work finishes" effect below).
  const activeJobs = itemJobs?.filter(
    (j) => j.status === 'queued' || j.status === 'running',
  )

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

  // ---- File management mutations (issues #18/#19) ----
  const [deletingFileId, setDeletingFileId] = useState<number | null>(null)
  const [renamingFileId, setRenamingFileId] = useState<number | null>(null)
  const [uploadFileError, setUploadFileError] = useState<string | null>(null)

  const deleteFileMutation = useMutation({
    mutationFn: async (fileId: number) => {
      setDeletingFileId(fileId)
      await api.deleteItemFile(key!, fileId)
    },
    onSuccess: () => {
      setDeletingFileId(null)
      void queryClient.invalidateQueries({ queryKey: ['item', key] })
    },
    onError: () => {
      setDeletingFileId(null)
    },
  })

  const renameFileMutation = useMutation({
    mutationFn: ({ fileId, name }: { fileId: number; name: string }) => {
      setRenamingFileId(fileId)
      return api.renameItemFile(key!, fileId, name)
    },
    onSettled: () => {
      setRenamingFileId(null)
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['item', key] })
    },
  })

  const uploadFileMutation = useMutation({
    mutationFn: (file: File) => api.uploadItemFile(key!, file),
    onSuccess: () => {
      setUploadFileError(null)
      void queryClient.invalidateQueries({ queryKey: ['item', key] })
    },
    onError: (e) => {
      setUploadFileError(e instanceof Error ? e.message : 'Upload failed.')
    },
  })

  const rescanMutation = useMutation({
    mutationFn: () => api.rescanItem(key!),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['item', key] })
      void queryClient.invalidateQueries({ queryKey: ['item-jobs', key] })
    },
  })

  const prevActiveJobCount = useRef(0)
  useEffect(() => {
    const current = activeJobs?.length ?? 0
    if (prevActiveJobCount.current > 0 && current === 0) {
      void queryClient.invalidateQueries({ queryKey: ['item', key] })
    }
    prevActiveJobCount.current = current
  }, [activeJobs, key, queryClient])

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
        maxWidth: 'min(1280px, 94vw)',
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
            <MoveToLibrary itemKey={item.key} currentLibraryId={item.library_id} />
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

      {/* Hero: images + metadata — 2 columns on wide, stacks on narrow */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16 }}>
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
        <ItemMetadata
          item={item}
          itemKey={item.key}
          isOwnerOrAdmin={isOwnerOrAdmin}
        />
      </div>

      {/* Location */}
      <AuroraSection title="Location">
        <PathDisplay dirPath={item.dir_path} itemKey={item.key} libraryId={item.library_id} />
      </AuroraSection>

      {/* Downloads — file tree with type-aware affordances and inline 3MF panels */}
      <AuroraSection
        title="Files &amp; Downloads"
        collapsible
        storageKey="partfolder3d-files-collapsed"
        headerRight={`${item.files.length} file${item.files.length === 1 ? '' : 's'}`}
      >
        <DownloadsSection
          itemKey={item.key}
          files={item.files}
          isOwner={isOwnerOrAdmin}
          onDeleteFile={(fileId) => deleteFileMutation.mutate(fileId)}
          onRenameFile={(fileId, name) => renameFileMutation.mutate({ fileId, name })}
          onUploadFile={(file) => uploadFileMutation.mutate(file)}
          onRescan={() => rescanMutation.mutate()}
          isDeletingFileId={deletingFileId}
          isRenamingFileId={renamingFileId}
          isUploadingFile={uploadFileMutation.isPending}
          isRescanning={rescanMutation.isPending}
          uploadFileError={uploadFileError}
        />
      </AuroraSection>

      {/* Object breakdown (Phase 16) — show when item has model files */}
      {item.files.some((f) => f.role === 'model') && (
        <AuroraSection title="Object Breakdown">
          <ObjectBreakdownSection item={item} jobs={itemJobs ?? []} />
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
