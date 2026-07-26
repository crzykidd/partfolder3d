import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Copy, Download, ExternalLink, FileCode2, Maximize2, Pencil, X } from 'lucide-react'

import * as api from '@/lib/api'
import { safeHref } from '@/lib/utils'
import { playgroundUrl } from '@/lib/openscadPlayground'
import { addConfirmedTag, removeConfirmedTag } from '@/lib/import-utils'

import { AURORA_BTN_GHOST, AURORA_BTN_PRIMARY, AURORA_CARD, AURORA_INPUT, formatBytes, formatDate } from './styles'

// ---------------------------------------------------------------------------
// Item metadata card (right column of hero grid)
// Includes: title, creator, tags, source/license, modified badge + override,
// description, Show SCAD (read-only source viewer), and timestamps.
// ---------------------------------------------------------------------------

/**
 * Size cap for inline .scad preview — a smaller cap than the 3D-viewer's
 * BROWSER_PREVIEW_MAX_MB since this is a plain-text read, not a mesh render.
 * Above this, the modal skips the fetch and offers Download only.
 */
const SCAD_PREVIEW_MAX_MB = 5

export interface ItemMetadataProps {
  item: api.ItemDetail
  itemKey: string
  isOwnerOrAdmin: boolean
}

export function ItemMetadata({ item, itemKey, isOwnerOrAdmin }: ItemMetadataProps) {
  const queryClient = useQueryClient()
  const [descExpanded, setDescExpanded] = useState(false)
  // A long description gets a capped, scrollable box + an "Expand" modal.
  const descLong = (item.description?.length ?? 0) > 280

  // "Show SCAD" — an OpenSCAD design-source file (role='source'; fallback to
  // extension in case an older row predates the source role migration).
  const scadFile = item.files.find(
    (f) => f.role === 'source' || f.path.toLowerCase().endsWith('.scad'),
  )
  const [scadModalOpen, setScadModalOpen] = useState(false)

  // Phase 15: manual modified-override mutation
  const overrideMutation = useMutation({
    mutationFn: (override: 'modified' | 'original' | null) =>
      api.patchModifiedOverride(itemKey, override),
    onSuccess: (updatedItem) => {
      queryClient.setQueryData(['item', itemKey], updatedItem)
    },
  })

  // -------------------------------------------------------------------------
  // Issue #47 — inline edit for description + tags.
  // -------------------------------------------------------------------------
  const [editingMeta, setEditingMeta] = useState(false)
  const [descDraft, setDescDraft] = useState(item.description ?? '')
  const [tagsDraft, setTagsDraft] = useState<string[]>(item.tags.map((t) => t.name))
  const [tagInput, setTagInput] = useState('')

  const startEditingMeta = () => {
    setDescDraft(item.description ?? '')
    setTagsDraft(item.tags.map((t) => t.name))
    setTagInput('')
    setEditingMeta(true)
  }
  const cancelEditingMeta = () => {
    setEditingMeta(false)
    setTagInput('')
  }

  // Popular existing tags for quick-add while editing — a distinct query key
  // from the catalog's ['tags','cloud'] (different params); saving invalidates
  // the whole ['tags'] prefix so both stay fresh.
  const popularTagsQuery = useQuery({
    queryKey: ['tags', 'popular', 'item-edit'],
    queryFn: () => api.listTags({ in_use_only: true, per_page: 24 }),
    enabled: editingMeta,
    staleTime: 5 * 60 * 1000,
  })
  const popularTags = (popularTagsQuery.data?.tags ?? []).filter(
    (t) => !tagsDraft.includes(t.name),
  )

  const addTagFromInput = () => {
    const next = addConfirmedTag(tagsDraft, tagInput)
    if (next !== tagsDraft) {
      setTagsDraft(next)
      setTagInput('')
    }
  }

  const updateMetaMutation = useMutation({
    // NOTE: ItemUpdate treats `description: null` as "leave unchanged" (same
    // convention as title/source_url/license on this endpoint), so an emptied
    // textarea must send `""`, not `null`, to actually clear it.
    mutationFn: () =>
      api.updateItem(itemKey, { description: descDraft, tags: tagsDraft }),
    onSuccess: (updatedItem) => {
      queryClient.setQueryData(['item', itemKey], updatedItem)
      void queryClient.invalidateQueries({ queryKey: ['tags'] })
      setEditingMeta(false)
      setTagInput('')
    },
  })

  return (
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

      {/* Issue #47 — entry point for the description/tags editor. Always shown
          (even with no tags/description yet) so an owner can add them. */}
      {isOwnerOrAdmin && !editingMeta && (
        <div>
          <button
            type="button"
            onClick={startEditingMeta}
            style={{
              ...AURORA_BTN_GHOST,
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              fontSize: 11,
              padding: '4px 10px',
            }}
            onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass-hover)' }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass)' }}
          >
            <Pencil size={11} />
            Edit description &amp; tags
          </button>
        </div>
      )}

      {/* Tags — editable inline (issue #47) when isOwnerOrAdmin */}
      {editingMeta ? (
        <TagEditor
          tags={tagsDraft}
          input={tagInput}
          onInputChange={setTagInput}
          onAdd={addTagFromInput}
          onRemove={(name) => setTagsDraft((c) => removeConfirmedTag(c, name))}
          popularTags={popularTags}
          onQuickAdd={(name) => setTagsDraft((c) => addConfirmedTag(c, name))}
        />
      ) : (
        item.tags.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {item.tags.map((tag) => (
              <span key={tag.id} style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                <Link
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
                {tag.status === 'pending' && (
                  <span
                    title="Awaiting admin approval"
                    style={{
                      fontSize: 9,
                      fontWeight: 700,
                      textTransform: 'uppercase',
                      letterSpacing: '0.05em',
                      color: '#D97706',
                      background: 'rgba(217,119,6,0.10)',
                      border: '1px solid rgba(217,119,6,0.30)',
                      borderRadius: 10,
                      padding: '1px 6px',
                    }}
                  >
                    pending
                  </span>
                )}
              </span>
            ))}
          </div>
        )
      )}

      {/* Source + license */}
      {(item.source_url || item.license) && (
        <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', columnGap: 10, rowGap: 6, alignItems: 'baseline', fontSize: 12 }}>
          {item.source_url && (
            <>
              <span style={{ color: 'var(--aurora-muted)', fontWeight: 600, fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.06em', whiteSpace: 'nowrap' }}>Source</span>
              <a
                href={safeHref(item.source_url)}
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

      {/* Show SCAD — only when the item has an OpenSCAD design-source file */}
      {scadFile && (
        <div>
          <button
            onClick={() => setScadModalOpen(true)}
            style={{
              ...AURORA_BTN_GHOST,
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              fontSize: 12,
              padding: '5px 12px',
            }}
          >
            <FileCode2 size={13} />
            Show SCAD
          </button>
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

      {/* Description — capped + scrollable when long, with an Expand modal.
          Issue #47: replaced by an editable textarea + Save/Cancel while editingMeta. */}
      {editingMeta ? (
        <div>
          <textarea
            value={descDraft}
            onChange={(e) => setDescDraft(e.target.value)}
            placeholder="Add a description…"
            rows={5}
            style={{ ...AURORA_INPUT, resize: 'vertical', fontFamily: 'inherit', lineHeight: 1.5 }}
            onFocus={(e) => { e.currentTarget.style.borderColor = 'var(--aurora-accent)' }}
            onBlur={(e) => { e.currentTarget.style.borderColor = 'var(--aurora-input-border)' }}
          />
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8 }}>
            <button
              type="button"
              disabled={updateMetaMutation.isPending}
              onClick={() => updateMetaMutation.mutate()}
              style={{
                ...AURORA_BTN_PRIMARY,
                opacity: updateMetaMutation.isPending ? 0.6 : 1,
                cursor: updateMetaMutation.isPending ? 'not-allowed' : 'pointer',
              }}
            >
              {updateMetaMutation.isPending ? 'Saving…' : 'Save'}
            </button>
            <button
              type="button"
              disabled={updateMetaMutation.isPending}
              onClick={cancelEditingMeta}
              style={{
                ...AURORA_BTN_GHOST,
                opacity: updateMetaMutation.isPending ? 0.6 : 1,
                cursor: updateMetaMutation.isPending ? 'not-allowed' : 'pointer',
              }}
            >
              Cancel
            </button>
          </div>
          {updateMetaMutation.isError && (
            <p style={{ fontSize: 12, color: 'var(--aurora-danger)', margin: '8px 0 0' }}>
              Failed to save changes. Please try again.
            </p>
          )}
        </div>
      ) : (
        item.description && (
          <div>
            <div
              style={{
                fontSize: 12,
                color: 'var(--aurora-text-dim)',
                lineHeight: 1.6,
                whiteSpace: 'pre-wrap',
                maxHeight: descLong ? 220 : undefined,
                overflowY: descLong ? 'auto' : undefined,
                paddingRight: descLong ? 6 : undefined,
              }}
            >
              {item.description}
            </div>
            {descLong && (
              <button
                onClick={() => setDescExpanded(true)}
                style={{
                  marginTop: 8,
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 4,
                  background: 'transparent',
                  border: 'none',
                  cursor: 'pointer',
                  color: 'var(--aurora-accent)',
                  fontSize: 11,
                  fontWeight: 600,
                  padding: 0,
                }}
              >
                <Maximize2 size={11} />
                Expand
              </button>
            )}
          </div>
        )
      )}

      {/* Timestamps */}
      <div style={{ fontSize: 11, color: 'var(--aurora-muted)', marginTop: 'auto' }}>
        Added {formatDate(item.created_at)}
        {item.updated_at !== item.created_at && (
          <> · Updated {formatDate(item.updated_at)}</>
        )}
      </div>

      {/* Expanded description modal — portaled so the card's backdrop-filter can't trap it */}
      {descExpanded && item.description &&
        createPortal(
          <div
            onClick={() => setDescExpanded(false)}
            style={{
              position: 'fixed',
              inset: 0,
              zIndex: 9999,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: 'rgba(5,13,28,0.80)',
              backdropFilter: 'blur(10px)',
              WebkitBackdropFilter: 'blur(10px)',
              padding: 16,
            }}
          >
            <div
              onClick={(e) => e.stopPropagation()}
              style={{
                background: 'var(--aurora-card)',
                border: '1px solid var(--aurora-card-border)',
                borderRadius: 14,
                width: '100%',
                maxWidth: 720,
                maxHeight: '85vh',
                display: 'flex',
                flexDirection: 'column',
                color: 'var(--aurora-text)',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 12,
                  padding: '16px 20px',
                  borderBottom: '1px solid var(--aurora-divider)',
                }}
              >
                <h2 style={{ margin: 0, fontSize: 15, fontWeight: 700 }}>{item.title}</h2>
                <button
                  onClick={() => setDescExpanded(false)}
                  aria-label="Close description"
                  style={{
                    background: 'transparent',
                    border: 'none',
                    cursor: 'pointer',
                    color: 'var(--aurora-muted)',
                    padding: 4,
                    display: 'flex',
                    flexShrink: 0,
                  }}
                >
                  <X size={18} />
                </button>
              </div>
              <div
                style={{
                  padding: '16px 20px',
                  overflowY: 'auto',
                  fontSize: 13,
                  lineHeight: 1.65,
                  color: 'var(--aurora-text-dim)',
                  whiteSpace: 'pre-wrap',
                }}
              >
                {item.description}
              </div>
            </div>
          </div>,
          document.body,
        )}

      {/* Show SCAD modal — read-only source viewer (v1: no editing, no server render) */}
      {scadFile && (
        <ShowScadModal
          open={scadModalOpen}
          onClose={() => setScadModalOpen(false)}
          itemKey={itemKey}
          file={scadFile}
        />
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tag editor (issue #47) — chips with remove + an add-tag input + a
// popular-tags quick-add row. Deliberately simpler than the import wizard's
// TagsStep (no AI suggestions, no pending/reconcile split, no autocomplete
// dropdown — none of that applies to editing an already-committed item); it
// reuses the wizard's pure add/remove helpers (`addConfirmedTag` /
// `removeConfirmedTag` from lib/import-utils) so the chip-array semantics
// stay identical rather than being reimplemented.
// ---------------------------------------------------------------------------

interface TagEditorProps {
  tags: string[]
  input: string
  onInputChange: (value: string) => void
  onAdd: () => void
  onRemove: (name: string) => void
  popularTags: api.TagSummary[]
  onQuickAdd: (name: string) => void
}

function TagEditor({
  tags,
  input,
  onInputChange,
  onAdd,
  onRemove,
  popularTags,
  onQuickAdd,
}: TagEditorProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
        {tags.length === 0 && (
          <p style={{ fontSize: 12, color: 'var(--aurora-muted)', fontStyle: 'italic', margin: 0 }}>
            No tags yet.
          </p>
        )}
        {tags.map((tag) => (
          <span
            key={tag}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              background: 'var(--aurora-pill)',
              border: '1px solid var(--aurora-pill-border)',
              borderRadius: 20,
              padding: '3px 10px 3px 9px',
              fontSize: 11,
              fontWeight: 600,
              color: 'var(--aurora-accent)',
            }}
          >
            #{tag}
            <button
              type="button"
              onClick={() => onRemove(tag)}
              aria-label={`Remove tag ${tag}`}
              style={{
                background: 'none',
                border: 'none',
                padding: 0,
                cursor: 'pointer',
                color: 'var(--aurora-accent)',
                lineHeight: 1,
                fontSize: 12,
                display: 'flex',
                alignItems: 'center',
                opacity: 0.7,
              }}
            >
              ✕
            </button>
          </span>
        ))}
      </div>

      <div style={{ display: 'flex', gap: 8 }}>
        <input
          type="text"
          value={input}
          onChange={(e) => onInputChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              onAdd()
            }
          }}
          placeholder="Add a tag"
          style={{ ...AURORA_INPUT, flex: 1 }}
          onFocus={(e) => { e.currentTarget.style.borderColor = 'var(--aurora-accent)' }}
          onBlur={(e) => { e.currentTarget.style.borderColor = 'var(--aurora-input-border)' }}
        />
        <button
          type="button"
          onClick={onAdd}
          disabled={!input.trim()}
          style={{
            ...AURORA_BTN_GHOST,
            opacity: !input.trim() ? 0.4 : 1,
            cursor: !input.trim() ? 'not-allowed' : 'pointer',
          }}
        >
          Add
        </button>
      </div>

      {popularTags.length > 0 && (
        <div>
          <p style={{ fontSize: 10, color: 'var(--aurora-muted)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', margin: '0 0 6px' }}>
            Popular tags — click to add
          </p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {popularTags.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => onQuickAdd(t.name)}
                title={`Add tag "${t.name}"`}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  borderRadius: 20,
                  padding: '3px 10px',
                  fontSize: 11,
                  fontWeight: 600,
                  cursor: 'pointer',
                  background: 'rgba(15,164,171,0.08)',
                  border: '1px solid var(--aurora-pill-border)',
                  color: 'var(--aurora-accent)',
                }}
              >
                + #{t.name}
              </button>
            ))}
          </div>
        </div>
      )}

      <p style={{ fontSize: 11, color: 'var(--aurora-muted)', margin: 0 }}>
        New tags are added immediately but may show as <strong>pending</strong> until
        an admin approves them.
      </p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Show SCAD modal
// ---------------------------------------------------------------------------

interface ShowScadModalProps {
  open: boolean
  onClose: () => void
  itemKey: string
  file: api.FileOut
}

function ShowScadModal({ open, onClose, itemKey, file }: ShowScadModalProps) {
  const [copied, setCopied] = useState(false)
  const [opening, setOpening] = useState(false)
  const basename = file.path.split('/').pop() ?? file.path
  const tooLarge = file.size > SCAD_PREVIEW_MAX_MB * 1024 * 1024

  const { data: code, isLoading, isError } = useQuery({
    queryKey: ['scad-text', itemKey, file.path],
    queryFn: () => api.fetchFileText(itemKey, file.path),
    enabled: open && !tooLarge,
  })

  // Close on Escape.
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, onClose])

  // Reset transient "Copied" state whenever the modal is reopened.
  useEffect(() => {
    if (open) setCopied(false)
  }, [open])

  if (!open) return null

  const handleCopy = async () => {
    if (!code) return
    await navigator.clipboard.writeText(code)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  const handleOpenInPlayground = async () => {
    if (!code) return
    setOpening(true)
    try {
      const url = await playgroundUrl(code, basename)
      window.open(url, '_blank', 'noopener')
    } finally {
      setOpening(false)
    }
  }

  return createPortal(
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'rgba(5,13,28,0.80)',
        backdropFilter: 'blur(10px)',
        WebkitBackdropFilter: 'blur(10px)',
        padding: 16,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={`SCAD source — ${basename}`}
        style={{
          background: 'var(--aurora-card)',
          border: '1px solid var(--aurora-card-border)',
          borderRadius: 14,
          width: '100%',
          maxWidth: 780,
          maxHeight: '85vh',
          display: 'flex',
          flexDirection: 'column',
          color: 'var(--aurora-text)',
        }}
      >
        {/* Header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 12,
            padding: '16px 20px',
            borderBottom: '1px solid var(--aurora-divider)',
          }}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
            <h2
              style={{
                margin: 0,
                fontSize: 15,
                fontWeight: 700,
                fontFamily: 'monospace',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {basename}
            </h2>
            <span style={{ fontSize: 11, color: 'var(--aurora-muted)' }}>{formatBytes(file.size)}</span>
          </div>
          <button
            onClick={onClose}
            aria-label="Close SCAD viewer"
            style={{
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              color: 'var(--aurora-muted)',
              padding: 4,
              display: 'flex',
              flexShrink: 0,
            }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div style={{ padding: '16px 20px', overflowY: 'auto', flex: 1, minHeight: 0 }}>
          {tooLarge ? (
            <p style={{ fontSize: 12, color: 'var(--aurora-muted)', margin: 0 }}>
              This file is larger than {SCAD_PREVIEW_MAX_MB} MB — too large to preview inline.
              Use Download below to get the full source.
            </p>
          ) : isLoading ? (
            <p style={{ fontSize: 12, color: 'var(--aurora-muted)', margin: 0 }}>Loading…</p>
          ) : isError ? (
            <p style={{ fontSize: 12, color: 'var(--aurora-danger)', margin: 0 }}>
              Failed to load the file's contents.
            </p>
          ) : (
            <pre
              style={{
                margin: 0,
                fontSize: 12,
                fontFamily: 'monospace',
                lineHeight: 1.6,
                color: 'var(--aurora-text-dim)',
                whiteSpace: 'pre',
                overflow: 'auto',
                background: 'var(--aurora-glass)',
                border: '1px solid var(--aurora-glass-border)',
                borderRadius: 8,
                padding: 12,
              }}
            >
              {code}
            </pre>
          )}
        </div>

        {/* Footer actions */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            flexWrap: 'wrap',
            padding: '12px 20px',
            borderTop: '1px solid var(--aurora-divider)',
          }}
        >
          <button
            onClick={handleCopy}
            disabled={!code}
            style={{
              ...AURORA_BTN_GHOST,
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              opacity: code ? 1 : 0.5,
              cursor: code ? 'pointer' : 'not-allowed',
            }}
          >
            <Copy size={12} />
            {copied ? 'Copied' : 'Copy'}
          </button>
          <a
            href={api.fileDownloadUrl(itemKey, file.path)}
            download
            style={{
              ...AURORA_BTN_GHOST,
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              textDecoration: 'none',
            }}
          >
            <Download size={12} />
            Download
          </a>
          <button
            onClick={handleOpenInPlayground}
            disabled={!code || opening}
            title="Open this file in the OpenSCAD web playground (editing/preview/STL export)"
            style={{
              ...AURORA_BTN_GHOST,
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              opacity: code && !opening ? 1 : 0.5,
              cursor: code && !opening ? 'pointer' : 'not-allowed',
            }}
          >
            <ExternalLink size={12} />
            {opening ? 'Opening…' : 'Open in OpenSCAD Playground'}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  )
}
