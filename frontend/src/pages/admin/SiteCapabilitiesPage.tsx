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
 * UI: Tailwind + CSS-variable theme + TanStack Query + apiFetch CSRF wrapper.
 * No Mantine, no toast library, no new deps.
 */

import React, { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as api from '@/lib/api'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatTs(ts: string | null): string {
  if (!ts) return '—'
  return new Date(ts).toLocaleString()
}

function BoolBadge({ value }: { value: boolean }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
        value
          ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
          : 'bg-muted text-muted-foreground'
      }`}
    >
      {value ? 'Yes' : 'No'}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Token set panel (expanded below the row)
// ---------------------------------------------------------------------------

function SetTokenPanel({
  domain,
  onClose,
}: {
  domain: string
  onClose: () => void
}) {
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
    <tr className="border-b border-border bg-muted/10">
      <td colSpan={8} className="px-4 py-4">
        <div className="space-y-3 max-w-md">
          <div className="flex items-center justify-between">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Set token for {domain}
            </h4>
            <button
              type="button"
              onClick={onClose}
              className="text-xs text-muted-foreground hover:text-foreground underline"
            >
              Cancel
            </button>
          </div>
          <p className="text-xs text-muted-foreground">
            The token is stored encrypted server-side and never shown again.
            It is used for authenticated scraping of this domain.
          </p>
          <div className="flex gap-2">
            <input
              type="password"
              value={token}
              onChange={(e) => {
                setToken(e.target.value)
                setError(null)
              }}
              placeholder="Enter token (write-only; stored encrypted)"
              autoComplete="new-password"
              className="input-base flex-1 text-sm"
            />
            <button
              type="button"
              disabled={setMutation.isPending || !token.trim()}
              onClick={() => setMutation.mutate()}
              className="rounded-md bg-primary px-3 py-1.5 text-xs text-primary-foreground hover:opacity-90 disabled:opacity-50 transition-colors"
            >
              {setMutation.isPending ? 'Saving…' : 'Save token'}
            </button>
          </div>
          {saved && (
            <p className="text-xs text-green-600 dark:text-green-400">Token saved.</p>
          )}
          {error && (
            <p className="text-xs text-red-600 dark:text-red-400">{error}</p>
          )}
        </div>
      </td>
    </tr>
  )
}

// ---------------------------------------------------------------------------
// Notes inline edit
// ---------------------------------------------------------------------------

function NotesCell({
  domain,
  notes,
}: {
  domain: string
  notes: string | null
}) {
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
      <div className="flex flex-col gap-1 min-w-[160px]">
        <input
          type="text"
          value={value}
          onChange={(e) => {
            setValue(e.target.value)
            setError(null)
          }}
          className="input-base w-full text-xs"
          autoFocus
        />
        <div className="flex gap-1">
          <button
            type="button"
            disabled={patchMutation.isPending}
            onClick={() =>
              patchMutation.mutate(value.trim() || null)
            }
            className="rounded px-2 py-0.5 text-xs bg-primary text-primary-foreground hover:opacity-90 disabled:opacity-50"
          >
            {patchMutation.isPending ? '…' : 'Save'}
          </button>
          <button
            type="button"
            onClick={() => {
              setEditing(false)
              setValue(notes ?? '')
              setError(null)
            }}
            className="rounded px-2 py-0.5 text-xs border border-border hover:bg-accent"
          >
            Cancel
          </button>
        </div>
        {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
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
      className="text-sm text-muted-foreground hover:text-foreground text-left max-w-[200px] truncate"
      title={notes ?? 'Click to add notes'}
    >
      {notes ? (
        <span>{notes}</span>
      ) : (
        <span className="italic text-muted-foreground/60">—</span>
      )}
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
      <tr className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors align-top">
        {/* Domain */}
        <td className="px-4 py-3 font-mono text-xs font-medium">{cap.domain}</td>

        {/* Booleans */}
        <td className="px-4 py-3">
          <BoolBadge value={cap.can_scrape_metadata} />
        </td>
        <td className="px-4 py-3">
          <BoolBadge value={cap.can_scrape_images} />
        </td>
        <td className="px-4 py-3">
          <BoolBadge value={cap.requires_token} />
        </td>

        {/* is_manual_only — inline toggle */}
        <td className="px-4 py-3">
          <button
            type="button"
            disabled={patchMutation.isPending}
            onClick={() => {
              setError(null)
              patchMutation.mutate({ is_manual_only: !cap.is_manual_only })
            }}
            className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors focus-visible:outline-none disabled:opacity-50 ${
              cap.is_manual_only ? 'bg-primary' : 'bg-muted'
            }`}
            aria-label={cap.is_manual_only ? 'Disable manual-only' : 'Enable manual-only'}
            title={cap.is_manual_only ? 'Manual-only (click to disable)' : 'Not manual-only (click to enable)'}
          >
            <span
              className={`pointer-events-none inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform ${
                cap.is_manual_only ? 'translate-x-4' : 'translate-x-0.5'
              }`}
            />
          </button>
        </td>

        {/* Last probed */}
        <td className="px-4 py-3 text-xs text-muted-foreground">
          {formatTs(cap.last_probed_at)}
        </td>

        {/* Notes */}
        <td className="px-4 py-3">
          <NotesCell domain={cap.domain} notes={cap.notes} />
        </td>

        {/* Actions */}
        <td className="px-4 py-3">
          <div className="flex flex-col gap-1.5">
            {/* Token actions */}
            <div className="flex items-center gap-2 flex-wrap">
              {cap.has_token && (
                <span className="inline-flex items-center rounded-full bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200 px-2 py-0.5 text-xs font-medium">
                  Token set
                </span>
              )}
              <button
                type="button"
                onClick={() => {
                  setShowTokenForm((v) => !v)
                  setError(null)
                }}
                className="text-xs text-muted-foreground hover:text-foreground underline"
              >
                {cap.has_token ? 'Rotate token' : 'Set token'}
              </button>
              {cap.has_token && (
                confirmClearToken ? (
                  <span className="flex items-center gap-1 text-xs">
                    <button
                      type="button"
                      disabled={clearTokenMutation.isPending}
                      onClick={() => clearTokenMutation.mutate()}
                      className="text-red-600 hover:text-red-700 font-medium disabled:opacity-50"
                    >
                      {clearTokenMutation.isPending ? '…' : 'Confirm clear'}
                    </button>
                    <button
                      type="button"
                      onClick={() => setConfirmClearToken(false)}
                      className="text-muted-foreground hover:text-foreground"
                    >
                      Cancel
                    </button>
                  </span>
                ) : (
                  <button
                    type="button"
                    onClick={() => {
                      setConfirmClearToken(true)
                      setError(null)
                    }}
                    className="text-xs text-amber-600 hover:text-amber-700 underline"
                  >
                    Clear token
                  </button>
                )
              )}
            </div>

            {/* Re-probe */}
            <button
              type="button"
              disabled={reprobeMutation.isPending}
              onClick={() => {
                setError(null)
                reprobeMutation.mutate()
              }}
              className="text-xs text-muted-foreground hover:text-foreground underline text-left disabled:opacity-50"
            >
              {reprobeMutation.isPending ? 'Re-probing…' : 'Re-probe'}
            </button>

            {/* Delete */}
            {confirmDelete ? (
              <span className="flex items-center gap-1 text-xs">
                <button
                  type="button"
                  disabled={deleteMutation.isPending}
                  onClick={() => deleteMutation.mutate()}
                  className="text-red-600 hover:text-red-700 font-medium disabled:opacity-50"
                >
                  {deleteMutation.isPending ? 'Deleting…' : 'Confirm delete'}
                </button>
                <button
                  type="button"
                  onClick={() => setConfirmDelete(false)}
                  className="text-muted-foreground hover:text-foreground"
                >
                  Cancel
                </button>
              </span>
            ) : (
              <button
                type="button"
                onClick={() => {
                  setConfirmDelete(true)
                  setError(null)
                }}
                className="text-xs text-red-500 hover:text-red-700 underline text-left"
              >
                Delete
              </button>
            )}

            {error && (
              <p className="text-xs text-red-600 dark:text-red-400">{error}</p>
            )}
            {reprobeMutation.isSuccess && (
              <p className="text-xs text-green-600 dark:text-green-400">Probe reset.</p>
            )}
          </div>
        </td>
      </tr>

      {showTokenForm && (
        <SetTokenPanel
          domain={cap.domain}
          onClose={() => setShowTokenForm(false)}
        />
      )}
    </>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function SiteCapabilitiesPage() {
  const { data: caps = [], isLoading, isError, error } = useQuery({
    queryKey: ['admin-site-capabilities'],
    queryFn: api.listAdminSiteCapabilities,
  })

  return (
    <div className="space-y-5">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold">Site Capabilities</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Per-domain scraping capabilities, authentication tokens, and
          manual-override settings used by the import wizard.
        </p>
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {isError && (
        <p className="text-sm text-red-600 dark:text-red-400">
          {error instanceof Error ? error.message : 'Failed to load site capabilities.'}
        </p>
      )}

      {!isLoading && !isError && caps.length === 0 && (
        <div className="rounded-lg border border-dashed border-border py-16 text-center">
          <p className="text-muted-foreground">No site capability records.</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Records are created automatically when the import wizard probes a
            new domain.
          </p>
        </div>
      )}

      {caps.length > 0 && (
        <div className="overflow-x-auto overflow-hidden rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50">
              <tr>
                {[
                  'Domain',
                  'Metadata',
                  'Images',
                  'Token req.',
                  'Manual only',
                  'Last probed',
                  'Notes',
                  'Actions',
                ].map((h) => (
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
              {caps.map((cap) => (
                <SiteCapRow key={cap.domain} cap={cap} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
