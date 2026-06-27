/**
 * ResetPasswordPage — public page to consume a password-reset token.
 *
 * URL: /password-reset/:token
 * POST /api/password-reset/{token} → { new_password }
 *
 * On success: redirect to /login.
 */

import React, { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'

import * as api from '@/lib/api'

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
    <div className="min-h-screen bg-background flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-foreground">Reset your password</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Enter your new password below.
          </p>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="rounded-lg border border-border bg-card p-6 shadow-sm flex flex-col gap-4">
            <div>
              <label className="block text-sm font-medium mb-1" htmlFor="new-password">
                New password
              </label>
              <input
                id="new-password"
                type="password"
                autoComplete="new-password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="input-base w-full"
                placeholder="At least 8 characters"
                required
                minLength={8}
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-1" htmlFor="confirm-password">
                Confirm new password
              </label>
              <input
                id="confirm-password"
                type="password"
                autoComplete="new-password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                className="input-base w-full"
                placeholder="Repeat password"
                required
              />
            </div>

            {(localError || mutation.isError) && (
              <p className="text-sm text-destructive">
                {localError ||
                  (mutation.error instanceof api.ApiError
                    ? mutation.error.message
                    : 'Failed to reset password. The link may be expired.')}
              </p>
            )}

            <button
              type="submit"
              disabled={mutation.isPending}
              className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
            >
              {mutation.isPending ? 'Updating…' : 'Update password'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
