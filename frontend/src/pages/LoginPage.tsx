/**
 * LoginPage — email + password form → POST /api/auth/login.
 *
 * On success: redirects to the page the user came from, or /.
 * On 401: shows a friendly error; other errors bubble.
 *
 * Styling: standalone Aurora screen (gradient bg + glass card, dark+light).
 */

import React, { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'

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
  letterSpacing: '-0.01em',
}

// ---------------------------------------------------------------------------
// Brand mark
// ---------------------------------------------------------------------------

function AuroraBrand() {
  return (
    <div style={{ textAlign: 'center', marginBottom: 28 }}>
      {/* Teal hexagon wordmark */}
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
        PartFolder 3D
      </h1>
      <p style={{ margin: '5px 0 0', fontSize: 13, color: 'var(--aurora-muted)' }}>
        Sign in to your account
      </p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// LoginPage
// ---------------------------------------------------------------------------

export function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const queryClient = useQueryClient()

  const from = (location.state as { from?: Location } | null)?.from?.pathname ?? '/'

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  const mutation = useMutation({
    mutationFn: () => api.login({ email, password }),
    onSuccess: async () => {
      // A successful login means the instance is initialized — assert it in the
      // cache so AuthGuard can't bounce us to /setup on a stale `false`.
      queryClient.setQueryData(['setupStatus'], { initialized: true })
      // Await the /me refetch so AuthContext.user is populated before we
      // navigate.  Without this await, AuthGuard can render with user===null and
      // isLoading===false (background refetch doesn't flip isLoading) and
      // immediately redirect back to /login — the same race as issue #13.
      try {
        await queryClient.refetchQueries({ queryKey: ['me'] })
      } catch {
        // Refetch failed; navigate anyway since the session cookie is set.
      }
      navigate(from, { replace: true })
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    mutation.mutate()
  }

  const isCredentialError =
    mutation.isError &&
    mutation.error instanceof api.ApiError &&
    mutation.error.status === 401

  return (
    <div style={PAGE_STYLE}>
      <div style={{ width: '100%', maxWidth: 360 }}>
        <AuroraBrand />

        <form onSubmit={handleSubmit}>
          <div style={CARD_STYLE}>
            <div>
              <label htmlFor="email" style={LABEL_STYLE}>Email</label>
              <AuroraInput
                id="email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                required
              />
            </div>

            <div>
              <label htmlFor="password" style={LABEL_STYLE}>Password</label>
              <AuroraInput
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                required
              />
            </div>

            {mutation.isError && (
              <p style={{ margin: 0, fontSize: 13, color: 'var(--aurora-danger)' }}>
                {isCredentialError
                  ? 'Invalid email or password.'
                  : mutation.error instanceof api.ApiError
                    ? mutation.error.message
                    : 'Sign-in failed. Please try again.'}
              </p>
            )}

            <button
              type="submit"
              disabled={mutation.isPending}
              style={{ ...BTN_PRIMARY, opacity: mutation.isPending ? 0.6 : 1, cursor: mutation.isPending ? 'not-allowed' : 'pointer' }}
            >
              {mutation.isPending ? 'Signing in…' : 'Sign in'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
