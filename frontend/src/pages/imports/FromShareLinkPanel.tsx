/**
 * FromShareLinkPanel — collapsible panel to import an item from another
 * PartFolder 3D instance's share link.
 */

import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'

import * as api from '@/lib/api'
import {
  AURORA_BTN_GHOST,
  AURORA_BTN_PRIMARY,
  AURORA_INPUT,
  onAuroraBlur,
  onAuroraFocus,
} from './styles'

export function FromShareLinkPanel() {
  const navigate = useNavigate()
  const [shareUrl, setShareUrl] = useState('')
  const [libraryId, setLibraryId] = useState<number | null>(null)
  const [includePublicNotes, setIncludePublicNotes] = useState(true)
  const [includeGcode, setIncludeGcode] = useState(false)
  const [includePhotos, setIncludePhotos] = useState(true)
  const [includeSettings, setIncludeSettings] = useState(true)
  const [open, setOpen] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  const { data: libraries = [] } = useQuery({
    queryKey: ['libraries'],
    queryFn: api.listLibraries,
    staleTime: 60_000,
  })

  const importMutation = useMutation({
    mutationFn: () =>
      api.importFromShareLink({
        share_url: shareUrl.trim(),
        library_id: libraryId,
        include_public_notes: includePublicNotes,
        include_gcode: includeGcode,
        include_photos: includePhotos,
        include_settings: includeSettings,
      }),
    onSuccess: (session) => {
      navigate(`/import/${session.id}`)
    },
    onError: (e) => {
      setSubmitError(e instanceof Error ? e.message : 'Import failed.')
    },
  })

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        style={AURORA_BTN_GHOST}
        onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass-hover)' }}
        onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass)' }}
      >
        Import from share link
      </button>
    )
  }

  return (
    <div
      style={{
        background: 'var(--aurora-glass)',
        border: '1px solid var(--aurora-glass-border)',
        borderRadius: 12,
        padding: '20px',
        display: 'flex',
        flexDirection: 'column',
        gap: 16,
        minWidth: 320,
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <h2 style={{ fontSize: 14, fontWeight: 700, color: 'var(--aurora-text)', margin: 0 }}>
          Import from share link
        </h2>
        <button
          onClick={() => { setOpen(false); setSubmitError(null) }}
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            color: 'var(--aurora-muted)',
            fontSize: 16,
            lineHeight: 1,
            padding: 4,
            display: 'flex',
            transition: 'color 0.15s',
          }}
          aria-label="Close"
          onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.color = 'var(--aurora-text)' }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.color = 'var(--aurora-muted)' }}
        >
          ✕
        </button>
      </div>

      {/* Share URL */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <label
          style={{ fontSize: 10, fontWeight: 700, color: 'var(--aurora-muted)', letterSpacing: '0.08em', textTransform: 'uppercase' }}
        >
          Share URL
        </label>
        <input
          type="url"
          value={shareUrl}
          onChange={(e) => setShareUrl(e.target.value)}
          placeholder="https://otherinstance.example.com/share/<token>"
          style={AURORA_INPUT}
          onFocus={onAuroraFocus}
          onBlur={onAuroraBlur}
        />
        <p style={{ fontSize: 11, color: 'var(--aurora-muted)', margin: 0 }}>
          Paste a share link from another PartFolder 3D instance.
        </p>
      </div>

      {/* Destination library */}
      {libraries.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <label
            style={{ fontSize: 10, fontWeight: 700, color: 'var(--aurora-muted)', letterSpacing: '0.08em', textTransform: 'uppercase' }}
          >
            Destination library
            <span style={{ fontWeight: 400, marginLeft: 4 }}>(optional)</span>
          </label>
          <select
            value={libraryId ?? ''}
            onChange={(e) => setLibraryId(e.target.value === '' ? null : Number(e.target.value))}
            style={AURORA_INPUT}
            onFocus={onAuroraFocus}
            onBlur={onAuroraBlur}
          >
            <option value="">Auto-select (first enabled)</option>
            {libraries.map((lib) => (
              <option key={lib.id} value={lib.id}>
                {lib.name}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Include options */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <p style={{ fontSize: 10, fontWeight: 700, color: 'var(--aurora-muted)', letterSpacing: '0.08em', textTransform: 'uppercase', margin: 0 }}>
          Include from public print history:
        </p>
        {(
          [
            [includePublicNotes, setIncludePublicNotes, 'Notes & ratings'] as const,
            [includeSettings, setIncludeSettings, 'Structured settings (printer, material, nozzle, etc.)'] as const,
            [includePhotos, setIncludePhotos, 'Print photos'] as const,
          ] as [boolean, React.Dispatch<React.SetStateAction<boolean>>, string][]
        ).map(([checked, setter, label]) => (
          <label
            key={label}
            style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, cursor: 'pointer', userSelect: 'none', color: 'var(--aurora-text-dim)' }}
          >
            <input
              type="checkbox"
              checked={checked}
              onChange={(e) => setter(e.target.checked)}
              style={{ accentColor: 'var(--aurora-accent)', width: 14, height: 14, cursor: 'pointer' }}
            />
            {label}
          </label>
        ))}
        <label
          style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, cursor: 'pointer', userSelect: 'none', color: 'var(--aurora-text-dim)' }}
        >
          <input
            type="checkbox"
            checked={includeGcode}
            onChange={(e) => setIncludeGcode(e.target.checked)}
            style={{ accentColor: 'var(--aurora-accent)', width: 14, height: 14, cursor: 'pointer' }}
          />
          Gcode files
          <span style={{ fontSize: 11, color: 'var(--aurora-muted)' }}>(can be large)</span>
        </label>
      </div>

      {submitError && (
        <p style={{ fontSize: 12, color: 'var(--aurora-danger)', margin: 0 }}>{submitError}</p>
      )}

      {/* Actions */}
      <div style={{ display: 'flex', gap: 8, paddingTop: 2 }}>
        <button
          onClick={() => importMutation.mutate()}
          disabled={!shareUrl.trim() || importMutation.isPending}
          style={{
            ...AURORA_BTN_PRIMARY,
            opacity: !shareUrl.trim() || importMutation.isPending ? 0.5 : 1,
            cursor: !shareUrl.trim() || importMutation.isPending ? 'not-allowed' : 'pointer',
          }}
          onMouseEnter={(e) => { if (shareUrl.trim() && !importMutation.isPending) (e.currentTarget as HTMLButtonElement).style.opacity = '0.85' }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.opacity = !shareUrl.trim() || importMutation.isPending ? '0.5' : '1' }}
        >
          {importMutation.isPending ? 'Importing…' : 'Import'}
        </button>
        <button
          onClick={() => { setOpen(false); setSubmitError(null) }}
          style={AURORA_BTN_GHOST}
          onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass-hover)' }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass)' }}
        >
          Cancel
        </button>
      </div>
    </div>
  )
}
