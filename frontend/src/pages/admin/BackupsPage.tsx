/**
 * BackupsPage — admin backup management (Phase 9 — PRD §13).
 *
 * Route: /admin/backups
 *
 * IMPORTANT: These backups contain only the database and config (encryption
 * key). Library binary files (STL, images, etc.) are NOT backed up. A loud
 * warning callout makes this unavoidably clear.
 *
 * Features:
 *  - Prominent warning banner about what is/isn't backed up.
 *  - Table of backup records: filename, size, status, created_at,
 *    download link (status=ready only), delete with inline confirm.
 *  - "Run Backup Now" button → POST /api/admin/backups/run.
 *  - Retention count setting: inline form → PUT /api/admin/backups/settings.
 *
 * Styling: Aurora aesthetic (B3b restyle — visual pass, all behavior preserved).
 */

import React, { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, RefreshCw } from 'lucide-react'
import * as api from '@/lib/api'
import {
  AdminPage, PageHeader,
  Card, SectionHeader,
  Badge,
  Button,
  DataTable, TableRow, Td,
  AuroraInput,
} from '@/components/ui'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatBytes(bytes: number | null): string {
  if (bytes == null) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatTs(ts: string): string {
  return new Date(ts).toLocaleString()
}

function backupStatusVariant(status: string): 'success' | 'danger' | 'info' | 'muted' {
  switch (status) {
    case 'ready':   return 'success'
    case 'failed':  return 'danger'
    case 'running': return 'info'
    default:        return 'muted'
  }
}

// ---------------------------------------------------------------------------
// Retention settings form (inline, no modal)
// ---------------------------------------------------------------------------

function RetentionForm({ current }: { current: number }) {
  const queryClient = useQueryClient()
  const [value, setValue] = useState(String(current))
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  const mutation = useMutation({
    mutationFn: (n: number) => api.updateBackupSettings(n),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['backup-settings'] })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : 'Failed to update.'),
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    const n = parseInt(value, 10)
    if (isNaN(n) || n < 1) {
      setError('Must be a whole number ≥ 1.')
      return
    }
    mutation.mutate(n)
  }

  return (
    <form onSubmit={handleSubmit} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <span style={{ fontSize: 13, color: 'var(--aurora-muted)' }}>Keep last</span>
      <AuroraInput
        type="number"
        min={1}
        value={value}
        onChange={(e) => {
          setValue(e.target.value)
          setError(null)
          setSaved(false)
        }}
        style={{ width: 70 }}
      />
      <span style={{ fontSize: 13, color: 'var(--aurora-muted)' }}>backups</span>
      <Button variant="ghost" size="sm" type="submit" disabled={mutation.isPending}>
        {mutation.isPending ? 'Saving…' : 'Save'}
      </Button>
      {saved && <span style={{ fontSize: 12, color: '#16A34A' }}>Saved</span>}
      {error && <span style={{ fontSize: 12, color: 'var(--aurora-danger)' }}>{error}</span>}
    </form>
  )
}

// ---------------------------------------------------------------------------
// Backup row
// ---------------------------------------------------------------------------

function BackupRow({ record }: { record: api.BackupRecordOut }) {
  const queryClient = useQueryClient()
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const deleteMutation = useMutation({
    mutationFn: () => api.deleteBackup(record.id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['backups'] }),
    onError: (err) =>
      setDeleteError(err instanceof Error ? err.message : 'Delete failed.'),
  })

  return (
    <TableRow>
      <Td style={{ fontFamily: 'monospace', fontSize: 11, color: 'var(--aurora-muted)' }}>
        {record.filename}
      </Td>
      <Td style={{ color: 'var(--aurora-muted)' }}>{formatBytes(record.size_bytes)}</Td>
      <Td>
        <Badge variant={backupStatusVariant(record.status)}>{record.status}</Badge>
      </Td>
      <Td style={{ fontSize: 12, color: 'var(--aurora-muted)', whiteSpace: 'nowrap' }}>
        {formatTs(record.created_at)}
      </Td>
      <Td>
        {record.status === 'ready' ? (
          <a
            href={api.backupDownloadUrl(record.id)}
            download={record.filename}
            style={{ fontSize: 12, color: 'var(--aurora-accent)', textDecoration: 'underline' }}
          >
            Download
          </a>
        ) : (
          <span style={{ fontSize: 12, color: 'var(--aurora-muted)' }}>—</span>
        )}
      </Td>
      <Td>
        {record.error && (
          <p style={{ margin: '0 0 4px', fontSize: 11, color: 'var(--aurora-danger)', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={record.error}>
            {record.error}
          </p>
        )}
        {confirmDelete ? (
          <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 12, color: 'var(--aurora-muted)' }}>Sure?</span>
            <Button
              variant="danger"
              size="sm"
              disabled={deleteMutation.isPending}
              onClick={() => deleteMutation.mutate()}
            >
              {deleteMutation.isPending ? 'Deleting…' : 'Confirm'}
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setConfirmDelete(false)}>
              Cancel
            </Button>
          </span>
        ) : (
          <Button
            variant="danger"
            size="sm"
            onClick={() => {
              setDeleteError(null)
              setConfirmDelete(true)
            }}
          >
            Delete
          </Button>
        )}
        {deleteError && (
          <p style={{ marginTop: 4, fontSize: 11, color: 'var(--aurora-danger)' }}>{deleteError}</p>
        )}
      </Td>
    </TableRow>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const COLUMNS = ['Filename', 'Size', 'Status', 'Created', 'Download', 'Actions']

export function BackupsPage() {
  const queryClient = useQueryClient()
  const [runMessage, setRunMessage] = useState<string | null>(null)
  const [runError, setRunError] = useState<string | null>(null)

  const {
    data: backups = [],
    isLoading: backupsLoading,
    isError: backupsError,
    error: backupsErr,
  } = useQuery({
    queryKey: ['backups'],
    queryFn: api.listBackups,
    refetchInterval: 15_000,
  })

  const {
    data: settings,
    isLoading: settingsLoading,
  } = useQuery({
    queryKey: ['backup-settings'],
    queryFn: api.getBackupSettings,
  })

  const runMutation = useMutation({
    mutationFn: api.runBackupNow,
    onSuccess: (data) => {
      setRunMessage(data.message)
      setRunError(null)
      setTimeout(() => setRunMessage(null), 5000)
      void queryClient.invalidateQueries({ queryKey: ['backups'] })
    },
    onError: (err) => {
      setRunError(err instanceof Error ? err.message : 'Failed to enqueue backup.')
      setRunMessage(null)
    },
  })

  return (
    <AdminPage>
      <PageHeader
        title="Backups"
        description="Database and configuration backups. Use the download link to retrieve an archive; use the scheduled job to run backups on a schedule."
        meta={backupsLoading ? undefined : `${backups.length} backup${backups.length === 1 ? '' : 's'}`}
        actions={
          <Button
            disabled={runMutation.isPending}
            onClick={() => {
              setRunError(null)
              runMutation.mutate()
            }}
          >
            {runMutation.isPending ? 'Enqueueing…' : 'Run Backup Now'}
          </Button>
        }
      />

      {/* Run feedback */}
      {runMessage && (
        <div style={{ fontSize: 13, color: '#16A34A' }}>{runMessage}</div>
      )}
      {runError && (
        <div style={{ fontSize: 13, color: 'var(--aurora-danger)' }}>{runError}</div>
      )}

      {/* LOUD warning callout — keep prominent */}
      <div
        style={{
          background: 'rgba(245,158,11,0.08)',
          border: '2px solid rgba(245,158,11,0.5)',
          borderRadius: 12,
          padding: '16px 20px',
          display: 'flex',
          gap: 12,
          alignItems: 'flex-start',
        }}
      >
        <AlertTriangle size={18} style={{ color: '#D97706', flexShrink: 0, marginTop: 1 }} />
        <div>
          <p style={{ margin: '0 0 4px', fontSize: 14, fontWeight: 700, color: '#D97706' }}>
            Library files are NOT backed up.
          </p>
          <p style={{ margin: 0, fontSize: 13, color: '#92400E', lineHeight: 1.6 }}>
            These backups contain only the <strong>database</strong> and{' '}
            <strong>config (encryption key)</strong>. Your 3D model files,
            images, and other library files are <strong>not included</strong>.
            You are responsible for backing up your library files separately
            (e.g. via filesystem snapshots, cloud sync, or your own backup
            solution).
          </p>
        </div>
      </div>

      {/* Retention settings */}
      <Card>
        <SectionHeader>Retention</SectionHeader>
        {settingsLoading ? (
          <p style={{ fontSize: 13, color: 'var(--aurora-muted)', margin: 0 }}>Loading…</p>
        ) : settings ? (
          <RetentionForm current={settings.retention_count} />
        ) : null}
      </Card>

      {/* Backup list */}
      {backupsError && (
        <div style={{ fontSize: 12, color: 'var(--aurora-danger)' }}>
          {backupsErr instanceof Error ? backupsErr.message : 'Failed to load backups.'}
        </div>
      )}

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end' }}>
        <button
          type="button"
          onClick={() => void queryClient.invalidateQueries({ queryKey: ['backups'] })}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 5,
            fontSize: 12,
            color: 'var(--aurora-muted)',
            background: 'none',
            border: 'none',
            cursor: 'pointer',
          }}
        >
          <RefreshCw size={12} />
          Refresh
        </button>
      </div>

      <DataTable
        columns={COLUMNS}
        isLoading={backupsLoading}
        isEmpty={!backupsLoading && !backupsError && backups.length === 0}
        emptyMessage={'No backups yet. Click "Run Backup Now" or wait for the scheduled backup job to run.'}
      >
        {backups.map((b) => (
          <BackupRow key={b.id} record={b} />
        ))}
      </DataTable>
    </AdminPage>
  )
}
