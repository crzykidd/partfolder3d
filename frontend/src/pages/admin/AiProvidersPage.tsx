/**
 * AiProvidersPage — admin CRUD for AI provider configurations.
 *
 * Route: /admin/ai-providers
 *
 * Lets admins configure Claude, OpenAI, and Ollama providers used by the
 * import wizard for tag suggestions and description cleanup. API keys are
 * stored encrypted server-side and are never returned — `has_key` tells the
 * UI whether a key is set.
 *
 * UI patterns (no Radix Dialog, no toast library):
 *  - Inline add-form that expands in place (not a modal).
 *  - Inline edit row that expands below the row being edited.
 *  - Inline delete confirmation: first click shows Confirm / Cancel.
 *  - Transient feedback via inline status text (3 s timeout).
 *
 * Styling: Aurora aesthetic (B3b restyle — visual pass, all behavior preserved).
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
// Provider defaults
// ---------------------------------------------------------------------------

type ProviderType = 'claude' | 'openai' | 'ollama'

const PROVIDER_DEFAULTS: Record<
  ProviderType,
  { placeholderModel: string; needsEndpoint: boolean }
> = {
  claude: { placeholderModel: 'claude-opus-4-8', needsEndpoint: false },
  openai: { placeholderModel: 'gpt-4o-mini', needsEndpoint: false },
  ollama: { placeholderModel: 'llama3', needsEndpoint: true },
}

// ---------------------------------------------------------------------------
// Provider type selector buttons
// ---------------------------------------------------------------------------

function ProviderTypeSelector({
  value,
  onChange,
}: {
  value: ProviderType
  onChange: (p: ProviderType) => void
}) {
  return (
    <Field label="Provider type">
      <div style={{ display: 'flex', gap: 6 }}>
        {(['claude', 'openai', 'ollama'] as ProviderType[]).map((p) => (
          <Button
            key={p}
            variant={value === p ? 'primary' : 'ghost'}
            size="sm"
            onClick={() => onChange(p)}
          >
            {p === 'openai' ? 'OpenAI' : p.charAt(0).toUpperCase() + p.slice(1)}
          </Button>
        ))}
      </div>
    </Field>
  )
}

// ---------------------------------------------------------------------------
// Inline status feedback
// ---------------------------------------------------------------------------

function TestStatus({ status }: { status: string | null }) {
  if (!status) return null
  const ok = status.startsWith('✓')
  return (
    <p style={{ fontSize: 12, color: ok ? '#16A34A' : 'var(--aurora-danger)', margin: 0 }}>
      {status}
    </p>
  )
}

// ---------------------------------------------------------------------------
// Add provider form (inline, not a dialog)
// ---------------------------------------------------------------------------

function AddProviderForm({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient()
  const [provider, setProvider] = useState<ProviderType>('claude')
  const [model, setModel] = useState('')
  const [endpoint, setEndpoint] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [enabled, setEnabled] = useState(false)
  const [testStatus, setTestStatus] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const def = PROVIDER_DEFAULTS[provider]

  const createMutation = useMutation({
    mutationFn: () =>
      api.createAiProvider({
        provider,
        endpoint: endpoint.trim() || null,
        model: model.trim() || null,
        api_key: apiKey.trim() || null,
        enabled,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['ai-providers'] })
      onClose()
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : 'Failed to create provider.'),
  })

  const testMutation = useMutation({
    mutationFn: () =>
      api.testAiConnection({
        provider,
        endpoint: endpoint.trim() || null,
        model: model.trim() || null,
        api_key: apiKey.trim() || null,
      }),
    onSuccess: (result) => {
      setTestStatus(result.ok ? '✓ Connection OK' : `Error: ${result.error ?? 'Connection failed'}`)
      setTimeout(() => setTestStatus(null), 3000)
    },
    onError: (err) => {
      setTestStatus(`Error: ${err instanceof Error ? err.message : 'Test failed'}`)
      setTimeout(() => setTestStatus(null), 3000)
    },
  })

  return (
    <Card>
      <SectionHeader>Add AI Provider</SectionHeader>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <ProviderTypeSelector
          value={provider}
          onChange={(p) => {
            setProvider(p)
            setModel('')
            setEndpoint('')
          }}
        />

        <Field
          label="Model"
          hint={!def.needsEndpoint && !model ? `Leave blank to use default: ${def.placeholderModel}` : undefined}
        >
          <AuroraInput
            type="text"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder={def.placeholderModel}
          />
        </Field>

        {def.needsEndpoint && (
          <Field label="Endpoint URL">
            <AuroraInput
              type="text"
              value={endpoint}
              onChange={(e) => setEndpoint(e.target.value)}
              placeholder="http://localhost:11434/v1"
            />
          </Field>
        )}

        <Field label="API Key">
          <AuroraInput
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="Enter key — write-only; stored encrypted"
            autoComplete="new-password"
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

        <TestStatus status={testStatus} />
        {error && <p style={{ fontSize: 12, color: 'var(--aurora-danger)', margin: 0 }}>{error}</p>}

        <div style={{ display: 'flex', gap: 8 }}>
          <Button
            variant="ghost"
            size="sm"
            disabled={testMutation.isPending || createMutation.isPending}
            onClick={() => {
              setError(null)
              testMutation.mutate()
            }}
          >
            {testMutation.isPending ? 'Testing…' : 'Test connection'}
          </Button>
          <Button
            size="sm"
            disabled={createMutation.isPending || testMutation.isPending}
            onClick={() => {
              setError(null)
              createMutation.mutate()
            }}
          >
            {createMutation.isPending ? 'Saving…' : 'Add Provider'}
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
// Inline edit panel (rendered as extra row below the provider row)
// ---------------------------------------------------------------------------

interface EditPanelProps {
  provider: api.AiProviderOut
  onClose: () => void
}

function EditPanel({ provider, onClose }: EditPanelProps) {
  const queryClient = useQueryClient()
  const [model, setModel] = useState(provider.model ?? '')
  const [endpoint, setEndpoint] = useState(provider.endpoint ?? '')
  const [newKey, setNewKey] = useState('')
  const [testStatus, setTestStatus] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const isOllama = provider.provider === 'ollama'

  const patchMutation = useMutation({
    mutationFn: (body: api.PatchAiProviderRequest) => api.patchAiProvider(provider.id, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['ai-providers'] })
      onClose()
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : 'Failed to update.'),
  })

  const testMutation = useMutation({
    mutationFn: () =>
      api.testAiConnection({
        provider: provider.provider,
        endpoint: endpoint.trim() || null,
        model: model.trim() || null,
        api_key: newKey.trim() || null,
        // No new key typed → test the saved provider using its stored key.
        provider_id: provider.id,
      }),
    onSuccess: (result) => {
      setTestStatus(result.ok ? '✓ Connection OK' : `Error: ${result.error ?? 'Connection failed'}`)
      setTimeout(() => setTestStatus(null), 3000)
    },
    onError: (err) => {
      setTestStatus(`Error: ${err instanceof Error ? err.message : 'Test failed'}`)
      setTimeout(() => setTestStatus(null), 3000)
    },
  })

  const handleSave = () => {
    setError(null)
    const body: api.PatchAiProviderRequest = {}
    const trimmedModel = model.trim()
    const trimmedEndpoint = endpoint.trim()
    const trimmedKey = newKey.trim()
    if (trimmedModel !== (provider.model ?? '')) body.model = trimmedModel || null
    if (isOllama && trimmedEndpoint !== (provider.endpoint ?? ''))
      body.endpoint = trimmedEndpoint || null
    if (trimmedKey) body.api_key = trimmedKey
    patchMutation.mutate(body)
  }

  return (
    <tr style={{ borderTop: '1px solid var(--aurora-divider)', background: 'rgba(15,164,171,0.02)' }}>
      <td colSpan={6} style={{ padding: '16px 18px' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, maxWidth: 560 }}>
          <div style={{ display: 'grid', gridTemplateColumns: isOllama ? '1fr 1fr' : '1fr', gap: 12 }}>
            <Field label="Model">
              <AuroraInput
                type="text"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder={
                  provider.provider === 'claude'
                    ? 'claude-opus-4-8'
                    : provider.provider === 'openai'
                      ? 'gpt-4o-mini'
                      : 'Required'
                }
              />
            </Field>
            {isOllama && (
              <Field label="Endpoint URL">
                <AuroraInput
                  type="text"
                  value={endpoint}
                  onChange={(e) => setEndpoint(e.target.value)}
                  placeholder="http://localhost:11434/v1"
                />
              </Field>
            )}
          </div>

          <Field label={provider.has_key ? 'Rotate API Key' : 'API Key'}>
            <AuroraInput
              type="password"
              value={newKey}
              onChange={(e) => setNewKey(e.target.value)}
              placeholder={
                provider.has_key
                  ? '•••••••• (leave blank to keep current key)'
                  : 'Enter key — write-only; stored encrypted'
              }
              autoComplete="new-password"
            />
          </Field>

          <TestStatus status={testStatus} />
          {error && <p style={{ fontSize: 12, color: 'var(--aurora-danger)', margin: 0 }}>{error}</p>}

          <div style={{ display: 'flex', gap: 8 }}>
            <Button
              variant="ghost"
              size="sm"
              disabled={testMutation.isPending || patchMutation.isPending}
              onClick={() => {
                setError(null)
                setTestStatus(null)
                testMutation.mutate()
              }}
            >
              {testMutation.isPending ? 'Testing…' : 'Test connection'}
            </Button>
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
// Provider table row
// ---------------------------------------------------------------------------

function ProviderRow({ provider }: { provider: api.AiProviderOut }) {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const enableMutation = useMutation({
    mutationFn: (enabled: boolean) => api.enableAiProvider(provider.id, { enabled }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['ai-providers'] }),
    onError: (err) =>
      setError(err instanceof Error ? err.message : 'Failed to toggle enable.'),
  })

  const deleteMutation = useMutation({
    mutationFn: () => api.deleteAiProvider(provider.id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['ai-providers'] }),
    onError: (err) =>
      setError(err instanceof Error ? err.message : 'Failed to delete.'),
  })

  const providerLabel =
    provider.provider === 'openai'
      ? 'OpenAI'
      : provider.provider.charAt(0).toUpperCase() + provider.provider.slice(1)

  return (
    <>
      <TableRow>
        <Td>
          <Badge variant="accent">{providerLabel}</Badge>
        </Td>
        <Td style={{ color: 'var(--aurora-muted)' }}>
          {provider.model ?? <span style={{ fontStyle: 'italic', opacity: 0.6 }}>default</span>}
        </Td>
        <Td style={{ color: 'var(--aurora-muted)' }}>
          {provider.endpoint ?? (
            provider.provider === 'ollama' ? (
              <span style={{ color: '#D97706', fontSize: 12 }}>No endpoint set</span>
            ) : '—'
          )}
        </Td>
        <Td>
          <Badge variant={provider.has_key ? 'success' : 'muted'}>
            {provider.has_key ? 'Key set' : 'No key'}
          </Badge>
        </Td>
        <Td>
          <AuroraToggle
            checked={provider.enabled}
            onChange={(v) => {
              setError(null)
              enableMutation.mutate(v)
            }}
            disabled={enableMutation.isPending}
            ariaLabel={provider.enabled ? 'Disable provider' : 'Enable provider'}
          />
        </Td>
        <Td>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
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
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setConfirmDelete(false)}
                >
                  Cancel
                </Button>
              </span>
            ) : (
              <Button
                variant="danger"
                size="sm"
                onClick={() => setConfirmDelete(true)}
              >
                Delete
              </Button>
            )}
          </div>

          {error && (
            <p style={{ marginTop: 4, fontSize: 11, color: 'var(--aurora-danger)' }}>{error}</p>
          )}
        </Td>
      </TableRow>

      {editing && <EditPanel provider={provider} onClose={() => setEditing(false)} />}
    </>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const COLUMNS = ['Provider', 'Model', 'Endpoint', 'Key', 'Enabled', 'Actions']

export function AiProvidersPage() {
  const [showAdd, setShowAdd] = useState(false)

  const { data: providers = [], isLoading, isError, error } = useQuery({
    queryKey: ['ai-providers'],
    queryFn: api.listAiProviders,
  })

  return (
    <AdminPage>
      <PageHeader
        title="AI Providers"
        description="Configure AI providers for tag suggestions and description assistance in the import wizard. API keys are stored encrypted and never returned in responses."
        meta={isLoading ? undefined : `${providers.length} provider${providers.length === 1 ? '' : 's'}`}
        actions={
          !showAdd ? (
            <Button onClick={() => setShowAdd(true)}>
              <Plus size={14} />
              Add Provider
            </Button>
          ) : undefined
        }
      />

      {showAdd && <AddProviderForm onClose={() => setShowAdd(false)} />}

      {isError && (
        <div style={{ fontSize: 12, color: 'var(--aurora-danger)' }}>
          {error instanceof Error ? error.message : 'Failed to load providers.'}
        </div>
      )}

      <DataTable
        columns={COLUMNS}
        isLoading={isLoading}
        isEmpty={!isLoading && !isError && providers.length === 0}
        emptyMessage="No AI providers configured. Add a provider to enable AI-assisted tagging."
      >
        {providers.map((p) => (
          <ProviderRow key={p.id} provider={p} />
        ))}
      </DataTable>
    </AdminPage>
  )
}
