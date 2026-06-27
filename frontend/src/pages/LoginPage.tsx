/**
 * LoginPage — email + password form → POST /api/auth/login.
 *
 * On success: redirects to the page the user came from, or /.
 * On 401: shows a friendly error; other errors bubble.
 */

import React, { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import * as api from '@/lib/api'

export function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const queryClient = useQueryClient()

  const from = (location.state as { from?: Location } | null)?.from?.pathname ?? '/'

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  const mutation = useMutation({
    mutationFn: () => api.login({ email, password }),
    onSuccess: () => {
      // Invalidate /me so AuthContext re-fetches the logged-in user.
      queryClient.invalidateQueries({ queryKey: ['me'] })
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
    <div className="min-h-screen bg-background flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-foreground">Sign in</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Enter your email and password to access PartFolder 3D.
          </p>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="rounded-lg border border-border bg-card p-6 shadow-sm flex flex-col gap-4">
            <div>
              <label className="block text-sm font-medium mb-1" htmlFor="email">
                Email
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="input-base w-full"
                placeholder="you@example.com"
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
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="input-base w-full"
                placeholder="••••••••"
                required
              />
            </div>

            {mutation.isError && (
              <p className="text-sm text-destructive">
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
              className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
            >
              {mutation.isPending ? 'Signing in…' : 'Sign in'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
