/**
 * SiteSetupBanner — shown on the Title step when a site requires an API token
 * or is manual-only (no automatic downloading).
 */

import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import * as api from '@/lib/api'
import { AURORA_INPUT, onAuroraFocus, onAuroraBlur } from './styles'

interface SiteSetupBannerProps {
  domain: string
  cap: api.SiteCapability
  sessionId: string
}

export function SiteSetupBanner({ domain, cap, sessionId }: SiteSetupBannerProps) {
  const [token, setToken] = useState('')
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const queryClient = useQueryClient()

  const patchMutation = useMutation({
    mutationFn: () => api.patchSiteCapability(domain, { token: token.trim() }),
    onSuccess: () => {
      setSaved(true)
      setToken('')
      void queryClient.invalidateQueries({ queryKey: ['site-cap', domain] })
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : 'Failed to save token.'),
  })

  if (!cap.requires_token && !cap.is_manual_only) return null

  return (
    <div
      style={{
        background: 'rgba(245,158,11,0.08)',
        border: '1px solid rgba(245,158,11,0.3)',
        borderRadius: 10,
        padding: '14px 16px',
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
      }}
    >
      {cap.is_manual_only && (
        <p style={{ fontSize: 13, fontWeight: 600, color: '#D97706', margin: 0 }}>
          This site requires manual file upload — automatic downloading is not supported.
          Please upload the files yourself in the previous step.
        </p>
      )}
      {cap.requires_token && !cap.has_token && (
        <>
          <p style={{ fontSize: 13, fontWeight: 600, color: '#D97706', margin: 0 }}>
            This site requires an API token to import files automatically.
          </p>
          <div style={{ display: 'flex', gap: 8 }}>
            <input
              type="password"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="Paste your API token here"
              style={{ ...AURORA_INPUT, flex: 1 }}
              onFocus={onAuroraFocus}
              onBlur={onAuroraBlur}
            />
            <button
              type="button"
              disabled={patchMutation.isPending || !token.trim()}
              onClick={() => { setError(null); setSaved(false); patchMutation.mutate() }}
              style={{
                background: '#D97706',
                border: 'none',
                borderRadius: 20,
                color: '#FFFFFF',
                fontSize: 12,
                fontWeight: 700,
                padding: '6px 16px',
                cursor: 'pointer',
                opacity: patchMutation.isPending || !token.trim() ? 0.5 : 1,
                transition: 'opacity 0.15s',
                flexShrink: 0,
              }}
            >
              {patchMutation.isPending ? 'Saving…' : 'Save Token'}
            </button>
          </div>
          {saved && (
            <p style={{ fontSize: 12, color: '#16A34A', margin: 0 }}>✓ Token saved.</p>
          )}
          {error && (
            <p style={{ fontSize: 12, color: 'var(--aurora-danger)', margin: 0 }}>{error}</p>
          )}
        </>
      )}
      {cap.requires_token && cap.has_token && (
        <p style={{ fontSize: 13, color: '#D97706', margin: 0 }}>
          Token is configured for this site.{' '}
          <span style={{ fontSize: 11, color: 'var(--aurora-muted)' }}>
            (Session: {sessionId.slice(0, 8)}…)
          </span>
        </p>
      )}
    </div>
  )
}
