/**
 * PasswordResetPage — admin password-reset management.
 *
 * Create: email → POST /api/password-reset → copy raw reset URL (shown once).
 * Revoke: DELETE /api/password-reset/{reset_id} on active tokens.
 *
 * Note: the backend has no "list active tokens" endpoint in Phase 1.
 * We track created tokens in local state (per session) and allow revoking them.
 *
 * Styling: Aurora aesthetic (B3b restyle — visual pass, all behavior preserved).
 */

import React, { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
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

// ---------------------------------------------------------------------------
// Local reset record
// ---------------------------------------------------------------------------

interface LocalReset {
  id: number
  user_id: number
  expires_at: string
  email: string
  revoked: boolean
}

// ---------------------------------------------------------------------------
// Copy URL dialog (shown once)
// ---------------------------------------------------------------------------

function CopyUrlDialog({ token, onClose }: { token: string; onClose: () => void }) {
  const url = `${window.location.origin}/password-reset/${token}`
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
          Reset link created
        </h2>
        <p style={{ fontSize: 13, color: 'var(--aurora-muted)', margin: 0, lineHeight: 1.6 }}>
          Copy this link and send it to the user. It is shown{' '}
          <strong style={{ color: 'var(--aurora-text-dim)' }}>once only</strong> and expires in 24 hours.
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

const COLUMNS = ['Email', 'Expires', 'Status', '']

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
      setResets((prev) => prev.map((r) => (r.id === id ? { ...r, revoked: true } : r)))
    },
  })

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault()
    if (!email) return
    createMutation.mutate()
  }

  return (
    <AdminPage>
      <PageHeader
        title="Password Reset"
        description="Generate a one-time reset link for a user. Links expire after 24 hours."
      />

      {/* Create form */}
      <Card>
        <SectionHeader>Generate reset link</SectionHeader>
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
            {createMutation.isPending ? 'Creating…' : 'Generate'}
          </Button>
        </form>
        {createMutation.isError && (
          <p style={{ marginTop: 8, fontSize: 12, color: 'var(--aurora-danger)' }}>
            {createMutation.error instanceof api.ApiError
              ? createMutation.error.message
              : 'Failed to generate reset link.'}
          </p>
        )}
      </Card>

      {/* Session history */}
      {resets.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--aurora-muted)', textTransform: 'uppercase', letterSpacing: '0.07em' }}>
            Generated this session
          </div>
          <DataTable
            columns={COLUMNS}
            isEmpty={false}
          >
            {resets.map((r) => (
              <TableRow key={r.id}>
                <Td style={{ fontFamily: 'monospace', fontSize: 12 }}>{r.email}</Td>
                <Td style={{ fontSize: 12, color: 'var(--aurora-muted)' }}>
                  {new Date(r.expires_at).toLocaleString()}
                </Td>
                <Td>
                  <Badge variant={r.revoked ? 'danger' : 'warning'}>
                    {r.revoked ? 'Revoked' : 'Active'}
                  </Badge>
                </Td>
                <Td>
                  {!r.revoked && (
                    <Button
                      variant="danger"
                      size="sm"
                      disabled={revokeMutation.isPending}
                      onClick={() => revokeMutation.mutate(r.id)}
                    >
                      Revoke
                    </Button>
                  )}
                </Td>
              </TableRow>
            ))}
          </DataTable>
        </div>
      )}

      {pendingToken && (
        <CopyUrlDialog token={pendingToken} onClose={() => setPendingToken(null)} />
      )}
    </AdminPage>
  )
}
