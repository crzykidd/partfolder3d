/**
 * SiteCapabilitiesPage — admin management of site scraping capabilities
 * (Phase 9 — PRD §13).
 *
 * Route: /admin/site-capabilities
 *
 * Shows all SiteCapability records with per-row actions:
 *  - Toggle is_manual_only (inline checkbox → PATCH).
 *  - Edit notes (inline text → PATCH on save).
 *  - Set Token (expand panel with token input → POST /{domain}/token).
 *  - Clear Token (DELETE /{domain}/token + confirm; shown when has_token=true).
 *  - Re-probe (POST /{domain}/reprobe).
 *  - Delete (DELETE /{domain} + inline confirm).
 *
 * Tokens are NEVER shown back (API never returns plaintext). Only has_token is shown.
 *
 * Styling: Aurora aesthetic (B3b restyle — visual pass, all behavior preserved).
 */

import React, { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as api from '@/lib/api'
import {
  AdminPage, PageHeader,
  Badge,
  Button,
  AuroraToggle,
  DataTable, TableRow, Td,
  AuroraInput,
} from '@/components/ui'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatTs(ts: string | null): string {
  if (!ts) return '—'
  return new Date(ts).toLocaleString()
}

// ---------------------------------------------------------------------------
// Token set panel (expanded below the row)
// ---------------------------------------------------------------------------

function SetTokenPanel({ domain, onClose }: { domain: string; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [token, setToken] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  const setMutation = useMutation({
    mutationFn: () => api.setAdminSiteToken(domain, token.trim()),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['admin-site-capabilities'] })
      setSaved(true)
      setToken('')
      setTimeout(() => {
        setSaved(false)
        onClose()
      }, 1500)
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : 'Failed to set token.'),
  })

  return (
    <tr style={{ borderTop: '1px solid var(--aurora-divider)', background: 'rgba(15,164,171,0.02)' }}>
      <td colSpan={8} style={{ padding: '16px 18px' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, maxWidth: 480 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--aurora-muted)', textTransform: 'uppercase', letterSpacing: '0.07em' }}>
              Set token for {domain}
            </span>
            <button
              type="button"
              onClick={onClose}
              style={{ fontSize: 12, color: 'var(--aurora-muted)', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}
            >
              Cancel
            </button>
          </div>
          <p style={{ fontSize: 12, color: 'var(--aurora-muted)', margin: 0, lineHeight: 1.5 }}>
            The token is stored encrypted server-side and never shown again.
            It is used for authenticated scraping of this domain.
          </p>
          <div style={{ display: 'flex', gap: 8 }}>
            <AuroraInput
              type="password"
              value={token}
              onChange={(e) => {
                setToken(e.target.value)
                setError(null)
              }}
              placeholder="Enter token (write-only; stored encrypted)"
              autoComplete="new-password"
              style={{ flex: 1 }}
            />
            <Button
              size="sm"
              disabled={setMutation.isPending || !token.trim()}
              onClick={() => setMutation.mutate()}
            >
              {setMutation.isPending ? 'Saving…' : 'Save token'}
            </Button>
          </div>
          {saved && <p style={{ fontSize: 12, color: '#16A34A', margin: 0 }}>Token saved.</p>}
          {error && <p style={{ fontSize: 12, color: 'var(--aurora-danger)', margin: 0 }}>{error}</p>}
        </div>
      </td>
    </tr>
  )
}

// ---------------------------------------------------------------------------
// Notes inline edit
// ---------------------------------------------------------------------------

function NotesCell({ domain, notes }: { domain: string; notes: string | null }) {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(notes ?? '')
  const [error, setError] = useState<string | null>(null)

  const patchMutation = useMutation({
    mutationFn: (newNotes: string | null) =>
      api.updateAdminSiteCapability(domain, { notes: newNotes }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['admin-site-capabilities'] })
      setEditing(false)
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : 'Failed to save notes.'),
  })

  if (editing) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, minWidth: 160 }}>
        <AuroraInput
          type="text"
          value={value}
          onChange={(e) => {
            setValue(e.target.value)
            setError(null)
          }}
          autoFocus
          style={{ fontSize: 12 }}
        />
        <div style={{ display: 'flex', gap: 4 }}>
          <Button
            size="sm"
            disabled={patchMutation.isPending}
            onClick={() => patchMutation.mutate(value.trim() || null)}
          >
            {patchMutation.isPending ? '…' : 'Save'}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setEditing(false)
              setValue(notes ?? '')
              setError(null)
            }}
          >
            Cancel
          </Button>
        </div>
        {error && <p style={{ fontSize: 11, color: 'var(--aurora-danger)', margin: 0 }}>{error}</p>}
      </div>
    )
  }

  return (
    <button
      type="button"
      onClick={() => {
        setEditing(true)
        setValue(notes ?? '')
      }}
      style={{
        fontSize: 13,
        color: 'var(--aurora-muted)',
        background: 'none',
        border: 'none',
        cursor: 'pointer',
        textAlign: 'left',
        maxWidth: 200,
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
      }}
      title={notes ?? 'Click to add notes'}
    >
      {notes ?? <span style={{ fontStyle: 'italic', opacity: 0.5 }}>—</span>}
    </button>
  )
}

// ---------------------------------------------------------------------------
// Site capability row
// ---------------------------------------------------------------------------

function SiteCapRow({ cap }: { cap: api.AdminSiteCapabilityOut }) {
  const queryClient = useQueryClient()
  const [showTokenForm, setShowTokenForm] = useState(false)
  const [confirmClearToken, setConfirmClearToken] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const patchMutation = useMutation({
    mutationFn: (body: api.AdminSiteCapabilityUpdate) =>
      api.updateAdminSiteCapability(cap.domain, body),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ['admin-site-capabilities'] }),
    onError: (err) =>
      setError(err instanceof Error ? err.message : 'Update failed.'),
  })

  const clearTokenMutation = useMutation({
    mutationFn: () => api.clearAdminSiteToken(cap.domain),
    onSuccess: () => {
      setConfirmClearToken(false)
      void queryClient.invalidateQueries({ queryKey: ['admin-site-capabilities'] })
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : 'Failed to clear token.'),
  })

  const reprobeMutation = useMutation({
    mutationFn: () => api.reprobeAdminSite(cap.domain),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ['admin-site-capabilities'] }),
    onError: (err) =>
      setError(err instanceof Error ? err.message : 'Re-probe failed.'),
  })

  const deleteMutation = useMutation({
    mutationFn: () => api.deleteAdminSiteCapability(cap.domain),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ['admin-site-capabilities'] }),
    onError: (err) =>
      setError(err instanceof Error ? err.message : 'Delete failed.'),
  })

  return (
    <>
      <TableRow style={{ verticalAlign: 'top' }}>
        {/* Domain */}
        <Td style={{ fontFamily: 'monospace', fontSize: 12, fontWeight: 600 }}>{cap.domain}</Td>

        {/* Booleans */}
        <Td>
          <Badge variant={cap.can_scrape_metadata ? 'success' : 'muted'}>
            {cap.can_scrape_metadata ? 'Yes' : 'No'}
          </Badge>
        </Td>
        <Td>
          <Badge variant={cap.can_scrape_images ? 'success' : 'muted'}>
            {cap.can_scrape_images ? 'Yes' : 'No'}
          </Badge>
        </Td>
        <Td>
          <Badge variant={cap.requires_token ? 'warning' : 'muted'}>
            {cap.requires_token ? 'Yes' : 'No'}
          </Badge>
        </Td>

        {/* is_manual_only — inline toggle */}
        <Td>
          <AuroraToggle
            checked={cap.is_manual_only}
            onChange={() => {
              setError(null)
              patchMutation.mutate({ is_manual_only: !cap.is_manual_only })
            }}
            disabled={patchMutation.isPending}
            ariaLabel={cap.is_manual_only ? 'Disable manual-only' : 'Enable manual-only'}
          />
        </Td>

        {/* Last probed */}
        <Td style={{ fontSize: 11, color: 'var(--aurora-muted)', whiteSpace: 'nowrap' }}>
          {formatTs(cap.last_probed_at)}
        </Td>

        {/* Notes */}
        <Td>
          <NotesCell domain={cap.domain} notes={cap.notes} />
        </Td>

        {/* Actions */}
        <Td>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {/* Token actions */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
              {cap.has_token && <Badge variant="success">Token set</Badge>}
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setShowTokenForm((v) => !v)
                  setError(null)
                }}
              >
                {cap.has_token ? 'Rotate token' : 'Set token'}
              </Button>
              {cap.has_token && (
                confirmClearToken ? (
                  <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12 }}>
                    <Button
                      variant="danger"
                      size="sm"
                      disabled={clearTokenMutation.isPending}
                      onClick={() => clearTokenMutation.mutate()}
                    >
                      {clearTokenMutation.isPending ? '…' : 'Confirm clear'}
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => setConfirmClearToken(false)}>
                      Cancel
                    </Button>
                  </span>
                ) : (
                  <Button
                    variant="ghost"
                    size="sm"
                    extraStyle={{ color: '#D97706', borderColor: 'rgba(217,119,6,0.3)', background: 'rgba(217,119,6,0.06)' }}
                    onClick={() => {
                      setConfirmClearToken(true)
                      setError(null)
                    }}
                  >
                    Clear token
                  </Button>
                )
              )}
            </div>

            {/* Re-probe */}
            <div>
              <Button
                variant="ghost"
                size="sm"
                disabled={reprobeMutation.isPending}
                onClick={() => {
                  setError(null)
                  reprobeMutation.mutate()
                }}
              >
                {reprobeMutation.isPending ? 'Re-probing…' : 'Re-probe'}
              </Button>
              {reprobeMutation.isSuccess && (
                <span style={{ marginLeft: 6, fontSize: 11, color: '#16A34A' }}>Probe reset.</span>
              )}
            </div>

            {/* Delete */}
            {confirmDelete ? (
              <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <Button
                  variant="danger"
                  size="sm"
                  disabled={deleteMutation.isPending}
                  onClick={() => deleteMutation.mutate()}
                >
                  {deleteMutation.isPending ? 'Deleting…' : 'Confirm delete'}
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
                  setConfirmDelete(true)
                  setError(null)
                }}
              >
                Delete
              </Button>
            )}

            {error && (
              <p style={{ fontSize: 11, color: 'var(--aurora-danger)', margin: 0 }}>{error}</p>
            )}
          </div>
        </Td>
      </TableRow>

      {showTokenForm && (
        <SetTokenPanel domain={cap.domain} onClose={() => setShowTokenForm(false)} />
      )}
    </>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const COLUMNS = ['Domain', 'Metadata', 'Images', 'Token req.', 'Manual only', 'Last probed', 'Notes', 'Actions']

export function SiteCapabilitiesPage() {
  const { data: caps = [], isLoading, isError, error } = useQuery({
    queryKey: ['admin-site-capabilities'],
    queryFn: api.listAdminSiteCapabilities,
  })

  return (
    <AdminPage>
      <PageHeader
        title="Site Capabilities"
        description="Per-domain scraping capabilities, authentication tokens, and manual-override settings used by the import wizard."
        meta={isLoading ? undefined : `${caps.length} domain${caps.length === 1 ? '' : 's'}`}
      />

      {isError && (
        <div style={{ fontSize: 12, color: 'var(--aurora-danger)' }}>
          {error instanceof Error ? error.message : 'Failed to load site capabilities.'}
        </div>
      )}

      <DataTable
        columns={COLUMNS}
        isLoading={isLoading}
        isEmpty={!isLoading && !isError && caps.length === 0}
        emptyMessage="No site capability records. Records are created automatically when the import wizard probes a new domain."
        style={{ overflowX: 'auto' }}
      >
        {caps.map((cap) => (
          <SiteCapRow key={cap.domain} cap={cap} />
        ))}
      </DataTable>
    </AdminPage>
  )
}
