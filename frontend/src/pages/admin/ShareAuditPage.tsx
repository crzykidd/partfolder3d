/**
 * ShareAuditPage — admin view of full-site share links and their audit events.
 *
 * Lists all full-site share links (admin/shares/site).  Each link can be
 * expanded to view its audit event table (accessed_view, accessed_download,
 * created, revoked, expired).  Admin can revoke any active link.
 *
 * Route: /admin/shares  (admin only)
 * Styling: Aurora aesthetic (B3a restyle — visual pass, all behavior preserved).
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Copy, Check } from 'lucide-react'
import * as api from '@/lib/api'
import {
  AdminPage, PageHeader,
  Card,
  Badge,
  Button,
  DataTable, TableRow, Td,
  Field, AuroraInput,
} from '@/components/ui'

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

const AUDIT_COLS = ['Event', 'IP', 'User-Agent', 'Timestamp']

function AuditTable({ shareId }: { shareId: number }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['share-audit', shareId],
    queryFn: () => api.getShareAudit(shareId),
    staleTime: 30_000,
  })

  return (
    <DataTable
      columns={AUDIT_COLS}
      isLoading={isLoading}
      isEmpty={!isLoading && !isError && (!data || data.length === 0)}
      emptyMessage="No audit events yet."
      style={{ borderRadius: 0, border: 'none', borderTop: '1px solid var(--aurora-divider)' }}
    >
      {isError ? (
        <tr>
          <td
            colSpan={4}
            style={{ padding: '10px 14px', fontSize: 11, color: 'var(--aurora-danger)' }}
          >
            Failed to load audit events.
          </td>
        </tr>
      ) : (
        data?.map((evt) => (
          <TableRow key={evt.id}>
            <Td style={{ fontFamily: 'monospace', fontSize: 11 }}>{evt.event_type}</Td>
            <Td style={{ fontSize: 11, color: 'var(--aurora-muted)' }}>{evt.ip_address ?? '—'}</Td>
            <Td
              style={{ fontSize: 11, color: 'var(--aurora-muted)', maxWidth: 240, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
              title={evt.user_agent ?? undefined}
            >
              {evt.user_agent
                ? `${evt.user_agent.slice(0, 60)}${evt.user_agent.length > 60 ? '…' : ''}`
                : '—'}
            </Td>
            <Td style={{ fontSize: 11, color: 'var(--aurora-muted)', whiteSpace: 'nowrap' }}>
              {formatTs(evt.created_at)}
            </Td>
          </TableRow>
        ))
      )}
    </DataTable>
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
      <TableRow onClick={() => setExpanded((v) => !v)}>
        <Td style={{ fontFamily: 'monospace', fontSize: 11, color: 'var(--aurora-muted)' }}>
          {link.token.slice(0, 8)}…
        </Td>
        <Td style={{ fontSize: 12 }}>
          {link.label ?? <em style={{ color: 'var(--aurora-muted)' }}>No label</em>}
        </Td>
        <Td>
          {link.revoked ? (
            <Badge variant="danger">Revoked</Badge>
          ) : (
            <Badge variant="success">Active</Badge>
          )}
        </Td>
        <Td style={{ fontSize: 11, color: 'var(--aurora-muted)', whiteSpace: 'nowrap' }}>
          {formatExpiry(link.expires_at)}
        </Td>
        <Td style={{ fontSize: 11, color: 'var(--aurora-muted)', whiteSpace: 'nowrap' }}>
          {formatTs(link.created_at)}
        </Td>
        <Td onClick={(e) => e.stopPropagation()}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            {!link.revoked && (
              <Button variant="ghost" size="sm" onClick={handleCopy}>
                {copiedToken ? <Check size={11} /> : <Copy size={11} />}
                {copiedToken ? 'Copied' : 'Copy'}
              </Button>
            )}
            {!link.revoked && !confirmRevoke && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setConfirmRevoke(true)}
                extraStyle={{ color: 'var(--aurora-danger)', borderColor: 'rgba(239,68,68,0.3)' }}
              >
                Revoke
              </Button>
            )}
            {confirmRevoke && (
              <div style={{ display: 'flex', gap: 4 }}>
                <Button
                  variant="danger"
                  size="sm"
                  disabled={revokeMutation.isPending}
                  onClick={() => revokeMutation.mutate()}
                >
                  {revokeMutation.isPending ? '…' : 'Confirm'}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setConfirmRevoke(false)}
                >
                  Cancel
                </Button>
              </div>
            )}
          </div>
        </Td>
      </TableRow>

      {expanded && (
        <tr style={{ borderTop: '1px solid var(--aurora-divider)' }}>
          <td colSpan={6} style={{ padding: 0 }}>
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
      <Card>
        <p style={{ fontSize: 13, fontWeight: 600, color: '#16A34A', margin: '0 0 12px' }}>
          Share link created!{' '}
          {copiedToken ? 'Copied to clipboard.' : 'Copy the URL from the table.'}
        </p>
        <Button variant="ghost" size="sm" onClick={onClose}>Done</Button>
      </Card>
    )
  }

  return (
    <Card>
      <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--aurora-text)', marginBottom: 16 }}>
        New full-site share link
      </div>
      <div className="grid grid-cols-2 gap-4">
        <Field label="Label (optional)">
          <AuroraInput
            type="text"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="e.g. Partner preview"
          />
        </Field>
        <Field label="Expires in (days)">
          <AuroraInput
            type="number"
            min="0"
            value={expiry}
            onChange={(e) => setExpiry(e.target.value)}
            placeholder="30 (blank = instance default)"
          />
        </Field>
      </div>
      {error && (
        <p style={{ fontSize: 12, color: 'var(--aurora-danger)', margin: '10px 0 0' }}>{error}</p>
      )}
      <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
        <Button
          variant="primary"
          size="md"
          disabled={mintMutation.isPending}
          onClick={() => mintMutation.mutate()}
        >
          {mintMutation.isPending ? 'Creating…' : 'Create'}
        </Button>
        <Button variant="ghost" size="md" onClick={onClose}>Cancel</Button>
      </div>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const COLUMNS = ['Token', 'Label', 'Status', 'Expiry', 'Created', 'Actions']

export function ShareAuditPage() {
  const [mintOpen, setMintOpen] = useState(false)

  const { data: links = [], isLoading, isError, error } = useQuery({
    queryKey: ['site-shares'],
    queryFn: api.listSiteShares,
    staleTime: 30_000,
  })

  return (
    <AdminPage>
      <PageHeader
        title="Site Shares"
        description="Full-site share links give unauthenticated visitors read-only access to the entire catalog. Click a row to expand audit events."
        actions={
          <Button
            variant="primary"
            size="md"
            onClick={() => setMintOpen(true)}
          >
            <Plus size={14} />
            New site share
          </Button>
        }
      />

      {mintOpen && <MintSiteShareForm onClose={() => setMintOpen(false)} />}

      {isError && (
        <p style={{ fontSize: 12, color: 'var(--aurora-danger)' }}>
          {error instanceof Error ? error.message : 'Failed to load site shares.'}
        </p>
      )}

      <DataTable
        columns={COLUMNS}
        isLoading={isLoading}
        isEmpty={!isLoading && links.length === 0}
        emptyMessage="No site share links yet."
      >
        {links.map((link) => (
          <ShareLinkRow key={link.id} link={link} />
        ))}
      </DataTable>
    </AdminPage>
  )
}
