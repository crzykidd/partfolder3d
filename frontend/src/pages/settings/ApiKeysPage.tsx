/**
 * ApiKeysPage — per-user API key management.
 *
 * GET  /api/api-keys → list (label, last_used_at, revoke button)
 * POST /api/api-keys → create → show raw key in copy-to-clipboard modal (once)
 * DELETE /api/api-keys/{key_id} → revoke
 *
 * Styling: Aurora aesthetic — AdminPage + Card + DataTable + Button primitives.
 */

import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Key, Copy, Check, Plus } from 'lucide-react'

import * as api from '@/lib/api'
import {
  AdminPage,
  PageHeader,
  Card,
  SectionHeader,
  Button,
  AuroraInput,
  DataTable,
  TableRow,
  Td,
  EmptyState,
} from '@/components/ui'

// ---------------------------------------------------------------------------
// "Key created" modal — copy-once dialog
// ---------------------------------------------------------------------------

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
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.55)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 50,
        padding: '16px',
      }}
    >
      <div
        style={{
          background: 'var(--aurora-card)',
          border: '1px solid var(--aurora-card-border)',
          borderRadius: 16,
          backdropFilter: 'blur(24px)',
          WebkitBackdropFilter: 'blur(24px)',
          padding: '28px 28px',
          width: '100%',
          maxWidth: 460,
          display: 'flex',
          flexDirection: 'column',
          gap: 18,
          boxShadow: '0 24px 64px rgba(0,0,0,0.22)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 36,
              height: 36,
              borderRadius: 10,
              background: 'rgba(15,164,171,0.12)',
              border: '1px solid rgba(15,164,171,0.25)',
            }}
          >
            <Key size={16} style={{ color: 'var(--aurora-accent)' }} />
          </div>
          <div>
            <h2 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: 'var(--aurora-text)' }}>
              API key created
            </h2>
            <p style={{ margin: 0, fontSize: 12, color: 'var(--aurora-muted)' }}>
              {label}
            </p>
          </div>
        </div>

        <p style={{ margin: 0, fontSize: 13, color: 'var(--aurora-text-dim)', lineHeight: 1.6 }}>
          <strong>Copy this key now</strong> — it will not be displayed again.
        </p>

        <div
          style={{
            background: 'var(--aurora-input-bg)',
            border: '1px solid var(--aurora-input-border)',
            borderRadius: 8,
            padding: '10px 12px',
            fontFamily: 'monospace',
            fontSize: 12,
            color: 'var(--aurora-text)',
            wordBreak: 'break-all',
            userSelect: 'all',
            lineHeight: 1.6,
          }}
        >
          {rawKey}
        </div>

        <div style={{ display: 'flex', gap: 10 }}>
          <Button
            variant="primary"
            size="md"
            onClick={handleCopy}
            style={{ flex: 1, justifyContent: 'center' }}
          >
            {copied ? <><Check size={14} /> Copied!</> : <><Copy size={14} /> Copy key</>}
          </Button>
          <Button
            variant="ghost"
            size="md"
            onClick={onClose}
            style={{ flex: 1, justifyContent: 'center' }}
          >
            Done
          </Button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// ApiKeysPage
// ---------------------------------------------------------------------------

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
    <AdminPage>
      <PageHeader
        title="API Keys"
        description="Manage your personal API keys for programmatic access. Each key is shown once at creation."
        meta={activeKeys.length > 0 ? `${activeKeys.length} active key${activeKeys.length === 1 ? '' : 's'}` : undefined}
      />

      {/* Create form */}
      <Card padding="18px 22px">
        <SectionHeader>Create new key</SectionHeader>
        <form onSubmit={handleCreate} style={{ display: 'flex', gap: 10 }}>
          <AuroraInput
            type="text"
            value={newLabel}
            onChange={(e) => setNewLabel(e.target.value)}
            placeholder="Label (e.g. Home Server)"
            style={{ flex: 1 }}
            required
          />
          <Button
            type="submit"
            variant="primary"
            size="md"
            disabled={createMutation.isPending || !newLabel.trim()}
          >
            <Plus size={14} />
            {createMutation.isPending ? 'Creating…' : 'Create'}
          </Button>
        </form>
        {createMutation.isError && (
          <p style={{ margin: '10px 0 0', fontSize: 13, color: 'var(--aurora-danger)' }}>
            {createMutation.error instanceof api.ApiError
              ? createMutation.error.message
              : 'Failed to create API key.'}
          </p>
        )}
      </Card>

      {/* Keys table */}
      <DataTable
        columns={['Label', 'Last used', '']}
        isLoading={isLoading}
        isEmpty={activeKeys.length === 0}
        emptyMessage="No active API keys. Create one above."
      >
        {activeKeys.map((k) => (
          <TableRow key={k.id}>
            <Td>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Key size={13} style={{ color: 'var(--aurora-muted)', flexShrink: 0 }} />
                <span style={{ fontWeight: 600 }}>{k.label}</span>
              </div>
            </Td>
            <Td style={{ color: 'var(--aurora-muted)' }}>
              {k.last_used_at
                ? new Date(k.last_used_at).toLocaleString()
                : 'Never'}
            </Td>
            <Td style={{ width: 80 }}>
              <Button
                variant="danger"
                size="sm"
                onClick={() => revokeMutation.mutate(k.id)}
                disabled={revokeMutation.isPending}
              >
                Revoke
              </Button>
            </Td>
          </TableRow>
        ))}
      </DataTable>

      {createdKey && (
        <KeyCreatedDialog
          rawKey={createdKey.key}
          label={createdKey.label}
          onClose={() => setCreatedKey(null)}
        />
      )}
    </AdminPage>
  )
}
