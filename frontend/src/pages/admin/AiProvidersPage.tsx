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
 */

import React, { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as api from '@/lib/api'

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
    <div className="rounded-lg border border-border bg-card p-5 space-y-4">
      <h3 className="text-sm font-semibold">Add AI Provider</h3>

      {/* Provider type selector */}
      <div>
        <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Provider type
        </label>
        <div className="flex gap-2">
          {(['claude', 'openai', 'ollama'] as ProviderType[]).map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => {
                setProvider(p)
                setModel('')
                setEndpoint('')
              }}
              className={`rounded-md border px-3 py-1.5 text-sm font-medium transition-colors capitalize ${
                provider === p
                  ? 'bg-primary text-primary-foreground border-primary'
                  : 'bg-background border-border text-muted-foreground hover:bg-accent'
              }`}
            >
              {p === 'openai' ? 'OpenAI' : p.charAt(0).toUpperCase() + p.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {/* Model */}
      <div>
        <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Model
        </label>
        <input
          type="text"
          value={model}
          onChange={(e) => setModel(e.target.value)}
          placeholder={def.placeholderModel || 'Required for Ollama'}
          className="input-base w-full text-sm"
        />
        {!def.needsEndpoint && !model && (
          <p className="mt-0.5 text-xs text-muted-foreground">
            Leave blank to use default: {def.placeholderModel}
          </p>
        )}
      </div>

      {/* Endpoint — only shown for Ollama */}
      {def.needsEndpoint && (
        <div>
          <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Endpoint URL
          </label>
          <input
            type="text"
            value={endpoint}
            onChange={(e) => setEndpoint(e.target.value)}
            placeholder="http://localhost:11434/v1"
            className="input-base w-full text-sm"
          />
        </div>
      )}

      {/* API Key */}
      <div>
        <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-muted-foreground">
          API Key
        </label>
        <input
          type="password"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          placeholder="Enter key — write-only; stored encrypted"
          autoComplete="new-password"
          className="input-base w-full text-sm"
        />
      </div>

      {/* Enabled toggle */}
      <label className="flex cursor-pointer items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) => setEnabled(e.target.checked)}
          className="h-4 w-4 rounded border-border accent-primary"
        />
        Enable immediately
      </label>

      {/* Test feedback */}
      {testStatus && (
        <p
          className={`text-xs ${
            testStatus.startsWith('✓')
              ? 'text-green-700 dark:text-green-400'
              : 'text-red-600 dark:text-red-400'
          }`}
        >
          {testStatus}
        </p>
      )}

      {/* Error */}
      {error && (
        <p className="text-xs text-red-600 dark:text-red-400">{error}</p>
      )}

      {/* Actions */}
      <div className="flex gap-2">
        <button
          type="button"
          disabled={testMutation.isPending || createMutation.isPending}
          onClick={() => {
            setError(null)
            testMutation.mutate()
          }}
          className="rounded-md border border-border px-3 py-1.5 text-xs hover:bg-accent disabled:opacity-50 transition-colors"
        >
          {testMutation.isPending ? 'Testing…' : 'Test connection'}
        </button>
        <button
          type="button"
          disabled={createMutation.isPending || testMutation.isPending}
          onClick={() => {
            setError(null)
            createMutation.mutate()
          }}
          className="rounded-md bg-primary px-4 py-1.5 text-xs text-primary-foreground hover:opacity-90 disabled:opacity-50 transition-colors"
        >
          {createMutation.isPending ? 'Saving…' : 'Add Provider'}
        </button>
        <button
          type="button"
          onClick={onClose}
          className="rounded-md border border-border px-3 py-1.5 text-xs hover:bg-accent transition-colors"
        >
          Cancel
        </button>
      </div>
    </div>
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
    mutationFn: (body: api.PatchAiProviderRequest) =>
      api.patchAiProvider(provider.id, body),
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
    <tr className="border-b border-border bg-muted/10">
      <td colSpan={6} className="px-4 py-4">
        <div className="space-y-3 max-w-xl">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">
                Model
              </label>
              <input
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
                className="input-base w-full text-sm"
              />
            </div>
            {isOllama && (
              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">
                  Endpoint URL
                </label>
                <input
                  type="text"
                  value={endpoint}
                  onChange={(e) => setEndpoint(e.target.value)}
                  placeholder="http://localhost:11434/v1"
                  className="input-base w-full text-sm"
                />
              </div>
            )}
            <div className={isOllama ? '' : 'col-span-2'}>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">
                {provider.has_key ? 'Rotate API Key' : 'API Key'}
              </label>
              <input
                type="password"
                value={newKey}
                onChange={(e) => setNewKey(e.target.value)}
                placeholder={
                  provider.has_key
                    ? '•••••••• (leave blank to keep current key)'
                    : 'Enter key — write-only; stored encrypted'
                }
                autoComplete="new-password"
                className="input-base w-full text-sm"
              />
            </div>
          </div>

          {testStatus && (
            <p
              className={`text-xs ${
                testStatus.startsWith('✓')
                  ? 'text-green-700 dark:text-green-400'
                  : 'text-red-600 dark:text-red-400'
              }`}
            >
              {testStatus}
            </p>
          )}
          {error && (
            <p className="text-xs text-red-600 dark:text-red-400">{error}</p>
          )}

          <div className="flex gap-2">
            <button
              type="button"
              disabled={testMutation.isPending || patchMutation.isPending}
              onClick={() => {
                setError(null)
                setTestStatus(null)
                testMutation.mutate()
              }}
              className="rounded-md border border-border px-3 py-1.5 text-xs hover:bg-accent disabled:opacity-50 transition-colors"
            >
              {testMutation.isPending ? 'Testing…' : 'Test connection'}
            </button>
            <button
              type="button"
              disabled={patchMutation.isPending}
              onClick={handleSave}
              className="rounded-md bg-primary px-3 py-1.5 text-xs text-primary-foreground hover:opacity-90 disabled:opacity-50 transition-colors"
            >
              {patchMutation.isPending ? 'Saving…' : 'Save changes'}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-border px-3 py-1.5 text-xs hover:bg-accent transition-colors"
            >
              Cancel
            </button>
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
    mutationFn: (enabled: boolean) =>
      api.enableAiProvider(provider.id, { enabled }),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ['ai-providers'] }),
    onError: (err) =>
      setError(err instanceof Error ? err.message : 'Failed to toggle enable.'),
  })

  const deleteMutation = useMutation({
    mutationFn: () => api.deleteAiProvider(provider.id),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ['ai-providers'] }),
    onError: (err) =>
      setError(err instanceof Error ? err.message : 'Failed to delete.'),
  })

  const providerLabel =
    provider.provider === 'openai' ? 'OpenAI' : provider.provider.charAt(0).toUpperCase() + provider.provider.slice(1)

  return (
    <>
      <tr className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors">
        {/* Provider badge */}
        <td className="px-4 py-3">
          <span className="inline-flex items-center rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-medium text-primary">
            {providerLabel}
          </span>
        </td>

        {/* Model */}
        <td className="px-4 py-3 text-sm text-muted-foreground">
          {provider.model ?? (
            <span className="italic text-muted-foreground/60">default</span>
          )}
        </td>

        {/* Endpoint */}
        <td className="px-4 py-3 text-sm text-muted-foreground">
          {provider.endpoint ?? (
            provider.provider === 'ollama' ? (
              <span className="text-amber-600 dark:text-amber-400 text-xs">
                No endpoint set
              </span>
            ) : (
              '—'
            )
          )}
        </td>

        {/* Key badge */}
        <td className="px-4 py-3">
          <span
            className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
              provider.has_key
                ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
                : 'bg-muted text-muted-foreground'
            }`}
          >
            {provider.has_key ? 'Key set' : 'No key'}
          </span>
        </td>

        {/* Enabled toggle */}
        <td className="px-4 py-3">
          <button
            type="button"
            disabled={enableMutation.isPending}
            onClick={() => {
              setError(null)
              enableMutation.mutate(!provider.enabled)
            }}
            className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors focus-visible:outline-none disabled:opacity-50 ${
              provider.enabled ? 'bg-primary' : 'bg-muted'
            }`}
            aria-label={provider.enabled ? 'Disable provider' : 'Enable provider'}
            title={provider.enabled ? 'Click to disable' : 'Click to enable'}
          >
            <span
              className={`pointer-events-none inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform ${
                provider.enabled ? 'translate-x-4' : 'translate-x-0.5'
              }`}
            />
          </button>
        </td>

        {/* Actions */}
        <td className="px-4 py-3">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => {
                setEditing((v) => !v)
                setError(null)
              }}
              className="text-xs text-muted-foreground hover:text-foreground underline"
            >
              {editing ? 'Collapse' : 'Edit'}
            </button>

            {confirmDelete ? (
              <span className="flex items-center gap-1.5 text-xs">
                <span className="text-muted-foreground">Sure?</span>
                <button
                  type="button"
                  disabled={deleteMutation.isPending}
                  onClick={() => deleteMutation.mutate()}
                  className="text-red-600 hover:text-red-700 font-medium disabled:opacity-50"
                >
                  {deleteMutation.isPending ? 'Deleting…' : 'Confirm'}
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
                onClick={() => setConfirmDelete(true)}
                className="text-xs text-red-500 hover:text-red-700 underline"
              >
                Delete
              </button>
            )}
          </div>

          {error && (
            <p className="mt-1 text-xs text-red-600 dark:text-red-400">{error}</p>
          )}
        </td>
      </tr>

      {editing && (
        <EditPanel
          provider={provider}
          onClose={() => setEditing(false)}
        />
      )}
    </>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function AiProvidersPage() {
  const [showAdd, setShowAdd] = useState(false)

  const {
    data: providers = [],
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: ['ai-providers'],
    queryFn: api.listAiProviders,
  })

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">AI Providers</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Configure AI providers for tag suggestions and description assistance
            in the import wizard. API keys are stored encrypted and never
            returned in responses.
          </p>
        </div>
        {!showAdd && (
          <button
            type="button"
            onClick={() => setShowAdd(true)}
            className="shrink-0 rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground hover:opacity-90 transition-colors"
          >
            + Add Provider
          </button>
        )}
      </div>

      {/* Inline add form */}
      {showAdd && <AddProviderForm onClose={() => setShowAdd(false)} />}

      {/* Loading / error */}
      {isLoading && (
        <p className="text-sm text-muted-foreground">Loading…</p>
      )}
      {isError && (
        <p className="text-sm text-red-600">
          {error instanceof Error ? error.message : 'Failed to load providers.'}
        </p>
      )}

      {/* Empty state */}
      {!isLoading && !isError && providers.length === 0 && !showAdd && (
        <div className="rounded-lg border border-dashed border-border py-16 text-center">
          <p className="text-muted-foreground">No AI providers configured.</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Add a provider to enable AI-assisted tagging and description cleanup
            in the import wizard.
          </p>
        </div>
      )}

      {/* Provider table */}
      {providers.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50">
              <tr>
                {['Provider', 'Model', 'Endpoint', 'Key', 'Enabled', 'Actions'].map(
                  (h) => (
                    <th
                      key={h}
                      className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground"
                    >
                      {h}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {providers.map((p) => (
                <ProviderRow key={p.id} provider={p} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
