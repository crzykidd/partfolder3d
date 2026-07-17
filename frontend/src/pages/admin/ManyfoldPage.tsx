/**
 * ManyfoldPage — admin CRUD for Manyfold instance configuration.
 *
 * Route: /admin/ai/manyfold
 *
 * Manyfold (https://manyfold.app) is a self-hosted 3D-model organizer with an
 * OAuth2 (client_credentials) API. An admin can register one or more
 * instances by base URL, pasting an OAuth client ID + client secret created
 * on that instance. Once registered and enabled, importing from a matching
 * domain pulls the model straight from Manyfold's API (metadata, tags,
 * images, files) instead of scraping the page — see the import wizard.
 *
 * `client_secret` is Fernet-encrypted server-side and never returned by any
 * endpoint — `has_secret` tells the UI whether one is stored. The secret
 * input is write-only, mirroring AiProvidersPage's API-key pattern.
 *
 * UI patterns (no Radix Dialog, no toast library):
 *  - Inline add-form that expands in place (not a modal).
 *  - Inline edit row that expands below the row being edited.
 *  - Inline delete confirmation: first click shows Confirm / Cancel.
 *  - Transient feedback via inline status text (3 s timeout).
 *
 * Styling: Aurora aesthetic — same primitives as AiProvidersPage.tsx /
 * SiteCapabilitiesPage.tsx.
 */

import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import * as api from '@/lib/api'
import {
  AdminPage, PageHeader,
  Card, SectionHeader,
  Badge,
  Button,
  AuroraToggle,
  DataTable, TableRow, Td,
  Field, AuroraInput,
} from '@/components/ui'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatTs(ts: string | null): string {
  if (!ts) return 'Never'
  return new Date(ts).toLocaleString()
}

/** Where to create OAuth credentials on the target instance. */
function OAuthHint({ baseUrl }: { baseUrl: string }) {
  const trimmed = baseUrl.trim().replace(/\/+$/, '')
  const appsUrl = trimmed ? `${trimmed}/oauth/applications` : '<base_url>/oauth/applications'
  return (
    <p style={{ fontSize: 11, color: 'var(--aurora-muted)', margin: 0, lineHeight: 1.5 }}>
      Create the OAuth application on the Manyfold instance at{' '}
      <code style={{ fontSize: 11 }}>{appsUrl}</code> — grant type{' '}
      <strong>client-credentials</strong>, scopes <strong>public read</strong>.
    </p>
  )
}

// ---------------------------------------------------------------------------
// Inline status feedback
// ---------------------------------------------------------------------------

function TestStatus({ result }: { result: api.ManyfoldTestConnectionResult | null }) {
  if (!result) return null
  return (
    <p style={{ fontSize: 12, color: result.ok ? '#16A34A' : 'var(--aurora-danger)', margin: 0 }}>
      {result.ok
        ? `✓ Connection OK${result.scope ? ` (scope: ${result.scope})` : ''}`
        : `✗ ${result.message ?? 'Connection failed'}`}
    </p>
  )
}

// ---------------------------------------------------------------------------
// Add instance form (inline, not a dialog)
// ---------------------------------------------------------------------------

function AddInstanceForm({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient()
  const [baseUrl, setBaseUrl] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [clientId, setClientId] = useState('')
  const [clientSecret, setClientSecret] = useState('')
  const [scopes, setScopes] = useState('public read')
  const [enabled, setEnabled] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const createMutation = useMutation({
    mutationFn: () =>
      api.createManyfoldInstance({
        base_url: baseUrl.trim(),
        display_name: displayName.trim() || null,
        client_id: clientId.trim(),
        client_secret: clientSecret,
        scopes: scopes.trim() || 'public read',
        enabled,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['manyfold-instances'] })
      onClose()
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : 'Failed to create instance.'),
  })

  const canSubmit = baseUrl.trim() && clientId.trim() && clientSecret.trim()

  return (
    <Card>
      <SectionHeader>Add Manyfold Instance</SectionHeader>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <Field label="Base URL">
          <AuroraInput
            type="text"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="https://manyfold.example.com"
          />
        </Field>

        <Field label="Display name" hint="Optional — defaults to the domain.">
          <AuroraInput
            type="text"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder="My Manyfold"
          />
        </Field>

        <Field label="Client ID">
          <AuroraInput
            type="text"
            value={clientId}
            onChange={(e) => setClientId(e.target.value)}
            placeholder="OAuth client_id"
          />
        </Field>

        <Field label="Client Secret">
          <AuroraInput
            type="password"
            value={clientSecret}
            onChange={(e) => setClientSecret(e.target.value)}
            placeholder="Write-only; stored encrypted"
            autoComplete="new-password"
          />
        </Field>

        <Field label="Scopes">
          <AuroraInput
            type="text"
            value={scopes}
            onChange={(e) => setScopes(e.target.value)}
            placeholder="public read"
          />
        </Field>

        <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13, color: 'var(--aurora-text)' }}>
          <AuroraToggle
            checked={enabled}
            onChange={setEnabled}
            ariaLabel="Enable immediately"
          />
          Enable immediately
        </label>

        <OAuthHint baseUrl={baseUrl} />

        {error && <p style={{ fontSize: 12, color: 'var(--aurora-danger)', margin: 0 }}>{error}</p>}

        <div style={{ display: 'flex', gap: 8 }}>
          <Button
            size="sm"
            disabled={!canSubmit || createMutation.isPending}
            onClick={() => {
              setError(null)
              createMutation.mutate()
            }}
          >
            {createMutation.isPending ? 'Saving…' : 'Add Instance'}
          </Button>
          <Button variant="ghost" size="sm" onClick={onClose}>
            Cancel
          </Button>
        </div>
      </div>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Inline edit panel (rendered as extra row below the instance row)
// ---------------------------------------------------------------------------

interface EditPanelProps {
  instance: api.ManyfoldInstance
  onClose: () => void
}

function EditPanel({ instance, onClose }: EditPanelProps) {
  const queryClient = useQueryClient()
  const [baseUrl, setBaseUrl] = useState(instance.base_url)
  const [displayName, setDisplayName] = useState(instance.display_name ?? '')
  const [clientId, setClientId] = useState(instance.client_id)
  const [newSecret, setNewSecret] = useState('')
  const [scopes, setScopes] = useState(instance.scopes)
  const [error, setError] = useState<string | null>(null)

  const patchMutation = useMutation({
    mutationFn: (body: api.PatchManyfoldInstanceRequest) =>
      api.patchManyfoldInstance(instance.id, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['manyfold-instances'] })
      onClose()
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : 'Failed to update instance.'),
  })

  const handleSave = () => {
    setError(null)
    const body: api.PatchManyfoldInstanceRequest = {}
    const trimmedBaseUrl = baseUrl.trim()
    const trimmedDisplayName = displayName.trim()
    const trimmedClientId = clientId.trim()
    const trimmedScopes = scopes.trim()
    const trimmedSecret = newSecret.trim()
    if (trimmedBaseUrl !== instance.base_url) body.base_url = trimmedBaseUrl
    if (trimmedDisplayName !== (instance.display_name ?? '')) body.display_name = trimmedDisplayName || null
    if (trimmedClientId !== instance.client_id) body.client_id = trimmedClientId
    if (trimmedScopes !== instance.scopes) body.scopes = trimmedScopes
    if (trimmedSecret) body.client_secret = trimmedSecret
    patchMutation.mutate(body)
  }

  return (
    <tr style={{ borderTop: '1px solid var(--aurora-divider)', background: 'rgba(15,164,171,0.02)' }}>
      <td colSpan={6} style={{ padding: '16px 18px' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, maxWidth: 560 }}>
          <Field label="Base URL">
            <AuroraInput
              type="text"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
            />
          </Field>

          <Field label="Display name">
            <AuroraInput
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
            />
          </Field>

          <Field label="Client ID">
            <AuroraInput
              type="text"
              value={clientId}
              onChange={(e) => setClientId(e.target.value)}
            />
          </Field>

          <Field label={instance.has_secret ? 'Rotate Client Secret' : 'Client Secret'}>
            <AuroraInput
              type="password"
              value={newSecret}
              onChange={(e) => setNewSecret(e.target.value)}
              placeholder={
                instance.has_secret
                  ? '•••••••• (leave blank to keep current secret)'
                  : 'Enter secret — write-only; stored encrypted'
              }
              autoComplete="new-password"
            />
          </Field>

          <Field label="Scopes">
            <AuroraInput
              type="text"
              value={scopes}
              onChange={(e) => setScopes(e.target.value)}
            />
          </Field>

          <OAuthHint baseUrl={baseUrl} />

          {error && <p style={{ fontSize: 12, color: 'var(--aurora-danger)', margin: 0 }}>{error}</p>}

          <div style={{ display: 'flex', gap: 8 }}>
            <Button
              size="sm"
              disabled={patchMutation.isPending}
              onClick={handleSave}
            >
              {patchMutation.isPending ? 'Saving…' : 'Save changes'}
            </Button>
            <Button variant="ghost" size="sm" onClick={onClose}>
              Cancel
            </Button>
          </div>
        </div>
      </td>
    </tr>
  )
}

// ---------------------------------------------------------------------------
// Instance table row
// ---------------------------------------------------------------------------

function InstanceRow({ instance }: { instance: api.ManyfoldInstance }) {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [testResult, setTestResult] = useState<api.ManyfoldTestConnectionResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const enableMutation = useMutation({
    mutationFn: (enabled: boolean) => api.patchManyfoldInstance(instance.id, { enabled }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['manyfold-instances'] }),
    onError: (err) =>
      setError(err instanceof Error ? err.message : 'Failed to toggle enable.'),
  })

  const deleteMutation = useMutation({
    mutationFn: () => api.deleteManyfoldInstance(instance.id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['manyfold-instances'] }),
    onError: (err) =>
      setError(err instanceof Error ? err.message : 'Failed to delete.'),
  })

  const testMutation = useMutation({
    mutationFn: () => api.testManyfoldConnection(instance.id),
    onSuccess: (result) => {
      setTestResult(result)
      if (result.ok) {
        void queryClient.invalidateQueries({ queryKey: ['manyfold-instances'] })
      }
    },
    onError: (err) =>
      setTestResult({ ok: false, message: err instanceof Error ? err.message : 'Test failed.' }),
  })

  return (
    <>
      <TableRow style={{ verticalAlign: 'top' }}>
        <Td>
          <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--aurora-text)' }}>
            {instance.display_name ?? instance.domain}
          </div>
          <div style={{ fontSize: 11, color: 'var(--aurora-muted)' }}>{instance.base_url}</div>
        </Td>
        <Td style={{ fontFamily: 'monospace', fontSize: 12 }}>{instance.client_id}</Td>
        <Td>
          <Badge variant={instance.has_secret ? 'success' : 'muted'}>
            {instance.has_secret ? 'Secret set' : 'No secret'}
          </Badge>
        </Td>
        <Td>
          <AuroraToggle
            checked={instance.enabled}
            onChange={(v) => {
              setError(null)
              enableMutation.mutate(v)
            }}
            disabled={enableMutation.isPending}
            ariaLabel={instance.enabled ? 'Disable instance' : 'Enable instance'}
          />
        </Td>
        <Td style={{ fontSize: 11, color: 'var(--aurora-muted)', whiteSpace: 'nowrap' }}>
          {formatTs(instance.last_connected_at)}
        </Td>
        <Td>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setEditing((v) => !v)
                  setError(null)
                }}
              >
                {editing ? 'Collapse' : 'Edit'}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                disabled={testMutation.isPending}
                onClick={() => {
                  setTestResult(null)
                  setError(null)
                  testMutation.mutate()
                }}
              >
                {testMutation.isPending ? 'Testing…' : 'Test connection'}
              </Button>

              {confirmDelete ? (
                <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
                  <span style={{ color: 'var(--aurora-muted)' }}>Sure?</span>
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
                <Button variant="danger" size="sm" onClick={() => setConfirmDelete(true)}>
                  Delete
                </Button>
              )}
            </div>

            <TestStatus result={testResult} />
            {error && (
              <p style={{ fontSize: 11, color: 'var(--aurora-danger)', margin: 0 }}>{error}</p>
            )}
          </div>
        </Td>
      </TableRow>

      {editing && <EditPanel instance={instance} onClose={() => setEditing(false)} />}
    </>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const COLUMNS = ['Instance', 'Client ID', 'Secret', 'Enabled', 'Last connected', 'Actions']

export function ManyfoldPage() {
  const [showAdd, setShowAdd] = useState(false)

  const { data: instances = [], isLoading, isError, error } = useQuery({
    queryKey: ['manyfold-instances'],
    queryFn: api.listManyfoldInstances,
  })

  return (
    <AdminPage>
      <PageHeader
        title="Manyfold"
        description="Register self-hosted Manyfold instances so importing from a matching URL pulls metadata, tags, images, and files straight from Manyfold's API instead of scraping the page. Client secrets are stored encrypted and never returned in responses."
        meta={isLoading ? undefined : `${instances.length} instance${instances.length === 1 ? '' : 's'}`}
        actions={
          !showAdd ? (
            <Button onClick={() => setShowAdd(true)}>
              <Plus size={14} />
              Add Instance
            </Button>
          ) : undefined
        }
      />

      {showAdd && <AddInstanceForm onClose={() => setShowAdd(false)} />}

      {isError && (
        <div style={{ fontSize: 12, color: 'var(--aurora-danger)' }}>
          {error instanceof Error ? error.message : 'Failed to load Manyfold instances.'}
        </div>
      )}

      <DataTable
        columns={COLUMNS}
        isLoading={isLoading}
        isEmpty={!isLoading && !isError && instances.length === 0}
        emptyMessage="No Manyfold instances configured. Add one to enable direct imports from that host."
      >
        {instances.map((inst) => (
          <InstanceRow key={inst.id} instance={inst} />
        ))}
      </DataTable>
    </AdminPage>
  )
}
