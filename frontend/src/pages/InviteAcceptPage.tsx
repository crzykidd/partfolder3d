/**
 * InviteAcceptPage — public page to accept an invite link.
 *
 * URL: /invites/:token/accept
 * POST /api/invites/{token}/accept → { name, password }
 *
 * On success: account created → redirect to /login.
 *
 * Styling: standalone Aurora screen (gradient bg + glass card, dark+light).
 */

import React, { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'

import * as api from '@/lib/api'
import { AuroraInput } from '@/components/ui'

// ---------------------------------------------------------------------------
// Style constants
// ---------------------------------------------------------------------------

const PAGE_STYLE: React.CSSProperties = {
  minHeight: '100vh',
  background: 'linear-gradient(135deg, var(--aurora-bg-from) 0%, var(--aurora-bg-to) 100%)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  padding: '24px 16px',
}

const CARD_STYLE: React.CSSProperties = {
  background: 'var(--aurora-card)',
  border: '1px solid var(--aurora-card-border)',
  borderRadius: 16,
  backdropFilter: 'blur(20px)',
  WebkitBackdropFilter: 'blur(20px)',
  padding: '28px 32px',
  display: 'flex',
  flexDirection: 'column',
  gap: 18,
}

const LABEL_STYLE: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  color: 'var(--aurora-muted)',
  textTransform: 'uppercase',
  letterSpacing: '0.07em',
  display: 'block',
  marginBottom: 5,
}

const BTN_PRIMARY: React.CSSProperties = {
  width: '100%',
  background: 'var(--aurora-accent)',
  color: '#fff',
  border: 'none',
  borderRadius: 10,
  padding: '10px 16px',
  fontSize: 14,
  fontWeight: 600,
  cursor: 'pointer',
  transition: 'opacity 0.15s',
}

// ---------------------------------------------------------------------------
// InviteAcceptPage
// ---------------------------------------------------------------------------

export function InviteAcceptPage() {
  const { token } = useParams<{ token: string }>()
  const navigate = useNavigate()

  const [name, setName] = useState('')
  const [password, setPassword] = useState('')

  const mutation = useMutation({
    mutationFn: () =>
      api.acceptInvite(token!, { name, password }),
    onSuccess: () => {
      navigate('/login', { replace: true, state: { message: 'Account created. Please sign in.' } })
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    mutation.mutate()
  }

  return (
    <div style={PAGE_STYLE}>
      <div style={{ width: '100%', maxWidth: 360 }}>
        {/* Brand header */}
        <div style={{ textAlign: 'center', marginBottom: 28 }}>
          <div
            aria-hidden="true"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 48,
              height: 48,
              borderRadius: 14,
              background: 'var(--aurora-accent)',
              boxShadow: 'var(--aurora-glow)',
              marginBottom: 14,
            }}
          >
            <span style={{ color: '#fff', fontWeight: 900, fontSize: 18, letterSpacing: '-0.03em' }}>PF</span>
          </div>
          <h1
            style={{
              margin: 0,
              fontSize: 20,
              fontWeight: 800,
              color: 'var(--aurora-text)',
              letterSpacing: '-0.02em',
            }}
          >
            Create your account
          </h1>
          <p style={{ margin: '5px 0 0', fontSize: 13, color: 'var(--aurora-muted)' }}>
            You've been invited to PartFolder 3D. Set your name and password to get started.
          </p>
        </div>

        <form onSubmit={handleSubmit}>
          <div style={CARD_STYLE}>
            <div>
              <label htmlFor="name" style={LABEL_STYLE}>Your name</label>
              <AuroraInput
                id="name"
                type="text"
                autoComplete="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Alice"
                required
              />
            </div>

            <div>
              <label htmlFor="password" style={LABEL_STYLE}>Password</label>
              <AuroraInput
                id="password"
                type="password"
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="At least 8 characters"
                required
                minLength={8}
              />
            </div>

            {mutation.isError && (
              <p style={{ margin: 0, fontSize: 13, color: 'var(--aurora-danger)' }}>
                {mutation.error instanceof api.ApiError
                  ? mutation.error.message
                  : 'Something went wrong. The invite link may be invalid or expired.'}
              </p>
            )}

            <button
              type="submit"
              disabled={mutation.isPending}
              style={{
                ...BTN_PRIMARY,
                opacity: mutation.isPending ? 0.6 : 1,
                cursor: mutation.isPending ? 'not-allowed' : 'pointer',
              }}
            >
              {mutation.isPending ? 'Creating account…' : 'Create account'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
