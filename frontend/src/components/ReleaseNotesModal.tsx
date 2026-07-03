/**
 * ReleaseNotesModal — "What's New" dismissible modal shown once after an upgrade.
 *
 * Reuses Aurora palette variables and the inline-style card pattern established
 * by AddAssetModal and ApiKeysPage.  No new UI libraries are introduced.
 *
 * Props:
 *   version  — the current running version string (bare, no "v" prefix)
 *   onClose  — called when the user dismisses; caller should persist seen-version
 */

import React, { useEffect } from 'react'
import { ExternalLink, Sparkles, X } from 'lucide-react'

import { getReleaseNote } from '@/lib/releaseNotes'
import { Button } from '@/components/ui/Button'

interface ReleaseNotesModalProps {
  version: string
  onClose: () => void
}

export function ReleaseNotesModal({ version, onClose }: ReleaseNotesModalProps) {
  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  const note = getReleaseNote(version)
  const title = note?.title ?? `What's New in v${version}`
  const bullets = note?.bullets ?? []
  const githubUrl =
    note?.githubReleaseUrl ??
    `https://github.com/crzykidd/partfolder3d/releases/tag/v${version}`

  return (
    /* Backdrop */
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 60,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'rgba(5,13,28,0.80)',
        backdropFilter: 'blur(10px)',
        WebkitBackdropFilter: 'blur(10px)',
        padding: 16,
      } as React.CSSProperties}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      {/* Dialog panel */}
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="release-notes-title"
        style={{
          background: 'var(--aurora-card)',
          border: '1px solid var(--aurora-card-border)',
          borderRadius: 16,
          backdropFilter: 'blur(32px)',
          WebkitBackdropFilter: 'blur(32px)',
          boxShadow: '0 24px 64px rgba(0,0,0,0.40)',
          width: '100%',
          maxWidth: 480,
          maxHeight: '90vh',
          overflowY: 'auto',
          color: 'var(--aurora-text)',
          display: 'flex',
          flexDirection: 'column',
          gap: 0,
        } as React.CSSProperties}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'flex-start',
            gap: 12,
            padding: '22px 22px 0',
          }}
        >
          {/* Icon */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 38,
              height: 38,
              borderRadius: 10,
              background: 'rgba(15,164,171,0.12)',
              border: '1px solid rgba(15,164,171,0.25)',
              flexShrink: 0,
              marginTop: 2,
            }}
          >
            <Sparkles size={17} style={{ color: 'var(--aurora-accent)' }} />
          </div>

          {/* Title + version badge */}
          <div style={{ flex: 1, minWidth: 0 }}>
            <h2
              id="release-notes-title"
              style={{
                margin: 0,
                fontSize: 15,
                fontWeight: 700,
                color: 'var(--aurora-text)',
                lineHeight: 1.3,
              }}
            >
              {title}
            </h2>
            <p style={{ margin: '3px 0 0', fontSize: 12, color: 'var(--aurora-muted)' }}>
              PartFolder 3D was just upgraded — here's what changed.
            </p>
          </div>

          {/* Close button */}
          <button
            onClick={onClose}
            aria-label="Dismiss release notes"
            style={{
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              color: 'var(--aurora-muted)',
              padding: 4,
              borderRadius: 6,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
              marginTop: -2,
            }}
          >
            <X size={16} />
          </button>
        </div>

        {/* Divider */}
        <div
          style={{
            height: 1,
            background: 'var(--aurora-divider)',
            margin: '16px 22px 0',
          }}
        />

        {/* Bullets */}
        <div style={{ padding: '16px 22px' }}>
          {bullets.length > 0 ? (
            <ul
              style={{
                margin: 0,
                padding: 0,
                listStyle: 'none',
                display: 'flex',
                flexDirection: 'column',
                gap: 10,
              }}
            >
              {bullets.map((bullet, i) => (
                <li
                  key={i}
                  style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: 10,
                    fontSize: 13,
                    color: 'var(--aurora-text-dim)',
                    lineHeight: 1.55,
                  }}
                >
                  {/* Teal dot */}
                  <span
                    style={{
                      width: 6,
                      height: 6,
                      borderRadius: '50%',
                      background: 'var(--aurora-accent)',
                      flexShrink: 0,
                      marginTop: 6,
                    }}
                  />
                  {bullet}
                </li>
              ))}
            </ul>
          ) : (
            <p style={{ margin: 0, fontSize: 13, color: 'var(--aurora-muted)' }}>
              See the release notes for details.
            </p>
          )}
        </div>

        {/* Footer */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 12,
            padding: '0 22px 20px',
            flexWrap: 'wrap',
          }}
        >
          {/* Release notes link */}
          <a
            href={githubUrl}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 5,
              fontSize: 12,
              color: 'var(--aurora-accent)',
              textDecoration: 'none',
              fontWeight: 500,
            }}
          >
            <ExternalLink size={12} />
            View full release notes
          </a>

          {/* Dismiss */}
          <Button variant="primary" size="sm" onClick={onClose}>
            Got it
          </Button>
        </div>
      </div>
    </div>
  )
}
