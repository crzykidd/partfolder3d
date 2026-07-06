/**
 * SiteCapabilitiesPage — admin management of site scraping capabilities
 * (Phase 9 — PRD §13; extended in issue #23 with pluggable fallback scrapers).
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
 * Also shows a "Scrapers" section with collapsible, drag-reorderable per-backend
 * sections (AgentQL + FlareSolverr). Priority is set by dragging; each section
 * remembers its expand/collapse state in sessionStorage.
 *
 * Tokens are NEVER shown back (API never returns plaintext). Only has_token is shown.
 *
 * Styling: Aurora aesthetic (B3b restyle — visual pass, all behavior preserved).
 */

import React, { useState, useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { GripVertical, ChevronDown, ChevronRight } from 'lucide-react'
import * as api from '@/lib/api'
import {
  AdminPage, PageHeader,
  Card,
  Badge,
  Button,
  AuroraToggle,
  DataTable, TableRow, Td,
  AuroraInput,
  Field,
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
// Shared UsagePanel — per-provider call count + clear button
// ---------------------------------------------------------------------------

function UsagePanel({ provider }: { provider: string }) {
  const queryClient = useQueryClient()
  const [confirmClear, setConfirmClear] = useState(false)
  const [clearMsg, setClearMsg] = useState<string | null>(null)

  const { data: rows = [] } = useQuery({
    queryKey: ['admin-scrapers-usage', provider],
    queryFn: () => api.getAllScraperUsage(provider),
  })

  const row = rows.find((r) => r.provider === provider)
  const calls = row?.calls ?? 0
  const cost = row?.est_cost_usd ?? 0

  const clearMutation = useMutation({
    mutationFn: () => api.clearScraperUsage(provider),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['admin-scrapers-usage', provider] })
      setConfirmClear(false)
      setClearMsg('Usage cleared.')
      setTimeout(() => setClearMsg(null), 2500)
    },
  })

  return (
    <div
      style={{
        background: 'var(--aurora-glass)',
        border: '1px solid var(--aurora-glass-border)',
        borderRadius: 8,
        padding: '12px 14px',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
        <div>
          <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--aurora-muted)', textTransform: 'uppercase', letterSpacing: '0.07em' }}>
            Usage (all-time)
          </span>
          <p style={{ fontSize: 13, color: 'var(--aurora-text)', marginTop: 4, marginBottom: 0 }}>
            <strong>{calls}</strong> call{calls !== 1 ? 's' : ''}
            {' · '}~${cost.toFixed(4)} est.
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {clearMsg && <span style={{ fontSize: 11, color: '#16A34A' }}>{clearMsg}</span>}
          {confirmClear ? (
            <>
              <Button
                variant="danger"
                size="sm"
                disabled={clearMutation.isPending}
                onClick={() => clearMutation.mutate()}
              >
                {clearMutation.isPending ? '…' : 'Confirm clear'}
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setConfirmClear(false)}>
                Cancel
              </Button>
            </>
          ) : (
            <Button
              variant="ghost"
              size="sm"
              extraStyle={{ color: '#D97706', borderColor: 'rgba(217,119,6,0.3)', background: 'rgba(217,119,6,0.06)' }}
              onClick={() => setConfirmClear(true)}
            >
              Clear usage
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Reorder helper — pure function, exported for tests
// ---------------------------------------------------------------------------

/**
 * Reorder a list of scraper entries by moving the item at `fromIndex` to
 * `toIndex`, then reassign sequential priorities (1-based).
 */
export function reorderScrapers<T extends { priority: number }>(
  items: T[],
  fromIndex: number,
  toIndex: number,
): T[] {
  if (fromIndex === toIndex) return items.map((item, idx) => ({ ...item, priority: idx + 1 }))
  const result = [...items]
  const [moved] = result.splice(fromIndex, 1)
  result.splice(toIndex, 0, moved)
  return result.map((item, idx) => ({ ...item, priority: idx + 1 }))
}

// ---------------------------------------------------------------------------
// FlareSolverrBody — card body (wrapped by ScraperSection chrome)
// ---------------------------------------------------------------------------

function FlareSolverrBody() {
  const queryClient = useQueryClient()
  const [saveStatus, setSaveStatus] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null)

  const { data: settings, isLoading } = useQuery({
    queryKey: ['admin-flaresolverr-settings'],
    queryFn: api.getFlareSolverrSettings,
  })

  const [formEnabled, setFormEnabled] = useState<boolean | undefined>(undefined)
  const [formBaseUrl, setFormBaseUrl] = useState('')
  const [formTimeoutS, setFormTimeoutS] = useState('')

  React.useEffect(() => {
    if (settings && formEnabled === undefined) {
      setFormEnabled(settings.enabled)
      setFormBaseUrl(settings.base_url)
      setFormTimeoutS(String(settings.timeout_s))
    }
  }, [settings, formEnabled])

  const updateMutation = useMutation({
    mutationFn: (body: api.FlareSolverrSettingsUpdate) => api.updateFlareSolverrSettings(body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['admin-flaresolverr-settings'] })
      setSaveStatus('Saved.')
      setTimeout(() => setSaveStatus(null), 2500)
    },
    onError: (err) => setError(err instanceof Error ? err.message : 'Save failed.'),
  })

  const testMutation = useMutation({
    mutationFn: api.testFlareSolverrConnection,
    onSuccess: (result) => setTestResult(result),
    onError: (err) =>
      setTestResult({ ok: false, message: err instanceof Error ? err.message : 'Test failed.' }),
  })

  function handleSave() {
    setError(null)
    const body: api.FlareSolverrSettingsUpdate = {}
    if (formEnabled !== undefined) body.enabled = formEnabled
    body.base_url = formBaseUrl.trim()
    const t = parseInt(formTimeoutS, 10)
    if (!isNaN(t) && t > 0) body.timeout_s = t
    updateMutation.mutate(body)
  }

  const effectiveEnabled = formEnabled !== undefined ? formEnabled : (settings?.enabled ?? false)

  return (
    <>
      <p style={{ fontSize: 13, color: 'var(--aurora-text-dim)', marginBottom: 16, lineHeight: 1.6 }}>
        Free, self-hosted fallback for Cloudflare-gated sites. Runs a headless browser
        to solve challenges. Add the service to your{' '}
        <code style={{ fontSize: 12 }}>docker-compose.dev.yml</code> (already included
        in this release) and point this card at{' '}
        <code style={{ fontSize: 12 }}>http://flaresolverr:8191</code>. Off by default.
      </p>

      {isLoading ? (
        <p style={{ fontSize: 13, color: 'var(--aurora-muted)' }}>Loading…</p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Enable toggle */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <AuroraToggle
              checked={effectiveEnabled}
              onChange={() => {
                setFormEnabled(!effectiveEnabled)
                setError(null)
              }}
              disabled={updateMutation.isPending}
              ariaLabel="Enable FlareSolverr fallback"
            />
            <span style={{ fontSize: 13, color: 'var(--aurora-text)' }}>
              {effectiveEnabled ? 'Enabled' : 'Disabled'}
            </span>
            {settings && (
              <Badge variant={settings.enabled ? 'success' : 'muted'}>
                {settings.enabled ? 'Active' : 'Off'}
              </Badge>
            )}
          </div>

          {/* Base URL */}
          <Field label="Base URL">
            <AuroraInput
              type="text"
              value={formBaseUrl}
              onChange={(e) => {
                setFormBaseUrl(e.target.value)
                setError(null)
              }}
              placeholder="http://flaresolverr:8191"
            />
            <p style={{ fontSize: 11, color: 'var(--aurora-muted)', marginTop: 4 }}>
              Internal Docker service URL. Not exposed to the internet.
            </p>
          </Field>

          {/* Timeout */}
          <Field label="Solve timeout (seconds)">
            <AuroraInput
              type="number"
              value={formTimeoutS}
              onChange={(e) => setFormTimeoutS(e.target.value)}
              style={{ width: 100 }}
              min={5}
            />
            <p style={{ fontSize: 11, color: 'var(--aurora-muted)', marginTop: 4 }}>
              Default 60s. Increase if challenges time out.
            </p>
          </Field>

          {/* Usage */}
          <UsagePanel provider="flaresolverr" />

          {/* Test result */}
          {testResult && (
            <p style={{ fontSize: 12, color: testResult.ok ? '#16A34A' : 'var(--aurora-danger)', margin: 0 }}>
              {testResult.ok ? '✓' : '✗'} {testResult.message}
            </p>
          )}

          {/* Actions */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <Button onClick={handleSave} disabled={updateMutation.isPending}>
              {updateMutation.isPending ? 'Saving…' : 'Save settings'}
            </Button>
            <Button
              variant="ghost"
              disabled={testMutation.isPending}
              onClick={() => {
                setTestResult(null)
                testMutation.mutate()
              }}
            >
              {testMutation.isPending ? 'Testing…' : 'Test connection'}
            </Button>
            {saveStatus && <span style={{ fontSize: 12, color: '#16A34A' }}>{saveStatus}</span>}
            {error && <span style={{ fontSize: 12, color: 'var(--aurora-danger)' }}>{error}</span>}
          </div>
        </div>
      )}
    </>
  )
}

// ---------------------------------------------------------------------------
// AgentQLBody — card body (wrapped by ScraperSection chrome)
// ---------------------------------------------------------------------------

function AgentQLBody() {
  const queryClient = useQueryClient()
  const [apiKeyInput, setApiKeyInput] = useState('')
  const [saveStatus, setSaveStatus] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null)

  const { data: settings, isLoading: settingsLoading } = useQuery({
    queryKey: ['admin-agentql-settings'],
    queryFn: api.getAgentQLSettings,
  })

  const { data: usage, isLoading: usageLoading } = useQuery({
    queryKey: ['admin-scraper-usage'],
    queryFn: api.getScraperUsage,
  })

  const [formEnabled, setFormEnabled] = useState<boolean | undefined>(undefined)
  const [formAllowance, setFormAllowance] = useState<string>('')
  const [formBudgetMode, setFormBudgetMode] = useState<string>('')
  const [formCapUsd, setFormCapUsd] = useState<string>('')
  const [formPerCall, setFormPerCall] = useState<string>('')
  const [formTimeoutS, setFormTimeoutS] = useState<string>('')

  // Populate form from loaded settings (once)
  React.useEffect(() => {
    if (settings && formEnabled === undefined) {
      setFormEnabled(settings.enabled)
      setFormAllowance(String(settings.free_allowance))
      setFormBudgetMode(settings.budget_mode)
      setFormCapUsd(settings.monthly_cap_usd != null ? String(settings.monthly_cap_usd) : '')
      setFormPerCall(String(settings.per_call_usd))
      setFormTimeoutS(String(settings.timeout_s ?? 120))
    }
  }, [settings, formEnabled])

  const updateMutation = useMutation({
    mutationFn: (body: api.AgentQLSettingsUpdate) => api.updateAgentQLSettings(body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['admin-agentql-settings'] })
      void queryClient.invalidateQueries({ queryKey: ['admin-scraper-usage'] })
      setSaveStatus('Saved.')
      setApiKeyInput('')
      setTimeout(() => setSaveStatus(null), 2500)
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : 'Save failed.')
    },
  })

  const testMutation = useMutation({
    mutationFn: api.testAgentQLConnection,
    onSuccess: (result) => setTestResult(result),
    onError: (err) =>
      setTestResult({ ok: false, message: err instanceof Error ? err.message : 'Test failed.' }),
  })

  function handleSave() {
    setError(null)
    const body: api.AgentQLSettingsUpdate = {}
    if (formEnabled !== undefined) body.enabled = formEnabled
    if (apiKeyInput.trim()) body.api_key = apiKeyInput.trim()
    const allowNum = parseInt(formAllowance, 10)
    if (!isNaN(allowNum)) body.free_allowance = allowNum
    if (formBudgetMode) body.budget_mode = formBudgetMode
    if (formBudgetMode === 'cap' && formCapUsd.trim()) {
      const capNum = parseFloat(formCapUsd)
      if (!isNaN(capNum)) body.monthly_cap_usd = capNum
    }
    const perCallNum = parseFloat(formPerCall)
    if (!isNaN(perCallNum)) body.per_call_usd = perCallNum
    const t = parseInt(formTimeoutS, 10)
    if (!isNaN(t) && t >= 1) body.timeout_s = t
    updateMutation.mutate(body)
  }

  const effectiveEnabled = formEnabled !== undefined ? formEnabled : (settings?.enabled ?? false)
  const effectiveBudgetMode = formBudgetMode || settings?.budget_mode || 'free_only'

  return (
    <>
      <p style={{ fontSize: 13, color: 'var(--aurora-text-dim)', marginBottom: 16, lineHeight: 1.6 }}>
        Optional BYO-key fallback for Cloudflare-gated sites (e.g. MakerWorld). Invoked{' '}
        <strong>only when the built-in scraper is blocked.</strong> Bring your own key at{' '}
        <a
          href="https://agentql.com"
          target="_blank"
          rel="noopener noreferrer"
          style={{ color: 'var(--aurora-accent)' }}
        >
          agentql.com
        </a>. Off by default.
      </p>

      {settingsLoading ? (
        <p style={{ fontSize: 13, color: 'var(--aurora-muted)' }}>Loading…</p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Enable toggle */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <AuroraToggle
              checked={effectiveEnabled}
              onChange={() => {
                setFormEnabled(!effectiveEnabled)
                setError(null)
              }}
              disabled={updateMutation.isPending}
              ariaLabel="Enable AgentQL fallback"
            />
            <span style={{ fontSize: 13, color: 'var(--aurora-text)' }}>
              {effectiveEnabled ? 'Enabled' : 'Disabled'}
            </span>
            {settings && (
              <Badge variant={settings.enabled ? 'success' : 'muted'}>
                {settings.enabled ? 'Active' : 'Off'}
              </Badge>
            )}
          </div>

          {/* API Key (write-only) */}
          <Field label={`API Key ${settings?.has_key ? '(key set — paste to rotate)' : '(not set)'}`}>
            <AuroraInput
              type="password"
              value={apiKeyInput}
              onChange={(e) => {
                setApiKeyInput(e.target.value)
                setError(null)
              }}
              placeholder={settings?.has_key ? '••••••••••••••••••••' : 'Paste AgentQL API key'}
              autoComplete="new-password"
            />
            <p style={{ fontSize: 11, color: 'var(--aurora-muted)', marginTop: 4 }}>
              Stored encrypted. Never returned. Leave blank to keep existing key.
            </p>
          </Field>

          {/* Timeout */}
          <Field label="Request timeout (seconds)">
            <AuroraInput
              type="number"
              value={formTimeoutS}
              onChange={(e) => setFormTimeoutS(e.target.value)}
              style={{ width: 100 }}
              min={10}
            />
            <p style={{ fontSize: 11, color: 'var(--aurora-muted)', marginTop: 4 }}>
              Default 120s (browser + proxy + challenge can take ~20s).
            </p>
          </Field>

          {/* Free allowance */}
          <Field label="Free allowance (calls / month)">
            <AuroraInput
              type="number"
              value={formAllowance}
              onChange={(e) => setFormAllowance(e.target.value)}
              style={{ width: 100 }}
              min={0}
            />
            <p style={{ fontSize: 11, color: 'var(--aurora-muted)', marginTop: 4 }}>
              Starter plan = 50 calls/month. Check your plan at agentql.com.
            </p>
          </Field>

          {/* Budget mode */}
          <Field label="Budget mode">
            <div style={{ display: 'flex', gap: 8 }}>
              {(['free_only', 'cap'] as const).map((mode) => (
                <Button
                  key={mode}
                  variant={effectiveBudgetMode === mode ? 'primary' : 'ghost'}
                  size="sm"
                  onClick={() => {
                    setFormBudgetMode(mode)
                    setError(null)
                  }}
                >
                  {mode === 'free_only' ? 'Free only' : 'Monthly $ cap'}
                </Button>
              ))}
            </div>
          </Field>

          {/* Monthly cap (shown only in cap mode) */}
          {effectiveBudgetMode === 'cap' && (
            <Field label="Monthly cap (USD)">
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ fontSize: 13, color: 'var(--aurora-text-dim)' }}>$</span>
                <AuroraInput
                  type="number"
                  value={formCapUsd}
                  onChange={(e) => setFormCapUsd(e.target.value)}
                  style={{ width: 100 }}
                  min={0}
                  step={0.01}
                />
              </div>
            </Field>
          )}

          {/* Per-call rate */}
          <Field label="Estimated cost per call (USD)">
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ fontSize: 13, color: 'var(--aurora-text-dim)' }}>$</span>
              <AuroraInput
                type="number"
                value={formPerCall}
                onChange={(e) => setFormPerCall(e.target.value)}
                style={{ width: 100 }}
                min={0}
                step={0.001}
              />
            </div>
            <p style={{ fontSize: 11, color: 'var(--aurora-muted)', marginTop: 4 }}>
              Default $0.02 (AgentQL Starter rate). Used for local budget tracking only.
            </p>
          </Field>

          {/* Usage display (AgentQL billing window) */}
          <div
            style={{
              background: 'var(--aurora-glass)',
              border: '1px solid var(--aurora-glass-border)',
              borderRadius: 8,
              padding: '12px 14px',
            }}
          >
            <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--aurora-muted)', textTransform: 'uppercase', letterSpacing: '0.07em' }}>
              This month's usage
            </span>
            {usageLoading ? (
              <p style={{ fontSize: 13, color: 'var(--aurora-muted)', marginTop: 6 }}>Loading…</p>
            ) : usage ? (
              <>
                <p style={{ fontSize: 13, color: 'var(--aurora-text)', marginTop: 6, marginBottom: 4 }}>
                  <strong>{usage.calls}</strong>
                  {usage.mode === 'free_only' ? ` / ${usage.allowance}` : ''} call{usage.calls !== 1 ? 's' : ''}
                  {' · '}~${usage.est_cost_usd.toFixed(2)} est.
                  {' · '}resets on the {usage.resets_on.split('-')[2] === '01' ? '1st' : usage.resets_on}
                </p>
                {usage.mode === 'cap' && usage.cap != null && (
                  <p style={{ fontSize: 12, color: 'var(--aurora-text-dim)', marginBottom: 4 }}>
                    Cap: ${usage.cap.toFixed(2)} / month
                  </p>
                )}
                <p style={{ fontSize: 11, color: 'var(--aurora-muted)', fontStyle: 'italic' }}>
                  AgentQL dashboard is authoritative for billing. This count is local.
                </p>
              </>
            ) : null}
          </div>

          {/* All-time usage with clear */}
          <UsagePanel provider="agentql" />

          {/* Test result */}
          {testResult && (
            <p style={{ fontSize: 12, color: testResult.ok ? '#16A34A' : 'var(--aurora-danger)', margin: 0 }}>
              {testResult.ok ? '✓' : '✗'} {testResult.message}
            </p>
          )}

          {/* Actions */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <Button
              onClick={handleSave}
              disabled={updateMutation.isPending}
            >
              {updateMutation.isPending ? 'Saving…' : 'Save settings'}
            </Button>
            <Button
              variant="ghost"
              disabled={testMutation.isPending}
              onClick={() => {
                setTestResult(null)
                testMutation.mutate()
              }}
            >
              {testMutation.isPending ? 'Testing…' : 'Test connection'}
            </Button>
            {saveStatus && (
              <span style={{ fontSize: 12, color: '#16A34A' }}>{saveStatus}</span>
            )}
            {error && (
              <span style={{ fontSize: 12, color: 'var(--aurora-danger)' }}>{error}</span>
            )}
          </div>
          <p style={{ fontSize: 11, color: 'var(--aurora-muted)', fontStyle: 'italic', margin: 0 }}>
            Test connection makes one real AgentQL API call (counts against your quota).
          </p>
        </div>
      )}
    </>
  )
}

// ---------------------------------------------------------------------------
// ScraperSection — collapsible section with drag handle for reordering
// ---------------------------------------------------------------------------

interface ScraperSectionProps {
  /** Unique key used for sessionStorage (e.g. 'flaresolverr') */
  name: string
  /** Display label shown in the collapsed header */
  label: string
  /** Current saved enabled state (undefined = still loading) */
  enabled: boolean | undefined
  /** True when another item is being dragged over this section (drop indicator) */
  isDragOver: boolean
  /** Fires when the user starts dragging from the header */
  onHeaderDragStart: (e: React.DragEvent) => void
  /** Fires when the drag ends (dropped or cancelled) */
  onHeaderDragEnd: () => void
  /** Fires when a dragged item is over this section */
  onDragOver: (e: React.DragEvent) => void
  /** Fires when a dragged item is dropped on this section */
  onDrop: (e: React.DragEvent) => void
  children: React.ReactNode
}

function ScraperSection({
  name,
  label,
  enabled,
  isDragOver,
  onHeaderDragStart,
  onHeaderDragEnd,
  onDragOver,
  onDrop,
  children,
}: ScraperSectionProps) {
  const storageKey = `pf3d.scrapers.expanded.${name}`

  // Default: expanded. Read from sessionStorage on first render.
  const [expanded, setExpanded] = useState<boolean>(() => {
    try {
      const raw = window.sessionStorage.getItem(storageKey)
      return raw !== null ? raw === 'true' : true
    } catch {
      return true
    }
  })

  function toggleExpanded() {
    const next = !expanded
    setExpanded(next)
    try {
      window.sessionStorage.setItem(storageKey, String(next))
    } catch {
      // Ignore (private browsing / storage unavailable)
    }
  }

  const enabledVariant = enabled === true ? 'success' : 'muted'
  const enabledText = enabled === undefined ? '—' : enabled ? 'Enabled' : 'Disabled'

  return (
    <div
      onDragOver={onDragOver}
      onDrop={onDrop}
      style={{
        marginBottom: 12,
        outline: isDragOver ? '2px solid var(--aurora-accent)' : '2px solid transparent',
        borderRadius: 14,
        transition: 'outline-color 0.12s',
      }}
    >
      <Card style={{ marginBottom: 0 }}>
        {/* ── Header row (draggable; clicking toggle button expands/collapses) ── */}
        <div
          draggable
          onDragStart={onHeaderDragStart}
          onDragEnd={onHeaderDragEnd}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            marginBottom: expanded ? 16 : 0,
            /* Prevent text selection during drag */
            userSelect: 'none',
          }}
        >
          {/* Drag handle */}
          <span
            aria-label="Drag to reorder"
            style={{
              display: 'flex',
              alignItems: 'center',
              color: 'var(--aurora-muted)',
              cursor: 'grab',
              flexShrink: 0,
            }}
          >
            <GripVertical size={16} />
          </span>

          {/* Expand/collapse toggle */}
          <button
            type="button"
            onClick={(e) => {
              // Stop propagation so clicking the button doesn't also trigger
              // a drag (though a click normally won't, this is a safety guard).
              e.stopPropagation()
              toggleExpanded()
            }}
            aria-expanded={expanded}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              flex: 1,
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              padding: 0,
              fontFamily: 'inherit',
              textAlign: 'left',
            }}
          >
            {expanded
              ? <ChevronDown size={14} style={{ color: 'var(--aurora-muted)', flexShrink: 0 }} />
              : <ChevronRight size={14} style={{ color: 'var(--aurora-muted)', flexShrink: 0 }} />
            }
            <span style={{ fontWeight: 600, fontSize: 14, color: 'var(--aurora-text)' }}>
              {label}
            </span>
            <Badge variant={enabledVariant}>{enabledText}</Badge>
          </button>
        </div>

        {/* ── Expanded body (not part of the draggable header) ── */}
        {expanded && (
          <div>
            {children}
          </div>
        )}
      </Card>
    </div>
  )
}

// ---------------------------------------------------------------------------
// ScrapersList — manages ordering, drag-to-reorder, and priority persistence
// ---------------------------------------------------------------------------

/** Lightweight entry used for ordering. Full settings live in each body's query. */
type ScraperOrderEntry = {
  name: string
  priority: number
}

function ScrapersList() {
  const queryClient = useQueryClient()

  const { data: fsSettings } = useQuery({
    queryKey: ['admin-flaresolverr-settings'],
    queryFn: api.getFlareSolverrSettings,
  })

  const { data: aqlSettings } = useQuery({
    queryKey: ['admin-agentql-settings'],
    queryFn: api.getAgentQLSettings,
  })

  // Ordered names — initialized from priorities once both queries load.
  // After that, only drag-and-drop updates this list (not query re-fetches).
  const [orderedNames, setOrderedNames] = useState<string[]>([])
  const [dragIndex, setDragIndex] = useState<number | null>(null)
  const [dropIndex, setDropIndex] = useState<number | null>(null)
  const [dropError, setDropError] = useState<string | null>(null)

  useEffect(() => {
    if (orderedNames.length === 0 && fsSettings && aqlSettings) {
      const entries: ScraperOrderEntry[] = [
        { name: 'flaresolverr', priority: fsSettings.priority },
        { name: 'agentql', priority: aqlSettings.priority },
      ]
      entries.sort((a, b) => a.priority - b.priority)
      setOrderedNames(entries.map((e) => e.name))
    }
  }, [orderedNames.length, fsSettings, aqlSettings])

  function getEnabled(name: string): boolean | undefined {
    if (name === 'flaresolverr') return fsSettings?.enabled
    if (name === 'agentql') return aqlSettings?.enabled
    return undefined
  }

  function getLabel(name: string): string {
    if (name === 'flaresolverr') return 'FlareSolverr (free, self-hosted)'
    if (name === 'agentql') return 'AgentQL Fallback'
    return name
  }

  function getBody(name: string): React.ReactNode {
    if (name === 'flaresolverr') return <FlareSolverrBody />
    if (name === 'agentql') return <AgentQLBody />
    return null
  }

  // ── Drag handlers ──────────────────────────────────────────────────────────

  function handleDragStart(e: React.DragEvent, index: number) {
    setDragIndex(index)
    setDropError(null)
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', String(index))
  }

  function handleDragEnd() {
    setDragIndex(null)
    setDropIndex(null)
  }

  function handleDragOver(e: React.DragEvent, index: number) {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    setDropIndex(index)
  }

  async function handleDrop(e: React.DragEvent, toIndex: number) {
    e.preventDefault()
    const from = dragIndex
    setDragIndex(null)
    setDropIndex(null)

    if (from === null || from === toIndex) return

    // Optimistic reorder
    const prevOrder = [...orderedNames]
    const newOrder = [...orderedNames]
    const [moved] = newOrder.splice(from, 1)
    newOrder.splice(toIndex, 0, moved)
    setOrderedNames(newOrder)

    try {
      // Persist: PUT priority = position (1-based) for each scraper
      await Promise.all(
        newOrder.map((name, idx) => {
          const priority = idx + 1
          if (name === 'flaresolverr') return api.updateFlareSolverrSettings({ priority })
          if (name === 'agentql') return api.updateAgentQLSettings({ priority })
          return Promise.resolve()
        }),
      )
      void queryClient.invalidateQueries({ queryKey: ['admin-flaresolverr-settings'] })
      void queryClient.invalidateQueries({ queryKey: ['admin-agentql-settings'] })
    } catch (err) {
      // Rollback on failure
      setOrderedNames(prevOrder)
      setDropError(err instanceof Error ? err.message : 'Failed to save priority order.')
    }
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  if (orderedNames.length === 0) {
    return <p style={{ fontSize: 13, color: 'var(--aurora-muted)' }}>Loading scrapers…</p>
  }

  return (
    <div>
      <p style={{ fontSize: 12, color: 'var(--aurora-muted)', marginBottom: 12, fontStyle: 'italic' }}>
        Drag to set fallback order — top is tried first.
      </p>
      {dropError && (
        <p style={{ fontSize: 12, color: 'var(--aurora-danger)', marginBottom: 8 }}>{dropError}</p>
      )}
      {orderedNames.map((name, index) => (
        <ScraperSection
          key={name}
          name={name}
          label={getLabel(name)}
          enabled={getEnabled(name)}
          isDragOver={dropIndex === index && dragIndex !== index}
          onHeaderDragStart={(e) => handleDragStart(e, index)}
          onHeaderDragEnd={handleDragEnd}
          onDragOver={(e) => handleDragOver(e, index)}
          onDrop={(e) => { void handleDrop(e, index) }}
        >
          {getBody(name)}
        </ScraperSection>
      ))}
    </div>
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

      {/* Scrapers section — collapsible per-backend sections, drag-to-reorder */}
      <div style={{ marginBottom: 8 }}>
        <p style={{ fontSize: 11, fontWeight: 700, color: 'var(--aurora-muted)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 16 }}>
          Fallback scrapers
          <span style={{ marginLeft: 8, fontWeight: 400, textTransform: 'none', fontSize: 12, letterSpacing: 0 }}>
            — tried in priority order when the primary scraper is blocked
          </span>
        </p>
        <ScrapersList />
      </div>

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
