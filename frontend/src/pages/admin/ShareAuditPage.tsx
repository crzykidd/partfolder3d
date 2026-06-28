/**
 * ShareAuditPage — admin view of full-site share links and their audit events.
 *
 * Lists all full-site share links (admin/shares/site).  Each link can be
 * expanded to view its audit event table (accessed_view, accessed_download,
 * created, revoked, expired).  Admin can revoke any active link.
 *
 * Route: /admin/shares  (admin only)
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import * as api from '@/lib/api'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatTs(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString()
}

function formatExpiry(iso: string | null): string {
  if (!iso) return 'Never'
  const d = new Date(iso)
  const now = Date.now()
  if (d.getTime() < now) return 'Expired'
  const days = Math.ceil((d.getTime() - now) / (1000 * 60 * 60 * 24))
  return `${days}d remaining`
}

// ---------------------------------------------------------------------------
// Audit event table for a single link
// ---------------------------------------------------------------------------

function AuditTable({ shareId }: { shareId: number }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['share-audit', shareId],
    queryFn: () => api.getShareAudit(shareId),
    staleTime: 30_000,
  })

  if (isLoading) return <p className="text-xs text-muted-foreground p-3">Loading…</p>
  if (isError) return <p className="text-xs text-destructive p-3">Failed to load audit events.</p>
  if (!data || data.length === 0) {
    return <p className="text-xs text-muted-foreground p-3 italic">No audit events yet.</p>
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead className="bg-muted/30">
          <tr>
            <th className="py-1.5 px-3 text-left font-medium text-muted-foreground">Event</th>
            <th className="py-1.5 px-3 text-left font-medium text-muted-foreground">IP</th>
            <th className="py-1.5 px-3 text-left font-medium text-muted-foreground">User-Agent</th>
            <th className="py-1.5 px-3 text-left font-medium text-muted-foreground">Timestamp</th>
          </tr>
        </thead>
        <tbody>
          {data.map((evt) => (
            <tr key={evt.id} className="border-t border-border">
              <td className="py-1.5 px-3 font-mono">{evt.event_type}</td>
              <td className="py-1.5 px-3 text-muted-foreground">{evt.ip_address ?? '—'}</td>
              <td className="py-1.5 px-3 text-muted-foreground max-w-xs truncate" title={evt.user_agent ?? undefined}>
                {evt.user_agent ? `${evt.user_agent.slice(0, 60)}${evt.user_agent.length > 60 ? '…' : ''}` : '—'}
              </td>
              <td className="py-1.5 px-3 whitespace-nowrap text-muted-foreground">
                {formatTs(evt.created_at)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Share link row (expandable)
// ---------------------------------------------------------------------------

function ShareLinkRow({ link }: { link: api.ShareLink }) {
  const [expanded, setExpanded] = useState(false)
  const [confirmRevoke, setConfirmRevoke] = useState(false)
  const [copiedToken, setCopiedToken] = useState(false)
  const queryClient = useQueryClient()

  const revokeMutation = useMutation({
    mutationFn: () => api.revokeShare(link.id),
    onSuccess: () => {
      setConfirmRevoke(false)
      void queryClient.invalidateQueries({ queryKey: ['site-shares'] })
    },
  })

  async function handleCopy() {
    const url = `${window.location.origin}/share/${link.token}`
    try {
      await navigator.clipboard.writeText(url)
      setCopiedToken(true)
      setTimeout(() => setCopiedToken(false), 2000)
    } catch {
      // ignore
    }
  }

  return (
    <>
      <tr
        className="border-b border-border hover:bg-muted/40 cursor-pointer"
        onClick={() => setExpanded((v) => !v)}
      >
        <td className="py-2 px-3 font-mono text-xs text-muted-foreground">
          {link.token.slice(0, 8)}…
        </td>
        <td className="py-2 px-3 text-xs">
          {link.label ?? <em className="text-muted-foreground">No label</em>}
        </td>
        <td className="py-2 px-3 text-xs">
          {link.revoked ? (
            <span className="inline-flex items-center rounded-full bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300 px-2 py-0.5 text-xs font-medium">
              Revoked
            </span>
          ) : (
            <span className="inline-flex items-center rounded-full bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200 px-2 py-0.5 text-xs font-medium">
              Active
            </span>
          )}
        </td>
        <td className="py-2 px-3 text-xs text-muted-foreground whitespace-nowrap">
          {formatExpiry(link.expires_at)}
        </td>
        <td className="py-2 px-3 text-xs text-muted-foreground whitespace-nowrap">
          {formatTs(link.created_at)}
        </td>
        <td className="py-2 px-3" onClick={(e) => e.stopPropagation()}>
          <div className="flex items-center gap-1">
            {!link.revoked && (
              <button
                onClick={handleCopy}
                className="rounded px-2 py-1 text-xs border border-border hover:bg-accent transition-colors"
              >
                {copiedToken ? '✓ Copied' : 'Copy'}
              </button>
            )}
            {!link.revoked && !confirmRevoke && (
              <button
                onClick={() => setConfirmRevoke(true)}
                className="rounded px-2 py-1 text-xs text-muted-foreground hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950 transition-colors"
              >
                Revoke
              </button>
            )}
            {confirmRevoke && (
              <div className="flex gap-1">
                <button
                  onClick={() => revokeMutation.mutate()}
                  disabled={revokeMutation.isPending}
                  className="rounded px-2 py-1 text-xs bg-red-600 text-white hover:bg-red-700 disabled:opacity-50 transition-colors"
                >
                  {revokeMutation.isPending ? '…' : 'Confirm'}
                </button>
                <button
                  onClick={() => setConfirmRevoke(false)}
                  className="rounded px-2 py-1 text-xs text-muted-foreground hover:bg-muted transition-colors"
                >
                  Cancel
                </button>
              </div>
            )}
          </div>
        </td>
      </tr>
      {expanded && (
        <tr className="border-b border-border bg-muted/10">
          <td colSpan={6} className="py-1 px-0">
            <AuditTable shareId={link.id} />
          </td>
        </tr>
      )}
    </>
  )
}

// ---------------------------------------------------------------------------
// Mint site share form
// ---------------------------------------------------------------------------

function MintSiteShareForm({ onClose }: { onClose: () => void }) {
  const [label, setLabel] = useState('')
  const [expiry, setExpiry] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [copiedToken, setCopiedToken] = useState(false)
  const queryClient = useQueryClient()

  const mintMutation = useMutation({
    mutationFn: () =>
      api.mintSiteShare({
        label: label || null,
        expires_days: expiry ? Number(expiry) : null,
      }),
    onSuccess: async (link) => {
      void queryClient.invalidateQueries({ queryKey: ['site-shares'] })
      const url = `${window.location.origin}/share/${link.token}`
      try {
        await navigator.clipboard.writeText(url)
        setCopiedToken(true)
      } catch {
        // ignore
      }
    },
    onError: (e) => setError(e instanceof Error ? e.message : 'Failed to create.'),
  })

  if (mintMutation.isSuccess) {
    return (
      <div className="rounded-lg border border-border bg-muted/20 p-4 flex flex-col gap-3">
        <p className="text-sm font-medium text-green-700 dark:text-green-400">
          Share link created!{' '}
          {copiedToken ? 'Copied to clipboard.' : 'Copy the URL from the table.'}
        </p>
        <button
          onClick={onClose}
          className="self-start rounded-md border border-border px-3 py-1.5 text-xs hover:bg-accent transition-colors"
        >
          Done
        </button>
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-border bg-muted/20 p-4 flex flex-col gap-3">
      <h3 className="text-sm font-semibold">New full-site share link</h3>
      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-muted-foreground">Label (optional)</label>
          <input
            type="text"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="e.g. Partner preview"
            className="input-base py-1.5 text-sm"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-muted-foreground">Expires in (days)</label>
          <input
            type="number"
            min="0"
            value={expiry}
            onChange={(e) => setExpiry(e.target.value)}
            placeholder="30 (blank = instance default)"
            className="input-base py-1.5 text-sm"
          />
        </div>
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
      <div className="flex gap-2">
        <button
          onClick={() => mintMutation.mutate()}
          disabled={mintMutation.isPending}
          className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
        >
          {mintMutation.isPending ? 'Creating…' : 'Create'}
        </button>
        <button
          onClick={onClose}
          className="rounded-md border border-border px-3 py-1.5 text-xs hover:bg-accent transition-colors"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function ShareAuditPage() {
  const [mintOpen, setMintOpen] = useState(false)

  const { data: links = [], isLoading, isError, error } = useQuery({
    queryKey: ['site-shares'],
    queryFn: api.listSiteShares,
    staleTime: 30_000,
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Site Shares</h1>
        <button
          onClick={() => setMintOpen(true)}
          className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          + New site share
        </button>
      </div>

      <p className="text-sm text-muted-foreground">
        Full-site share links give unauthenticated visitors read-only access to the
        entire catalog. Click a row to expand audit events.
      </p>

      {mintOpen && <MintSiteShareForm onClose={() => setMintOpen(false)} />}

      {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {isError && (
        <p className="text-sm text-destructive">
          {error instanceof Error ? error.message : 'Failed to load site shares.'}
        </p>
      )}

      {!isLoading && links.length === 0 && (
        <p className="text-sm text-muted-foreground italic">No site share links yet.</p>
      )}

      {links.length > 0 && (
        <div className="rounded-lg border border-border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted/50">
              <tr>
                <th className="py-2 px-3 text-left font-medium text-muted-foreground text-xs">Token</th>
                <th className="py-2 px-3 text-left font-medium text-muted-foreground text-xs">Label</th>
                <th className="py-2 px-3 text-left font-medium text-muted-foreground text-xs">Status</th>
                <th className="py-2 px-3 text-left font-medium text-muted-foreground text-xs">Expiry</th>
                <th className="py-2 px-3 text-left font-medium text-muted-foreground text-xs">Created</th>
                <th className="py-2 px-3 text-left font-medium text-muted-foreground text-xs">Actions</th>
              </tr>
            </thead>
            <tbody>
              {links.map((link) => (
                <ShareLinkRow key={link.id} link={link} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
