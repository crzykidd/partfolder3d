/**
 * CreatorStep — Step 4 of the import wizard.
 *
 * Toggle "my own design" / attributed to a creator, with name and profile URL.
 */

import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import * as api from '@/lib/api'
import {
  SECTION_LABEL,
  AURORA_INPUT,
  AURORA_BTN_GHOST,
  AURORA_BTN_PRIMARY,
  onAuroraFocus,
  onAuroraBlur,
} from './styles'

export interface CreatorStepProps {
  session: api.ImportSession
  onNext: () => void
  onPrev: () => void
}

export function CreatorStep({ session, onNext, onPrev }: CreatorStepProps) {
  const queryClient = useQueryClient()
  const [ownDesign, setOwnDesign] = useState(session.creator_is_own_design)
  const [creatorName, setCreatorName] = useState(session.creator_name ?? '')
  const [profileUrl, setProfileUrl] = useState(session.creator_profile_url ?? '')
  const [error, setError] = useState<string | null>(null)

  const patchMutation = useMutation({
    mutationFn: () =>
      api.patchImportSession(session.id, {
        creator_is_own_design: ownDesign,
        creator_name: ownDesign ? null : creatorName.trim() || null,
        creator_profile_url: ownDesign ? null : profileUrl.trim() || null,
      }),
    onSuccess: (updated) => {
      queryClient.setQueryData(['import-session', session.id], updated)
      onNext()
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : 'Failed to save creator.'),
  })

  const handleNext = () => {
    setError(null)
    patchMutation.mutate()
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      {/* Own design toggle — aurora interactive card */}
      <label
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 14,
          background: ownDesign ? 'var(--aurora-pill)' : 'var(--aurora-glass)',
          border: `1px solid ${ownDesign ? 'var(--aurora-pill-border)' : 'var(--aurora-glass-border)'}`,
          borderRadius: 10,
          padding: '14px 16px',
          cursor: 'pointer',
          transition: 'all 0.2s',
          boxShadow: ownDesign ? 'var(--aurora-glow)' : 'none',
        }}
      >
        <input
          type="checkbox"
          checked={ownDesign}
          onChange={(e) => setOwnDesign(e.target.checked)}
          style={{ accentColor: 'var(--aurora-accent)', width: 16, height: 16, cursor: 'pointer', flexShrink: 0 }}
        />
        <div>
          <p style={{ fontSize: 14, fontWeight: 600, color: ownDesign ? 'var(--aurora-accent)' : 'var(--aurora-text)', margin: '0 0 2px', transition: 'color 0.2s' }}>
            This is my own design
          </p>
          <p style={{ fontSize: 11, color: 'var(--aurora-muted)', margin: 0 }}>
            Links this item to your account in "My Creations"
          </p>
        </div>
      </label>

      {/* Attribution fields */}
      {!ownDesign && (
        <div
          style={{
            background: 'var(--aurora-glass)',
            border: '1px solid var(--aurora-glass-border)',
            borderRadius: 10,
            padding: '16px',
            display: 'flex',
            flexDirection: 'column',
            gap: 14,
          }}
        >
          <span style={SECTION_LABEL}>Attributed to a creator</span>

          <div>
            <label style={SECTION_LABEL}>Designer name</label>
            <input
              type="text"
              value={creatorName}
              onChange={(e) => setCreatorName(e.target.value)}
              placeholder="Creator name"
              style={AURORA_INPUT}
              onFocus={onAuroraFocus}
              onBlur={onAuroraBlur}
            />
          </div>

          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
              <label style={{ ...SECTION_LABEL, marginBottom: 0 }}>Profile URL</label>
              <span style={{ fontSize: 10, color: 'var(--aurora-muted)' }}>optional</span>
            </div>
            <input
              type="url"
              value={profileUrl}
              onChange={(e) => setProfileUrl(e.target.value)}
              placeholder="https://…"
              style={AURORA_INPUT}
              onFocus={onAuroraFocus}
              onBlur={onAuroraBlur}
            />
            {profileUrl && (
              <a
                href={profileUrl}
                target="_blank"
                rel="noopener noreferrer"
                style={{ display: 'block', marginTop: 4, fontSize: 11, color: 'var(--aurora-accent)', textDecoration: 'none' }}
                onMouseEnter={(e) => { (e.currentTarget as HTMLAnchorElement).style.textDecoration = 'underline' }}
                onMouseLeave={(e) => { (e.currentTarget as HTMLAnchorElement).style.textDecoration = 'none' }}
              >
                Open profile ↗
              </a>
            )}
          </div>
        </div>
      )}

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
          disabled={patchMutation.isPending}
          onClick={handleNext}
          style={{
            ...AURORA_BTN_PRIMARY,
            opacity: patchMutation.isPending ? 0.6 : 1,
          }}
          onMouseEnter={(e) => { if (!patchMutation.isPending) (e.currentTarget as HTMLButtonElement).style.opacity = '0.85' }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.opacity = patchMutation.isPending ? '0.6' : '1' }}
        >
          {patchMutation.isPending ? 'Saving…' : 'Next →'}
        </button>
      </div>
    </div>
  )
}
