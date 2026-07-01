import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Check, Copy } from 'lucide-react'

import * as api from '@/lib/api'

import { AURORA_BTN_GHOST, AURORA_BTN_PRIMARY, AURORA_INPUT, formatExpiry } from './styles'

// ---------------------------------------------------------------------------
// Share controls section
// ---------------------------------------------------------------------------

export interface ShareSectionProps {
  itemKey: string
}

export function ShareSection({ itemKey }: ShareSectionProps) {
  const queryClient = useQueryClient()
  const [mintOpen, setMintOpen] = useState(false)
  const [mintLabel, setMintLabel] = useState('')
  const [mintExpiry, setMintExpiry] = useState('')
  const [mintError, setMintError] = useState<string | null>(null)
  const [copiedToken, setCopiedToken] = useState<string | null>(null)
  const [confirmRevoke, setConfirmRevoke] = useState<number | null>(null)

  const { data: links = [], isLoading, isError } = useQuery({
    queryKey: ['item-shares', itemKey],
    queryFn: () => api.listItemShares(itemKey),
    staleTime: 30_000,
  })

  const mintMutation = useMutation({
    mutationFn: () =>
      api.mintItemShare(itemKey, {
        label: mintLabel || null,
        expires_days: mintExpiry ? Number(mintExpiry) : null,
      }),
    onSuccess: async (link) => {
      setMintOpen(false)
      setMintLabel('')
      setMintExpiry('')
      setMintError(null)
      void queryClient.invalidateQueries({ queryKey: ['item-shares', itemKey] })
      // Auto-copy the new link
      const url = `${window.location.origin}/share/${link.token}`
      try {
        await navigator.clipboard.writeText(url)
        setCopiedToken(link.token)
        setTimeout(() => setCopiedToken(null), 3000)
      } catch {
        // ignore clipboard failure
      }
    },
    onError: (e) => {
      setMintError(e instanceof Error ? e.message : 'Failed to mint share link.')
    },
  })

  const revokeMutation = useMutation({
    mutationFn: (shareId: number) => api.revokeShare(shareId),
    onSuccess: () => {
      setConfirmRevoke(null)
      void queryClient.invalidateQueries({ queryKey: ['item-shares', itemKey] })
    },
  })

  async function handleCopy(token: string) {
    const url = `${window.location.origin}/share/${token}`
    try {
      await navigator.clipboard.writeText(url)
      setCopiedToken(token)
      setTimeout(() => setCopiedToken(null), 2000)
    } catch {
      // ignore
    }
  }

  const labelStyle: React.CSSProperties = {
    fontSize: 10,
    fontWeight: 700,
    color: 'var(--aurora-muted)',
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
    display: 'block',
    marginBottom: 5,
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {isLoading && <p style={{ fontSize: 12, color: 'var(--aurora-muted)', margin: 0 }}>Loading…</p>}
      {isError && <p style={{ fontSize: 12, color: 'var(--aurora-danger)', margin: 0 }}>Failed to load share links.</p>}

      {!isLoading && links.length === 0 && (
        <p style={{ fontSize: 12, color: 'var(--aurora-muted)', fontStyle: 'italic', margin: 0 }}>No share links yet.</p>
      )}

      {links.length > 0 && (
        <div
          style={{
            background: 'var(--aurora-glass)',
            border: '1px solid var(--aurora-glass-border)',
            borderRadius: 10,
            overflow: 'hidden',
          }}
        >
          {links.map((link, idx) => (
            <div
              key={link.id}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '10px 14px',
                borderTop: idx > 0 ? '1px solid var(--aurora-divider)' : 'none',
                transition: 'background 0.1s',
              }}
              onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.background = 'var(--aurora-glass-hover)' }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.background = 'transparent' }}
            >
              <div style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <span style={{ fontSize: 12, fontFamily: 'monospace', color: 'var(--aurora-muted)' }}>
                    {link.token.slice(0, 8)}…
                  </span>
                  {link.label && (
                    <span style={{ fontSize: 12, fontWeight: 500, color: 'var(--aurora-text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {link.label}
                    </span>
                  )}
                  {link.revoked && (
                    <span style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      padding: '2px 7px',
                      borderRadius: 20,
                      fontSize: 10,
                      fontWeight: 700,
                      background: 'rgba(239,68,68,0.15)',
                      color: '#EF4444',
                      border: '1px solid rgba(239,68,68,0.3)',
                    }}>
                      Revoked
                    </span>
                  )}
                  {copiedToken === link.token && (
                    <span style={{ fontSize: 11, color: '#22C55E', display: 'flex', alignItems: 'center', gap: 3 }}>
                      <Check size={11} /> Copied!
                    </span>
                  )}
                </div>
                <span style={{ fontSize: 11, color: 'var(--aurora-muted)' }}>
                  {formatExpiry(link.expires_at)}
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0, marginLeft: 8 }}>
                {!link.revoked && (
                  <button
                    onClick={() => void handleCopy(link.token)}
                    style={{ ...AURORA_BTN_GHOST, fontSize: 11, padding: '3px 9px', display: 'flex', alignItems: 'center', gap: 4 }}
                  >
                    <Copy size={11} />
                    Copy link
                  </button>
                )}
                {!link.revoked && confirmRevoke !== link.id && (
                  <button
                    onClick={() => setConfirmRevoke(link.id)}
                    style={{ ...AURORA_BTN_GHOST, fontSize: 11, padding: '3px 9px' }}
                    onMouseEnter={(e) => {
                      (e.currentTarget as HTMLButtonElement).style.background = 'rgba(239,68,68,0.12)'
                      ;(e.currentTarget as HTMLButtonElement).style.color = '#EF4444'
                      ;(e.currentTarget as HTMLButtonElement).style.borderColor = 'rgba(239,68,68,0.3)'
                    }}
                    onMouseLeave={(e) => {
                      (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass)'
                      ;(e.currentTarget as HTMLButtonElement).style.color = 'var(--aurora-text-dim)'
                      ;(e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--aurora-glass-border)'
                    }}
                  >
                    Revoke
                  </button>
                )}
                {confirmRevoke === link.id && (
                  <div style={{ display: 'flex', gap: 4 }}>
                    <button
                      onClick={() => revokeMutation.mutate(link.id)}
                      disabled={revokeMutation.isPending}
                      style={{
                        background: '#EF4444',
                        border: 'none',
                        borderRadius: 20,
                        color: '#FFF',
                        fontSize: 11,
                        padding: '3px 9px',
                        cursor: 'pointer',
                        opacity: revokeMutation.isPending ? 0.5 : 1,
                      }}
                    >
                      {revokeMutation.isPending ? '…' : 'Confirm'}
                    </button>
                    <button
                      onClick={() => setConfirmRevoke(null)}
                      style={{ ...AURORA_BTN_GHOST, fontSize: 11, padding: '3px 9px' }}
                    >
                      Cancel
                    </button>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Mint button */}
      {!mintOpen && (
        <button
          onClick={() => setMintOpen(true)}
          style={{ ...AURORA_BTN_GHOST, alignSelf: 'flex-start' }}
        >
          + Create share link
        </button>
      )}

      {/* Mint form */}
      {mintOpen && (
        <div
          style={{
            background: 'var(--aurora-glass)',
            border: '1px solid var(--aurora-glass-border)',
            borderRadius: 10,
            padding: '14px',
            display: 'flex',
            flexDirection: 'column',
            gap: 12,
          }}
        >
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <label style={labelStyle}>Label (optional)</label>
              <input
                type="text"
                value={mintLabel}
                onChange={(e) => setMintLabel(e.target.value)}
                placeholder="e.g. Public gallery"
                style={AURORA_INPUT}
              />
            </div>
            <div>
              <label style={labelStyle}>Expires in (days)</label>
              <input
                type="number"
                min="0"
                value={mintExpiry}
                onChange={(e) => setMintExpiry(e.target.value)}
                placeholder="30 (blank = instance default)"
                style={AURORA_INPUT}
              />
            </div>
          </div>
          {mintError && <p style={{ fontSize: 11, color: 'var(--aurora-danger)', margin: 0 }}>{mintError}</p>}
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={() => mintMutation.mutate()}
              disabled={mintMutation.isPending}
              style={{ ...AURORA_BTN_PRIMARY, opacity: mintMutation.isPending ? 0.5 : 1 }}
            >
              {mintMutation.isPending ? 'Creating…' : 'Create & copy link'}
            </button>
            <button
              onClick={() => { setMintOpen(false); setMintError(null) }}
              style={AURORA_BTN_GHOST}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
