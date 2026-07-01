/**
 * ResetPasswordPage — public page to consume a password-reset token.
 *
 * URL: /password-reset/:token
 * POST /api/password-reset/{token} → { new_password }
 *
 * On success: redirect to /login.
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
// ResetPasswordPage
// ---------------------------------------------------------------------------

export function ResetPasswordPage() {
  const { token } = useParams<{ token: string }>()
  const navigate = useNavigate()

  const [newPassword, setNewPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [localError, setLocalError] = useState('')

  const mutation = useMutation({
    mutationFn: () => api.useResetToken(token!, newPassword),
    onSuccess: () => {
      navigate('/login', {
        replace: true,
        state: { message: 'Password updated. Please sign in.' },
      })
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (newPassword !== confirm) {
      setLocalError('Passwords do not match.')
      return
    }
    setLocalError('')
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
            Reset your password
          </h1>
          <p style={{ margin: '5px 0 0', fontSize: 13, color: 'var(--aurora-muted)' }}>
            Enter your new password below.
          </p>
        </div>

        <form onSubmit={handleSubmit}>
          <div style={CARD_STYLE}>
            <div>
              <label htmlFor="new-password" style={LABEL_STYLE}>New password</label>
              <AuroraInput
                id="new-password"
                type="password"
                autoComplete="new-password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="At least 8 characters"
                required
                minLength={8}
              />
            </div>

            <div>
              <label htmlFor="confirm-password" style={LABEL_STYLE}>Confirm new password</label>
              <AuroraInput
                id="confirm-password"
                type="password"
                autoComplete="new-password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                placeholder="Repeat password"
                required
              />
            </div>

            {(localError || mutation.isError) && (
              <p style={{ margin: 0, fontSize: 13, color: 'var(--aurora-danger)' }}>
                {localError ||
                  (mutation.error instanceof api.ApiError
                    ? mutation.error.message
                    : 'Failed to reset password. The link may be expired.')}
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
              {mutation.isPending ? 'Updating…' : 'Update password'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
