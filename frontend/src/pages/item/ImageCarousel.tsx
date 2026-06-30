import React, { useEffect, useState } from 'react'
import { Trash2, X as XIcon } from 'lucide-react'

import * as api from '@/lib/api'
import { buildCarouselPagerItems } from '@/lib/carousel-utils'

import { AURORA_CARD, AURORA_BTN_GHOST } from './styles'

// ---------------------------------------------------------------------------
// Image carousel
// ---------------------------------------------------------------------------

/** Number of thumbnails visible at one time in the strip. */
const THUMBS_VISIBLE = 6

export interface ImageCarouselProps {
  images: api.ImageOut[]
  itemKey: string
  onSetDefault: (imageId: number) => void
  onDeleteImage: (imageId: number) => void
  isSettingDefault: boolean
  isDeletingImage: boolean
  isOwner: boolean
}

export function ImageCarousel({
  images,
  itemKey,
  onSetDefault,
  onDeleteImage,
  isSettingDefault,
  isDeletingImage,
  isOwner,
}: ImageCarouselProps) {
  const [activeIdx, setActiveIdx] = useState(0)
  // thumbOffset: index of the leftmost visible thumbnail in the strip
  const [thumbOffset, setThumbOffset] = useState(0)
  const [lightbox, setLightbox] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null)

  // Keep activeIdx in bounds when images list changes
  const clampedIdx = Math.min(activeIdx, Math.max(0, images.length - 1))

  // Auto-scroll the strip so the active thumbnail is always visible
  useEffect(() => {
    setThumbOffset((prev) => {
      if (clampedIdx < prev) return clampedIdx
      if (clampedIdx >= prev + THUMBS_VISIBLE) return Math.max(0, clampedIdx - THUMBS_VISIBLE + 1)
      return prev
    })
  }, [clampedIdx])

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
  const maxThumbOffset = Math.max(0, images.length - THUMBS_VISIBLE)
  const totalPages = Math.ceil(images.length / THUMBS_VISIBLE)
  const currentPage = Math.floor(clampedIdx / THUMBS_VISIBLE)
  const pagerItems = buildCarouselPagerItems(currentPage, totalPages)
  const visibleThumbs = images.slice(thumbOffset, thumbOffset + THUMBS_VISIBLE)
  const emptySlots = Math.max(0, THUMBS_VISIBLE - visibleThumbs.length)

  function handleDeleteConfirm(imageId: number) {
    setConfirmDelete(null)
    onDeleteImage(imageId)
  }

  function scrollThumbsLeft() {
    setThumbOffset((o) => Math.max(0, o - 1))
  }

  function scrollThumbsRight() {
    setThumbOffset((o) => Math.min(maxThumbOffset, o + 1))
  }

  function jumpToPage(page: number) {
    const firstIdx = page * THUMBS_VISIBLE
    setActiveIdx(firstIdx)
    setThumbOffset(Math.min(firstIdx, maxThumbOffset))
  }

  const arrowBtnStyle: React.CSSProperties = {
    ...AURORA_BTN_GHOST,
    width: 28,
    height: 60,
    padding: 0,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
    fontSize: 18,
    lineHeight: 1,
    borderRadius: 8,
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {/* Main image — fixed height so it never dominates the hero */}
      <div
        style={{
          ...AURORA_CARD,
          position: 'relative',
          overflow: 'hidden',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: 300,
        }}
      >
        <img
          src={`/api/items/${itemKey}/files/${active.path}`}
          alt={`Image ${clampedIdx + 1}`}
          style={{ maxHeight: '100%', maxWidth: '100%', objectFit: 'contain', cursor: 'zoom-in' }}
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

        {/* Bottom-right: image counter */}
        {images.length > 1 && (
          <div
            style={{
              position: 'absolute',
              bottom: 8,
              right: 8,
              background: 'rgba(0,0,0,0.45)',
              color: '#fff',
              borderRadius: 20,
              fontSize: 11,
              padding: '2px 8px',
              lineHeight: 1.4,
            }}
          >
            {clampedIdx + 1} / {images.length}
          </div>
        )}
      </div>

      {/* Compact thumbnail strip + pager (only when > 1 image) */}
      {images.length > 1 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
          {/* Strip row: ‹ [thumb slots] › */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            {/* Left scroll arrow */}
            <button
              onClick={scrollThumbsLeft}
              disabled={thumbOffset === 0}
              aria-label="Scroll thumbnails left"
              style={{
                ...arrowBtnStyle,
                opacity: thumbOffset === 0 ? 0.3 : 1,
                cursor: thumbOffset === 0 ? 'default' : 'pointer',
              }}
            >
              ‹
            </button>

            {/* Visible thumbnail slots (always THUMBS_VISIBLE wide) */}
            <div style={{ display: 'flex', gap: 5, flex: 1, minWidth: 0 }}>
              {visibleThumbs.map((img, slotIdx) => {
                const idx = thumbOffset + slotIdx
                const isActive = idx === clampedIdx
                return (
                  <button
                    key={img.id}
                    onClick={() => setActiveIdx(idx)}
                    aria-label={`Select image ${idx + 1}`}
                    aria-pressed={isActive}
                    style={{
                      flex: '1 1 0',
                      minWidth: 0,
                      height: 60,
                      borderRadius: 8,
                      overflow: 'hidden',
                      border: `2px solid ${isActive ? 'var(--aurora-accent)' : 'var(--aurora-glass-border)'}`,
                      boxShadow: isActive ? 'var(--aurora-glow)' : 'none',
                      cursor: 'pointer',
                      padding: 0,
                      transition: 'all 0.15s',
                      position: 'relative',
                      background: 'var(--aurora-glass)',
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
                )
              })}
              {/* Empty spacer slots to keep strip width stable */}
              {Array.from({ length: emptySlots }).map((_, i) => (
                <div key={`empty-${i}`} style={{ flex: '1 1 0', minWidth: 0, height: 60 }} />
              ))}
            </div>

            {/* Right scroll arrow */}
            <button
              onClick={scrollThumbsRight}
              disabled={thumbOffset >= maxThumbOffset}
              aria-label="Scroll thumbnails right"
              style={{
                ...arrowBtnStyle,
                opacity: thumbOffset >= maxThumbOffset ? 0.3 : 1,
                cursor: thumbOffset >= maxThumbOffset ? 'default' : 'pointer',
              }}
            >
              ›
            </button>
          </div>

          {/* Jump nav: page number buttons (only when totalPages > 1) */}
          {pagerItems.length > 0 && (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4 }}>
              {pagerItems.map((pageItem, i) =>
                pageItem === 'ellipsis' ? (
                  <span
                    key={`ellipsis-${i}`}
                    style={{ fontSize: 11, color: 'var(--aurora-muted)', userSelect: 'none', padding: '0 1px' }}
                  >
                    …
                  </span>
                ) : (
                  <button
                    key={`page-${pageItem}`}
                    onClick={() => jumpToPage(pageItem)}
                    aria-label={`Jump to images ${pageItem * THUMBS_VISIBLE + 1}–${Math.min((pageItem + 1) * THUMBS_VISIBLE, images.length)}`}
                    aria-pressed={pageItem === currentPage}
                    style={{
                      width: 24,
                      height: 24,
                      borderRadius: 6,
                      border: pageItem === currentPage
                        ? '1px solid var(--aurora-accent)'
                        : '1px solid var(--aurora-glass-border)',
                      background: pageItem === currentPage
                        ? 'rgba(15,164,171,0.15)'
                        : 'var(--aurora-glass)',
                      color: pageItem === currentPage
                        ? 'var(--aurora-accent)'
                        : 'var(--aurora-text-dim)',
                      fontSize: 11,
                      fontWeight: pageItem === currentPage ? 700 : 400,
                      cursor: 'pointer',
                      padding: 0,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      transition: 'all 0.15s',
                    }}
                  >
                    {pageItem + 1}
                  </button>
                ),
              )}
            </div>
          )}
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
