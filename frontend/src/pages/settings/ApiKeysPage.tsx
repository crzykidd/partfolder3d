/**
 * ApiKeysPage — per-user API key management.
 *
 * GET  /api/api-keys → list (label, last_used_at, revoke button)
 * POST /api/api-keys → create → show raw key in copy-to-clipboard modal (once)
 * DELETE /api/api-keys/{key_id} → revoke
 */

import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'

import * as api from '@/lib/api'

function KeyCreatedDialog({
  rawKey,
  label,
  onClose,
}: {
  rawKey: string
  label: string
  onClose: () => void
}) {
  const [copied, setCopied] = useState(false)

  const handleCopy = () => {
    navigator.clipboard.writeText(rawKey).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 px-4">
      <div className="bg-card border border-border rounded-lg shadow-xl w-full max-w-md p-6 flex flex-col gap-4">
        <h2 className="text-lg font-semibold">API key created</h2>
        <p className="text-sm text-muted-foreground">
          Your new key <strong>{label}</strong> is shown below.{' '}
          <strong>Copy it now</strong> — it will not be displayed again.
        </p>

        <div className="rounded-md bg-muted px-3 py-2 font-mono text-xs break-all select-all">
          {rawKey}
        </div>

        <div className="flex gap-3">
          <button
            onClick={handleCopy}
            className="flex-1 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            {copied ? 'Copied!' : 'Copy key'}
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

export function ApiKeysPage() {
  const queryClient = useQueryClient()
  const [newLabel, setNewLabel] = useState('')
  const [createdKey, setCreatedKey] = useState<{ key: string; label: string } | null>(null)

  const { data: keys = [], isLoading } = useQuery({
    queryKey: ['apiKeys'],
    queryFn: api.listApiKeys,
  })

  const createMutation = useMutation({
    mutationFn: () => api.createApiKey(newLabel.trim()),
    onSuccess: (data) => {
      setCreatedKey({ key: data.key, label: data.label })
      setNewLabel('')
      queryClient.invalidateQueries({ queryKey: ['apiKeys'] })
    },
  })

  const revokeMutation = useMutation({
    mutationFn: (id: number) => api.revokeApiKey(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['apiKeys'] })
    },
  })

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault()
    if (!newLabel.trim()) return
    createMutation.mutate()
  }

  // Only show active keys.
  const activeKeys = keys.filter((k) => k.is_active)

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold">API keys</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Manage your personal API keys for programmatic access. Each key is
          shown <strong>once</strong> at creation.
        </p>
      </div>

      {/* Create form */}
      <div className="rounded-lg border border-border bg-card p-4">
        <h2 className="text-sm font-semibold mb-3">Create new key</h2>
        <form onSubmit={handleCreate} className="flex gap-3">
          <input
            type="text"
            value={newLabel}
            onChange={(e) => setNewLabel(e.target.value)}
            placeholder="Label (e.g. Home Server)"
            className="input-base flex-1"
            required
          />
          <button
            type="submit"
            disabled={createMutation.isPending || !newLabel.trim()}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
          >
            {createMutation.isPending ? 'Creating…' : 'Create'}
          </button>
        </form>
        {createMutation.isError && (
          <p className="mt-2 text-sm text-destructive">
            {createMutation.error instanceof api.ApiError
              ? createMutation.error.message
              : 'Failed to create API key.'}
          </p>
        )}
      </div>

      {/* Keys list */}
      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50">
              <tr>
                {['Label', 'Last used', ''].map((h) => (
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
              {activeKeys.map((k) => (
                <tr
                  key={k.id}
                  className="border-t border-border hover:bg-muted/30 transition-colors"
                >
                  <td className="px-4 py-3 font-medium">{k.label}</td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {k.last_used_at
                      ? new Date(k.last_used_at).toLocaleString()
                      : 'Never'}
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => revokeMutation.mutate(k.id)}
                      disabled={revokeMutation.isPending}
                      className="text-xs text-destructive hover:underline disabled:opacity-50"
                    >
                      Revoke
                    </button>
                  </td>
                </tr>
              ))}
              {activeKeys.length === 0 && (
                <tr>
                  <td
                    colSpan={3}
                    className="px-4 py-8 text-center text-sm text-muted-foreground"
                  >
                    No active API keys. Create one above.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {createdKey && (
        <KeyCreatedDialog
          rawKey={createdKey.key}
          label={createdKey.label}
          onClose={() => setCreatedKey(null)}
        />
      )}
    </div>
  )
}
