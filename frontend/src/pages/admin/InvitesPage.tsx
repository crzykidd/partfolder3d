/**
 * InvitesPage — admin invite management.
 *
 * Create form: email → POST /api/invites → shows raw invite URL in a dialog (once).
 * History table: email, status, expires_at, created_at, revoke button.
 *
 * Note: the invite accept URL is /invites/{token}/accept (frontend route).
 *
 * Styling: Aurora aesthetic (B3b restyle — visual pass, all behavior preserved).
 */

import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Copy, Check } from 'lucide-react'
import * as api from '@/lib/api'
import {
  AdminPage, PageHeader,
  Card, SectionHeader,
  Badge,
  Button,
  DataTable, TableRow, Td,
  Field, AuroraInput,
  CARD_STYLE,
} from '@/components/ui'
import type { BadgeVariant } from '@/components/ui'

// ---------------------------------------------------------------------------
// Badge helper
// ---------------------------------------------------------------------------

function inviteStatusVariant(status: string): BadgeVariant {
  switch (status) {
    case 'pending':  return 'warning'
    case 'accepted': return 'success'
    case 'revoked':  return 'danger'
    default:         return 'muted'
  }
}

// ---------------------------------------------------------------------------
// Copy URL dialog (shown once after creation)
// ---------------------------------------------------------------------------

function CopyUrlDialog({ token, onClose }: { token: string; onClose: () => void }) {
  const url = `${window.location.origin}/invites/${token}/accept`
  const [copied, setCopied] = useState(false)

  const handleCopy = () => {
    navigator.clipboard.writeText(url).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.5)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 50,
        padding: '0 16px',
      }}
    >
      <div
        style={{
          ...CARD_STYLE,
          padding: '24px',
          maxWidth: 480,
          width: '100%',
          display: 'flex',
          flexDirection: 'column',
          gap: 16,
        }}
      >
        <h2 style={{ fontSize: 16, fontWeight: 700, color: 'var(--aurora-text)', margin: 0 }}>
          Invite link created
        </h2>
        <p style={{ fontSize: 13, color: 'var(--aurora-muted)', margin: 0, lineHeight: 1.6 }}>
          Copy this link and send it to the invitee. It is shown{' '}
          <strong style={{ color: 'var(--aurora-text-dim)' }}>once only</strong> and expires in 7 days.
        </p>

        <div
          style={{
            background: 'var(--aurora-glass)',
            border: '1px solid var(--aurora-glass-border)',
            borderRadius: 8,
            padding: '8px 12px',
            fontFamily: 'monospace',
            fontSize: 12,
            wordBreak: 'break-all',
            userSelect: 'all',
            color: 'var(--aurora-text)',
          }}
        >
          {url}
        </div>

        <div style={{ display: 'flex', gap: 10 }}>
          <Button onClick={handleCopy} extraStyle={{ flex: 1, justifyContent: 'center' }}>
            {copied ? <><Check size={14} /> Copied!</> : <><Copy size={14} /> Copy link</>}
          </Button>
          <Button variant="ghost" onClick={onClose} extraStyle={{ flex: 1, justifyContent: 'center' }}>
            Done
          </Button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const COLUMNS = ['Email', 'Status', 'Expires', 'Created', '']

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
      void queryClient.invalidateQueries({ queryKey: ['invites'] })
    },
  })

  const revokeMutation = useMutation({
    mutationFn: (id: number) => api.revokeInvite(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['invites'] }),
  })

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault()
    if (!email) return
    createMutation.mutate()
  }

  return (
    <AdminPage>
      <PageHeader
        title="Invites"
        description="Generate invite links to onboard new users. Links expire after 7 days."
        meta={isLoading ? undefined : `${invites.length} invite${invites.length === 1 ? '' : 's'}`}
      />

      {/* Create form */}
      <Card>
        <SectionHeader>Create invite</SectionHeader>
        <form onSubmit={handleCreate} style={{ display: 'flex', gap: 10, alignItems: 'flex-end' }}>
          <div style={{ flex: 1 }}>
            <Field label="Email">
              <AuroraInput
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="user@example.com"
                required
              />
            </Field>
          </div>
          <Button type="submit" disabled={createMutation.isPending} extraStyle={{ marginBottom: 4 }}>
            {createMutation.isPending ? 'Creating…' : 'Create'}
          </Button>
        </form>
        {createMutation.isError && (
          <p style={{ marginTop: 8, fontSize: 12, color: 'var(--aurora-danger)' }}>
            {createMutation.error instanceof api.ApiError
              ? createMutation.error.message
              : 'Failed to create invite.'}
          </p>
        )}
      </Card>

      {/* History table */}
      <DataTable
        columns={COLUMNS}
        isLoading={isLoading}
        isEmpty={!isLoading && invites.length === 0}
        emptyMessage="No invites yet."
      >
        {invites.map((inv) => (
          <TableRow key={inv.id}>
            <Td style={{ fontFamily: 'monospace', fontSize: 12 }}>{inv.email}</Td>
            <Td><Badge variant={inviteStatusVariant(inv.status)}>{inv.status}</Badge></Td>
            <Td style={{ fontSize: 12, color: 'var(--aurora-muted)' }}>
              {new Date(inv.expires_at).toLocaleDateString()}
            </Td>
            <Td style={{ fontSize: 12, color: 'var(--aurora-muted)' }}>
              {new Date(inv.created_at).toLocaleDateString()}
            </Td>
            <Td>
              {inv.status === 'pending' && (
                <Button
                  variant="danger"
                  size="sm"
                  disabled={revokeMutation.isPending}
                  onClick={() => revokeMutation.mutate(inv.id)}
                >
                  Revoke
                </Button>
              )}
            </Td>
          </TableRow>
        ))}
      </DataTable>

      {pendingToken && (
        <CopyUrlDialog token={pendingToken} onClose={() => setPendingToken(null)} />
      )}
    </AdminPage>
  )
}
