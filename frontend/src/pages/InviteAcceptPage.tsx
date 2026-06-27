/**
 * InviteAcceptPage — public page to accept an invite link.
 *
 * URL: /invites/:token/accept
 * POST /api/invites/{token}/accept → { name, password }
 *
 * On success: account created → redirect to /login.
 */

import React, { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'

import * as api from '@/lib/api'

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
    <div className="min-h-screen bg-background flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-foreground">Create your account</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            You've been invited to PartFolder 3D. Set your name and password to get started.
          </p>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="rounded-lg border border-border bg-card p-6 shadow-sm flex flex-col gap-4">
            <div>
              <label className="block text-sm font-medium mb-1" htmlFor="name">
                Your name
              </label>
              <input
                id="name"
                type="text"
                autoComplete="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="input-base w-full"
                placeholder="Alice"
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-1" htmlFor="password">
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="input-base w-full"
                placeholder="At least 8 characters"
                required
                minLength={8}
              />
            </div>

            {mutation.isError && (
              <p className="text-sm text-destructive">
                {mutation.error instanceof api.ApiError
                  ? mutation.error.message
                  : 'Something went wrong. The invite link may be invalid or expired.'}
              </p>
            )}

            <button
              type="submit"
              disabled={mutation.isPending}
              className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
            >
              {mutation.isPending ? 'Creating account…' : 'Create account'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
