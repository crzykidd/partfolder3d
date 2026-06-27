/**
 * InvitesPage — admin invite management.
 *
 * Create form: email → POST /api/invites → shows raw invite URL in a dialog (once).
 * History table: email, status, expires_at, created_at, revoke button.
 *
 * Note: the invite accept URL is /invites/{token}/accept (frontend route).
 */

import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'

import * as api from '@/lib/api'

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    pending: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200',
    accepted: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
    expired: 'bg-muted text-muted-foreground',
    revoked: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
  }
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
        colors[status] ?? 'bg-muted text-muted-foreground'
      }`}
    >
      {status}
    </span>
  )
}

function CopyUrlDialog({
  token,
  onClose,
}: {
  token: string
  onClose: () => void
}) {
  const url = `${window.location.origin}/invites/${token}/accept`
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
        <h2 className="text-lg font-semibold">Invite link created</h2>
        <p className="text-sm text-muted-foreground">
          Copy this link and send it to the invitee. It is shown{' '}
          <strong>once only</strong> and expires in 7 days.
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

export function InvitesPage() {
  const queryClient = useQueryClient()
  const [email, setEmail] = useState('')
  const [pendingToken, setPendingToken] = useState<string | null>(null)

  const { data: invites = [], isLoading } = useQuery({
    queryKey: ['invites'],
    queryFn: api.listInvites,
  })

  const createMutation = useMutation({
    mutationFn: () => api.createInvite(email),
    onSuccess: (data) => {
      if (data.token) setPendingToken(data.token)
      setEmail('')
      queryClient.invalidateQueries({ queryKey: ['invites'] })
    },
  })

  const revokeMutation = useMutation({
    mutationFn: (id: number) => api.revokeInvite(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['invites'] })
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
        <h1 className="text-2xl font-bold">Invites</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Generate invite links to onboard new users. Links expire after 7 days.
        </p>
      </div>

      {/* Create form */}
      <div className="rounded-lg border border-border bg-card p-4">
        <h2 className="text-sm font-semibold mb-3">Create invite</h2>
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
            {createMutation.isPending ? 'Creating…' : 'Create'}
          </button>
        </form>
        {createMutation.isError && (
          <p className="mt-2 text-sm text-destructive">
            {createMutation.error instanceof api.ApiError
              ? createMutation.error.message
              : 'Failed to create invite.'}
          </p>
        )}
      </div>

      {/* History table */}
      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50">
              <tr>
                {['Email', 'Status', 'Expires', 'Created', ''].map((h) => (
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
              {invites.map((inv) => (
                <tr
                  key={inv.id}
                  className="border-t border-border hover:bg-muted/30 transition-colors"
                >
                  <td className="px-4 py-3 font-mono">{inv.email}</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={inv.status} />
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {new Date(inv.expires_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {new Date(inv.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3">
                    {inv.status === 'pending' && (
                      <button
                        onClick={() => revokeMutation.mutate(inv.id)}
                        disabled={revokeMutation.isPending}
                        className="text-xs text-destructive hover:underline disabled:opacity-50"
                      >
                        Revoke
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {invites.length === 0 && (
                <tr>
                  <td
                    colSpan={5}
                    className="px-4 py-8 text-center text-sm text-muted-foreground"
                  >
                    No invites yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
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
