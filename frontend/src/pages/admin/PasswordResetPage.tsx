/**
 * PasswordResetPage — admin password-reset management.
 *
 * Create: email → POST /api/password-reset → copy raw reset URL (shown once).
 * Revoke: DELETE /api/password-reset/{reset_id} on active tokens.
 *
 * Note: the backend has no "list active tokens" endpoint in Phase 1.
 * We track created tokens in local state (per session) and allow revoking them.
 */

import React, { useState } from 'react'
import { useMutation } from '@tanstack/react-query'

import * as api from '@/lib/api'

interface LocalReset {
  id: number
  user_id: number
  expires_at: string
  email: string
  revoked: boolean
}

function CopyUrlDialog({
  token,
  onClose,
}: {
  token: string
  onClose: () => void
}) {
  const url = `${window.location.origin}/password-reset/${token}`
  const [copied, setCopied] = useState(false)

  const handleCopy = () => {
    navigator.clipboard.writeText(url).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 px-4">
      <div className="bg-card border border-border rounded-lg shadow-xl w-full max-w-md p-6 flex flex-col gap-4">
        <h2 className="text-lg font-semibold">Reset link created</h2>
        <p className="text-sm text-muted-foreground">
          Copy this link and send it to the user. It is shown{' '}
          <strong>once only</strong> and expires in 24 hours.
        </p>

        <div className="rounded-md bg-muted px-3 py-2 font-mono text-xs break-all select-all">
          {url}
        </div>

        <div className="flex gap-3">
          <button
            onClick={handleCopy}
            className="flex-1 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            {copied ? 'Copied!' : 'Copy link'}
          </button>
          <button
            onClick={onClose}
            className="flex-1 rounded-md border border-border bg-background px-4 py-2 text-sm font-medium hover:bg-accent transition-colors"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  )
}

export function PasswordResetPage() {
  const [email, setEmail] = useState('')
  const [pendingToken, setPendingToken] = useState<string | null>(null)
  const [resets, setResets] = useState<LocalReset[]>([])

  const createMutation = useMutation({
    mutationFn: () => api.createPasswordReset(email),
    onSuccess: (data) => {
      if (data.token) setPendingToken(data.token)
      setResets((prev) => [
        { id: data.id, user_id: data.user_id, expires_at: data.expires_at, email, revoked: false },
        ...prev,
      ])
      setEmail('')
    },
  })

  const revokeMutation = useMutation({
    mutationFn: (id: number) => api.revokePasswordReset(id),
    onSuccess: (_, id) => {
      setResets((prev) =>
        prev.map((r) => (r.id === id ? { ...r, revoked: true } : r)),
      )
    },
  })

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault()
    if (!email) return
    createMutation.mutate()
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold">Password reset</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Generate a one-time reset link for a user. Links expire after 24 hours.
        </p>
      </div>

      {/* Create form */}
      <div className="rounded-lg border border-border bg-card p-4">
        <h2 className="text-sm font-semibold mb-3">Generate reset link</h2>
        <form onSubmit={handleCreate} className="flex gap-3">
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="user@example.com"
            className="input-base flex-1"
            required
          />
          <button
            type="submit"
            disabled={createMutation.isPending}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
          >
            {createMutation.isPending ? 'Creating…' : 'Generate'}
          </button>
        </form>
        {createMutation.isError && (
          <p className="mt-2 text-sm text-destructive">
            {createMutation.error instanceof api.ApiError
              ? createMutation.error.message
              : 'Failed to generate reset link.'}
          </p>
        )}
      </div>

      {/* Session history */}
      {resets.length > 0 && (
        <div className="flex flex-col gap-2">
          <h2 className="text-sm font-semibold">Generated this session</h2>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr>
                  {['Email', 'Expires', 'Status', ''].map((h) => (
                    <th
                      key={h}
                      className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {resets.map((r) => (
                  <tr
                    key={r.id}
                    className="border-t border-border hover:bg-muted/30 transition-colors"
                  >
                    <td className="px-4 py-3 font-mono">{r.email}</td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {new Date(r.expires_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                          r.revoked
                            ? 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200'
                            : 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200'
                        }`}
                      >
                        {r.revoked ? 'Revoked' : 'Active'}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {!r.revoked && (
                        <button
                          onClick={() => revokeMutation.mutate(r.id)}
                          disabled={revokeMutation.isPending}
                          className="text-xs text-destructive hover:underline disabled:opacity-50"
                        >
                          Revoke
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {pendingToken && (
        <CopyUrlDialog
          token={pendingToken}
          onClose={() => setPendingToken(null)}
        />
      )}
    </div>
  )
}
